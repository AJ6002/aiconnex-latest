"""
aiconnex_agent/parser/contract_manager.py
============================================
contract_manager_node — Pre-Upload v1 Architecture (Task 3)

THE ONE GENUINE GAP this rebuild fixes: today, StructuredOutputValidator.validate()
takes only this turn's raw extraction dict and builds a BRAND NEW
ConversationUnderstandingContract from it — state.cuc from the previous turn is
discarded outright. There is no merge, no "don't forget what the user already
told us", and no contradiction detection. This module is that missing merge step.

Responsibilities (owns):
  - Merge this turn's raw extraction (state.latest_extraction) into the existing
    state.cuc, preserving any field the new extraction didn't touch.
  - Detect contradictions: when a field the CUC already holds a real value for
    is contradicted by a new, different, non-empty value this turn, RECORD it
    (ContradictionRecord) instead of silently overwriting.
  - Track contract versioning implicitly via ContradictionRecord.turn_detected.

Does NOT own (per the architecture's node responsibility table):
  - Asking questions (response_writer_node).
  - Deciding what to do next (conversation_planner_node).
  - Extraction itself (intent_extraction_node / SemanticExtractor).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from agentic.schemas import ConversationUnderstandingContract, ContradictionRecord, Goal, BusinessContext
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

# Scalar goal fields eligible for contradiction detection. goal.confidence is
# handled separately (it's a score, not a fact — see _merge_confidence).
# business_goal is deliberately EXCLUDED: it's free text (e.g. "Predict
# Remaining Useful Life"), and the extractor may rephrase it turn to turn
# without the user having actually changed their mind — contradiction-
# checking free text would create false positives. It always takes the
# newest non-empty value (see merge_cuc's goal-merging section below).
_GOAL_CONTRADICTION_FIELDS = ("primary_intent", "task_family")

# BusinessContext fields (industry/process/asset/operational_objective) — not
# contradiction-checked for the same reason as 'inferred': these are framing/
# derived context, not asserted facts the user is expected to defend.
_BUSINESS_CONTEXT_FIELDS = ("industry", "process", "asset", "operational_objective")

# Dict-shaped CUC fields merged key-by-key. Each is a flat Dict[str, Any] on
# the contract (observed, inferred, constraints, dataset_expectation).
_DICT_FIELDS = ("observed", "inferred", "constraints", "dataset_expectation")

# Contradiction detection (via _merge_scalar's confirm-don't-overwrite path) is
# reserved for fields the user explicitly asserts as fact — 'goal' fields and
# 'observed' entities. It is deliberately NOT applied to 'inferred',
# 'constraints', or 'dataset_expectation': these are technical/derived
# parameters (e.g. constraints.missing_value_tolerance), not conversational
# facts. Contradiction-checking them surfaced a real bug during integration
# testing: a low-signal reply like "ok" makes the extractor produce noisy
# values for these fields each turn, and since nothing ever marks a technical
# default "resolved" by the user, it created an infinite unresolvable
# confirm-loop. These fields instead take the newest meaningful value
# directly, with no contradiction bookkeeping.
_CONTRADICTION_CHECKED_DICT_FIELDS = ("observed",)

_DEFAULT_INTENT = "general"


def _is_meaningful(value: Any) -> bool:
    """True if `value` carries real information (not None/""/[]/{})."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != "" and value.strip() != _DEFAULT_INTENT
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _merge_scalar(
    field_path: str,
    old_value: Any,
    new_value: Any,
    turn: int,
    contradictions: List[ContradictionRecord],
) -> Any:
    """Merge a single scalar field. Records a contradiction (and keeps the
    OLD value) if both old and new are meaningful and differ. Fills in the
    new value if old was empty/default. Otherwise keeps old."""
    if not _is_meaningful(new_value):
        return old_value  # nothing new said this turn — preserve prior knowledge
    if not _is_meaningful(old_value):
        return new_value  # first time this field has been filled
    if old_value == new_value:
        return old_value  # consistent — no-op
    # Both meaningful and different -> real contradiction, don't silently overwrite.
    contradictions.append(ContradictionRecord(
        field_path=field_path,
        previous_value=old_value,
        new_value=new_value,
        turn_detected=turn,
        resolved=False,
    ))
    logger.info(f"[ContractManager] Contradiction detected at '{field_path}': "
                f"{old_value!r} -> {new_value!r} (turn {turn})")
    return old_value  # keep prior value until explicitly resolved (response_writer_node's job)


def _merge_confidence(old_confidence: float, new_confidence: float) -> float:
    """goal.confidence is an extraction-quality score, not a fact — take the
    max seen so far so a low-information turn doesn't regress prior confidence."""
    try:
        return max(float(old_confidence), float(new_confidence))
    except (TypeError, ValueError):
        return old_confidence


