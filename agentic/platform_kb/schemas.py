"""
aiconnex_agent/platform_kb/schemas.py

Pydantic schemas and data contracts for the AIConnex Platform Knowledge Base.
Defines canonical contracts for:
- KnowledgeSourceRecord (Master Source Register entry)
- KnowledgeDocumentRecord (Document Registry & Versioning)
- KnowledgeChunkRecord (Structural Chunk Definition)
- EvidenceItem & EvidencePack (Authoritative Retrieval Envelopes)
- ContextRequest (Agent Knowledge Query)
- PlatformCapabilities & ManifestRegistryEntry (Deterministic Knowledge)
"""

from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field


# ─── 1. Source Register Contract ──────────────────────────────────────────────

class KnowledgeSourceRecord(BaseModel):
    source_id: str = Field(..., description="Unique source identifier (e.g. PLAT-DOC-001)")
    title: str = Field(..., description="Human-readable title of the source document")
    knowledge_domain: Literal["platform", "industrial", "terminology", "dataset", "ml_methodology", "equipment_asset", "standards_regulatory", "tenant_knowledge", "documentation", "all"] = Field(
        "platform", description="Knowledge domain partition"
    )
    source_type: str = Field(..., description="Type of source (e.g., Architecture Doc, Contract Spec, ADR)")
    source_location: str = Field(..., description="Git repo path or URL of raw source file")
    authority_level: Literal["A", "B", "C"] = Field(
        "A", description="A = Primary/Official system truth, B = Secondary/Reputable, C = Inferred/Internal"
    )
    owner: str = Field("AIConnex Engineering", description="Team or entity maintaining this source")
    tenant_scope: str = Field("global", description="Scope of tenant access (global or tenant_id)")
    license: str = Field("Internal", description="Usage rights or license classification")
    version: str = Field("1.0", description="Source document version")
    status: Literal["Pending", "Approved", "Rejected", "Archived"] = Field(
        "Pending", description="Ingestion gate status - MUST be Approved to ingest"
    )
    approved_at: Optional[str] = Field(None, description="ISO timestamp of review approval")


# ─── 2. Document Registry Contract ────────────────────────────────────────────

class KnowledgeDocumentRecord(BaseModel):
    document_id: str = Field(..., description="Unique document ID (e.g. DOC-PLAT-001-V1)")
    source_id: str = Field(..., description="Foreign key reference to KnowledgeSourceRecord.source_id")
    document_type: str = Field(..., description="Format type (e.g. markdown, pdf, json_ast)")
    title: str = Field(..., description="Document title")
    version: str = Field("1.0", description="Document version number")
    content_hash: str = Field(..., description="SHA-256 hash of original raw content for change tracking")
    storage_uri: str = Field(..., description="MinIO S3 object key (e.g. platform/architecture/doc.md)")
    status: Literal["Active", "Superseded", "Archived"] = "Active"
    effective_from: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_to: Optional[str] = None
    language: str = "en"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── 3. Structural Chunk Contract ─────────────────────────────────────────────

class KnowledgeChunkRecord(BaseModel):
    chunk_id: str = Field(..., description="Unique chunk ID (e.g. CH-PLAT-00231)")
    document_id: str = Field(..., description="Parent document ID")
    version: str = Field("1.0", description="Document version")
    section: str = Field(..., description="Heading or section hierarchy (e.g. Compiler -> Join Engine)")
    subsection: Optional[str] = Field(None, description="Sub-heading if present")
    page_start: Optional[int] = Field(None, description="Start page number if applicable")
    page_end: Optional[int] = Field(None, description="End page number if applicable")
    chunk_index: int = Field(..., description="0-indexed sequence position within document")
    text: str = Field(..., description="Text content of the chunk")
    text_hash: str = Field(..., description="SHA-256 hash of chunk text")
    token_count: int = Field(..., description="Token count estimate")
    authority_level: Literal["A", "B", "C"] = "A"
    status: Literal["Active", "Archived"] = "Active"


# ─── 4. Retrieval Request & Evidence Pack Envelopes ───────────────────────────

