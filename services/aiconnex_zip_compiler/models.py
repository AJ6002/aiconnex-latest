"""
models.py - Shared Data Models for Compiler Pipeline
=====================================================
Contains SchemaMap and JoinAudit dataclasses used across compiler.py and handoff.py.
Previously these lived in schema_mapper.py and relational_joiner.py (now deleted).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class CompilerState(str, Enum):
    """12-state compiler execution lifecycle matching Section 40 specification."""
    RECEIVED = "RECEIVED"
    INSPECTING = "INSPECTING"
    WAITING_FOR_AGENT = "WAITING_FOR_AGENT"
    PLAN_READY = "PLAN_READY"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    COMPILED = "COMPILED"
    WARNING = "WARNING"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class CompilerWorkspace:
    """Manages spec-compliant directory lifecycle for a compilation job (data/compiler/)."""

    def __init__(self, job_id: str, root: Optional[Path] = None):
        self.root = root or Path(r"x:\TAS\AICONNEX\data\compiler")
        self.job_id = job_id
        self.incoming = self.root / "incoming" / job_id
        self.quarantine = self.root / "quarantine"
        self.extracted = self.root / "extracted" / job_id
        self.intermediate = self.root / "intermediate" / job_id
        self.unified = self.root / "unified" / job_id
        self.reports = self.root / "reports" / job_id

    def setup(self) -> None:
        """Create the directory hierarchy."""
        for d in [self.incoming, self.extracted, self.intermediate, self.unified, self.reports]:
            d.mkdir(parents=True, exist_ok=True)
        self.quarantine.mkdir(parents=True, exist_ok=True)

    def quarantine_file(self, filepath: Path, reason: str) -> Path:
        """Quarantine a corrupted/malformed file and persist audit metadata."""
        dest = self.quarantine / f"{self.job_id}_{filepath.name}"
        try:
            shutil.copy2(filepath, dest)
            sha256 = hashlib.sha256(filepath.read_bytes()).hexdigest()
        except Exception:
            sha256 = "unknown"
            dest.touch()

        meta = {
            "job_id": self.job_id,
            "original_path": str(filepath),
            "reason": reason,
            "sha256": sha256,
            "status": "QUARANTINED"
        }
        meta_file = self.quarantine / f"{dest.name}.meta.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return dest


@dataclass
class SchemaMap:
    """Bi-directional column name mapping and timestamp format metadata."""
    raw_to_canonical: Dict[str, str] = field(default_factory=dict)
    canonical_to_raw: Dict[str, str] = field(default_factory=dict)
    detected_timestamp_formats: Dict[str, str] = field(default_factory=dict)
    canonical_timestamp_col: Optional[str] = None
    canonical_group_col: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_to_canonical": self.raw_to_canonical,
            "canonical_to_raw": self.canonical_to_raw,
            "detected_timestamp_formats": self.detected_timestamp_formats,
            "canonical_timestamp_col": self.canonical_timestamp_col,
            "canonical_group_col": self.canonical_group_col,
            "warnings": self.warnings,
        }


@dataclass
class JoinAudit:
    """Audit record for a single table join operation."""
    group_id: str
    fact_file: str
    dimension_files: List[str]
    join_keys: List[str]
    join_type: str
    fact_rows_before: int
    merged_rows_after: int
    null_column_percentages: Dict[str, float]
    cartesian_guard_passed: bool
    warnings: List[str] = field(default_factory=list)
    redundant_keys_excluded: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "fact_file": self.fact_file,
            "dimension_files": self.dimension_files,
            "join_keys": self.join_keys,
            "join_type": self.join_type,
            "fact_rows_before": self.fact_rows_before,
            "merged_rows_after": self.merged_rows_after,
            "null_column_percentages": self.null_column_percentages,
            "cartesian_guard_passed": self.cartesian_guard_passed,
            "warnings": self.warnings,
            "redundant_keys_excluded": self.redundant_keys_excluded,
        }


def create_compiler_temp_dir(prefix: str = "aic_compiler_") -> Path:
    """Create a temporary working directory for the compiler, preferring workspace drive (X: drive) if available."""
    import os
    import tempfile
    from pathlib import Path

    ws_temp = Path(r"x:\TAS\AICONNEX\scratch\temp")
    try:
        ws_temp.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=ws_temp))
    except Exception:
        pass

    return Path(tempfile.mkdtemp(prefix=prefix))
