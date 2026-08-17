"""
evaluation.py — Comprehensive regression evaluation metrics
============================================================
Computes RMSE, MAE, MAPE, R², NRMSE, per-entity breakdown, bootstrap CI,
and asymmetric RUL scoring for remaining-useful-life tasks.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from sklearn.metrics import (
    root_mean_squared_error, mean_absolute_error,
    mean_absolute_percentage_error, r2_score,
)

from services.aiconnex_ml.regression.losses import asymmetric_rul_score
from services.aiconnex_ml.shared.utils.compatibility import safe_dict


def compute_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    is_rul: bool = False,
    target_col: str = "target",
) -> Dict[str, float]:
    """Compute standard and optional RUL-specific regression metrics."""
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()

    rmse = float(root_mean_squared_error(y_true, y_pred))
    mae = float(mean_absolute_error(y_true, y_pred))
    r2 = float(np.clip(r2_score(y_true, y_pred), -1.0, 1.0))
    target_range = y_true.max() - y_true.min()
    nrmse = rmse / target_range if target_range > 0 else float("nan")

    # MAPE: avoid zero division
    mask = y_true != 0
    mape = float(mean_absolute_percentage_error(y_true[mask], y_pred[mask])) if mask.any() else float("nan")

    metrics: Dict[str, float] = {
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "mape": round(mape, 4),
        "r2": round(r2, 4),
        "nrmse": round(nrmse, 4) if not np.isnan(nrmse) else None,
    }

    if is_rul:
        metrics["rul_asymmetric_score"] = round(asymmetric_rul_score(y_true, y_pred), 4)

    return metrics


def bootstrap_confidence_interval(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_fn: callable = root_mean_squared_error,
    n_bootstrap: int = 200,
    ci: float = 0.95,
    random_state: int = 42,
) -> Dict[str, float]:
    """
    Compute bootstrap confidence interval for a metric.

    Returns:
        {"mean": float, "lower": float, "upper": float}
    """
    rng = np.random.default_rng(random_state)
    scores = []
    n = len(y_true)
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        scores.append(float(metric_fn(y_true[idx], y_pred[idx])))
    lower = float(np.percentile(scores, (1 - ci) / 2 * 100))
    upper = float(np.percentile(scores, (1 + ci) / 2 * 100))
    return {"mean": round(np.mean(scores), 4), "lower": round(lower, 4), "upper": round(upper, 4)}


def per_entity_metrics(
    df_test: pd.DataFrame,
    y_pred: np.ndarray,
    entity_col: str,
    target_col: str,
    is_rul: bool = False,
) -> Dict[str, Dict[str, float]]:
    """
    Compute regression metrics per entity (e.g., per engine, per machine).

    Returns:
        {entity_id: {rmse: ..., r2: ...}, ...}
    """
    df = df_test.copy()
    df["__pred__"] = y_pred
    results = {}
    for entity, grp in df.groupby(entity_col):
        y_t = grp[target_col].values
        y_p = grp["__pred__"].values
        if len(y_t) < 2:
            continue
        results[str(entity)] = compute_regression_metrics(y_t, y_p, is_rul)
    return results


def run_evaluation(
    model: Any,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    manifest: Dict[str, Any],
    df_test: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Full evaluation pipeline entry point.

    Returns:
        evaluation_report: {train_metrics, val_metrics, test_metrics,
                            bootstrap_ci, per_entity_metrics}
    """
    is_rul = manifest.get("label_contract", {}).get("target_type") == "time_to_event"
    target_col = manifest.get("label_contract", {}).get("target_column", "target")
    entity_col = manifest.get("schema_config", {}).get("entity_column")

    train_pred = model.predict(X_train)
    val_pred = model.predict(X_val)
    test_pred = model.predict(X_test)

    report = {
        "train": compute_regression_metrics(y_train, train_pred, is_rul),
        "val": compute_regression_metrics(y_val, val_pred, is_rul),
        "test": compute_regression_metrics(y_test, test_pred, is_rul),
        "bootstrap_ci_rmse": bootstrap_confidence_interval(y_test, test_pred),
    }

    # Overfitting check
    report["train_val_rmse_gap"] = round(
        abs(report["train"]["rmse"] - report["val"]["rmse"]), 4
    )

    # Per-entity metrics
    if entity_col and df_test is not None and entity_col in df_test.columns:
        report["per_entity"] = per_entity_metrics(
            df_test, test_pred, entity_col, target_col, is_rul
        )

    report = safe_dict(report)

    print(f"[Evaluation] Test RMSE={report['test']['rmse']}  R²={report['test']['r2']}")
    if is_rul:
        print(f"[Evaluation] RUL Asymmetric Score={report['test']['rul_asymmetric_score']}")

    manifest.setdefault("results", {})
    manifest["results"]["evaluation"] = report
    return report
