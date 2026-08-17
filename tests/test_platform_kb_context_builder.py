"""
tests/test_platform_kb_context_builder.py

Unit test suite for ContextBuilder interface.
Validates:
- context_builder.get_context(ContextRequest) returns formatted prompt context
- EvidencePack formatting into markdown for LLM injection
- Context prompt injection helper
"""

import pytest
from unittest.mock import MagicMock

from agentic.platform_kb.schemas import ContextRequest, EvidencePack, EvidenceItem
from agentic.platform_kb.context_builder import ContextBuilder


def test_context_builder_get_context_mock():
    mock_retrieval = MagicMock()
    mock_pack = EvidencePack(
        query="Tell me about compiler join engine",
        knowledge_domain="platform",
        retrieval_mode="hybrid",
        results=[
            EvidenceItem(
                document_id="DOC-PLAT-DOC-001-V1",
                source_id="PLAT-DOC-001",
                version="1.0",
                section="Compiler > Joins",
                chunk_id="CH-001",
                text="Multi-table relational join engine processes CSV inputs.",
                score=0.92,
                authority="A",
            )
        ],
        deterministic_facts={"capabilities": {"file_ingestion": {"supported": ["csv"]}}},
        trace_id="trc_test_12345",
    )
    mock_retrieval.retrieve.return_value = mock_pack

    builder = ContextBuilder(retrieval_service=mock_retrieval)
    req = ContextRequest(query="Tell me about compiler join engine")
    ctx = builder.get_context(req)

    assert ctx["trace_id"] == "trc_test_12345"
    assert "### RETRIEVED KNOWLEDGE EVIDENCE" in ctx["prompt_context"]
    assert "Multi-table relational join engine" in ctx["prompt_context"]
    assert "capabilities" in ctx["deterministic_facts"]


def test_context_builder_inject_context_into_prompt_mock():
    mock_retrieval = MagicMock()
    mock_pack = EvidencePack(
        query="Upload rules",
        knowledge_domain="platform",
        retrieval_mode="exact",
        results=[],
        deterministic_facts={"rules": "Must validate checksum"},
        trace_id="trc_test_67890",
    )
    mock_retrieval.retrieve.return_value = mock_pack

    builder = ContextBuilder(retrieval_service=mock_retrieval)
    req = ContextRequest(query="Upload rules")
    prompt = builder.inject_context_into_prompt("System prompt: You are AIConnex PreUploadAgent.", req)

    assert "System prompt: You are AIConnex PreUploadAgent." in prompt
    assert "### RETRIEVED KNOWLEDGE EVIDENCE" in prompt
    assert "Must validate checksum" in prompt


def test_context_builder_auto_tag_resolution_known_asset():
    """Validates that a known plant tag (e.g. P-201A) is automatically resolved against the Tenant KB."""
    builder = ContextBuilder()
    req = ContextRequest(
        query="Check operating temperature on pump P-201A",
        tenant_id="TENANT-DEMO-ACME",
        project_id="PROJ-ACME-HOUSTON",
    )
    ctx = builder.get_context(req)

    # 1. Deterministic facts must contain resolved asset
    assert "tenant_asset_P-201A" in ctx["deterministic_facts"]
    asset_data = ctx["deterministic_facts"]["tenant_asset_P-201A"]
    assert asset_data["found"] is True
    assert asset_data["asset"]["tag_number"] == "P-201A"
    assert asset_data["asset"]["equipment_id"] == "EQP-PUMP-CENTRIFUGAL"

    # 2. Prompt context must contain strict grounding directives and tenant truth block
    prompt_ctx = ctx["prompt_context"]
    assert "STRICT GROUNDING & PRECEDENCE DIRECTIVES" in prompt_ctx
    assert "TENANT OVERRIDE" in prompt_ctx
    assert "Verified Tenant Asset Metadata" in prompt_ctx
    assert "P-201A" in prompt_ctx


def test_context_builder_auto_tag_resolution_unknown_asset_zero_assumption():
    """Validates that an unknown plant tag (e.g. P-2971) triggers an unregistered alert and zero assumptions."""
    builder = ContextBuilder()
    req = ContextRequest(
        query="Analyze vibration on unknown pump P-2971",
        tenant_id="TENANT-DEMO-ACME",
    )
    ctx = builder.get_context(req)

    # 1. Deterministic facts must flag unresolved tag
    assert "unresolved_tag_P-2971" in ctx["deterministic_facts"]
    alert = ctx["deterministic_facts"]["unresolved_tag_P-2971"]
    assert alert["status"] == "NOT_FOUND"
    assert "Zero assumptions will be made" in alert["message"]

    # 2. Prompt context must render warning to block LLM from guessing
    prompt_ctx = ctx["prompt_context"]
    assert "Unregistered Asset Tag Alerts (Zero-Assumption Active)" in prompt_ctx
    assert "P-2971" in prompt_ctx
    assert "NOT FOUND" in prompt_ctx
