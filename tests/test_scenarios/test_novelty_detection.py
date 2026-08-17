"""
Scenario Test 3: Novelty Detection (New Operating Mode)
========================================================
Real scenario: A model is trained on data from two known operating modes
(Mode-A = low-speed, Mode-B = high-speed). At inference time, a third
mode appears (Mode-C = emergency over-speed) that the model has NEVER seen.

The system must:
  1. Detect that Mode-C data produces anomaly scores significantly higher
     than the calibrated threshold (i.e., flag it as anomalous).
  2. The OperatingModeDetector must identify Mode-C as an "unknown mode".
  3. Precision on Mode-C (all should be flagged as anomalous) must be high.
  4. No Mode-A or Mode-B rows should be flagged as anomalous after calibration
     (i.e., false alarm rate on known modes is controlled).

This is the most critical scenario for industrial AD platforms because
operators lose trust the moment the system alarms on a planned startup ramp.
"""

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.tier3

from sklearn.ensemble import IsolationForest

from services.aiconnex_ml.anomaly.operating_modes import OperatingModeDetector
from services.aiconnex_ml.anomaly.threshold import ThresholdCalibrator
from services.aiconnex_ml.anomaly.evaluation import compute_anomaly_metrics


# -- Fixtures -------------------------------------------------------------------

def make_mode_dataset(n_per_mode: int = 300, seed: int = 42):
    """
    Generate a 3-mode sensor dataset:
      Mode-A (normal steady state): sensors centred at (50, 200, 1.0)
      Mode-B (high-load normal):    sensors centred at (80, 250, 1.5)
      Mode-C (anomalous over-speed): sensors centred at (150, 400, 4.0) - never seen in training
    """
    rng = np.random.default_rng(seed)

    def make_block(n, centre, mode_label):
        X = rng.normal(loc=centre, scale=[3, 5, 0.05], size=(n, 3))
        return pd.DataFrame(X, columns=["sensor_speed", "sensor_load", "sensor_vibration"]).assign(mode=mode_label)

    df_A = make_block(n_per_mode, [50, 200, 1.0], "Mode-A")
    df_B = make_block(n_per_mode, [80, 250, 1.5], "Mode-B")
    df_C = make_block(n_per_mode, [150, 400, 4.0], "Mode-C")   # NOVEL mode

    return df_A, df_B, df_C


def make_novelty_manifest():
    return {
        "ml_task": "anomaly",
        "label_contract": {
            "supervision_mode": "semi_supervised",
        },
        "operating_modes": {
            "enabled": True,
            "mode_column": "mode",
            "known_modes": ["Mode-A", "Mode-B"],    # Mode-C deliberately absent
            "normalize_per_mode": False,
        },
        "threshold_config": {
            "method": "percentile",
            "percentile": 99.0,
        },
        "results": {},
        "monitoring": {},
    }


# -- Tests ----------------------------------------------------------------------

def test_unknown_mode_is_flagged_by_detector():
    """
    OperatingModeDetector must identify Mode-C as an unknown mode
    (since it was not in known_modes during training).
    """
    manifest = make_novelty_manifest()
    detector = OperatingModeDetector(manifest)

    assert not detector.is_unknown_mode("Mode-A"), "Mode-A should be known"
    assert not detector.is_unknown_mode("Mode-B"), "Mode-B should be known"
    assert detector.is_unknown_mode("Mode-C"),     "Mode-C MUST be flagged as unknown"


def test_novel_mode_scores_significantly_higher():
    """
    An Isolation Forest trained on Mode-A + Mode-B data should assign
    much higher anomaly scores to Mode-C data.

    We expect:
      - Median anomaly score for Mode-A & Mode-B < threshold (known modes pass)
      - Median anomaly score for Mode-C >> threshold (novel mode is flagged)
    """
    df_A, df_B, df_C = make_mode_dataset(n_per_mode=300)

    feature_cols = ["sensor_speed", "sensor_load", "sensor_vibration"]

    # Train ONLY on normal modes
    X_train = pd.concat([df_A, df_B])[feature_cols].values
    X_novel = df_C[feature_cols].values

    model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    model.fit(X_train)

    # Invert decision_function so higher = more anomalous
    train_scores   = -model.decision_function(X_train)
    novel_scores   = -model.decision_function(X_novel)

    threshold_99th = float(np.percentile(train_scores, 99))

    # The 50th percentile of novel scores should be above the 99th percentile of training scores
    novel_median = float(np.median(novel_scores))
    assert novel_median > threshold_99th, (
        f"Novel mode median score ({novel_median:.4f}) should exceed "
        f"99th-percentile training threshold ({threshold_99th:.4f}). "
        "The model is not separating the novel operating mode."
    )
    print(
        f"[NoveltyTest] 99th-pct train threshold: {threshold_99th:.4f} | "
        f"Novel mode median score: {novel_median:.4f}"
    )


