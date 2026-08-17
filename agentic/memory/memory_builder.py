"""
aiconnex_agent/memory/memory_builder.py
==========================================
Deterministic MemoryBuilder: projects an ordered event log into a MemoryBank
by asking the MemoryPolicyEngine what to do with each event, then routing it
into the correct layer. Pure function of (events, policy) -> MemoryBank -
zero LLM calls, zero I/O.

Idempotency: build() called twice on the same log yields a structurally
identical MemoryBank. This is what makes replay.py's rebuild-from-events
guarantee possible - memory is always a re-derivable projection of the log,
never independently mutated state.
"""

from __future__ import annotations

from typing import List, Optional

from agentic.memory.events import BaseEvent
from agentic.memory.policy_engine import MemoryPolicyEngine
from agentic.memory.memory_layers import (
    SessionMemory,
    EntityMemory,
    ProceduralMemory,
    DecisionMemory,
    MemoryBank,
)
from agentic.memory.backends.base import SemanticMemoryBackend


class MemoryBuilder:
    """Projects an event log into a MemoryBank per the configured MemoryPolicyEngine.

    Entity memory is additionally mirrored into a SemanticMemoryBackend (Phase
    5a.6), so fuzzy cross-session recall becomes possible over exactly the same
    facts that are deterministically recorded here. Decision and Procedural
    memory are NEVER mirrored - see docs/superpowers/plans/2026-07-29-phase5a6-
    mem0-sprint2.md for the guardrail rationale (HITL decisions and failure
    patterns must stay fully deterministic/auditable, never LLM-derived).
    """

    def __init__(self, policy: MemoryPolicyEngine, semantic_backend: Optional[SemanticMemoryBackend] = None):
        self.policy = policy
        # Stored as _explicit_semantic_backend rather than resolved eagerly: when no
        # explicit backend is given, self.semantic_backend resolves get_semantic_backend()
        # freshly on every access (see property below). This matters because MemoryBuilder
        # is used as a long-lived module-level singleton (see memory_agent.py) - caching the
        # default backend once at __init__ time would go stale the moment anything calls
        # reset_semantic_backend() (as tests do), silently writing to an orphaned instance.
        self._explicit_semantic_backend = semantic_backend

    @property
    def semantic_backend(self) -> SemanticMemoryBackend:
        if self._explicit_semantic_backend is not None:
            return self._explicit_semantic_backend
        from agentic.memory.backends.factory import get_semantic_backend
        return get_semantic_backend()

    def build(self, events: List[BaseEvent]) -> MemoryBank:
        """Deterministically project the event log into a fresh MemoryBank."""
        bank = MemoryBank()

        for event in events:
            decision = self.policy.decide(event)

            if decision.action == "discard":
                continue

            if decision.target_layer == "session":
                self._route_session(bank, event)
            elif decision.target_layer == "entity":
                self._route_entity(bank, event)
            elif decision.target_layer == "decision":
                self._route_decision(bank, event)
            elif decision.target_layer == "procedural":
                self._route_procedural(bank, event)

        return bank

    @staticmethod
    def _route_session(bank: MemoryBank, event: BaseEvent) -> None:
        session = bank.session.get(event.workflow_id)
        if session is None:
            session = SessionMemory(workflow_id=event.workflow_id, status="running")
            bank.session[event.workflow_id] = session

        session.steps_run.append(event.event_type)
        if event.event_type == "ConversationParsed":
            intent = event.payload.get("intent")
            if intent:
                session.last_intent = intent

    def _route_entity(self, bank: MemoryBank, event: BaseEvent) -> None:
        entity = bank.entities.get(event.subject_id)
        if entity is None:
            entity = EntityMemory(subject_id=event.subject_id, subject_type=event.subject_type)
            bank.entities[event.subject_id] = entity
        entity.observations.append(dict(event.payload))

        # Mirror into the semantic backend - Entity layer only (see class docstring).
        summary = f"{event.subject_type} {event.subject_id}: {event.event_type} {event.payload}"
        self.semantic_backend.add(
            text=summary,
            metadata={"subject_id": event.subject_id, "subject_type": event.subject_type},
        )

    @staticmethod
    def _route_decision(bank: MemoryBank, event: BaseEvent) -> None:
        bank.decisions.append(
            DecisionMemory(
                decision_id=event.event_id,
                question=event.payload.get("question", ""),
                answer=event.payload.get("answer"),
                workflow_id=event.workflow_id,
            )
        )

    @staticmethod
    def _route_procedural(bank: MemoryBank, event: BaseEvent) -> None:
        # Aggregate by (pattern, outcome) instead of appending duplicates.
        pattern = event.event_type
        for existing in bank.procedures:
            if existing.pattern == pattern and existing.outcome == event.outcome:
                existing.occurrences += 1
                return
        bank.procedures.append(ProceduralMemory(pattern=pattern, outcome=event.outcome, occurrences=1))
