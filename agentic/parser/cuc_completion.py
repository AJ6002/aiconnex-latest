"""
aiconnex_agent/parser/cuc_completion.py
=========================================
Field-driven CUC completion helper (chatbot_5jul Task 3).

Single source of truth for "is the minimal intent manifest filled?"
Used by graph.py routing to decide: keep clarifying vs. advise upload.

Minimal required keys (locked in plan decisions log):
  1. goal.primary_intent != "general"  — user named a real task
  2. goal.task_family != ""            — problem-type bucket known
  3. goal.confidence >= 0.85           — same bar as clarification gate

dataset_expectation fields are deliberately excluded: Scout auto-detects
file type / schema post-upload. Requiring them conversationally recreates
the over-questioning this rebuild removes.
"""

from __future__ import annotations

from typing import List

from agentic.schemas import ConversationUnderstandingContract

REQUIRED_CONFIDENCE = 0.85


def is_manifest_minimally_complete(cuc: ConversationUnderstandingContract) -> bool:
    """Return True when the minimum intent keys are filled.

    Conditions (all must hold):
      - goal.primary_intent is a real intent (not the default 'general')
      - goal.task_family is non-empty
      - goal.confidence >= 0.85
    """
    goal = cuc.goal
    return (
        goal.primary_intent not in ("", "general")
        and bool(goal.task_family)
        and goal.confidence >= REQUIRED_CONFIDENCE
    )


def get_missing_keys(cuc: ConversationUnderstandingContract) -> List[str]:
    """Return a human-readable list of what the user still needs to provide."""
    goal = cuc.goal
    missing: List[str] = []

    if goal.primary_intent in ("", "general"):
        missing.append(
            "the primary task (e.g. 'predict remaining useful life', "
            "'detect anomalies', 'classify failures')"
        )
    if not goal.task_family:
        missing.append(
            "the problem type (e.g. 'regression', 'anomaly detection', "
            "'classification', 'forecasting')"
        )
    if goal.confidence < REQUIRED_CONFIDENCE:
        missing.append(
            f"more detail to reach {int(REQUIRED_CONFIDENCE * 100)}% confidence "
            f"(currently {int(goal.confidence * 100)}%)"
        )

    return missing
