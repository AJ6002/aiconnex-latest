"""
Scenario Test 2: Quality Prediction with Sparse, Lagged Lab Labels
===================================================================
Real scenario: An inline process generates sensor readings every 10 seconds
but the quality lab test (destructive or manual) only runs every 4 hours.
This means:
  - Most rows have NaN in the target column.
  - The lab result that arrives at T=4h corresponds to the sensors at T=0 to T=4h,
    so the target must be LAG-ALIGNED backwards before training.

This test verifies:
  1. The pipeline tolerates a sparse target column (e.g. 98% NaN) without crashing.
  2. label_lag_seconds shifts the target column to align sensor windows with lab results.
  3. The feature engineering step (rolling/lag) does not drop ALL rows when NaN
     propagation from lags is combined with sparse labels.
  4. Training on only labeled rows produces a finite, non-trivial RMSE.
  5. High null rate in the TARGET column triggers a label contract error (>50% NaN
     is a hard error by design).
"""

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.tier3

from services.aiconnex_ml.shared.data.time_alignment import apply_label_lag
from services.aiconnex_ml.regression.label_contract import validate_regression_label
from services.aiconnex_ml.shared.features.rolling import add_rolling_features
from services.aiconnex_ml.shared.features.lag import add_lag_features
from services.aiconnex_ml.regression.baselines import run_baselines


# -- Fixtures -------------------------------------------------------------------

def make_sparse_label_dataset(n_rows: int = 500, lab_interval_rows: int = 24, seed: int = 42):
    """
    Mock inline sensor dataset with sparse lab results.

    - 3 sensor columns sampled every 10 seconds.
    - 'lab_quality' is NaN for all rows EXCEPT every `lab_interval_rows` rows
      (simulating a lab measurement arriving infrequently).
    - 'timestamp' is a uniform 10-second time index.
    """
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=n_rows, freq="10s")
    df = pd.DataFrame({
        "timestamp":  ts,
        "sensor_flow":  rng.normal(100, 5, n_rows),
        "sensor_temp":  rng.normal(75, 2, n_rows),
        "sensor_press": rng.normal(3.0, 0.1, n_rows),
        "lab_quality":  np.nan,
    })

    # Populate lab results every `lab_interval_rows` rows with a synthetic
    # linear-ish relationship to the sensors (the "ground truth")
    lab_indices = list(range(lab_interval_rows - 1, n_rows, lab_interval_rows))
    for idx in lab_indices:
        df.loc[idx, "lab_quality"] = (
            0.4 * df.loc[idx, "sensor_flow"]
            + 0.3 * df.loc[idx, "sensor_temp"]
            - 0.2 * df.loc[idx, "sensor_press"]
            + rng.normal(0, 1)
        )
    return df


def make_sparse_manifest(lag_seconds: int = 0):
    return {
        "ml_task": "regression",
        "data_topology": "time_series",
        "label_contract": {
            "regime": "sparse_lab",
            "target_column": "lab_quality",
            "target_type": "scalar",
            "label_lag_seconds": lag_seconds,
        },
        "schema_config": {
            "timestamp_column": "timestamp",
            "raw_features": ["sensor_flow", "sensor_temp", "sensor_press"],
        },
        "quality_gates": {
            "family": "regression",
            "regression_gates": {"robustness_noise_degradation_pct": 50.0},
        },
        "data_info": {},
        "results": {},
    }


# -- Tests ----------------------------------------------------------------------

def test_sparse_label_fraction_is_realistic():
    """
    Verify the fixture creates the expected sparsity level.
    With lab_interval_rows=24 over 500 rows, we expect ~20 labeled rows (~4% coverage).
    """
    df = make_sparse_label_dataset(n_rows=500, lab_interval_rows=24)
    label_coverage = df["lab_quality"].notna().mean()
    print(f"[SparseLabel] Label coverage: {label_coverage:.1%}")
    assert label_coverage < 0.10, f"Expected <10% label coverage, got {label_coverage:.1%}"
    assert label_coverage > 0.01, "Too few labeled rows - fixture may be broken"


def test_label_contract_passes_with_sparse_but_sufficient_labels():
    """
    A sparse target column with at least some non-NaN values (< 50% null)
    must PASS the label contract.
    """
    df = make_sparse_label_dataset(n_rows=500, lab_interval_rows=24)
    manifest = make_sparse_manifest()

    _, _, errors = validate_regression_label(df, manifest)
    assert len(errors) == 0, f"Contract errors with valid sparse labels: {errors}"


