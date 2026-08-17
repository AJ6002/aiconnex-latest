"""
aiconnex_agent/graph.py - LangGraph StateGraph Topology Builder
================================================================
Assembles the complete LangGraph StateGraph topology with checkpointer and routing edges.

chatbot_5jul changes:
- SqliteSaver replaces MemorySaver (survives Flask debug-mode auto-reloads)
- route_after_parser uses is_manifest_minimally_complete() instead of raw confidence threshold
- advise_upload_node parks the graph when manifest is complete but no file uploaded yet
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END

from agentic.state import MasterAgentState

# Pre-Upload chain (unchanged from Task 8)
from agentic.parser.conversation_parser import (
    real_conversation_parser_node,  # legacy — kept importable for older tests
    conversation_manager_node,
    intent_extraction_node,
)
from agentic.parser.contract_manager import contract_manager_node
from agentic.parser.conversation_planner import conversation_planner_node
from agentic.parser.response_writer import response_writer_node
from agentic.parser.clarification_node import real_clarification_node as clarification_node  # legacy
from agentic.parser.cuc_completion import is_manifest_minimally_complete

# Post-Upload chain — 8-node Scout split (Tasks 2-10) + HITL + Lock + Workflow (Tasks 11-13)
from agentic.scout.nodes import (
    archive_discovery_node,
    structure_analysis_node,
    entity_analysis_node,
    relationship_analysis_node,
    temporal_analysis_node,
    feature_analysis_node,
    quality_analysis_node,
    statistical_analysis_node,
    exploration_synthesizer_node,
)
from agentic.planning.hitl_node import hitl_node
from agentic.planning.pipeline_lock import pipeline_lock_node
from agentic.planning.workflow_planner import workflow_planner_node

# Legacy post-upload nodes — no longer wired, kept importable for archaeology
from agentic.planning.planning_engine import real_planning_engine_node as planning_engine_node  # noqa: F401
from agentic.scout.scout_node import real_scout_agent_node as scout_agent_node  # noqa: F401
from agentic.nodes.plan_evaluator import real_plan_evaluator_node as plan_evaluator_node  # noqa: F401

# Platform + Memory — unchanged, wired as the terminal stages of the new chain
from agentic.platform.platform_node import real_platform_agent_node as platform_agent_node
from agentic.memory.memory_agent import real_memory_agent_node as memory_agent_node


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def advise_upload_node(state: MasterAgentState) -> dict:
    """Park node: manifest is complete but no file uploaded yet.

    Emits an InterruptPayload with interrupt_type='advise_upload' so the
    frontend SSE adapter renders the 'please upload your dataset' card.
    The graph parks here on interrupt(). When /api/upload resumes this thread
    with the saved file path, interrupt() returns that path — which we MUST
    capture into state.upload_path so route_after_upload advances into Scout
    with the real file (previously the resume value was discarded, so Scout
    always saw upload_path=None and fell into its 'no file' failure branch).
    """
    from langgraph.types import interrupt
    from agentic.schemas import InterruptPayload

    payload = InterruptPayload(
        interrupt_type="advise_upload",
        questions=["Your intent is clear. Please upload your dataset to continue."],
        options=[],
        reason="Manifest complete, awaiting dataset upload",
    )
    upload_path = interrupt(payload.model_dump())

    # On resume, /api/upload passes the saved filesystem path as the resume value.
    if isinstance(upload_path, str) and upload_path.strip():
        return {"upload_path": upload_path.strip(), "active_agent": "planner"}
    return {}


def upload_gate_node(state: MasterAgentState) -> dict:
    """Pre-Upload v1 Architecture (Task 7): upload_gate_node.

    Same interrupt()/resume mechanism as advise_upload_node (proven correct
    across this session — untouched here), reframed as the terminal node of
    the new 6-node chain. Where advise_upload_node was reached unconditionally
    from the legacy route_after_parser once is_manifest_minimally_complete()
    held, upload_gate_node is reached ONLY when conversation_planner_node's
    ConversationPlan.action == 'recommend_upload' — i.e. it CONSUMES the
    UploadReadinessContract that conversation_planner_node already computed,
    rather than recomputing readiness itself.

    Owns: the upload-readiness HITL pause/resume transition.
    Does NOT own: dataset reasoning (that starts downstream in Scout once
    resumed) — matches the v1 responsibility table exactly.
    """
    from langgraph.types import interrupt
    from agentic.schemas import InterruptPayload

    readiness = state.upload_readiness
    missing = readiness.missing_fields if readiness else []
    reason = (
        "Manifest complete, awaiting dataset upload"
        if not missing
        else f"Reached upload_gate_node with unexpected missing fields: {missing}"
    )

    payload = InterruptPayload(
        interrupt_type="advise_upload",
        questions=["Your intent is clear. Please upload your dataset to continue."],
        options=[],
        reason=reason,
    )
    upload_path = interrupt(payload.model_dump())

    if isinstance(upload_path, str) and upload_path.strip():
        return {"upload_path": upload_path.strip(), "active_agent": "planner"}
    return {}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_parser(state: MasterAgentState) -> str:
    """LEGACY conditional edge — no longer wired into build_graph()'s topology.
    Kept only because it's still imported/exercised by older tests referencing
    the pre-v1 pipeline. Pre-Upload v1 uses route_after_planner below instead.
    """
    if not is_manifest_minimally_complete(state.cuc):
        return "clarification_node"
    if not state.upload_path:
        return "advise_upload_node"
    return "planning_engine_node"


def route_after_planner(state: MasterAgentState) -> str:
    """Pre-Upload v1 Architecture (Task 8): conditional edge reading
    ConversationPlan.action (set by conversation_planner_node) instead of a
    raw confidence float.

    - action == 'recommend_upload' → upload_gate_node (park, awaiting file)
    - any other action (ask/summarize/confirm)  → response_writer_node
      (renders the text, then itself pauses via interrupt() for the next
      user turn — see response_writer_node's docstring)
    - action == 'wait' should not normally reach here (turn<=0 only happens
      before any node runs), but falls through to response_writer_node
      defensively rather than crashing.
    """
    plan = state.conversation_plan
    action = plan.get("action") if isinstance(plan, dict) else getattr(plan, "action", None)
    if action == "recommend_upload":
        return "upload_gate_node"
    return "response_writer_node"


def route_agent(state: MasterAgentState) -> str:
    """LEGACY conditional edge — no longer wired into build_graph()'s topology.
    Kept only because it's still imported by older tests that reference the
    pre-Task-14 pipeline (plan_steps-driven routing). The new post-upload
    topology is a linear chain, no plan_steps needed."""
    if not state.plan_steps or state.current_step_index >= len(state.plan_steps):
        return END
    target = state.plan_steps[state.current_step_index].get("target_agent", "scout")
    if target == "scout":
        return "scout_agent_node"
    elif target == "platform":
        return "platform_agent_node"
    elif target == "memory":
        return "memory_agent_node"
    return "scout_agent_node"


def route_after_evaluator(state: MasterAgentState) -> str:
    """LEGACY conditional edge — no longer wired into build_graph()'s topology."""
    if not state.plan_steps or state.current_step_index >= len(state.plan_steps):
        return END
    target = state.plan_steps[state.current_step_index].get("target_agent", "scout")
    if target == "platform":
        return "platform_agent_node"
    elif target == "memory":
        return "memory_agent_node"
    return "scout_agent_node"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(with_checkpointer: bool = True):
    """Build and compile the master LangGraph StateGraph.

    Args:
        with_checkpointer: If True, attaches a SqliteSaver checkpointer
            (persists threads across Flask auto-reloads). Falls back to
            MemorySaver if SqliteSaver is unavailable.
    """
    workflow = StateGraph(MasterAgentState)

    # ══════════════════════════════════════════════════════════════════════
    # PRE-UPLOAD CHAIN (unchanged from Task 8)
    # ══════════════════════════════════════════════════════════════════════
    # NOTE: the node registered under the name "conversation_parser_node" is
    # actually conversation_manager_node (the first node of the pre-upload
    # 6-node chain). The name is preserved because /api/agent/seed's
    # update_state(as_node="conversation_parser_node") depends on it.
    workflow.add_node("conversation_parser_node", conversation_manager_node)
    workflow.add_node("intent_extraction_node", intent_extraction_node)
    workflow.add_node("contract_manager_node", contract_manager_node)
    workflow.add_node("conversation_planner_node", conversation_planner_node)
    workflow.add_node("response_writer_node", response_writer_node)
    workflow.add_node("upload_gate_node", upload_gate_node)

    # ══════════════════════════════════════════════════════════════════════
    # POST-UPLOAD CHAIN (Task 14 wiring — Scout 8-node split + HITL + Lock + Workflow + Platform)
    # ══════════════════════════════════════════════════════════════════════
    # Scout 8+1 nodes (Tasks 2-10)
    workflow.add_node("archive_discovery_node", archive_discovery_node)
    workflow.add_node("structure_analysis_node", structure_analysis_node)
    workflow.add_node("entity_analysis_node", entity_analysis_node)
    workflow.add_node("relationship_analysis_node", relationship_analysis_node)
    workflow.add_node("temporal_analysis_node", temporal_analysis_node)
    workflow.add_node("feature_analysis_node", feature_analysis_node)
    workflow.add_node("quality_analysis_node", quality_analysis_node)
    workflow.add_node("statistical_analysis_node", statistical_analysis_node)
    workflow.add_node("exploration_synthesizer_node", exploration_synthesizer_node)

    # HITL + Pipeline Lock + Workflow Planner (Tasks 13, 11, 12)
    workflow.add_node("hitl_node", hitl_node)
    workflow.add_node("pipeline_lock_node", pipeline_lock_node)
    workflow.add_node("workflow_planner_node", workflow_planner_node)

    # Platform + Memory (unchanged, terminal stages of the new chain)
    workflow.add_node("platform_agent_node", platform_agent_node)
    workflow.add_node("memory_agent_node", memory_agent_node)

    # ══════════════════════════════════════════════════════════════════════
    # EDGES
    # ══════════════════════════════════════════════════════════════════════

    # --- Entry & Pre-Upload chain ---
    workflow.add_edge(START, "conversation_parser_node")
    workflow.add_edge("conversation_parser_node", "intent_extraction_node")
    workflow.add_edge("intent_extraction_node", "contract_manager_node")
    workflow.add_edge("contract_manager_node", "conversation_planner_node")

    workflow.add_conditional_edges(
        "conversation_planner_node",
        route_after_planner,
        {
            "response_writer_node": "response_writer_node",
            "upload_gate_node": "upload_gate_node",
        },
    )
    # response_writer_node interrupts for the user's next message, then loops
    # back to re-run the full pre-upload chain with the new message.
    workflow.add_edge("response_writer_node", "conversation_parser_node")

    # --- Bridge: upload_gate parks; on resume with an upload_path, dive into Scout ---
    workflow.add_edge("upload_gate_node", "archive_discovery_node")

    # --- Post-Upload: linear 8-node Scout analysis chain ---
    workflow.add_edge("archive_discovery_node", "structure_analysis_node")
    workflow.add_edge("structure_analysis_node", "entity_analysis_node")
    workflow.add_edge("entity_analysis_node", "relationship_analysis_node")
    workflow.add_edge("relationship_analysis_node", "temporal_analysis_node")
    workflow.add_edge("temporal_analysis_node", "feature_analysis_node")
    workflow.add_edge("feature_analysis_node", "quality_analysis_node")
    workflow.add_edge("quality_analysis_node", "statistical_analysis_node")
    workflow.add_edge("statistical_analysis_node", "exploration_synthesizer_node")

    # --- Synthesizer → HITL → Lock → Workflow → Platform → Memory → END ---
    workflow.add_edge("exploration_synthesizer_node", "hitl_node")
    workflow.add_edge("hitl_node", "pipeline_lock_node")
    workflow.add_edge("pipeline_lock_node", "workflow_planner_node")
    workflow.add_edge("workflow_planner_node", "platform_agent_node")
    workflow.add_edge("platform_agent_node", "memory_agent_node")
    workflow.add_edge("memory_agent_node", END)

    if with_checkpointer:
        try:
            # SqliteSaver: persists threads across Flask auto-reloads (debug=True)
            # so multi-request conversations survive backend restarts.
            # *.db is already in .gitignore.
            #
            # NOTE: SqliteSaver.from_conn_string() returns a *context manager*,
            # not a saver. For a long-lived, module-level graph singleton we
            # instead open a persistent connection and construct SqliteSaver(conn)
            # directly. check_same_thread=False is required because Flask serves
            # requests on multiple worker threads that share this one graph.
            #
            # Import lazily so the graph still builds (falling back to
            # MemorySaver below) when langgraph-checkpoint-sqlite isn't
            # installed — the module-level import would otherwise break the
            # entire aiconnex_agent package rather than degrade gracefully.
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3

            _db_dir = os.path.join(
                os.path.dirname(__file__), "..", "backend", "data", "sessions"
            )
            os.makedirs(_db_dir, exist_ok=True)
            _db_path = os.path.join(_db_dir, "agent_checkpoints.sqlite")
            _conn = sqlite3.connect(_db_path, check_same_thread=False)
            saver = SqliteSaver(_conn)
            logger.info(f"[Graph] Compiled with SqliteSaver at {_db_path}")
            return workflow.compile(checkpointer=saver)
        except Exception as exc:
            logger.warning(f"[Graph] SqliteSaver unavailable ({exc}), falling back to MemorySaver.")
            from langgraph.checkpoint.memory import MemorySaver
            return workflow.compile(checkpointer=MemorySaver())
    return workflow.compile()
