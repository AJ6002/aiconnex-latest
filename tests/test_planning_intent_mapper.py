# tests/test_planning_intent_mapper.py
# Updated to reflect recipe-driven architecture:
# Platform steps are NOT in the initial plan template for any intent.
# They are enqueued dynamically after HITL recipe selection.
import pytest
from agentic.planning.intent_plan_mapper import IntentPlanMapper


def test_compile_zip_plan():
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("compile_zip")
    assert steps[0]["target_agent"] == "scout"
    assert steps[-1]["target_agent"] == "memory"


def test_train_rul_plan_has_no_platform():
    """Platform is NOT in the initial plan — it is appended after recipe selection."""
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("train_rul")
    agents = [s["target_agent"] for s in steps]
    assert "platform" not in agents
    assert agents[0] == "scout"
    assert agents[-1] == "memory"


def test_detect_anomalies_plan_has_no_platform():
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("detect_anomalies")
    agents = [s["target_agent"] for s in steps]
    assert "platform" not in agents
    assert agents[0] == "scout"


def test_query_status_plan_is_memory_only():
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("query_status")
    assert len(steps) == 1
    assert steps[0]["target_agent"] == "memory"


def test_unknown_intent_falls_back_to_scout_and_memory():
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("general")
    assert steps[0]["target_agent"] == "scout"

    steps_unknown = mapper.get_plan("totally_made_up_intent")
    assert steps_unknown[0]["target_agent"] == "scout"


def test_step_ids_are_unique_and_sequential():
    mapper = IntentPlanMapper()
    steps = mapper.get_plan("train_rul")
    ids = [s["step_id"] for s in steps]
    # train_rul now has 2 steps: scout + memory
    assert ids == ["step_1", "step_2"]
    assert len(set(ids)) == len(ids)  # all unique


def test_get_platform_steps_regression():
    mapper = IntentPlanMapper()
    steps = mapper.get_platform_steps("REGRESSION", "Predict TDS")
    agents = [s["target_agent"] for s in steps]
    assert "platform" in agents
    assert steps[0]["step_id"] == "platform_step_1"
    assert "Predict TDS" in steps[0]["task"]


def test_get_platform_steps_anomaly():
    mapper = IntentPlanMapper()
    steps = mapper.get_platform_steps("ANOMALY", "Detect Anomalies")
    agents = [s["target_agent"] for s in steps]
    assert "platform" in agents
    assert len(steps) >= 2
