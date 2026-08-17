"""
baselines.py — Run all candidate regression baselines and rank by primary metric
================================================================================
Runs a quick training pass on all candidate algorithms listed in the manifest,
evaluates on validation data, and returns a ranked leaderboard.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error, r2_score

from services.aiconnex_ml.regression.registry import get_algorithm, list_algorithms
from services.aiconnex_ml.regression.losses import asymmetric_rul_score


def run_baselines(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    candidate_algorithms: List[str],
    manifest: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Train each candidate algorithm with default parameters and rank by val RMSE.

    Returns:
        Sorted list of results: [{"algorithm": str, "rmse": float, "r2": float, "model": obj}, ...]
    """
    is_rul = manifest.get("label_contract", {}).get("target_type") == "time_to_event"
    results = []

    for name in candidate_algorithms:
        try:
            entry = get_algorithm(name)
            ModelClass = entry["class"]
            model = ModelClass()
            model.fit(X_train, y_train)
            y_pred = model.predict(X_val)

            rmse = float(root_mean_squared_error(y_val, y_pred))
            r2 = float(r2_score(y_val, y_pred))
            rul_score = asymmetric_rul_score(y_val, y_pred) if is_rul else None

            result = {
                "algorithm": name,
                "val_rmse": round(rmse, 4),
                "val_r2": round(r2, 4),
                "val_rul_score": round(rul_score, 4) if rul_score is not None else None,
                "model": model,
            }
            results.append(result)
            print(f"[Baselines] {name:30s} RMSE={rmse:.4f}  R²={r2:.4f}"
                  + (f"  RUL={rul_score:.2f}" if is_rul else ""))

        except Exception as e:
            print(f"[Baselines] ⚠️  {name} failed: {e}")

    results.sort(key=lambda x: x["val_rmse"])
    print(f"\n[Baselines] Best baseline: {results[0]['algorithm']} (RMSE={results[0]['val_rmse']})")
    return results
