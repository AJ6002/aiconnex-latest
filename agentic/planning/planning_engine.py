"""
aiconnex_agent/planning/planning_engine.py
===========================================
Main Planning Engine Orchestrator running the 2 sub-modules:
  1. IntentPlanMapper
  2. PlanValidator
Replaces stub_planning_engine_node with real deterministic CUC -> ExecutionPlan routing.

Telemetry: emits execution plan DAG and intent to the cross-cutting
AgentTelemetry service via PlannerEmitter.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from agentic.state import MasterAgentState
from agentic.planning.intent_plan_mapper import IntentPlanMapper
from agentic.planning.plan_validator import PlanValidator

logger = logging.getLogger(__name__)

# Module singletons
intent_plan_mapper = IntentPlanMapper()
plan_validator = PlanValidator()


def real_planning_engine_node(state: MasterAgentState) -> Dict[str, Any]:
    """Real Planning Engine Node: CUC primary_intent -> validated ExecutionPlan."""
    logger.info("[PlanningEngine] Executing intent -> plan routing")
    intent = state.cuc.goal.primary_intent if hasattr(state.cuc.goal, "primary_intent") else state.cuc.goal.get("primary_intent", "general")


    raw_steps = intent_plan_mapper.get_plan(intent)
    plan = plan_validator.validate(raw_steps, source_intent=intent)

    plan_steps = [step.model_dump() if hasattr(step, "model_dump") else step.dict() for step in plan.steps]
    first_agent = plan_steps[0]["target_agent"]

    # --- Telemetry: emit to cross-cutting observability service ---
    try:
        from agentic.telemetry.emitters import PlannerEmitter
        PlannerEmitter().emit(
            session_id=state.session_id,
            intent=intent,
            plan_steps=plan_steps,
        )
    except Exception as exc:
        logger.debug(f"[PlanningEngine] Telemetry emit skipped: {exc}")

    return {
        "plan_steps": plan_steps,
        "current_step_index": 0,
        "active_agent": first_agent,
    }
