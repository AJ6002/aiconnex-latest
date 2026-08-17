# tests/test_mlflow_logger.py
"""Tests for MLflow Logger facade (refactored to cross-cutting telemetry service).

The facade ``agentic.platform.mlflow_logger.log_experiment()`` now
delegates to ``PlatformEmitter``. These tests verify:
  1. The facade API contract is preserved (correct return dict).
  2. PlatformEmitter.log_experiment() is called with the right arguments.
  3. Graceful no-op fallback when mlflow is unavailable.
"""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

from agentic.schemas import (
    ScorerReport, JudgeReport, SelectionResult, LeaderboardEntry,
)
from agentic.platform.mlflow_logger import log_experiment


def _make_test_data():
    scorers = [
        ScorerReport(recipe_id="A", r2_score=0.90, rmse=15.0, mae=10.0, mape=5.0, latency_ms=10, model_size_mb=1.0),
        ScorerReport(recipe_id="B", r2_score=0.95, rmse=10.0, mae=7.0, mape=3.0, latency_ms=8, model_size_mb=0.5),
    ]
    judges = [
        JudgeReport(recipe_id="A", qualitative_score=0.7, rubric_ratings={}, reasoning="ok", risk_assessment="medium"),
        JudgeReport(recipe_id="B", qualitative_score=0.9, rubric_ratings={}, reasoning="good", risk_assessment="low"),
    ]
    leaderboard = [
        LeaderboardEntry(rank=1, model_id="B", dag_id="DAG_414", algo_name="LightGBM",
                         composite_score=0.93, r2_score=0.95, rmse=10.0, mae=7.0, is_winner=True),
        LeaderboardEntry(rank=2, model_id="A", dag_id="DAG_241", algo_name="RandomForest",
                         composite_score=0.85, r2_score=0.90, rmse=15.0, mae=10.0, is_winner=False),
    ]
    selection = SelectionResult(
        winner_model_id="B", winner_dag_id="DAG_414", is_ensemble=False,
        selection_rationale="Best composite score.", leaderboard=leaderboard,
    )
    return scorers, judges, selection


def test_log_experiment_returns_run_info():
    """log_experiment() facade should return a dict with session_id and status."""
    scorers, judges, selection = _make_test_data()
    # Patch PlatformEmitter.log_experiment in the telemetry layer
    mock_result = {
        "status": "logged",
        "run_id": "abc123",
        "experiment_name": "aiconnex_wf_test1234",
        "tracking_uri": "./mlruns",
        "session_id": "wf_test1234",
    }
    with patch(
        "agentic.telemetry.emitters.PlatformEmitter.log_experiment",
        return_value=mock_result,
    ) as mock_emit:
        result = log_experiment("wf_test1234", selection, scorers, judges)

    assert "session_id" in result
    assert result["session_id"] == "wf_test1234"
    assert "status" in result
    mock_emit.assert_called_once()


def test_log_experiment_logs_winner_metrics():
    """log_experiment() facade should invoke PlatformEmitter with scorer/judge reports."""
    scorers, judges, selection = _make_test_data()

    with patch(
        "agentic.telemetry.emitters.PlatformEmitter.log_experiment",
        return_value={"status": "logged", "session_id": "wf_test5678"},
    ) as mock_emit:
        log_experiment("wf_test5678", selection, scorers, judges)

    # Verify PlatformEmitter received the scorer and judge reports
    call_kwargs = mock_emit.call_args.kwargs
    assert call_kwargs["scorer_reports"] == scorers
    assert call_kwargs["judge_reports"] == judges
    assert call_kwargs["selection_result"] == selection


def test_log_experiment_graceful_without_mlflow():
    """If mlflow is not installed (tracker has _HAS_MLFLOW=False), log_experiment must not raise."""
    with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
        scorers, judges, selection = _make_test_data()
        result = log_experiment("wf_nomlflow", selection, scorers, judges)
    # Must return a dict with at least session_id (either logged or no-run graceful)
    assert isinstance(result, dict)
    assert "session_id" in result
