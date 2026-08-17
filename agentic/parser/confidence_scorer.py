"""
aiconnex_agent/parser/confidence_scorer.py
===========================================
Sub-module 5: Evaluates ambiguity and assigns a confidence score via a REAL
LLM self-assessment call (the primary, configured path - see
aiconnex_agent/llm.py). The rule-based ladder below exists ONLY as a
resilience fallback for when the LLM call genuinely fails (network error,
timeout, or a malformed/out-of-range response) - it is not the default
scoring mechanism.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from agentic.schemas import ConversationUnderstandingContract
from agentic.llm import get_llm

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Scores extraction clarity via a real LLM self-assessment, with rule-based fallback on failure."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self._llm = None  # lazily constructed on first real use

    def score(self, cuc: ConversationUnderstandingContract) -> float:
        """Compute confidence score [0.0-1.0] via a real LLM call.

        Falls back to the deterministic rule-based ladder ONLY if the LLM
        call raises or returns an unparseable/out-of-range value - never as
        the default path.
        """
        if self.use_llm:
            try:
                result = self._score_via_llm(cuc)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(f"[ConfidenceScorer] LLM scoring failed, falling back to rule-based ladder: {exc}")

        return self._score_heuristic(cuc)

    def _score_via_llm(self, cuc: ConversationUnderstandingContract) -> Optional[float]:
        """Calls the configured LLM to self-assess extraction confidence."""
        if self._llm is None:
            self._llm = get_llm()

        prompt = self._build_prompt(cuc)
        response = self._llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        parsed = self._parse_json_response(text)
        confidence = parsed.get("confidence")

        if not isinstance(confidence, (int, float)):
            raise ValueError(f"LLM response missing numeric 'confidence': {parsed!r}")
        if not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(f"LLM hallucinated out-of-range confidence: {confidence!r}")

        return float(confidence)

    @staticmethod
    def _build_prompt(cuc: ConversationUnderstandingContract) -> str:
        return (
            "You are assessing how confidently a Conversation Understanding Contract (CUC) "
            "was extracted from a user's request. Rate your confidence that the extracted "
            "intent and entities are correct and complete enough to proceed WITHOUT asking "
            "the user a clarifying question.\n\n"
            f"Primary intent: {cuc.goal.primary_intent if hasattr(cuc.goal, 'primary_intent') else cuc.goal.get('primary_intent', 'general')}\n"
            f"Mentioned files: {cuc.observed.get('mentioned_files', [])}\n"
            f"Mentioned entities: {cuc.observed.get('mentioned_entities', [])}\n"
            f"Inferred domain: {cuc.inferred.get('domain')}\n\n"
            "Respond with ONLY a JSON object: "
            '{"confidence": <float 0.0-1.0>, "reasoning": "<one sentence>"}\n'
            "A vague or general intent with no mentioned files should score low (< 0.85). "
            "A specific, unambiguous intent with mentioned files should score high (>= 0.90)."
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
        return json.loads(match.group(0))

    @staticmethod
    def _score_heuristic(cuc: ConversationUnderstandingContract) -> float:
        """Deterministic fallback path - used ONLY when the real LLM call above fails."""
        intent = cuc.goal.primary_intent if hasattr(cuc.goal, "primary_intent") else cuc.goal.get("primary_intent", "general")

        files = cuc.observed.get("mentioned_files", [])

        if intent != "general" and files:
            return 0.95
        elif intent != "general":
            return 0.88
        elif files:
            return 0.86
        else:
            return 0.50
