"""
entity_analysis_node (Task 4) — Scout stage 3 of 9.
====================================================
Classifies each column of the compiled dataset into a role:
  - entity_id       — unique identifiers per entity (e.g. unit_id, batch_id)
  - timestamp       — datetime / time-of-observation columns
  - measurement     — high-variance numeric sensor / metric columns
  - dimension       — low-cardinality categorical columns
  - target_candidate — numeric columns with sufficient variance to model
  - metadata        — id-shaped or descriptive columns not useful as features

Uses heuristics ONLY (no LLM) — deterministic, fast, fully unit-testable.

Reads:  state.structure_analysis (for compiled_csv_path + column dtypes)
Writes: state.entity_inventory
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from agentic.schemas import EntityInventory, EntityRole
from agentic.scout.nodes._shared import load_compiled_dataframe
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_ENTITY_ID_NAME_PATTERNS = re.compile(
    r"(^|_)(id|key|uuid|guid|serial|number|batch|unit|asset|device|sensor)($|_)",
    re.IGNORECASE,
)
_TIMESTAMP_NAME_PATTERNS = re.compile(
    r"(^|_)(date|time|timestamp|dt|datetime|created_at|updated_at|cycle)($|_)",
    re.IGNORECASE,
)
_METADATA_NAME_PATTERNS = re.compile(
    r"(^|_)(index|row|name|status|type|category|label|comment|description|version)($|_)",
    re.IGNORECASE,
)
_MIN_CV_FOR_TARGET = 0.05  # coefficient of variation
_CATEGORICAL_CARDINALITY = 20


def _cv(series) -> float:
    clean = series.dropna()
    if len(clean) == 0:
        return 0.0
    try:
        mean = float(clean.mean())
    except (TypeError, ValueError):
        return 0.0
    if abs(mean) < 1e-9:
        return float(clean.std() or 0.0)
    return float((clean.std() or 0.0) / abs(mean))


def _classify(col: str, series) -> EntityRole:
    import pandas as pd

    total = len(series)
    non_null = series.notna().sum()

    # 1) Datetime (dtype-based OR parseable OR name-based)
    if pd.api.types.is_datetime64_any_dtype(series):
        return EntityRole(
            column=col, role="timestamp", confidence=0.98,
            reason="dtype is datetime64",
        )
    if _TIMESTAMP_NAME_PATTERNS.search(col):
        # Try to parse a sample; if parseable, timestamp with high confidence
        try:
            sample = series.dropna().head(30)
            pd.to_datetime(sample, errors="raise")
            return EntityRole(
                column=col, role="timestamp", confidence=0.92,
                reason=f"name matches timestamp pattern and sample parses as datetime",
            )
        except Exception:
            # Name looks temporal but data isn't parseable — treat as metadata
            return EntityRole(
                column=col, role="metadata", confidence=0.55,
                reason="name looks temporal but values do not parse as datetime",
            )

    # 2) Entity ID (high cardinality + name-matches OR uniqueness ratio very high)
    unique_ratio = (series.nunique() / total) if total else 0.0
    if _ENTITY_ID_NAME_PATTERNS.search(col) and unique_ratio > 0.5:
        return EntityRole(
            column=col, role="entity_id", confidence=0.9,
            reason=f"name matches id/key pattern and unique_ratio={unique_ratio:.2f}",
        )
    if unique_ratio > 0.95 and non_null > 10:
        return EntityRole(
            column=col, role="entity_id", confidence=0.85,
            reason=f"unique_ratio={unique_ratio:.2f} (near-unique across {non_null} non-null rows)",
        )

    # 3) Metadata (name-based)
    if _METADATA_NAME_PATTERNS.search(col):
        return EntityRole(
            column=col, role="metadata", confidence=0.75,
            reason="name matches metadata pattern",
        )

    # 4) Numeric branches: measurement vs target_candidate vs dimension
    if pd.api.types.is_numeric_dtype(series):
        nuniq = series.nunique()
        if nuniq <= _CATEGORICAL_CARDINALITY:
            return EntityRole(
                column=col, role="dimension", confidence=0.75,
                reason=f"numeric but low cardinality ({nuniq} unique values)",
            )
        cv = _cv(series)
        if cv >= _MIN_CV_FOR_TARGET:
            # High-variance numeric: BOTH a valid measurement AND a target candidate
            return EntityRole(
                column=col, role="target_candidate", confidence=min(0.99, 0.7 + cv * 0.25),
                reason=f"numeric with coefficient_of_variation={cv:.3f} (>= {_MIN_CV_FOR_TARGET})",
            )
        return EntityRole(
            column=col, role="measurement", confidence=0.6,
            reason=f"numeric but low variance (cv={cv:.3f})",
        )

    # 5) Non-numeric: dimension if low cardinality, metadata otherwise
    nuniq = series.nunique()
    if nuniq <= _CATEGORICAL_CARDINALITY:
        return EntityRole(
            column=col, role="dimension", confidence=0.7,
            reason=f"non-numeric with low cardinality ({nuniq} unique values)",
        )
    return EntityRole(
        column=col, role="metadata", confidence=0.55,
        reason=f"non-numeric with high cardinality ({nuniq} unique values)",
    )


def entity_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/entity_analysis] Starting")

    df = load_compiled_dataframe(state, sample_rows=50000)
    if df is None or df.empty:
        # Structure_analysis presumably failed. Emit an honest empty inventory.
        return {
            "entity_inventory": EntityInventory().model_dump(),
        }

    roles: List[EntityRole] = []
    for col in df.columns:
        try:
            roles.append(_classify(col, df[col]))
        except Exception as exc:
            logger.warning(f"[Scout/entity_analysis] Failed to classify {col}: {exc}")
            roles.append(EntityRole(column=col, role="unknown", confidence=0.0, reason=f"classifier error: {exc}"))

    def _cols_with_role(role: str) -> List[str]:
        return [r.column for r in roles if r.role == role]

    inv = EntityInventory(
        columns=roles,
        entity_id_columns=_cols_with_role("entity_id"),
        timestamp_columns=_cols_with_role("timestamp"),
        measurement_columns=_cols_with_role("measurement"),
        dimension_columns=_cols_with_role("dimension"),
        target_candidate_columns=_cols_with_role("target_candidate"),
        metadata_columns=_cols_with_role("metadata"),
    )
    logger.info(
        f"[Scout/entity_analysis] {len(roles)} cols classified — "
        f"targets={len(inv.target_candidate_columns)}, entities={len(inv.entity_id_columns)}, "
        f"timestamps={len(inv.timestamp_columns)}"
    )
    return {
        "entity_inventory": inv.model_dump(),
        "active_agent": "scout",
    }
