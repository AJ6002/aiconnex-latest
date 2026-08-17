"""
Scenario Test 4: Changepoint / Concept Drift Detection
=======================================================
Real scenario: A pump is running normally for 3 months. Then a component
degrades and the process distribution shifts gradually over 2 weeks
(higher average temperature, wider variance in flow, subtle vibration shift).
This is NOT a single-point anomaly - it's a concept drift / changepoint.

The pipeline must detect this via Population Stability Index (PSI) and
KS-test on feature distributions, and correctly route to the appropriate
drift action.

This test verifies:
  1. PSI < 0.1 on identical distributions (stable - no action).
  2. PSI > 0.2 on strongly shifted distributions (drift detected).
  3. AnomalyDriftPolicy correctly routes to "recalibrate_threshold"
     when only the anomaly SCORE distribution shifts (features stable).
  4. AnomalyDriftPolicy correctly routes to "retrain_normal_model"
     when the input FEATURE distribution itself has shifted.
  5. Regression drift policy correctly triggers "retrain" when RMSE
     on the holdout set exceeds the allowed degradation threshold.
"""

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.tier3

from services.aiconnex_ml.anomaly.drift import AnomalyDriftPolicy, compute_psi, run_ks_test
from services.aiconnex_ml.regression.drift import RegressionDriftPolicy


# -- Helpers --------------------------------------------------------------------