class ContextRequest(BaseModel):
    query: str = Field(..., description="Agent question or retrieval prompt")
    knowledge_domain: Literal["platform", "industrial", "terminology", "dataset", "ml_methodology", "equipment_asset", "standards_regulatory", "tenant_knowledge", "documentation", "all"] = "platform"
    knowledge_type: Optional[str] = Field(None, description="Filter tag (e.g., compiler, contracts, architecture)")
    tenant_id: str = Field("global", description="Tenant scope ID")
    project_id: Optional[str] = Field(None, description="Project scope ID within tenant")
    scope: Literal["global", "tenant", "project", "session", "all"] = Field("all", description="Knowledge scope boundary")
    agent_id: Optional[str] = Field(None, description="ID of requesting agent (e.g., ScoutAgent, PreUploadAgent)")
    session_id: Optional[str] = Field(None, description="Active session ID")
    top_k: int = Field(5, ge=1, le=20, description="Max number of vector evidence chunks to return")
    min_score: float = Field(0.60, ge=0.0, le=1.0, description="Minimum vector relevance score threshold")
    include_deterministic: bool = Field(True, description="Whether to include exact YAML/JSON lookups")


class EvidenceItem(BaseModel):
    document_id: str
    source_id: str
    version: str
    section: str
    page: Optional[int] = None
    chunk_id: str
    text: str
    score: float = Field(..., description="Relevance score (0.0 - 1.0)")
    authority: Literal["A", "B", "C"] = "A"


class EvidencePack(BaseModel):
    query: str
    knowledge_domain: str
    retrieval_mode: Literal["exact", "structured", "semantic", "hybrid", "graph_traversal"]
    results: List[EvidenceItem] = Field(default_factory=list)
    deterministic_facts: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(..., description="Audit trace identifier for this retrieval")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def retrieval_strategy(self) -> str:
        """Alias property for backward compatibility with retrieval_strategy references."""
        return self.retrieval_mode


# ─── 5. Deterministic Knowledge Contracts ──────────────────────────────────────

class PlatformCapabilities(BaseModel):
    supported_formats: List[str] = Field(
        default_factory=lambda: ["csv", "xlsx", "parquet", "mat", "tdms", "zip"]
    )
    enabled_agents: List[str] = Field(
        default_factory=lambda: ["PreUploadAgent", "ScoutAgent", "WorkflowPlanner", "PlatformAgent", "MemoryAgent"]
    )
    compiler_stages: List[str] = Field(
        default_factory=lambda: ["discovery", "parser", "assembler", "harvester", "normalizer"]
    )
    ml_supported_dags: List[str] = Field(
        default_factory=lambda: ["DAG_414", "DAG_949"]
    )
    model_export_formats: List[str] = Field(
        default_factory=lambda: ["onnx", "joblib", "pkl"]
    )


class ManifestRegistryEntry(BaseModel):
    manifest_type: str
    schema_version: str
    status: Literal["Active", "Deprecated"] = "Active"
    owner: str = "AIConnex Engineering"
    required_fields: List[str] = Field(default_factory=list)
    parent_manifest_types: List[str] = Field(default_factory=list)


# ─── 6. Terminology KB Data Contracts (Sprint 2) ───────────────────────────────

class CanonicalTermRelation(BaseModel):
    relation_type: Literal["synonym_of", "related_to", "used_for", "same_domain_as", "measured_by"] = Field(
        ..., description="Relationship type distinguishing exact synonyms from related domain concepts"
    )
    target_term_id: str = Field(..., description="Target canonical term ID (e.g. TERM-WQ-TDS)")


class TerminologyTermRecord(BaseModel):
    term_id: str = Field(..., description="Unique term ID (e.g. WQ.TDS or TERM-PHM-RUL)")
    canonical_name: str = Field(..., description="Standardized canonical term name")
    term_type: Literal["measurement", "abbreviation", "business_concept", "industrial_concept", "dataset_column"] = Field(
        "measurement", description="Category of terminology"
    )
    definition: str = Field(..., description="Authoritative definition of the term")
    synonyms: List[str] = Field(default_factory=list, description="Exact synonym strings")
    abbreviations: List[str] = Field(default_factory=list, description="Acronyms or short aliases")
    domain: List[str] = Field(default_factory=list, description="Domain scopes e.g. ['wastewater', 'phm']")
    unit: Optional[Dict[str, Any]] = Field(None, description="Canonical unit dictionary e.g. {'canonical': 'mg/L'}")
    related_terms: List[CanonicalTermRelation] = Field(default_factory=list, description="Typed related concept links")
    parent_concept: Optional[str] = Field(None, description="Broader parent concept ID")
    column_patterns: List[str] = Field(default_factory=list, description="Raw column name patterns e.g. ['tds_mg_l']")
    source: List[str] = Field(default_factory=list, description="Authoritative source references")
    authority: Literal["A", "B", "C"] = "A"
    status: Literal["Approved", "Draft", "Archived"] = "Approved"


