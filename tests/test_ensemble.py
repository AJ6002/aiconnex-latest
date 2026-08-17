# tests/test_ensemble.py
"""Tests for the StackedEnsembleMetaLearner (Phase 5c)."""

from __future__ import annotations
import numpy as np
import pytest
from services.aiconnex_ml.shared.ensemble import StackedEnsembleMetaLearner


def test_fit_and_predict_basic():
    """Ensemble of 3 base models on 100 samples should produce predictions."""
    np.random.seed(42)
    N, K = 100, 3
    y_true = np.random.randn(N) * 10 + 50
    # Base model predictions — each is y_true + noise
    oof = np.column_stack([y_true + np.random.randn(N) * s for s in [2, 5, 3]])

    meta = StackedEnsembleMetaLearner()
    assert meta.is_fitted is False

    meta.fit(oof, y_true)
    assert meta.is_fitted is True

    preds = meta.predict(oof)
    assert preds.shape == (N,)
    # Ensemble should be at least as good as best base model
    base_maes = [np.mean(np.abs(oof[:, k] - y_true)) for k in range(K)]
    ensemble_mae = np.mean(np.abs(preds - y_true))
    assert ensemble_mae <= max(base_maes) * 1.1  # within 10% tolerance


def test_weights_are_non_negative():
    """All meta-learner weights must satisfy w_k >= 0."""
    np.random.seed(0)
    N = 50
    y_true = np.random.randn(N) * 5
    oof = np.column_stack([y_true + np.random.randn(N) * s for s in [1, 3]])

    meta = StackedEnsembleMetaLearner()
    meta.fit(oof, y_true)
    weights = meta.get_weights()

    assert weights.shape == (2,)
    assert np.all(weights >= 0), f"Negative weights found: {weights}"


def test_predict_before_fit_raises():
    """Calling predict() before fit() should raise a RuntimeError."""
    meta = StackedEnsembleMetaLearner()
    with pytest.raises(RuntimeError, match="not fitted"):
        meta.predict(np.array([[1, 2]]))


def test_get_weights_before_fit_raises():
    """Calling get_weights() before fit() should raise a RuntimeError."""
    meta = StackedEnsembleMetaLearner()
    with pytest.raises(RuntimeError, match="not fitted"):
        meta.get_weights()


def test_single_model_passthrough():
    """With K=1 base model, the meta-learner should effectively pass it through."""
    np.random.seed(7)
    N = 30
    y_true = np.arange(N, dtype=float)
    oof = y_true.reshape(-1, 1) + np.random.randn(N, 1) * 0.1

    meta = StackedEnsembleMetaLearner()
    meta.fit(oof, y_true)
    preds = meta.predict(oof)

    assert np.allclose(preds, oof.ravel(), atol=0.5)


def test_minimum_two_samples():
    """Meta-learner requires at least 2 samples to fit."""
    meta = StackedEnsembleMetaLearner()
    with pytest.raises(ValueError, match="at least 2"):
        meta.fit(np.array([[1.0]]), np.array([1.0]))
