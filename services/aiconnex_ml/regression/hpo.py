"""
hpo.py — Hyperparameter Optimization for regression models
===========================================================
Uses RandomizedSearchCV with a PredefinedSplit so that the validation
set is fixed (not randomly selected by CV). Supports monotonic constraints
for XGBoost/LightGBM and GPU device detection.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple
import numpy as np
from sklearn.model_selection import RandomizedSearchCV, PredefinedSplit
from sklearn.metrics import make_scorer

from services.aiconnex_ml.regression.registry import get_algorithm
from services.aiconnex_ml.regression.losses import asymmetric_rul_score
from services.aiconnex_ml.shared.utils.hardware import xgboost_device, lightgbm_device


def run_hpo(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    algorithm_name: str,
    manifest: Dict[str, Any],
) -> Tuple[Any, Dict[str, Any]]:
    """
    Run hyperparameter search for the selected regression algorithm.

    Returns:
        best_model:         Refitted best estimator.
        best_params:        Dict of best hyperparameters.
    """
    hpo_cfg = manifest.get("hpo_config", {})
    n_iter = int(hpo_cfg.get("n_iter", 30))
    n_jobs = int(hpo_cfg.get("n_jobs_search", -1))
    random_state = int(hpo_cfg.get("random_state", 42))

    # G-01 Fix: Wire asymmetric RUL scoring if target is time_to_event (RUL)
    target_type = manifest.get("label_contract", {}).get("target_type", "scalar")
    if target_type == "time_to_event":
        scoring = make_scorer(asymmetric_rul_score, greater_is_better=False)
        print("[HPO] Target type is 'time_to_event' — using asymmetric RUL loss for search optimization.")
    else:
        scoring = hpo_cfg.get("scoring", "neg_root_mean_squared_error")

    entry = get_algorithm(algorithm_name)
    ModelClass = entry["class"]
    param_grid = entry["params"]

    # Apply monotonic constraints if defined (XGBoost / LightGBM)
    monotonic = manifest.get("features_config", {}).get("monotonic_constraints", {})
    extra_params: Dict[str, Any] = {}
    if monotonic and algorithm_name in ("XGBoost", "LightGBM"):
        if algorithm_name == "XGBoost":
            extra_params["device"] = xgboost_device()
            # monotonic_constraints is set as a tuple in XGB
            # (done in trainer.py since it requires feature_col ordering)

    # Combine train + val for PredefinedSplit
    X_combined = np.vstack([X_train, X_val])
    y_combined = np.concatenate([y_train, y_val])
    test_fold = np.array([-1] * len(X_train) + [0] * len(X_val))
    ps = PredefinedSplit(test_fold)

    model = ModelClass(**extra_params)

    if not param_grid:
        # No HPO needed (e.g., LinearRegression)
        model.fit(X_train, y_train)
        print(f"[HPO] {algorithm_name}: no search params — fitted directly.")
        return model, {}

    search = RandomizedSearchCV(
        estimator=model,
        param_distributions=param_grid,
        n_iter=min(n_iter, 10) if not param_grid else n_iter,
        scoring=scoring,
        cv=ps,
        n_jobs=n_jobs,
        random_state=random_state,
        verbose=0,
        refit=True,
    )

    print(f"[HPO] Running {n_iter}-iteration search for '{algorithm_name}'...")
    search.fit(X_combined, y_combined)

    best_params = search.best_params_
    print(f"[HPO] Best params: {best_params}")
    print(f"[HPO] Best CV score: {search.best_score_:.4f}")

    return search.best_estimator_, best_params
