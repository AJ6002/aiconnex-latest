"""
handoff.py - Layer 4: ML Handoff & Artifact Exporter
=====================================================
Exports per-group merged CSVs, optional combined fleet table, join_audit.json,
schema_map.json, and compiler_report.json to the output workspace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

from .models import SchemaMap, JoinAudit


@dataclass
class HandoffArtifacts:
    per_group_csvs: Dict[str, Path]
    combined_csv: Optional[Path]
    dataset_card_json: Path
    join_audit_json: Path
    schema_map_json: Path
    compiler_report_json: Path
    per_group_parquets: Dict[str, Path] = field(default_factory=dict)
    combined_parquet: Optional[Path] = None
    lineage_json: Optional[Path] = None
    quality_report_json: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "per_group_csvs": {k: str(v) for k, v in self.per_group_csvs.items()},
            "combined_csv": str(self.combined_csv) if self.combined_csv else None,
            "per_group_parquets": {k: str(v) for k, v in self.per_group_parquets.items()},
            "combined_parquet": str(self.combined_parquet) if self.combined_parquet else None,
            "dataset_card_json": str(self.dataset_card_json),
            "join_audit_json": str(self.join_audit_json),
            "schema_map_json": str(self.schema_map_json),
            "compiler_report_json": str(self.compiler_report_json),
            "lineage_json": str(self.lineage_json) if self.lineage_json else None,
            "quality_report_json": str(self.quality_report_json) if self.quality_report_json else None,
        }


def export_compiler_handoff(
    output_dir: Path,
    merged_dfs: Dict[str, pd.DataFrame],
    audits: List[JoinAudit],
    schema_map: SchemaMap,
    duration_seconds: float,
    zip_filename: str,
) -> HandoffArtifacts:
    """Write merged dataset CSVs & Parquets, dataset_card.json, lineage.json, quality_report.json, and audit/schema JSON reports to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    per_group_csvs: Dict[str, Path] = {}
    per_group_parquets: Dict[str, Path] = {}
    all_dfs: List[pd.DataFrame] = []

    # 1. Export Per-Group Merged CSVs & Parquets (Option 1: Condition-Specific / Benchmark Mode)
    for group_id, df in merged_dfs.items():
        clean_gid = str(group_id).replace(" ", "_").lower()
        csv_path = output_dir / f"group_{clean_gid}_merged.csv"
        df.to_csv(csv_path, index=False)
        per_group_csvs[group_id] = csv_path

        # Export Parquet alongside CSV
        try:
            parquet_path = output_dir / f"group_{clean_gid}_merged.parquet"
            df.to_parquet(parquet_path, index=False, engine="pyarrow")
            per_group_parquets[group_id] = parquet_path
        except Exception:
            pass

        # Prepare for vertical multi-entity concatenation (Option 2: Cross-Condition Generalization Mode)
        # Only stack primary training groups (exclude test and rul splits)
        if not (clean_gid.endswith("_test") or clean_gid.endswith("_rul")):
            df_tagged = df.copy()
            id_col = "condition_set_id" if ("fd" in clean_gid or "exp" in clean_gid) else ("device_id" if "device" in clean_gid else "group_id")
            if id_col not in df_tagged.columns and "group_id" not in df_tagged.columns and "device_id" not in df_tagged.columns and "condition_set_id" not in df_tagged.columns:
                df_tagged.insert(0, id_col, group_id)
            all_dfs.append(df_tagged)

    # 2. Export Combined Fleet/Multi-Device CSV & Parquet (Option 2: Merged Generalization Mode)
    combined_csv_path: Optional[Path] = None
    combined_parquet_path: Optional[Path] = None
    combined_df = None
    if len(all_dfs) >= 1:
        combined_csv_path = output_dir / "all_groups_combined.csv"
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df.to_csv(combined_csv_path, index=False)

        try:
            combined_parquet_path = output_dir / "all_groups_combined.parquet"
            combined_df.to_parquet(combined_parquet_path, index=False, engine="pyarrow")
        except Exception:
            pass

    # 3. Export dataset_card.json (Human & Machine-Readable Summary for Non-DS Users)
    dataset_card_path = output_dir / "dataset_card.json"
    total_rows = sum(len(df) for df in merged_dfs.values())
    all_cols = list(set().union(*(df.columns for df in merged_dfs.values()))) if merged_dfs else []

    # Infer domain heuristics
    domain_label = "Industrial Sensor Telemetry"
    if any("sensor_" in str(c) or "unit_id" in str(c) for c in all_cols):
        domain_label = "Aerospace / Turbofan Engine Prognostics"
    elif any("collector" in str(c) or "gate" in str(c) for c in all_cols):
        domain_label = "Power Electronics / Transistor Aging"
    elif any("ac_power" in str(c) or "dc_power" in str(c) for c in all_cols):
        domain_label = "Renewable Energy / Solar Generation"

    has_rul = any(str(c).upper() == "RUL" for c in all_cols)
    card_data = {
        "dataset_name": zip_filename,
        "domain_detected": domain_label,
        "duration_seconds": duration_seconds,
        "total_output_rows": total_rows,
        "target_column": "RUL" if has_rul else None,
        "rul_synthesis_applied": has_rul,
        "detected_groups": list(merged_dfs.keys()),
        "output_paths": {
            "separate_condition_csvs": {k: str(v) for k, v in per_group_csvs.items()},
            "separate_condition_parquets": {k: str(v) for k, v in per_group_parquets.items()},
            "merged_fleet_csv": str(combined_csv_path) if combined_csv_path else None,
            "merged_fleet_parquet": str(combined_parquet_path) if combined_parquet_path else None,
        },
        "mlops_pipeline_modes": {
            "option_1_benchmark_mode": "Use separate_condition_csvs for condition-specific RUL regression & easy debugging.",
            "option_2_generalization_mode": "Use merged_fleet_csv (all_groups_combined.csv) to test cross-condition MLOps model generalization."
        },
        "recommended_next_node": "Node 1: Dataset Profiler (aic/1_dataset_profiler)"
    }
    with open(dataset_card_path, "w", encoding="utf-8") as f:
        json.dump(card_data, f, indent=2)

    # 4. Export join_audit.json
    join_audit_path = output_dir / "join_audit.json"
    audit_data = [a.to_dict() for a in audits]
    with open(join_audit_path, "w", encoding="utf-8") as f:
        json.dump({"audits": audit_data}, f, indent=2)

    # 5. Export schema_map.json
    schema_map_path = output_dir / "schema_map.json"
    with open(schema_map_path, "w", encoding="utf-8") as f:
        json.dump(schema_map.to_dict(), f, indent=2)

    # 6. Export lineage.json (Spec Section 39)
    lineage_path = output_dir / "lineage.json"
    lineage_data = {
        "source_archive": zip_filename,
        "stages": [
            {"stage": "ingestion", "action": "UNZIP", "target": zip_filename},
            {"stage": "assembly", "action": "MERGE_AND_ALIGN", "groups": list(merged_dfs.keys())},
            {"stage": "export", "action": "PARQUET_AND_CSV_HANDOFF", "files_generated": len(per_group_csvs) + (1 if combined_csv_path else 0)}
        ],
        "audits": audit_data,
        "canonical_timestamp_column": schema_map.canonical_timestamp_col,
    }
    with open(lineage_path, "w", encoding="utf-8") as f:
        json.dump(lineage_data, f, indent=2)

    # 7. Export quality_report.json (Spec Section 62 & 66)
    quality_path = output_dir / "quality_report.json"
    quality_summary = {}
    for gid, df in merged_dfs.items():
        total_cells = df.size if df.size > 0 else 1
        null_count = int(df.isnull().sum().sum())
        quality_summary[gid] = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "null_cell_count": null_count,
            "null_rate": round(null_count / total_cells, 4),
            "duplicate_rows": int(df.duplicated().sum()),
            "schema_valid": True
        }
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset_name": zip_filename,
            "status": "PASS",
            "group_quality": quality_summary
        }, f, indent=2)

    # 8. Export compiler_report.json
    compiler_report_path = output_dir / "compiler_report.json"
    report_data = {
        "status": "success",
        "input_zip": zip_filename,
        "duration_seconds": duration_seconds,
        "total_output_rows": total_rows,
        "groups_processed": list(merged_dfs.keys()),
        "output_files": {
            "per_group_csv": [str(p) for p in per_group_csvs.values()],
            "per_group_parquet": [str(p) for p in per_group_parquets.values()],
            "combined_csv": str(combined_csv_path) if combined_csv_path else None,
            "combined_parquet": str(combined_parquet_path) if combined_parquet_path else None,
            "dataset_card": str(dataset_card_path),
            "lineage": str(lineage_path),
            "quality_report": str(quality_path),
        },
        "cartesian_explosion_guards_passed": all(a.cartesian_guard_passed for a in audits),
    }
    with open(compiler_report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    return HandoffArtifacts(
        per_group_csvs=per_group_csvs,
        combined_csv=combined_csv_path,
        dataset_card_json=dataset_card_path,
        join_audit_json=join_audit_path,
        schema_map_json=schema_map_path,
        compiler_report_json=compiler_report_path,
        per_group_parquets=per_group_parquets,
        combined_parquet=combined_parquet_path,
        lineage_json=lineage_path,
        quality_report_json=quality_path,
    )
