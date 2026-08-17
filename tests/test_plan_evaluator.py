"""
tests/test_plan_evaluator.py - Unit Tests for real PlanEvaluatorNode
====================================================================
Verifies:
  1. Gating on active interrupt_reason
  2. Quality validation for scout, platform, memory steps
  3. Step index advancement and active_agent resolution
"""

import pytest
from agentic.state import MasterAgentState
from agentic.schemas import (
    ConversationUnderstandingContract,
    Goal,
    DatasetIntelligenceContract,
    CompiledDatasetSummary,
    ScorerReport,
)
from agentic.nodes.plan_evaluator import real_plan_evaluator_node


def test_plan_evaluator_advances_index_on_success():
    state = MasterAgentState(
        plan_steps=[
            {"step_id": "step_1", "target_agent": "scout", "task": "compile zip"},
            {"step_id": "step_2", "target_agent": "platform", "task": "train RUL"},
            {"step_id": "step_3", "target_agent": "memory", "task": "persist"},
        ],
        current_step_index=0,
        dic=DatasetIntelligenceContract(
            compiled_dataset=CompiledDatasetSummary(rows=500, columns=10)
        )
    )
    res = real_plan_evaluator_node(state)
    assert res["current_step_index"] == 1
    assert res["active_agent"] == "platform"


def test_plan_evaluator_holds_pointer_on_interrupt():
    state = MasterAgentState(
        plan_steps=[
            {"step_id": "step_1", "target_agent": "scout", "task": "compile zip"},
            {"step_id": "step_2", "target_agent": "platform", "task": "train RUL"},
        ],
        current_step_index=0,
        interrupt_reason="strategy_choice"
    )
    res = real_plan_evaluator_node(state)
    assert res["current_step_index"] == 0
    assert res["active_agent"] == "scout"


def test_plan_evaluator_completion_on_final_step():
    state = MasterAgentState(
        plan_steps=[
            {"step_id": "step_1", "target_agent": "memory", "task": "persist"},
        ],
        current_step_index=0,
        memory_context={"memory_bank": {"sessions": 1}}
    )
    res = real_plan_evaluator_node(state)
    assert res["current_step_index"] == 1
    assert res["active_agent"] == "complete"
