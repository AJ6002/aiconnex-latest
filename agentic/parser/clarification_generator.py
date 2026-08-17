"""
aiconnex_agent/parser/clarification_generator.py
=================================================
Sub-module 6: Generates targeted clarification questions when confidence <
0.85, via a REAL LLM call (the primary, configured path - see
aiconnex_agent/llm.py). The fixed template strings below exist ONLY as a
resilience fallback for when the LLM call genuinely fails - it is not the
default question-generation mechanism.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from agentic.schemas import ConversationUnderstandingContract
from agentic.llm import get_llm

logger = logging.getLogger(__name__)


class ClarificationGenerator:
    """Generates clarification questions via a real LLM call, with template fallback on failure."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self._llm = None  # lazily constructed on first real use

    def generate(self, cuc: ConversationUnderstandingContract) -> List[str]:
        """Generate 1+ targeted clarification questions via a real LLM call.

        Falls back to fixed templates ONLY if the LLM call raises or returns
        an unparseable/empty response - never as the default path.
        """
        if self.use_llm:
            try:
                result = self._generate_via_llm(cuc)
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"[ClarificationGenerator] LLM generation failed, falling back to templates: {exc}")

        return self._generate_heuristic(cuc)

    def _generate_via_llm(self, cuc: ConversationUnderstandingContract) -> Optional[List[str]]:
        """Calls the configured LLM to compose targeted clarification questions."""
        if self._llm is None:
            self._llm = get_llm()

        prompt = self._build_prompt(cuc)
        response = self._llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        parsed = self._parse_json_response(text)
        questions = parsed.get("questions")

        if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
            raise ValueError(f"LLM response missing valid 'questions' list: {parsed!r}")
        if not questions:
            raise ValueError("LLM returned an empty questions list")

        return questions

    @staticmethod
    def _build_prompt(cuc: ConversationUnderstandingContract) -> str:
        intent = cuc.goal.primary_intent if hasattr(cuc.goal, "primary_intent") else cuc.goal.get("primary_intent", "general")
        raw_prompt = cuc.goal.raw_prompt if hasattr(cuc.goal, "raw_prompt") else cuc.goal.get("raw_prompt", "")
        return (
            "A user sent a message to AIConnex Chatbot. "
            "Write 1-2 friendly, natural, conversational responses/questions to ask the user. "
            "If the user said a simple greeting (like 'hi' or 'hello'), greet them warmly first, "
            "then ask what dataset file or ML pipeline goal (training, profiling, anomaly detection) they would like to work on.\n\n"
            f"Primary intent extracted so far: {intent}\n"
            f"Mentioned files: {cuc.observed.get('mentioned_files', [])}\n"
            f"Mentioned entities: {cuc.observed.get('mentioned_entities', [])}\n"
            f"Raw user prompt: {raw_prompt}\n\n"
            'Respond with ONLY a JSON object: {"questions": ["<friendly greeting / clarifying question 1>", "<question 2>"]}'
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
    def _generate_heuristic(cuc: ConversationUnderstandingContract) -> List[str]:
        """Deterministic fallback path - used ONLY when the real LLM call above fails."""
        intent = cuc.goal.primary_intent if hasattr(cuc.goal, "primary_intent") else cuc.goal.get("primary_intent", "general")
        raw_prompt = cuc.goal.raw_prompt if hasattr(cuc.goal, "raw_prompt") else cuc.goal.get("raw_prompt", "")
        raw = str(raw_prompt).strip().lower()
        files = cuc.observed.get("mentioned_files", [])
        questions = []

        if raw in ("hi", "hello", "hey", "greetings", "hi there", "hello there"):
            questions.append("Hello! 👋 I'm the AIConnex Autonomous MLOps Agent.")
            questions.append("Which dataset file or project goal (data compilation, predictive model training, or anomaly detection) would you like to work on?")
            return questions

        if not files:
            questions.append("Which dataset file or archive would you like to process?")
        if intent == "general":
            questions.append("Would you like to compile a raw dataset, train an ML model, or run anomaly detection?")

        return questions or ["Could you please specify your dataset or project goal?"]
