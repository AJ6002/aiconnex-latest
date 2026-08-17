# tests/test_memory_policy_engine.py
import pytest
from agentic.memory.events import make_event
from agentic.memory.policy_engine import MemoryPolicyEngine, RetentionDecision
from agentic.memory.memory_layers import (
    SessionMemory,
    EntityMemory,
    ProceduralMemory,
    DecisionMemory,
    MemoryBank,
)


@pytest.mark.parametrize("event_type,expected_action,expected_layer", [
    ("DatasetCompiled", "retain_summary", "entity"),
    ("ModelTrained", "retain_summary", "entity"),
    ("ModelEvaluated", "retain_summary", "entity"),
    ("ClarificationAnswered", "retain_full", "decision"),
    ("ClarificationRequested", "discard", None),
    ("ConversationParsed", "retain_summary", "session"),
    ("PlanCreated", "retain_summary", "session"),
    ("ArchiveUploaded", "retain_summary", "session"),
    ("ArchiveDiscovered", "retain_summary", "session"),
    ("ParserSelected", "retain_summary", "session"),
])
def test_policy_decisions_for_known_event_types(event_type, expected_action, expected_layer):
    engine = MemoryPolicyEngine()
    evt = make_event(event_type, "wf_1", "agent", "subject", "sub_1", {})
    decision = engine.decide(evt)
    assert isinstance(decision, RetentionDecision)
    assert decision.action == expected_action
    assert decision.target_layer == expected_layer


def test_failure_outcome_overrides_to_procedural_regardless_of_type():
    engine = MemoryPolicyEngine()
    evt = make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_1", {}, outcome="failure")
    decision = engine.decide(evt)
    assert decision.action == "aggregate"
    assert decision.target_layer == "procedural"


def test_unknown_event_type_discards_safely():
    engine = MemoryPolicyEngine()
    evt = make_event("SomeFutureEventType", "wf_1", "agent", "subject", "sub_1", {})
    decision = engine.decide(evt)
    assert decision.action == "discard"


def test_memory_bank_to_context_is_json_serializable():
    import json
    bank = MemoryBank(
        session={"wf_1": SessionMemory(workflow_id="wf_1", last_intent="train_rul", steps_run=["scout"], status="running")},
        entities={"ds_1": EntityMemory(subject_id="ds_1", subject_type="dataset", observations=[{"rows": 100}])},
        procedures=[ProceduralMemory(pattern="compile_timeout", outcome="failure", occurrences=2)],
        decisions=[DecisionMemory(decision_id="dec_1", question="mode?", answer="auto", workflow_id="wf_1")],
    )
    ctx = bank.to_context()
    # Must not raise - proves plain-dict serializability for MasterAgentState.memory_context
    json.dumps(ctx)
    assert ctx["session"]["wf_1"]["last_intent"] == "train_rul"
    assert ctx["entities"]["ds_1"]["observations"][0]["rows"] == 100
    assert ctx["procedures"][0]["occurrences"] == 2
    assert ctx["decisions"][0]["answer"] == "auto"
