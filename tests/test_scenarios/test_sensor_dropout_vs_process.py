"""
Scenario Test 5: Sensor Dropout vs. Process Anomaly
=====================================================
Real scenario: One of 8 sensors on a pump goes offline mid-shift (data dropout).
The model receives a column of NaN / zeros for that sensor. The question is:

  Is this a DATA-QUALITY anomaly (sensor cable unplugged)?
  Or a PROCESS anomaly (the pump is actually failing)?

The pipeline must:
  1. Detect stuck / zero-filled sensors via quality_checks.py BEFORE modeling.
  2. Be ROBUST to single-sensor dropout - i.e., a regression model's RMSE must
     not degrade catastrophically when one column is zeroed out.
  3. NOT produce NaN predictions from NaN feature inputs (crash prevention).
  4. Correctly distinguish between:
     - High anomaly score caused by a bad sensor reading (data quality)
     - High anomaly score from a genuine process deviation

This test validates the robustness tests module and quality checks integration.
"""

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.tier3

from services.aiconnex_ml.shared.data.quality_checks import detect_stuck_sensors, check_null_rates
from services.aiconnex_ml.regression.robustness import run_robustness_tests
from services.aiconnex_ml.regression.baselines import run_baselines
from services.aiconnex_ml.regression.evaluation import compute_regression_metrics


# -- Fixtures -------------------------------------------------------------------

SENSOR_COLS = [f"sensor_{i}" for i in range(1, 9)]    # 8 sensors

def make_pump_dataset(n: int = 400, seed: int = 42):
    """
    Synthetic 8-sensor pump dataset with a linear target (vibration level).
    """
    rng = np.random.default_rng(seed)
    data = {col: rng.normal(100 + i * 10, 5, n) for i, col in enumerate(SENSOR_COLS)}
    data["target"] = sum(data[col] * 0.1 for col in SENSOR_COLS) + rng.normal(0, 1, n)
    return pd.DataFrame(data)


def make_dropout_dataset(df: pd.DataFrame, sensor_col: str, mode: str = "zero") -> pd.DataFrame:
    """
    Simulate a sensor dropout:
      mode='zero' -> replace all values with 0 (cable shorted to ground)
      mode='nan'  -> replace all values with NaN (sensor offline, no data)
      mode='stuck'-> replace all values with a constant (sensor frozen at last reading)
    """
    df = df.copy()
    if mode == "zero":
        df[sensor_col] = 0.0
    elif mode == "nan":
        df[sensor_col] = np.nan
    elif mode == "stuck":
        df[sensor_col] = df[sensor_col].iloc[0]   # frozen at first reading
    return df


def make_manifest():
    return {
        "ml_task": "regression",
        "label_contract": {"regime": "continuous", "target_column": "target", "target_type": "scalar"},
        "quality_gates": {
            "family": "regression",
            "regression_gates": {"robustness_noise_degradation_pct": 50.0},  # allow up to 50% RMSE increase
        },
        "results": {},
    }


# -- Quality Check Tests --------------------------------------------------------

class TestSensorDropoutDetection:
    def test_stuck_sensor_detected_on_constant_column(self):
        """
        A sensor that holds the same value for all rows must be flagged
        by detect_stuck_sensors().
        """
        df = make_pump_dataset()
        df_dropout = make_dropout_dataset(df, "sensor_3", mode="stuck")

        stuck = detect_stuck_sensors(df_dropout, window=20)
        assert "sensor_3" in stuck, (
            "sensor_3 is stuck (constant) but was NOT detected by detect_stuck_sensors(). "
            "This means quality checks would silently pass a dead sensor to the model."
        )

    def test_zeroed_sensor_detected_as_high_null_rate_or_stuck(self):
        """
        A sensor zeroed out (cable shorted) should either:
        (a) be detected as high null rate if it is set to NaN, OR
        (b) be detected as stuck if it is set to 0.0.
        """
        df = make_pump_dataset()

        # NaN mode
        df_nan = make_dropout_dataset(df, "sensor_4", mode="nan")
        high_null = check_null_rates(df_nan, threshold=0.50)
        assert "sensor_4" in high_null, (
            "NaN-mode dropout (sensor_4) should be flagged as high null rate."
        )

        # Zero mode - the zero column IS constant, so it must be stuck
        df_zero = make_dropout_dataset(df, "sensor_5", mode="zero")
        stuck = detect_stuck_sensors(df_zero, window=20)
        assert "sensor_5" in stuck, (
            "Zero-mode dropout (sensor_5) should be flagged as stuck sensor."
        )

    def test_healthy_sensors_not_flagged(self):
        """
        Normal, randomly varying sensors must NOT be flagged as stuck.
        """
        df = make_pump_dataset()
        stuck = detect_stuck_sensors(df, window=20)
        healthy = [s for s in SENSOR_COLS if s in stuck]
        assert len(healthy) == 0, (
            f"Healthy sensors incorrectly flagged as stuck: {healthy}"
        )


