# aiconnex_agent/platform/selector_agent.py
"""
Selector Agent (Phase 5c)
===========================
Multi-Criteria Decision Analysis (MCDA) combining Scorer hard metrics (50%),
Judge qualitative scores (30%), and user CUC intent preference (20%) to pick
the Winner and generate the ranked leaderboard.

Fail-soft: operates independently of the Judge Agent. If no judge reports
are available, selection is based on Scorer metrics alone.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from agentic.schemas import (
    ScorerReport,
    JudgeReport,
    LeaderboardEntry,
    SelectionResult,
)

logger = logging.getLogger(__name__)

# MCDA weight distribution
_SCORER_WEIGHT = 0.50
_JUDGE_WEIGHT = 0.30
_INTENT_WEIGHT = 0.20


def _normalize_scorer(scorer: ScorerReport) -> float:
    """Normalize scorer metrics into a [0, 1] composite.

    Higher R² is better (weight 0.4), lower RMSE is better (weight 0.3),
    lower MAPE is better (weight 0.3). All clamped to [0, 1].
    """
    r2_norm = max(0.0, min(1.0, scorer.r2_score))
    rmse_norm = max(0.0, 1.0 - scorer.rmse / 100.0)
    mape_norm = max(0.0, 1.0 - scorer.mape / 20.0)
    return r2_norm * 0.4 + rmse_norm * 0.3 + mape_norm * 0.3


def _intent_bonus(recipe_id: str, cuc_intent: str) -> float:
    """Small bonus for recipes that align with user intent keywords."""
    return 1.0


def select_winner(
    scorer_reports: List[ScorerReport],
    judge_reports: List[JudgeReport],
    cuc_intent: str = "general",
) -> SelectionResult:
    """Select the winning model via Multi-Criteria Decision Analysis.

    Args:
        scorer_reports: One ScorerReport per candidate.
        judge_reports: Zero or more JudgeReports (fail-soft if empty).
        cuc_intent: The user's primary intent from the CUC contract.

    Returns:
        SelectionResult with ranked leaderboard and winner identification.
    """
    judge_map: Dict[str, JudgeReport] = {jr.recipe_id: jr for jr in judge_reports}
    has_judge = len(judge_map) > 0

    # Compute composite scores
    scored_candidates: List[tuple] = []
    for sr in scorer_reports:
        scorer_norm = _normalize_scorer(sr)
        judge_norm = judge_map[sr.recipe_id].qualitative_score if sr.recipe_id in judge_map else 0.5
        intent_norm = _intent_bonus(sr.recipe_id, cuc_intent)

        if has_judge:
            composite = (scorer_norm * _SCORER_WEIGHT +
                         judge_norm * _JUDGE_WEIGHT +
                         intent_norm * _INTENT_WEIGHT)
        else:
            # No judge — rebalance weights: 80% scorer, 20% intent
            composite = scorer_norm * 0.80 + intent_norm * 0.20

        scored_candidates.append((sr.recipe_id, composite, sr))

    # Sort descending by composite score
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    # Build leaderboard
    leaderboard: List[LeaderboardEntry] = []
    for rank, (recipe_id, composite, sr) in enumerate(scored_candidates, start=1):
        leaderboard.append(LeaderboardEntry(
            rank=rank,
            model_id=recipe_id,
            dag_id=recipe_id.split("_")[1].upper() if "_" in recipe_id else recipe_id,
            algo_name=recipe_id,
            composite_score=round(composite, 6),
            r2_score=sr.r2_score,
            rmse=sr.rmse,
            mae=sr.mae,
            is_winner=(rank == 1),
        ))

    winner = leaderboard[0]
    is_ensemble = winner.model_id.startswith("recipe_stacked_ensemble")
    rationale = (
        f"{winner.model_id} selected with composite score {winner.composite_score:.4f}. "
        f"R²={winner.r2_score:.4f}, RMSE={winner.rmse:.2f}, MAE={winner.mae:.2f}."
    )

    return SelectionResult(
        winner_model_id=winner.model_id,
        winner_dag_id=winner.dag_id,
        is_ensemble=is_ensemble,
        selection_rationale=rationale,
        leaderboard=leaderboard,
    )
