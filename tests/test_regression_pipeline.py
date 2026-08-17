"""
test_regression_pipeline.py - End-to-end regression pipeline smoke test
Uses synthetic data so it runs without any external files.
"""

import numpy as np
import pandas as pd
import pytest
from services.aiconnex_ml.regression.baselines import run_baselines
from services.aiconnex_ml.regression.evaluation import compute_regression_metrics
from services.aiconnex_ml.regression.robustness import run_robustness_tests
from services.aiconnex_ml.regression.losses import asymmetric_rul_score


def _make_regression_data(n_train=300, n_val=80, n_test=80, n_features=10):
    rng = np.random.default_rng(42)
    X_train = rng.standard_normal((n_train, n_features))
    X_val = rng.standard_normal((n_val, n_features))
    X_test = rng.standard_normal((n_test, n_features))
    w = rng.standard_normal(n_features)
    y_train = X_train @ w + rng.standard_normal(n_train) * 0.1
    y_val = X_val @ w + rng.standard_normal(n_val) * 0.1
    y_test = X_test @ w + rng.standard_normal(n_test) * 0.1
    return X_train, y_train, X_val, y_val, X_test, y_test


def _make_manifest():
    return {
        "ml_task": "regression",
        "label_contract": {"regime": "continuous", "target_column": "target", "target_type": "scalar"},
        "quality_gates": {
            "family": "regression",
            "regression_gates": {"robustness_noise_degradation_pct": 50.0}
        },
    }


@pytest.mark.tier2
def test_baselines_run_and_rank():
    X_train, y_train, X_val, y_val, X_test, y_test = _make_regression_data()
    manifest = _make_manifest()
    results = run_baselines(
        X_train, y_train, X_val, y_val,
        candidate_algorithms=["Linear Regression", "Ridge Regression", "Random Forest"],
        manifest=manifest,
    )
    assert len(results) == 3
    assert results[0]["val_rmse"] <= results[-1]["val_rmse"]  # sorted by RMSE ascending


def test_evaluation_metrics():
    y_true = np.array([100.0, 80.0, 60.0, 40.0, 20.0])
    y_pred = np.array([95.0, 85.0, 55.0, 45.0, 22.0])
    metrics = compute_regression_metrics(y_true, y_pred)
    assert "rmse" in metrics
    assert "r2" in metrics
    assert metrics["r2"] >= 0.0


def test_asymmetric_rul_score():
    y_true = np.array([100.0, 50.0, 10.0])
    # Perfect predictions
    perfect = asymmetric_rul_score(y_true, y_true)
    assert perfect == 0.0

    # Late predictions should score higher than early
    y_late = y_true + 20
    y_early = y_true - 20
    score_late = asymmetric_rul_score(y_true, y_late)
    score_early = asymmetric_rul_score(y_true, y_early)
    assert score_late > score_early  # Late prediction is penalized more


def test_robustness_tests():
    X_train, y_train, X_val, y_val, X_test, y_test = _make_regression_data()
    manifest = _make_manifest()
    results = run_baselines(X_train, y_train, X_val, y_val, ["Ridge Regression"], manifest)
    model = results[0]["model"]
    report = run_robustness_tests(model, X_test, y_test, manifest)
    assert "noise_tests" in report
    assert "dropout_tests" in report
    assert len(report["noise_tests"]) == 4
