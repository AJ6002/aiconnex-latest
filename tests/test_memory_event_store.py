# tests/test_memory_event_store.py
import pytest
from agentic.memory.events import make_event, BaseEvent
from agentic.memory.event_store import EventStore, get_event_store, reset_event_store


def test_make_event_populates_id_and_timestamp():
    evt = make_event(
        event_type="DatasetCompiled",
        workflow_id="wf_1",
        agent="scout",
        subject_type="dataset",
        subject_id="ds_1",
        payload={"rows": 100},
    )
    assert isinstance(evt, BaseEvent)
    assert evt.event_id.startswith("evt_")
    assert len(evt.timestamp) > 0
    assert evt.outcome == "success"
    assert evt.payload == {"rows": 100}


def test_make_event_custom_outcome():
    evt = make_event(
        event_type="RowParseWarning",
        workflow_id="wf_1",
        agent="scout",
        subject_type="dataset",
        subject_id="ds_1",
        payload={},
        outcome="failure",
    )
    assert evt.outcome == "failure"


def test_append_and_all_preserves_order():
    store = EventStore()
    e1 = make_event("ConversationParsed", "wf_1", "parser", "conversation", "wf_1", {})
    e2 = make_event("PlanCreated", "wf_1", "planner", "plan", "wf_1", {})
    store.append(e1)
    store.append(e2)
    events = store.all()
    assert [e.event_id for e in events] == [e1.event_id, e2.event_id]


def test_by_workflow_filters_correctly():
    store = EventStore()
    e1 = make_event("ConversationParsed", "wf_1", "parser", "conversation", "wf_1", {})
    e2 = make_event("ConversationParsed", "wf_2", "parser", "conversation", "wf_2", {})
    store.append(e1)
    store.append(e2)
    result = store.by_workflow("wf_1")
    assert len(result) == 1
    assert result[0].event_id == e1.event_id


def test_by_subject_filters_correctly():
    store = EventStore()
    e1 = make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_1", {})
    e2 = make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_2", {})
    store.append(e1)
    store.append(e2)
    result = store.by_subject("ds_2")
    assert len(result) == 1
    assert result[0].event_id == e2.event_id


def test_events_are_immutable_on_repeated_reads():
    store = EventStore()
    e1 = make_event("DatasetCompiled", "wf_1", "scout", "dataset", "ds_1", {"rows": 5})
    store.append(e1)
    first_read = store.all()
    second_read = store.all()
    assert first_read[0].payload == second_read[0].payload == {"rows": 5}


def test_clear_empties_the_store():
    store = EventStore()
    store.append(make_event("PlanCreated", "wf_1", "planner", "plan", "wf_1", {}))
    store.clear()
    assert store.all() == []


def test_reset_event_store_yields_empty_singleton():
    store1 = get_event_store()
    store1.append(make_event("PlanCreated", "wf_1", "planner", "plan", "wf_1", {}))
    assert len(get_event_store().all()) == 1

    reset_event_store()
    store2 = get_event_store()
    assert store2.all() == []
