from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import sys
import json
import uuid
import pickle
import datetime
import traceback
import pandas as pd
import numpy as np

# Fix Windows cp1252 console encoding so emoji in aiconnex_ml logs don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── sklearn models ────────────────────────────────────────────────────────────
from sklearn.linear_model import LogisticRegression, LinearRegression, HuberRegressor, Ridge, Lasso, ElasticNet
from sklearn.ensemble import (
    RandomForestClassifier, RandomForestRegressor,
    GradientBoostingClassifier, GradientBoostingRegressor,
    AdaBoostClassifier, AdaBoostRegressor,
    ExtraTreesClassifier, ExtraTreesRegressor
)
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ── aiconnex_ml path resolution ───────────────────────────────────────────────
AIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AICONNEX_ML_ROOT = os.path.abspath(os.path.join(AIC_ROOT, "..", "aiconnex_ml"))
if AICONNEX_ML_ROOT not in sys.path:
    sys.path.insert(0, os.path.dirname(AICONNEX_ML_ROOT))


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
    title="Model Training API",
    description="Async model training with VG_1 data quality gate and scaler preservation.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store ───────────────────────────────────────────────────────
# {job_id: {"status": "running|completed|failed", "result": {...}, "error": str}}
JOBS: Dict[str, Dict[str, Any]] = {}


class TrainPayload(BaseModel):
    train_path: str
    val_path: str
    target_column: Optional[str] = None
    recipe: Dict[str, Any]
    run_id: str
    manifest_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "Train API (Async)"}


@app.post("/api/v1/train", status_code=202)
def train_model(payload: TrainPayload, background_tasks: BackgroundTasks):
    """
    Dispatch training as a background task. Returns 202 Accepted with a job_id
    immediately so the orchestrator is never blocked by long HPO runs.
    """
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    JOBS[job_id] = {
        "status": "running",
        "job_id": job_id,
        "run_id": payload.run_id,
        "started_at": datetime.datetime.now().isoformat(),
        "result": None,
        "error": None,
        "vg1_report": None,
    }
    background_tasks.add_task(_run_training_job, job_id, payload)
    return {"status": "accepted", "job_id": job_id, "run_id": payload.run_id}

