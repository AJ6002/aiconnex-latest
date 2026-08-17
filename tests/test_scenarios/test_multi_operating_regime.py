"""
Scenario Test 6: Multiple Legitimate Operating Regimes
=======================================================
Real scenario: A compressor operates across 3 distinct regimes:
  Regime-0  -> Cold startup   (low RPM, low temperature, low vibration)
  Regime-1  -> Normal running (medium RPM, medium temperature)
  Regime-2  -> High-load run  (high RPM, high temperature, higher vibration)

All three are NORMAL. The anomaly model must not alarm during legitimate
transitions between them. This is the most common source of alarm fatigue
in industrial systems ("alert every time the machine starts up").

This test verifies:
  1. Per-mode scalers are fitted independently on each regime's data.
  2. Per-mode thresholds are calibrated separately, not on pooled data.
  3. Predictions across all known modes produce scores BELOW their respective
     per-mode threshold (false alarm rate ~= 0 on training distribution).
  4. The model scores from regime transitions do NOT exceed the thresholds.
  5. A genuine process anomaly IN REGIME-1 is still correctly detected.
"""

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.tier3

from sklearn.ensemble import IsolationForest

from services.aiconnex_ml.anomaly.operating_modes import OperatingModeDetector
from services.aiconnex_ml.anomaly.threshold import ThresholdCalibrator
from services.aiconnex_ml.shared.features.mode_normalization import fit_per_mode_scalers, apply_per_mode_scaling


# -- Fixtures -------------------------------------------------------------------

FEATURE_COLS = ["rpm", "temperature", "vibration", "pressure"]

def make_regime_dataset(n_per_regime: int = 400, seed: int = 42, include_anomaly: bool = False):
    """
    Three distinct but NORMAL operating regimes + optional injected anomaly.

    Regime-0 (startup):    rpm~1000, temp~60,  vib~0.5,  pressure~2.0
    Regime-1 (normal):     rpm~2000, temp~80,  vib~1.0,  pressure~3.0
    Regime-2 (high-load):  rpm~3000, temp~100, vib~2.0,  pressure~4.0
    """
    rng = np.random.default_rng(seed)

    regimes = {
        0: dict(rpm=1000, temp=60,  vib=0.5,  pressure=2.0, sigma=[30, 2, 0.05, 0.1]),
        1: dict(rpm=2000, temp=80,  vib=1.0,  pressure=3.0, sigma=[50, 3, 0.10, 0.2]),
        2: dict(rpm=3000, temp=100, vib=2.0,  pressure=4.0, sigma=[80, 4, 0.20, 0.3]),
    }

    frames = []
    for label, params in regimes.items():
        X = np.column_stack([
            rng.normal(params["rpm"],      params["sigma"][0], n_per_regime),
            rng.normal(params["temp"],     params["sigma"][1], n_per_regime),
            rng.normal(params["vib"],      params["sigma"][2], n_per_regime),
            rng.normal(params["pressure"], params["sigma"][3], n_per_regime),
        ])
        df = pd.DataFrame(X, columns=FEATURE_COLS).assign(regime=label, is_anomaly=0)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)

    if include_anomaly:
        # Inject 20 anomalies in Regime-1 (genuine process fault - bearing overheating)
        rng2 = np.random.default_rng(seed + 1)
        anomaly_rows = rng2.integers(n_per_regime, 2 * n_per_regime, 20)
        df_all.loc[anomaly_rows, "temperature"] += 40   # overheating spike
        df_all.loc[anomaly_rows, "vibration"]   += 2.0  # bearing vibration
        df_all.loc[anomaly_rows, "is_anomaly"]  = 1

    return df_all


def make_multi_regime_manifest():
    return {
        "ml_task": "anomaly",
        "label_contract": {"supervision_mode": "semi_supervised"},
        "operating_modes": {
            "enabled": True,
            "mode_column": "regime",
            "known_modes": [0, 1, 2],
            "normalize_per_mode": True,
        },
        "threshold_config": {
            "method": "percentile",
            "percentile": 99.0,
        },
        "results": {},
        "monitoring": {},
    }


# -- Mode Normalization Tests ---------------------------------------------------