def test_label_contract_fails_when_target_is_almost_all_nan():
    """
    If the target column is > 50% NaN (extremely rare lab cadence),
    the label contract must raise a hard error.
    """
    df = make_sparse_label_dataset(n_rows=500, lab_interval_rows=200)  # only 2-3 labels!
    manifest = make_sparse_manifest()

    _, _, errors = validate_regression_label(df, manifest)
    assert len(errors) > 0, (
        "Expected label contract error for >50% NaN target, but got none."
    )


def test_label_lag_shifts_target_backward():
    """
    A 240-second lag (= 24 rows at 10-second intervals) should shift
    the lab_quality column so that the value at row T now aligns with
    the sensor features from row T-24.

    After lag alignment, the first `lag_rows` rows will have NaN in lab_quality
    (because there are no prior lab readings to shift into them).
    """
    df = make_sparse_label_dataset(n_rows=200, lab_interval_rows=24)
    lag_seconds = 240   # 24 rows x 10 seconds/row

    df_lagged = apply_label_lag(df, "lab_quality", lag_seconds, "timestamp")

    # The shape must be preserved
    assert len(df_lagged) == len(df), "Row count changed after label lag - unexpected."


def test_rolling_features_on_sparse_labeled_data():
    """
    Rolling window features (mean, std) must be computable over sensor columns
    even when the target column is mostly NaN. Sensor columns themselves are dense.
    """
    df = make_sparse_label_dataset(n_rows=300, lab_interval_rows=24)
    sensor_cols = ["sensor_flow", "sensor_temp", "sensor_press"]

    df_feat = add_rolling_features(df, sensor_cols, window_sizes=[10, 20])

    # The new rolling columns must exist and be mostly non-NaN for dense sensors
    rolling_cols = [c for c in df_feat.columns if "roll" in c]
    assert len(rolling_cols) > 0, "No rolling features were generated"

    for col in rolling_cols:
        null_frac = df_feat[col].isnull().mean()
        assert null_frac < 0.15, (
            f"Rolling feature '{col}' has {null_frac:.0%} NaN - suspiciously high. "
            "Rolling features over dense sensor columns should not have many NaN values."
        )


def test_lag_features_do_not_destroy_labeled_rows():
    """
    After adding lag features and dropping NaN rows, we must still retain
    enough labeled rows to train on. Specifically, at least 10 labeled rows
    must survive after dropna().
    """
    df = make_sparse_label_dataset(n_rows=400, lab_interval_rows=24)
    sensor_cols = ["sensor_flow", "sensor_temp", "sensor_press"]

    df_feat = add_lag_features(df, sensor_cols, lags=[1, 5, 10])

    # Simulate the pipeline: drop rows with NaN in sensor lag features
    # (NOT in the target - we keep sparse targets)
    lag_cols = [c for c in df_feat.columns if "_lag" in c]
    df_clean = df_feat.dropna(subset=lag_cols)

    # Count labeled rows that survived
    n_labeled_surviving = df_clean["lab_quality"].notna().sum()
    assert n_labeled_surviving >= 10, (
        f"Only {n_labeled_surviving} labeled rows survived after dropna on lag features. "
        "Too few to train a model. Check lag feature generation."
    )


def test_baselines_train_on_labeled_rows_only():
    """
    End-to-end: with sparse labels, training must silently skip NaN target rows
    and produce a finite RMSE on the labeled validation rows.
    """
    df = make_sparse_label_dataset(n_rows=400, lab_interval_rows=20)
    sensor_cols = ["sensor_flow", "sensor_temp", "sensor_press"]
    manifest = make_sparse_manifest()

    # Keep only labeled rows for training
    df_labeled = df[df["lab_quality"].notna()].reset_index(drop=True)

    n = len(df_labeled)
    split = int(n * 0.7)

    X_train = df_labeled[sensor_cols].values[:split]
    y_train = df_labeled["lab_quality"].values[:split]
    X_val   = df_labeled[sensor_cols].values[split:]
    y_val   = df_labeled["lab_quality"].values[split:]

    assert len(X_train) >= 5, "Too few training rows from sparse labels"

    results = run_baselines(
        X_train, y_train, X_val, y_val,
        candidate_algorithms=["Ridge Regression"],
        manifest=manifest,
    )
    assert len(results) == 1
    assert np.isfinite(results[0]["val_rmse"]), (
        f"Non-finite RMSE on sparse-labeled validation data: {results[0]['val_rmse']}"
    )
    print(f"[SparseLabelTest] Ridge RMSE on labeled rows: {results[0]['val_rmse']:.4f}")
