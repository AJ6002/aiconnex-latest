# tests/test_planning_engine_node.py
import pytest
from agentic.state import MasterAgentState
from agentic.schemas import ConversationUnderstandingContract
from agentic.planning.planning_engine import real_planning_engine_node


@pytest.mark.parametrize("intent,expected_first_agent,expected_len", [
    ("compile_zip", "scout", 2),
    ("train_rul", "scout", 2),      # scout + memory (platform enqueued after HITL)
    ("detect_anomalies", "scout", 2),  # scout + memory
    ("query_status", "memory", 1),
    ("general", "scout", 2),        # fallback now also has memory step
])
def test_planning_engine_routes_by_intent(intent, expected_first_agent, expected_len):
    state = MasterAgentState(cuc=ConversationUnderstandingContract(goal={"primary_intent": intent}))
    res = real_planning_engine_node(state)

    assert len(res["plan_steps"]) == expected_len
    assert res["plan_steps"][0]["target_agent"] == expected_first_agent
    assert res["current_step_index"] == 0
    assert res["active_agent"] == expected_first_agent


def test_planning_engine_handles_missing_intent_gracefully():
    state = MasterAgentState()  # no cuc.goal set at all
    res = real_planning_engine_node(state)
    assert len(res["plan_steps"]) >= 1
    assert res["active_agent"] in {"scout", "platform", "memory"}
