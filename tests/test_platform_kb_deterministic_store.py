"""
tests/test_platform_kb_deterministic_store.py

Unit test suite for Platform KB Deterministic Store & PostgreSQL Catalog (Step 11).
Validates:
- DDL schema initialization and trigram index creation logic
- Source, document, and chunk relational catalog registration
- Trigram keyword search query execution (pg_trgm)
- Tier 11 (11_relational_catalog) catalog manifest JSON persistence
- Catalog pipeline orchestration
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from agentic.platform_kb.schemas import (
    KnowledgeSourceRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
)
from agentic.platform_kb.deterministic_store import (
    DeterministicStore,
    CatalogPipeline,
    CATALOG_DIR,
)


def test_deterministic_store_init_db_schema_mock():
    mock_db_client = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()

    mock_db_client.get_postgres_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    store = DeterministicStore(db_client=mock_db_client)
    store.init_db_schema()

    mock_db_client.get_postgres_connection.assert_called_once()
    mock_cur.execute.assert_called_once()
    assert "CREATE TABLE IF NOT EXISTS knowledge_sources" in mock_cur.execute.call_args[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_chunks_trgm" in mock_cur.execute.call_args[0][0]
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()


def test_deterministic_store_register_sources_mock():
    mock_db_client = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()

    mock_db_client.get_postgres_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    store = DeterministicStore(db_client=mock_db_client)

    src = KnowledgeSourceRecord(
        source_id="PLAT-DOC-TEST",
        title="Test Spec",
        knowledge_domain="platform",
        source_type="Architecture Spec",
        source_location="aiconnex_knowledge/02_platform/architecture/test.md",
        authority_level="A",
        owner="AIConnex Engineering",
        tenant_scope="global",
        license="Internal",
        version="1.0",
        status="Approved",
        approved_at="2026-08-13T12:00:00",
    )

    count = store.register_sources([src])
    assert count == 1
    mock_cur.execute.assert_called()


def test_deterministic_store_search_chunks_keyword_mock():
    mock_db_client = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()

    mock_db_client.get_postgres_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mock_cur.fetchall.return_value = [
        (
            "DOC-001-CH-0000",
            "DOC-001",
            "Architecture > Compiler",
            0,
            "The compiler handles join conditions.",
            12,
            "A",
            "Master Spec",
            "platform",
            "Architecture Spec",
            0.85,
        )
    ]

    store = DeterministicStore(db_client=mock_db_client)
    results = store.search_chunks_keyword("compiler join", top_k=5, min_score=0.1)

    assert len(results) == 1
    r = results[0]
    assert r["chunk_id"] == "DOC-001-CH-0000"
    assert r["score"] == 0.85
    assert r["title"] == "Master Spec"


def test_catalog_pipeline_saves_manifest(tmp_path):
    output_dir = str(tmp_path / "11_relational_catalog")
    mock_store = MagicMock()
    mock_store.db_client.config.postgres.db_name = "aiconnex_kb_prod"

    pipeline = CatalogPipeline(store=mock_store, output_dir=output_dir)
    manifest_path = pipeline.save_catalog_manifest(total_sources=13, total_documents=13, total_chunks=356)

    assert os.path.exists(manifest_path)
    assert os.path.exists(os.path.join(output_dir, "README.md"))

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["database_name"] == "aiconnex_kb_prod"
    assert data["total_sources"] == 13
    assert data["total_documents"] == 13
    assert data["total_chunks"] == 356
    assert data["status"] == "Active"
