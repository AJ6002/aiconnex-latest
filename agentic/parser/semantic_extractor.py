"""
aiconnex_agent/parser/semantic_extractor.py
============================================
Sub-module 3: Extracts intent & entities via a REAL LLM call (the primary,
configured path - see aiconnex_agent/llm.py for the AICONNEX_LLM_BACKEND
switch, Ollama by default). The deterministic heuristic below exists ONLY
as a resilience fallback for when the LLM call genuinely fails (network
error, timeout, or a malformed/hallucinated response that fails
validation) - it is not the default extraction mechanism.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from agentic.llm import get_llm

logger = logging.getLogger(__name__)

# Every LLM response is validated before use. A primary_intent outside this
# set is treated as a hallucination and rejected, triggering the heuristic
# fallback rather than being silently trusted downstream.
_VALID_INTENTS = {"compile_zip", "train_rul", "detect_anomalies", "predict", "query_status", "general"}


class SemanticExtractor:
    """Extracts structured intent/entities via a real LLM call, with heuristic fallback on failure."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self._llm = None  # lazily constructed on first real use - never at import/construction time

    def extract(self, user_prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """Extract structured dictionary from user prompt via a real LLM call.

        Falls back to the deterministic heuristic ONLY if the LLM call raises
        (network/timeout) or its response fails validation (hallucinated or
        malformed output) - never as the default path.
        """
        if self.use_llm:
            try:
                result = self._extract_via_llm(user_prompt, system_prompt)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(f"[SemanticExtractor] LLM extraction failed, falling back to heuristics: {exc}")

        return self._extract_heuristic(user_prompt)

    def _extract_via_llm(self, user_prompt: str, system_prompt: str) -> Optional[Dict[str, Any]]:
        """Calls the configured LLM (agentic.llm.get_llm) and parses its structured JSON response."""
        if self._llm is None:
            self._llm = get_llm()

        prompt = system_prompt or user_prompt
        response = self._llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        parsed = self._parse_json_response(text)
        self._validate_llm_response(parsed)
        return self._normalize_llm_response(parsed, user_prompt)

    @staticmethod
    def _parse_json_response(text: str) -> Dict[str, Any]:
        """Extracts and parses a JSON object from raw LLM text output (handles markdown code fences)."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
        return json.loads(match.group(0))

    @staticmethod
    def _validate_llm_response(parsed: Dict[str, Any]) -> None:
        """Rejects hallucinated/malformed LLM output before it reaches the rest of the pipeline."""
        goal = parsed.get("goal")
        if not isinstance(goal, dict) or "primary_intent" not in goal:
            raise ValueError("LLM response missing goal.primary_intent")
        if goal["primary_intent"] not in _VALID_INTENTS:
            raise ValueError(f"LLM hallucinated unknown primary_intent: {goal['primary_intent']!r}")

    @staticmethod
    def _normalize_llm_response(parsed: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
        """Fills in any missing optional keys so downstream contract validation never KeyErrors."""
        goal = dict(parsed.get("goal", {}))
        goal.setdefault("raw_prompt", user_prompt)
        prompt_lower = user_prompt.lower()
        if not goal.get("task_family"):
            if "regression" in prompt_lower or goal.get("primary_intent") == "train_rul":
                goal["task_family"] = "regression"
            elif "anomaly" in prompt_lower or goal.get("primary_intent") == "detect_anomalies":
                goal["task_family"] = "anomaly_detection"
            elif "forecast" in prompt_lower:
                goal["task_family"] = "forecasting"

        return {
            "conversation": parsed.get("conversation") or {"raw_prompt": user_prompt},
            "goal": goal,
            "observed": parsed.get("observed") or {"mentioned_files": [], "mentioned_entities": []},
            "inferred": parsed.get("inferred") or {},
            "business_context": parsed.get("business_context") or {},
            "constraints": parsed.get("constraints") or {"missing_value_tolerance": 0.2},
            "dataset_expectation": parsed.get("dataset_expectation") or {},
            "clarifications_required": parsed.get("clarifications_required") or [],
            "planning_hints": parsed.get("planning_hints") or {},
        }

    def _extract_heuristic(self, user_prompt: str) -> Dict[str, Any]:
        """Deterministic fallback path - used ONLY when the real LLM call above fails or is disabled."""
        prompt_lower = user_prompt.lower()

        # Detect files
        files = re.findall(r'[\w\-\.]+\.(?:zip|csv|xlsx|mat|parquet|tdms|txt)', user_prompt, re.IGNORECASE)

        # Detect primary intent & task_family
        intent = "general"
        task_family = ""
        if any(w in prompt_lower for w in ["anomaly", "outlier", "isolation forest"]):
            intent = "detect_anomalies"
            task_family = "anomaly_detection"
        elif any(w in prompt_lower for w in ["accuracy", "evaluate", "metrics", "score", "status"]):
            intent = "query_status"
        elif any(w in prompt_lower for w in ["train", "rul", "regression"]):
            intent = "train_rul"
            task_family = "regression"
        elif any(w in prompt_lower for w in ["upload", "compile", "parse", "zip"]):
            intent = "compile_zip"

        if "regression" in prompt_lower:
            task_family = "regression"

        return {
            "conversation": {"raw_prompt": user_prompt},
            "goal": {"raw_prompt": user_prompt, "primary_intent": intent, "task_family": task_family},
            "observed": {"mentioned_files": files, "mentioned_entities": []},
            "inferred": {"domain": "Industrial Telemetry" if files else None},
            "business_context": {},
            "constraints": {"missing_value_tolerance": 0.2},
            "dataset_expectation": {
                "expected_format": "zip" if any(f.endswith(".zip") for f in files) else None,
                "expected_source": "inferred",
            },
            "clarifications_required": [],
            "planning_hints": {},
        }
