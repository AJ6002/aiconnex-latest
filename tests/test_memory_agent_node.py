# tests/test_memory_agent_node.py
import pytest
from agentic.state import MasterAgentState
from agentic.schemas import ConversationUnderstandingContract, DatasetIntelligenceContract
from agentic.memory.event_store import get_event_store, reset_event_store
from agentic.memory.events import make_event
from agentic.memory.memory_agent import real_memory_agent_node


@pytest.fixture(autouse=True)
def _clean_store():
    reset_event_store()
    yield
    reset_event_store()


def test_write_path_records_dataset_compiled_and_returns_entity():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "compile_zip"}),
        dic=DatasetIntelligenceContract(
            dataset_identity={"name": "NASA FD001", "family": "Aircraft Engine"},
            compiled_dataset={"rows": 26898, "columns": 253, "tables": 1},
        ),
    )
    res = real_memory_agent_node(state)

    assert res["active_agent"] == "evaluator"
    bank = res["memory_context"]["memory_bank"]
    assert len(bank["entities"]) == 1
    entity = list(bank["entities"].values())[0]
    assert entity["observations"][0]["rows"] == 26898
    assert "last_saved_session" in res["memory_context"]


def test_write_path_records_model_trained_when_platform_already_ran():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "train_rul"}),
        dic=DatasetIntelligenceContract(
            dataset_identity={"name": "NASA FD001", "family": "Aircraft Engine"},
            compiled_dataset={"rows": 26898, "columns": 253, "tables": 1},
        ),
        plan_steps=[
            {"step_id": "step_1", "target_agent": "scout", "task": "compile"},
            {"step_id": "step_2", "target_agent": "platform", "task": "train"},
            {"step_id": "step_3", "target_agent": "memory", "task": "persist"},
        ],
        current_step_index=2,
    )
    res = real_memory_agent_node(state)
    store = get_event_store()
    types = [e.event_type for e in store.all()]
    assert "ModelTrained" in types
    assert "ModelEvaluated" in types


def test_read_path_does_not_duplicate_existing_events():
    store = get_event_store()
    store.append(make_event("DatasetCompiled", "wf_existing", "scout", "dataset", "ds_seed", {"rows": 500}))
    before_count = len(store.by_subject("ds_seed"))

    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(
            conversation={"session_id": "wf_existing"},
            goal={"primary_intent": "query_status"},
        ),
    )
    res = real_memory_agent_node(state)

    after_count = len(store.by_subject("ds_seed"))
    assert after_count == before_count  # no duplicate event appended on read path

    bank = res["memory_context"]["memory_bank"]
    assert "ds_seed" in bank["entities"]
    assert bank["entities"]["ds_seed"]["observations"][0]["rows"] == 500


def test_clarification_answer_is_recorded_as_decision_memory():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(
            goal={"primary_intent": "train_rul"},
            planning_hints={"user_choice": "Automatic Pipeline"},
        ),
    )
    res = real_memory_agent_node(state)
    bank = res["memory_context"]["memory_bank"]
    assert len(bank["decisions"]) == 1
    assert bank["decisions"][0]["answer"] == "Automatic Pipeline"


def test_default_state_produces_no_dataset_entity():
    state = MasterAgentState()
    res = real_memory_agent_node(state)
    bank = res["memory_context"]["memory_bank"]
    assert bank["entities"] == {}
    assert res["active_agent"] == "evaluator"


# --- Phase 5a.6 Task 3: semantic search on query_status read path ---

def test_query_status_returns_semantic_hits_for_matching_prompt():
    from agentic.memory.backends.factory import reset_semantic_backend

    reset_semantic_backend()

    # Write path first: compile a dataset so an Entity-layer fact exists,
    # which memory_builder.py mirrors into the semantic backend.
    write_state = MasterAgentState(
        cuc=ConversationUnderstandingContract(
            conversation={"session_id": "wf_semantic_1"},
            goal={"primary_intent": "compile_zip"},
        ),
        dic=DatasetIntelligenceContract(
            dataset_identity={"name": "NASA FD001", "family": "Aircraft Engine"},
            compiled_dataset={"rows": 26898, "columns": 253, "tables": 1},
        ),
    )
    real_memory_agent_node(write_state)

    # Read path: query_status with a matching prompt should surface semantic_hits.
    read_state = MasterAgentState(
        messages=[{"role": "user", "content": "what happened with the NASA FD001 dataset"}],
        cuc=ConversationUnderstandingContract(
            conversation={"session_id": "wf_semantic_1"},
            goal={"primary_intent": "query_status"},
        ),
    )
    res = real_memory_agent_node(read_state)

    assert "semantic_hits" in res["memory_context"]
    assert len(res["memory_context"]["semantic_hits"]) > 0
    # memory_bank structure is unaffected - still has the standard 4 keys.
    bank = res["memory_context"]["memory_bank"]
    assert set(bank.keys()) == {"session", "entities", "procedures", "decisions"}

    reset_semantic_backend()


def test_query_status_with_no_messages_returns_empty_semantic_hits():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "query_status"}),
    )
    res = real_memory_agent_node(state)
    assert res["memory_context"]["semantic_hits"] == []


def test_write_path_intent_does_not_populate_semantic_hits():
    state = MasterAgentState(
        cuc=ConversationUnderstandingContract(goal={"primary_intent": "compile_zip"}),
    )
    res = real_memory_agent_node(state)
    assert res["memory_context"]["semantic_hits"] == []
