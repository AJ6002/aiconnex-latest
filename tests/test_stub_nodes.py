# tests/test_stub_nodes.py
import pytest
from unittest.mock import patch
from agentic.state import MasterAgentState
from agentic.nodes.stub_nodes import (
    stub_conversation_parser_node,
    stub_planning_engine_node,
    stub_scout_agent_node,
)


def test_stub_conversation_parser_node():
    state = MasterAgentState(messages=[{"role": "user", "content": "compile data"}])
    res = stub_conversation_parser_node(state)
    assert res["active_agent"] == "planner"
    assert res["confidence_score"] >= 0.85
    assert res["cuc"]["goal"]["primary_intent"] == "compile_zip"


def test_stub_planning_engine_node():
    # Default MasterAgentState() has no primary_intent -> resolves to "general"
    # which the real Planning Engine maps to scout discovery + memory (2 steps).
    state = MasterAgentState()
    res = stub_planning_engine_node(state)
    assert len(res["plan_steps"]) == 2
    assert res["plan_steps"][0]["target_agent"] == "scout"
    assert res["active_agent"] == "scout"


def test_stub_scout_agent_node_flags_missing_upload_path():
    """Delegates to the real Scout node (Phase 5b). With no upload_path set,
    Scout must flag via a real clarification interrupt (Gap 1 safety net) and
    route back to 'scout' — NOT 'evaluator' — so the graph does not advance
    the plan with an empty/fake DIC. (Bug #1 fix verification.)"""
    state = MasterAgentState(plan_steps=[{"target_agent": "scout", "step_id": "step_1"}])
    with patch("agentic.scout.scout_node.interrupt", return_value="ok") as mock_interrupt:
        res = stub_scout_agent_node(state)
    assert mock_interrupt.called
    assert "no dataset file" in mock_interrupt.call_args[0][0]["questions"][0]
    # Bug #1 fix: must route back to scout (not evaluator) and set interrupt_reason
    assert res["active_agent"] == "scout"
    assert res["interrupt_reason"] == "missing_upload_path"
