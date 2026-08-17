"""
test_anomaly_pipeline.py - Anomaly detection pipeline smoke tests
"""

import numpy as np
import pandas as pd
import pytest
from services.aiconnex_ml.anomaly.threshold import ThresholdCalibrator
from services.aiconnex_ml.anomaly.evaluation import compute_anomaly_metrics
from services.aiconnex_ml.anomaly.drift import AnomalyDriftPolicy, compute_psi


def _make_anomaly_data(n_normal=400, n_anomaly=20, n_features=8, random_seed=42):
    rng = np.random.default_rng(random_seed)
    X_normal = rng.standard_normal((n_normal, n_features))
    X_anomaly = rng.standard_normal((n_anomaly, n_features)) * 3 + 5  # shifted distribution
    X_all = np.vstack([X_normal, X_anomaly])
    y_all = np.array([0] * n_normal + [1] * n_anomaly)
    return X_all, y_all


@pytest.mark.tier2
def test_threshold_percentile_calibration():
    rng = np.random.default_rng(0)
    scores = rng.standard_normal(500)
    manifest = {
        "threshold_config": {"method": "percentile", "percentile": 95.0},
        "results": {}
    }
    cal = ThresholdCalibrator(manifest)
    threshold, report = cal.calibrate(scores)
    expected = float(np.percentile(scores, 95.0))
    assert abs(threshold - expected) < 1e-6
    assert report["method"] == "percentile"


def test_threshold_sme_override():
    manifest = {
        "threshold_config": {"method": "sme_override", "sme_override_threshold": 2.5},
        "results": {}
    }
    cal = ThresholdCalibrator(manifest)
    threshold, report = cal.calibrate(np.random.rand(100))
    assert threshold == 2.5
    assert report["method"] == "sme_override"


def test_anomaly_metrics_with_labels():
    rng = np.random.default_rng(42)
    y_true = np.array([0] * 90 + [1] * 10)
    scores = np.concatenate([rng.uniform(0, 0.5, 90), rng.uniform(0.7, 1.0, 10)])
    y_pred = (scores > 0.6).astype(int)
    metrics = compute_anomaly_metrics(y_true, y_pred, scores)
    assert "precision" in metrics
    assert "recall" in metrics
    assert "pr_auc" in metrics
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0


def test_psi_stable_distributions():
    rng = np.random.default_rng(0)
    d1 = rng.standard_normal(500)
    d2 = rng.standard_normal(500)  # same distribution
    psi = compute_psi(d1, d2)
    assert psi < 0.1  # stable


def test_psi_shifted_distributions():
    rng = np.random.default_rng(0)
    d1 = rng.standard_normal(500)
    d2 = rng.standard_normal(500) + 3  # strongly shifted
    psi = compute_psi(d1, d2)
    assert psi > 0.2  # significant drift


def test_drift_policy_feature_shift_triggers_retrain():
    manifest = {
        "drift_policy": {
            "anomaly_drift": {
                "psi_threshold": 0.2,
                "action_routing": {
                    "score_distribution_shifted_only": "recalibrate_threshold",
                    "feature_distribution_shifted": "retrain_normal_model",
                }
            }
        },
        "monitoring": {}
    }
    rng = np.random.default_rng(42)
    # Baseline features
    baseline_feats = rng.standard_normal((300, 5))
    # Current features: strongly shifted
    current_feats = rng.standard_normal((300, 5)) + 4

    baseline_scores = rng.standard_normal(300)
    current_scores = rng.standard_normal(300)  # scores stable

    policy = AnomalyDriftPolicy(manifest)
    action, report = policy.evaluate(baseline_scores, current_scores, baseline_feats, current_feats)
    assert action == "retrain_normal_model"
    assert report["features_drifted"] is True
