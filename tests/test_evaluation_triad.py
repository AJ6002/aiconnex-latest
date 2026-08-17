# tests/test_evaluation_triad.py
"""Tests for Evaluation Triad: Scorer, Judge, Selector Agents (Phase 5c)."""

from __future__ import annotations
import numpy as np
import pytest
from unittest.mock import patch

from agentic.schemas import ScorerReport, JudgeReport, SelectionResult
from agentic.platform.scorer_agent import score_candidate
from agentic.platform.judge_agent import judge_candidate
from agentic.platform.selector_agent import select_winner


# --- Scorer Agent ---

def test_scorer_computes_all_metrics():
    np.random.seed(42)
    y_true = np.random.randn(100) * 10 + 50
    y_pred = y_true + np.random.randn(100) * 2

    report = score_candidate(
        recipe_id="recipe_dag414_lgbm",
        y_true=y_true,
        y_pred=y_pred,
        latency_ms=15.0,
        model_size_mb=0.8,
    )
    assert isinstance(report, ScorerReport)
    assert report.recipe_id == "recipe_dag414_lgbm"
    assert 0.0 < report.r2_score <= 1.0
    assert report.rmse > 0
    assert report.mae > 0
    assert report.mape >= 0
    assert report.latency_ms == 15.0
    assert report.model_size_mb == 0.8


def test_scorer_perfect_predictions():
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_pred = y_true.copy()
    report = score_candidate("perfect", y_true, y_pred, 1.0, 0.1)
    assert report.r2_score == pytest.approx(1.0)
    assert report.rmse == pytest.approx(0.0)
    assert report.mae == pytest.approx(0.0)


# --- Judge Agent ---

def test_judge_deterministic_fallback():
    """When LLM is unavailable, judge should return deterministic fallback."""
    scorer = ScorerReport(
        recipe_id="test_recipe", r2_score=0.9, rmse=10.0,
        mae=7.0, mape=5.0, latency_ms=10.0, model_size_mb=0.5,
    )
    with patch("agentic.platform.judge_agent.get_llm", side_effect=Exception("LLM unavailable")):
        report = judge_candidate("test_recipe", scorer, {"rows": 1000, "columns": 20})

    assert isinstance(report, JudgeReport)
    assert report.recipe_id == "test_recipe"
    assert report.reasoning == "qualitative_unavailable"
    assert 0.0 <= report.qualitative_score <= 1.0


def test_judge_heuristic_scoring():
    """Heuristic fallback should produce a reasonable qualitative score."""
    scorer = ScorerReport(
        recipe_id="good_model", r2_score=0.95, rmse=5.0,
        mae=3.0, mape=2.0, latency_ms=5.0, model_size_mb=0.3,
    )
    with patch("agentic.platform.judge_agent.get_llm", side_effect=Exception("No LLM")):
        report = judge_candidate("good_model", scorer, {})
    # Good metrics should yield a high qualitative score
    assert report.qualitative_score >= 0.7


# --- Selector Agent ---

def test_selector_picks_best_composite():
    """Selector should pick the candidate with the highest composite score."""
    scorers = [
        ScorerReport(recipe_id="A", r2_score=0.90, rmse=15.0, mae=10.0, mape=5.0, latency_ms=10, model_size_mb=1.0),
        ScorerReport(recipe_id="B", r2_score=0.95, rmse=10.0, mae=7.0, mape=3.0, latency_ms=8, model_size_mb=0.5),
    ]
    judges = [
        JudgeReport(recipe_id="A", qualitative_score=0.7, rubric_ratings={}, reasoning="ok", risk_assessment="medium"),
        JudgeReport(recipe_id="B", qualitative_score=0.9, rubric_ratings={}, reasoning="good", risk_assessment="low"),
    ]
    result = select_winner(scorers, judges, cuc_intent="train_rul")

    assert isinstance(result, SelectionResult)
    assert result.winner_model_id == "B"
    assert len(result.leaderboard) == 2
    assert result.leaderboard[0].is_winner is True
    assert result.leaderboard[0].rank == 1


def test_selector_works_without_judge():
    """Selector should work with empty judge reports (fail-soft)."""
    scorers = [
        ScorerReport(recipe_id="X", r2_score=0.80, rmse=20.0, mae=15.0, mape=8.0, latency_ms=20, model_size_mb=2.0),
        ScorerReport(recipe_id="Y", r2_score=0.85, rmse=18.0, mae=12.0, mape=6.0, latency_ms=15, model_size_mb=1.5),
    ]
    result = select_winner(scorers, judge_reports=[], cuc_intent="train_rul")

    assert isinstance(result, SelectionResult)
    assert result.winner_model_id == "Y"  # Better metrics
    assert len(result.leaderboard) == 2


def test_selector_leaderboard_is_sorted_by_rank():
    scorers = [
        ScorerReport(recipe_id="C", r2_score=0.70, rmse=25.0, mae=20.0, mape=12.0, latency_ms=30, model_size_mb=3.0),
        ScorerReport(recipe_id="D", r2_score=0.88, rmse=14.0, mae=9.0, mape=4.5, latency_ms=12, model_size_mb=1.0),
        ScorerReport(recipe_id="E", r2_score=0.82, rmse=18.0, mae=13.0, mape=7.0, latency_ms=18, model_size_mb=1.8),
    ]
    result = select_winner(scorers, [], "train_rul")
    ranks = [e.rank for e in result.leaderboard]
    assert ranks == [1, 2, 3]
    assert result.leaderboard[0].composite_score >= result.leaderboard[1].composite_score