def _merge_dict_field(
    field_name: str,
    old_dict: Dict[str, Any],
    new_dict: Dict[str, Any],
    turn: int,
    contradictions: List[ContradictionRecord],
) -> Dict[str, Any]:
    """Merge one flat dict-shaped CUC field key by key.
    - List values: union + de-dupe (preserve order, no info lost).
    - Scalar values: contradiction-aware merge ONLY for fields in
      _CONTRADICTION_CHECKED_DICT_FIELDS (currently just 'observed');
      other fields (inferred/constraints/dataset_expectation) simply take
      the newest meaningful value, since they're technical/derived
      parameters rather than user-asserted facts (see module docstring
      near _CONTRADICTION_CHECKED_DICT_FIELDS for why).
    - Other/complex values: prefer new if old is empty, else keep old.
    """
    if not isinstance(new_dict, dict):
        return old_dict
    check_contradictions = field_name in _CONTRADICTION_CHECKED_DICT_FIELDS
    merged = dict(old_dict)
    for key, new_value in new_dict.items():
        old_value = merged.get(key)
        field_path = f"{field_name}.{key}"
        if isinstance(new_value, list) or isinstance(old_value, list):
            old_list = old_value if isinstance(old_value, list) else ([old_value] if _is_meaningful(old_value) else [])
            new_list = new_value if isinstance(new_value, list) else ([new_value] if _is_meaningful(new_value) else [])
            merged_list = list(old_list)
            for item in new_list:
                if item not in merged_list:
                    merged_list.append(item)
            merged[key] = merged_list
        elif isinstance(new_value, dict) or isinstance(old_value, dict):
            # Nested dict: shallow-prefer new if old absent, else keep old (out of scope for contradiction detection)
            merged[key] = new_value if not _is_meaningful(old_value) else old_value
        elif check_contradictions:
            merged[key] = _merge_scalar(field_path, old_value, new_value, turn, contradictions)
        else:
            merged[key] = new_value if _is_meaningful(new_value) else old_value
    return merged


def merge_cuc(
    existing_cuc: ConversationUnderstandingContract,
    raw_extraction: Dict[str, Any],
    turn: int,
) -> ConversationUnderstandingContract:
    """Pure merge function: existing CUC + this turn's raw extraction -> updated CUC.
    No LLM calls, no I/O — fully deterministic and unit-testable in isolation.
    """
    contradictions: List[ContradictionRecord] = list(existing_cuc.contradictions)

    # --- goal ---
    new_goal_raw = raw_extraction.get("goal") or {}
    merged_goal_kwargs: Dict[str, Any] = {}
    for field in _GOAL_CONTRADICTION_FIELDS:
        old_val = getattr(existing_cuc.goal, field)
        new_val = new_goal_raw.get(field)
        merged_goal_kwargs[field] = _merge_scalar(f"goal.{field}", old_val, new_val, turn, contradictions)

    merged_goal_kwargs["confidence"] = _merge_confidence(
        existing_cuc.goal.confidence, new_goal_raw.get("confidence", existing_cuc.goal.confidence)
    )
    # raw_prompt is a log of what was said, not a fact to contradict — always take latest non-empty.
    merged_goal_kwargs["raw_prompt"] = new_goal_raw.get("raw_prompt") or existing_cuc.goal.raw_prompt
    # business_goal: free text, not contradiction-checked (see _GOAL_CONTRADICTION_FIELDS comment above).
    merged_goal_kwargs["business_goal"] = new_goal_raw.get("business_goal") or existing_cuc.goal.business_goal

    merged_goal = Goal(**merged_goal_kwargs)

    # --- business_context (not contradiction-checked, same policy as 'inferred') ---
    new_business_context_raw = raw_extraction.get("business_context") or {}
    merged_business_context_kwargs: Dict[str, Any] = {}
    for field in _BUSINESS_CONTEXT_FIELDS:
        old_val = getattr(existing_cuc.business_context, field)
        new_val = new_business_context_raw.get(field)
        merged_business_context_kwargs[field] = new_val if _is_meaningful(new_val) else old_val
    merged_business_context = BusinessContext(**merged_business_context_kwargs)

    # --- flat dict fields ---
    merged_dicts: Dict[str, Dict[str, Any]] = {}
    for field_name in _DICT_FIELDS:
        old_dict = getattr(existing_cuc, field_name) or {}
        new_dict = raw_extraction.get(field_name) or {}
        merged_dicts[field_name] = _merge_dict_field(field_name, old_dict, new_dict, turn, contradictions)

    # --- conversation / planning_hints / clarifications_required: not this node's concern.
    # conversation metadata is refreshed each turn (session/turn bookkeeping lives upstream in
    # conversation_manager_node); clarifications_required and planning_hints belong to
    # response_writer_node / conversation_planner_node, left untouched here.
    merged_conversation = raw_extraction.get("conversation") or existing_cuc.conversation

    return ConversationUnderstandingContract(
        conversation=merged_conversation,
        goal=merged_goal,
        observed=merged_dicts["observed"],
        inferred=merged_dicts["inferred"],
        business_context=merged_business_context,
        constraints=merged_dicts["constraints"],
        dataset_expectation=merged_dicts["dataset_expectation"],
        clarifications_required=existing_cuc.clarifications_required,
        planning_hints=existing_cuc.planning_hints,
        contradictions=contradictions,
    )


def contract_manager_node(state: MasterAgentState) -> Dict[str, Any]:
    """LangGraph node wrapper: merges state.latest_extraction into state.cuc.

    Reads:  state.cuc (existing, accumulated contract), state.latest_extraction
            (this turn's raw dict, produced by intent_extraction_node upstream).
    Writes: state.cuc (merged), active_agent='planner' handoff marker.
    """
    turn = len(state.messages)
    raw_extraction = state.latest_extraction or {}

    logger.info(f"[ContractManager] Merging turn {turn} extraction into existing CUC")
    merged_cuc = merge_cuc(state.cuc, raw_extraction, turn)

    if merged_cuc.contradictions:
        unresolved = [c for c in merged_cuc.contradictions if not c.resolved]
        if unresolved:
            logger.info(f"[ContractManager] {len(unresolved)} unresolved contradiction(s) present")

    return {
        "cuc": merged_cuc.model_dump(),
        "active_agent": "planner",
    }
