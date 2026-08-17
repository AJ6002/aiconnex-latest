"""
agentic/platform_kb/documentation_service.py

Documentation and Performance Specification Knowledge Service for AIConnex (Sprint 7).
Provides:
- Deterministic access to the 22 Authoritative Product Specifications
- Component-level specification lookup (e.g., ScoutAgent, DataStudioCompiler)
- Granular performance SLA and latency quota querying
- State machine transition contract validation
- Automated compliance evaluation for Judge Agent / Plan Evaluator
- PostgreSQL multi-tenant synchronization
"""

import os
import json
import yaml
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from agentic.platform_kb.schemas import (
    DocumentationSpecRecord,
    PerformanceSLARecord,
    StateTransitionRecord,
    ComplianceAuditReport,
)
from agentic.platform_kb.db_client import KBInfraClient

logger = logging.getLogger(__name__)

SPECS_YAML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "03_deterministic",
    "registries",
    "documentation_specs.yaml",
)
SLAS_YAML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "03_deterministic",
    "registries",
    "performance_slas.yaml",
)


class DocumentationService:
    """
    Authoritative Service for Product Specifications, SLAs, and Behavioral Contracts.
    Replaces ad-hoc documentation scraping with deterministic, verified system truth.
    """

    def __init__(
        self,
        specs_file: Optional[str] = None,
        slas_file: Optional[str] = None,
        db_client: Optional[KBInfraClient] = None,
    ):
        self.specs_file = specs_file or SPECS_YAML_PATH
        self.slas_file = slas_file or SLAS_YAML_PATH
        self.db_client = db_client or KBInfraClient()

        self.specs: Dict[str, DocumentationSpecRecord] = {}
        self.slas: Dict[str, PerformanceSLARecord] = {}
        self.component_to_specs: Dict[str, List[str]] = {}

        self._load_registries()

    def _load_registries(self) -> None:
        """Loads and validates specs and SLAs from YAML registries."""
        if os.path.exists(self.specs_file):
            try:
                with open(self.specs_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for item in data.get("specs", []):
                    rec = DocumentationSpecRecord(**item)
                    self.specs[rec.spec_id] = rec
                    for comp in rec.target_subsystems:
                        self.component_to_specs.setdefault(comp.lower(), []).append(rec.spec_id)
                logger.info(f"Loaded {len(self.specs)} Documentation Spec records into DocumentationService.")
            except Exception as e:
                logger.error(f"Failed to load documentation specs from {self.specs_file}: {e}")

        if os.path.exists(self.slas_file):
            try:
                with open(self.slas_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for item in data.get("slas", []):
                    rec = PerformanceSLARecord(**item)
                    self.slas[rec.sla_id] = rec
                logger.info(f"Loaded {len(self.slas)} Performance SLA records into DocumentationService.")
            except Exception as e:
                logger.error(f"Failed to load performance SLAs from {self.slas_file}: {e}")

    # ─── Query Operations ─────────────────────────────────────────────────────────

    def get_spec(self, spec_id: str) -> Optional[DocumentationSpecRecord]:
        """Retrieves a single specification record by ID."""
        return self.specs.get(spec_id)

    def list_specs(self) -> List[DocumentationSpecRecord]:
        """Returns all registered product specification records."""
        return list(self.specs.values())

    def get_specs_for_component(self, component_name: str) -> List[DocumentationSpecRecord]:
        """Retrieves all specifications governing a particular system component or agent."""
        spec_ids = self.component_to_specs.get(component_name.lower(), [])
        return [self.specs[sid] for sid in spec_ids if sid in self.specs]

    def get_specs_by_category(self, category: str) -> List[DocumentationSpecRecord]:
        """Retrieves all specifications within a category (e.g. Performance, Architecture)."""
        return [s for s in self.specs.values() if s.category.lower() == category.lower()]

    def get_specs_by_studio(self, studio: str) -> List[DocumentationSpecRecord]:
        """Retrieves all specifications for a studio (DataStudio, MLStudio, AgenticStudio)."""
        return [s for s in self.specs.values() if s.studio.lower() == studio.lower()]

    def get_performance_slas(self, component_name: Optional[str] = None) -> List[PerformanceSLARecord]:
        """Retrieves SLAs for a component, or all SLAs across the system."""
        if not component_name:
            return list(self.slas.values())
        comp_lower = component_name.lower()

        # 1. Direct match on component_name
        direct_slas = [s for s in self.slas.values() if s.component_name.lower() == comp_lower]
        if direct_slas:
            return direct_slas

        # 2. Match via governed target_subsystems in specs
        spec_ids = self.component_to_specs.get(comp_lower, [])
        governed_slas = []
        for sid in spec_ids:
            spec = self.specs.get(sid)
            if spec:
                governed_slas.extend(spec.governing_slas)

        if governed_slas:
            return governed_slas

        # 3. Global fallback
        return [s for s in self.slas.values() if s.component_name.lower() in ["coreengine", "platformcore", "masterplatformkernel"]]

    def get_state_transitions(self, feature_or_agent: Optional[str] = None) -> List[StateTransitionRecord]:
        """Retrieves state machine transition rules for an agent or feature."""
        transitions = []
        for spec in self.specs.values():
            for t in spec.state_transitions:
                if not feature_or_agent or t.feature_or_agent.lower() == feature_or_agent.lower():
                    transitions.append(t)
        return transitions

    # ─── Automated Compliance Evaluation ─────────────────────────────────────────

    def verify_compliance(self, component_name: str, metrics: Dict[str, Any]) -> ComplianceAuditReport:
        """
        Audits reported execution metrics (e.g., latency, memory, throughput) against
        authoritative performance SLAs defined in the specifications.
        """
        slas = self.get_performance_slas(component_name)
        if not slas:
            # Check global fallback SLAs
            slas = [s for s in self.slas.values() if s.component_name.lower() in ["coreengine", "platformcore"]]

        total_checked = 0
        passed = 0
        breached = 0
        breaches = []

        for sla in slas:
            metric_val = metrics.get(sla.metric_name)
            if metric_val is None:
                continue

            total_checked += 1
            is_valid = True

            try:
                val = float(metric_val)
                target = float(sla.target_value)

                if sla.comparison_op == "<=" and not (val <= target):
                    is_valid = False
                elif sla.comparison_op == "<" and not (val < target):
                    is_valid = False
                elif sla.comparison_op == ">=" and not (val >= target):
                    is_valid = False
                elif sla.comparison_op == ">" and not (val > target):
                    is_valid = False
                elif sla.comparison_op == "==" and not (val == target):
                    is_valid = False
            except (ValueError, TypeError):
                is_valid = False

            if is_valid:
                passed += 1
            else:
                breached += 1
                breaches.append({
                    "sla_id": sla.sla_id,
                    "metric_name": sla.metric_name,
                    "reported_value": metric_val,
                    "target_value": sla.target_value,
                    "comparison_op": sla.comparison_op,
                    "unit": sla.unit,
                    "severity": sla.severity_on_breach,
                    "workload_condition": sla.workload_condition,
                    "source_spec_id": sla.source_spec_id,
                })

        return ComplianceAuditReport(
            component_name=component_name,
            is_compliant=(breached == 0),
            total_slas_checked=total_checked,
            slas_passed=passed,
            slas_breached=breached,
            breaches=breaches,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ─── PostgreSQL Synchronization ───────────────────────────────────────────────

    def sync_to_postgres(self) -> int:
        """
        Provisions tables and synchronizes all documentation specifications and SLAs to PostgreSQL.
        """
        try:
            conn = self.db_client.get_postgres_connection()
            cur = conn.cursor()

            # Create tables
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documentation (
                    spec_id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    studio VARCHAR(64) NOT NULL,
                    category VARCHAR(64) NOT NULL,
                    target_subsystems JSONB NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL,
                    governing_slas JSONB NOT NULL DEFAULT '[]',
                    state_transitions JSONB NOT NULL DEFAULT '[]',
                    error_contracts JSONB NOT NULL DEFAULT '[]',
                    acceptance_criteria JSONB NOT NULL DEFAULT '[]',
                    source_document_path VARCHAR(255) NOT NULL,
                    authority VARCHAR(8) NOT NULL DEFAULT 'A',
                    status VARCHAR(32) NOT NULL DEFAULT 'Approved',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_performance_slas (
                    sla_id VARCHAR(64) PRIMARY KEY,
                    component_name VARCHAR(128) NOT NULL,
                    metric_name VARCHAR(128) NOT NULL,
                    target_value DOUBLE PRECISION NOT NULL,
                    unit VARCHAR(32) NOT NULL,
                    comparison_op VARCHAR(8) NOT NULL DEFAULT '<=',
                    workload_condition TEXT NOT NULL DEFAULT 'default',
                    severity_on_breach VARCHAR(32) NOT NULL DEFAULT 'critical',
                    source_spec_id VARCHAR(64) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            # Upsert Specs
            for spec in self.specs.values():
                cur.execute(
                    """
                    INSERT INTO knowledge_documentation (
                        spec_id, title, studio, category, target_subsystems,
                        summary, governing_slas, state_transitions, error_contracts,
                        acceptance_criteria, source_document_path, authority, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (spec_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        studio = EXCLUDED.studio,
                        category = EXCLUDED.category,
                        target_subsystems = EXCLUDED.target_subsystems,
                        summary = EXCLUDED.summary,
                        governing_slas = EXCLUDED.governing_slas,
                        state_transitions = EXCLUDED.state_transitions,
                        error_contracts = EXCLUDED.error_contracts,
                        acceptance_criteria = EXCLUDED.acceptance_criteria,
                        source_document_path = EXCLUDED.source_document_path,
                        authority = EXCLUDED.authority,
                        status = EXCLUDED.status;
                    """,
                    (
                        spec.spec_id,
                        spec.title,
                        spec.studio,
                        spec.category,
                        json.dumps(spec.target_subsystems),
                        spec.summary,
                        json.dumps([s.model_dump() for s in spec.governing_slas]),
                        json.dumps([t.model_dump() for t in spec.state_transitions]),
                        json.dumps(spec.error_contracts),
                        json.dumps(spec.acceptance_criteria),
                        spec.source_document_path,
                        spec.authority,
                        spec.status,
                    ),
                )

            # Upsert SLAs
            for sla in self.slas.values():
                cur.execute(
                    """
                    INSERT INTO knowledge_performance_slas (
                        sla_id, component_name, metric_name, target_value,
                        unit, comparison_op, workload_condition, severity_on_breach, source_spec_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sla_id) DO UPDATE SET
                        component_name = EXCLUDED.component_name,
                        metric_name = EXCLUDED.metric_name,
                        target_value = EXCLUDED.target_value,
                        unit = EXCLUDED.unit,
                        comparison_op = EXCLUDED.comparison_op,
                        workload_condition = EXCLUDED.workload_condition,
                        severity_on_breach = EXCLUDED.severity_on_breach,
                        source_spec_id = EXCLUDED.source_spec_id;
                    """,
                    (
                        sla.sla_id,
                        sla.component_name,
                        sla.metric_name,
                        sla.target_value,
                        sla.unit,
                        sla.comparison_op,
                        sla.workload_condition,
                        sla.severity_on_breach,
                        sla.source_spec_id,
                    ),
                )

            conn.commit()
            cur.close()
            logger.info(f"Synchronized {len(self.specs)} specifications and {len(self.slas)} SLAs to PostgreSQL.")
            return len(self.specs)
        except Exception as e:
            logger.warning(f"PostgreSQL synchronization skipped or encountered issue: {e}")
            return len(self.specs)
