"""
hitl_node (Task 13) — LangGraph node wrapping the dataset-driven HITL flow.
=============================================================================
Converts the previously-external `hitl_flow.process_hitl_turn()` loop (called
by terminal_runner) into a real LangGraph node that uses interrupt()/resume
for user interaction, matching the pattern the pre-upload chain already uses
(response_writer_node, upload_gate_node).

Design (matches the multi-interrupt-per-node pattern LangGraph supports):
  - First entry: contract is None → call process_hitl_turn("[HITL_START]")
    to build the recipe-catalog opening from the DIC that Scout produced.
  - Interrupt with the opening message, wait for user's first answer.
  - On resume: call process_hitl_turn(user_answer, contract=...) which does
    the real LLM extract + merge + apply_recipe_context.
  - Loop until contract.hitl_complete = True (recipe picked with confidence).
  - Exit → hand off to pipeline_lock_node with the finalised contract.

Each interrupt() checkpoints state via LangGraph's SqliteSaver, so a process
restart mid-conversation resumes cleanly from the last user prompt.

Reads:  state.dic (from exploration_synthesizer), state.session_id
Writes: state.hitl_contract, state.response_text
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List

from langgraph.types import interrupt

from agentic.schemas import InterruptPayload
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


# ─── Defensive sys.path setup ────────────────────────────────────────────────
# chatbot/backend/ isn't on the aiconnex_agent import path by default; do the
# same insertion terminal_runner.py does so we can import hitl_flow / hitl_schemas.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CHATBOT_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _CHATBOT_BACKEND not in sys.path:
    sys.path.insert(0, _CHATBOT_BACKEND)


def _dic_as_dict(state_dic: Any) -> Dict[str, Any]:
    """Normalize state.dic (Pydantic model OR dict OR None) to a plain dict
    that hitl_extraction.build_hitl_system_prompt can consume."""
    if state_dic is None:
        return {}
    if hasattr(state_dic, "model_dump"):
        return state_dic.model_dump()
    if isinstance(state_dic, dict):
        return dict(state_dic)
    return {}


def _hydrate_contract(raw: Any):
    """Convert whatever's in state.hitl_contract to a real HITLContract, or None."""
    if raw is None:
        return None
    from hitl_schemas import HITLContract  # lazy, after sys.path insert
    if isinstance(raw, HITLContract):
        return raw
    if isinstance(raw, dict):
        return HITLContract.model_validate(raw)
    if hasattr(raw, "model_dump"):
        return HITLContract.model_validate(raw.model_dump())
    return None


def _interrupt_payload(message: str, turn_count: int) -> Dict[str, Any]:
    return InterruptPayload(
        interrupt_type="clarification",
        questions=[message],
        options=[],
        reason=f"HITL turn {turn_count}",
    ).model_dump()


def hitl_node(state: MasterAgentState) -> Dict[str, Any]:
    """Task 13: interactive HITL as a real LangGraph node.

    Runs the process_hitl_turn loop with interrupt() at each user-input
    boundary. Exits when the contract's hitl_complete flag flips true.
    """
    logger.info("[HITL] Starting")

    from hitl_flow import process_hitl_turn  # lazy, after sys.path insert

    session_id = state.session_id
    dic_context = _dic_as_dict(state.dic)
    contract = _hydrate_contract(state.hitl_contract)

    history: List[Dict[str, str]] = []

    # ── Step 1: send the opening (recipe-catalog menu built from real DIC) ─────
    if contract is None or contract.turn_count == 0:
        opening_result = process_hitl_turn(
            message="[HITL_START]",
            session_id=session_id,
            dic_context=dic_context,
            contract=None,
            history=history,
        )
        contract = opening_result["contract"]
        message = opening_result["reply"]
        logger.info(
            f"[HITL] Sending opening menu with "
            f"{len(dic_context.get('recipes', []))} recipes"
        )
    else:
        # Re-entry from a resumed checkpoint after a process restart mid-HITL.
        # We don't know exactly which question was pending, so re-prompt with
        # the last known reply seed — the LLM (or the recipe-aware fallback)
        # will re-render the appropriate follow-up on the next process_hitl_turn.
        message = (
            "I'd like to pick up where we left off. Could you tell me which "
            "analytical objective you'd like to pursue, or refine the one we discussed?"
        )
        logger.info(f"[HITL] Resuming from checkpoint (turn_count={contract.turn_count})")

    # ── Step 2: interactive loop — interrupt/process until complete ───────────
    max_turns = 20  # Safety bound; a well-behaved LLM converges in 1-4 turns
    while not contract.hitl_complete and contract.turn_count < max_turns:
        user_answer = interrupt(_interrupt_payload(message, contract.turn_count))

        answer_str = str(user_answer or "").strip()
        history.append({"role": "user", "content": answer_str})
        logger.info(f"[HITL] Turn {contract.turn_count} — user answer: {answer_str[:80]!r}")

        turn_result = process_hitl_turn(
            message=answer_str,
            session_id=session_id,
            dic_context=dic_context,
            contract=contract,
            history=history,
        )
        contract = turn_result["contract"]
        message = turn_result["reply"]
        history.append({"role": "assistant", "content": message})

        logger.info(
            f"[HITL] Post-turn state — recipe={contract.selected_recipe_id!r}, "
            f"complete={contract.hitl_complete}"
        )

    if not contract.hitl_complete:
        logger.warning(
            f"[HITL] Hit max_turns={max_turns} without completion — exiting with "
            f"partial contract; pipeline_lock will refuse to lock"
        )

    return {
        "hitl_contract": contract.model_dump(),
        "response_text": message,
        "active_agent": "pipeline_lock",
    }
