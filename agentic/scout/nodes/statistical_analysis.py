"""
statistical_analysis_node (Task 9) — Scout stage 8 of 9.
=========================================================
Numerical shape-of-data profile:

  - Per-column summary: count, mean, std, min, max, skew, kurtosis, CoV
    (numeric columns only)
  - Pairwise Pearson correlation matrix (numeric cols, capped for perf)
  - High-correlation pair extraction (|r| >= 0.85)
  - Deterministic sampling for datasets larger than 100k rows

Reads:  state.structure_analysis, state.entity_inventory
Writes: state.statistical_profile
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agentic.schemas import (
    ColumnStats,
    CorrelationPair,
    StatisticalProfile,
)
from agentic.scout.nodes._shared import load_compiled_dataframe
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_HIGH_CORR_THRESHOLD = 0.85
_MAX_CORRELATION_COLS = 40


def _row_count(state) -> int:
    sa = state.structure_analysis
    if sa is None:
        return 0
    if hasattr(sa, "combined_rows"):
        return int(sa.combined_rows or 0)
    return int((sa or {}).get("combined_rows") or 0)


def statistical_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/statistical_analysis] Starting")

    total_rows = _row_count(state)
    sample_cap = 100_000
    df = load_compiled_dataframe(state, sample_rows=sample_cap)
    if df is None or df.empty:
        return {"statistical_profile": StatisticalProfile(total_rows=total_rows).model_dump()}

    sampled = total_rows > sample_cap
    sample_size = len(df) if sampled else 0

    import pandas as pd

    # Identify numeric columns (safest to coerce and check post-hoc so string-numeric works too)
    numeric_data: Dict[str, "pd.Series"] = {}
    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() >= 10:
            numeric_data[col] = s.dropna()

    # Per-column stats
    per_column: Dict[str, ColumnStats] = {}
    for col, s in numeric_data.items():
        try:
            mean = float(s.mean())
            std = float(s.std())
            mn = float(s.min())
            mx = float(s.max())
            skew = float(s.skew()) if len(s) > 3 else None
            kurt = float(s.kurt()) if len(s) > 3 else None
            cv = float(std / mean) if abs(mean) > 1e-9 else None
        except Exception as exc:
            logger.debug(f"[Scout/statistical_analysis] {col} stats failed: {exc}")
            continue
        per_column[col] = ColumnStats(
            mean=mean, std=std, min=mn, max=mx,
            skew=skew, kurtosis=kurt, count=int(len(s)),
            coefficient_of_variation=cv,
        )

    # Correlation matrix + high-correlation pair extraction
    high_pairs: List[CorrelationPair] = []
    if len(numeric_data) >= 2:
        cols_capped = list(numeric_data.keys())[:_MAX_CORRELATION_COLS]
        numeric_df = df[cols_capped].apply(pd.to_numeric, errors="coerce")
        try:
            corr = numeric_df.corr(method="pearson")
        except Exception as exc:
            logger.warning(f"[Scout/statistical_analysis] Correlation matrix failed: {exc}")
            corr = None
        if corr is not None:
            cols = corr.columns.tolist()
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    r = corr.iloc[i, j]
                    if r is None or r != r:  # NaN check
                        continue
                    r_val = float(r)
                    if abs(r_val) >= _HIGH_CORR_THRESHOLD:
                        high_pairs.append(CorrelationPair(
                            col_a=cols[i], col_b=cols[j], r=round(r_val, 4),
                        ))

    profile = StatisticalProfile(
        per_column=per_column,
        high_correlation_pairs=high_pairs,
        sampled=sampled,
        sample_size=sample_size,
        total_rows=total_rows or len(df),
    )
    logger.info(
        f"[Scout/statistical_analysis] {len(per_column)} numeric cols profiled, "
        f"{len(high_pairs)} high-|r| pairs (|r| >= {_HIGH_CORR_THRESHOLD}), "
        f"sampled={sampled} ({sample_size}/{total_rows} rows)"
    )
    return {
        "statistical_profile": profile.model_dump(),
        "active_agent": "scout",
    }
