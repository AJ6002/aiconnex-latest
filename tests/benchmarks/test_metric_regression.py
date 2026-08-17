"""
test_metric_regression.py - Version-over-Version Metric Baseline Tracking
===========================================================================
Compares the metrics in latest run reports (outputs/regression/reports/ and outputs/anomaly/reports/)
against baseline tolerances in tests/benchmarks/baseline_metrics.json to prevent performance regressions.
"""

from __future__ import annotations
import os
import json
import pytest


BASELINE_JSON_PATH = "tests/benchmarks/baseline_metrics.json"


@pytest.fixture
def baselines():
    assert os.path.exists(BASELINE_JSON_PATH), f"Baseline metrics file missing: {BASELINE_JSON_PATH}"
    with open(BASELINE_JSON_PATH, "r") as f:
        return json.load(f)


@pytest.mark.tier2
def test_regression_metric_baseline(baselines):
    """Assert latest regression run metrics do not regress past baseline tolerance bounds."""
    cfg = baselines["regression"]
    report_path = cfg["report_path"]

    if not os.path.exists(report_path):
        pytest.skip(f"Regression report not found: {report_path}. Run regression runner first.")
    with open(report_path, "r") as f:
        report = json.load(f)

    algo = report.get("best_algorithm")
    assert algo == cfg["expected_best_algorithm"], f"Algorithm changed from {cfg['expected_best_algorithm']} to {algo}"
    for metric_name, bound in cfg["tolerances"].items():
        actual = report["metrics"].get(metric_name)
        assert actual is not None, f"Metric '{metric_name}' missing from regression report."
        if "max" in bound:
            assert actual <= bound["max"], f"Regression metric {metric_name}={actual} exceeded max tolerance {bound['max']}"
        if "min" in bound:
            assert actual >= bound["min"], f"Regression metric {metric_name}={actual} below min tolerance {bound['min']}"


@pytest.mark.tier2
def test_anomaly_metric_baseline(baselines):
    """Assert latest anomaly run metrics do not regress past baseline tolerance bounds."""
    cfg = baselines["anomaly"]
    report_path = cfg["report_path"]

    if not os.path.exists(report_path):
        pytest.skip(f"Anomaly report not found: {report_path}. Run anomaly runner first.")
    with open(report_path, "r") as f:
        report = json.load(f)

    algo = report.get("best_algorithm")
    assert algo == cfg["expected_best_algorithm"], f"Algorithm changed from {cfg['expected_best_algorithm']} to {algo}"

    eval_data = report.get("evaluation", {})
    p99 = eval_data.get("p99_score", 0.0)

    assert p99 <= cfg["max_allowed_p99_score"], f"Anomaly p99 score shifted too high: got {p99:.4f}, max allowed {cfg['max_allowed_p99_score']}"
