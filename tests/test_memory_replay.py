# tests/test_memory_replay.py
import pytest
from agentic.memory.events import make_event
from agentic.memory.event_store import EventStore
from agentic.memory.policy_engine import MemoryPolicyEngine, RetentionDecision
from agentic.memory.replay import (
    rebuild_memory_from_events,
    replay_workflow,
    explain_fact,
)


def _fixture_log():
    return [
        make_event("ConversationParsed", "wf_1", "parser", "conversation", "wf_1", {"intent": "train_rul"}),
        make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_nasa_fd001", {"rows": 26898}),
        make_event("ModelTrained", "wf_1", "platform", "model", "model_ds_nasa_fd001", {}),
        make_event("DatasetCompiled", "wf_2", "scout", "dataset", "ds_nasa_fd001", {"rows": 26900}),
    ]


def test_rebuild_is_deterministic_across_calls():
    log = _fixture_log()
    bank1 = rebuild_memory_from_events(log)
    bank2 = rebuild_memory_from_events(log)
    assert bank1.to_context() == bank2.to_context()


def test_rebuild_reproduces_bank_after_deletion():
    log = _fixture_log()
    bank_original = rebuild_memory_from_events(log)
    original_ctx = bank_original.to_context()

    # Simulate "delete materialized memory" then rebuild from the log alone.
    del bank_original
    bank_rebuilt = rebuild_memory_from_events(log)
    assert bank_rebuilt.to_context() == original_ctx


def test_replay_workflow_returns_only_that_workflows_events_in_order():
    store = EventStore()
    for evt in _fixture_log():
        store.append(evt)

    events = replay_workflow(store, "wf_1")
    assert len(events) == 3
    assert [e.event_type for e in events] == ["ConversationParsed", "DatasetCompiled", "ModelTrained"]


def test_explain_fact_returns_provenance_for_a_subject():
    store = EventStore()
    for evt in _fixture_log():
        store.append(evt)

    provenance = explain_fact(store, "ds_nasa_fd001")
    assert len(provenance) == 2
    assert all(e.subject_id == "ds_nasa_fd001" for e in provenance)
    # Provenance spans both workflows that touched this subject.
    assert {e.workflow_id for e in provenance} == {"wf_1", "wf_2"}


class _DiscardCompiledPolicy(MemoryPolicyEngine):
    """Test-only policy: DatasetCompiled is discarded instead of retained."""
    def decide(self, event):
        if event.event_type == "DatasetCompiled":
            return RetentionDecision(action="discard", target_layer=None)
        return super().decide(event)


def test_policy_change_rebuilds_bank_without_the_discarded_entity():
    log = _fixture_log()
    bank_default = rebuild_memory_from_events(log)
    assert "ds_nasa_fd001" in bank_default.entities

    bank_new_policy = rebuild_memory_from_events(log, policy=_DiscardCompiledPolicy())
    assert "ds_nasa_fd001" not in bank_new_policy.entities
