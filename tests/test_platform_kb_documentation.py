"""
tests/test_platform_kb_documentation.py

Comprehensive Test Suite for Documentation KB (Sprint 7).
Validates:
- Schema contracts for DocumentationSpecRecord, PerformanceSLARecord, and StateTransitionRecord
- Deterministic loading of all 22 specification documents and SLAs
- Component-level and Studio-level specification queries
- Automated SLA compliance verification (Pass / Breach)
- ContextBuilder integration and audit helpers
- Closed-world boundaries on unlisted specs
"""

import pytest
from pydantic import ValidationError

from agentic.platform_kb.schemas import (
    DocumentationSpecRecord,
    PerformanceSLARecord,
    StateTransitionRecord,
    ComplianceAuditReport,
    ContextRequest,
)
from agentic.platform_kb.documentation_service import DocumentationService
from agentic.platform_kb.context_builder import ContextBuilder


def test_documentation_schemas_validation():
    """Test valid and invalid creation of documentation Pydantic models."""
    sla = PerformanceSLARecord(
        sla_id="SLA-TEST-001",
        component_name="TestEngine",
        metric_name="p95_latency_ms",
        target_value=200.0,
        unit="ms",
        comparison_op="<=",
        workload_condition="test batch",
        severity_on_breach="critical",
        source_spec_id="DOC-SPEC-TEST",
    )
    assert sla.sla_id == "SLA-TEST-001"
    assert sla.target_value == 200.0

    # Invalid comparison op should fail
    with pytest.raises(ValidationError):
        PerformanceSLARecord(
            sla_id="SLA-TEST-002",
            component_name="TestEngine",
            metric_name="p95_latency_ms",
            target_value=200.0,
            unit="ms",
            comparison_op="INVALID_OP",  # type: ignore
            source_spec_id="DOC-SPEC-TEST",
        )


def test_documentation_registry_loading():
    """Test that DocumentationService loads all 22 specs and all SLAs from YAML."""
    svc = DocumentationService()
    assert len(svc.specs) == 22, f"Expected 22 specs, found {len(svc.specs)}"
    assert len(svc.slas) >= 22, f"Expected at least 22 SLAs, found {len(svc.slas)}"
    assert "DOC-SPEC-001" in svc.specs
    assert "DOC-SPEC-022" in svc.specs


def test_documentation_service_get_spec():
    """Test retrieving a single spec by ID."""
    svc = DocumentationService()
    spec = svc.get_spec("DOC-SPEC-001")
    assert spec is not None
    assert spec.studio == "DataStudio"
    assert "DataStudioCompiler" in spec.target_subsystems
    assert spec.authority == "A"
    assert spec.status == "Approved"


def test_documentation_service_component_lookup():
    """Test querying specs and SLAs governing a specific subsystem."""
    svc = DocumentationService()
    compiler_specs = svc.get_specs_for_component("DataStudioCompiler")
    assert len(compiler_specs) >= 2
    spec_ids = [s.spec_id for s in compiler_specs]
    assert "DOC-SPEC-001" in spec_ids or "DOC-SPEC-002" in spec_ids

    slas = svc.get_performance_slas("DataStudioCompiler")
    assert len(slas) >= 1
    assert slas[0].unit in ["ms", "s", "MB", "rows/sec"]


def test_documentation_service_studio_and_category_lookup():
    """Test filtering specs by studio and category."""
    svc = DocumentationService()
    data_studio_specs = svc.get_specs_by_studio("DataStudio")
    assert len(data_studio_specs) >= 8

    agentic_specs = svc.get_specs_by_studio("AgenticStudio")
    assert len(agentic_specs) >= 6

    perf_specs = svc.get_specs_by_category("Performance")
    assert len(perf_specs) >= 5


def test_documentation_service_compliance_checker_pass():
    """Test automated compliance auditing when metrics meet the SLA."""
    svc = DocumentationService()
    metrics = {
        "p95_latency_ms": 150.0,
        "max_memory_mb": 512.0,
    }
    report = svc.verify_compliance("DataStudioCompiler", metrics)
    assert isinstance(report, ComplianceAuditReport)
    assert report.is_compliant is True
    assert report.slas_breached == 0


def test_documentation_service_compliance_checker_breach():
    """Test automated compliance auditing when metrics breach the SLA."""
    svc = DocumentationService()
    # Provide an egregiously high latency that breaches the SLA
    metrics = {
        "p95_latency_ms": 99999.0,
    }
    report = svc.verify_compliance("DataStudioCompiler", metrics)
    assert isinstance(report, ComplianceAuditReport)
    assert report.is_compliant is False
    assert report.slas_breached > 0
    assert len(report.breaches) > 0
    assert report.breaches[0]["severity"] in ["critical", "warning"]


def test_documentation_service_state_transitions():
    """Test retrieving state machine transition contracts."""
    svc = DocumentationService()
    transitions = svc.get_state_transitions()
    assert len(transitions) >= 40
    for t in transitions[:5]:
        assert t.from_state is not None
        assert t.to_state is not None
        assert t.trigger_event is not None


def test_context_builder_documentation_context_by_spec_id():
    """Test ContextBuilder.get_documentation_context with spec_id."""
    cb = ContextBuilder()
    ctx = cb.get_documentation_context(spec_id="DOC-SPEC-003")
    assert ctx.get("found") is True
    assert ctx["spec"]["spec_id"] == "DOC-SPEC-003"
    assert "DataProfiler" in ctx["spec"]["target_subsystems"]


def test_context_builder_documentation_context_by_component():
    """Test ContextBuilder.get_documentation_context with component_name."""
    cb = ContextBuilder()
    ctx = cb.get_documentation_context(component_name="ScoutAgent")
    assert ctx.get("found") is True
    assert ctx["component_name"] == "ScoutAgent"
    assert ctx["specs_count"] >= 1


def test_context_builder_audit_plan_compliance():
    """Test ContextBuilder.audit_plan_compliance helper."""
    cb = ContextBuilder()
    passing_metrics = {"p95_latency_ms": 100.0}
    res = cb.audit_plan_compliance("ScoutAgent", passing_metrics)
    assert res.get("is_compliant") is True

    failing_metrics = {"p95_latency_ms": 99999.0}
    res_fail = cb.audit_plan_compliance("ScoutAgent", failing_metrics)
    assert res_fail.get("is_compliant") is False
    assert res_fail.get("slas_breached") >= 1


def test_closed_world_non_existent_spec():
    """Test that querying a non-existent spec ID returns found=False with zero hallucination."""
    cb = ContextBuilder()
    ctx = cb.get_documentation_context(spec_id="DOC-SPEC-NONEXISTENT-999")
    assert ctx.get("found") is False

    ctx_comp = cb.get_documentation_context(component_name="TotallyFakeUnknownSubsystem")
    assert ctx_comp.get("found") is False
    assert ctx_comp.get("specs_count") == 0
