"""
8_evaluate/main.py — Universal Evaluator Node (Sprint 4)
=========================================================
Routes to the correct aiconnex_ml evaluation function based on ml_task
from the manifest. Runs Advisory VG_2 gate (non-blocking). Writes
evaluation results to the shared manifest (Tier 1 storage).

Topology coverage:
  regression / time_to_event (RUL) → aiconnex_ml.regression.evaluation.run_evaluation
  anomaly_detection              → aiconnex_ml.anomaly.evaluation (metrics only)
  classification                 → sklearn classification metrics
  clustering                     → silhouette + inertia

VG_2 Advisory Mode:
  The gate score is computed and logged. It NEVER blocks deployment;
  deploy_approved is always True unless a hard config override is set.
  This lets the system warn while still shipping.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import os
import sys
import json
import pickle
import datetime
import traceback

import pandas as pd
import numpy as np
from sklearn.metrics import (
    r2_score, mean_absolute_error, mean_squared_error,
    accuracy_score, f1_score, precision_score, recall_score,
    silhouette_score,
)

# ── aiconnex_ml path resolution ───────────────────────────────────────────────
AIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AICONNEX_ML_ROOT = os.path.abspath(os.path.join(AIC_ROOT, "..", "aiconnex_ml"))
if AICONNEX_ML_ROOT not in sys.path:
    sys.path.insert(0, os.path.dirname(AICONNEX_ML_ROOT))

# Windows console encoding fix
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── Robust Path Resolver ──────────────────────────────────────────────────────
def resolve_path(p: str) -> str:
    if not p:
        return p
    p = p.replace("\\", "/").strip()
    if os.path.isabs(p):
        return p
    # Try relative to the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_p = os.path.abspath(os.path.join(script_dir, p))
    if os.path.exists(abs_p):
        return abs_p
    # Try relative to the workspace root (aic/)
    workspace_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    root_p = os.path.join(workspace_root, p)
    if os.path.exists(root_p):
        return root_p
    # Handle 'services/' prefix
    if p.startswith("services/"):
        strip_p = p.replace("services/", "", 1)
        services_dir = os.path.abspath(os.path.join(script_dir, ".."))
        svc_p = os.path.join(services_dir, strip_p)
        if os.path.exists(svc_p):
            return svc_p
    # Fallback to default join with workspace root
    return os.path.join(workspace_root, p)

app = FastAPI(
    title="Universal Evaluator API",
    description=(
        "Topology- and task-aware model evaluation with Advisory VG_2 gate. "
        "Writes results to the shared manifest. Never blocks deployment."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EvaluatePayload(BaseModel):
    model_path: str
    test_path: str
    run_id: Optional[str] = None
    train_path: Optional[str] = None
    val_path: Optional[str] = None
    target_column: Optional[str] = None
    metrics: List[str] = []
    manifest_path: Optional[str] = None


@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "Universal Evaluator API"}


def resolve_file_path(p: Optional[str]) -> Optional[str]:
    if not p:
        return p
    abs_p = resolve_path(p)
    if os.path.exists(abs_p):
        return abs_p
    alt_p = abs_p.replace("\\splits\\", "\\").replace("/splits/", "/")
    if os.path.exists(alt_p):
        return alt_p
    dir_name, file_name = os.path.split(abs_p)
    alt_p2 = os.path.join(dir_name, "splits", file_name)
    if os.path.exists(alt_p2):
        return alt_p2
    return abs_p

@app.post("/api/v1/evaluate")
def evaluate_model(payload: EvaluatePayload):
    try:
        run_id        = payload.run_id
        model_path    = resolve_file_path(payload.model_path)
        test_path     = resolve_file_path(payload.test_path)
        train_path    = resolve_file_path(payload.train_path) if payload.train_path else None
        val_path      = resolve_file_path(payload.val_path) if payload.val_path else None
        target_col    = payload.target_column
        manifest_path = payload.manifest_path

        # Auto-resolve by run_id if default placeholder or missing
        if run_id:
            workspace_data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
            run_dir = os.path.join(workspace_data_root, run_id)
            if os.path.exists(run_dir):
                if not os.path.exists(test_path) or "ds1_FD001" in test_path or "test.csv" in test_path or "split_test" in test_path:
                    for f in os.listdir(run_dir):
                        if f.startswith("split_test_") and f.endswith(".csv"):
                            test_path = os.path.join(run_dir, f)
                            print(f"[AutoResolve] Resolved test split path: {test_path}")
                            break
                if not os.path.exists(model_path) or "model.pkl" in model_path or "trained_" in model_path:
                    for f in os.listdir(run_dir):
                        if f.startswith("trained_") and f.endswith(".pkl"):
                            model_path = os.path.join(run_dir, f)
                            print(f"[AutoResolve] Resolved model path: {model_path}")
                            break

        # ── Validate paths ──────────────────────────────────────────────────
        if not os.path.exists(model_path):
            raise HTTPException(status_code=404, detail=f"Model file not found at {model_path}")
        if not os.path.exists(test_path):
            raise HTTPException(status_code=404, detail=f"Test dataset not found at {test_path}")

        # ── 1. Load manifest ────────────────────────────────────────────────
        manifest: Dict[str, Any] = {}
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

        ml_task   = manifest.get("ml_task", "regression")
        topology  = manifest.get("data_topology", "tabular")
        entity_col = (manifest.get("entity_column")
                      or manifest.get("schema_config", {}).get("entity_column"))

        print(f"[Evaluator] ml_task='{ml_task}' | topology='{topology}' | entity='{entity_col}'")

        # ── 2. Load model ───────────────────────────────────────────────────
        with open(model_path, "rb") as f:
            model = pickle.load(f)

        # ── 2.5. Extract model and scaler from sklearn Pipeline if present ──
        scaler = None
        from sklearn.pipeline import Pipeline
        if isinstance(model, Pipeline):
            print("[Evaluator] Loaded bundled Pipeline. Extracting scaler and estimator steps dynamically.")
            scaler = model.named_steps.get('scaler')
            model = model.named_steps.get('model')

        # ── 3. Load scaler (Sprint 3 output) ────────────────────────────────
        if scaler is None:
            scaler_path = manifest.get("training_results", {}).get("scaler_path")
            if scaler_path and os.path.exists(scaler_path):
                with open(scaler_path, "rb") as f:
                    scaler = pickle.load(f)
                print(f"[Evaluator] Loaded standalone scaler from {scaler_path}")
            else:
                print("[Evaluator] No scaler found — using raw features.")
        else:
            print("[Evaluator] Using scaler extracted from bundled Pipeline.")

        # ── 4. Load data partitions ─────────────────────────────────────────
        df_test  = pd.read_csv(test_path)
        df_train = pd.read_csv(train_path)  if train_path  and os.path.exists(train_path)  else None
        df_val   = pd.read_csv(val_path)    if val_path    and os.path.exists(val_path)    else None

        def _prep_X(df: pd.DataFrame) -> np.ndarray:
            """Drop target, coerce string columns to numeric, align features, fill NaN, apply saved scaler."""
            X = df.copy()
            if target_col and target_col in X.columns:
                X = X.drop(columns=[target_col])

            for col in X.columns:
                if not pd.api.types.is_numeric_dtype(X[col]):
                    X[col] = pd.to_numeric(X[col], errors="coerce")
            X = X.fillna(0)

            # Feature alignment
            if scaler is not None and hasattr(scaler, "feature_names_in_"):
                valid_cols = [c for c in scaler.feature_names_in_ if c != target_col]
                X = X.reindex(columns=valid_cols, fill_value=0)
            elif hasattr(model, "feature_names_in_"):
                valid_cols = [c for c in model.feature_names_in_ if c != target_col]
                X = X.reindex(columns=valid_cols, fill_value=0)
            elif hasattr(model, "n_features_in_"):
                expected_n = model.n_features_in_
                if X.shape[1] != expected_n:
                    if X.shape[1] == expected_n + 1:
                        X = X.iloc[:, :expected_n]
                    elif X.shape[1] > expected_n:
                        X = X.iloc[:, :expected_n]
                    else:
                        pad_cols = [f"pad_{i}" for i in range(expected_n - X.shape[1])]
                        pad_df = pd.DataFrame(0, index=X.index, columns=pad_cols)
                        X = pd.concat([X, pad_df], axis=1)

            return scaler.transform(X) if scaler is not None else X.values

        def _prep_y(df: pd.DataFrame) -> Optional[np.ndarray]:
            if target_col and target_col in df.columns:
                return df[target_col].values
            return None

        X_test  = _prep_X(df_test)
        y_test  = _prep_y(df_test)
        X_train = _prep_X(df_train) if df_train is not None else None
        y_train = _prep_y(df_train) if df_train is not None else None
        X_val   = _prep_X(df_val)   if df_val   is not None else None
        y_val   = _prep_y(df_val)   if df_val   is not None else None

        # ── 5. Route to the correct evaluator ──────────────────────────────
        eval_report: Dict[str, Any] = {}
        model_class = model.__class__.__name__.lower()
        is_rul = (ml_task == "regression"
                  and target_col
                  and any(k in str(target_col).lower() for k in ("rul", "remaining", "time_to")))

        # ── Branch A: Regression / RUL ──────────────────────────────────────
        if ml_task in ("regression", "time_to_event", "rul"):
            try:
                from services.aiconnex_ml.regression.evaluation import (
                    compute_regression_metrics,
                    bootstrap_confidence_interval,
                    per_entity_metrics,
                )
                from sklearn.metrics import root_mean_squared_error

                test_pred = model.predict(X_test)

                eval_report["test"]  = compute_regression_metrics(y_test, test_pred, is_rul=is_rul)
                eval_report["bootstrap_ci_rmse"] = bootstrap_confidence_interval(
                    y_test, test_pred, metric_fn=root_mean_squared_error
                )

                if X_train is not None and y_train is not None:
                    train_pred = model.predict(X_train)
                    eval_report["train"] = compute_regression_metrics(y_train, train_pred, is_rul=is_rul)

                if X_val is not None and y_val is not None:
                    val_pred = model.predict(X_val)
                    eval_report["val"] = compute_regression_metrics(y_val, val_pred, is_rul=is_rul)

                # Overfitting gap
                if "train" in eval_report and "val" in eval_report:
                    eval_report["train_val_rmse_gap"] = round(
                        abs(eval_report["train"]["rmse"] - eval_report["val"]["rmse"]), 4
                    )

                # Per-entity breakdown (multi-asset time-series)
                if entity_col and entity_col in df_test.columns and target_col:
                    eval_report["per_entity"] = per_entity_metrics(
                        df_test, test_pred, entity_col, target_col, is_rul=is_rul
                    )

                primary_metrics = eval_report["test"]
                evaluator_used = "aiconnex_ml.regression"

            except Exception as reg_ex:
                print(f"[Evaluator] aiconnex_ml regression fallback: {reg_ex}")
                preds = model.predict(X_test)
                primary_metrics = _sklearn_regression_metrics(y_test, preds)
                eval_report["test"] = primary_metrics
                evaluator_used = "sklearn_regression_fallback"

        # ── Branch B: Anomaly Detection ─────────────────────────────────────
        elif ml_task == "anomaly_detection" or "isolationforest" in model_class:
            try:
                from services.aiconnex_ml.anomaly.evaluation import compute_anomaly_metrics

                raw_scores = model.decision_function(X_test)      # lower = more anomalous
                preds_raw  = model.predict(X_test)                # +1 normal, -1 anomaly
                y_pred_bin = np.where(preds_raw == -1, 1, 0)
                anom_scores = -raw_scores                          # flip: higher = more anomalous

                if y_test is not None and len(np.unique(y_test)) > 1:
                    primary_metrics = compute_anomaly_metrics(y_test, y_pred_bin, anom_scores)
                else:
                    primary_metrics = {
                        "anomaly_ratio": float(np.mean(y_pred_bin)),
                        "mean_anomaly_score": float(np.mean(anom_scores)),
                    }

                eval_report["test"] = primary_metrics
                evaluator_used = "aiconnex_ml.anomaly"

            except Exception as anm_ex:
                print(f"[Evaluator] Anomaly eval fallback: {anm_ex}")
                preds = model.predict(X_test)
                y_pred_bin = np.where(preds == -1, 1, 0)
                primary_metrics = {"anomaly_ratio": float(np.mean(y_pred_bin))}
                eval_report["test"] = primary_metrics
                evaluator_used = "sklearn_anomaly_fallback"

        # ── Branch C: Classification ────────────────────────────────────────
        elif ml_task == "classification" or "classifier" in model_class:
            preds = model.predict(X_test)
            primary_metrics = {}
            if y_test is not None:
                primary_metrics = {
                    "accuracy":  float(accuracy_score(y_test, preds)),
                    "f1":        float(f1_score(y_test, preds, average="weighted", zero_division=0)),
                    "precision": float(precision_score(y_test, preds, average="weighted", zero_division=0)),
                    "recall":    float(recall_score(y_test, preds, average="weighted", zero_division=0)),
                }
            eval_report["test"] = primary_metrics
            evaluator_used = "sklearn_classification"

        # ── Branch D: Clustering ────────────────────────────────────────────
        elif ml_task == "clustering" or "kmeans" in model_class:
            labels = model.predict(X_test)
            primary_metrics = {"inertia": float(model.inertia_)}
            if len(X_test) > 1:
                sz = min(len(X_test), 2000)
                sub_labels = labels[:sz]
                if len(np.unique(sub_labels)) > 1:
                    primary_metrics["silhouette"] = float(silhouette_score(X_test[:sz], sub_labels))
            eval_report["test"] = primary_metrics
            evaluator_used = "sklearn_clustering"

        # ── Fallback: unknown task → try regression ─────────────────────────
        else:
            preds = model.predict(X_test)
            if y_test is not None:
                primary_metrics = _sklearn_regression_metrics(y_test, preds)
            else:
                primary_metrics = {"samples_evaluated": len(X_test)}
            eval_report["test"] = primary_metrics
            evaluator_used = "generic_fallback"

        # ── 6. Advisory VG_2 Gate (non-blocking) ───────────────────────────
        try:
            from services.aiconnex_ml.monitoring.validation_gate_2 import run_vg2
            # Populate manifest structure required by check_vg2
            manifest.setdefault("results", {})
            manifest["results"]["evaluation"] = {
                "test": primary_metrics
            }
            manifest["results"]["anomaly_evaluation"] = primary_metrics
            manifest.setdefault("quality_gates", {})
            manifest["quality_gates"].setdefault("regression_gates", {"max_rmse": 9999, "min_r2": -1})
            manifest["quality_gates"].setdefault("anomaly_gates", {"min_f1": 0.0})

            _, vg2_report = run_vg2(manifest)
        except Exception as vg2_ex:
            print(f"[VG_2] Warning: Gate run failed with exception: {vg2_ex}. Falling back to advisory logic.")
            vg2_report = _run_advisory_vg2(primary_metrics, ml_task, manifest)

        deploy_approved = True   # ADVISORY MODE — never blocks

        print(f"[VG_2] Advisory result: score={vg2_report.get('score', 1.0) if isinstance(vg2_report.get('score'), (int, float)) else 1.0:.3f} | "
              f"checks={len(vg2_report.get('checks', {}))}")

        # ── 7. Write evaluation results to shared manifest ──────────────────
        if manifest_path:
            try:
                if os.path.exists(manifest_path):
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                manifest.setdefault("results", {})
                manifest["results"]["evaluation"] = {
                    "evaluator_used":   evaluator_used,
                    "ml_task":          ml_task,
                    "topology":         topology,
                    "metrics":          eval_report,
                    "vg2_advisory":     vg2_report,
                    "deploy_approved":  deploy_approved,
                    "evaluated_at":     datetime.datetime.now().isoformat(),
                }
                manifest.setdefault("quality_gate_metrics", {})
                manifest["quality_gate_metrics"]["vg2"] = vg2_report
                manifest["pipeline_step"] = "evaluate"
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[Evaluator] Warning: Could not write manifest: {e}")

        return {
            "status":          "success",
            "metrics":         primary_metrics,
            "evaluation":      eval_report,
            "evaluator_used":  evaluator_used,
            "vg2_advisory":    vg2_report,
            "deploy_approved": deploy_approved,
            "ml_task":         ml_task,
        }

    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Evaluate error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────────────────
# Advisory VG_2 Gate
# ─────────────────────────────────────────────────────────────────────────────

def _run_advisory_vg2(
    metrics: Dict[str, Any],
    ml_task: str,
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Non-blocking VG_2 gate.
    Computes a readiness score [0, 1] and flags warnings, but deploy_approved
    is ALWAYS True (advisory mode until VG_2 is fully hardened in a future sprint).

    Score thresholds (configurable via manifest.validation_gates.vg_2):
      regression  : rmse_threshold, r2_min
      classification: f1_min, accuracy_min
      anomaly     : f1_min (or anomaly_ratio_max)
      clustering  : silhouette_min
    """
    thresholds = manifest.get("validation_gates", {}).get("vg_2", {})
    warnings = []
    score = 1.0

    if ml_task in ("regression", "time_to_event", "rul"):
        r2   = float(metrics.get("r2",   0.0) or 0.0)
        rmse = float(metrics.get("rmse", 9999) or 9999)

        r2_min      = float(thresholds.get("r2_min",      0.5))
        rmse_thresh = float(thresholds.get("rmse_threshold", 20.0))

        if r2 < r2_min:
            warnings.append(f"R² = {r2:.4f} below advisory minimum {r2_min}")
            score -= 0.35
        if rmse > rmse_thresh:
            warnings.append(f"RMSE = {rmse:.4f} above advisory threshold {rmse_thresh}")
            score -= 0.25

    elif ml_task == "classification":
        f1       = float(metrics.get("f1",       0.0) or 0.0)
        accuracy = float(metrics.get("accuracy", 0.0) or 0.0)

        f1_min       = float(thresholds.get("f1_min",       0.7))
        accuracy_min = float(thresholds.get("accuracy_min", 0.75))

        if f1 < f1_min:
            warnings.append(f"F1 = {f1:.4f} below advisory minimum {f1_min}")
            score -= 0.35
        if accuracy < accuracy_min:
            warnings.append(f"Accuracy = {accuracy:.4f} below advisory minimum {accuracy_min}")
            score -= 0.20

    elif ml_task == "anomaly_detection":
        f1    = float(metrics.get("f1",    0.0) or 0.0)
        f1_min = float(thresholds.get("f1_min", 0.5))
        if f1 < f1_min and f1 > 0:
            warnings.append(f"Anomaly F1 = {f1:.4f} below advisory minimum {f1_min}")
            score -= 0.30

    score = round(max(0.0, min(1.0, score)), 4)

    return {
        "gate":     "VG_2",
        "mode":     "advisory",
        "score":    score,
        "passed":   score >= 0.5,
        "warnings": warnings,
        "note":     "Non-blocking advisory mode. Deploy proceeds regardless of score.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sklearn Regression Fallback Helper
# ─────────────────────────────────────────────────────────────────────────────

def _sklearn_regression_metrics(y_true, y_pred) -> Dict[str, float]:
    if y_true is None:
        return {"samples_evaluated": int(len(y_pred))}
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "r2":   round(float(r2_score(y_true, y_pred)), 4),
        "mae":  round(float(mean_absolute_error(y_true, y_pred)), 4),
        "mse":  round(mse, 4),
        "rmse": round(float(np.sqrt(mse)), 4),
    }


if __name__ == "__main__":
    import uvicorn
    should_reload = os.environ.get("AIC_RELOAD", "0").lower() in ("true", "1", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8007, reload=should_reload)
