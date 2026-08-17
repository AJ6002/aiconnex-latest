"""
aiconnex_agent/state.py - Master LangGraph State Definition
===========================================================
Defines the MasterAgentState Pydantic model integrating the 5-stage contract pipeline.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agentic.schemas import (
    ConversationUnderstandingContract,
    ScoutEnrichedContract,
    PreCompilerContract,
    DatasetIntelligenceContract,
    ConversationPlan,
    UploadReadinessContract,
    ArchiveManifest,
    StructureAnalysis,
    EntityInventory,
    RelationshipGraph,
    TemporalStructure,
    FeatureCatalogV2,
    QualityAssessment,
    StatisticalProfile,
    DatasetExplorationManifest,
    PipelineLockManifest,
    WorkflowManifest,
)


class MasterAgentState(BaseModel):
    """Master State for LangGraph Orchestration."""
    # session_id is generated once at state construction and never mutated.
    # It is the stable key for the event-sourced memory audit log and for
    # Scout's compiled-output directory — both must use the same ID across
    # every node execution in a single conversation (Bug #2 fix).
    session_id: str = Field(
        default_factory=lambda: f"wf_{uuid.uuid4().hex[:8]}",
        description="Stable session identifier, generated once at state creation. Used as the workflow_id for the event-sourced memory log and Scout's output directory.",
    )
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Chat message history")
    cuc: ConversationUnderstandingContract = Field(default_factory=ConversationUnderstandingContract, description="Stage 1: Pre-Upload CUC")
    conversation_plan: Optional[ConversationPlan] = Field(default=None, description="Pre-Upload v1: latest decision from conversation_planner_node")
    upload_readiness: Optional[UploadReadinessContract] = Field(default=None, description="Pre-Upload v1: formal readiness artifact, set once the planner recommends upload")
    latest_extraction: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pre-Upload v1: transient handoff of THIS turn's raw extraction dict from "
                     "intent_extraction_node to contract_manager_node. Not a persisted artifact — "
                     "cleared/overwritten each turn, unlike cuc which accumulates across turns.",
    )
    response_text: Optional[str] = Field(
        default=None,
        description="Pre-Upload v1: natural-language text produced by response_writer_node for "
                     "the current turn, rendering whatever conversation_planner_node decided "
                     "(ask/summarize/confirm). This is the node's externally-visible output — "
                     "the surface a chat UI/SSE layer reads to show the user something.",
    )

    # --- Scout 8-node split intermediate artifacts (Tasks 2-10) ---
    # Each Scout analysis node writes its own typed section here for per-stage
    # observability via GET /api/agent/state. The synthesizer combines them
    # into `dataset_exploration_manifest` and also populates the legacy `dic`
    # for backward compatibility with hitl_flow / platform_node / manifest_builder.
    archive_manifest: Optional[ArchiveManifest] = Field(default=None)
    structure_analysis: Optional[StructureAnalysis] = Field(default=None)
    entity_inventory: Optional[EntityInventory] = Field(default=None)
    relationship_graph: Optional[RelationshipGraph] = Field(default=None)
    temporal_structure: Optional[TemporalStructure] = Field(default=None)
    feature_catalog_v2: Optional[FeatureCatalogV2] = Field(default=None)
    quality_assessment: Optional[QualityAssessment] = Field(default=None)
    statistical_profile: Optional[StatisticalProfile] = Field(default=None)
    dataset_exploration_manifest: Optional[DatasetExplorationManifest] = Field(default=None)

    # --- HITL + Pipeline Lock (Tasks 11 + 13) ---
    # hitl_contract is populated by hitl_node (Task 13); pipeline_lock is set
    # by pipeline_lock_node (Task 11) immediately after HITL completes and
    # freezes the decision as an immutable audit boundary.
    hitl_contract: Optional[Any] = Field(
        default=None,
        description="HITLContract from chatbot/backend/hitl_schemas — kept as Any to avoid a cross-package "
                     "import at state-definition time",
    )
    pipeline_lock: Optional[PipelineLockManifest] = Field(default=None)

    # --- Workflow Planner (Task 12) ---
    # Derived from pipeline_lock; describes the technical execution DAG the
    # Compiler + Platform Agent will run. Regeneratable (unlike pipeline_lock
    # which is immutable) since it's downstream of the frozen decision.
    workflow_manifest: Optional[WorkflowManifest] = Field(default=None)
    scout_enriched: ScoutEnrichedContract = Field(default_factory=ScoutEnrichedContract, description="Stage 2: During Upload Scout Enriched")
    pre_compiler: PreCompilerContract = Field(default_factory=PreCompilerContract, description="Stage 3: Pre-Compiler Contract")
    dic: DatasetIntelligenceContract = Field(default_factory=DatasetIntelligenceContract, description="Stage 4 & 5: Post-Compiler DIC")
    upload_path: Optional[str] = Field(default=None, description="Filesystem path to the real uploaded dataset archive/file, set by the caller before graph invocation (Phase 5b gap 1)")
    active_agent: Optional[str] = Field(default="parser", description="Current active agent/node name")
    current_step_index: int = Field(default=0, description="Step pointer in multi-agent execution plan")
    plan_steps: List[Dict[str, Any]] = Field(default_factory=list, description="List of planned task steps")
    confidence_score: float = Field(default=1.0, description="Overall parser/routing confidence score [0.0 - 1.0]")
    interrupt_reason: Optional[str] = Field(default=None, description="Reason for HITL interrupt if paused")
    memory_context: Dict[str, Any] = Field(default_factory=dict, description="Session and memory bank context")
    candidate_recipes: List[Dict[str, Any]] = Field(default_factory=list, description="Resolved candidate DAG recipes for parallel training")
    oof_predictions: Dict[str, Any] = Field(default_factory=dict, description="Out-of-fold CV prediction matrices keyed by recipe_id")
    scorer_reports: List[Dict[str, Any]] = Field(default_factory=list, description="ScorerAgent metric reports per candidate")
    judge_reports: List[Dict[str, Any]] = Field(default_factory=list, description="JudgeAgent qualitative reports per candidate")
    selection_result: Dict[str, Any] = Field(default_factory=dict, description="SelectionResult from SelectorAgent MCDA")

