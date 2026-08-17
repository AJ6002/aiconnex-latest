"""
tests/test_platform_kb_terminology.py

Sprint 2 Validation Test Suite for Terminology KB.
Tests:
1. Canonical Term schema validation & YAML registry loading.
2. Exact acronym & alias resolution (RUL, TDS, PdM, SCADA).
3. Dataset column header pattern normalization (tds_mg_l, cod_ppm, temp_c, vib_mm_s).
4. Synonym vs. Related-concept distinction (COD vs BOD).
5. Business phrase normalization (predict servicing -> PdM).
6. PostgreSQL table `knowledge_terminology` sync.
7. Scout Agent Feature Catalog annotation.
"""

import os
import pytest
from agentic.platform_kb.schemas import (
    TerminologyTermRecord,
    CanonicalTermRelation,
    CanonicalTermResolution,
)
from agentic.platform_kb.terminology_service import TerminologyService
from agentic.platform_kb.context_builder import ContextBuilder


@pytest.fixture
def term_svc():
    return TerminologyService()


def test_01_canonical_term_schema():
    """Verify TerminologyTermRecord Pydantic model contracts."""
    rec = TerminologyTermRecord(
        term_id="WQ.TDS",
        canonical_name="Total Dissolved Solids",
        term_type="measurement",
        definition="Total concentration of dissolved substances in water.",
        synonyms=["TDS", "Total Dissolved Solids"],
        abbreviations=["TDS"],
        domain=["water_quality"],
        unit={"canonical": "mg/L"}
    )
    assert rec.term_id == "WQ.TDS"
    assert rec.canonical_name == "Total Dissolved Solids"
    assert rec.unit["canonical"] == "mg/L"


def test_02_exact_acronym_resolution(term_svc):
    """Verify exact acronym lookup (RUL -> Remaining Useful Life, TDS -> Total Dissolved Solids)."""
    res_rul = term_svc.resolve_term("RUL")
    assert res_rul.match_type in ("exact", "alias")
    assert res_rul.confidence >= 0.95
    assert res_rul.term is not None
    assert res_rul.term.term_id == "PHM.RUL"
    assert res_rul.term.canonical_name == "Remaining Useful Life"

    res_tds = term_svc.resolve_term("TDS")
    assert res_tds.match_type in ("exact", "alias")
    assert res_tds.term.term_id == "WQ.TDS"
    assert res_tds.term.canonical_name == "Total Dissolved Solids"


def test_03_column_pattern_normalization(term_svc):
    """Verify dataset column header mapping (tds_mg_l -> Total Dissolved Solids, unit mg/L)."""
    res_tds_col = term_svc.resolve_column("tds_mg_l")
    assert res_tds_col.match_type == "column_pattern"
    assert res_tds_col.term is not None
    assert res_tds_col.term.term_id == "WQ.TDS"
    assert res_tds_col.suggested_unit == "mg/L"

    res_temp_col = term_svc.resolve_column("temp_c")
    assert res_temp_col.match_type == "column_pattern"
    assert res_temp_col.suggested_unit == "°C"


def test_04_synonym_vs_related_concept_distinction(term_svc):
    """Verify COD and BOD are related metrics, NOT synonyms."""
    res_cod = term_svc.resolve_term("COD")
    res_bod = term_svc.resolve_term("BOD")

    assert res_cod.term.term_id == "WQ.COD"
    assert res_bod.term.term_id == "WQ.BOD"
    assert res_cod.term.term_id != res_bod.term.term_id  # Not synonyms!

    related = term_svc.get_related_terms("WQ.COD")
    assert len(related) > 0
    assert any(r.term_id == "WQ.BOD" for r in related)


def test_05_business_phrase_normalization(term_svc):
    """Verify conversational business phrase mapping to canonical intent."""
    phrase = "How to predict when the machine needs servicing?"
    resolutions = term_svc.resolve_phrase(phrase)
    assert len(resolutions) > 0
    top = resolutions[0]
    assert top.term.term_id == "PHM.PDM"
    assert top.term.canonical_name == "Predictive Maintenance"


def test_06_context_builder_integration():
    """Verify ContextBuilder get_terminology_context facade method."""
    builder = ContextBuilder()
    ctx = builder.get_terminology_context("tds_mg_l")
    assert ctx["match_type"] == "column_pattern"
    assert ctx["term"]["term_id"] == "WQ.TDS"
    assert ctx["suggested_unit"] == "mg/L"


def test_07_postgres_terminology_sync(term_svc):
    """Verify sync_to_postgres creates and populates knowledge_terminology table."""
    count = term_svc.sync_to_postgres()
    assert count >= 20
