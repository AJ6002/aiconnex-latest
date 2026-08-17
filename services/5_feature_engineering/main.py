from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import sys
import os
import pandas as pd
import numpy as np

# ── aiconnex_ml path resolution ──────────────────────────────────────────────
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
    title="Feature Engineering API",
    description="Transforms, creates interaction terms, applies PCA, and performs feature selection on prepared tabular datasets.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FeatureEngineerPayload(BaseModel):
    prepared_file_path: str
    recipe: Dict[str, Any]
    run_id: str
    target_column: Optional[str] = None
    manifest_path: Optional[str] = None

class ChartPlotPayload(BaseModel):
    file_path: str
    target_column: Optional[str] = None

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "Feature Engineering API"}

@app.post("/api/v1/feature_engineer")
def feature_engineer_data(payload: FeatureEngineerPayload):
    try:
        recipe = payload.recipe
        run_id = payload.run_id
        target_col = payload.target_column
        manifest_path = payload.manifest_path

        prep_path = resolve_path(payload.prepared_file_path)

        # Auto-resolve by run_id if default placeholder or missing
        if not os.path.exists(prep_path) or "ds1_FD001" in prep_path or "prepared.csv" in prep_path or "prepare" in prep_path:
            workspace_data_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
            run_dir = os.path.join(workspace_data_root, run_id)
            if os.path.exists(run_dir):
                for f in os.listdir(run_dir):
                    if f.startswith("prepare_") and f.endswith(".csv"):
                        prep_path = os.path.join(run_dir, f)
                        print(f"[AutoResolve] Resolved prepared path: {prep_path}")
                        break

        if not os.path.exists(prep_path):
            raise HTTPException(status_code=404, detail=f"Prepared dataset file not found at {prep_path}")

        # Load prepared file
        df = pd.read_csv(prep_path)
        orig_feature_count = len(df.columns)

        # ── Read manifest to determine topology ────────────────────────
        manifest: Dict[str, Any] = {}
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

        topology = manifest.get("data_topology", "tabular")
        entity_col = manifest.get("entity_column") or manifest.get("schema_config", {}).get("entity_column")
        timestamp_col = manifest.get("timestamp_column") or manifest.get("schema_config", {}).get("timestamp_column")
        numeric_cols = [c for c in df.columns if c != target_col and pd.api.types.is_numeric_dtype(df[c])]

        print(f"[FeatureEng] Topology='{topology}' | entity='{entity_col}' | features={len(numeric_cols)}")

        # ══════════════════════════════════════════════════════
        # BRANCH A: Temporal features (Time-Series topologies)
        # Lags + Rolling + Diff REPLACE Poly/PCA to preserve physics.
        # ══════════════════════════════════════════════════════
        if topology in ("time_series", "multi_entity_time_series"):
            from services.aiconnex_ml.shared.features.lag import add_lag_features, add_diff_features
            from services.aiconnex_ml.shared.features.rolling import add_rolling_features

            # Read recipe overrides or use sensible defaults
            lags = recipe.get("lag_steps", [1, 2, 5])
            windows = recipe.get("rolling_windows", [5, 10])
            sensor_cols = [c for c in numeric_cols if c not in (entity_col, timestamp_col)]

            if entity_col and entity_col in df.columns:
                # Group-aware: sort by entity then time before windowing
                sort_keys = [entity_col] + ([timestamp_col] if timestamp_col and timestamp_col in df.columns else [])
                df = df.sort_values(sort_keys).reset_index(drop=True)
                group_col = entity_col
            else:
                if timestamp_col and timestamp_col in df.columns:
                    df = df.sort_values(timestamp_col).reset_index(drop=True)
                group_col = None

            # Apply temporal feature engineering via aiconnex_ml
            df = add_lag_features(df, cols=sensor_cols, lags=lags, group_col=group_col)
            df = add_rolling_features(df, cols=sensor_cols, window_sizes=windows, group_col=group_col)
            df = add_diff_features(df, cols=sensor_cols, periods=[1], group_col=group_col)

            # Fill NaNs introduced by lag/rolling (first rows per entity have no history)
            df = df.bfill().fillna(0)

            # Re-ensure target column is last
            if target_col and target_col in df.columns:
                cols_ordered = [c for c in df.columns if c != target_col] + [target_col]
                df = df[cols_ordered]

            feature_method = "temporal_lag_rolling_diff"

        # ══════════════════════════════════════════════════════
        # BRANCH B: Tabular features (Polynomial + PCA + SelectKBest)
        # Original logic — unchanged.
        # ══════════════════════════════════════════════════════
        else:
            from sklearn.preprocessing import PolynomialFeatures
            from sklearn.decomposition import PCA
            from sklearn.feature_selection import SelectKBest, f_classif, f_regression

            target_series = df[target_col].copy() if target_col and target_col in df.columns else None

            # 1. Row-wise aggregate features
            create_aggs = recipe.get("create_aggregate_features", True)
            if create_aggs and len(numeric_cols) >= 2:
                df["feat_row_mean"] = df[numeric_cols].mean(axis=1)
                df["feat_row_std"] = df[numeric_cols].std(axis=1).fillna(0)
                df["feat_row_sum"] = df[numeric_cols].sum(axis=1)

            # 2. Interaction & Polynomial Features
            poly_degree = recipe.get("polynomial_degree", 1)
            interaction_only = recipe.get("interaction_features", False)
            if (poly_degree > 1 or interaction_only) and len(numeric_cols) >= 2:
                variances = df[numeric_cols].var().sort_values(ascending=False)
                top_numeric = list(variances.head(6).index)
                if len(top_numeric) >= 2:
                    poly = PolynomialFeatures(degree=min(poly_degree, 2), interaction_only=interaction_only, include_bias=False)
                    poly_array = poly.fit_transform(df[top_numeric].fillna(0))
                    feature_names = poly.get_feature_names_out(top_numeric)
                    for idx, name in enumerate(feature_names):
                        clean_name = name.replace(" ", "_")
                        if clean_name not in df.columns and (" " in name or "^" in name or "*" in name):
                            df[clean_name] = poly_array[:, idx]

            # 3. PCA Features
            pca_comps = recipe.get("pca_components", 0)
            if pca_comps > 0 and len(numeric_cols) >= 3:
                actual_comps = min(pca_comps, len(numeric_cols), min(df.shape) - 1)
                if actual_comps >= 1:
                    pca = PCA(n_components=actual_comps)
                    pca_transformed = pca.fit_transform(df[numeric_cols].fillna(0))
                    for i in range(actual_comps):
                        df[f"pca_comp_{i+1}"] = pca_transformed[:, i]

            # 4. Feature Selection
            sel_method = recipe.get("feature_selection_method", "none")
            k_best = recipe.get("k_best_features", 15)
            if sel_method == "k_best" and target_series is not None and len(df.columns) > k_best + 1:
                all_feat_cols = [c for c in df.columns if c != target_col]
                num_feat_cols = [c for c in all_feat_cols if pd.api.types.is_numeric_dtype(df[c])]
                if len(num_feat_cols) > k_best:
                    try:
                        is_classification = target_series.nunique() < 20 or not pd.api.types.is_numeric_dtype(target_series)
                        score_func = f_classif if is_classification else f_regression
                        selector = SelectKBest(score_func=score_func, k=min(k_best, len(num_feat_cols)))
                        selector.fit(
                            df[num_feat_cols].fillna(0),
                            target_series.astype(float) if pd.api.types.is_numeric_dtype(target_series) else target_series.astype("category").cat.codes
                        )
                        selected_mask = selector.get_support()
                        selected_numeric = [num_feat_cols[i] for i, v in enumerate(selected_mask) if v]
                        non_numeric_cols = [c for c in all_feat_cols if c not in num_feat_cols]
                        df = df[selected_numeric + non_numeric_cols + ([target_col] if target_col in df.columns else [])]
                    except Exception as ex:
                        print("Feature selection warning:", ex)

            # Re-ensure target column is last
            if target_col and target_col in df.columns:
                cols_ordered = [c for c in df.columns if c != target_col] + [target_col]
                df = df[cols_ordered]

            feature_method = "tabular_poly_pca_select"

        # ── Save engineered dataset ────────────────────────────────────
        if run_id:
            services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            workspace_data_dir = os.path.join(services_dir, "workspace_data", run_id)
        else:
            workspace_data_dir = os.path.dirname(prep_path)
        os.makedirs(workspace_data_dir, exist_ok=True)
        
        orig_filename = os.path.basename(prep_path)
        dataset_stem = os.path.splitext(orig_filename)[0]
        if dataset_stem.startswith("prepare_"):
            dataset_stem = dataset_stem[8:]
        elif dataset_stem.startswith("dag_"):
            dataset_stem = dataset_stem[4:]
        elif dataset_stem.startswith("profiled_"):
            dataset_stem = dataset_stem[9:]
        elif dataset_stem.startswith("compiled_"):
            dataset_stem = dataset_stem[9:]
            
        engineered_path = os.path.join(workspace_data_dir, f"feature_{dataset_stem}.csv")
        df.to_csv(engineered_path, index=False)

        features_added = len(df.columns) - orig_feature_count

        # ── Sprint 2: Write features_config to manifest ───────────────────
        if manifest_path and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest["features_config"] = {
                    "method": feature_method,
                    "topology_used": topology,
                    "original_feature_count": orig_feature_count,
                    "final_feature_count": int(len(df.columns)),
                    "features_added": int(max(0, features_added)),
                    "feature_names": list(df.columns),
                    "engineered_file_path": engineered_path,
                }
                manifest["pipeline_step"] = "feature_engineering"
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[FeatureEng] Warning: Could not update manifest: {e}")

        return {
            "status": "success",
            "engineered_file_path": engineered_path,
            "features_added": max(0, features_added),
            "total_features": len(df.columns),
            "feature_names": list(df.columns),
            "topology_used": topology,
            "feature_method": feature_method,
        }

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Feature Engineering error: {str(e)}")

