"""
test_algorithm_matrix.py - Algorithm-by-Scenario Matrix Tests
==============================================================
Validates that every single algorithm in REGRESSION_REGISTRY and ANOMALY_REGISTRY:
  1. Instantiates and fits without errors on clean synthetic data.
  2. Produces valid predictions/scores with correct shapes and no NaN/Inf.
  3. Can be serialized (pickled) and reloaded to produce identical predictions.
"""

from __future__ import annotations
import pickle
import numpy as np
import pandas as pd
import pytest

from services.aiconnex_ml.regression.registry import REGRESSION_REGISTRY, get_algorithm as get_reg_algo
from services.aiconnex_ml.anomaly.registry import ANOMALY_REGISTRY, get_algorithm as get_anom_algo
from services.aiconnex_ml.anomaly.trainer import _score_model


@pytest.fixture
def synthetic_regression_data():
    """Synthetic clean 100-row dataset for regression testing."""
    np.random.seed(42)
    X = np.random.randn(100, 10)
    # Simple linear target + noise
    y = X[:, 0] * 2.0 + X[:, 1] * -1.5 + np.random.randn(100) * 0.1
    return X, y


@pytest.fixture
def synthetic_anomaly_data():
    """Synthetic clean 100-row dataset for anomaly testing."""
    np.random.seed(42)
    X = np.random.randn(100, 10)
    # 5% synthetic anomalies (spikes)
    X[:5] += 5.0
    y = np.zeros(100)
    y[:5] = 1 # 1 = anomaly, 0 = normal
    return X, y


# --- REGRESSION ALGORITHM MATRIX ---------------------------------------------

REGRESSION_ALGORITHMS = list(REGRESSION_REGISTRY.keys())


@pytest.mark.tier1
@pytest.mark.parametrize("algo_name", REGRESSION_ALGORITHMS)
def test_regression_algorithm_matrix(algo_name, synthetic_regression_data):
    X, y = synthetic_regression_data
    X_train, y_train = X[:80], y[:80]
    X_val = X[80:]

    requires = REGRESSION_REGISTRY[algo_name].get("requires")
    if requires:
        pytest.importorskip(requires)

    entry = get_reg_algo(algo_name)
    ModelClass = entry["class"]
    model = ModelClass()

    # 1. Fit
    model.fit(X_train, y_train)

    # 2. Predict
    preds = model.predict(X_val)
    assert isinstance(preds, np.ndarray), f"{algo_name} predict output must be numpy array"
    assert preds.shape == (20,), f"{algo_name} predict shape mismatch: expected (20,), got {preds.shape}"
    assert not np.isnan(preds).any(), f"{algo_name} predictions contain NaN"
    assert not np.isinf(preds).any(), f"{algo_name} predictions contain Inf"

    # 3. Serialization & Reload
    serialized = pickle.dumps(model)
    reloaded_model = pickle.loads(serialized)
    reloaded_preds = reloaded_model.predict(X_val)
    np.testing.assert_allclose(preds, reloaded_preds, rtol=1e-5, err_msg=f"{algo_name} reloaded model prediction mismatch")


# --- ANOMALY ALGORITHM MATRIX ------------------------------------------------

ANOMALY_ALGORITHMS = list(ANOMALY_REGISTRY.keys())


@pytest.mark.tier1
@pytest.mark.parametrize("algo_name", ANOMALY_ALGORITHMS)
def test_anomaly_algorithm_matrix(algo_name, synthetic_anomaly_data):
    X, y = synthetic_anomaly_data

    requires = ANOMALY_REGISTRY[algo_name].get("requires")
    if requires:
        pytest.importorskip(requires)

    entry = get_anom_algo(algo_name)
    ModelClass = entry["class"]
    model = ModelClass()
    eligible_modes = entry.get("eligible_modes", ["unsupervised"])

    # 1. Fit based on primary eligible mode
    if "semi_supervised" in eligible_modes:
        X_normal = X[y == 0] # fit on normal data only
        model.fit(X_normal)
    elif "supervised" in eligible_modes:
        model.fit(X, y)
    else:
        model.fit(X)

    # 2. Extract anomaly scores
    scores = _score_model(model, X, entry)
    assert isinstance(scores, np.ndarray), f"{algo_name} score output must be numpy array"
    assert scores.shape == (100,), f"{algo_name} score shape mismatch: expected (100,), got {scores.shape}"
    assert not np.isnan(scores).any(), f"{algo_name} scores contain NaN"
    assert not np.isinf(scores).any(), f"{algo_name} scores contain Inf"

    # 3. Serialization & Reload
    serialized = pickle.dumps(model)
    reloaded_model = pickle.loads(serialized)
    reloaded_scores = _score_model(reloaded_model, X, entry)
    np.testing.assert_allclose(scores, reloaded_scores, rtol=1e-5, err_msg=f"{algo_name} reloaded model score mismatch")