def test_false_alarm_rate_low_on_known_modes():
    """
    After calibrating threshold at the 99th percentile of known-mode training scores,
    the false alarm rate on Mode-A and Mode-B validation data must be <= 2%.
    """
    df_A, df_B, df_C = make_mode_dataset(n_per_mode=500)
    feature_cols = ["sensor_speed", "sensor_load", "sensor_vibration"]

    df_train = pd.concat([df_A[:300], df_B[:300]])
    df_val   = pd.concat([df_A[300:], df_B[300:]])

    model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    model.fit(df_train[feature_cols].values)

    val_scores = -model.decision_function(df_val[feature_cols].values)

    manifest = make_novelty_manifest()
    calibrator = ThresholdCalibrator(manifest)
    threshold, _ = calibrator.calibrate(val_scores, y_val_true=None)

    # False alarm rate on known-mode validation data
    val_preds = calibrator.predict(val_scores)
    far = float(val_preds.mean())

    assert far <= 0.02, (
        f"False alarm rate on known modes ({far:.2%}) exceeds 2% tolerance. "
        f"Threshold calibration ({threshold:.4f}) may be too aggressive."
    )
    print(f"[NoveltyTest] FAR on known-mode validation data: {far:.2%} (threshold: {threshold:.4f})")


def test_majority_of_novel_mode_is_flagged():
    """
    When Mode-C data is scored against the threshold calibrated on Mode-A/B,
    at least 80% of Mode-C rows must be flagged as anomalous.
    (Not 100%, because the score distribution edges can overlap slightly.)
    """
    df_A, df_B, df_C = make_mode_dataset(n_per_mode=500)
    feature_cols = ["sensor_speed", "sensor_load", "sensor_vibration"]

    df_train = pd.concat([df_A[:300], df_B[:300]])
    df_val   = pd.concat([df_A[300:], df_B[300:]])

    model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    model.fit(df_train[feature_cols].values)

    val_scores  = -model.decision_function(df_val[feature_cols].values)
    novel_scores = -model.decision_function(df_C[feature_cols].values)

    manifest = make_novelty_manifest()
    calibrator = ThresholdCalibrator(manifest)
    threshold, _ = calibrator.calibrate(val_scores, y_val_true=None)

    novel_preds = calibrator.predict(novel_scores)
    detection_rate = float(novel_preds.mean())

    assert detection_rate >= 0.80, (
        f"Novel mode detection rate ({detection_rate:.2%}) is below 80%. "
        "The model is failing to identify the new operating regime as anomalous."
    )
    print(f"[NoveltyTest] Novel mode detection rate: {detection_rate:.2%}")


def test_mode_split_by_detector():
    """
    OperatingModeDetector.split_by_mode() must return separate arrays
    for each operating mode.
    """
    df_A, df_B, _ = make_mode_dataset(n_per_mode=100)
    df_combined = pd.concat([df_A, df_B]).reset_index(drop=True)

    feature_cols = ["sensor_speed", "sensor_load", "sensor_vibration"]
    manifest = make_novelty_manifest()
    detector = OperatingModeDetector(manifest)

    splits = detector.split_by_mode(df_combined, feature_cols)

    assert "Mode-A" in splits, "Mode-A split not found"
    assert "Mode-B" in splits, "Mode-B split not found"
    assert splits["Mode-A"].shape == (100, 3), f"Unexpected Mode-A shape: {splits['Mode-A'].shape}"
    assert splits["Mode-B"].shape == (100, 3), f"Unexpected Mode-B shape: {splits['Mode-B'].shape}"