@app.post("/api/v1/plots/feature_importance")
def get_feature_importance_plot(payload: ChartPlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        df = pd.read_csv(payload.file_path)
        target_col = payload.target_column or df.columns[-1]
        
        if target_col not in df.columns:
            target_col = df.columns[-1]
            
        numeric_cols = [c for c in df.columns if c != target_col and pd.api.types.is_numeric_dtype(df[c])]
        
        if not numeric_cols:
            return {"features": [], "importances": []}
            
        # Calculate correlation with target as proxy for importance if regression/binary
        if pd.api.types.is_numeric_dtype(df[target_col]):
            corrs = df[numeric_cols].apply(lambda c: abs(c.corr(df[target_col]))).fillna(0)
            sorted_corrs = corrs.sort_values(ascending=False).head(15)
            return {
                "features": sorted_corrs.index.tolist(),
                "importances": [round(float(v), 4) for v in sorted_corrs.values]
            }
        else:
            # Variance-based fallback
            vars_s = df[numeric_cols].var().sort_values(ascending=False).head(15)
            norm_vars = (vars_s / (vars_s.sum() + 1e-9)).fillna(0)
            return {
                "features": norm_vars.index.tolist(),
                "importances": [round(float(v), 4) for v in norm_vars.values]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/plots/pca_variance")
def get_pca_variance_plot(payload: ChartPlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        df = pd.read_csv(payload.file_path)
        target_col = payload.target_column
        numeric_cols = [c for c in df.columns if c != target_col and pd.api.types.is_numeric_dtype(df[c])]
        
        if len(numeric_cols) < 2:
            return {"components": ["PC1"], "explained_variance": [1.0], "cumulative_variance": [1.0]}
            
        n_comps = min(10, len(numeric_cols), len(df) - 1)
        pca = PCA(n_components=n_comps)
        pca.fit(df[numeric_cols].fillna(0))
        
        exp_var = [round(float(v), 4) for v in pca.explained_variance_ratio_]
        cum_var = [round(float(v), 4) for v in np.cumsum(pca.explained_variance_ratio_)]
        labels = [f"PC{i+1}" for i in range(n_comps)]
        
        return {
            "components": labels,
            "explained_variance": exp_var,
            "cumulative_variance": cum_var
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    should_reload = os.environ.get("AIC_RELOAD", "0").lower() in ("true", "1", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=should_reload)
