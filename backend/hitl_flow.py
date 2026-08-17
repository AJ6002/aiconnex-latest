"""
hitl_flow.py — Per-turn HITL conversation handler (Task 1, v2 dataset-driven).

Mirrors pre_upload_flow.process_turn() exactly:
  1. Extract    — call LLM (with dataset-aware system prompt built from the
                  DIC) or recipe-aware keyword fallback for this turn.
  2. Merge      — update HITLContract only where confidence is higher.
  3. Complete?  — check if the user has picked a recipe with real confidence.
  4. Derive     — resolve target_column / task_family from the chosen recipe.

Returns a dict compatible with the terminal_runner loop.
"""

from __future__ import annotations

import logging
import time

from hitl_schemas import (
    HITLContract,
    HITLTurnExtraction,
    _is_complete,
    apply_recipe_context,
)
from hitl_extraction import extract_hitl_turn

logger = logging.getLogger(__name__)

# Confidence threshold — only accept LLM-extracted fields above this
MIN_CONFIDENCE = 0.50


# ─── Merge ────────────────────────────────────────────────────────────────────

def _merge(contract: HITLContract, extraction: HITLTurnExtraction) -> HITLContract:
    """Merge extraction into contract — only overwrite the recipe pick when the
    new confidence is at least as strong as what we already have. Free-form
    operational_preferences / success_metrics are additive (never lose info
    already captured)."""
    if (
        extraction.selected_recipe_id is not None
        and extraction.selected_recipe_confidence >= MIN_CONFIDENCE
        and extraction.selected_recipe_confidence >= contract.selected_recipe_confidence
    ):
        contract.selected_recipe_id = extraction.selected_recipe_id
        contract.selected_recipe_confidence = extraction.selected_recipe_confidence

    if extraction.operational_preferences:
        # Additive dict update — never discard a preference already captured
        for k, v in extraction.operational_preferences.items():
            contract.operational_preferences[k] = v

    if extraction.success_metrics:
        # Deduplicated union of any success metrics stated so far
        for m in extraction.success_metrics:
            if m and m not in contract.success_metrics:
                contract.success_metrics.append(m)

    return contract


_FALLBACK_OPENING_MESSAGE = (
    "Your dataset 'your dataset' has been compiled, but Scout wasn't "
    "able to derive concrete analytical objectives automatically. "
    "Could you tell me in one sentence what you'd like this dataset to "
    "help you accomplish?"
)


def _build_recipe_opening(dic_context: dict) -> str:
    """Dynamic HITL opening prompt built from Scout's actual Recipe Catalog.

    No hardcoded ETP fallback — if Scout produced no recipes, we honestly ask
    the user to describe their goal in their own words rather than pretending
    to know about wastewater / TDS / COD.
    """
    dic_context = dic_context or {}
    recipes = dic_context.get("recipes", []) or []
    dataset_name = (dic_context.get("dataset_identity") or {}).get("name") or "your dataset"

    if not recipes:
        if dataset_name == "your dataset":
            return _FALLBACK_OPENING_MESSAGE
        return (
            f"Your dataset '{dataset_name}' has been compiled, but Scout wasn't "
            "able to derive concrete analytical objectives automatically. "
            "Could you tell me in one sentence what you'd like this dataset to "
            "help you accomplish?"
        )

    lines = [
        f"Great news — your dataset '{dataset_name}' has been compiled and analysed.",
        "Based on what I found, here are the available analytical objectives:\n",
    ]

    for i, r in enumerate(recipes, start=1):
        rid = r.get("id", f"R{i:03d}")
        conf_pct = int((r.get("confidence") or 1.0) * 100)
        task_tag = r.get("task", "")
        title = r.get("title", f"Recipe {i}")
        target = r.get("target")
        target_str = f" — target: {target}" if target else ""
        rationale = (r.get("rationale") or "").strip()
        lines.append(f"  [{i}] {title}  ({rid} · {task_tag}{target_str} · {conf_pct}% confidence)")
        if rationale:
            lines.append(f"       {rationale}")

    lines.append("")
    lines.append("Please reply with the number of the objective you'd like to pursue (e.g. 1, 2, 3).")

    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────

def process_hitl_turn(
    message: str,
    session_id: str,
    dic_context: dict,
    contract=None,
    history=None,
) -> dict:
    """Process one HITL conversation turn.

    Args:
        message:     User's input (or "[HITL_START]" to open the conversation)
        session_id:  Current session ID (for MLflow logging)
        dic_context: Compiled DIC from Scout — drives BOTH the opening menu
                     and the LLM's per-turn system prompt.
        contract:    Current HITLContract (None = first turn)
        history:     Conversation history for multi-turn context

    Returns:
        reply:              str  — LLM-generated message to display to user
        hitl_complete:      bool — True when recipe is picked with real confidence
        contract:           HITLContract — updated state
        selected_recipe_id: str | None
        target_column:      str | None  (derived from selected recipe)
        selected_task_family: str | None
        operational_preferences: dict
    """
    start = time.time()

    if contract is None:
        contract = HITLContract()

    contract.turn_count += 1

    # ── Opening turn: build dynamic prompt from DIC recipes ──────────────────
    if message.strip() == "[HITL_START]":
        opening = _build_recipe_opening(dic_context)
        return {
            "reply": opening,
            "hitl_complete": False,
            "contract": contract,
            "selected_recipe_id": None,
            "target_column": None,
            "selected_task_family": None,
            "operational_preferences": {},
        }

    # ── Step 1: Extract (LLM with dataset-aware prompt, or recipe-aware fallback)
    extraction: HITLTurnExtraction = extract_hitl_turn(
        message=message,
        history=history or [],
        contract=contract,
        dic_context=dic_context,
    )

    # ── Step 2: Merge ─────────────────────────────────────────────────────────
    contract = _merge(contract, extraction)

    # ── Step 3: Derive recipe context (target_column / task_family) ──────────
    contract = apply_recipe_context(contract, dic_context)

    # ── Step 4: Completion check ─────────────────────────────────────────────
    complete = extraction.hitl_complete or _is_complete(contract)
    contract.hitl_complete = complete

    # ── Reply ─────────────────────────────────────────────────────────────────
    reply = extraction.reply or (
        "I've captured that. Let me know if you'd like to adjust anything."
        if complete
        else "Could you clarify? Please choose one of the options above."
    )

    elapsed_ms = int((time.time() - start) * 1000)
    logger.debug(
        f"[HITLFlow] turn={contract.turn_count} "
        f"recipe={contract.selected_recipe_id} "
        f"target={contract.target_column} "
        f"task={contract.selected_task_family} "
        f"complete={complete} elapsed={elapsed_ms}ms"
    )

    return {
        "reply": reply,
        "hitl_complete": complete,
        "contract": contract,
        "selected_recipe_id": contract.selected_recipe_id,
        "target_column": contract.target_column,
        "selected_task_family": contract.selected_task_family,
        "operational_preferences": dict(contract.operational_preferences),
        "elapsed_ms": elapsed_ms,
    }
