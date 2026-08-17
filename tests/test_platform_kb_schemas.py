"""
tests/test_platform_kb_schemas.py

Unit test suite validating Bucket 3 & Step 4 Pydantic Contracts for Platform KB.
"""

import pytest
from pydantic import ValidationError
from agentic.platform_kb.schemas import (
    KnowledgeSourceRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
    ContextRequest,
    EvidenceItem,
    EvidencePack,
    PlatformCapabilities,
    ManifestRegistryEntry,
)


def test_knowledge_source_record_validation():
    source = KnowledgeSourceRecord(
        source_id="PLAT-DOC-001",
        title="AIConnex Complete Agentic Flow",
        knowledge_domain="platform",
        source_type="Internal Architecture Doc",
        source_location="Documentation/aiconnex_complete_flow.md",
        authority_level="A",
        status="Approved",
    )
    assert source.source_id == "PLAT-DOC-001"
    assert source.status == "Approved"
    assert source.authority_level == "A"


def test_knowledge_source_record_invalid_authority_raises_error():
    with pytest.raises(ValidationError):
        KnowledgeSourceRecord(
            source_id="PLAT-DOC-999",
            title="Invalid Source",
            source_type="Test",
            source_location="test.md",
            authority_level="X",  # Invalid, must be A, B, or C
            status="Approved",
        )


def test_knowledge_document_record_defaults_and_timezone():
    doc = KnowledgeDocumentRecord(
        document_id="DOC-PLAT-001-V1",
        source_id="PLAT-DOC-001",
        document_type="markdown",
        title="AIConnex Master Final Architecture",
        version="1.0",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        storage_uri="platform/architecture/aiconnex_final_master_architecture.md",
    )
    assert doc.document_id == "DOC-PLAT-001-V1"
    assert doc.status == "Active"
    assert "T" in doc.created_at
    assert doc.language == "en"


def test_knowledge_chunk_record():
    chunk = KnowledgeChunkRecord(
        chunk_id="CH-PLAT-00231",
        document_id="DOC-PLAT-001-V1",
        version="1.0",
        section="Compiler -> Join Engine",
        chunk_index=0,
        text="Cartesian explosion guard prevents full outer join fan-out.",
        text_hash="a1b2c3d4e5",
        token_count=12,
        authority_level="A",
    )
    assert chunk.chunk_id == "CH-PLAT-00231"
    assert chunk.section == "Compiler -> Join Engine"
    assert chunk.token_count == 12


def test_context_request_validation_and_bounds():
    req = ContextRequest(query="How does the compiler work?", top_k=10, min_score=0.75)
    assert req.top_k == 10
    assert req.min_score == 0.75
    assert req.knowledge_domain == "platform"

    # Out of bounds top_k (>20)
    with pytest.raises(ValidationError):
        ContextRequest(query="Test", top_k=25)

    # Out of bounds min_score (>1.0)
    with pytest.raises(ValidationError):
        ContextRequest(query="Test", min_score=1.5)


def test_evidence_pack_envelope_and_alias():
    item = EvidenceItem(
        document_id="DOC-PLAT-001-V1",
        source_id="PLAT-DOC-001",
        version="1.0",
        section="Compiler -> Join Engine",
        chunk_id="CH-PLAT-00231",
        text="Cartesian explosion guard prevents full outer join fan-out.",
        score=0.94,
        authority="A",
    )
    pack = EvidencePack(
        query="How does the join engine handle Cartesian explosion?",
        knowledge_domain="platform",
        retrieval_mode="hybrid",
        results=[item],
        deterministic_facts={"cartesian_guard_enabled": True},
        trace_id="tr_9481a0e",
    )
    assert pack.query.startswith("How does the join engine")
    assert pack.results[0].chunk_id == "CH-PLAT-00231"
    assert pack.deterministic_facts["cartesian_guard_enabled"] is True
    # Test backward compatibility alias property
    assert pack.retrieval_strategy == "hybrid"


def test_platform_capabilities_default_schema():
    caps = PlatformCapabilities()
    assert "tdms" in caps.supported_formats
    assert "csv" in caps.supported_formats
    assert "discovery" in caps.compiler_stages
    assert "DAG_414" in caps.ml_supported_dags


def test_manifest_registry_entry():
    entry = ManifestRegistryEntry(
        manifest_type="training_manifest",
        schema_version="1.0",
        required_fields=["dataset_path", "target_column", "model_type"],
    )
    assert entry.manifest_type == "training_manifest"
    assert entry.status == "Active"
    assert len(entry.required_fields) == 3

