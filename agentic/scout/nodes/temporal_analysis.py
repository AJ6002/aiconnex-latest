"""
temporal_analysis_node (Task 6) — Scout stage 5 of 9.
======================================================
Detects time-series structure. For tabular datasets with no timestamp
columns, cleanly outputs is_time_series=False without error.

Analysis:
  - Primary timestamp column selection (first from entity_inventory)
  - Sampling frequency detection (daily / hourly / per-cycle / monthly / irregular)
  - Gap detection (missing intervals between consecutive timestamps)
  - Monotonicity check
  - Date range
  - Coarse seasonality hints via autocorrelation at weekly / monthly lags

Reads:  state.structure_analysis, state.entity_inventory
Writes: state.temporal_structure
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agentic.schemas import TemporalStructure
from agentic.scout.nodes._shared import load_compiled_dataframe
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


def _detect_frequency(sorted_ts) -> tuple[str | None, float]:
    """Given a sorted, non-null datetime Series, return (frequency_label, confidence)."""
    import pandas as pd

    if len(sorted_ts) < 3:
        return None, 0.0

    deltas = sorted_ts.diff().dropna()
    if deltas.empty:
        return None, 0.0

    median_seconds = deltas.dt.total_seconds().median()
    if median_seconds is None or median_seconds <= 0:
        return None, 0.0

    # Consistency: what fraction of deltas are within 20% of the median?
    within = ((deltas.dt.total_seconds() - median_seconds).abs() <= 0.2 * median_seconds).mean()
    confidence = float(within)

    # Map median delta to a coarse label
    if median_seconds < 60:
        label = "sub_minute"
    elif median_seconds < 60 * 60:
        label = "minute"
    elif median_seconds < 60 * 60 * 24 * 0.9:
        label = "hourly"
    elif median_seconds < 60 * 60 * 24 * 1.5:
        label = "daily"
    elif median_seconds < 60 * 60 * 24 * 9:
        label = "weekly"
    elif median_seconds < 60 * 60 * 24 * 45:
        label = "monthly"
    else:
        label = "sparse"

    if confidence < 0.5:
        return "irregular", confidence
    return label, confidence


def _seasonality_hints(daily_series, is_daily: bool) -> List[str]:
    """Cheap seasonality hints via lag-N autocorrelation. Only meaningful for
    dense daily data; returns [] otherwise."""
    hints: List[str] = []
    if not is_daily or len(daily_series) < 40:
        return hints
    try:
        for lag, name in [(7, "weekly"), (30, "monthly")]:
            if len(daily_series) <= lag:
                continue
            ac = daily_series.autocorr(lag=lag)
            if ac is not None and ac > 0.3:
                hints.append(name)
    except Exception:
        pass
    return hints


def temporal_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/temporal_analysis] Starting")

    if state.entity_inventory is None:
        return {"temporal_structure": TemporalStructure().model_dump()}

    inv = state.entity_inventory
    ts_cols = inv.timestamp_columns if hasattr(inv, "timestamp_columns") else (inv or {}).get("timestamp_columns", [])
    if not ts_cols:
        logger.info("[Scout/temporal_analysis] No timestamp columns — tabular dataset")
        return {"temporal_structure": TemporalStructure(is_time_series=False).model_dump()}

    df = load_compiled_dataframe(state, sample_rows=100000)
    if df is None or df.empty:
        return {"temporal_structure": TemporalStructure(is_time_series=False).model_dump()}

    import pandas as pd

    primary = ts_cols[0]
    try:
        parsed = pd.to_datetime(df[primary], errors="coerce")
    except Exception as exc:
        logger.warning(f"[Scout/temporal_analysis] Could not parse {primary!r} as datetime: {exc}")
        return {
            "temporal_structure": TemporalStructure(
                is_time_series=False,
                timestamp_columns=ts_cols,
                seasonality_hints=[f"failed_to_parse: {primary}"],
            ).model_dump()
        }

    parsed_non_null = parsed.dropna()
    if parsed_non_null.empty:
        return {
            "temporal_structure": TemporalStructure(
                is_time_series=False,
                timestamp_columns=ts_cols,
                primary_timestamp=primary,
            ).model_dump()
        }

    sorted_ts = parsed_non_null.sort_values().reset_index(drop=True)
    monotonic = bool((parsed_non_null.diff().dropna() >= pd.Timedelta(0)).all())

    freq, freq_conf = _detect_frequency(sorted_ts)
    has_gaps = False
    if freq and freq not in ("irregular", "sparse"):
        # Gap = any delta > 2x the median (rough heuristic)
        median_seconds = sorted_ts.diff().dropna().dt.total_seconds().median()
        if median_seconds:
            has_gaps = bool((sorted_ts.diff().dt.total_seconds() > median_seconds * 2).any())

    date_range = None
    try:
        date_range = f"{sorted_ts.min().strftime('%Y-%m-%d')} - {sorted_ts.max().strftime('%Y-%m-%d')}"
    except Exception:
        pass

    # Seasonality hints on the first target-candidate column if we have one
    target_cols = inv.target_candidate_columns if hasattr(inv, "target_candidate_columns") else (inv or {}).get("target_candidate_columns", [])
    hints: List[str] = []
    if freq == "daily" and target_cols:
        try:
            df_time = df.assign(_ts=parsed).dropna(subset=["_ts", target_cols[0]])
            df_time = df_time.sort_values("_ts").reset_index(drop=True)
            hints = _seasonality_hints(df_time[target_cols[0]], is_daily=True)
        except Exception as exc:
            logger.debug(f"[Scout/temporal_analysis] Seasonality hint calc failed: {exc}")

    ts = TemporalStructure(
        is_time_series=True,
        timestamp_columns=ts_cols,
        primary_timestamp=primary,
        detected_frequency=freq,
        frequency_confidence=round(freq_conf, 3),
        has_gaps=has_gaps,
        monotonic=monotonic,
        date_range=date_range,
        seasonality_hints=hints,
    )
    logger.info(
        f"[Scout/temporal_analysis] is_time_series=True, primary={primary}, "
        f"freq={freq} (conf={freq_conf:.2f}), gaps={has_gaps}, monotonic={monotonic}, "
        f"seasonality={hints}"
    )
    return {
        "temporal_structure": ts.model_dump(),
        "active_agent": "scout",
    }
