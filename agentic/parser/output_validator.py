"""
aiconnex_agent/parser/output_validator.py
==========================================
Sub-module 4: Validates extraction dict against ConversationUnderstandingContract.
"""

from __future__ import annotations
from typing import Dict, Any
from agentic.schemas import ConversationUnderstandingContract, Goal


class StructuredOutputValidator:
    """Validates raw extraction dicts into strongly-typed Pydantic CUC objects."""

    def validate(self, raw_dict: Dict[str, Any]) -> ConversationUnderstandingContract:
        """Validate raw dictionary into ConversationUnderstandingContract."""
        try:
            return ConversationUnderstandingContract(**raw_dict)
        except Exception:
            goal_raw = raw_dict.get("goal", {})
            goal_obj = Goal(**goal_raw) if isinstance(goal_raw, dict) else Goal()
            return ConversationUnderstandingContract(
                goal=goal_obj,
                observed=raw_dict.get("observed", {}),
                inferred=raw_dict.get("inferred", {}),
            )

