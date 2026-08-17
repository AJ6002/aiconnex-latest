# tests/test_clarification_node.py
"""
Tests for the real Clarification Node (replaces the previously hardcoded
stub that always asked "Which processing mode would you like?" regardless
of what was actually ambiguous). Verifies real_clarification_node calls the
real ClarificationGenerator with the actual CUC, rather than using fixed
strings.
"""
import pytest
from unittest.mock import patch

from agentic.state import MasterAgentState
from agentic.schemas import ConversationUnderstandingContract
from agentic.parser.clarification_node import real_clarification_node


def test_clarification_node_uses_real_generator_questions_not_hardcoded():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "general"}, observed={"mentioned_files": []}),
    )

    captured_interrupt_payload = {}

    def _fake_interrupt(payload):
        captured_interrupt_payload.update(payload)
        return "Automatic Pipeline"

    with patch("agentic.parser.clarification_node.interrupt", side_effect=_fake_interrupt):
        res = real_clarification_node(state)

    # The questions passed to interrupt() must come from ClarificationGenerator,
    # not the old hardcoded "Which processing mode would you like?" string.
    assert "questions" in captured_interrupt_payload
    assert captured_interrupt_payload["questions"]
    assert "Which processing mode would you like?" not in captured_interrupt_payload["questions"]

    assert res["active_agent"] == "planner"
    assert res["confidence_score"] == 1.0
    assert res["cuc"]["planning_hints"]["user_choice"] == "Automatic Pipeline"


def test_clarification_node_questions_reflect_missing_files():
    """A CUC missing mentioned_files should get a question about which file/archive to use."""
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "train_rul"}, observed={"mentioned_files": []}),
    )

    with patch("agentic.parser.clarification_node.interrupt", return_value="ok") as mock_interrupt:
        real_clarification_node(state)

    payload = mock_interrupt.call_args[0][0]
    assert any("file" in q.lower() or "archive" in q.lower() for q in payload["questions"])
