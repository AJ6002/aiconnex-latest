"""
tests/test_event_store_idempotency.py - Idempotency Unit Test Suite for EventStore
==================================================================================
Verifies that exact duplicate domain events appended for the same workflow are skipped.
"""

import pytest
from agentic.memory.event_store import EventStore
from agentic.memory.events import make_event


def test_event_store_skips_identical_duplicate_events():
    store = EventStore(backend="memory")
    event1 = make_event(
        event_type="ConversationParsed",
        workflow_id="wf_1001",
        agent="memory",
        subject_type="conversation",
        subject_id="wf_1001",
        payload={"intent": "train_rul"},
    )
    event2 = make_event(
        event_type="ConversationParsed",
        workflow_id="wf_1001",
        agent="memory",
        subject_type="conversation",
        subject_id="wf_1001",
        payload={"intent": "train_rul"},
    )

    store.append(event1)
    assert len(store.all()) == 1

    # Appending identical event for same workflow must be skipped by _is_duplicate
    store.append(event2)
    assert len(store.all()) == 1


def test_event_store_allows_distinct_events():
    store = EventStore(backend="memory")
    event1 = make_event(
        event_type="ConversationParsed",
        workflow_id="wf_1001",
        agent="memory",
        subject_type="conversation",
        subject_id="wf_1001",
        payload={"intent": "train_rul"},
    )
    event2 = make_event(
        event_type="PlanCreated",
        workflow_id="wf_1001",
        agent="memory",
        subject_type="plan",
        subject_id="wf_1001",
        payload={"steps": 2},
    )

    store.append(event1)
    store.append(event2)
    assert len(store.all()) == 2
