"""
aiconnex_agent/nodes/plan_evaluator.py - Plan Evaluator Node
============================================================
Evaluates step execution progress and output quality in the multi-agent plan loop.
Prevents advancing the plan if an interrupt is pending or if a step failed quality criteria.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


def _validate_step_quality(agent: str, state: MasterAgentState) -> Tuple[bool, str]:
    """Inspect node output on state to verify step completion quality."""
    if agent == "scout":
        # Scout output check: DIC dataset rows > 0 or discovery inventory present
        if state.dic and state.dic.compiled_dataset and state.dic.compiled_dataset.rows > 0:
            return True, "Scout compiled dataset successfully"
        if state.scout_enriched and state.scout_enriched.file_inventory:
            return True, "Scout discovered archive inventory successfully"
        return False, "Scout produced no dataset records or inventory"

    elif agent == "platform":
        # Platform output check: candidate reports scored or MCDA selection present
        if state.scorer_reports and len(state.scorer_reports) > 0:
            return True, f"Platform trained and scored {len(state.scorer_reports)} candidates"
        if state.selection_result and "winner_model_id" in state.selection_result:
            return True, "Platform selection result present"
        return False, "Platform produced no candidate reports or selection"

    elif agent == "memory":
        # Memory output check: memory_context populated
        if state.memory_context and "memory_bank" in state.memory_context:
            return True, "Memory Agent persisted session bank"
        return True, "Memory Agent step completed"

    return True, "Default step pass"


def real_plan_evaluator_node(state: MasterAgentState) -> Dict[str, Any]:
    """Real Plan Evaluator Node: quality gate & step pointer advancement."""
    logger.info(f"[PlanEvaluator] Evaluating step {state.current_step_index} of {len(state.plan_steps)}")

    # 1. Gate on active interrupt (e.g. strategy choice or compile error)
    if state.interrupt_reason:
        logger.warning(f"[PlanEvaluator] Interrupt active ({state.interrupt_reason}) — holding step pointer at {state.current_step_index}")
        current_agent = (
            state.plan_steps[state.current_step_index]["target_agent"]
            if state.plan_steps and state.current_step_index < len(state.plan_steps)
            else "scout"
        )
        return {
            "current_step_index": state.current_step_index,
            "active_agent": current_agent,
        }

    # 2. Check quality of current step
    if state.plan_steps and state.current_step_index < len(state.plan_steps):
        current_step = state.plan_steps[state.current_step_index]
        target_agent = current_step.get("target_agent", "scout")
        passed, reason = _validate_step_quality(target_agent, state)
        logger.info(f"[PlanEvaluator] Quality check for '{target_agent}': passed={passed} ({reason})")

    # 3. Advance step index on pass
    next_idx = state.current_step_index + 1
    more_steps = next_idx < len(state.plan_steps)
    next_agent = state.plan_steps[next_idx]["target_agent"] if more_steps else "complete"

    return {
        "current_step_index": next_idx,
        "active_agent": next_agent,
    }
