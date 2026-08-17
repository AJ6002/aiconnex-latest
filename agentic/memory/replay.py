"""
aiconnex_agent/memory/replay.py
==================================
Replayability layer. Because memory is event-sourced (MemoryBuilder is a
pure, idempotent projection - see memory_builder.py), it is always a
re-derivable product of the event log + policy. This module gives that
property a small, explicit public API:

  - rebuild_memory_from_events - the canonical "rebuild memory from the log"
    entry point. Delete the materialized MemoryBank at any time; this
    reproduces it exactly from events alone.
  - replay_workflow            - "what happened during this one run" -
    the ordered event slice for a single workflow_id.
  - explain_fact                - "why does this memory fact exist" -
    provenance: every event that touched a given subject, across all
    workflows that ever mentioned it.

Zero LLM calls, zero I/O - pure functions over the event log.
"""

from __future__ import annotations

from typing import List, Optional

from agentic.memory.events import BaseEvent
from agentic.memory.event_store import EventStore
from agentic.memory.policy_engine import MemoryPolicyEngine
from agentic.memory.memory_builder import MemoryBuilder
from agentic.memory.memory_layers import MemoryBank


def rebuild_memory_from_events(
    events: List[BaseEvent],
    policy: Optional[MemoryPolicyEngine] = None,
) -> MemoryBank:
    """Rebuild a MemoryBank from an event log. Deterministic and idempotent.

    Passing a different policy re-derives memory under different retention
    rules without touching the underlying event log - proving memory is a
    policy-dependent view of the log, not independently stored truth.
    """
    active_policy = policy or MemoryPolicyEngine()
    builder = MemoryBuilder(active_policy)
    return builder.build(events)


def replay_workflow(store: EventStore, workflow_id: str) -> List[BaseEvent]:
    """Return the ordered event slice for a single workflow - 'what happened here'."""
    return store.by_workflow(workflow_id)


def explain_fact(store: EventStore, subject_id: str) -> List[BaseEvent]:
    """Return every event about one subject, across all workflows - provenance/audit trail."""
    return store.by_subject(subject_id)