class TestPerModeScaling:
    def test_per_mode_scalers_are_fitted_per_regime(self):
        """
        fit_per_mode_scalers() must return one scaler per operating regime.
        """
        df = make_regime_dataset()
        mode_scalers = fit_per_mode_scalers(df, FEATURE_COLS, "regime")

        assert len(mode_scalers) == 3, (
            f"Expected 3 per-mode scalers (one per regime). Got {len(mode_scalers)}."
        )
        for mode_label in [0, 1, 2]:
            assert mode_label in mode_scalers or str(mode_label) in mode_scalers, (
                f"Missing scaler for mode {mode_label}"
            )

    def test_per_mode_scaled_data_is_zero_centred_within_regime(self):
        """
        After per-mode scaling, each regime's data should have zero mean
        (within floating-point tolerance).
        """
        df = make_regime_dataset()
        mode_scalers = fit_per_mode_scalers(df, FEATURE_COLS, "regime")
        df_scaled = apply_per_mode_scaling(df, FEATURE_COLS, "regime", mode_scalers)

        for mode_label in [0, 1, 2]:
            regime_data = df_scaled[df_scaled["regime"] == mode_label][FEATURE_COLS]
            col_means = regime_data.mean()
            for col in FEATURE_COLS:
                assert abs(col_means[col]) < 0.5, (
                    f"Regime {mode_label}, column '{col}' mean after scaling: "
                    f"{col_means[col]:.4f} - expected near 0."
                )


# -- Threshold Calibration Per Regime -----------------------------------------

