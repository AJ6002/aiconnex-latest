"""
trainer.py — RegressionTrainer: pipeline entry point called by train_node
==========================================================================
Orchestrates the full regression modeling sequence:
  label_contract → baselines → HPO → evaluation → robustness

Called as:
    from services.aiconnex_ml.regression.trainer import RegressionTrainer
    trainer = RegressionTrainer(manifest)
    manifest = trainer.run(X_train, y_train, X_val, y_val, X_test, y_test, df_test)
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd

from services.aiconnex_ml.regression.label_contract import validate_regression_label
from services.aiconnex_ml.regression.baselines import run_baselines
from services.aiconnex_ml.regression.hpo import run_hpo
from services.aiconnex_ml.regression.evaluation import run_evaluation
from services.aiconnex_ml.regression.robustness import run_robustness_tests
from services.aiconnex_ml.shared.utils.serialization import export_model
from services.aiconnex_ml.shared.utils.manifest import mark_step_complete


class RegressionTrainer:
    """
    Entry point for the regression modeling track.
    Accepts pre-split, pre-scaled numpy arrays and a manifest dict.
    """

    def __init__(self, manifest: Dict[str, Any]):
        self.manifest = manifest
        self.best_model = None
        self.best_algorithm = None
        self.best_params: Dict[str, Any] = {}

    def run(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        feature_cols: List[str],
        df_test: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full regression training sequence.

        Returns:
            Updated manifest dict with results, model path, and evaluation report.
        """
        manifest = self.manifest

        # ── Step 1: Label Contract ─────────────────────────────────────────────
        print("\n" + "="*60)
        print("[RegressionTrainer] STEP 1: Validating Label Contract")
        print("="*60)
        target_col = manifest.get("label_contract", {}).get("target_column", "target")
        censoring = manifest.get("label_contract", {}).get("censoring", {})
        censor_col = censoring.get("censor_flag_column") if censoring.get("enabled") else None

        dummy_dict = {target_col: y_train}
        if censor_col:
            dummy_dict[censor_col] = np.zeros(len(y_train))

        _, manifest, errors = validate_regression_label(
            pd.DataFrame(dummy_dict), manifest
        )
        if errors:
            raise ValueError(f"Label contract failed: {errors}")

        # G-04 Fix: Filter out NaN target rows from train/val before fitting models
        if y_train is not None and np.isnan(y_train).any():
            valid_train = ~np.isnan(y_train)
            print(f"[RegressionTrainer] G-04: Filtered {int(np.sum(~valid_train))} NaN targets from X_train/y_train (sparse_lab regime).")
            X_train, y_train = X_train[valid_train], y_train[valid_train]
        if y_val is not None and np.isnan(y_val).any():
            valid_val = ~np.isnan(y_val)
            print(f"[RegressionTrainer] G-04: Filtered {int(np.sum(~valid_val))} NaN targets from X_val/y_val (sparse_lab regime).")
            X_val, y_val = X_val[valid_val], y_val[valid_val]

        # ── Step 2: Baseline Models ────────────────────────────────────────────
        print("\n" + "="*60)
        print("[RegressionTrainer] STEP 2: Running Baseline Models")
        print("="*60)
        candidates = manifest.get("candidate_algorithms", [])
        if not candidates:
            raise ValueError("No candidate_algorithms listed in manifest.")

        baseline_results = run_baselines(X_train, y_train, X_val, y_val, candidates, manifest)
        best_baseline = baseline_results[0]
        self.best_algorithm = best_baseline["algorithm"]

        manifest.setdefault("results", {})
        manifest["results"]["baseline_leaderboard"] = [
            {k: v for k, v in r.items() if k != "model"}  # strip model objects
            for r in baseline_results
        ]

        # ── Step 3: HPO ───────────────────────────────────────────────────────
        print("\n" + "="*60)
        print(f"[RegressionTrainer] STEP 3: HPO for '{self.best_algorithm}'")
        print("="*60)
        best_model, best_params = run_hpo(
            X_train, y_train, X_val, y_val, self.best_algorithm, manifest
        )
        self.best_model = best_model
        self.best_params = best_params
        manifest["results"]["best_algorithm"] = self.best_algorithm
        manifest["results"]["best_params"] = best_params

        # ── Step 4: Evaluation ────────────────────────────────────────────────
        print("\n" + "="*60)
        print("[RegressionTrainer] STEP 4: Evaluation")
        print("="*60)
        eval_report = run_evaluation(
            best_model, X_train, y_train, X_val, y_val, X_test, y_test,
            manifest, df_test
        )

        # ── Step 5: Robustness ────────────────────────────────────────────────
        print("\n" + "="*60)
        print("[RegressionTrainer] STEP 5: Robustness Tests")
        print("="*60)
        run_robustness_tests(best_model, X_test, y_test, manifest)

        # ── Step 6: Save Model ─────────────────────────────────────────────────
        print("\n" + "="*60)
        print("[RegressionTrainer] STEP 6: Saving Model")
        print("="*60)
        model_path = manifest.get("paths", {}).get("best_model", "outputs/best_model")
        fmt = manifest.get("deployment_target", {}).get("compilation_format", "pickle")
        saved_path = export_model(
            best_model, model_path, format=fmt,
            feature_names=feature_cols, n_features=len(feature_cols)
        )
        manifest.setdefault("paths", {})
        manifest["paths"]["best_model"] = saved_path
        manifest = mark_step_complete(manifest, "regression_training")

        print(f"\n[RegressionTrainer] ✅ Training complete. Model saved: {saved_path}")
        self.manifest = manifest
        return manifest
