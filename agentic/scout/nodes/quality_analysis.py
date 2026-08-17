"""
quality_analysis_node (Task 8) — Scout stage 7 of 9.
=====================================================
Deep data-quality assessment. Extends what the legacy DICValidator did
(structural completeness) with real row-level checks:

  - Per-column null percentages
  - Duplicate row count (exact-match rows)
  - Constant-column detection
  - IQR-based outlier detection per numeric column
  - Class-imbalance detection for target candidates that are discrete

Each issue is a typed QualityIssue with severity: info / warning / error.
`passed = False` iff at least one error-severity issue was recorded.

Reads:  state.structure_analysis, state.entity_inventory
Writes: state.quality_assessment
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agentic.schemas import QualityAssessment, QualityIssue
from agentic.scout.nodes._shared import load_compiled_dataframe
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_NULL_WARNING_PCT = 0.20  # warn if a column is > 20% null
_NULL_ERROR_PCT = 0.80    # error if a column is > 80% null
_IMBALANCE_RATIO = 0.9    # error if a single class exceeds 90% of a discrete target


def _iqr_outlier_count(series) -> int:
    import pandas as pd
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 10:
        return 0
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return 0
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((s < lo) | (s > hi)).sum())


def quality_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/quality_analysis] Starting")

    df = load_compiled_dataframe(state, sample_rows=50000)
    if df is None or df.empty:
        return {"quality_assessment": QualityAssessment(passed=False, issues=[
            QualityIssue(kind="null", severity="error", detail="No compiled dataset available to assess")
        ]).model_dump()}

    inv = state.entity_inventory
    target_cols = []
    if inv is not None:
        target_cols = inv.target_candidate_columns if hasattr(inv, "target_candidate_columns") else (inv or {}).get("target_candidate_columns", [])

    issues: List[QualityIssue] = []
    null_pct: Dict[str, float] = {}
    outliers: Dict[str, int] = {}
    constants: List[str] = []
    imbalance_notes: List[str] = []
    total_rows = len(df)

    # --- Nulls
    for col in df.columns:
        n = int(df[col].isna().sum())
        pct = n / max(total_rows, 1)
        null_pct[col] = round(pct, 4)
        if pct >= _NULL_ERROR_PCT:
            issues.append(QualityIssue(kind="null", column=col, severity="error",
                                       detail=f"{pct:.0%} null values in '{col}' — column may be unusable"))
        elif pct >= _NULL_WARNING_PCT:
            issues.append(QualityIssue(kind="null", column=col, severity="warning",
                                       detail=f"{pct:.0%} null values in '{col}'"))

    # --- Duplicate rows
    try:
        dup_count = int(df.duplicated().sum())
    except Exception:
        dup_count = 0
    if dup_count > 0:
        severity = "warning" if dup_count / max(total_rows, 1) < 0.1 else "error"
        issues.append(QualityIssue(
            kind="duplicate", severity=severity,
            detail=f"{dup_count} duplicate row(s) detected ({dup_count / total_rows:.1%} of dataset)",
        ))

    # --- Constant columns
    for col in df.columns:
        try:
            nuniq = int(df[col].nunique(dropna=True))
        except Exception:
            nuniq = 0
        if nuniq <= 1 and total_rows > 5:
            constants.append(col)
            issues.append(QualityIssue(
                kind="constant", column=col, severity="warning",
                detail=f"Column '{col}' has {nuniq} unique value(s) — no information for modelling",
            ))

    # --- Outliers per numeric column (bounded)
    for col in df.columns:
        try:
            n_out = _iqr_outlier_count(df[col])
        except Exception:
            n_out = 0
        if n_out > 0:
            outliers[col] = n_out
            if n_out / max(total_rows, 1) > 0.05:
                issues.append(QualityIssue(
                    kind="outlier", column=col, severity="warning",
                    detail=f"{n_out} IQR outliers in '{col}' ({n_out / total_rows:.1%})",
                ))

    # --- Imbalance for discrete-target candidates
    for col in target_cols:
        if col not in df.columns:
            continue
        try:
            counts = df[col].value_counts(dropna=True, normalize=True)
        except Exception:
            continue
        if not len(counts):
            continue
        top_share = float(counts.iloc[0])
        if top_share >= _IMBALANCE_RATIO and len(counts) <= 20:
            imbalance_notes.append(
                f"'{col}': dominant value has {top_share:.0%} share across {len(counts)} classes"
            )
            issues.append(QualityIssue(
                kind="imbalance", column=col, severity="error",
                detail=f"Target candidate '{col}' is heavily imbalanced (dominant class = {top_share:.0%})",
            ))

    passed = not any(i.severity == "error" for i in issues)

    assessment = QualityAssessment(
        issues=issues,
        null_percentages=null_pct,
        duplicate_row_count=dup_count,
        constant_columns=constants,
        outlier_summary=outliers,
        imbalance_notes=imbalance_notes,
        passed=passed,
    )
    logger.info(
        f"[Scout/quality_analysis] passed={passed} — "
        f"{len(issues)} issue(s), {dup_count} dupes, {len(constants)} constants, "
        f"{sum(1 for pct in null_pct.values() if pct >= _NULL_WARNING_PCT)} high-null cols"
    )
    return {
        "quality_assessment": assessment.model_dump(),
        "active_agent": "scout",
    }
