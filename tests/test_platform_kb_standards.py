"""
tests/test_platform_kb_standards.py

Unit & Integration Test Suite for Sprint 5 Standards & Regulatory Knowledge Base.
Validates:
1. StandardRecord Pydantic schema validation.
2. Canonical YAML registry loading and standards completeness.
3. Standard retrieval by ID, designation, and name.
4. Equipment applicability mapping (Pumps, Compressors, Motors, Heat Exchangers).
5. Issuing body filtering (ISO, IEC, NIST, EPA, API, OPC UA).
6. Concept governance lookups (failure_mode, RUL, FMEA, OT security).
7. PostgreSQL `knowledge_standards` sync and persistence.
8. Qdrant vector semantic search under `knowledge_domain='standards_regulatory'`.
9. ContextBuilder unified standards context facade integration.
10. Version lineage (supersedes/superseded_by) and stub document availability flags.
"""

import pytest
from pydantic import ValidationError

from agentic.platform_kb.schemas import StandardRecord, ContextRequest
from agentic.platform_kb.standards_service import StandardsService
from agentic.platform_kb.context_builder import ContextBuilder
from agentic.platform_kb.retrieval_service import RetrievalService
from agentic.platform_kb.db_client import KBInfraClient


def test_01_standard_record_schema_validation():
    """Validates StandardRecord Pydantic contract."""
    valid_data = {
        "standard_id": "STD-ISO-14224",
        "designation": "ISO 14224:2016",
        "title": "Reliability and maintenance data for equipment",
        "issuing_body": "ISO",
        "standard_type": "international_standard",
        "version": "2016",
        "scope": "Defines reliability taxonomy and data collection for equipment.",
        "applicability": ["rotating_equipment", "static_equipment"],
        "jurisdiction": "international",
        "key_concepts": ["failure_mode", "MTBF"],
        "supersedes": "STD-ISO-14224-2006",
        "authority": "A",
        "status": "Approved",
    }
    rec = StandardRecord(**valid_data)
    assert rec.standard_id == "STD-ISO-14224"
    assert rec.designation == "ISO 14224:2016"
    assert rec.document_available is True
    assert rec.jurisdiction == "international"

    # Negative test: invalid standard_type
    invalid_data = valid_data.copy()
    invalid_data["standard_type"] = "unsupported_type_xyz"
    with pytest.raises(ValidationError):
        StandardRecord(**invalid_data)


def test_02_registry_loading():
    """Verifies canonical standards YAML loads ≥35 standards and covers core bodies."""
    svc = StandardsService()
    assert len(svc.standards) >= 35

    # Check key foundational standards exist
    assert "STD-ISO-14224" in svc.standards
    assert "STD-ISO-55000" in svc.standards
    assert "STD-ISO-13381-1" in svc.standards
    assert "STD-IEC-60812" in svc.standards
    assert "STD-CRISP-MLQ" in svc.standards
    assert "STD-NISTIR-8012" in svc.standards
    assert "STD-OPC-UA-PART110" in svc.standards
    assert "STD-EPA-WW-PACKAGE" in svc.standards


def test_03_get_standard_by_id_and_designation():
    """Verifies standard retrieval by ID, designation, and partial match."""
    svc = StandardsService()

    # Exact ID
    std_14224 = svc.get_standard("STD-ISO-14224")
    assert std_14224 is not None
    assert "14224" in std_14224.designation

    # Designation
    std_55k = svc.get_standard("ISO 55000:2024")
    assert std_55k is not None
    assert std_55k.standard_id == "STD-ISO-55000"

    # Case-insensitive
    std_fmea = svc.get_standard("iec 60812:2018")
    assert std_fmea is not None
    assert std_fmea.standard_id == "STD-IEC-60812"


def test_04_applicable_standards_for_equipment():
    """Verifies equipment-to-standards mapping for rotating and static equipment."""
    svc = StandardsService()

    # Centrifugal Pump
    pump_stds = svc.get_applicable_standards("EQP-PUMP-CENTRIFUGAL")
    pump_ids = [s.standard_id for s in pump_stds]
    assert "STD-ISO-2858" in pump_ids
    assert "STD-ISO-5199" in pump_ids
    assert "STD-API-610" in pump_ids
    assert "STD-ISO-14224" in pump_ids

    # Centrifugal Compressor
    comp_stds = svc.get_applicable_standards("EQP-COMP-CENTRIFUGAL")
    comp_ids = [s.standard_id for s in comp_stds]
    assert "STD-ISO-5390" in comp_ids
    assert "STD-API-617" in comp_ids

    # Heat Exchanger
    hex_stds = svc.get_applicable_standards("EQP-HEX-SHELLTUBE")
    hex_ids = [s.standard_id for s in hex_stds]
    assert "STD-ISO-16812" in hex_ids
    assert "STD-TEMA-10TH" in hex_ids