class CanonicalTermResolution(BaseModel):
    input_text: str = Field(..., description="Original input query, column name, or phrase")
    match_type: Literal["exact", "alias", "column_pattern", "semantic", "none"] = Field(
        ..., description="Match mechanism used for resolution"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence score")
    term: Optional[TerminologyTermRecord] = Field(None, description="Resolved canonical term record")
    suggested_unit: Optional[str] = Field(None, description="Canonical physical unit symbol")
    suggested_entity_type: Optional[str] = Field(None, description="Inferred entity type e.g. Measurement")


# ─── 7. ML Methodology KB Data Contracts (Sprint 3) ───────────────────────────

class MLMethodRecord(BaseModel):
    method_id: str = Field(..., description="Unique method ID (e.g. ML-PROG-WEIBULL, ML-ANOM-IFOREST)")
    name: str = Field(..., description="Human-readable method name")
    problem_family: Literal[
        "Prognostics", "Forecasting", "Classification",
        "Regression", "Anomaly Detection", "Survival Analysis"
    ] = Field(..., description="High-level CRISP-ML problem family")
    task_type: str = Field(..., description="Specific analytical task type (e.g. RUL estimation)")
    lifecycle_phase: Literal[
        "Data Understanding", "Data Preparation", "Modeling", "Evaluation", "Deployment & Monitoring"
    ] = Field("Modeling", description="CRISP-ML(Q) lifecycle phase")
    
    # 1. Data Requirements
    required_data_structure: List[str] = Field(default_factory=list, description="Data shapes e.g. ['time_series_regular']")
    minimum_sample_size: str = Field("medium_n", description="Qualitative sample size requirement")
    label_requirements: str = Field("unsupervised", description="Label requirements e.g. ['rul_labels']")
    data_compatibility: Dict[str, bool] = Field(default_factory=dict, description="Boolean feature capability flags")
    
    # 2. Preprocessing & Feature Engineering
    recommended_preprocessing: List[str] = Field(default_factory=list, description="Recommended prep steps")
    feature_engineering_patterns: List[str] = Field(default_factory=list, description="Feature extraction patterns")
    
    # 3. Model Characteristics
    model_family: str = Field(..., description="Algorithm family e.g. tree_based, parametric_survival")
    capacity_level: str = Field("medium", description="Model capacity e.g. baseline, high_capacity")
    interpretability: Literal["high", "medium", "low"] = Field("medium", description="Explainability level")
    
    # 4. Evaluation & Validation
    primary_metrics: List[str] = Field(default_factory=list, description="Recommended evaluation metrics")
    validation_patterns: List[str] = Field(default_factory=list, description="Validation schemes e.g. time_series_split")
    canonical_baseline: str = Field("naive_persistence", description="Canonical baseline comparison algorithm")
    
    # 5. Assumptions & Limitations (Anti-Patterns)
    assumptions: List[str] = Field(default_factory=list, description="Mathematical or statistical assumptions")
    limitations: List[str] = Field(default_factory=list, description="Known weaknesses and failure modes")
    anti_patterns: List[str] = Field(default_factory=list, description="Explicit 'When NOT to use' guidance")
    
    # 6. Operational Considerations & References
    resource_profile: Dict[str, str] = Field(default_factory=dict, description="Resource requirements e.g. training_cost")
    source_documents: List[str] = Field(default_factory=list, description="Reference document IDs")
    authority: Literal["A", "B", "C"] = "A"
    status: Literal["Approved", "Draft", "Archived"] = "Approved"


# ─── 8. Equipment & Asset KB Contract (Sprint 4) ──────────────────────────────

class EquipmentRecord(BaseModel):
    equipment_id: str = Field(..., description="Unique canonical equipment ID (e.g. EQP-PUMP-CENTRIFUGAL)")
    name: str = Field(..., description="Canonical equipment name")
    equipment_class: str = Field(..., description="Equipment classification e.g. Pump, Compressor, Valve")
    category: str = Field("Rotating Equipment", description="General equipment category e.g. Rotating, Static, Electrical, Piping")
    standard_ref: str = Field(..., description="Governing standard reference e.g. ISO 2858 / ISO 5199")
    subsystems: List[Dict[str, Any]] = Field(default_factory=list, description="Subsystem definitions with nested components")
    direct_components: List[str] = Field(default_factory=list, description="Direct components attached to equipment")
    monitored_sensors: List[Dict[str, str]] = Field(default_factory=list, description="Sensors and parameters monitoring this equipment")
    failure_modes: List[Dict[str, Any]] = Field(default_factory=list, description="ISO 14224 failure modes and maintenance actions")
    operating_modes: List[str] = Field(default_factory=list, description="Supported operating states")
    source_documents: List[str] = Field(default_factory=list, description="Reference document IDs")
    authority: Literal["A", "B", "C"] = "A"
    status: Literal["Approved", "Draft", "Archived"] = "Approved"


# ─── 9. Standards & Regulatory KB Contract (Sprint 5) ─────────────────────────

class StandardRecord(BaseModel):
    standard_id: str = Field(..., description="Unique canonical standard ID (e.g. STD-ISO-14224)")
    designation: str = Field(..., description="Formal designation (e.g. ISO 14224:2016)")
    title: str = Field(..., description="Full title of the standard or regulation")
    issuing_body: str = Field(..., description="Issuing organization (e.g. ISO, IEC, NIST, EPA, IEEE, API, ISA, VDMA)")
    standard_type: Literal[
        "international_standard", "national_standard", "technical_report",
        "government_standard", "industry_standard", "methodology_framework",
        "companion_specification", "regulatory_guidance"
    ] = Field("international_standard", description="Classification of standard document")
    version: str = Field("1.0", description="Edition or publication year/version")
    publication_date: Optional[str] = Field(None, description="ISO publication date (e.g. 2016-08-01)")
    scope: str = Field(..., description="Core scope and purpose of the standard")
    applicability: List[str] = Field(default_factory=list, description="Domains, equipment families, or processes it governs")
    jurisdiction: str = Field("international", description="Jurisdiction scope (e.g. international, US-federal, EU, industry-wide)")
    key_concepts: List[str] = Field(default_factory=list, description="Key concepts, terms, or parameters defined/governed")
    supersedes: Optional[str] = Field(None, description="Standard ID or designation of prior superseded version")
    superseded_by: Optional[str] = Field(None, description="Standard ID or designation of newer replacement version")
    related_source_ids: List[str] = Field(default_factory=list, description="Foreign keys to KnowledgeSourceRecord in source_register")
    document_available: bool = Field(True, description="True if raw PDF/markdown document exists in local corpus")
    authority: Literal["A", "B", "C"] = Field("A", description="Authority level")
    status: Literal["Approved", "Draft", "Archived"] = Field("Approved", description="Governance status")


# ─── 10. Tenant Knowledge Contracts (Sprint 6) ───────────────────────────────

class TenantRecord(BaseModel):
    """Organization / client company registration."""
    tenant_id: str = Field(..., description="Unique tenant ID (e.g. TENANT-DEMO-ACME)")
    name: str = Field(..., description="Organization name (e.g. Acme Petrochemical Corp)")
    industry: str = Field(..., description="Industry vertical (e.g. Oil & Gas, Power Generation, Chemical)")
    tier: Literal["free", "professional", "enterprise"] = Field("professional", description="Subscription tier")
    status: Literal["active", "suspended", "archived"] = Field("active", description="Tenant account lifecycle status")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")
    custom_glossary: List[str] = Field(default_factory=list, description="Organization-level custom canonical term IDs")
    adopted_standards: List[str] = Field(default_factory=list, description="Standard IDs adopted by this organization")


class ProjectRecord(BaseModel):
    """Plant / site / workspace within a tenant (Primary Data Isolation Boundary)."""
    project_id: str = Field(..., description="Unique project ID (e.g. PROJ-ACME-HOUSTON)")
    tenant_id: str = Field(..., description="Foreign key to TenantRecord.tenant_id")
    name: str = Field(..., description="Human-readable project/plant name")
    plant_type: Optional[str] = Field(None, description="Plant classification (e.g. Refinery, Chemical Plant, WWTP)")
    status: Literal["active", "archived"] = Field("active", description="Project lifecycle status")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")


class TenantAssetRecord(BaseModel):
    """Physical asset instance owned by a tenant project, linked to global equipment taxonomy."""
    asset_id: str = Field(..., description="Unique asset ID (e.g. ASSET-P201A)")
    tenant_id: str = Field(..., description="Foreign key to TenantRecord.tenant_id")
    project_id: str = Field(..., description="Foreign key to ProjectRecord.project_id")
    equipment_id: str = Field(..., description="Foreign key to global EquipmentRecord.equipment_id (e.g. EQP-PUMP-CENTRIFUGAL)")
    tag_number: str = Field(..., description="Plant engineering tag identifier (e.g. P-201A)")
    description: str = Field(..., description="Description of the physical asset")
    location: Optional[str] = Field(None, description="Physical location within plant (e.g. Unit 2, Ground Floor)")
    manufacturer: Optional[str] = Field(None, description="Asset manufacturer (e.g. Flowserve, KSB)")
    model_number: Optional[str] = Field(None, description="Manufacturer model/part number")
    install_date: Optional[str] = Field(None, description="Installation date (ISO format or YYYY-MM-DD)")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary tenant-specific metadata")
    status: Literal["operational", "standby", "decommissioned"] = Field("operational", description="Asset operational state")


class TenantContext(BaseModel):
    """
    Authenticated tenant execution context.
    Passes tenant_id and project_id down to storage, retrieval, and agent DAG execution.
    Acts as the security scaffolding interface for future auth/JWT middleware.
    """
    tenant_id: str = Field(..., description="Active tenant ID")
    project_id: Optional[str] = Field(None, description="Active project ID")
    user_id: Optional[str] = Field(None, description="Authenticated user ID")
    user_role: Optional[str] = Field(None, description="User role in project/tenant")
    scope: Literal["global", "tenant", "project", "session", "all"] = Field("all", description="Active query scope")


# ─── 11. Documentation & Performance Specification Contracts (Sprint 7) ───────

class PerformanceSLARecord(BaseModel):
    """Deterministic SLA and performance constraint extracted from specification documents."""
    sla_id: str = Field(..., description="Unique SLA identifier (e.g. SLA-LATENCY-COMPILER-001)")
    component_name: str = Field(..., description="Governed system component (e.g. DataStudioCompiler, ScoutAgent)")
    metric_name: str = Field(..., description="Target metric (e.g. p95_latency_ms, max_memory_mb, throughput_rows_sec)")
    target_value: float = Field(..., description="Numeric boundary value")
    unit: str = Field(..., description="Metric engineering unit (e.g. ms, MB, rows/sec, %)")
    comparison_op: Literal["<=", ">=", "==", "<", ">"] = Field("<=", description="Constraint comparison operator")
    workload_condition: str = Field("default", description="Workload or operational regime under which this SLA applies")
    severity_on_breach: Literal["critical", "warning", "info"] = Field("critical", description="Failure severity if violated")
    source_spec_id: str = Field(..., description="Reference to originating DocumentationSpecRecord")


class StateTransitionRecord(BaseModel):
    """State machine transition rule governing an agent or studio pipeline node."""
    transition_id: str = Field(..., description="Unique transition rule ID")
    feature_or_agent: str = Field(..., description="Target agent, studio, or state machine name")
    from_state: str = Field(..., description="Source state name")
    to_state: str = Field(..., description="Target state name")
    trigger_event: str = Field(..., description="Event or condition initiating transition")
    guard_condition: Optional[str] = Field(None, description="Boolean constraint required to permit transition")
    is_terminal: bool = Field(False, description="True if target state terminates execution")
    source_spec_id: str = Field(..., description="Reference to originating DocumentationSpecRecord")


class DocumentationSpecRecord(BaseModel):
    """Authoritative Product Performance and Specification Document Model."""
    spec_id: str = Field(..., description="Unique spec document identifier (e.g. DOC-SPEC-001)")
    title: str = Field(..., description="Full human-readable specification title")
    studio: Literal["DataStudio", "MLStudio", "AgenticStudio", "PlatformCore", "CrossStudio"] = Field("PlatformCore", description="Associated studio subsystem")
    category: Literal["Performance", "Architecture", "DataContract", "StateTransition", "Security", "Evaluation", "Visualization"] = Field("Performance", description="Specification category")
    target_subsystems: List[str] = Field(default_factory=list, description="List of system components governed by this specification")
    summary: str = Field(..., description="Executive summary of the specification")
    governing_slas: List[PerformanceSLARecord] = Field(default_factory=list, description="Hard quantifiable performance SLAs")
    state_transitions: List[StateTransitionRecord] = Field(default_factory=list, description="Permitted state machine transitions")
    error_contracts: List[Dict[str, str]] = Field(default_factory=list, description="Standard error codes, exceptions, and recovery policies")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Specific criteria required to verify conformance")
    cross_references: List[str] = Field(default_factory=list, description="Related specification or standard document IDs")
    source_document_path: str = Field(..., description="Path to raw source file in corpus")
    authority: Literal["A", "B", "C"] = Field("A", description="Authority level (A = Official System Truth)")
    status: Literal["Approved", "Draft", "Archived"] = Field("Approved", description="Governance status")


class ComplianceAuditReport(BaseModel):
    """Audit result verifying a plan, codebase change, or benchmark run against performance specs."""
    component_name: str
    is_compliant: bool
    total_slas_checked: int
    slas_passed: int
    slas_breached: int
    breaches: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())





