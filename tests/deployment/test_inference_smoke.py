"""
test_inference_smoke.py - Production Deployment & Inference Smoke Tests
========================================================================
Validates that exported artifacts (models, scalers, thresholds, reports):
  1. Exist and pass size/integrity checks.
  2. Can be reloaded and execute single-sample inference in < 50ms.
  3. Return valid, properly typed predictions (Regression float, Anomaly binary flag).
"""

from __future__ import annotations
import os
import json
import time
import pickle
import numpy as np
import pytest


REGRESSION_MODEL_PATH = "outputs/regression/best_model.pkl"
REGRESSION_SCALER_PATH = "outputs/regression/scaler.pkl"
REGRESSION_REPORT_JSON = "outputs/regression/reports/reg_run_001_report.json"
REGRESSION_REPORT_MD   = "outputs/regression/reports/reg_run_001_report.md"

ANOMALY_MODEL_PATH = "outputs/anomaly/best_model.pkl"
ANOMALY_SCALER_PATH = "outputs/anomaly/scaler.pkl"
ANOMALY_REPORT_JSON = "outputs/anomaly/reports/anomaly_run_001_report.json"
ANOMALY_REPORT_MD   = "outputs/anomaly/reports/anomaly_run_001_report.md"


@pytest.mark.tier1
def test_regression_artifact_integrity():
    """Verify regression output files exist and are non-empty."""
    for path in [REGRESSION_MODEL_PATH, REGRESSION_SCALER_PATH]:
        if not os.path.exists(path):
            pytest.skip(f"Artifact not found: {path}. Run training pipeline first.")
        assert os.path.getsize(path) > 0, f"Artifact empty: {path}"

    if not os.path.exists(REGRESSION_REPORT_JSON):
        pytest.skip("JSON report missing. Run training pipeline first.")
    assert os.path.getsize(REGRESSION_REPORT_JSON) > 0, "JSON report empty"

    with open(REGRESSION_REPORT_JSON, "r") as f:
        report = json.load(f)

    assert "pipeline_run_id" in report, "Report missing 'pipeline_run_id'"
    assert "best_algorithm" in report, "Report missing 'best_algorithm'"
    assert "evaluation" in report, "Report missing 'evaluation'"

    assert os.path.exists(REGRESSION_REPORT_MD), "Markdown report missing"
    assert os.path.getsize(REGRESSION_REPORT_MD) > 0, "Markdown report empty"


@pytest.mark.tier1
def test_regression_inference_latency():
    """Load deployed regression model + scaler, predict on 1 sample, assert latency < 50ms."""
    if not (os.path.exists(REGRESSION_MODEL_PATH) and os.path.exists(REGRESSION_SCALER_PATH)):
        pytest.skip("Regression artifacts must exist to run inference smoke test.")

    with open(REGRESSION_SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    with open(REGRESSION_MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    n_features = scaler.mean_.shape[0]
    sample = np.random.randn(1, n_features)

    t0 = time.perf_counter()
    sample_scaled = scaler.transform(sample)
    pred = model.predict(sample_scaled)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert isinstance(pred, np.ndarray)
    assert pred.shape == (1,)
    assert not np.isnan(pred[0])
    assert latency_ms < 50.0, f"Regression inference too slow: {latency_ms:.2f}ms (threshold 50ms)"


@pytest.mark.tier1
def test_anomaly_artifact_integrity():
    """Verify anomaly output files exist and are non-empty."""
    for path in [ANOMALY_MODEL_PATH, ANOMALY_SCALER_PATH]:
        if not os.path.exists(path):
            pytest.skip(f"Artifact not found: {path}. Run training pipeline first.")
        assert os.path.getsize(path) > 0, f"Artifact empty: {path}"

    if not os.path.exists(ANOMALY_REPORT_JSON):
        pytest.skip("JSON report missing. Run training pipeline first.")
    assert os.path.getsize(ANOMALY_REPORT_JSON) > 0, "JSON report empty"

    with open(ANOMALY_REPORT_JSON, "r") as f:
        report = json.load(f)

    assert "pipeline_run_id" in report, "Report missing 'pipeline_run_id'"
    assert "best_algorithm" in report, "Report missing 'best_algorithm'"
    assert "evaluation" in report, "Report missing 'evaluation'"

    assert os.path.exists(ANOMALY_REPORT_MD), "Markdown report missing"
    assert os.path.getsize(ANOMALY_REPORT_MD) > 0, "Markdown report empty"


@pytest.mark.tier1
def test_anomaly_inference_latency():
    """Load deployed anomaly model + scaler, score 1 sample, assert latency < 50ms and valid binary alert."""
    if not (os.path.exists(ANOMALY_MODEL_PATH) and os.path.exists(ANOMALY_SCALER_PATH)):
        pytest.skip("Anomaly artifacts must exist to run inference smoke test.")

    with open(ANOMALY_SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    with open(ANOMALY_MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    n_features = scaler.mean_.shape[0]
    sample = np.random.randn(1, n_features)

    t0 = time.perf_counter()
    sample_scaled = scaler.transform(sample)
    raw_score = -model.decision_function(sample_scaled)[0]
    threshold = 0.013208 # Calibrated threshold from anomaly run
    is_anomalous = int(raw_score > threshold)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert is_anomalous in (0, 1), f"Anomaly decision must be 0 or 1, got {is_anomalous}"
    assert latency_ms < 50.0, f"Anomaly inference too slow: {latency_ms:.2f}ms (threshold 50ms)"
