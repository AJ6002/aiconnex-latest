# tests/test_planning_plan_validator.py
import pytest
from agentic.schemas import ExecutionPlan, TaskStep
from agentic.planning.plan_validator import PlanValidator


def test_valid_plan_passes_through():
    validator = PlanValidator()
    raw = [
        {"step_id": "step_1", "target_agent": "scout", "task": "Discover archive"},
        {"step_id": "step_2", "target_agent": "platform", "task": "Train model"},
    ]
    plan = validator.validate(raw, source_intent="train_rul")
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.steps) == 2
    assert plan.steps[0].target_agent == "scout"
    assert plan.source_intent == "train_rul"


def test_invalid_agent_step_is_dropped():
    validator = PlanValidator()
    raw = [
        {"step_id": "step_1", "target_agent": "scout", "task": "Discover archive"},
        {"step_id": "step_2", "target_agent": "not_a_real_agent", "task": "Do something invalid"},
    ]
    plan = validator.validate(raw, source_intent="compile_zip")
    assert len(plan.steps) == 1
    assert plan.steps[0].target_agent == "scout"


def test_all_invalid_steps_fall_back_to_safe_default():
    validator = PlanValidator()
    raw = [{"step_id": "step_1", "target_agent": "rogue_agent", "task": "bad"}]
    plan = validator.validate(raw, source_intent="general")
    assert len(plan.steps) == 1
    assert plan.steps[0].target_agent == "scout"


def test_empty_input_falls_back_to_safe_default():
    validator = PlanValidator()
    plan = validator.validate([], source_intent="general")
    assert len(plan.steps) == 1
    assert plan.steps[0].target_agent == "scout"
