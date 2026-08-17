"""
test_data_quality.py - Tests for quality checks, contract, time alignment
"""

import numpy as np
import pandas as pd
import pytest
from services.aiconnex_ml.shared.data.quality_checks import (
    detect_stuck_sensors, check_null_rates, detect_duplicates,
    check_timestamp_monotonicity
)
from services.aiconnex_ml.shared.data.contract import enforce_contract, validate_or_raise
from services.aiconnex_ml.shared.data.time_alignment import align_to_common_clock, detect_gaps


def _make_df():
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "sensor_1": rng.standard_normal(200),
        "sensor_2": rng.standard_normal(200),
        "target": rng.random(200) * 100,
        "timestamp": pd.date_range("2026-01-01", periods=200, freq="10s"),
    })


def test_stuck_sensor_detection():
    df = _make_df()
    df["flat_sensor"] = 5.0  # constant - should be detected as stuck
    stuck = detect_stuck_sensors(df, window=10)
    assert "flat_sensor" in stuck
    assert "sensor_1" not in stuck


def test_null_rate_detection():
    df = _make_df()
    df.loc[:60, "sensor_1"] = np.nan  # 30.5% null
    high_null = check_null_rates(df, threshold=0.30)
    assert "sensor_1" in high_null


def test_duplicate_detection_and_removal():
    df = _make_df()
    df = pd.concat([df, df.iloc[:10]], ignore_index=True)  # add 10 duplicates
    n_dupes, frac = detect_duplicates(df)
    assert n_dupes == 10


def test_timestamp_monotonicity():
    df = _make_df()
    result = check_timestamp_monotonicity(df, "timestamp")
    assert result["is_monotonic"] is True

    # Insert backwards jump
    df_bad = df.copy()
    df_bad.loc[100, "timestamp"] = pd.Timestamp("2025-01-01")
    result_bad = check_timestamp_monotonicity(df_bad, "timestamp")
    assert result_bad["n_violations"] >= 1


def test_contract_missing_column():
    df = _make_df()
    manifest = {
        "schema_config": {"raw_features": ["sensor_1", "sensor_missing"]},
        "label_contract": {"target_column": "target"},
    }
    _, _, errors = enforce_contract(df, manifest)
    assert any("sensor_missing" in e for e in errors)


def test_contract_passes_valid_df():
    df = _make_df()
    manifest = {
        "schema_config": {"raw_features": ["sensor_1", "sensor_2"]},
        "label_contract": {"target_column": "target"},
    }
    _, _, errors = enforce_contract(df, manifest)
    assert len(errors) == 0


def test_time_alignment_resampling():
    df = _make_df()
    aligned = align_to_common_clock(df, "timestamp", interval="30s")
    # At 30s intervals over 200 * 10s = 2000s range, expect ~66-67 rows
    assert 50 <= len(aligned) <= 100


def test_gap_detection():
    timestamps = pd.date_range("2026-01-01", periods=100, freq="10s").tolist()
    # Shift all timestamps from index 50 onwards by 5 minutes to create a real monotonic gap
    for i in range(50, len(timestamps)):
        timestamps[i] = timestamps[i] + pd.Timedelta("5min")
    df = pd.DataFrame({"timestamp": timestamps, "val": np.random.rand(100)})
    gaps = detect_gaps(df, "timestamp", expected_interval="10s", gap_multiplier=3.0)
    assert len(gaps) >= 1
    assert gaps[0]["duration_seconds"] >= 300
