"""
tests/test_telemetry.py
========================
Unit and integration tests for the cross-cutting Telemetry infrastructure:
  - AgentTelemetry singleton and node_run() context manager
  - LLM tracer initialization (idempotency, graceful no-op without mlflow)
  - PlannerEmitter, ScoutEmitter, PlatformEmitter, MemoryEmitter
  - Silent fallback behavior when mlflow is disabled/unavailable
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_telemetry():
    """Reset the telemetry singleton between tests."""
    from agentic.telemetry.tracker import reset_telemetry
    from agentic.telemetry.llm_tracer import reset_llm_tracing
    reset_telemetry()
    reset_llm_tracing()


# ---------------------------------------------------------------------------
# LLM Tracer Tests
# ---------------------------------------------------------------------------

class TestLLMTracer:
    def setup_method(self):
        _reset_telemetry()

    def test_init_llm_tracing_is_idempotent(self):
        """Calling init_llm_tracing multiple times must not raise."""
        from agentic.telemetry.llm_tracer import init_llm_tracing
        init_llm_tracing()
        init_llm_tracing()  # second call must be a no-op

    def test_init_llm_tracing_no_op_without_mlflow(self):
        """init_llm_tracing gracefully no-ops if mlflow cannot be imported."""
        from agentic.telemetry.llm_tracer import init_llm_tracing, reset_llm_tracing
        reset_llm_tracing()
        with patch.dict("sys.modules", {"mlflow": None}):
            init_llm_tracing()  # Must not raise


# ---------------------------------------------------------------------------
# AgentTelemetry Singleton Tests
# ---------------------------------------------------------------------------

class TestAgentTelemetry:
    def setup_method(self):
        _reset_telemetry()

    def test_get_telemetry_returns_singleton(self):
        """get_telemetry() must return the same instance on repeated calls."""
        from agentic.telemetry.tracker import get_telemetry
        t1 = get_telemetry()
        t2 = get_telemetry()
        assert t1 is t2

    def test_reset_telemetry_creates_new_instance(self):
        """reset_telemetry() should allow a fresh singleton to be created."""
        from agentic.telemetry.tracker import get_telemetry, reset_telemetry
        t1 = get_telemetry()
        reset_telemetry()
        t2 = get_telemetry()
        assert t1 is not t2

    def test_setup_is_idempotent(self):
        """setup() with the same session_id must not raise on repeat calls."""
        from agentic.telemetry.tracker import AgentTelemetry
        t = AgentTelemetry(tracking_uri="./mlruns")
        t.setup("wf_test001")
        t.setup("wf_test001")  # must be a no-op

    def test_node_run_yields_without_mlflow(self):
        """node_run() must yield None gracefully when mlflow is unavailable."""
        from agentic.telemetry.tracker import AgentTelemetry
        t = AgentTelemetry()
        # Force _HAS_MLFLOW to False via patch
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            with t.node_run("planner", "wf_test") as run:
                assert run is None

    def test_log_params_no_op_without_mlflow(self):
        """log_params must not raise when mlflow is unavailable."""
        from agentic.telemetry.tracker import AgentTelemetry
        t = AgentTelemetry()
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            t.log_params({"intent": "train_rul", "steps": 3})  # must not raise

    def test_log_metrics_no_op_without_mlflow(self):
        """log_metrics must not raise when mlflow is unavailable."""
        from agentic.telemetry.tracker import AgentTelemetry
        t = AgentTelemetry()
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            t.log_metrics({"rows": 1000.0, "missing_ratio": 0.02})  # must not raise


# ---------------------------------------------------------------------------
# PlannerEmitter Tests
# ---------------------------------------------------------------------------

class TestPlannerEmitter:
    def setup_method(self):
        _reset_telemetry()

    def test_emit_does_not_raise(self):
        """PlannerEmitter.emit() must not raise even with a minimal plan."""
        from agentic.telemetry.emitters import PlannerEmitter
        emitter = PlannerEmitter()
        emitter.emit(
            session_id="wf_planner01",
            intent="compile_zip",
            plan_steps=[{"target_agent": "scout", "description": "Compile dataset"}],
        )

    def test_emit_no_op_without_mlflow(self):
        """PlannerEmitter.emit() must not raise when mlflow is disabled."""
        from agentic.telemetry.emitters import PlannerEmitter
        emitter = PlannerEmitter()
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            emitter.emit(
                session_id="wf_planner02",
                intent="train_rul",
                plan_steps=[],
            )


# ---------------------------------------------------------------------------
# ScoutEmitter Tests
# ---------------------------------------------------------------------------

class TestScoutEmitter:
    def setup_method(self):
        _reset_telemetry()

    def _make_dic_and_scout(self):
        dic = {
            "dataset_identity": {"name": "test_dataset", "family": "time_series"},
            "compiled_dataset": {"rows": 5000, "columns": 12, "tables": 1},
            "quality_report": {"missing_ratio": 0.01},
        }
        scout = {
            "file_inventory": [{"filename": "data.csv"}],
            "parser_selection": {"compile_mode": "auto"},
        }
        return dic, scout

    def test_emit_does_not_raise(self):
        """ScoutEmitter.emit() must not raise with valid dict payloads."""
        from agentic.telemetry.emitters import ScoutEmitter
        dic, scout = self._make_dic_and_scout()
        ScoutEmitter().emit(session_id="wf_scout01", dic_dict=dic, scout_dict=scout)

    def test_emit_no_op_without_mlflow(self):
        """ScoutEmitter.emit() must not raise when mlflow is disabled."""
        from agentic.telemetry.emitters import ScoutEmitter
        dic, scout = self._make_dic_and_scout()
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            ScoutEmitter().emit(session_id="wf_scout02", dic_dict=dic, scout_dict=scout)


# ---------------------------------------------------------------------------
# PlatformEmitter Tests
# ---------------------------------------------------------------------------

class TestPlatformEmitter:
    def setup_method(self):
        _reset_telemetry()

    def _make_mock_platform_args(self):
        import numpy as np
        from agentic.schemas import (
            ScorerReport, JudgeReport, SelectionResult, LeaderboardEntry
        )
        sr = ScorerReport(
            recipe_id="recipe_xgb",
            r2_score=0.88,
            rmse=3.2,
            mae=2.1,
            mape=5.5,
            latency_ms=120.0,
            model_size_mb=1.4,
        )
        jr = JudgeReport(
            recipe_id="recipe_xgb",
            qualitative_score=0.82,
            rationale="Good generalization",
            recommendation="accept",
        )
        lb_entry = LeaderboardEntry(
            rank=1,
            model_id="recipe_xgb",
            dag_id="dag_001",
            algo_name="XGBoost",
            composite_score=0.87,
            r2_score=0.88,
            rmse=3.2,
        )
        sel = SelectionResult(
            winner_model_id="recipe_xgb",
            winner_dag_id="dag_001",
            is_ensemble=False,
            leaderboard=[lb_entry],
            selection_rationale="Best MCDA score",
        )
        weights = np.array([0.6, 0.4])
        return sr, jr, sel, weights

    def test_emit_does_not_raise(self):
        """PlatformEmitter.emit() must not raise with valid schema objects."""
        from agentic.telemetry.emitters import PlatformEmitter
        sr, jr, sel, weights = self._make_mock_platform_args()
        result = PlatformEmitter().emit(
            session_id="wf_platform01",
            selection_result=sel,
            scorer_reports=[sr],
            judge_reports=[jr],
            ensemble_weights=weights,
        )
        assert "session_id" in result
        assert result["session_id"] == "wf_platform01"

    def test_log_experiment_facade_alias(self):
        """log_experiment() must be a working alias for emit()."""
        from agentic.telemetry.emitters import PlatformEmitter
        sr, jr, sel, weights = self._make_mock_platform_args()
        result = PlatformEmitter().log_experiment(
            session_id="wf_platform02",
            selection_result=sel,
            scorer_reports=[sr],
            judge_reports=[jr],
        )
        assert "session_id" in result

    def test_emit_no_op_without_mlflow(self):
        """PlatformEmitter.emit() must not raise when mlflow is disabled."""
        from agentic.telemetry.emitters import PlatformEmitter
        sr, jr, sel, weights = self._make_mock_platform_args()
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            result = PlatformEmitter().emit(
                session_id="wf_platform03",
                selection_result=sel,
                scorer_reports=[sr],
                judge_reports=[jr],
            )
        assert "session_id" in result


# ---------------------------------------------------------------------------
# MemoryEmitter Tests
# ---------------------------------------------------------------------------

class TestMemoryEmitter:
    def setup_method(self):
        _reset_telemetry()

    def test_emit_does_not_raise(self):
        """MemoryEmitter.emit() must not raise with valid args."""
        from agentic.telemetry.emitters import MemoryEmitter
        MemoryEmitter().emit(
            session_id="wf_memory01",
            event_count=5,
            memory_bank_summary={
                "session": {"facts": ["f1", "f2"]},
                "entities": {"ds_test": {"name": "test"}},
                "decisions": ["d1"],
            },
            semantic_hits=2,
        )

    def test_emit_no_op_without_mlflow(self):
        """MemoryEmitter.emit() must not raise when mlflow is disabled."""
        from agentic.telemetry.emitters import MemoryEmitter
        with patch("agentic.telemetry.tracker._HAS_MLFLOW", False):
            MemoryEmitter().emit(
                session_id="wf_memory02",
                event_count=3,
                memory_bank_summary={},
                semantic_hits=0,
            )


# ---------------------------------------------------------------------------
# MLflow Logger Facade Tests (backward compatibility)
# ---------------------------------------------------------------------------

class TestMLflowLoggerFacade:
    """Verify the legacy platform/mlflow_logger.py facade delegates correctly."""

    def test_log_experiment_delegates_to_platform_emitter(self):
        """mlflow_logger.log_experiment() must call PlatformEmitter.log_experiment()."""
        from agentic.telemetry.emitters import PlatformEmitter
        from agentic.schemas import (
            ScorerReport, JudgeReport, SelectionResult, LeaderboardEntry
        )

        sr = ScorerReport(recipe_id="r1", r2_score=0.9, rmse=2.0, mae=1.5, mape=3.0, latency_ms=100.0, model_size_mb=1.0)
        jr = JudgeReport(recipe_id="r1", qualitative_score=0.85, rationale="OK", recommendation="accept")
        lb = LeaderboardEntry(rank=1, model_id="r1", dag_id="d1", algo_name="XGBoost", composite_score=0.88, r2_score=0.9, rmse=2.0)
        sel = SelectionResult(winner_model_id="r1", winner_dag_id="d1", is_ensemble=False, leaderboard=[lb], selection_rationale="Best")

        with patch.object(PlatformEmitter, "log_experiment", return_value={"status": "logged", "session_id": "wf_facade01"}) as mock_emit:
            from agentic.platform import mlflow_logger
            import importlib
            importlib.reload(mlflow_logger)
            result = mlflow_logger.log_experiment("wf_facade01", sel, [sr], [jr])

        assert result.get("session_id") == "wf_facade01"

    def test_log_experiment_returns_error_dict_on_failure(self):
        """mlflow_logger.log_experiment() returns error dict (not exception) on failure."""
        from agentic.platform import mlflow_logger
        from agentic.schemas import SelectionResult, LeaderboardEntry

        lb = LeaderboardEntry(rank=1, model_id="r1", dag_id="d1", algo_name="XGBoost", composite_score=0.88, r2_score=0.9, rmse=2.0)
        sel = SelectionResult(winner_model_id="r1", winner_dag_id="d1", is_ensemble=False, leaderboard=[lb], selection_rationale="Best")

        with patch("agentic.telemetry.emitters.PlatformEmitter.log_experiment", side_effect=Exception("boom")):
            result = mlflow_logger.log_experiment("wf_facade02", sel, [], [])

        # Must return a dict, not raise
        assert isinstance(result, dict)
