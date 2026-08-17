from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import json
import sys
import pandas as pd
from sklearn.model_selection import train_test_split

# ── aiconnex_ml path resolution ───────────────────────────────────────────
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
    title="Data Splitting API",
    description="Splits prepared datasets into train, validation, and test subsets.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SplitPayload(BaseModel):
    prepared_file_path: Optional[str] = None
    engineered_file_path: Optional[str] = None
    recipe: Dict[str, Any]
    run_id: str
    target_column: Optional[str] = None
    manifest_path: Optional[str] = None

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "Split API"}

@app.post("/api/v1/split")
def split_data(payload: SplitPayload):
    try:
        recipe = payload.recipe
        run_id = payload.run_id
        target_col = payload.target_column
        manifest_path = payload.manifest_path

        prep_path = resolve_path(payload.engineered_file_path or payload.prepared_file_path)

        # Auto-resolve by run_id if default placeholder or missing
        if not os.path.exists(prep_path) or "ds1_FD001" in prep_path or "engineered" in prep_path or "prepared" in prep_path or "feature" in prep_path:
            workspace_data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
            run_dir = os.path.join(workspace_data_root, run_id)
            if os.path.exists(run_dir):
                found = False
                for f in os.listdir(run_dir):
                    if f.startswith("feature_") and f.endswith(".csv"):
                        prep_path = os.path.join(run_dir, f)
                        found = True
                        print(f"[AutoResolve] Resolved feature path: {prep_path}")
                        break
                if not found:
                    for f in os.listdir(run_dir):
                        if f.startswith("prepare_") and f.endswith(".csv"):
                            prep_path = os.path.join(run_dir, f)
                            found = True
                            print(f"[AutoResolve] Resolved prepare path: {prep_path}")
                            break

        if not prep_path or not os.path.exists(prep_path):
            raise HTTPException(status_code=404, detail=f"Dataset file not found at {prep_path}")

        df = pd.read_csv(prep_path)

        # ── Save paths ────────────────────────────────────────────────────
        if run_id:
            services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            workspace_data_dir = os.path.join(services_dir, "workspace_data", run_id)
        else:
            workspace_data_dir = os.path.dirname(prep_path)
        os.makedirs(workspace_data_dir, exist_ok=True)
        
        orig_filename = os.path.basename(prep_path)
        dataset_stem = os.path.splitext(orig_filename)[0]
        if dataset_stem.startswith("feature_"):
            dataset_stem = dataset_stem[8:]
        elif dataset_stem.startswith("prepare_"):
            dataset_stem = dataset_stem[8:]
        elif dataset_stem.startswith("dag_"):
            dataset_stem = dataset_stem[4:]
        elif dataset_stem.startswith("profiled_"):
            dataset_stem = dataset_stem[9:]
        elif dataset_stem.startswith("compiled_"):
            dataset_stem = dataset_stem[9:]
            
        train_path = os.path.join(workspace_data_dir, f"split_train_{dataset_stem}.csv")
        val_path   = os.path.join(workspace_data_dir, f"split_val_{dataset_stem}.csv")
        test_path  = os.path.join(workspace_data_dir, f"split_test_{dataset_stem}.csv")

        # ── Read manifest for topology ──────────────────────────────────────
        manifest: Dict[str, Any] = {}
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

        topology = manifest.get("data_topology", "tabular")
        print(f"[SplitNode] Topology='{topology}' | rows={len(df)}")

        # ════════════════════════════════════════════════════
        # BRANCH A: Topology-Enforced Group Split (Time-Series)
        # Delegates to aiconnex_ml.shared.splitter.policy.enforce_split()
        # Guarantees zero entity leakage across train/val/test.
        # ════════════════════════════════════════════════════
        if topology in ("time_series", "multi_entity_time_series"):
            from services.aiconnex_ml.shared.splitter.policy import enforce_split

            # Inject recipe ratios into manifest for enforce_split to use
            manifest.setdefault("split_policy", {})
            manifest["split_policy"]["train_ratio"] = recipe.get("train_size", 0.70)
            manifest["split_policy"]["val_ratio"]   = recipe.get("val_size",   0.15)
            manifest["split_policy"]["random_state"] = recipe.get("random_state", 42)

            train_df, val_df, test_df, manifest = enforce_split(df, manifest)

            split_method = "group_chronological"

        # ════════════════════════════════════════════════════
        # BRANCH B: Random / Stratified Split (Tabular)
        # Original sklearn logic — unchanged.
        # ════════════════════════════════════════════════════
        else:
            test_size      = recipe.get("test_size", 0.2)
            val_size       = recipe.get("val_size",  0.1)
            stratify_flag  = recipe.get("stratify",  False)

            stratify_col = None
            if stratify_flag and target_col and target_col in df.columns:
                y = df[target_col].dropna()
                if len(y) == len(df) and df[target_col].nunique() > 1:
                    class_counts = df[target_col].value_counts()
                    if class_counts.min() >= 2:
                        stratify_col = df[target_col]

            val_test_ratio = test_size + val_size
            if val_test_ratio >= 1.0 or val_test_ratio <= 0.0:
                test_size, val_size, val_test_ratio = 0.15, 0.15, 0.3

            train_val_df, test_df = train_test_split(
                df, test_size=test_size, random_state=42,
                stratify=stratify_col if stratify_col is not None else None
            )
            val_ratio_scaled = val_size / (1.0 - test_size)
            if val_ratio_scaled >= 1.0 or val_ratio_scaled <= 0.0:
                val_ratio_scaled = 0.15
            train_df, val_df = train_test_split(train_val_df, test_size=val_ratio_scaled, random_state=42)

            manifest.setdefault("data_info", {})
            manifest["data_info"]["split_sizes"] = {
                "train": int(len(train_df)),
                "val":   int(len(val_df)),
                "test":  int(len(test_df)),
            }
            split_method = "random_stratified"

        # ── Save partitions ───────────────────────────────────────────────
        train_df.to_csv(train_path, index=False)
        val_df.to_csv(val_path, index=False)
        test_df.to_csv(test_path, index=False)

        # ── Sprint 2: Write split_policy to manifest ─────────────────────────
        if manifest_path:
            try:
                manifest["split_policy"] = manifest.get("split_policy", {})
                manifest["split_policy"].update({
                    "method": split_method,
                    "topology_used": topology,
                    "train_path": train_path,
                    "val_path":   val_path,
                    "test_path":  test_path,
                    "actual_sizes": {
                        "train": int(len(train_df)),
                        "val":   int(len(val_df)),
                        "test":  int(len(test_df)),
                    },
                })
                manifest["pipeline_step"] = "split"
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[SplitNode] Warning: Could not update manifest: {e}")

        return {
            "status": "success",
            "train_path": train_path,
            "val_path":   val_path,
            "test_path":  test_path,
            "topology_used": topology,
            "split_method": split_method,
            "split_sizes": {
                "train": len(train_df),
                "val":   len(val_df),
                "test":  len(test_df),
            },
        }

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Split error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    should_reload = os.environ.get("AIC_RELOAD", "0").lower() in ("true", "1", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=should_reload)