def stable_normal(n: int, mu: float = 0, sigma: float = 1, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(mu, sigma, n)


def shifted_normal(n: int, mu_shift: float = 5, sigma: float = 1, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).normal(mu_shift, sigma, n)


def make_anomaly_drift_manifest(psi_threshold: float = 0.2):
    return {
        "drift_policy": {
            "anomaly_drift": {
                "psi_threshold": psi_threshold,
                "action_routing": {
                    "score_distribution_shifted_only": "recalibrate_threshold",
                    "feature_distribution_shifted":    "retrain_normal_model",
                },
            },
        },
        "monitoring": {},
    }


def make_regression_drift_manifest(rmse_threshold_pct: float = 20.0):
    return {
        "drift_policy": {
            "regression_drift": {
                "trigger_threshold_rmse_increase_pct": rmse_threshold_pct,
                "action": "retrain",
            },
        },
        "monitoring": {},
        "results": {},
    }


# -- PSI Tests -----------------------------------------------------------------

class TestPSI:
    def test_psi_near_zero_for_identical_distribution(self):
        """
        PSI of a distribution against itself should be essentially 0.
        """
        data = stable_normal(1000)
        psi = compute_psi(data, data)
        assert psi < 0.05, f"PSI of identical distributions should be near 0, got {psi:.4f}"

    def test_psi_near_zero_for_same_distribution_different_samples(self):
        """
        PSI < 0.10 when two samples come from the same underlying distribution.
        """
        d1 = stable_normal(1000, seed=10)
        d2 = stable_normal(1000, seed=20)
        psi = compute_psi(d1, d2)
        assert psi < 0.10, (
            f"Same-distribution PSI should be < 0.10 (stable). Got {psi:.4f}"
        )

    def test_psi_above_02_for_mean_shift(self):
        """
        A 5-sigma mean shift must produce PSI > 0.2 (significant drift).
        """
        baseline = stable_normal(1000)
        current  = shifted_normal(1000, mu_shift=5.0)
        psi = compute_psi(baseline, current)
        assert psi > 0.2, (
            f"5-sigma mean shift should produce PSI > 0.2 (significant drift). Got {psi:.4f}"
        )

    def test_psi_above_02_for_variance_shift(self):
        """
        A large variance increase (sigma x5) must also produce PSI > 0.2.
        """
        rng = np.random.default_rng(42)
        baseline = rng.normal(0, 1, 1000)
        current  = rng.normal(0, 5, 1000)     # same mean, 5x wider spread
        psi = compute_psi(baseline, current)
        assert psi > 0.2, (
            f"Variance shift (sigma x5) should produce PSI > 0.2. Got {psi:.4f}"
        )

    def test_psi_monotonically_increases_with_shift_magnitude(self):
        """
        PSI must increase monotonically as the mean shift grows.
        """
        baseline = stable_normal(500)
        psi_values = [compute_psi(baseline, shifted_normal(500, mu_shift=delta, seed=delta))
                      for delta in [0, 1, 2, 4, 8]]
        for i in range(len(psi_values) - 1):
            assert psi_values[i] <= psi_values[i + 1], (
                f"PSI not monotonically increasing: {psi_values}"
            )


# -- KS-Test Tests -------------------------------------------------------------

class TestKSTest:
    def test_ks_pvalue_high_for_same_distribution(self):
        """
        KS-test p-value should be high (> 0.05) when both samples share the same distribution.
        """
        d1 = stable_normal(500, seed=1)
        d2 = stable_normal(500, seed=2)
        _, p_value = run_ks_test(d1, d2)
        assert p_value > 0.05, (
            f"KS-test p-value ({p_value:.4f}) should be > 0.05 for same-distribution samples."
        )

    def test_ks_statistic_high_for_shifted_distribution(self):
        """
        KS statistic should be high and p-value < 0.01 for a strongly shifted distribution.
        """
        baseline = stable_normal(500)
        current  = shifted_normal(500, mu_shift=10.0)
        ks_stat, p_value = run_ks_test(baseline, current)
        assert ks_stat > 0.5, f"KS statistic should be > 0.5 for 10-sigma shift. Got {ks_stat:.4f}"
        assert p_value < 0.01, f"KS p-value should be < 0.01 for 10-sigma shift. Got {p_value:.4f}"


# -- Anomaly Drift Policy Routing Tests -----------------------------------------

class TestAnomalyDriftRouting:
    def test_score_only_drift_routes_to_recalibrate(self):
        """
        If anomaly scores have shifted but feature distributions are stable,
        the correct action is 'recalibrate_threshold' - NOT retraining the model.
        """
        rng = np.random.default_rng(42)
        baseline_feats   = rng.normal(0, 1, (500, 4))
        current_feats    = rng.normal(0, 1, (500, 4))    # features stable

        baseline_scores  = rng.normal(0, 1, 500)
        current_scores   = rng.normal(5, 1, 500)          # scores strongly shifted

        manifest = make_anomaly_drift_manifest(psi_threshold=0.2)
        policy   = AnomalyDriftPolicy(manifest)
        action, report = policy.evaluate(
            baseline_scores, current_scores,
            baseline_feats, current_feats
        )

        assert action == "recalibrate_threshold", (
            f"Score-only drift should route to 'recalibrate_threshold'. Got '{action}'.\n"
            f"Report: {report}"
        )

    def test_feature_drift_routes_to_retrain(self):
        """
        If the input feature distribution itself has shifted (concept drift),
        the correct action is 'retrain_normal_model' - the threshold alone cannot fix this.
        """
        rng = np.random.default_rng(42)
        baseline_feats   = rng.normal(0, 1, (500, 4))
        current_feats    = rng.normal(0, 1, (500, 4)) + 5  # features shifted

        baseline_scores  = rng.normal(0, 1, 500)
        current_scores   = rng.normal(0, 1, 500)             # scores stable (not the point)

        manifest = make_anomaly_drift_manifest(psi_threshold=0.2)
        policy   = AnomalyDriftPolicy(manifest)
        action, report = policy.evaluate(
            baseline_scores, current_scores,
            baseline_feats, current_feats
        )

        assert action == "retrain_normal_model", (
            f"Feature distribution drift should route to 'retrain_normal_model'. Got '{action}'.\n"
            f"Report: {report}"
        )

    def test_no_drift_routes_to_none(self):
        """
        When both feature distributions and score distributions are stable,
        the drift policy must recommend no action.
        """
        rng = np.random.default_rng(0)
        feats1 = rng.normal(0, 1, (500, 4))
        feats2 = rng.normal(0, 1, (500, 4))      # same
        scores1 = rng.normal(0, 1, 500)
        scores2 = rng.normal(0, 1, 500)           # same

        manifest = make_anomaly_drift_manifest(psi_threshold=0.2)
        policy   = AnomalyDriftPolicy(manifest)
        action, report = policy.evaluate(scores1, scores2, feats1, feats2)

        assert action == "none", (
            f"Stable distributions should recommend 'none'. Got '{action}'."
        )

    def test_drift_report_contains_required_keys(self):
        """
        The drift report dict must always contain all required keys,
        regardless of which action is taken.
        """
        rng = np.random.default_rng(1)
        feats   = rng.normal(0, 1, (100, 3))
        scores  = rng.normal(0, 1, 100)

        manifest = make_anomaly_drift_manifest()
        policy   = AnomalyDriftPolicy(manifest)
        _, report = policy.evaluate(scores, scores, feats, feats)

        required_keys = {
            "score_psi", "score_ks_statistic", "score_ks_pvalue",
            "mean_feature_psi", "score_drifted", "features_drifted",
            "psi_threshold", "recommended_action", "decision",
        }
        missing = required_keys - set(report.keys())
        assert not missing, f"Drift report missing keys: {missing}"


# -- Regression Drift Policy Test -----------------------------------------------

class TestRegressionDrift:
    def test_rmse_increase_triggers_retrain(self):
        """
        If RMSE on the current holdout set has increased by more than the
        configured threshold (e.g. 20%), the regression drift policy must
        trigger a retrain.
        """
        manifest = make_regression_drift_manifest(rmse_threshold_pct=20.0)
        policy = RegressionDriftPolicy(manifest)

        action, report = policy.evaluate(
            baseline_rmse=10.0,
            current_rmse=15.0,    # 50% increase - above 20% threshold
        )
        assert action == "retrain", (
            f"RMSE increase of 50% should trigger retrain. Got '{action}'."
        )
        assert report["rmse_increase_pct"] == pytest.approx(50.0, rel=0.01)

    def test_small_rmse_change_does_not_trigger_retrain(self):
        """
        A minor RMSE change (within the tolerance band) must not trigger a retrain.
        """
        manifest = make_regression_drift_manifest(rmse_threshold_pct=20.0)
        policy = RegressionDriftPolicy(manifest)

        action, report = policy.evaluate(
            baseline_rmse=10.0,
            current_rmse=10.5,    # 5% increase - within 20% tolerance
        )
        assert action == "none", (
            f"5% RMSE increase should not trigger retrain. Got '{action}'."
        )
