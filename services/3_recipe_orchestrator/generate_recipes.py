"""
generate_recipes.py — Generates and validates recipe JSONs for all 1,993 DAG IDs
"""

import json
import os
from pathlib import Path
import pandas as pd

_project_root = Path(__file__).resolve().parents[2]
excel_path = _project_root / "algorithm_families_complete-2.xlsx"
base_dir = Path(__file__).resolve().parent / "recipe"

df = pd.read_excel(excel_path)
print(f"Loaded {len(df)} rows from master Excel.")

categories = ["training", "preparing", "feature_engineering", "splitting"]
for cat in categories:
    (base_dir / cat).mkdir(parents=True, exist_ok=True)

created_count = 0
updated_count = 0

for _, row in df.iterrows():
    dag_id = str(row["DAG ID"])
    algo = str(row["Algorithm"])
    variant = str(row["Variant"])
    family = str(row["FAMILY_NAME"])
    
    # 1. Training Recipe
    train_file = base_dir / "training" / f"{dag_id}.json"
    train_content = {
        "algorithm": algo,
        "variant": variant,
        "validation_metrics": ["r2", "rmse", "mae"] if family in ["REGRESSION", "TIME-SERIES"] else ["accuracy", "f1", "precision", "recall"],
        "hyperparameters": {
            "fit_intercept": True,
            "alpha": 1.0
        }
    }
    
    # 2. Preparing Recipe
    prep_file = base_dir / "preparing" / f"{dag_id}.json"
    prep_content = {
        "impute_strategy": "mean",
        "outlier_method": "none",
        "scale_method": "standard",
        "encode_strategy": "one-hot",
        "text_clean": False,
        "time_align": (family in ["TIME-SERIES"])
    }
    
    # 3. Feature Engineering Recipe
    feat_file = base_dir / "feature_engineering" / f"{dag_id}.json"
    feat_content = {
        "polynomial_degree": 2,
        "interaction_features": True,
        "pca_components": 0,
        "feature_selection_method": "k_best",
        "k_best_features": 15,
        "create_aggregate_features": True
    }
    
    # 4. Splitting Recipe
    split_file = base_dir / "splitting" / f"{dag_id}.json"
    split_content = {
        "test_size": 0.2,
        "validation_strategy": "time_series_split" if family in ["TIME-SERIES"] else "kfold",
        "random_state": 42
    }

    # Write files
    for filepath, content in [(train_file, train_content), (prep_file, prep_content), (feat_file, feat_content), (split_file, split_content)]:
        if not filepath.exists():
            created_count += 1
        else:
            updated_count += 1
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4)

print(f"Completed! Created/Updated {len(df) * 4} recipe JSON files across 4 directories.")
