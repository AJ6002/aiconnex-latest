"""
feature_analysis_node (Task 7) — Scout stage 6 of 9.
=====================================================
Builds a per-column feature catalog and suggests derived features and
redundant pairs.

Categorises each column: raw (as-is data), derived (already engineered),
encoded (categorical needing one-hot), lagged/rolling (only added by later
stages — never appears as pre-existing raw data).

Derived-feature candidates are proposed domain-agnostically:
  - For temporal + target: lag_1, lag_7, rolling_mean_7 of the target
  - For measurement columns: rolling_mean_7, first_diff
  - For categorical dimensions: one_hot_encoding suggestion
  - For target candidates: log_transform if highly skewed

Redundant pairs = numeric columns with |correlation| >= 0.95 on the sample.

Reads:  state.structure_analysis, state.entity_inventory, state.temporal_structure
Writes: state.feature_catalog_v2
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agentic.schemas import (
    DerivedFeatureCandidate,
    FeatureCatalogV2,
    FeatureEntry,
)
from agentic.scout.nodes._shared import load_compiled_dataframe
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_REDUNDANCY_THRESHOLD = 0.95
_MAX_CORRELATION_COLUMNS = 40  # bound the correlation matrix so it stays cheap


def _describe(role: str, dtype: str) -> str:
    descriptions = {
        "entity_id": "Unique identifier for an entity",
        "timestamp": "Time-of-observation column",
        "measurement": "Numeric measurement / sensor reading",
        "target_candidate": "Numeric column suitable as a prediction target",
        "dimension": "Low-cardinality categorical dimension",
        "metadata": "Descriptive / free-form field",
    }
    return descriptions.get(role, f"{dtype} column (role unclassified)")


def _category_for(role: str) -> str:
    if role in ("target_candidate", "measurement"):
        return "raw"
    if role == "dimension":
        return "encoded"
    return "raw"


def _derived_candidates(inv, temporal, df) -> List[DerivedFeatureCandidate]:
    """Domain-agnostic feature-engineering suggestions."""
    candidates: List[DerivedFeatureCandidate] = []

    target_cols = inv.target_candidate_columns if hasattr(inv, "target_candidate_columns") else (inv or {}).get("target_candidate_columns", [])
    measurement_cols = inv.measurement_columns if hasattr(inv, "measurement_columns") else (inv or {}).get("measurement_columns", [])
    dim_cols = inv.dimension_columns if hasattr(inv, "dimension_columns") else (inv or {}).get("dimension_columns", [])

    is_ts = temporal.is_time_series if hasattr(temporal, "is_time_series") else (temporal or {}).get("is_time_series", False)

    # Temporal → lag / rolling on primary target
    if is_ts and target_cols:
        top = target_cols[0]
        candidates.append(DerivedFeatureCandidate(
            name=f"{top}_lag_1", source_columns=[top], kind="lag",
            rationale=f"Temporal structure detected — lag_1 of '{top}' captures autoregressive signal",
        ))
        candidates.append(DerivedFeatureCandidate(
            name=f"{top}_rolling_mean_7", source_columns=[top], kind="rolling_mean",
            rationale=f"7-period rolling mean of '{top}' smooths short-term noise for trend detection",
        ))

    # Measurement cols → first difference (captures rate-of-change)
    for col in measurement_cols[:5]:  # cap to keep this reasonable
        candidates.append(DerivedFeatureCandidate(
            name=f"{col}_diff_1", source_columns=[col], kind="diff",
            rationale=f"First difference of '{col}' surfaces short-term rate-of-change",
        ))

    # Categorical dimensions → one-hot encoding
    for col in dim_cols[:5]:
        candidates.append(DerivedFeatureCandidate(
            name=f"{col}_one_hot", source_columns=[col], kind="encoding",
            rationale=f"Low-cardinality categorical '{col}' benefits from one-hot encoding",
        ))

    # Highly skewed targets → log transform
    if df is not None and target_cols:
        import pandas as pd
        for col in target_cols[:3]:
            if col not in df.columns:
                continue
            try:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(s) < 20 or (s <= 0).any():
                    continue
                skew = float(s.skew())
                if abs(skew) > 1.0:
                    candidates.append(DerivedFeatureCandidate(
                        name=f"{col}_log", source_columns=[col], kind="ratio",
                        rationale=f"Target '{col}' skewness={skew:.2f} — log transform recommended",
                    ))
            except Exception:
                continue

    return candidates


def _redundant_pairs(df, numeric_cols: List[str]) -> List[List[str]]:
    if len(numeric_cols) < 2:
        return []
    import pandas as pd
    cols_capped = numeric_cols[:_MAX_CORRELATION_COLUMNS]
    numeric_df = df[cols_capped].apply(pd.to_numeric, errors="coerce")
    try:
        corr = numeric_df.corr(method="pearson").abs()
    except Exception as exc:
        logger.warning(f"[Scout/feature_analysis] Correlation failed: {exc}")
        return []
    pairs: List[List[str]] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if r is None or r != r:  # NaN check
                continue
            if float(r) >= _REDUNDANCY_THRESHOLD:
                pairs.append([cols[i], cols[j]])
    return pairs


def feature_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/feature_analysis] Starting")

    inv = state.entity_inventory
    if inv is None:
        return {"feature_catalog_v2": FeatureCatalogV2().model_dump()}

    df = load_compiled_dataframe(state, sample_rows=30000)

    # Build FeatureEntry per column from entity_inventory
    entries: List[FeatureEntry] = []
    columns_iter = inv.columns if hasattr(inv, "columns") else (inv or {}).get("columns", [])
    schema = {}
    if state.structure_analysis is not None:
        schema = getattr(state.structure_analysis, "combined_columns", None) or state.structure_analysis.get("combined_columns", {}) if hasattr(state.structure_analysis, "get") else {}
        if not schema:
            schema = state.structure_analysis.combined_columns if hasattr(state.structure_analysis, "combined_columns") else {}

    for r in columns_iter:
        col = getattr(r, "column", None) or (r or {}).get("column", "")
        role = getattr(r, "role", None) or (r or {}).get("role", "unknown")
        dtype = schema.get(col, "unknown")
        entries.append(FeatureEntry(
            column=col,
            category=_category_for(role),
            dtype=dtype,
            role="target_candidate" if role == "target_candidate" else ("entity" if role in ("entity_id",) else ("metadata" if role in ("metadata", "timestamp") else "feature")),
            description=_describe(role, dtype),
        ))

    # Derived-feature candidates
    derived = _derived_candidates(inv, state.temporal_structure or {}, df)

    # Redundant pairs (numeric only, cap for perf)
    redundant: List[List[str]] = []
    if df is not None and not df.empty:
        numeric_cols = [
            e.column for e in entries
            if e.dtype in ("integer", "float") and e.column in df.columns
        ]
        redundant = _redundant_pairs(df, numeric_cols)

    catalog = FeatureCatalogV2(
        features=entries,
        derived_candidates=derived,
        redundant_pairs=redundant,
    )
    logger.info(
        f"[Scout/feature_analysis] {len(entries)} features, "
        f"{len(derived)} derived candidates, {len(redundant)} redundant pairs"
    )
    return {
        "feature_catalog_v2": catalog.model_dump(),
        "active_agent": "scout",
    }
