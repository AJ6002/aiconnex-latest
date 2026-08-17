"""
aiconnex_agent/planning/plan_validator.py
==========================================
Sub-module 2: Validates raw plan step dicts into a strongly-typed ExecutionPlan.
Guarantees the plan is never empty/unroutable.
"""

from __future__ import annotations
from typing import Any, Dict, List
from agentic.schemas import ExecutionPlan, TaskStep

_VALID_AGENTS = {"scout", "platform", "memory"}

_SAFE_FALLBACK_STEP: Dict[str, Any] = {
    "step_id": "step_1",
    "target_agent": "scout",
    "task": "General discovery — inspect available data sources",
}


class PlanValidator:
    """Validates and sanitizes raw plan step dicts into an ExecutionPlan contract."""

    def validate(self, raw_steps: List[Dict[str, Any]], source_intent: str = "general") -> ExecutionPlan:
        """Drop invalid steps; guarantee at least one safe, routable step remains."""
        valid_steps: List[TaskStep] = []
        for raw in raw_steps:
            if raw.get("target_agent") not in _VALID_AGENTS:
                continue
            try:
                valid_steps.append(TaskStep(**raw))
            except Exception:
                continue

        if not valid_steps:
            valid_steps = [TaskStep(**_SAFE_FALLBACK_STEP)]

        return ExecutionPlan(steps=valid_steps, source_intent=source_intent)
