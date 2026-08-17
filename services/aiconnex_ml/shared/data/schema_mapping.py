"""
schema_mapping.py — Tenant tag registry: plant sensor names → canonical names
=============================================================================
Industrial plants use proprietary sensor naming conventions (e.g., FIC_101_PV).
This module translates those site-specific tag names into canonical column names
that the ML pipeline expects (e.g., inlet_flow_rate).

Tag registry format (JSON):
{
  "FIC_101_PV": {"canonical": "inlet_flow_rate", "unit": "m3/h"},
  "TI_202_Val": {"canonical": "inlet_temperature", "unit": "degC"},
  ...
}

Usage:
  df = apply_tag_mapping(df, "config/tenants/plant_alpha/tag_mapping.json")
"""

from __future__ import annotations
import json
import os
from typing import Dict, Any, Optional
import pandas as pd


def load_tag_registry(registry_path: str) -> Dict[str, Dict[str, str]]:
    """
    Load tag registry JSON from a local path or S3 URI.
    Returns: {raw_tag: {"canonical": "name", "unit": "..."}, ...}
    """
    if registry_path.startswith("s3://"):
        from services.aiconnex_ml.shared.utils.s3 import parse_s3_uri
        import boto3
        bucket, key = parse_s3_uri(registry_path)
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    else:
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)


def apply_tag_mapping(
    df: pd.DataFrame,
    registry_path: str,
    drop_unmapped: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Rename DataFrame columns from site-specific sensor tags to canonical names.

    Args:
        df:            Input DataFrame with raw sensor tag column names.
        registry_path: Path to tag registry JSON file (local or S3).
        drop_unmapped: If True, drop columns not in the registry.
                       If False, keep unmapped columns with original names.
        verbose:       Print mapping summary.

    Returns:
        DataFrame with renamed canonical columns.
    """
    registry = load_tag_registry(registry_path)

    rename_map = {}
    unmapped = []
    for col in df.columns:
        if col in registry:
            rename_map[col] = registry[col]["canonical"]
        else:
            unmapped.append(col)

    df = df.rename(columns=rename_map)

    if verbose:
        print(f"[SchemaMapping] Mapped {len(rename_map)} columns to canonical names.")
        if unmapped:
            print(f"[SchemaMapping] Unmapped columns ({len(unmapped)}): {unmapped[:10]}")

    if drop_unmapped and unmapped:
        df = df.drop(columns=unmapped)
        print(f"[SchemaMapping] Dropped {len(unmapped)} unmapped columns.")

    return df


def run_schema_mapping(
    df: pd.DataFrame,
    manifest: Dict[str, Any],
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Pipeline-callable wrapper. Reads registry path from manifest and applies mapping.
    Skips silently if no tenant tag_registry_path is configured.

    Returns:
        df:       DataFrame with canonical column names.
        manifest: Unchanged manifest (mapping is transparent to pipeline state).
    """
    registry_path: Optional[str] = (
        manifest.get("tenant", {}).get("tag_registry_path")
        if manifest.get("tenant")
        else None
    )

    if not registry_path:
        print("[SchemaMapping] No tag registry configured. Skipping.")
        return df, manifest

    if not (registry_path.startswith("s3://") or os.path.exists(registry_path)):
        print(f"[SchemaMapping] Registry not found at '{registry_path}'. Skipping.")
        return df, manifest

    df = apply_tag_mapping(df, registry_path)
    manifest.setdefault("data_info", {})
    manifest["data_info"]["schema_mapping_applied"] = True
    manifest["data_info"]["canonical_columns"] = df.columns.tolist()
    return df, manifest
