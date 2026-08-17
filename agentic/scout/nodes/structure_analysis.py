"""
structure_analysis_node (Task 3) — Scout stage 2 of 9.
======================================================
Parses the archive and runs UnifiedCompiler to produce the compiled CSV.
Downstream analysis nodes read the compiled CSV via the path stored here
rather than re-parsing.

Responsibilities:
  - Invoke UnifiedCompiler with the correct strategy override (if the user
    picked one at archive_discovery_node's interrupt) and CompilerRequest
    flags.
  - Retry once on transient failure (e.g. locked temp dir).
  - On persistent failure, raise a LangGraph compile_failure interrupt for
    re-upload (unchanged behaviour from the legacy scout_node).
  - Produce StructureAnalysis: compiled_csv_path, output_dir, per-table
    schema slices, combined columns/dtypes, row count, compiler warnings.

Reads:  state.upload_path, state.archive_manifest, state.cuc.planning_hints['strategy_override']
Writes: state.structure_analysis
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from langgraph.types import interrupt

from agentic.schemas import (
    InterruptPayload,
    StructureAnalysis,
    TableSchema,
)
from agentic.scout.nodes._shared import dtype_str
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


def _flag_compile_failure(error_message: str) -> str:
    payload = InterruptPayload(
        interrupt_type="compile_failure",
        questions=[
            f"I couldn't process this file: {error_message}. Could you check the file and re-upload it?"
        ],
        options=[],
        reason="structure_analysis_node compile failure after retry",
    )
    return interrupt(payload.model_dump())


def _read_table_schema(csv_path: Path) -> TableSchema:
    """Read just the header + a small slice so we can report the schema
    without loading the entire file into memory here."""
    import pandas as pd
    try:
        head_df = pd.read_csv(csv_path, low_memory=False, nrows=200)
    except Exception as exc:
        logger.warning(f"[Scout/structure_analysis] Could not read {csv_path.name}: {exc}")
        return TableSchema(filename=csv_path.name)

    columns = {col: dtype_str(head_df[col]) for col in head_df.columns}
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            row_count = sum(1 for _ in f) - 1
    except Exception:
        row_count = -1

    return TableSchema(filename=csv_path.name, columns=columns, row_count=max(row_count, 0))


def _resolve_output_dir(state: MasterAgentState) -> Path:
    return Path("scratch") / "scout_output" / state.session_id


def structure_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    """Task 3: parse+compile the archive; produce StructureAnalysis pointing at
    the compiled CSV on disk."""
    logger.info("[Scout/structure_analysis] Starting")

    if not state.upload_path:
        return {
            "structure_analysis": StructureAnalysis(
                compile_success=False,
                warnings=["structure_analysis_node reached without state.upload_path set"],
            ).model_dump(),
        }

    upload_path = Path(state.upload_path).resolve()
    output_dir = _resolve_output_dir(state)

    # Pull strategy override from CUC planning_hints (set by archive_discovery
    # when its interrupt resolved to a specific option).
    cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else dict(state.cuc)
    hints = cuc_dict.get("planning_hints") or {}
    strategy_override = hints.get("strategy_override")

    # Pull CompilerRequest flags from state.pre_compiler.
    compiler_request = state.pre_compiler.compiler_request
    enable_intelligence = compiler_request.infer_targets or compiler_request.infer_problem_candidates

    # Compile with 1 retry on transient failure
    from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
    result = None
    last_error: str | None = None
    for attempt in range(2):
        try:
            compiler = UnifiedCompiler(
                zip_path=upload_path,
                output_dir=output_dir,
                batch=True,
                strategy_override=strategy_override,
                enable_intelligence=enable_intelligence,
            )
            result = compiler.compile()
        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"[Scout/structure_analysis] Compile attempt {attempt + 1} raised: {exc}")
            continue
        if result.success:
            break
        last_error = result.error
        logger.warning(f"[Scout/structure_analysis] Compile attempt {attempt + 1} failed: {last_error}")

    if result is None or not result.success:
        user_answer = _flag_compile_failure(last_error or "unknown compilation error")
        # Store the user's re-upload response for a possible retry loop; don't
        # advance to entity_analysis without a real compiled CSV.
        cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else state.cuc.dict()
        cuc_dict["planning_hints"] = {**hints, "reupload_response": user_answer}
        return {
            "cuc": cuc_dict,
            "structure_analysis": StructureAnalysis(
                compile_success=False,
                warnings=[f"Compile failed after retry: {last_error}"],
            ).model_dump(),
            "compile_error": last_error or "Compilation failed",
            "active_agent": "scout",
        }

    # Build per-table schemas
    tables: List[TableSchema] = []
    for merged in result.merged_files:
        tables.append(_read_table_schema(Path(merged)))

    # Combined-CSV schema
    combined_columns: Dict[str, str] = {}
    combined_rows = 0
    compiled_csv_path = result.combined_file or (result.merged_files[0] if result.merged_files else None)
    if compiled_csv_path:
        ts = _read_table_schema(Path(compiled_csv_path))
        combined_columns = ts.columns
        combined_rows = ts.row_count

    # Compiler warnings from join audits
    warnings: List[str] = []
    for audit in result.audits:
        warnings.extend(audit.warnings)

    manifest = StructureAnalysis(
        compiled_csv_path=str(compiled_csv_path) if compiled_csv_path else None,
        output_dir=result.output_dir,
        tables=tables,
        combined_columns=combined_columns,
        combined_rows=combined_rows,
        warnings=warnings,
        compile_success=True,
    )
    logger.info(
        f"[Scout/structure_analysis] Compiled OK — {combined_rows} rows × "
        f"{len(combined_columns)} cols across {len(tables)} table(s)"
    )

    return {
        "structure_analysis": manifest.model_dump(),
        "active_agent": "scout",
    }
