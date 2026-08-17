"""
workflow_planner_node (Task 12) — locked recipe → technical WorkflowManifest.
================================================================================
Reads state.pipeline_lock (produced by pipeline_lock_node) and emits a
WorkflowManifest that describes the technical execution DAG the Compiler and
Platform Agent will run.

Design intent:
  - v1 always produces a linear 3-stage workflow: feature_engineering → task
    (train / detect_anomalies) → evaluate. Every task type is a concrete stage,
    not a stub.
  - v2 will extend this to compound workflows (predictive maintenance: anomaly
    → health_index → RUL → maintenance_schedule with real depends_on chains).
    The WorkflowManifest schema already supports that shape; only the planning
    logic here needs to grow.
  - Refuses to plan without a pipeline_lock — honours the audit boundary from
    Task 11.

Reads:  state.pipeline_lock
Writes: state.workflow_manifest
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agentic.schemas import WorkflowManifest, WorkflowStage
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


# Task family → primary "middle" stage name for the linear 3-stage workflow.
# Kept as data so v2 can extend it without touching planner logic below.
_TASK_TO_MIDDLE_STAGE: Dict[str, str] = {
    "regression": "train",
    "forecast": "train",
    "classification": "train",
    "anomaly": "detect_anomalies",
    # HYBRID is deliberately absent — the planner drops to a fallback single-
    # stage warning workflow if it sees a hybrid or unknown task_family.
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a Pydantic model or a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _plan_linear_workflow(lock: Any) -> WorkflowManifest:
    """v1: 3-stage linear pipeline for well-known task families."""
    task_family = str(_get(lock, "selected_workflow_type", "") or "").lower().strip()
    middle_task = _TASK_TO_MIDDLE_STAGE.get(task_family)

    session_id = _get(lock, "session_id")
    recipe_id = _get(lock, "locked_recipe_id", "")
    target_column = _get(lock, "target_column")
    operational_preferences = dict(_get(lock, "operational_preferences", {}) or {})
    success_metrics = list(_get(lock, "success_metrics", []) or [])

    if middle_task is None:
        # Unknown/hybrid task family — safe single-stage fallback with a note,
        # per the "no stubs but be honest" principle.
        stage = WorkflowStage(
            stage_id="stage_1",
            task="train",
            depends_on=[],
            config={
                "target_column": target_column,
                "task_family": task_family or "unknown",
                "operational_preferences": operational_preferences,
                "success_metrics": success_metrics,
                "warning": (
                    f"task_family={task_family!r} is not supported by workflow_planner v1; "
                    "downstream may need to specialise the plan"
                ),
            },
        )
        return WorkflowManifest(
            session_id=session_id,
            locked_recipe_id=recipe_id,
            stages=[stage],
            total_stages=1,
            parallel_possible=False,
            planner_notes=[
                f"Task family {task_family!r} not recognised — produced a single-stage safe fallback plan",
            ],
        )

    # 3-stage linear workflow: feature_engineering → middle_task → evaluate
    fe_stage = WorkflowStage(
        stage_id="stage_1",
        task="feature_engineering",
        depends_on=[],
        config={
            "target_column": target_column,
            "task_family": task_family,
            "operational_preferences": operational_preferences,
        },
    )
    middle_stage = WorkflowStage(
        stage_id="stage_2",
        task=middle_task,
        depends_on=["stage_1"],
        config={
            "target_column": target_column,
            "task_family": task_family,
            "operational_preferences": operational_preferences,
            "success_metrics": success_metrics,
        },
    )
    eval_stage = WorkflowStage(
        stage_id="stage_3",
        task="evaluate",
        depends_on=["stage_2"],
        config={
            "target_column": target_column,
            "task_family": task_family,
            "success_metrics": success_metrics,
        },
    )

    return WorkflowManifest(
        session_id=session_id,
        locked_recipe_id=recipe_id,
        stages=[fe_stage, middle_stage, eval_stage],
        total_stages=3,
        parallel_possible=False,  # linear chain — always False in v1
        planner_notes=[
            f"Linear 3-stage plan produced for task_family={task_family!r}, "
            f"target={target_column!r}, recipe={recipe_id!r}",
        ],
    )


def workflow_planner_node(state: MasterAgentState) -> Dict[str, Any]:
    """Task 12: convert a PipelineLockManifest into a WorkflowManifest."""
    logger.info("[WorkflowPlanner] Starting")

    lock = state.pipeline_lock
    if lock is None:
        logger.warning("[WorkflowPlanner] No pipeline_lock on state — refusing to plan; returning empty")
        return {}

    manifest = _plan_linear_workflow(lock)
    logger.info(
        f"[WorkflowPlanner] Planned {manifest.total_stages}-stage workflow for "
        f"recipe={manifest.locked_recipe_id}: {[s.task for s in manifest.stages]}"
    )
    return {
        "workflow_manifest": manifest.model_dump(),
        "active_agent": "platform",
    }