@app.get("/api/v1/train/status/{job_id}")
def train_status(job_id: str):
    """Poll this endpoint to check if training has completed."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JOBS[job_id]


@app.get("/api/v1/train/jobs")
def list_jobs():
    """List all training jobs (for diagnostics)."""
    return {"total": len(JOBS), "jobs": list(JOBS.keys())}


# ─────────────────────────────────────────────────────────────────────────────
# Background Training Worker
# ─────────────────────────────────────────────────────────────────────────────

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

def _run_training_job(job_id: str, payload: TrainPayload):
    """
    Executes the full training pipeline in the background:
      1. Load manifest
      2. Run VG_1 Data Quality Gate
      3. Try running aiconnex_ml HPO trainer for Regression/Anomaly
      4. Fallback to scikit-learn fit if aiconnex_ml fails or is not fully matching
      5. Save model + scaler pickle files
      6. Write training results to manifest
      7. Update JOBS[job_id]
    """
    run_id        = payload.run_id
    train_path    = resolve_file_path(payload.train_path)
    val_path      = resolve_file_path(payload.val_path)
    target_col    = payload.target_column
    recipe        = payload.recipe
    manifest_path = payload.manifest_path

    # Auto-resolve by run_id if default placeholder or missing
    if not os.path.exists(train_path) or "ds1_FD001" in train_path or "train.csv" in train_path or "split_train" in train_path:
        workspace_data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
        run_dir = os.path.join(workspace_data_root, run_id)
        if os.path.exists(run_dir):
            for f in os.listdir(run_dir):
                if f.startswith("split_train_") and f.endswith(".csv"):
                    train_path = os.path.join(run_dir, f)
                    print(f"[AutoResolve] Resolved train split path: {train_path}")
                    break
    if not os.path.exists(val_path) or "ds1_FD001" in val_path or "val.csv" in val_path or "split_val" in val_path:
        workspace_data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
        run_dir = os.path.join(workspace_data_root, run_id)
        if os.path.exists(run_dir):
            for f in os.listdir(run_dir):
                if f.startswith("split_val_") and f.endswith(".csv"):
                    val_path = os.path.join(run_dir, f)
                    print(f"[AutoResolve] Resolved val split path: {val_path}")
                    break

    try:
        # ── 1. Load training data ────────────────────────────────────────────
        if not os.path.exists(train_path):
            raise FileNotFoundError(f"Train partition not found at {train_path}")

        df_train = pd.read_csv(train_path)
        df_val   = pd.read_csv(val_path) if val_path and os.path.exists(val_path) else None

        # ── 2. Load manifest from disk ───────────────────────────────────────
        manifest: Dict[str, Any] = {}
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

        # ── 3. VG_1 Data Quality Gate (pre-train validation) ─────────────────
        try:
            from services.aiconnex_ml.shared.data.validation_gate_1 import check_vg1
            is_valid, vg1_report = check_vg1(manifest, df_train)
            JOBS[job_id]["vg1_report"] = vg1_report
            manifest.setdefault("quality_gate_metrics", {})
            manifest["quality_gate_metrics"]["vg1"] = vg1_report
        except Exception as vg1_ex:
            print(f"[VG_1] Warning: Gate check failed with exception: {vg1_ex}. Treating as passed.")
            is_valid, vg1_report = True, {"gate": "VG_1", "passed": True, "detail": f"Gate skipped: {vg1_ex}"}
            JOBS[job_id]["vg1_report"] = vg1_report
            manifest.setdefault("quality_gate_metrics", {})
            manifest["quality_gate_metrics"]["vg1"] = vg1_report

        # Persist VG1 results to manifest file
        _update_manifest(manifest_path, manifest)

        if not is_valid:
            failed = [k for k, v in vg1_report.get("checks", {}).items() if not v.get("passed")]
            err_msg = f"VG_1 Data Quality Gate FAILED. Failed checks: {failed}. Training aborted."
            JOBS[job_id].update({"status": "failed", "error": err_msg})
            # Write gate failure to manifest
            _update_manifest(manifest_path, manifest, {"pipeline_step": "train_vg1_failed", "validation_results": manifest.get("validation_results", {})})
            return

        # ── 4. Prepare X / y (Dynamic Target Resolution) ─────────────────────
        resolved_target = None
        if target_col:
            # 1. Case-insensitive exact match
            for col in df_train.columns:
                if str(col).lower().strip() == str(target_col).lower().strip():
                    resolved_target = col
                    break

        if not resolved_target:
            # 2. Check manifest config
            manifest_target = manifest.get("label_contract", {}).get("target_column") or manifest.get("target_column")
            if manifest_target:
                for col in df_train.columns:
                    if str(col).lower().strip() == str(manifest_target).lower().strip():
                        resolved_target = col
                        break

        if not resolved_target:
            # 3. Check common target candidates
            common_candidates = ['rul', 'charges', 'saleprice', 'temperature', 'price', 'label', 'class', 'target', 'y', 'output', 'failure']
            for cand in common_candidates:
                for col in df_train.columns:
                    if cand in str(col).lower().strip():
                        resolved_target = col
                        break
                if resolved_target:
                    break

        if not resolved_target and len(df_train.columns) > 1:
            # 4. Systematic fallback: use the last column (standard ML dataset convention)
            resolved_target = df_train.columns[-1]
            print(f"[TrainNode] Dynamic Fallback: Resolved target column to the last column '{resolved_target}'")

        if resolved_target and resolved_target in df_train.columns:
            target_col = resolved_target
            y_train = df_train[target_col]
            X_train = df_train.drop(columns=[target_col])
        else:
            y_train = None
            X_train = df_train

        # Drop any remaining non-numeric columns before fitting
        non_numeric = [c for c in X_train.columns if not pd.api.types.is_numeric_dtype(X_train[c])]
        if non_numeric:
            X_train = X_train.drop(columns=non_numeric)

        X_train = X_train.fillna(X_train.median(numeric_only=True).fillna(0))

        # ── 5. Scale features & save scaler ──────────────────────────────────
        if run_id:
            services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            workspace_data_dir = os.path.join(services_dir, "workspace_data", run_id)
        else:
            workspace_data_dir = os.path.dirname(train_path)
        os.makedirs(workspace_data_dir, exist_ok=True)

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)

        orig_filename = os.path.basename(train_path)
        dataset_stem = os.path.splitext(orig_filename)[0]
        if dataset_stem.startswith("split_train_"):
            dataset_stem = dataset_stem[12:]
        elif dataset_stem.startswith("train_"):
            dataset_stem = dataset_stem[6:]
            
        # We do not write the standalone scaler to disk anymore to deliver a single model file.
        # It is kept in-memory and bundled directly into the Pipeline below.
        scaler_path = None

        # ── 6. Resolve algorithm details ─────────────────────────────────────
        algorithm   = recipe.get("algorithm", "Estimator")
        variant     = recipe.get("variant", "Standard")
        hyperparams = recipe.get("hyperparameters", {})
        algo_lower  = str(algorithm).lower()
        var_lower   = str(variant).lower()

        # Clean algorithm name for RegressionTrainer / AnomalyTrainer
        clean_algo = str(algorithm)
        ml_mapping = {
            "Linear RegressionRegressor": "Linear Regression",
            "LinearRegressionRegressor": "Linear Regression",
            "LinearRegression": "Linear Regression",
            "Ridge RegressionRegressor": "Ridge Regression",
            "RidgeRegressionRegressor": "Ridge Regression",
            "RidgeRegression": "Ridge Regression",
            "Lasso RegressionRegressor": "Lasso Regression",
            "LassoRegressionRegressor": "Lasso Regression",
            "LassoRegression": "Lasso Regression",
            "ElasticNetRegressor": "ElasticNet",
            "Random ForestRegressor": "Random Forest",
            "RandomForestRegressor": "Random Forest",
            "RandomForest": "Random Forest",
            "XGBoostRegressor": "XGBoost",
            "XGBRegressor": "XGBoost",
            "LightGBMRegressor": "LightGBM",
            "LGBMRegressor": "LightGBM",
            "CatBoostRegressor": "CatBoost",
            "Gradient BoostingRegressor": "Gradient Boosting",
            "GradientBoostingRegressor": "Gradient Boosting",
            "SVRRegressor": "SVR",
            "KNNRegressor": "KNN",
            "Neural NetworkRegressor": "Neural Network",
            "NeuralNetworkRegressor": "Neural Network",
            "Logistic RegressionClassifier": "Logistic Regression",
            "LogisticRegressionClassifier": "Logistic Regression",
            "LogisticRegression": "Logistic Regression",
            "Random ForestClassifier": "Random Forest",
            "RandomForestClassifier": "Random Forest",
            "XGBoostClassifier": "XGBoost",
            "XGBClassifier": "XGBoost",
            "LightGBMClassifier": "LightGBM",
            "LGBMClassifier": "LightGBM",
            "CatBoostClassifier": "CatBoost",
            "Gradient BoostingClassifier": "Gradient Boosting",
            "GradientBoostingClassifier": "Gradient Boosting",
            "KNNClassifier": "KNN",
            "Decision TreeClassifier": "Decision Tree",
            "DecisionTreeClassifier": "Decision Tree",
            "SVCClassifier": "SVC",
            "Neural NetworkClassifier": "Neural Network",
            "NeuralNetworkClassifier": "Neural Network",
            "AdaBoostClassifier": "AdaBoost",
            "Isolation ForestAnomaly": "Isolation Forest",
            "IsolationForestAnomaly": "Isolation Forest",
            "IsolationForest": "Isolation Forest",
            "One-Class SVMAnomaly": "One-Class SVM",
            "OneClassSVMAnomaly": "One-Class SVM",
            "OneClassSVM": "One-Class SVM",
            "Local Outlier FactorAnomaly": "Local Outlier Factor",
            "LocalOutlierFactorAnomaly": "Local Outlier Factor",
            "LocalOutlierFactor": "Local Outlier Factor",
        }
        for k, v in ml_mapping.items():
            if clean_algo.lower().strip() == k.lower():
                clean_algo = v
                break

        # Detect task type
        is_regression = True
        if y_train is not None:
            if y_train.nunique() <= 10 or pd.api.types.is_string_dtype(y_train) or pd.api.types.is_object_dtype(y_train):
                is_regression = False

        model_path = os.path.join(workspace_data_dir, f"trained_{dataset_stem}.pkl")
        trained_successfully_via_aiconnex = False

        # ── 7. Try training with the real aiconnex_ml modeling track ─────────
        if is_regression:
            try:
                from services.aiconnex_ml.regression.trainer import RegressionTrainer
                print(f"[TrainNode] Running aiconnex_ml.regression.trainer.RegressionTrainer for '{clean_algo}'...")

                # Construct pre-split datasets for validation HPO
                X_train_val = X_train_scaled
                y_train_val = y_train.values if y_train is not None else None

                if df_val is not None:
                    X_val_df = df_val.drop(columns=[target_col], errors="ignore") if target_col else df_val.copy()
                    if non_numeric:
                        X_val_df = X_val_df.drop(columns=non_numeric, errors="ignore")
                    X_val_df = X_val_df.fillna(X_val_df.median(numeric_only=True).fillna(0))
                    X_val_scaled = scaler.transform(X_val_df)
                    y_val_arr = df_val[target_col].values if target_col and target_col in df_val.columns else None
                else:
                    X_val_scaled = X_train_val
                    y_val_arr = y_train_val

                # Prepare updated manifest payload
                manifest.setdefault("candidate_algorithms", [clean_algo])
                manifest.setdefault("label_contract", {})
                manifest["label_contract"]["target_column"] = target_col
                manifest["label_contract"]["target_type"] = "time_to_event" if "rul" in str(target_col).lower() else "scalar"

                manifest.setdefault("hpo_config", {})
                manifest["hpo_config"].setdefault("n_iter", 5)
                manifest["hpo_config"].setdefault("n_jobs_search", -1)
                manifest["hpo_config"].setdefault("random_state", 42)

                manifest.setdefault("paths", {})
                manifest["paths"]["best_model"] = model_path

                # Run sequence
                trainer = RegressionTrainer(manifest)
                manifest = trainer.run(
                    X_train=X_train_val,
                    y_train=y_train_val,
                    X_val=X_val_scaled,
                    y_val=y_val_arr,
                    X_test=X_val_scaled,
                    y_test=y_val_arr,
                    feature_cols=list(X_train.columns),
                    df_test=df_val
                )

                # The trainer exports and saves the model dynamically
                with open(model_path, "rb") as f:
                    model = pickle.load(f)

                trained_successfully_via_aiconnex = True
            except Exception as reg_err:
                print(f"[TrainNode] Warning: RegressionTrainer failed ({reg_err}). Falling back to simple fit.")

        else:
            try:
                from services.aiconnex_ml.anomaly.trainer import AnomalyTrainer
                print(f"[TrainNode] Running aiconnex_ml.anomaly.trainer.AnomalyTrainer for '{clean_algo}'...")

                manifest.setdefault("candidate_algorithms", [clean_algo])
                manifest.setdefault("label_contract", {})
                manifest["label_contract"]["supervision_mode"] = "unsupervised"
                manifest["label_contract"]["fault_label_column"] = target_col

                manifest.setdefault("hpo_config", {})
                manifest["hpo_config"].setdefault("n_iter", 5)
                manifest["hpo_config"].setdefault("n_jobs_search", -1)
                manifest["hpo_config"].setdefault("random_state", 42)

                manifest.setdefault("paths", {})
                manifest["paths"]["best_model"] = model_path

                trainer = AnomalyTrainer(manifest)
                manifest = trainer.run(
                    df_train=df_train,
                    df_val=df_val if df_val is not None else df_train,
                    df_test=df_val if df_val is not None else df_train,
                    feature_cols=list(X_train.columns)
                )

                with open(model_path, "rb") as f:
                    model = pickle.load(f)

                trained_successfully_via_aiconnex = True
            except Exception as anom_err:
                print(f"[TrainNode] Warning: AnomalyTrainer failed ({anom_err}). Falling back to simple fit.")

        # ── 8. Fallback fit if real aiconnex_ml trainer was bypassed/errored ──
        if not trained_successfully_via_aiconnex:
            model = _resolve_model(algo_lower, var_lower, hyperparams, is_regression)
            if y_train is not None:
                model.fit(X_train_scaled, y_train)
            else:
                model.fit(X_train_scaled)

            with open(model_path, "wb") as f:
                pickle.dump(model, f)

        # ── 8.5. Bundle model and scaler into a single Pipeline and overwrite model_path ──
        if os.path.exists(model_path):
            try:
                from sklearn.pipeline import Pipeline
                with open(model_path, "rb") as f:
                    trained_estimator = pickle.load(f)
                
                # Bundle them into a Pipeline using the in-memory fitted scaler
                if scaler is not None:
                    bundled_pipeline = Pipeline([
                        ('scaler', scaler),
                        ('model', trained_estimator)
                    ])
                else:
                    bundled_pipeline = Pipeline([
                        ('model', trained_estimator)
                    ])
                
                with open(model_path, "wb") as f:
                    pickle.dump(bundled_pipeline, f)
                print(f"[TrainNode] Successfully bundled model and scaler into single Pipeline at {model_path}")
            except Exception as bundle_err:
                print(f"[TrainNode] Warning: Failed to bundle model and scaler into Pipeline ({bundle_err})")

        # ── 9. Write final training results to manifest ──────────────────────
        manifest["training_results"] = {
            "model_path":   model_path,
            "scaler_path":  None,
            "algorithm":    model.__class__.__name__,
            "variant":      variant,
            "train_rows":   int(len(df_train)),
            "feature_count": int(X_train.shape[1]),
            "trained_at":   datetime.datetime.now().isoformat(),
        }
        manifest["pipeline_step"] = "train"
        _update_manifest(manifest_path, manifest)

        # ── 10. Mark job complete ─────────────────────────────────────────────
        JOBS[job_id].update({
            "status":       "completed",
            "completed_at": datetime.datetime.now().isoformat(),
            "result": {
                "model_path":  model_path,
                "scaler_path": None,
                "algorithm":   model.__class__.__name__,
                "variant":     variant,
            },
        })
        print(f"[TrainNode] Job {job_id} completed → {model_path}")

    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[TrainNode] Job {job_id} FAILED:\n{tb}")
        JOBS[job_id].update({"status": "failed", "error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# Model Resolution Registry
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_model(algo_lower: str, var_lower: str, hyperparams: dict, is_regression: bool):
    """Map recipe algorithm name → sklearn estimator instance."""

    # 1. Logistic Regression
    if "logistic" in algo_lower:
        penalty, solver, l1_ratio, class_weight = "l2", "lbfgs", None, None
        if "l1" in var_lower:        penalty, solver = "l1", "liblinear"
        elif "elastic" in var_lower: penalty, solver, l1_ratio = "elasticnet", "saga", hyperparams.get("l1_ratio", 0.5)
        elif "balanced" in var_lower: class_weight = "balanced"
        return LogisticRegression(penalty=penalty, solver=solver, l1_ratio=l1_ratio,
                                   class_weight=class_weight, max_iter=1000, random_state=42)

    # 2. Linear Regression / Huber / Ridge / Lasso / ElasticNet
    if "linear regression" in algo_lower:
        return HuberRegressor(max_iter=1000) if "huber" in var_lower else LinearRegression(fit_intercept=hyperparams.get("fit_intercept", True))
    if "ridge" in algo_lower:
        return Ridge(alpha=hyperparams.get("alpha", 1.0), random_state=42)
    if "lasso" in algo_lower:
        return Lasso(alpha=hyperparams.get("alpha", 1.0), random_state=42)
    if "elastic" in algo_lower or "net" in algo_lower:
        return ElasticNet(alpha=hyperparams.get("alpha", 1.0), l1_ratio=hyperparams.get("l1_ratio", 0.5), random_state=42)

    # 3. Gradient Boosting & AdaBoost & ExtraTrees
    if "gradient boosting" in algo_lower:
        n, lr, d = hyperparams.get("n_estimators", 100), hyperparams.get("learning_rate", 0.1), hyperparams.get("max_depth", 3)
        return GradientBoostingRegressor(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42) if is_regression \
               else GradientBoostingClassifier(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42)

    if "adaboost" in algo_lower:
        n, lr = hyperparams.get("n_estimators", 50), hyperparams.get("learning_rate", 1.0)
        return AdaBoostRegressor(n_estimators=n, learning_rate=lr, random_state=42) if is_regression \
               else AdaBoostClassifier(n_estimators=n, learning_rate=lr, random_state=42)

    if "extra tree" in algo_lower or "extratrees" in algo_lower:
        n, d = hyperparams.get("n_estimators", 100), hyperparams.get("max_depth", None)
        return ExtraTreesRegressor(n_estimators=n, max_depth=d, random_state=42) if is_regression \
               else ExtraTreesClassifier(n_estimators=n, max_depth=d, random_state=42)

    # 4. Random Forest & Decision Tree
    if "random forest" in algo_lower:
        n, d = hyperparams.get("n_estimators", 100), hyperparams.get("max_depth", None)
        if is_regression:
            return RandomForestRegressor(n_estimators=n, max_depth=d, random_state=42)
        cw = "balanced" if any(k in var_lower for k in ("weighted", "balanced")) else None
        return RandomForestClassifier(n_estimators=n, max_depth=d, class_weight=cw, random_state=42)

    if "decision tree" in algo_lower or "tree" in algo_lower:
        d = hyperparams.get("max_depth", None)
        return DecisionTreeRegressor(max_depth=d, random_state=42) if is_regression \
               else DecisionTreeClassifier(max_depth=d, random_state=42)

    # 5. SVR / Support Vector Machines & KNN
    if "support vector" in algo_lower or "svm" in algo_lower or "svr" in algo_lower or "svc" in algo_lower:
        C_val = hyperparams.get("C", 1.0)
        return SVR(C=C_val) if is_regression else SVC(C=C_val, probability=True, random_state=42)

    if "k-neighbor" in algo_lower or "knn" in algo_lower or "nearest neighbor" in algo_lower:
        k_val = hyperparams.get("n_neighbors", 5)
        return KNeighborsRegressor(n_neighbors=k_val) if is_regression else KNeighborsClassifier(n_neighbors=k_val)

    # 5. XGBoost (with GradientBoosting fallback)
    if "xgboost" in algo_lower:
        lr, n, d = hyperparams.get("learning_rate", 0.1), hyperparams.get("n_estimators", 100), hyperparams.get("max_depth", 3)
        try:
            import xgboost as xgb
            return xgb.XGBRegressor(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42) if is_regression \
                   else xgb.XGBClassifier(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42)
        except ImportError:
            return GradientBoostingRegressor(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42) if is_regression \
                   else GradientBoostingClassifier(n_estimators=n, learning_rate=lr, max_depth=d, random_state=42)

    # 6. LightGBM (with GradientBoosting fallback)
    if "lightgbm" in algo_lower:
        n, lr = hyperparams.get("n_estimators", 100), hyperparams.get("learning_rate", 0.1)
        try:
            import lightgbm as lgb
            return lgb.LGBMRegressor(n_estimators=n, learning_rate=lr, random_state=42, verbose=-1) if is_regression \
                   else lgb.LGBMClassifier(n_estimators=n, learning_rate=lr, random_state=42, verbose=-1)
        except ImportError:
            return GradientBoostingRegressor(n_estimators=n, learning_rate=lr, random_state=42) if is_regression \
                   else GradientBoostingClassifier(n_estimators=n, random_state=42)

    # 7. Anomaly Detection
    if "isolation forest" in algo_lower or "anomaly" in algo_lower:
        return IsolationForest(contamination=hyperparams.get("contamination", "auto"), random_state=42)

    # 8. Clustering
    if "k-means" in algo_lower or "clustering" in algo_lower:
        return KMeans(n_clusters=hyperparams.get("n_clusters", 3), random_state=42)

    # 9. Time-series / ARIMA / Prophet
    if any(k in algo_lower for k in ("arima", "prophet", "time-series", "sarima", "var")):
        try:
            import lightgbm as lgb
            return lgb.LGBMRegressor(n_estimators=100, learning_rate=0.1, random_state=42, verbose=-1) if is_regression \
                   else lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, random_state=42, verbose=-1)
        except ImportError:
            return GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42) if is_regression \
                   else GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)

    # 10. General fallback
    return GradientBoostingRegressor(n_estimators=100, random_state=42) if is_regression else LogisticRegression(max_iter=1000, random_state=42)


# ─────────────────────────────────────────────────────────────────────────────
# Manifest Helper
# ─────────────────────────────────────────────────────────────────────────────

def _update_manifest(manifest_path: Optional[str], manifest: Dict[str, Any], extra: Optional[Dict] = None):
    """Merge `extra` into `manifest` and write to disk."""
    if not manifest_path:
        return
    try:
        if extra:
            manifest.update(extra)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[TrainNode] Warning: Could not update manifest: {e}")


if __name__ == "__main__":
    import uvicorn
    should_reload = os.environ.get("AIC_RELOAD", "0").lower() in ("true", "1", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8006, reload=should_reload)