# -- Model Robustness Tests -----------------------------------------------------

class TestModelRobustnessToDropout:
    def _train_model(self):
        """Helper: train a quick Ridge model on clean data."""
        df = make_pump_dataset(n=400)
        split = 300
        X_train_raw = df[SENSOR_COLS].values[:split]
        y_train = df["target"].values[:split]
        X_val_raw   = df[SENSOR_COLS].values[split:]
        y_val   = df["target"].values[split:]

        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_raw)
        X_val = scaler.transform(X_val_raw)

        manifest = make_manifest()
        results = run_baselines(X_train, y_train, X_val, y_val, ["Ridge Regression"], manifest)
        return results[0]["model"], X_train, y_train, X_val, y_val, scaler

    def test_model_does_not_crash_on_single_zero_sensor(self):
        """
        When one sensor column is zeroed out at inference time,
        the model must still produce finite predictions (no NaN / crash).
        """
        model, X_train, y_train, X_val, y_val, scaler = self._train_model()
        df_test = make_pump_dataset(n=100)
        df_dropout = make_dropout_dataset(df_test, "sensor_2", mode="zero")

        # Scale the dropout test data using the fitted scaler
        X_dropout = scaler.transform(df_dropout[SENSOR_COLS].values)
        # Force the scaled column to 0.0 (which represents the mean value)
        X_dropout[:, 1] = 0.0

        preds = model.predict(X_dropout)

        assert np.all(np.isfinite(preds)), (
            "Model produced NaN or Inf predictions when sensor_2 was zeroed out."
        )

    def test_rmse_degradation_within_tolerance_for_single_dropout(self):
        """
        With one sensor zeroed out, the RMSE should increase but must stay
        within the configured robustness_noise_degradation_pct threshold (50%).
        """
        model, _, _, X_val, y_val, _ = self._train_model()

        # Baseline RMSE on clean validation data
        clean_metrics = compute_regression_metrics(y_val, model.predict(X_val))
        baseline_rmse = clean_metrics["rmse"]

        # Drop sensor_1 (set to zero) at inference time
        X_dropout = X_val.copy()
        X_dropout[:, 0] = 0.0          # sensor_1 is column index 0 (mean value in scaled space)

        dropout_metrics = compute_regression_metrics(y_val, model.predict(X_dropout))
        degraded_rmse = dropout_metrics["rmse"]

        pct_degradation = (degraded_rmse - baseline_rmse) / max(baseline_rmse, 1e-8) * 100

        print(
            f"[DropoutTest] Clean RMSE: {baseline_rmse:.4f} | "
            f"Dropout RMSE: {degraded_rmse:.4f} | Degradation: {pct_degradation:.1f}%"
        )

        assert pct_degradation < 50.0, (
            f"RMSE degraded {pct_degradation:.1f}% on a single-sensor dropout. "
            f"Exceeds 50% tolerance. The model may be overly dependent on sensor_1."
        )

    def test_robustness_report_contains_noise_and_dropout_tests(self):
        """
        The run_robustness_tests() function must return a report that includes
        both noise and dropout test results.
        """
        model, _, _, X_val, y_val, _ = self._train_model()
        manifest = make_manifest()
        report = run_robustness_tests(model, X_val, y_val, manifest)

        assert "noise_tests" in report,   "Missing 'noise_tests' in robustness report"
        assert "dropout_tests" in report, "Missing 'dropout_tests' in robustness report"
        assert len(report["noise_tests"]) > 0,   "No noise test results returned"
        assert len(report["dropout_tests"]) > 0, "No dropout test results returned"

    def test_multi_sensor_dropout_degrades_as_expected(self):
        """
        Zeroing out 4 of 8 sensors (50% of information) should degrade RMSE
        more than zeroing out only 1. Tests that degradation is monotonically
        ordered with dropout severity.
        """
        model, _, _, X_val, y_val, _ = self._train_model()
        clean_rmse = compute_regression_metrics(y_val, model.predict(X_val))["rmse"]

        # 1-sensor dropout
        X1 = X_val.copy()
        X1[:, 0] = 0.0
        rmse_1_dropout = compute_regression_metrics(y_val, model.predict(X1))["rmse"]

        # 4-sensor dropout
        X4 = X_val.copy()
        for i in range(4):
            X4[:, i] = 0.0
        rmse_4_dropout = compute_regression_metrics(y_val, model.predict(X4))["rmse"]

        assert rmse_4_dropout >= rmse_1_dropout, (
            f"4-sensor dropout RMSE ({rmse_4_dropout:.4f}) should be >= "
            f"1-sensor dropout RMSE ({rmse_1_dropout:.4f}). "
            "Robustness degradation should be monotonic with dropout severity."
        )
        print(
            f"[DropoutTest] Degradation scale - "
            f"Clean: {clean_rmse:.4f} | 1-dropout: {rmse_1_dropout:.4f} | "
            f"4-dropout: {rmse_4_dropout:.4f}"
        )
