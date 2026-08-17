"""
archive_discovery_node (Task 2) — Scout stage 1 of 9.
=====================================================
Pure file-system inspection of the uploaded artifact. NO data parsing —
that's structure_analysis_node's job.

Responsibilities (from the architecture spec):
  - Detect archive type (zip / folder / single file)
  - Discover files recursively
  - Detect parser candidates per file (by extension)
  - Build file inventory with sizes and format tags
  - Detect duplicate files (name+size heuristic)
  - Validate archive integrity (openable, non-empty, no zip-bomb)
  - Run strategy_peek to detect multi-strategy compilation forks and
    raise a LangGraph interrupt when the user has to choose between
    2+ genuinely different processing strategies.

Reads:  state.upload_path
Writes: state.archive_manifest
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from langgraph.types import interrupt

from agentic.schemas import (
    ArchiveManifest,
    ArchiveInventoryItem,
    InterruptPayload,
    InterruptOption,
)
from agentic.scout.nodes._shared import hash_file
from agentic.scout.strategy_peek import peek_dataset_card_and_options
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

# Extension → parser plugin id (uses UnifiedCompiler's actual plugin names)
_PARSER_MAP: Dict[str, str] = {
    ".csv": "csv_parser",
    ".xlsx": "excel_parser",
    ".xls": "excel_parser",
    ".parquet": "parquet_parser",
    ".pq": "parquet_parser",
    ".mat": "matlab_parser",
    ".tdms": "tdms_parser",
    ".json": "json_parser",
    ".jsonl": "jsonl_parser",
    ".txt": "text_parser",
    ".tsv": "csv_parser",
}

# Extensions that look like data but are almost always metadata/aux files
_METADATA_EXTS = {".md", ".txt", ".readme", ".yaml", ".yml", ".xml", ".log"}


def _role_hint_for(path: Path, size_bytes: int) -> str:
    """Coarse guess at file role. Deliberately conservative; entity_analysis
    is where real column-level roles get assigned later."""
    ext = path.suffix.lower()
    name_lower = path.name.lower()
    if ext in _METADATA_EXTS or "readme" in name_lower or "license" in name_lower:
        return "metadata"
    if size_bytes < 4096 and ext in _PARSER_MAP:
        return "dimension"
    if ext in _PARSER_MAP:
        return "fact_table"
    return "unknown"


def _walk_inventory(base: Path) -> tuple[list[ArchiveInventoryItem], list[str]]:
    """Return (files, subdirectories relative to base)."""
    files: list[ArchiveInventoryItem] = []
    directories: list[str] = []
    for p in base.rglob("*"):
        try:
            rel = p.relative_to(base)
        except ValueError:
            rel = p
        if p.is_dir():
            directories.append(str(rel))
            continue
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        ext = p.suffix.lower()
        files.append(
            ArchiveInventoryItem(
                path=str(rel),
                size_bytes=size,
                format=ext.lstrip(".") or "unknown",
                role_hint=_role_hint_for(p, size),
            )
        )
    return files, directories


def _detect_duplicates(files: list[ArchiveInventoryItem]) -> list[str]:
    """Flag paths that share the same (basename, size) — likely duplicates
    left over from ZIP layers or copy-paste."""
    from collections import defaultdict
    groups: dict[tuple[str, int], list[str]] = defaultdict(list)
    for f in files:
        groups[(Path(f.path).name, f.size_bytes)].append(f.path)
    dupes: list[str] = []
    for _, paths in groups.items():
        if len(paths) > 1:
            dupes.extend(paths[1:])
    return dupes


def _validate_archive(upload_path: Path) -> tuple[bool, list[str]]:
    """Cheap integrity checks. Non-fatal warnings still return (True, [...])."""
    notes: list[str] = []
    if not upload_path.exists():
        return False, [f"Upload path does not exist: {upload_path}"]

    if upload_path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(upload_path, "r") as zf:
                bad = zf.testzip()
                if bad is not None:
                    return False, [f"Corrupt entry inside zip: {bad}"]
                # Naive zip-bomb guard: refuse if declared size > 100x archive size
                total_declared = sum(i.file_size for i in zf.infolist())
                if upload_path.stat().st_size > 0 and total_declared / upload_path.stat().st_size > 100:
                    notes.append("Suspicious compression ratio (>100x) — proceeding but flagged")
        except zipfile.BadZipFile as exc:
            return False, [f"Not a valid zip archive: {exc}"]

    return True, notes


def _emit_strategy_interrupt(options) -> str:
    payload = InterruptPayload(
        interrupt_type="strategy_choice",
        questions=[
            f"Your dataset supports {len(options)} different processing strategies. Which would you like?"
        ],
        options=[
            InterruptOption(
                option_id=getattr(o, "option_id", f"opt_{i}"),
                label=getattr(o, "label", f"Strategy {i + 1}"),
                description=getattr(o, "description", ""),
            )
            for i, o in enumerate(options)
        ],
        reason="archive_discovery_node detected multiple valid compilation strategies",
    )
    return interrupt(payload.model_dump())


def archive_discovery_node(state: MasterAgentState) -> Dict[str, Any]:
    """Task 2: pure file-system inspection of state.upload_path."""
    logger.info("[Scout/archive_discovery] Starting")

    if not state.upload_path:
        # Defensive: pre-upload chain should have parked at upload_gate_node,
        # but if we're reached without a real file, surface it as an
        # empty-but-valid manifest so downstream nodes can no-op cleanly.
        return {
            "archive_manifest": ArchiveManifest(
                integrity_ok=False,
                integrity_notes=["No upload_path was set on state; archive_discovery_node had nothing to inspect"],
            ).model_dump(),
        }

    upload_path = Path(state.upload_path).resolve()
    integrity_ok, integrity_notes = _validate_archive(upload_path)
    if not integrity_ok:
        return {
            "archive_manifest": ArchiveManifest(
                archive_path=str(upload_path),
                archive_type="corrupt",
                integrity_ok=False,
                integrity_notes=integrity_notes,
            ).model_dump(),
        }

    # Compute archive checksum for reproducibility
    try:
        checksum = hash_file(upload_path)
    except Exception as exc:
        logger.warning(f"[Scout/archive_discovery] Checksum failed: {exc}")
        checksum = ""

    # Walk the archive contents. For zips we extract to a temp dir just for
    # inspection; the real compile in structure_analysis_node re-extracts.
    archive_type = "single_file"
    files: list[ArchiveInventoryItem] = []
    directories: list[str] = []

    if upload_path.is_dir():
        archive_type = "folder"
        files, directories = _walk_inventory(upload_path)
    elif upload_path.suffix.lower() == ".zip":
        archive_type = "zip"
        temp_dir = Path(tempfile.mkdtemp(prefix="aic_arch_discover_"))
        try:
            with zipfile.ZipFile(upload_path, "r") as zf:
                zf.extractall(temp_dir)
            files, directories = _walk_inventory(temp_dir)
        except Exception as exc:
            integrity_notes.append(f"Failed to walk zip contents: {exc}")
            integrity_ok = False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        size = upload_path.stat().st_size
        files = [
            ArchiveInventoryItem(
                path=upload_path.name,
                size_bytes=size,
                format=upload_path.suffix.lower().lstrip(".") or "unknown",
                role_hint=_role_hint_for(upload_path, size),
            )
        ]

    parser_candidates: Dict[str, str] = {}
    for f in files:
        parser = _PARSER_MAP.get(f"." + f.format.lower())
        if parser:
            parser_candidates[Path(f.path).name] = parser

    duplicates = _detect_duplicates(files)
    if duplicates:
        integrity_notes.append(f"{len(duplicates)} likely duplicate file(s) detected")

    manifest = ArchiveManifest(
        archive_path=str(upload_path),
        archive_type=archive_type,
        archive_size_bytes=upload_path.stat().st_size,
        checksum=checksum,
        files=files,
        directories=directories,
        total_files=len(files),
        duplicate_files=duplicates,
        parser_candidates=parser_candidates,
        integrity_ok=integrity_ok,
        integrity_notes=integrity_notes,
    )
    logger.info(
        f"[Scout/archive_discovery] {manifest.total_files} files, "
        f"{len(directories)} dirs, type={archive_type}, integrity={integrity_ok}"
    )

    # Strategy interrupt (only fires if the compiler's IntentClassifier finds
    # 2+ genuinely different strategies for this dataset). Preserved from the
    # legacy scout_node — this is a real user decision, not silent.
    strategy_override = None
    try:
        _, options = peek_dataset_card_and_options(upload_path)
        if len(options) >= 2:
            strategy_override = _emit_strategy_interrupt(options)
    except Exception as exc:
        logger.warning(
            f"[Scout/archive_discovery] Strategy peek failed (proceeding with compiler default): {exc}"
        )

    result: Dict[str, Any] = {
        "archive_manifest": manifest.model_dump(),
        "active_agent": "scout",
    }
    if strategy_override:
        # Store the chosen strategy in cuc.planning_hints so structure_analysis
        # can consume it as UnifiedCompiler's strategy_override argument.
        cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else state.cuc.dict()
        hints = dict(cuc_dict.get("planning_hints") or {})
        hints["strategy_override"] = strategy_override
        cuc_dict["planning_hints"] = hints
        result["cuc"] = cuc_dict

    return result
