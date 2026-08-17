"""
loader.py — Data loading from S3, local filesystem, or database
================================================================
Supports: CSV, Parquet, JSON, Excel (.xlsx), Delta (optional)
All loaders return a pandas DataFrame and update the manifest with row/col counts.
"""

from __future__ import annotations
import os
from typing import Dict, Any, Optional
import pandas as pd


def load_dataframe(path: str, **kwargs) -> pd.DataFrame:
    """
    Load a dataset from a local or S3 path.
    Auto-detects format from file extension.

    Supported: .csv, .parquet, .json, .xlsx, .xls
    """
    resolved_path = path
    if path.startswith("s3://"):
        resolved_path = _download_from_s3(path)

    ext = os.path.splitext(resolved_path)[-1].lower()

    if ext == ".csv":
        return pd.read_csv(resolved_path, **kwargs)
    elif ext == ".parquet":
        return pd.read_parquet(resolved_path, **kwargs)
    elif ext == ".json":
        return pd.read_json(resolved_path, **kwargs)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(resolved_path, **kwargs)
    else:
        raise ValueError(f"Unsupported file format: '{ext}'. "
                         f"Supported: csv, parquet, json, xlsx, xls")


def _download_from_s3(s3_uri: str) -> str:
    """Download an S3 file to a local temp location and return the local path."""
    import tempfile
    from services.aiconnex_ml.shared.utils.s3 import parse_s3_uri, download_file
    bucket, key = parse_s3_uri(s3_uri)
    filename = os.path.basename(key)
    tmp_dir = tempfile.mkdtemp(prefix="aiconnex_load_")
    local_path = os.path.join(tmp_dir, filename)
    return download_file(bucket, key, local_path)


def load_dataset(manifest: Dict[str, Any]) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Primary entry point called by the ACQUIRE node.
    Reads manifest["paths"]["raw_data"] and returns the loaded DataFrame.
    Updates manifest with shape metadata.

    Returns:
        df:       Loaded pandas DataFrame.
        manifest: Updated manifest dict with shape info.
    """
    raw_path = manifest.get("paths", {}).get("raw_data") or manifest.get("paths", {}).get("input_csv")
    if not raw_path:
        raise ValueError("manifest['paths']['raw_data'] is not set. Cannot load dataset.")

    print(f"[Loader] Loading dataset from: {raw_path}")
    df = load_dataframe(raw_path)

    print(f"[Loader] Loaded shape: {df.shape}")

    # Update manifest with shape metadata
    manifest.setdefault("data_info", {})
    manifest["data_info"]["raw_rows"] = int(df.shape[0])
    manifest["data_info"]["raw_cols"] = int(df.shape[1])
    manifest["data_info"]["column_names"] = df.columns.tolist()
    manifest["data_info"]["dtypes"] = {c: str(df[c].dtype) for c in df.columns}

    return df, manifest


def merge_dataframes(paths: list[str], strategy: str = "concat") -> pd.DataFrame:
    """
    Load and merge multiple dataset files.

    Strategies:
        'concat' — Vertical stack (same schema expected)
        'join'   — Horizontal merge on common key column (not yet implemented)
    """
    dfs = [load_dataframe(p) for p in paths]
    if strategy == "concat":
        return pd.concat(dfs, ignore_index=True)
    else:
        raise NotImplementedError(f"Merge strategy '{strategy}' is not yet implemented.")
