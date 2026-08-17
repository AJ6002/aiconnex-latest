"""
edge_monitor.py — Live edge inference monitor
=============================================
Runs on the plant floor at the edge node.
Performs:
  1. Live tag name translation (same schema_mapping as training)
  2. Score prediction from loaded model
  3. Anomaly/RUL alert generation
  4. Drift detection on incoming feature batches (PSI/KS)
  5. Logging to a local JSON-lines file for shipment back to cloud

Designed to run as a standalone inference loop with minimal dependencies.
"""

from __future__ import annotations
import json
import os
import pickle
from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd


class EdgeMonitor:
    """
    Lightweight edge inference engine for deployed anomaly/regression models.

    Usage:
        monitor = EdgeMonitor.from_manifest(manifest_path)
        alert = monitor.predict_row(row_dict)
    """

    def __init__(
        self,
        model: Any,
        feature_cols: List[str],
        manifest: Dict[str, Any],
        threshold: Optional[float] = None,
        tag_registry: Optional[Dict[str, Dict[str, str]]] = None,
        log_path: str = "edge_monitor.log.jsonl",
    ):
        self.model = model
        self.feature_cols = feature_cols
        self.manifest = manifest
        self.threshold = threshold
        self.tag_registry = tag_registry or {}
        self.log_path = log_path
        self.ml_task = manifest.get("ml_task", "anomaly")
        self.baseline_scores: List[float] = []  # filled from initial calibration run

    @classmethod
    def from_manifest(cls, manifest: Dict[str, Any]) -> "EdgeMonitor":
        """
        Load model, scaler, and threshold from paths stored in the manifest.
        """
        paths = manifest.get("paths", {})
        model_path = paths.get("best_model")
        threshold_path = paths.get("threshold")

        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at '{model_path}'")

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        threshold = None
        if threshold_path and os.path.exists(threshold_path):
            with open(threshold_path, "r") as f:
                threshold = json.load(f).get("threshold")

        feature_cols = manifest.get("schema_config", {}).get("final_features") or \
                       manifest.get("schema_config", {}).get("raw_features", [])

        return cls(model=model, feature_cols=feature_cols, manifest=manifest, threshold=threshold)

    def translate_tags(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Translate plant-specific tag names to canonical names."""
        translated = {}
        for key, val in row.items():
            canonical = self.tag_registry.get(key, {}).get("canonical", key)
            translated[canonical] = val
        return translated

    def predict_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run inference on a single row (dict of {tag: value}).
        Returns an alert dict with score, decision, and timestamp.
        """
        # Tag translation
        row = self.translate_tags(row)

        # Build feature vector
        feature_vector = np.array([[row.get(col, 0.0) for col in self.feature_cols]])

        # Predict
        if self.ml_task == "regression":
            pred = float(self.model.predict(feature_vector)[0])
            alert = {
                "timestamp": datetime.utcnow().isoformat(),
                "prediction": round(pred, 4),
                "model_type": "regression",
            }
        else:
            # Anomaly
            try:
                score = float(self.model.decision_function(feature_vector)[0])
            except Exception:
                try:
                    score = float(self.model.predict_proba(feature_vector)[0, 1])
                except Exception:
                    score = 0.0

            is_anomaly = bool(score > self.threshold) if self.threshold is not None else None
            alert = {
                "timestamp": datetime.utcnow().isoformat(),
                "anomaly_score": round(score, 6),
                "is_anomaly": is_anomaly,
                "threshold_used": self.threshold,
                "model_type": "anomaly",
            }
            if is_anomaly:
                print(f"[EdgeMonitor] 🚨 ANOMALY DETECTED | score={score:.4f} > threshold={self.threshold:.4f}")

        # Log
        self._log_alert(alert)
        self.baseline_scores.append(alert.get("anomaly_score", alert.get("prediction", 0.0)))
        return alert

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run inference on a batch DataFrame. Returns df with score/prediction columns appended."""
        alerts = []
        for _, row in df.iterrows():
            alerts.append(self.predict_row(row.to_dict()))
        alert_df = pd.DataFrame(alerts)
        return pd.concat([df.reset_index(drop=True), alert_df], axis=1)

    def _log_alert(self, alert: Dict[str, Any]) -> None:
        """Append alert to local JSONL log file."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert) + "\n")
        except Exception as e:
            print(f"[EdgeMonitor] Warning: could not write to log ({e})")

    def compute_recent_psi(self, baseline: np.ndarray, bins: int = 10) -> float:
        """
        Compute PSI between baseline scores and recent inference scores.
        Call periodically (e.g., daily) to detect drift.
        """
        recent = np.array(self.baseline_scores[-len(baseline):])
        if len(recent) < 10:
            return 0.0
        from services.aiconnex_ml.anomaly.drift import compute_psi
        return compute_psi(baseline, recent, bins)
