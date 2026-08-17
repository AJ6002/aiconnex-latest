"""
aiconnex_agent/parser/clarification_node.py
==============================================
Real Clarification Node: replaces the previously hardcoded stub, which
always asked the same fixed question regardless of what was actually
ambiguous about the request. This node uses the real ClarificationGenerator
(sub-module 6) to compose targeted questions from the actual CUC gaps, then
pauses the graph via LangGraph's interrupt() until the user answers.

chatbot_5jul fix: interrupt() now emits a typed InterruptPayload with
interrupt_type="clarification" so the frontend SSE adapter can distinguish
clarification events from strategy_choice events uniformly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.types import interrupt

from agentic.state import MasterAgentState
from agentic.parser.clarification_generator import ClarificationGenerator
from agentic.schemas import InterruptPayload, InterruptOption

logger = logging.getLogger(__name__)

# Module singleton, consistent with conversation_parser.py's pattern.
clarification_generator = ClarificationGenerator()


def real_clarification_node(state: MasterAgentState) -> Dict[str, Any]:
    """Real Clarification Node: real, CUC-derived questions instead of a hardcoded one.

    Emits a typed InterruptPayload(interrupt_type='clarification') so the
    frontend SSE adapter and assistant-ui can render clarification questions
    distinctly from strategy_choice interrupts.
    """
    logger.info("[ClarificationNode] Executing real HITL clarification")

    questions = clarification_generator.generate(state.cuc)

    options = []
    goal = state.cuc.goal if hasattr(state.cuc, "goal") else {}
    intent = goal.primary_intent if hasattr(goal, "primary_intent") else (goal.get("primary_intent") if isinstance(goal, dict) else "general")
    if intent in ("general", "unknown", ""):
        options = [
            InterruptOption(option_id="compile", label="Compile Dataset (.zip)", description="Upload and compile multi-table archive"),
            InterruptOption(option_id="rul", label="Predict Remaining Useful Life (RUL)", description="Time-to-failure regression modeling"),
            InterruptOption(option_id="anomaly", label="Detect Sensor Anomalies", description="Unsupervised anomaly detection on SCADA telemetry"),
        ]

    payload = InterruptPayload(
        interrupt_type="clarification",
        questions=questions,
        options=options,
        reason="Parser confidence below 0.85 or required CUC fields missing",
    )

    user_answer = interrupt(payload.model_dump())

    cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else state.cuc.dict()
    hints = dict(cuc_dict.get("planning_hints") or {})
    hints["user_choice"] = user_answer
    cuc_dict["planning_hints"] = hints

    # Append the user's clarification answer to the message history so that
    # conversation_parser_node re-extracts from the NEW answer on the next loop.
    # Without this the parser would re-read the original message, re-produce the
    # same low-confidence CUC, and clarify again forever (repeat-question bug).
    result: Dict[str, Any] = {
        "cuc": cuc_dict,
        "active_agent": "planner",
        "confidence_score": 1.0,
    }
    if isinstance(user_answer, str) and user_answer.strip():
        # messages has no LangGraph reducer, so returning a list REPLACES it.
        # Build the full appended history explicitly to preserve prior turns.
        result["messages"] = list(state.messages) + [
            {"role": "user", "content": user_answer.strip()}
        ]
    return result
