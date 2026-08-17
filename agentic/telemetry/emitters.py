"""
aiconnex_agent/telemetry/emitters.py
=======================================
Specialized telemetry emitters — one per agent node type.

Each emitter encapsulates the knowledge of *what* to log for its node,
delegating the *how* to AgentTelemetry (which owns MLflow plumbing).

Emitters:
  PlannerEmitter  — execution plan DAGs and step sequences
  ScoutEmitter    — dataset compilation profile, file inventory, DIC stats
  PlatformEmitter — multi-candidate benchmarks, ensemble weights, evaluation triad
  MemoryEmitter   — event store metrics, memory layer projection stats

All emitters are stateless and safe to instantiate multiple times.
All public methods are no-ops when mlflow is not installed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PlannerEmitter
# ---------------------------------------------------------------------------

class PlannerEmitter:
    """Emits planning engine telemetry to MLflow.

    Logs:
      - Number of plan steps and target agent sequence
      - Primary intent detected
      - Full ExecutionPlan JSON as an artifact
    """

    def emit(
        self,
        session_id: str,
        intent: str,
        plan_steps: List[Dict[str, Any]],
    ) -> None:
        """Emit planning engine telemetry."""
        from agentic.telemetry.tracker import get_telemetry

        telemetry = get_telemetry()
        telemetry.setup(session_id)

        with telemetry.node_run("planner", session_id):
            telemetry.log_params({
                "planner_intent": intent,
                "planner_step_count": len(plan_steps),
                "planner_agents_sequence": " -> ".join(
                    s.get("target_agent", "?") for s in plan_steps
                ),
            })
            telemetry.log_metrics({"plan_steps_count": float(len(plan_steps))})
            telemetry.log_json_artifact(
                {"session_id": session_id, "intent": intent, "steps": plan_steps},
                artifact_name="execution_plan.json",
            )
            telemetry.log_tag("node_type", "planner")

        logger.debug(f"[PlannerEmitter] Emitted telemetry for session {session_id}")


# ---------------------------------------------------------------------------
# ScoutEmitter
# ---------------------------------------------------------------------------

class ScoutEmitter:
    """Emits Scout Agent dataset compilation telemetry to MLflow.

    Logs:
      - Dataset dimensions (rows, cols, tables)
      - Missing ratio and quality flags
      - File inventory count and detected formats
      - Full DatasetIntelligenceContract JSON as artifact
    """

    def emit(
        self,
        session_id: str,
        dic_dict: Dict[str, Any],
        scout_dict: Dict[str, Any],
    ) -> None:
        """Emit Scout Agent compilation telemetry."""
        from agentic.telemetry.tracker import get_telemetry

        telemetry = get_telemetry()
        telemetry.setup(session_id)

        compiled = dic_dict.get("compiled_dataset", {})
        quality = dic_dict.get("quality_report", {})
        identity = dic_dict.get("dataset_identity", {})
        file_inventory = scout_dict.get("file_inventory", [])

        with telemetry.node_run("scout", session_id):
            telemetry.log_params({
                "scout_dataset_name": identity.get("name", "unknown"),
                "scout_dataset_family": identity.get("family", "unknown"),
                "scout_file_count": len(file_inventory),
                "scout_compile_mode": scout_dict.get("parser_selection", {}).get("compile_mode", "auto"),
            })
            telemetry.log_metrics({
                "scout_rows": float(compiled.get("rows", 0)),
                "scout_columns": float(compiled.get("columns", 0)),
                "scout_tables": float(compiled.get("tables", 0)),
                "scout_missing_ratio": float(quality.get("missing_ratio", 0.0)),
                "scout_file_count": float(len(file_inventory)),
            })
            telemetry.log_json_artifact(
                {"session_id": session_id, "dic": dic_dict, "scout": scout_dict},
                artifact_name="dataset_intelligence_contract.json",
            )
            telemetry.log_tag("node_type", "scout")

        logger.debug(f"[ScoutEmitter] Emitted telemetry for session {session_id}")


# ---------------------------------------------------------------------------
# PlatformEmitter
# ---------------------------------------------------------------------------

class PlatformEmitter:
    """Emits Platform Agent experiment telemetry to MLflow.

    Logs:
      - Multi-candidate leaderboard (winner, all candidates)
      - Scorer metrics (R², RMSE, MAE, MAPE, latency, model size)
      - Ensemble meta-learner weights
      - Full SelectionResult JSON as artifact
      - Optional: model binary artifact
    """

    def emit(
        self,
        session_id: str,
        selection_result: Any,
        scorer_reports: List[Any],
        judge_reports: List[Any],
        ensemble_weights: Optional[np.ndarray] = None,
        model_artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Emit Platform Agent multi-candidate experiment telemetry.

        Returns:
            Dict with ``run_id``, ``experiment_name``, ``tracking_uri``, ``status``.
        """
        from agentic.telemetry.tracker import get_telemetry

        telemetry = get_telemetry()
        telemetry.setup(session_id)

        with telemetry.node_run("platform", session_id) as run:
            # --- Winner params ---
            telemetry.log_params({
                "platform_winner_model_id": selection_result.winner_model_id,
                "platform_winner_dag_id": selection_result.winner_dag_id,
                "platform_is_ensemble": str(selection_result.is_ensemble),
                "platform_num_candidates": len(scorer_reports),
                "platform_rationale": selection_result.selection_rationale[:500],
            })

            # --- Ensemble meta-learner weights ---
            if ensemble_weights is not None:
                for k, w in enumerate(ensemble_weights):
                    telemetry.log_params({f"meta_weight_base_{k}": float(w)})

            # --- Winner scorer metrics ---
            winner_scorer = next(
                (sr for sr in scorer_reports if sr.recipe_id == selection_result.winner_model_id),
                None,
            )
            if winner_scorer:
                telemetry.log_metrics({
                    "platform_winner_r2": winner_scorer.r2_score,
                    "platform_winner_rmse": winner_scorer.rmse,
                    "platform_winner_mae": winner_scorer.mae,
                    "platform_winner_mape": winner_scorer.mape,
                    "platform_winner_latency_ms": winner_scorer.latency_ms,
                    "platform_winner_model_size_mb": winner_scorer.model_size_mb,
                })

            # --- All candidate metrics ---
            for i, sr in enumerate(scorer_reports):
                telemetry.log_metrics({
                    f"platform_candidate_{i}_r2": sr.r2_score,
                    f"platform_candidate_{i}_rmse": sr.rmse,
                    f"platform_candidate_{i}_mae": sr.mae,
                })

            # --- Leaderboard tag ---
            lb_summary = " | ".join(
                f"#{e.rank} {e.model_id} (R²={e.r2_score:.4f})"
                for e in selection_result.leaderboard
            )
            telemetry.log_tag("platform_leaderboard", lb_summary)
            telemetry.log_tag("node_type", "platform")

            # --- Full SelectionResult artifact ---
            telemetry.log_json_artifact(
                {
                    "session_id": session_id,
                    "selection_result": selection_result.model_dump(),
                    "scorer_reports": [sr.model_dump() for sr in scorer_reports],
                    "judge_reports": [jr.model_dump() for jr in judge_reports],
                    "ensemble_weights": (
                        ensemble_weights.tolist() if ensemble_weights is not None else None
                    ),
                },
                artifact_name="platform_experiment.json",
            )

            # --- Optional model binary artifact ---
            if model_artifact_path:
                try:
                    import os
                    import mlflow as _mlflow
                    if os.path.exists(model_artifact_path):
                        _mlflow.log_artifact(model_artifact_path, artifact_path="model_binaries")
                except Exception as exc:
                    logger.debug(f"[PlatformEmitter] Could not log model artifact: {exc}")

            run_id = run.info.run_id if run else "no_run"

        logger.info(f"[PlatformEmitter] Experiment logged. Run ID: {run_id}")
        return {
            "status": "logged",
            "run_id": run_id,
            "experiment_name": f"aiconnex_{session_id}",
            "tracking_uri": "./mlruns",
            "session_id": session_id,
        }

    def log_experiment(
        self,
        session_id: str,
        selection_result: Any,
        scorer_reports: List[Any],
        judge_reports: List[Any],
        ensemble_weights: Optional[np.ndarray] = None,
        model_artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible alias for emit(). Called by the mlflow_logger facade."""
        return self.emit(
            session_id=session_id,
            selection_result=selection_result,
            scorer_reports=scorer_reports,
            judge_reports=judge_reports,
            ensemble_weights=ensemble_weights,
            model_artifact_path=model_artifact_path,
        )


# ---------------------------------------------------------------------------
# MemoryEmitter
# ---------------------------------------------------------------------------

class MemoryEmitter:
    """Emits Memory Agent telemetry to MLflow.

    Logs:
      - Event store total event count for this session
      - Memory layer population counts (session, entity, procedural, decision)
      - Semantic search hits count
    """

    def emit(
        self,
        session_id: str,
        event_count: int,
        memory_bank_summary: Dict[str, Any],
        semantic_hits: int = 0,
    ) -> None:
        """Emit Memory Agent telemetry."""
        from agentic.telemetry.tracker import get_telemetry

        telemetry = get_telemetry()
        telemetry.setup(session_id)

        with telemetry.node_run("memory", session_id):
            telemetry.log_params({
                "memory_session_id": session_id,
            })
            telemetry.log_metrics({
                "memory_event_count": float(event_count),
                "memory_semantic_hits": float(semantic_hits),
                "memory_session_facts": float(
                    len(memory_bank_summary.get("session", {}).get("facts", []))
                ),
                "memory_entity_count": float(
                    len(memory_bank_summary.get("entities", {}))
                ),
                "memory_decision_count": float(
                    len(memory_bank_summary.get("decisions", []))
                ),
            })
            telemetry.log_json_artifact(
                {"session_id": session_id, "memory_bank": memory_bank_summary},
                artifact_name="memory_bank_snapshot.json",
            )
            telemetry.log_tag("node_type", "memory")

        logger.debug(f"[MemoryEmitter] Emitted memory telemetry for session {session_id}")
