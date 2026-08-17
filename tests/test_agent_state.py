# tests/test_agent_state.py
import pytest
from agentic.schemas import ConversationUnderstandingContract
from agentic.state import MasterAgentState


def test_master_agent_state_initialization():
    state = MasterAgentState(
        messages=[{"role": "user", "content": "Upload suyash2.zip"}],
        cuc=ConversationUnderstandingContract(
            goal={"primary_intent": "compile_zip"}
        ),
        active_agent="scout",
        current_step_index=0
    )
    assert state.active_agent == "scout"
    assert state.cuc.goal.primary_intent == "compile_zip"

    assert state.current_step_index == 0
