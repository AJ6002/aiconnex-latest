"""
engineer_node.py — ENGINEER DAG Node: shared feature engineering pipeline
==========================================================================
This is the code that runs inside the ENGINEER node of the DAG.
It orchestrates all shared feature engineering steps in order:
  1. Schema mapping (tag registry)
  2. Time alignment (resampling + label lag)
  3. Quality checks + deduplication
  4. Schema contract enforcement
  5. Rolling + lag + spectral features (per manifest config)
  6. Scaler fit (on train only) and apply to all splits
  7. Per-mode normalization (if operating_modes enabled)
  8. Feature validation (PSI drift, collinearity)

Inputs:  df_train, df_val, df_test, manifest (all pre-split)
Outputs: X_train, y_train, X_val, y_val, X_test, y_test, feature_cols, manifest
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd

from services.aiconnex_ml.shared.data.schema_mapping import run_schema_mapping
from services.aiconnex_ml.shared.data.time_alignment import run_time_alignment
from services.aiconnex_ml.shared.data.quality_checks import run_quality_checks
from services.aiconnex_ml.shared.data.contract import enforce_contract
from services.aiconnex_ml.shared.features.rolling import add_rolling_features, add_trend_features
from services.aiconnex_ml.shared.features.lag import add_lag_features, add_diff_features
from services.aiconnex_ml.shared.features.spectral import add_statistical_spectral_features
from services.aiconnex_ml.shared.features.scaling import fit_and_apply_all_splits, save_scaler
from services.aiconnex_ml.shared.features.mode_normalization import (
    fit_per_mode_scalers, apply_per_mode_scaling, save_mode_scalers
)
from services.aiconnex_ml.shared.features.validation import run_feature_validation
from services.aiconnex_ml.shared.utils.manifest import mark_step_complete


def run_engineer_node(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    df_test: pd.DataFrame,
    manifest: Dict[str, Any],
) -> Tuple[np.ndarray, Optional[np.ndarray], np.ndarray, Optional[np.ndarray],
           np.ndarray, Optional[np.ndarray], List[str], Dict[str, Any]]:
    """
    Full feature engineering pipeline node.

    Returns:
        X_train, y_train, X_val, y_val, X_test, y_test, feature_cols, manifest
    """
    print("\n" + "="*60)
    print("[EngineerNode] Starting Feature Engineering")
    print("="*60)

    feat_cfg = manifest.get("features_config", {})
    schema_cfg = manifest.get("schema_config", {})
    ml_task = manifest.get("ml_task", "regression")
    label_cfg = manifest.get("label_contract", {})

    entity_col = schema_cfg.get("entity_column")
    ts_col = schema_cfg.get("timestamp_column")
    target_col = label_cfg.get("target_column")
    fault_col = label_cfg.get("fault_label_column")
    raw_features = schema_cfg.get("raw_features", [])

    # ── Step 1: Schema Mapping ────────────────────────────────────────────────
    print("\n[EngineerNode] 1/8 Schema Mapping...")
    df_train, manifest = run_schema_mapping(df_train, manifest)
    df_val, _ = run_schema_mapping(df_val, manifest)
    df_test, _ = run_schema_mapping(df_test, manifest)

    # Refresh raw_features after mapping
    if manifest.get("data_info", {}).get("schema_mapping_applied"):
        raw_features = manifest["data_info"]["canonical_columns"]

    # ── Step 2: Time Alignment (train only to determine params, then apply) ──
    print("\n[EngineerNode] 2/8 Time Alignment...")
    df_train, manifest = run_time_alignment(df_train, manifest)
    df_val, _ = run_time_alignment(df_val, manifest)
    df_test, _ = run_time_alignment(df_test, manifest)

    # ── Step 3: Quality Checks (train only) ───────────────────────────────────
    print("\n[EngineerNode] 3/8 Quality Checks...")
    df_train, manifest, _ = run_quality_checks(df_train, manifest)

    # ── Step 4: Schema Contract ───────────────────────────────────────────────
    print("\n[EngineerNode] 4/8 Schema Contract...")
    df_train, manifest, errors = enforce_contract(df_train, manifest)
    if errors:
        print(f"[EngineerNode] ⚠️  Contract errors: {errors}")

    # ── Step 5: Feature Engineering ───────────────────────────────────────────
    print("\n[EngineerNode] 5/8 Feature Engineering...")

    # Identify sensor columns (exclude metadata columns)
    exclude_cols = [c for c in [target_col, fault_col, entity_col, ts_col] if c]
    sensor_cols = [c for c in raw_features if c in df_train.columns and c not in exclude_cols]

    window_sizes = feat_cfg.get("time_window_sizes", [10, 20, 50])

    def apply_features(df: pd.DataFrame) -> pd.DataFrame:
        """Apply all configured features to a single split."""
        if feat_cfg.get("lag_features", True):
            df = add_lag_features(df, sensor_cols, lags=[1, 5, 10], group_col=entity_col)
            df = add_diff_features(df, sensor_cols, periods=[1, 5], group_col=entity_col)

        if manifest.get("data_topology", "tabular") != "tabular":
            df = add_rolling_features(df, sensor_cols, window_sizes, group_col=entity_col)
            df = add_trend_features(df, sensor_cols, window=20, group_col=entity_col)

        if feat_cfg.get("spectral_features", False):
            vibration_cols = [c for c in sensor_cols if "vib" in c.lower() or "accel" in c.lower() or "s" in c.lower()]
            if vibration_cols:
                from services.aiconnex_ml.shared.features.spectral import add_fft_features
                df = add_fft_features(df, vibration_cols, window=64, n_components=5, group_col=entity_col)
                df = add_statistical_spectral_features(df, vibration_cols)

        return df

    df_train = apply_features(df_train)
    df_val = apply_features(df_val)
    df_test = apply_features(df_test)

    # Drop NaN rows created by lag/rolling features (train only)
    pre_drop = len(df_train)
    df_train = df_train.dropna().reset_index(drop=True)
    print(f"[EngineerNode] Dropped {pre_drop - len(df_train)} rows with NaN from lag/rolling.")

    # ── Step 6: Determine Final Feature Columns ───────────────────────────────
    exclude = set([c for c in [target_col, fault_col, entity_col, ts_col] if c])
    feature_cols = [c for c in df_train.columns if c not in exclude and
                    pd.api.types.is_numeric_dtype(df_train[c])]

    # Save final feature cols to manifest
    manifest["schema_config"]["final_features"] = feature_cols
    print(f"[EngineerNode] Final feature set: {len(feature_cols)} columns.")

    # ── Step 7: Scaling ───────────────────────────────────────────────────────
    print("\n[EngineerNode] 6/8 Scaling...")
    mode_cfg = manifest.get("operating_modes", {})

    if mode_cfg.get("enabled") and mode_cfg.get("normalize_per_mode"):
        mode_col = mode_cfg.get("mode_column")
        if mode_col and mode_col in df_train.columns:
            mode_scalers = fit_per_mode_scalers(df_train, feature_cols, mode_col)
            df_train = apply_per_mode_scaling(df_train, feature_cols, mode_col, mode_scalers)
            df_val = apply_per_mode_scaling(df_val, feature_cols, mode_col, mode_scalers)
            df_test = apply_per_mode_scaling(df_test, feature_cols, mode_col, mode_scalers)
            scaler_path = manifest.get("paths", {}).get("scaler", "outputs/mode_scalers.pkl")
            save_mode_scalers(mode_scalers, scaler_path)
        else:
            df_train, df_val, df_test, scaler = fit_and_apply_all_splits(
                df_train, df_val, df_test, feature_cols
            )
            scaler_path = manifest.get("paths", {}).get("scaler", "outputs/scaler.pkl")
            save_scaler(scaler, scaler_path)
    else:
        scaler_method = feat_cfg.get("normalization", "global")
        df_train, df_val, df_test, scaler = fit_and_apply_all_splits(
            df_train, df_val, df_test, feature_cols,
            method="standard" if scaler_method == "global" else "robust"
        )
        scaler_path = manifest.get("paths", {}).get("scaler", "outputs/scaler.pkl")
        save_scaler(scaler, scaler_path)
        manifest["paths"]["scaler"] = scaler_path

    # ── Step 8: Feature Validation ────────────────────────────────────────────
    print("\n[EngineerNode] 7/8 Feature Validation...")
    run_feature_validation(df_train, df_val, feature_cols, target_col, manifest)

    # ── Step 9: Prepare Arrays ────────────────────────────────────────────────
    print("\n[EngineerNode] 8/8 Preparing Arrays...")
    X_train = df_train[feature_cols].values
    X_val = df_val[feature_cols].values
    X_test = df_test[feature_cols].values

    # Target column
    y_train = df_train[target_col].values if target_col and target_col in df_train.columns else None
    y_val = df_val[target_col].values if target_col and target_col in df_val.columns else None
    y_test = df_test[target_col].values if target_col and target_col in df_test.columns else None

    manifest = mark_step_complete(manifest, "feature_engineering")
    print(f"\n[EngineerNode] ✅ Complete. X_train={X_train.shape}, X_val={X_val.shape}, X_test={X_test.shape}")

    return X_train, y_train, X_val, y_val, X_test, y_test, feature_cols, manifest, df_train, df_val, df_test
