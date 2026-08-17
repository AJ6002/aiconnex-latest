"""
aiconnex_agent/parser/conversation_planner.py
================================================
conversation_planner_node — Pre-Upload v1 Architecture (Task 5)

Replaces the legacy binary `score < 0.85` branch (real_conversation_parser_node)
with an explicit, registry-driven, multi-valued decision. This node OWNS
deciding what should happen next in the conversation; it does NOT write the
user-facing text (response_writer_node, Task 6) and does NOT extract or
merge CUC fields (intent_extraction_node / contract_manager_node).

Decision priority (highest first):
  1. Unresolved contradiction exists AND conversation_rules.surface_contradictions
     -> action='confirm'  (ask the user which value is correct; do not guess)
  2. Required fields (per Required Fields Registry) still missing
     -> action='ask'      (one field per turn, per max_questions_per_turn=1)
  3. All required fields satisfied, no unresolved contradictions, but this is
     the first turn reaching that state AND conversation_rules.always_summarize_before_upload
     -> action='summarize' (recap what was understood, once, before asking for upload)
  4. All required fields satisfied and already summarized (or summarization
     disabled by registry)
     -> action='recommend_upload'
  0. No user input yet
     -> action='wait'

UploadReadinessContract is computed every turn (not just on recommend_upload)
so it's always inspectable, per Upload Readiness Rules Registry.

Stall handling: if the conversation has run for >= stall_warning_after_turns
turns while still asking the same class of question, the rationale is
prefixed with the stable marker "[STALL_WARNING]" so response_writer_node
(Task 6) can detect it and vary its phrasing — WITHOUT falling back to a
hardcoded numbered menu (explicitly rejected earlier in this architecture).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from agentic.registries.registry_loader import (
    get_missing_required_fields,
    get_conversation_rules,
    get_upload_readiness_rules,
)
from agentic.schemas import (
    ConversationUnderstandingContract,
    ConversationPlan,
    UploadReadinessContract,
    ContradictionRecord,
)
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

STALL_MARKER = "[STALL_WARNING]"


def _unresolved_contradictions(cuc: ConversationUnderstandingContract) -> List[ContradictionRecord]:
    return [c for c in cuc.contradictions if not c.resolved]


def _compute_upload_readiness(
    missing_field_paths: List[str],
    unresolved: List[ContradictionRecord],
    turn: int,
) -> UploadReadinessContract:
    rules = get_upload_readiness_rules()
    ready = True
    if rules.all_required_fields_satisfied and missing_field_paths:
        ready = False
    if rules.no_unresolved_contradictions and unresolved:
        ready = False
    return UploadReadinessContract(ready=ready, missing_fields=missing_field_paths, evaluated_at_turn=turn)


def _pick_ask_target(
    missing_field_paths: List[str],
    previous_plan: Optional[ConversationPlan],
    avoid_repeat_questions: bool,
) -> str:
    """Choose which missing field to ask about this turn.

    If the previous turn already asked about the same field and made no
    progress (it's still missing) and avoid_repeat_questions is set, rotate
    to a different missing field when one is available. If it's the only
    missing field left, there's nothing to rotate to — repetition is
    unavoidable and is handled by the stall marker + response_writer's
    rewording instead.
    """
    if not missing_field_paths:
        raise ValueError("_pick_ask_target called with no missing fields")

    first = missing_field_paths[0]
    if (
        avoid_repeat_questions
        and previous_plan is not None
        and previous_plan.action == "ask"
        and previous_plan.target_field == first
        and len(missing_field_paths) > 1
    ):
        return missing_field_paths[1]
    return first


def decide(
    cuc: ConversationUnderstandingContract,
    previous_plan: Optional[ConversationPlan],
    turn: int,
) -> Tuple[ConversationPlan, UploadReadinessContract]:
    """Pure decision function — no I/O beyond the registry reads, fully
    unit-testable independent of LangGraph state plumbing."""
    rules = get_conversation_rules()

    # 'wait' only when there is GENUINELY nothing to work with — no turns AND
    # no CUC content. Gating purely on turn (=len(state.messages)) is wrong:
    # /api/agent/seed injects a fully-populated CUC directly via
    # graph.update_state() without ever touching state.messages, so turn==0
    # there despite the CUC being complete. Checking CUC content too avoids
    # that bypass path being misdiagnosed as "no input yet".
    cuc_has_content = cuc.goal.primary_intent not in ("", "general") or bool(cuc.goal.task_family)
    if turn <= 0 and not cuc_has_content:
        plan = ConversationPlan(action="wait", rationale="No user input yet.")
        readiness = _compute_upload_readiness([], [], turn)
        return plan, readiness

    missing_rules = get_missing_required_fields(cuc)
    missing_field_paths = [r.field for r in missing_rules]
    unresolved = _unresolved_contradictions(cuc)
    readiness = _compute_upload_readiness(missing_field_paths, unresolved, turn)

    stalled = turn >= rules.stall_warning_after_turns and bool(missing_field_paths)
    stall_prefix = f"{STALL_MARKER} " if stalled else ""

    # --- Priority 1: surface contradictions ---
    if unresolved and rules.surface_contradictions:
        target = unresolved[0]
        plan = ConversationPlan(
            action="confirm",
            target_field=target.field_path,
            rationale=(
                f"{stall_prefix}Contradiction on '{target.field_path}': previously understood as "
                f"{target.previous_value!r}, now stated as {target.new_value!r}. Ask the user to confirm."
            ),
            missing_required_fields=missing_field_paths,
        )
        return plan, readiness

    # --- Priority 2: required fields still missing ---
    if missing_field_paths:
        target_field = _pick_ask_target(missing_field_paths, previous_plan, rules.avoid_repeat_questions)
        plan = ConversationPlan(
            action="ask",
            target_field=target_field,
            rationale=f"{stall_prefix}Required field '{target_field}' is not yet filled.",
            missing_required_fields=missing_field_paths,
        )
        return plan, readiness

    # --- No missing fields, no unresolved contradictions ---
    already_summarized = previous_plan is not None and previous_plan.action == "summarize"
    if rules.always_summarize_before_upload and not already_summarized:
        plan = ConversationPlan(
            action="summarize",
            rationale="All required information gathered; summarizing before requesting upload.",
            missing_required_fields=[],
        )
        return plan, readiness

    plan = ConversationPlan(
        action="recommend_upload",
        rationale="Manifest minimally complete; advising the user to upload their dataset.",
        missing_required_fields=[],
    )
    return plan, readiness


def conversation_planner_node(state: MasterAgentState) -> dict:
    """LangGraph node wrapper around decide().

    Reads:  state.cuc (merged by contract_manager_node), state.conversation_plan
            (previous turn's decision, for repeat-question/summarize-once logic),
            state.messages (turn count).
    Writes: state.conversation_plan, state.upload_readiness, active_agent handoff.
    """
    turn = len(state.messages)
    plan, readiness = decide(state.cuc, state.conversation_plan, turn)

    logger.info(f"[ConversationPlanner] turn={turn} action={plan.action} "
                f"target_field={plan.target_field} ready={readiness.ready}")

    next_agent = "upload_gate" if plan.action == "recommend_upload" else "response_writer"
    return {
        "conversation_plan": plan.model_dump(),
        "upload_readiness": readiness.model_dump(),
        "active_agent": next_agent,
    }
