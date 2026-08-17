# tests/test_platform_node.py
"""Tests for Platform Agent Node (Phase 5c)."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from agentic.state import MasterAgentState
from agentic.schemas import CandidateRecipe, ScorerReport
from agentic.platform.platform_node import real_platform_agent_node


def _make_state_with_dic() -> MasterAgentState:
    """Create a MasterAgentState with populated DIC for platform node."""
    state = MasterAgentState()
    dic_dict = state.dic.model_dump()
    dic_dict["dataset_identity"] = {"name": "Test Dataset", "family": "Industrial SCADA"}
    dic_dict["compiled_dataset"] = {"tables": 1, "rows": 500, "columns": 25}
    state_dict = state.model_dump()
    state_dict["dic"] = dic_dict
    state_dict["cuc"]["goal"] = {"primary_intent": "train_rul"}
    return MasterAgentState(**state_dict)


@patch("agentic.platform.platform_node.resolve_candidates")
@patch("agentic.platform.platform_node._train_candidate")
@patch("agentic.platform.platform_node.judge_candidate")
@patch("agentic.platform.platform_node.log_experiment")
def test_platform_node_produces_selection_result(mock_log, mock_judge, mock_train, mock_resolve):
    """Platform node should populate selection_result on state."""
    mock_resolve.return_value = [
        CandidateRecipe(recipe_id="r1", dag_id="DAG_414", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
        CandidateRecipe(recipe_id="r2", dag_id="DAG_241", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
        CandidateRecipe(recipe_id="r3", dag_id="DAG_906", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
    ]

    np.random.seed(42)
    y_true = np.random.randn(50)
    mock_train.return_value = (y_true, y_true + np.random.randn(50) * 0.5, 10.0, 0.5)

    from agentic.schemas import JudgeReport
    mock_judge.return_value = JudgeReport(
        recipe_id="r1", qualitative_score=0.8, rubric_ratings={},
        reasoning="heuristic", risk_assessment="low",
    )
    mock_log.return_value = {"status": "logged", "run_id": "test_run"}

    state = _make_state_with_dic()
    updates = real_platform_agent_node(state)

    assert "selection_result" in updates
    assert "scorer_reports" in updates
    assert "candidate_recipes" in updates
    assert "oof_predictions" in updates
    assert len(updates["candidate_recipes"]) == 3
    assert len(updates["scorer_reports"]) >= 3
    assert updates["selection_result"]["winner_model_id"] is not None


@patch("agentic.platform.platform_node.resolve_candidates")
@patch("agentic.platform.platform_node._train_candidate")
def test_platform_node_handles_candidate_failure(mock_train, mock_resolve):
    """If one candidate fails, platform should proceed with remaining (K >= 2)."""
    mock_resolve.return_value = [
        CandidateRecipe(recipe_id="ok1", dag_id="DAG_414", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
        CandidateRecipe(recipe_id="fail1", dag_id="DAG_999", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
        CandidateRecipe(recipe_id="ok2", dag_id="DAG_241", algo_family="REGRESSION", hyperparameters={}, feature_config={}),
    ]

    np.random.seed(42)
    y_true = np.random.randn(50)

    def side_effect(candidate, state):
        if candidate.recipe_id == "fail1":
            raise RuntimeError("OOM on DAG_999")
        return (y_true, y_true + np.random.randn(50) * 0.3, 8.0, 0.4)

    mock_train.side_effect = side_effect

    state = _make_state_with_dic()
    updates = real_platform_agent_node(state)

    # Should still produce a result from 2 successful candidates
    assert len(updates["scorer_reports"]) >= 2
    assert updates["selection_result"]["winner_model_id"] is not None
