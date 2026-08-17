# aiconnex_agent/platform/judge_agent.py
"""
Judge Agent (Phase 5c)
========================
LLM-based qualitative risk evaluation with deterministic heuristic fallback.
Follows the standard AIConnex LLM pattern: get_llm() → Pydantic validation →
fallback on any failure. Includes robust JSON block extraction (Remediation 4).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from agentic.schemas import ScorerReport, JudgeReport

try:
    from agentic.llm import get_llm
except ImportError:
    get_llm = None  # type: ignore

logger = logging.getLogger(__name__)



def _heuristic_qualitative_score(scorer: ScorerReport) -> float:
    """Deterministic heuristic fallback when LLM is unavailable.

    Maps hard metrics into a [0.0, 1.0] qualitative score:
      - R² contributes 40% (higher is better)
      - MAPE contributes 30% (lower is better, capped at 20%)
      - RMSE contributes 30% (normalized, lower is better)
    """
    r2_component = max(0.0, min(1.0, scorer.r2_score)) * 0.4
    mape_component = max(0.0, 1.0 - scorer.mape / 20.0) * 0.3
    rmse_component = max(0.0, 1.0 - scorer.rmse / 100.0) * 0.3
    return round(max(0.0, min(1.0, r2_component + mape_component + rmse_component)), 4)


def _extract_json_dict(text: str) -> Dict[str, Any]:
    """Robust JSON dictionary extraction handling markdown fences and raw JSON (Remediation 4)."""
    # Strip markdown ```json ... ``` code blocks
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
    # Try parsing directly
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Regex search for first object
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data

    raise ValueError("No valid JSON dictionary found in response text")


def judge_candidate(
    recipe_id: str,
    scorer_report: ScorerReport,
    dataset_summary: Dict[str, Any],
) -> JudgeReport:
    """Evaluate a candidate model qualitatively.

    Attempts LLM-based evaluation first; falls back to deterministic
    heuristic scoring on any failure (network error, API timeout, etc.).

    Args:
        recipe_id: Identifier of the candidate recipe.
        scorer_report: Hard metrics from the Scorer Agent.
        dataset_summary: Dataset metadata (rows, columns, etc.).

    Returns:
        JudgeReport with qualitative assessment.
    """
    # Attempt LLM evaluation
    try:
        if get_llm is None:
            raise RuntimeError("agentic.llm unavailable")
        llm = get_llm()


        prompt = (
            f"Evaluate this ML model for industrial deployment.\n"
            f"Metrics: R²={scorer_report.r2_score:.4f}, RMSE={scorer_report.rmse:.2f}, "
            f"MAE={scorer_report.mae:.2f}, MAPE={scorer_report.mape:.2f}%\n"
            f"Dataset: {dataset_summary}\n"
            f"Rate on a 0-1 scale for: physical_realism, extrapolation_risk, overfitting_risk.\n"
            f"Return JSON with keys: qualitative_score, rubric_ratings, reasoning, risk_assessment"
        )
        response = llm.invoke(prompt)
        text = response if isinstance(response, str) else getattr(response, "content", str(response))
        
        parsed = _extract_json_dict(text)
        return JudgeReport(
            recipe_id=recipe_id,
            qualitative_score=float(parsed.get("qualitative_score", 0.5)),
            rubric_ratings=parsed.get("rubric_ratings", {}),
            reasoning=str(parsed.get("reasoning", "")),
            risk_assessment=str(parsed.get("risk_assessment", "")),
        )

    except Exception as e:
        logger.warning(f"[JudgeAgent] LLM evaluation failed for {recipe_id}: {e}. Using heuristic fallback.")

    # Deterministic heuristic fallback
    qual_score = _heuristic_qualitative_score(scorer_report)
    return JudgeReport(
        recipe_id=recipe_id,
        qualitative_score=qual_score,
        rubric_ratings={
            "physical_realism": qual_score,
            "extrapolation_risk": qual_score,
            "overfitting_risk": qual_score,
        },
        reasoning="qualitative_unavailable",
        risk_assessment="Heuristic fallback — LLM unavailable.",
    )
