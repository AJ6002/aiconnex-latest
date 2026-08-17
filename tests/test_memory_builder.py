# tests/test_memory_builder.py
import pytest
from agentic.memory.events import make_event
from agentic.memory.policy_engine import MemoryPolicyEngine
from agentic.memory.memory_builder import MemoryBuilder


def _fixture_log():
    return [
        make_event("ConversationParsed", "wf_1", "parser", "conversation", "wf_1", {"intent": "train_rul"}),
        make_event("PlanCreated", "wf_1", "planner", "plan", "wf_1", {"steps": 3}),
        make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_nasa_fd001", {"rows": 26898}),
        make_event("ClarificationAnswered", "wf_1", "clarification", "decision", "wf_1", {"question": "mode?", "answer": "auto"}),
        make_event("ArchiveUploaded", "wf_1", "scout", "conversation", "wf_1", {}, outcome="failure"),
    ]


def test_dataset_compiled_lands_in_entities():
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(_fixture_log())
    assert "ds_nasa_fd001" in bank.entities
    assert bank.entities["ds_nasa_fd001"].observations[0]["rows"] == 26898


def test_clarification_answered_lands_in_decisions():
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(_fixture_log())
    assert len(bank.decisions) == 1
    assert bank.decisions[0].answer == "auto"


def test_conversation_parsed_lands_in_session():
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(_fixture_log())
    assert "wf_1" in bank.session
    assert "ConversationParsed" in bank.session["wf_1"].steps_run
    assert "PlanCreated" in bank.session["wf_1"].steps_run


def test_failure_event_lands_in_procedures():
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(_fixture_log())
    assert len(bank.procedures) == 1
    assert bank.procedures[0].pattern == "ArchiveUploaded"
    assert bank.procedures[0].outcome == "failure"
    assert bank.procedures[0].occurrences == 1


def test_duplicate_failure_patterns_are_aggregated_not_duplicated():
    log = [
        make_event("ArchiveUploaded", "wf_1", "scout", "conversation", "wf_1", {}, outcome="failure"),
        make_event("ArchiveUploaded", "wf_2", "scout", "conversation", "wf_2", {}, outcome="failure"),
    ]
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(log)
    assert len(bank.procedures) == 1
    assert bank.procedures[0].occurrences == 2


def test_build_is_idempotent():
    builder = MemoryBuilder(MemoryPolicyEngine())
    log = _fixture_log()
    bank1 = builder.build(log)
    bank2 = builder.build(log)
    assert bank1.to_context() == bank2.to_context()


def test_discarded_event_types_are_dropped():
    log = [make_event("ClarificationRequested", "wf_1", "clarification", "decision", "wf_1", {})]
    builder = MemoryBuilder(MemoryPolicyEngine())
    bank = builder.build(log)
    assert bank.decisions == []
    assert bank.entities == {}


# --- Phase 5a.6 Task 2: semantic backend mirroring (Entity layer only) ---

class _SpyBackend:
    """Test spy implementing SemanticMemoryBackend to record add() calls."""

    def __init__(self):
        self.add_calls = []

    def add(self, text, metadata):
        self.add_calls.append({"text": text, "metadata": metadata})

    def search(self, query, limit=5):
        return []


def test_entity_events_mirror_into_semantic_backend():
    spy = _SpyBackend()
    builder = MemoryBuilder(MemoryPolicyEngine(), semantic_backend=spy)
    log = [
        make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_nasa_fd001", {"rows": 26898}),
    ]
    builder.build(log)
    assert len(spy.add_calls) == 1
    assert spy.add_calls[0]["metadata"]["subject_id"] == "ds_nasa_fd001"


def test_decision_and_procedural_events_never_call_semantic_backend():
    spy = _SpyBackend()
    builder = MemoryBuilder(MemoryPolicyEngine(), semantic_backend=spy)
    log = [
        make_event("ClarificationAnswered", "wf_1", "clarification", "decision", "wf_1", {"question": "mode?", "answer": "auto"}),
        make_event("ArchiveUploaded", "wf_1", "scout", "conversation", "wf_1", {}, outcome="failure"),
        make_event("ConversationParsed", "wf_1", "parser", "conversation", "wf_1", {"intent": "train_rul"}),
    ]
    builder.build(log)
    assert spy.add_calls == []


def test_semantic_backend_defaults_to_get_semantic_backend_singleton():
    from agentic.memory.backends.factory import get_semantic_backend, reset_semantic_backend
    from agentic.memory.backends.local_fake import LocalFakeBackend

    reset_semantic_backend()
    builder = MemoryBuilder(MemoryPolicyEngine())
    assert isinstance(builder.semantic_backend, LocalFakeBackend)
    assert builder.semantic_backend is get_semantic_backend()
    reset_semantic_backend()
