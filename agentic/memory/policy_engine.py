"""
aiconnex_agent/memory/policy_engine.py
========================================
Deterministic Memory Policy Engine. Decides, per-event, whether it becomes
long-term memory, gets aggregated, or is discarded - and which memory layer
it belongs in. Pure lookup table, zero LLM calls, zero I/O.

Failure events (outcome == "failure") always override to procedural/aggregate
regardless of event_type, since a failure's value is in recognizing a repeated
pattern, not in the specific event's raw detail.

Unknown event types default to "discard" so the pipeline never crashes on a
future/unrecognized event_type - it just fails safe by not retaining it.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from agentic.memory.events import BaseEvent

Action = Literal["retain_full", "retain_summary", "aggregate", "discard"]
Layer = Literal["session", "entity", "procedural", "decision"]


class RetentionDecision(BaseModel):
    """The Memory Policy Engine's verdict for one event."""
    action: Action = Field(..., description="retain_full | retain_summary | aggregate | discard")
    target_layer: Optional[Layer] = Field(default=None, description="Which memory layer this routes to, if any")


class MemoryPolicyEngine:
    """Deterministic event_type -> RetentionDecision lookup table."""

    # (action, target_layer) keyed by event_type, for the success path.
    _RULES: dict[str, tuple] = {
        "DatasetCompiled": ("retain_summary", "entity"),
        "ModelTrained": ("retain_summary", "entity"),
        "ModelEvaluated": ("retain_summary", "entity"),
        "ClarificationAnswered": ("retain_full", "decision"),
        "ClarificationRequested": ("discard", None),
        "ConversationParsed": ("retain_summary", "session"),
        "PlanCreated": ("retain_summary", "session"),
        "ArchiveUploaded": ("retain_summary", "session"),
        "ArchiveDiscovered": ("retain_summary", "session"),
        "ParserSelected": ("retain_summary", "session"),
    }

    _DEFAULT: tuple = ("discard", None)

    def decide(self, event: BaseEvent) -> RetentionDecision:
        """Return the retention decision for one event. Failure always wins over event_type."""
        if event.outcome == "failure":
            return RetentionDecision(action="aggregate", target_layer="procedural")

        action, target_layer = self._RULES.get(event.event_type, self._DEFAULT)
        return RetentionDecision(action=action, target_layer=target_layer)