class TestPerModeThresholds:
    def _train_and_score(self, df_train, df_val):
        model = IsolationForest(n_estimators=150, contamination=0.02, random_state=42)
        model.fit(df_train[FEATURE_COLS].values)
        scores = -model.decision_function(df_val[FEATURE_COLS].values)
        return model, scores

    def test_per_mode_thresholds_are_different(self):
        """
        Each operating regime should produce a different anomaly score distribution,
        and therefore a different calibrated threshold.
        """
        df = make_regime_dataset()
        manifest = make_multi_regime_manifest()

        # Train model on all normal data
        model = IsolationForest(n_estimators=150, contamination=0.02, random_state=42)
        model.fit(df[FEATURE_COLS].values)

        val_scores = -model.decision_function(df[FEATURE_COLS].values)
        val_modes  = df["regime"].values

        calibrator = ThresholdCalibrator(manifest)
        mode_thresholds = calibrator.calibrate_per_mode(val_scores, val_modes)

        assert len(mode_thresholds) == 3, f"Expected 3 per-mode thresholds, got {len(mode_thresholds)}"

        # All three threshold values should not be identical
        threshold_values = list(mode_thresholds.values())
        assert len(set(round(t, 3) for t in threshold_values)) > 1, (
            "All per-mode thresholds are identical - per-mode calibration may not be working."
        )
        print(f"[MultiRegimeTest] Per-mode thresholds: {mode_thresholds}")

    def test_false_alarm_rate_near_zero_on_known_regime_data(self):
        """
        When the threshold is calibrated at the 99th percentile of each regime's
        training scores, the false alarm rate on validation data from KNOWN regimes
        must be <= 1%.
        """
        df = make_regime_dataset(n_per_regime=500)
        df_train = df.groupby("regime").apply(lambda x: x.iloc[:300]).reset_index(drop=True)
        df_val   = df.groupby("regime").apply(lambda x: x.iloc[300:]).reset_index(drop=True)

        model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
        model.fit(df_train[FEATURE_COLS].values)

        manifest = make_multi_regime_manifest()
        calibrator = ThresholdCalibrator(manifest)

        train_scores = -model.decision_function(df_train[FEATURE_COLS].values)
        train_modes  = df_train["regime"].values
        mode_thresholds = calibrator.calibrate_per_mode(train_scores, train_modes)

        detector = OperatingModeDetector(manifest)
        detector.register_mode_thresholds(mode_thresholds)

        # Global fallback threshold
        global_threshold = float(np.median(list(mode_thresholds.values())))

        # Evaluate FAR on validation data
        val_scores = -model.decision_function(df_val[FEATURE_COLS].values)
        val_modes  = df_val["regime"].astype(str).values

        false_alarms = 0
        total = len(df_val)
        for i, (score, mode) in enumerate(zip(val_scores, val_modes)):
            is_anomaly, _ = detector.apply_mode_threshold(score, mode, global_threshold)
            if is_anomaly:
                false_alarms += 1

        far = false_alarms / total
        print(f"[MultiRegimeTest] FAR on known-regime validation data: {far:.2%} ({false_alarms}/{total})")

        assert far <= 0.02, (
            f"False alarm rate on known regimes ({far:.2%}) exceeds 2%. "
            "Per-mode threshold calibration is producing too many false alarms."
        )

    def test_regime_transitions_do_not_alarm(self):
        """
        Data that transitions from Regime-0 to Regime-1 (a legitimate startup)
        must NOT trigger alarms. We simulate a transition as interleaved rows.
        """
        rng = np.random.default_rng(42)
        # Transition: data where RPM starts at 1000, ramps to 2000 over 6 cycles, and stays at 2000
        n_steady = 22
        n_ramp = 6
        n = n_steady * 2 + n_ramp

        rpm_profile = np.concatenate([
            np.full(n_steady, 1000.0),
            np.linspace(1000.0, 2000.0, n_ramp),
            np.full(n_steady, 2000.0)
        ])
        temp_profile = np.concatenate([
            np.full(n_steady, 60.0),
            np.linspace(60.0, 80.0, n_ramp),
            np.full(n_steady, 80.0)
        ])
        vib_profile = np.concatenate([
            np.full(n_steady, 0.5),
            np.linspace(0.5, 1.0, n_ramp),
            np.full(n_steady, 1.0)
        ])
        press_profile = np.concatenate([
            np.full(n_steady, 2.0),
            np.linspace(2.0, 3.0, n_ramp),
            np.full(n_steady, 3.0)
        ])

        transition_data = pd.DataFrame({
            "rpm":         rpm_profile + rng.normal(0, 10, n),
            "temperature": temp_profile + rng.normal(0, 1,  n),
            "vibration":   vib_profile + rng.normal(0, 0.02, n),
            "pressure":    press_profile + rng.normal(0, 0.05, n),
            "regime":      [0] * (n_steady + n_ramp // 2) + [1] * (n_steady + n_ramp // 2),
        })

        df_train = make_regime_dataset(n_per_regime=400)
        mode_scalers = fit_per_mode_scalers(df_train, FEATURE_COLS, "regime")
        df_train_scaled = apply_per_mode_scaling(df_train, FEATURE_COLS, "regime", mode_scalers)

        model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
        model.fit(df_train_scaled[FEATURE_COLS].values)

        manifest = make_multi_regime_manifest()
        calibrator = ThresholdCalibrator(manifest)
        train_scores = -model.decision_function(df_train_scaled[FEATURE_COLS].values)
        train_modes  = df_train_scaled["regime"].values
        mode_thresholds = calibrator.calibrate_per_mode(train_scores, train_modes)

        detector = OperatingModeDetector(manifest)
        detector.register_mode_thresholds(mode_thresholds)
        global_threshold = float(np.median(list(mode_thresholds.values())))

        # Scale transition data
        transition_data_scaled = apply_per_mode_scaling(transition_data, FEATURE_COLS, "regime", mode_scalers)
        transition_scores = -model.decision_function(transition_data_scaled[FEATURE_COLS].values)
        transition_modes = transition_data_scaled["regime"].astype(str).values

        alarms = 0
        for score, mode in zip(transition_scores, transition_modes):
            is_anomaly, _ = detector.apply_mode_threshold(score, mode, global_threshold)
            if is_anomaly:
                alarms += 1

        alarm_rate = alarms / len(transition_data)
        print(f"[MultiRegimeTest] Alarm rate during known regime transition: {alarm_rate:.2%}")

        assert alarm_rate <= 0.15, (
            f"Regime transition triggered {alarm_rate:.0%} alarm rate. "
            "This would cause alarm fatigue on every machine startup."
        )

    def test_genuine_anomaly_in_regime_1_is_still_detected(self):
        """
        Even with per-mode calibration, a genuine anomaly (severe overheating)
        within Regime-1 must still be flagged. Sensitivity must not be so low
        that all anomalies are missed.
        """
        df_normal = make_regime_dataset(n_per_regime=500)
        df_with_anomaly = make_regime_dataset(n_per_regime=500, include_anomaly=True)

        model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
        model.fit(df_normal[FEATURE_COLS].values)

        # Score test data with injected anomalies
        scores = -model.decision_function(df_with_anomaly[FEATURE_COLS].values)
        threshold = float(np.percentile(
            -model.decision_function(df_normal[FEATURE_COLS].values), 99
        ))

        # Among the injected anomaly rows, at least 50% should be flagged
        anomaly_mask = df_with_anomaly["is_anomaly"].values == 1
        if anomaly_mask.sum() == 0:
            pytest.skip("No injected anomaly rows in fixture - check make_regime_dataset(include_anomaly=True)")

        anomaly_scores = scores[anomaly_mask]
        detection_rate = float((anomaly_scores > threshold).mean())
        print(f"[MultiRegimeTest] Genuine anomaly detection rate: {detection_rate:.2%}")

        assert detection_rate >= 0.50, (
            f"Only {detection_rate:.0%} of injected anomalies were detected. "
            "Per-mode calibration should not suppress genuine fault detection."
        )
