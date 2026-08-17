"""
aiconnex_agent/platform_kb/context_builder.py

Context Builder Interface for AIConnex Agent Integration.
Acts as the single context facade for all agents (PreUploadAgent, ScoutAgent, WorkflowPlanner, etc.).
Converts EvidencePack items into formatted LLM system/user prompts and deterministic rule payloads.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, Literal, List

from agentic.platform_kb.schemas import ContextRequest, EvidencePack
from agentic.platform_kb.retrieval_service import RetrievalService
from agentic.platform_kb.terminology_service import TerminologyService
from agentic.platform_kb.methodology_service import MethodologyService
from agentic.platform_kb.equipment_service import EquipmentService
from agentic.platform_kb.standards_service import StandardsService
from agentic.platform_kb.tenant_service import TenantService
from agentic.platform_kb.documentation_service import DocumentationService

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Unified Agent Context Builder.
    Replaces all direct database and registry calls in AIConnex agents.
    Provides `get_context(ContextRequest)` to return formatted LLM prompt context and deterministic facts.
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        terminology_service: Optional[TerminologyService] = None,
        methodology_service: Optional[MethodologyService] = None,
        equipment_service: Optional[EquipmentService] = None,
        standards_service: Optional[StandardsService] = None,
        tenant_service: Optional[TenantService] = None,
        documentation_service: Optional[DocumentationService] = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService()
        self.terminology_service = terminology_service or TerminologyService()
        self.methodology_service = methodology_service or MethodologyService()
        self.equipment_service = equipment_service or EquipmentService()
        self.standards_service = standards_service or StandardsService()
        self.tenant_service = tenant_service or TenantService()
        self.documentation_service = documentation_service or DocumentationService()

    def get_tenant_context(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        tag_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns tenant-scoped knowledge: org profile, project assets,
        tag resolutions, and full multi-tier cross-scope equipment/standards context.
        """
        # Case 1: Specific asset ID requested
        if asset_id:
            return self.tenant_service.get_asset_with_global_context(asset_id)

        # Case 2: Tag number resolution
        if tag_number:
            asset = self.tenant_service.resolve_tag_to_asset(tenant_id, tag_number, project_id=project_id)
            if not asset:
                return {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "tag_number": tag_number,
                    "found": False,
                    "message": f"Asset tag '{tag_number}' not found in tenant '{tenant_id}'."
                }
            return self.tenant_service.get_asset_with_global_context(asset.asset_id)

        # Case 3: Project-level assets
        if project_id:
            project = self.tenant_service.get_project(project_id)
            if not project or project.tenant_id != tenant_id:
                return {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "found": False,
                    "message": f"Project '{project_id}' not found for tenant '{tenant_id}'."
                }
            assets = self.tenant_service.get_assets_for_project(tenant_id, project_id)
            return {
                "found": True,
                "project": project.model_dump(),
                "assets_count": len(assets),
                "assets": [a.model_dump() for a in assets],
            }

        # Case 4: Tenant-level profile & projects
        tenant = self.tenant_service.get_tenant(tenant_id)
        if not tenant:
            return {
                "tenant_id": tenant_id,
                "found": False,
                "message": f"Tenant '{tenant_id}' not found."
            }

        projects = self.tenant_service.get_projects_for_tenant(tenant_id)
        return {
            "found": True,
            "tenant": tenant.model_dump(),
            "projects_count": len(projects),
            "projects": [p.model_dump() for p in projects],
        }

    def get_standards_context(
        self,
        standard_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        concept: Optional[str] = None,
        issuing_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns governing standards, regulatory requirements, scope, and applicability.
        """
        if standard_id:
            std = self.standards_service.get_standard(standard_id)
            if not std:
                return {"standard_id": standard_id, "found": False}
            return {
                "found": True,
                "standard": std.model_dump(),
                "governing_body": std.issuing_body,
                "applicability": std.applicability,
                "key_concepts": std.key_concepts,
            }

        if equipment_id:
            stds = self.standards_service.get_applicable_standards(equipment_id)
            return {
                "equipment_id": equipment_id,
                "applicable_standards_count": len(stds),
                "standards": [s.model_dump() for s in stds],
            }

        if concept:
            stds = self.standards_service.get_governing_standards(concept)
            return {
                "concept": concept,
                "governing_standards_count": len(stds),
                "standards": [s.model_dump() for s in stds],
            }

        if issuing_body:
            stds = self.standards_service.get_standards_by_body(issuing_body)
            return {
                "issuing_body": issuing_body,
                "count": len(stds),
                "standards": [s.model_dump() for s in stds],
            }

        return {"found": False, "message": "No query parameters provided for standards lookup."}

    def get_documentation_context(
        self,
        spec_id: Optional[str] = None,
        component_name: Optional[str] = None,
        studio: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns authoritative product specifications, SLAs, error contracts, and state machines.
        """
        if spec_id:
            spec = self.documentation_service.get_spec(spec_id)
            if not spec:
                return {"spec_id": spec_id, "found": False}
            return {
                "found": True,
                "spec": spec.model_dump(),
                "governing_slas": [s.model_dump() for s in spec.governing_slas],
                "state_transitions": [t.model_dump() for t in spec.state_transitions],
                "error_contracts": spec.error_contracts,
                "acceptance_criteria": spec.acceptance_criteria,
            }

        if component_name:
            specs = self.documentation_service.get_specs_for_component(component_name)
            slas = self.documentation_service.get_performance_slas(component_name)
            return {
                "found": len(specs) > 0,
                "component_name": component_name,
                "specs_count": len(specs),
                "specs": [s.model_dump() for s in specs],
                "slas": [s.model_dump() for s in slas],
            }

        if studio:
            specs = self.documentation_service.get_specs_by_studio(studio)
            return {
                "found": len(specs) > 0,
                "studio": studio,
                "specs_count": len(specs),
                "specs": [s.model_dump() for s in specs],
            }

        if category:
            specs = self.documentation_service.get_specs_by_category(category)
            return {
                "found": len(specs) > 0,
                "category": category,
                "specs_count": len(specs),
                "specs": [s.model_dump() for s in specs],
            }

        return {"found": False, "message": "No query parameters provided for documentation lookup."}

    def audit_plan_compliance(
        self,
        component_name: str,
        reported_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Audits a proposed architecture plan or runtime benchmark metrics against
        the official specification SLAs. Used by Judge Agent for automated compliance gating.
        """
        report = self.documentation_service.verify_compliance(component_name, reported_metrics)
        return report.model_dump()

    def get_equipment_context(
        self,
        equipment_id: str,
    ) -> Dict[str, Any]:
        """
        Returns canonical equipment topology, subsystems, monitored sensors, and ISO 14224 failure modes.
        """
        eq = self.equipment_service.get_equipment(equipment_id)
        if not eq:
            return {"equipment_id": equipment_id, "found": False}

        return {
            "found": True,
            "equipment": eq.model_dump(),
            "failure_modes": self.equipment_service.get_failure_modes(equipment_id),
            "monitored_sensors": self.equipment_service.get_monitored_sensors(equipment_id),
        }

    def get_methodology_context(
        self,
        problem_family: str,
        data_characteristics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Returns applicable ML methods, baselines, and anti-patterns for a problem family and dataset profile.
        """
        methods = self.methodology_service.get_applicable_methods(problem_family, data_characteristics)
        baselines = self.methodology_service.recommend_baselines(problem_family)
        return {
            "problem_family": problem_family,
            "applicable_methods": [m.model_dump() for m in methods],
            "recommended_baselines": baselines,
        }

    def get_terminology_context(self, input_text: str) -> Dict[str, Any]:
        """
        Resolves terminology for a column header, acronym, or user phrase.
        """
        res_col = self.terminology_service.resolve_column(input_text)
        if res_col.match_type != "none":
            return res_col.model_dump()

        res_term = self.terminology_service.resolve_term(input_text)
        if res_term.match_type != "none":
            return res_term.model_dump()

        res_phrases = self.terminology_service.resolve_phrase(input_text)
        if res_phrases:
            return res_phrases[0].model_dump()

        return {"input_text": input_text, "match_type": "none", "confidence": 0.0}

    def _extract_potential_tags(self, query: str) -> List[str]:
        """
        Extracts candidate plant equipment tag identifiers from natural language queries.
        Matches patterns like 'P-201A', 'P-2971', 'K-101', 'V-301', 'WWTP-PACKAGE'.
        """
        matches = re.findall(r"\b([A-Z]{1,4}-\d{2,5}[A-Z]?)\b", query.upper())
        return list(dict.fromkeys(matches))

    def format_evidence_for_llm(self, pack: EvidencePack) -> str:
        """
        Formats EvidencePack results into markdown context block ready for LLM prompt injection,
        with strict closed-world grounding and tenant override directives.
        """
        if not pack.results and not pack.deterministic_facts:
            return ""

        lines = [
            f"### RETRIEVED KNOWLEDGE EVIDENCE (Domain: {pack.knowledge_domain.upper()} | Trace ID: {pack.trace_id})",
            "",
            "#### 🛡️ STRICT GROUNDING & PRECEDENCE DIRECTIVES:",
            "1. **TENANT OVERRIDE**: Client/Tenant-specific asset metadata, custom operating limits, and tenant SOPs strictly SUPERSEDE global reference standards.",
            "2. **CLOSED-WORLD BOUNDARY**: If an asset tag, sensor, or operating parameter is marked 'NOT_FOUND' or 'UNKNOWN', explicitly state that it is not registered. NEVER infer or extrapolate unlisted specifications.",
            "",
        ]

        # 1. Render Tenant Resolved Assets if present
        tenant_asset_facts = {k: v for k, v in pack.deterministic_facts.items() if k.startswith("tenant_asset_")}
        if tenant_asset_facts:
            lines.append("#### 🏭 Verified Tenant Asset Metadata (Priority 1 - Absolute Truth):")
            for _, asset_data in tenant_asset_facts.items():
                if isinstance(asset_data, dict) and asset_data.get("found"):
                    asset = asset_data.get("asset", {})
                    lines.append(f"- **Tag**: `{asset.get('tag_number')}` ({asset.get('description', '')})")
                    lines.append(f"  - **Asset ID**: `{asset.get('asset_id')}` | **Equipment Type**: `{asset.get('equipment_id')}`")
                    lines.append(f"  - **Manufacturer/Model**: {asset.get('manufacturer', 'N/A')} {asset.get('model_number', '')}")
                    if asset.get("custom_metadata"):
                        lines.append(f"  - **Custom Limits/Parameters [TENANT OVERRIDE]**: {asset.get('custom_metadata')}")
                    if asset_data.get("failure_modes"):
                        fm_names = [f.get("name") for f in asset_data.get("failure_modes", [])]
                        lines.append(f"  - **Governing Failure Modes**: {', '.join(fm_names)}")
                    if asset_data.get("monitored_sensors"):
                        s_names = [s.get("sensor_type") for s in asset_data.get("monitored_sensors", [])]
                        lines.append(f"  - **Monitored Sensor Channels**: {', '.join(s_names)}")
            lines.append("")

        # 2. Render Unresolved Tag Alerts if present
        unresolved_facts = {k: v for k, v in pack.deterministic_facts.items() if k.startswith("unresolved_tag_")}
        if unresolved_facts:
            lines.append("#### ⚠️ Unregistered Asset Tag Alerts (Zero-Assumption Active):")
            for _, alert in unresolved_facts.items():
                if isinstance(alert, dict):
                    lines.append(f"- 🛑 **Tag `{alert.get('tag')}`**: NOT FOUND in tenant `{alert.get('tenant_id')}` records. Treat as unregistered machine — do not assume equipment type or limits.")
            lines.append("")

        # 3. Render Knowledge Chunks
        if pack.results:
            lines.append("#### 📚 Supporting Documentation & Standards:")
            for idx, item in enumerate(pack.results, start=1):
                lines.append(
                    f"{idx}. [Doc: {item.document_id} | Section: {item.section} | "
                    f"Score: {item.score:.2f} | Authority: {item.authority}]\n"
                    f"   \"{item.text.strip()}\""
                )

        # 4. Render Other Deterministic Facts
        other_facts = {
            k: v for k, v in pack.deterministic_facts.items()
            if not k.startswith("tenant_asset_") and not k.startswith("unresolved_tag_")
        }
        if other_facts:
            lines.append("\n#### ⚙️ System Capabilities & Deterministic Registries:")
            for fact_key, fact_val in other_facts.items():
                formatted_val = str(fact_val)[:300]
                lines.append(f"- **{fact_key}**: {formatted_val}")

        return "\n".join(lines)

    def get_context(
        self,
        request: ContextRequest,
        mode: Literal["exact", "semantic", "keyword", "hybrid", "graph_traversal"] = "hybrid",
    ) -> Dict[str, Any]:
        """
        Single unified entry point for AIConnex agents to fetch knowledge context.
        Applies auto-tag detection, tenant-first resolution, and closed-world constraints.

        Returns:
            Dict containing:
            - prompt_context (str): Formatted markdown for LLM system/user prompt injection
            - deterministic_facts (dict): Raw deterministic rule dictionaries
            - evidence_pack (EvidencePack): Full Pydantic evidence pack object
            - trace_id (str): Unique audit trace ID
            - timestamp (str): ISO timestamp
        """
        pack = self.retrieval_service.retrieve(request, mode=mode)

        # Auto-tag resolution against Tenant KB
        detected_tags = self._extract_potential_tags(request.query)
        if detected_tags and request.tenant_id:
            for tag in detected_tags:
                resolved_asset = self.tenant_service.resolve_tag_to_asset(
                    tenant_id=request.tenant_id,
                    tag_number=tag,
                    project_id=request.project_id,
                )
                if resolved_asset:
                    asset_ctx = self.tenant_service.get_asset_with_global_context(resolved_asset.asset_id)
                    pack.deterministic_facts[f"tenant_asset_{tag}"] = asset_ctx
                else:
                    pack.deterministic_facts[f"unresolved_tag_{tag}"] = {
                        "tag": tag,
                        "tenant_id": request.tenant_id,
                        "project_id": request.project_id,
                        "status": "NOT_FOUND",
                        "message": f"Asset tag '{tag}' is not registered in tenant '{request.tenant_id}'. Zero assumptions will be made.",
                    }

        prompt_context = self.format_evidence_for_llm(pack)

        return {
            "prompt_context": prompt_context,
            "deterministic_facts": pack.deterministic_facts,
            "evidence_pack": pack,
            "trace_id": pack.trace_id,
            "timestamp": pack.timestamp,
        }

    def inject_context_into_prompt(self, base_prompt: str, request: ContextRequest) -> str:
        """
        Convenience method to inject retrieved context directly into an agent's base LLM prompt.
        """
        ctx = self.get_context(request)
        prompt_ctx = ctx["prompt_context"]

        if not prompt_ctx:
            return base_prompt

        return f"{base_prompt}\n\n---\n{prompt_ctx}\n---"
