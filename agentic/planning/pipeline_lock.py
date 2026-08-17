"""
pipeline_lock_node (Task 11) — freeze the user's HITL decision.
=================================================================
Runs immediately after HITL completes and produces a formal
PipelineLockManifest that downstream nodes (Workflow Planner, Platform
Agent) read from instead of the raw HITL contract.

Immutability = idempotency:
  - First invocation with a completed HITL contract → produces the lock.
  - Second invocation on the same session → returns {} (no-op).
  - This is enforced in Python via a guard in the node, not by pydantic's
    frozen=True — the manifest itself stays a normal model so it can be
    serialised through LangGraph's msgpack checkpointer unchanged.

Reads:  state.hitl_contract (from Task 13's hitl_node — or seeded directly
        during testing), state.cuc.goal, state.dic.recipes
Writes: state.pipeline_lock
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agentic.schemas import PipelineLockManifest
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a Pydantic model or a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _lookup_recipe(dic: Any, recipe_id: str) -> Optional[Dict[str, Any]]:
    """Find the picked recipe in state.dic.recipes; None if not found."""
    if dic is None or not recipe_id:
        return None
    recipes = _get(dic, "recipes", []) or []
    for r in recipes:
        if _get(r, "id") == recipe_id:
            if hasattr(r, "model_dump"):
                return r.model_dump()
            return dict(r) if isinstance(r, dict) else None
    return None


def pipeline_lock_node(state: MasterAgentState) -> Dict[str, Any]:
    """Task 11: freeze the HITL decision into an immutable PipelineLockManifest."""
    logger.info("[PipelineLock] Starting")

    # Idempotency guard: never re-lock once locked.
    if state.pipeline_lock is not None:
        logger.info("[PipelineLock] Already locked — refusing to overwrite (idempotent)")
        return {}

    contract = state.hitl_contract
    if contract is None:
        logger.warning("[PipelineLock] No hitl_contract on state — cannot lock; returning empty")
        return {}

    # Only lock if HITL genuinely completed.
    hitl_complete = _get(contract, "hitl_complete", False)
    selected_recipe_id = _get(contract, "selected_recipe_id")
    if not hitl_complete or not selected_recipe_id:
        logger.info(
            f"[PipelineLock] HITL not complete (complete={hitl_complete}, "
            f"recipe={selected_recipe_id!r}) — refusing to lock"
        )
        return {}

    # Resolve the recipe details from the DIC so the lock is self-contained
    # (downstream doesn't need to re-look up the recipe by id).
    recipe = _lookup_recipe(state.dic, selected_recipe_id)
    if recipe is None:
        logger.warning(
            f"[PipelineLock] Recipe id {selected_recipe_id!r} not found in DIC — locking with "
            "HITL-derived fields only"
        )

    # Business objective: prefer the CUC's own-words goal; fall back to the recipe title.
    business_goal = ""
    if state.cuc is not None:
        goal = _get(state.cuc, "goal")
        business_goal = _get(goal, "business_goal", "") or _get(goal, "raw_prompt", "")
    if not business_goal and recipe is not None:
        business_goal = recipe.get("title", "") or ""

    # Task family: prefer contract-derived (post-Task-1 rewrite), fall back to recipe.task.
    task_family = (_get(contract, "selected_task_family") or "").lower()
    if not task_family and recipe is not None:
        task_family = str(recipe.get("task", "")).lower()

    target_column = _get(contract, "target_column")
    if not target_column and recipe is not None:
        target_column = recipe.get("target")

    operational_preferences = dict(_get(contract, "operational_preferences", {}) or {})
    success_metrics = list(_get(contract, "success_metrics", []) or [])
    turn_count = int(_get(contract, "turn_count", 0) or 0)

    manifest = PipelineLockManifest(
        session_id=state.session_id,
        locked_recipe_id=selected_recipe_id,
        business_objective=business_goal,
        selected_workflow_type=task_family,
        target_column=target_column,
        operational_preferences=operational_preferences,
        success_metrics=success_metrics,
        locked_at=datetime.now(timezone.utc).isoformat(),
        locked_by="user" if turn_count > 0 else "system_auto",
        hitl_turn_count=turn_count,
    )

    logger.info(
        f"[PipelineLock] Locked recipe={manifest.locked_recipe_id}, "
        f"task={manifest.selected_workflow_type}, target={manifest.target_column}, "
        f"by={manifest.locked_by} @ {manifest.locked_at}"
    )

    return {
        "pipeline_lock": manifest.model_dump(),
        "active_agent": "workflow_planner",
    }
