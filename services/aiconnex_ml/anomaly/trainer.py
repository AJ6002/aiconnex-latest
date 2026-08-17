"""
trainer.py — AnomalyTrainer: pipeline entry point called by train_node
=======================================================================
Orchestrates the full anomaly modeling sequence:
  label_contract → data_load → baselines → HPO → threshold_calibration → evaluation

Called as:
    from services.aiconnex_ml.anomaly.trainer import AnomalyTrainer
    trainer = AnomalyTrainer(manifest)
    manifest = trainer.run(df_train, df_val, df_test, feature_cols)
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from services.aiconnex_ml.anomaly.label_contract import validate_anomaly_label
from services.aiconnex_ml.anomaly.data_loader import load_for_supervision_mode
from services.aiconnex_ml.anomaly.registry import get_algorithm, filter_by_supervision
from services.aiconnex_ml.anomaly.threshold import ThresholdCalibrator
from services.aiconnex_ml.anomaly.evaluation import run_evaluation
from services.aiconnex_ml.anomaly.operating_modes import OperatingModeDetector
from services.aiconnex_ml.shared.utils.serialization import export_model
from services.aiconnex_ml.shared.utils.manifest import mark_step_complete


def _score_model(model: Any, X: np.ndarray, entry: Dict[str, Any]) -> np.ndarray:
    """Extract anomaly scores from a fitted model using its declared score_method."""
    method = entry.get("score_method", "decision_function")
    invert = entry.get("invert_score", False)

    if method == "decision_function":
        scores = model.decision_function(X)
    elif method == "predict_proba":
        scores = model.predict_proba(X)[:, 1]
    elif method == "negative_outlier_factor_":
        scores = -model.negative_outlier_factor_
    elif method == "reconstruction_error":
        # PCA-based reconstruction error
        X_reconstructed = model.inverse_transform(model.transform(X))
        scores = np.mean((X - X_reconstructed) ** 2, axis=1)
    elif method is None:
        # DBSCAN: -1 label = anomaly
        labels = model.labels_
        scores = (labels == -1).astype(float)
    else:
        scores = model.decision_function(X)

    if invert:
        scores = -scores

    return scores


class AnomalyTrainer:
    """
    Entry point for the anomaly detection modeling track.
    Handles all three supervision modes automatically.
    """

    def __init__(self, manifest: Dict[str, Any]):
        self.manifest = manifest
        self.best_model = None
        self.best_algorithm = None
        self.threshold: Optional[float] = None

    def run(
        self,
        df_train: pd.DataFrame,
        df_val: pd.DataFrame,
        df_test: pd.DataFrame,
        feature_cols: List[str],
        y_val_true: Optional[np.ndarray] = None,
        y_test_true: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Execute the full anomaly training and calibration sequence."""
        manifest = self.manifest
        supervision_mode = manifest.get("label_contract", {}).get("supervision_mode", "unsupervised")
        mode_detector = OperatingModeDetector(manifest)

        # ── Step 1: Label Contract ─────────────────────────────────────────────
        print("\n" + "="*60)
        print(f"[AnomalyTrainer] STEP 1: Label Contract [{supervision_mode}]")
        print("="*60)
        _, manifest, errors = validate_anomaly_label(df_train, manifest)
        if errors:
            raise ValueError(f"Anomaly label contract failed: {errors}")

        # ── Step 2: Load Data by Supervision Mode ──────────────────────────────
        print("\n" + "="*60)
        print("[AnomalyTrainer] STEP 2: Loading Training Data")
        print("="*60)
        X_train, y_train = load_for_supervision_mode(df_train, feature_cols, manifest)
        X_val = df_val[feature_cols].values
        X_test = df_test[feature_cols].values

        # ── Step 3: Baseline Candidate Models ─────────────────────────────────
        print("\n" + "="*60)
        print("[AnomalyTrainer] STEP 3: Running Baseline Models")
        print("="*60)
        candidates = manifest.get("candidate_algorithms", [])
        eligible = filter_by_supervision(supervision_mode)
        candidates = [c for c in candidates if c in eligible] or eligible[:3]

        best_model, best_algo, best_entry = None, None, None
        best_pr_auc = -1.0

        for algo_name in candidates:
            try:
                entry = get_algorithm(algo_name)
                ModelClass = entry["class"]
                model = ModelClass()

                if supervision_mode == "supervised" and y_train is not None:
                    model.fit(X_train, y_train)
                else:
                    model.fit(X_train)

                val_scores = _score_model(model, X_val, entry)

                # Quick calibration for ranking
                rough_threshold = float(np.percentile(val_scores, 95))
                val_preds = (val_scores > rough_threshold).astype(int)

                if y_val_true is not None:
                    from sklearn.metrics import average_precision_score
                    pr_auc = float(average_precision_score(y_val_true, val_scores))
                    print(f"[Baselines] {algo_name:30s} PR-AUC={pr_auc:.4f}")
                    if pr_auc > best_pr_auc:
                        best_pr_auc = pr_auc
                        best_model = model
                        best_algo = algo_name
                        best_entry = entry
                else:
                    print(f"[Baselines] {algo_name:30s} (no labels — score-based selection)")
                    if best_model is None:
                        best_model = model
                        best_algo = algo_name
                        best_entry = entry

            except Exception as e:
                print(f"[Baselines] ⚠️  {algo_name} failed: {e}")

        if best_model is None:
            raise RuntimeError("All candidate anomaly algorithms failed.")

        self.best_model = best_model
        self.best_algorithm = best_algo
        print(f"\n[AnomalyTrainer] Best model: {best_algo}")

        manifest.setdefault("results", {})
        manifest["results"]["best_algorithm"] = best_algo

        # ── Step 4: Threshold Calibration ─────────────────────────────────────
        print("\n" + "="*60)
        print("[AnomalyTrainer] STEP 4: Threshold Calibration")
        print("="*60)
        val_scores = _score_model(best_model, X_val, best_entry)
        calibrator = ThresholdCalibrator(manifest)

        if mode_detector.is_configured() and manifest.get("operating_modes", {}).get("mode_column") in df_val.columns:
            mode_col = manifest["operating_modes"]["mode_column"]
            val_modes = df_val[mode_col].astype(str).values
            mode_thresholds = calibrator.calibrate_per_mode(val_scores, val_modes)
            mode_detector.register_mode_thresholds(mode_thresholds)
            # Use median threshold as global fallback
            global_threshold = float(np.median(list(mode_thresholds.values())))
        else:
            global_threshold, _ = calibrator.calibrate(val_scores, y_val_true)

        self.threshold = global_threshold

        # ── Step 5: Evaluation ────────────────────────────────────────────────
        print("\n" + "="*60)
        print("[AnomalyTrainer] STEP 5: Evaluation")
        print("="*60)
        test_scores = _score_model(best_model, X_test, best_entry)
        test_preds = (test_scores > global_threshold).astype(int)

        mode_col = manifest.get("operating_modes", {}).get("mode_column")
        run_evaluation(test_scores, test_preds, y_test_true, manifest, df_test, mode_col)

        # ── Step 6: Save Model + Threshold ────────────────────────────────────
        print("\n" + "="*60)
        print("[AnomalyTrainer] STEP 6: Saving Model + Threshold")
        print("="*60)
        model_path = manifest.get("paths", {}).get("best_model", "outputs/anomaly_model")
        fmt = manifest.get("deployment_target", {}).get("compilation_format", "pickle")
        saved_path = export_model(best_model, model_path, format=fmt, n_features=len(feature_cols))
        manifest["paths"]["best_model"] = saved_path

        # Save threshold alongside model
        import json, os
        threshold_path = model_path.replace(".pkl", "_threshold.json")
        os.makedirs(os.path.dirname(os.path.abspath(threshold_path)), exist_ok=True)
        with open(threshold_path, "w") as f:
            json.dump({"threshold": global_threshold}, f)
        manifest.setdefault("paths", {})
        manifest["paths"]["threshold"] = threshold_path

        manifest = mark_step_complete(manifest, "anomaly_training")
        print(f"\n[AnomalyTrainer] ✅ Training complete. Model: {saved_path} | Threshold: {global_threshold:.6f}")
        self.manifest = manifest
        return manifest