def test_05_standards_by_issuing_body():
    """Verifies filtering by issuing organization (ISO, IEC, NIST, EPA, API)."""
    svc = StandardsService()

    iso_stds = svc.get_standards_by_body("ISO")
    assert len(iso_stds) >= 8
    assert all("ISO" in s.issuing_body for s in iso_stds)

    iec_stds = svc.get_standards_by_body("IEC")
    assert len(iec_stds) >= 3

    nist_stds = svc.get_standards_by_body("NIST")
    assert len(nist_stds) >= 4

    epa_stds = svc.get_standards_by_body("EPA")
    assert len(epa_stds) >= 2


def test_06_governing_standards_for_concept():
    """Verifies lookup of standards defining or governing specific industrial concepts."""
    svc = StandardsService()

    # Failure Mode / FMEA
    fm_stds = svc.get_governing_standards("failure_mode")
    fm_ids = [s.standard_id for s in fm_stds]
    assert "STD-ISO-14224" in fm_ids

    fmea_stds = svc.get_governing_standards("failure_cause")
    assert any(s.standard_id == "STD-IEC-60812" for s in fmea_stds)

    # Remaining Useful Life / Prognostics
    rul_stds = svc.get_governing_standards("remaining_useful_life")
    assert any(s.standard_id == "STD-ISO-13381-1" for s in rul_stds)

    # Operational Technology Security
    ot_stds = svc.get_governing_standards("OT_security_architecture")
    assert any(s.standard_id == "STD-NIST-SP-800-82" for s in ot_stds)


def test_07_postgres_sync():
    """Verifies syncing standards to PostgreSQL table knowledge_standards."""
    svc = StandardsService()
    synced_count = svc.sync_to_postgres()
    assert synced_count >= 35

    # Query PostgreSQL directly to verify
    conn = svc.db_client.get_postgres_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM knowledge_standards;")
    count = cur.fetchone()[0]
    assert count >= 35

    cur.execute("SELECT designation, issuing_body FROM knowledge_standards WHERE standard_id = 'STD-ISO-14224';")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "ISO 14224:2016"
    assert row[1] == "ISO"

    cur.close()
    conn.close()


def test_08_qdrant_vector_retrieval():
    """Verifies vector semantic search under knowledge_domain='standards_regulatory'."""
    retrieval = RetrievalService()

    # Query asset management
    req = ContextRequest(
        query="asset management principles terminology and requirements",
        knowledge_domain="standards_regulatory",
        top_k=5,
        min_score=0.40,
    )
    pack = retrieval.retrieve(req, mode="semantic")
    assert len(pack.results) > 0
    assert pack.knowledge_domain == "standards_regulatory"

    # Query prognostics & RUL
    req_phm = ContextRequest(
        query="predicting remaining useful life prognostic horizons and degradation",
        knowledge_domain="standards_regulatory",
        top_k=5,
        min_score=0.40,
    )
    pack_phm = retrieval.retrieve(req_phm, mode="semantic")
    assert len(pack_phm.results) > 0


def test_09_context_builder_standards_integration():
    """Verifies ContextBuilder unified standards context method."""
    cb = ContextBuilder()

    # Query by standard_id
    ctx_std = cb.get_standards_context(standard_id="STD-ISO-55000")
    assert ctx_std["found"] is True
    assert ctx_std["governing_body"] == "ISO"
    assert "asset_lifecycle" in ctx_std["applicability"]

    # Query by equipment_id
    ctx_eqp = cb.get_standards_context(equipment_id="EQP-PUMP-CENTRIFUGAL")
    assert ctx_eqp["applicable_standards_count"] >= 5
    stds = [s["standard_id"] for s in ctx_eqp["standards"]]
    assert "STD-ISO-2858" in stds

    # Query by concept
    ctx_concept = cb.get_standards_context(concept="remaining_useful_life")
    assert ctx_concept["governing_standards_count"] >= 1

    # Negative test: unknown standard
    ctx_missing = cb.get_standards_context(standard_id="STD-NON-EXISTENT-999")
    assert ctx_missing["found"] is False


def test_10_version_lineage_and_stub_records():
    """Verifies supersedes lineage tracking and document availability flags."""
    svc = StandardsService()

    # ISO 14224 supersedes 2006 edition
    std_14224 = svc.get_standard("STD-ISO-14224")
    assert std_14224.supersedes == "STD-ISO-14224-2006"

    std_14224_old = svc.get_standard("STD-ISO-14224-2006")
    assert std_14224_old is not None
    assert std_14224_old.superseded_by == "STD-ISO-14224"
    assert std_14224_old.document_available is False  # Stub/archived

    # Referenced standards without raw docs are marked document_available=False
    std_api610 = svc.get_standard("STD-API-610")
    assert std_api610 is not None
    assert std_api610.document_available is False

    # Acquired standards with raw docs are marked document_available=True
    std_iso5390 = svc.get_standard("STD-ISO-5390")
    assert std_iso5390 is not None
    assert std_iso5390.document_available is True
