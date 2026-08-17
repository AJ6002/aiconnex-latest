# tests/test_phase5c_contracts.py
"""Tests for Phase 5c Pydantic contracts and MasterAgentState extensions."""

from __future__ import annotations
import pytest
from agentic.schemas import (
    CandidateRecipe,
    ScorerReport,
    JudgeReport,
    LeaderboardEntry,
    SelectionResult,
)
from agentic.state import MasterAgentState


def test_candidate_recipe_roundtrip():
    cr = CandidateRecipe(
        recipe_id="recipe_dag414_lgbm",
        dag_id="DAG_414",
        algo_family="REGRESSION",
        hyperparameters={"n_estimators": 200, "learning_rate": 0.05},
        feature_config={"lag_steps": [1, 5, 10], "rolling_windows": [5, 10]},
    )
    d = cr.model_dump()
    assert d["dag_id"] == "DAG_414"
    assert d["algo_family"] == "REGRESSION"
    rebuilt = CandidateRecipe(**d)
    assert rebuilt == cr


def test_scorer_report_fields():
    sr = ScorerReport(
        recipe_id="recipe_dag414_lgbm",
        r2_score=0.92,
        rmse=12.5,
        mae=8.3,
        mape=4.1,
        latency_ms=23.5,
        model_size_mb=1.2,
    )
    assert sr.r2_score == 0.92
    assert sr.model_size_mb == 1.2


def test_judge_report_fields():
    jr = JudgeReport(
        recipe_id="recipe_dag414_lgbm",
        qualitative_score=0.85,
        rubric_ratings={"physical_realism": 0.9, "extrapolation_risk": 0.8},
        reasoning="Model predictions stay within physical bounds.",
        risk_assessment="Low risk — no out-of-bounds extrapolation detected.",
    )
    assert jr.qualitative_score == 0.85
    assert "physical_realism" in jr.rubric_ratings


def test_leaderboard_entry_defaults():
    entry = LeaderboardEntry(
        rank=1,
        model_id="model_lgbm_dag414",
        dag_id="DAG_414",
        algo_name="LightGBM",
        composite_score=0.91,
        r2_score=0.92,
        rmse=12.5,
        mae=8.3,
        is_winner=True,
    )
    assert entry.is_winner is True
    assert entry.rank == 1


def test_selection_result_with_leaderboard():
    entries = [
        LeaderboardEntry(rank=1, model_id="m1", dag_id="DAG_414", algo_name="LightGBM",
                         composite_score=0.91, r2_score=0.92, rmse=12.5, mae=8.3, is_winner=True),
        LeaderboardEntry(rank=2, model_id="m2", dag_id="DAG_241", algo_name="RandomForest",
                         composite_score=0.87, r2_score=0.88, rmse=15.0, mae=10.1, is_winner=False),
    ]
    result = SelectionResult(
        winner_model_id="m1",
        winner_dag_id="DAG_414",
        is_ensemble=False,
        selection_rationale="LightGBM scored highest on composite MCDA.",
        leaderboard=entries,
    )
    assert result.is_ensemble is False
    assert len(result.leaderboard) == 2
    assert result.leaderboard[0].is_winner is True


def test_master_agent_state_has_phase5c_fields():
    state = MasterAgentState()
    assert state.candidate_recipes == []
    assert state.oof_predictions == {}
    assert state.scorer_reports == []
    assert state.judge_reports == []
    assert state.selection_result == {}
