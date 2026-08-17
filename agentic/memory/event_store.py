"""
aiconnex_agent/memory/event_store.py
======================================
Append-only Event Store. Default backend is an in-memory list (fast,
deterministic, zero I/O - used by tests and the LangGraph node by default).
An optional "jsonl" backend appends each event as a line of JSON to a file
for durable persistence across process restarts.

Events are never mutated or deleted once appended - memory is rebuilt by
re-projecting the log (see memory_builder.py / replay.py), never by editing
history in place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from agentic.memory.events import BaseEvent


class EventStore:
    """Append-only log of BaseEvent records."""

    def __init__(self, backend: str = "memory", path: Optional[str] = None):
        self.backend = backend
        self.path = Path(path) if path else None
        self._events: List[BaseEvent] = []

        if self.backend == "jsonl" and self.path and self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._events.append(BaseEvent(**json.loads(line)))

    def _is_duplicate(self, event: BaseEvent) -> bool:
        """Check if an identical domain event was already appended for this workflow."""
        for e in reversed(self._events):
            if (
                e.workflow_id == event.workflow_id
                and e.event_type == event.event_type
                and e.subject_type == event.subject_type
                and e.subject_id == event.subject_id
                and e.payload == event.payload
            ):
                return True
        return False

    def append(self, event: BaseEvent) -> None:
        """Append one event to the log. Skips exact duplicate appends for idempotency."""
        if self._is_duplicate(event):
            return
        self._events.append(event)
        if self.backend == "jsonl" and self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")


    def all(self) -> List[BaseEvent]:
        """Return all recorded events in insertion order."""
        return list(self._events)

    def by_workflow(self, workflow_id: str) -> List[BaseEvent]:
        """Return the ordered event slice belonging to one workflow."""
        return [e for e in self._events if e.workflow_id == workflow_id]

    def by_subject(self, subject_id: str) -> List[BaseEvent]:
        """Return all events recorded about one subject (dataset/model/etc.)."""
        return [e for e in self._events if e.subject_id == subject_id]

    def clear(self) -> None:
        """Empty the in-memory log. Does not delete a jsonl backing file."""
        self._events = []


# ---------------------------------------------------------------------------
# Module-level singleton, for the LangGraph node and test isolation.
# ---------------------------------------------------------------------------

_default_store: Optional[EventStore] = None


def get_event_store() -> EventStore:
    """Return the process-wide default in-memory EventStore singleton."""
    global _default_store
    if _default_store is None:
        _default_store = EventStore(backend="memory")
    return _default_store


def reset_event_store() -> None:
    """Reset the default singleton to a fresh, empty EventStore. For test isolation."""
    global _default_store
    _default_store = EventStore(backend="memory")
