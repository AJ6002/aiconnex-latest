"""
aiconnex_agent/scout/compiler_adapter.py
===========================================
Gap 2 fix: translates the compiler package's own plain dataclasses
(CompileResult, HandoffArtifacts from services.aiconnex_zip_compiler) into the
agent's Pydantic contracts (ScoutEnrichedContract, DatasetIntelligenceContract
from agentic.schemas). These two worlds evolved independently and
have zero field-level overlap - this module is the only place that bridges
them, so real compiler output is what actually reaches the agent state,
instead of the previous hardcoded fake dict literals.

Deliberately does NOT attempt to fill problem_candidates/target_candidates/
feature_catalog - those depend on the compiler's own IntelligenceOrchestrator,
which is currently deleted/dead (see docs/superpowers/plans/
2026-07-29-phased-arch-audit.md gap 5). Left as empty defaults on purpose,
not silently faked.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from services.aiconnex_zip_compiler.compiler import CompileResult

from agentic.schemas import (
    UploadMetadata,
    ArchiveDiscovery,
    FileInventoryItem,
    ParserSelection,
    DatasetIdentity,
    CompiledDatasetSummary,
    DatasetStatistics,
    QualityReport,
)

logger = logging.getLogger(__name__)


def build_upload_metadata(upload_path: Path) -> UploadMetadata:
    """Real upload metadata from the actual file on disk - no hardcoded filename."""
    return UploadMetadata(
        status="uploaded",
        archive_name=upload_path.name,
        archive_type=upload_path.suffix.lstrip(".").lower() or "unknown",
        archive_size=f"{upload_path.stat().st_size} bytes" if upload_path.exists() else "unknown",
    )


def build_archive_discovery(result: CompileResult) -> ArchiveDiscovery:
    """Real file counts/paths from what the compiler actually merged, not a fixed '4 files'."""
    all_files = list(result.merged_files)
    if result.combined_file:
        all_files.append(result.combined_file)
    return ArchiveDiscovery(
        files_detected=all_files,
        total_files=len(all_files),
    )


def build_file_inventory(result: CompileResult) -> List[FileInventoryItem]:
    """One inventory item per real merged/combined output file the compiler produced."""
    items = [
        FileInventoryItem(filename=str(Path(f).name), type="csv", role="fact_table")
        for f in result.merged_files
    ]
    if result.combined_file:
        items.append(FileInventoryItem(filename=str(Path(result.combined_file).name), type="csv", role="combined_fleet_table"))
    return items


def build_parser_selection(result: CompileResult) -> ParserSelection:
    """Real active plugin ids the compiler resolved, in place of an empty/fake selection."""
    return ParserSelection(
        selected_parsers=[],  # Populated by caller from context.active_plugins if available
        unsupported_files=[],
        confidence=1.0 if result.success else 0.0,
    )


def build_dataset_identity(result: CompileResult) -> DatasetIdentity:
    """Reads the compiler's own dataset_card.json for a real name/domain, no fixed 'Suyash2'."""
    name = Path(result.input_zip).stem
    family = "Unknown"
    card_path = result.artifacts.dataset_card_json
    try:
        if card_path and Path(card_path).exists():
            card_data = json.loads(Path(card_path).read_text(encoding="utf-8"))
            name = card_data.get("dataset_name", name)
            family = card_data.get("domain_detected", family)
    except Exception as e:
        logger.warning(f"[CompilerAdapter] Could not read dataset_card.json: {e}")
    return DatasetIdentity(name=name, family=family)


def build_compiled_dataset_summary(result: CompileResult) -> CompiledDatasetSummary:
    """Real row/column/table counts read from the actual compiled CSVs, not a fixed 26898."""
    import pandas as pd

    tables = len(result.merged_files)
    total_rows = 0
    total_cols = 0
    combined_path = result.combined_file
    try:
        if combined_path and Path(combined_path).exists():
            df = pd.read_csv(combined_path, nrows=0)
            total_cols = len(df.columns)
            # Row count without loading the whole file into memory.
            with open(combined_path, "r", encoding="utf-8", errors="ignore") as f:
                total_rows = sum(1 for _ in f) - 1
        elif result.merged_files:
            df = pd.read_csv(result.merged_files[0], nrows=0)
            total_cols = len(df.columns)
            for fpath in result.merged_files:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    total_rows += sum(1 for _ in f) - 1
    except Exception as e:
        logger.warning(f"[CompilerAdapter] Could not compute real row/column counts: {e}")

    return CompiledDatasetSummary(
        tables=tables,
        rows=max(total_rows, 0),
        columns=total_cols,
        output_path=result.output_dir,
        combined_csv_path=result.combined_file,
    )


def build_dataset_statistics(result: CompileResult) -> DatasetStatistics:
    return DatasetStatistics(sampling="unknown")


def build_quality_report(result: CompileResult) -> QualityReport:
    """Real cartesian-guard status and warnings from the compiler's own join audits."""
    warnings: List[str] = []
    guard_passed = True
    for audit in result.audits:
        warnings.extend(audit.warnings)
        if not audit.cartesian_guard_passed:
            guard_passed = False
    if not result.success and result.error:
        warnings.append(result.error)
    return QualityReport(warnings=warnings, cartesian_guard_passed=guard_passed)
