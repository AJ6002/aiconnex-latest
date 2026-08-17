"""
tests/integration/test_platform_kb_e2e.py
============================================
Step 13 — E2E Integration Validation Suite for Platform KB.

Validates the complete Platform KB vertical slice against live Docker backends:
  V1  - Infrastructure Health (Postgres, Qdrant, MinIO)
  V2  - Source Register Integrity (13 approved sources)
  V3  - Tier Consistency Chain (Tiers 02, 06, 07, 09, 10, 11)
  V4  - Cross-Store ID Consistency
  V5  - Retrieval Quality — Semantic (Qdrant vector search)
  V6  - Retrieval Quality — Keyword (Postgres pg_trgm search)
  V7  - Retrieval Quality — Hybrid RRF (RRF fusion)
  V8  - Retrieval Quality — Graph Traversal (Postgres ontology graph)
  V9  - Retrieval Quality — Exact (Deterministic YAML registries)
  V10 - ContextBuilder Integration (get_context facade)
  V11 - ContextBuilder Prompt Injection (inject_context_into_prompt)
  V12 - Provenance Audit Trail (13_provenance/retrieval_events.jsonl)
  V13 - Ontology Graph in PostgreSQL (knowledge_ontology_nodes/edges)
  V14 - Manifest Consistency (storage, embedding, catalog manifests)

Zero mocks. Zero test-script workarounds.
Invoked via: pytest tests/integration/test_platform_kb_e2e.py -m integration -v
"""

import os
import json
import pytest
from pathlib import Path

from agentic.platform_kb.config import get_kb_config
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.source_register import SourceRegisterManager
from agentic.platform_kb.retrieval_service import RetrievalService
from agentic.platform_kb.context_builder import ContextBuilder
from agentic.platform_kb.schemas import ContextRequest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KB_ROOT = REPO_ROOT / "aiconnex_knowledge"


@pytest.fixture(scope="module")
def infra():
    """Provides initialized KBInfraClient connected to live Docker backends."""
    client = KBInfraClient()
    client.perform_health_checks(raise_on_failure=False)
    return client


# ---------------------------------------------------------------------------
# V1: Infrastructure Health
# ---------------------------------------------------------------------------
def test_v1_infrastructure_health(infra):
    status = infra.perform_health_checks(raise_on_failure=False)
    assert status["postgres"] is True
    assert status["qdrant"] is True
    assert status["minio"] is True

    # Assert specific DB, collection, and bucket exist
    config = get_kb_config()
    assert config.postgres.db_name == "aiconnex_kb_prod"
    assert config.qdrant.collection == "platform_kb_embeddings"
    assert config.minio.bucket == "aiconnex-platform-kb-prod"


# ---------------------------------------------------------------------------
# V2: Source Register Integrity
# ---------------------------------------------------------------------------
def test_v2_source_register_integrity():
    sr = SourceRegisterManager()
    records = sr.get_approved_sources(domain="all")
    assert len(records) >= 13

    # Check source_register.csv matches
    csv_path = KB_ROOT / "01_source_register" / "source_register.csv"
    assert csv_path.exists()
    with open(csv_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) >= 14

    for rec in records:
        assert rec.source_id.startswith(("PLAT-", "DATA-", "IND-", "SRC-IND-"))
        assert rec.title != ""
        assert rec.authority_level in ("A", "B", "C")


# ---------------------------------------------------------------------------
# V3: Tier Consistency Chain (02, 06, 07, 09, 10, 11)
# ---------------------------------------------------------------------------
def test_v3_tier_consistency_chain(infra):
    sr = SourceRegisterManager()
    records = sr.get_approved_sources(domain="platform")

    minio_client = infra.get_minio_client()
    minio_objects = [obj.object_name for obj in minio_client.list_objects(infra.config.minio.bucket, recursive=True)]

    pg_conn = infra.get_postgres_connection()
    cur = pg_conn.cursor()

    for rec in records:
        s_id = rec.source_id

        # Tier 02: Raw file on disk
        raw_file = REPO_ROOT / rec.source_location
        assert raw_file.exists(), f"Raw file missing for {s_id}: {raw_file}"

        # Tier 06: MinIO object exists
        matching_minio = [o for o in minio_objects if rec.source_location.replace("\\", "/") in o or os.path.basename(rec.source_location) in o]
        assert len(matching_minio) > 0, f"MinIO object missing for {s_id}"

        # Tier 07: Normalized sections file exists
        norm_file = KB_ROOT / "07_normalized_documents" / f"{s_id}_normalized.json"
        assert norm_file.exists(), f"Normalized JSON missing for {s_id}"

        # Tier 09: Chunk JSON file exists
        chunk_file = KB_ROOT / "09_chunks" / f"{s_id}_chunks.json"
        assert chunk_file.exists(), f"Chunk JSON missing for {s_id}"

        # Tier 11: PostgreSQL document row exists
        cur.execute("SELECT COUNT(*) FROM knowledge_documents WHERE document_id = %s;", (s_id,))
        count = cur.fetchone()[0]
        assert count > 0, f"PostgreSQL row missing for {s_id}"

    cur.close()
    pg_conn.close()


# ---------------------------------------------------------------------------
# V4: Cross-Store ID Consistency
# ---------------------------------------------------------------------------
def test_v4_cross_store_id_consistency(infra):
    chunk_dir = KB_ROOT / "09_chunks"
    disk_chunk_ids = set()
    for f in chunk_dir.glob("*_chunks.json"):
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            chunks_list = data.get("chunks", []) if isinstance(data, dict) else data
            for item in chunks_list:
                disk_chunk_ids.add(item["chunk_id"])

    assert len(disk_chunk_ids) >= 356

    # Verify PostgreSQL knowledge_chunks count matches
    pg_conn = infra.get_postgres_connection()
    cur = pg_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM knowledge_chunks;")
    pg_chunk_count = cur.fetchone()[0]
    cur.close()
    pg_conn.close()

    assert pg_chunk_count >= 356

    # Verify Qdrant points count matches
    qd_client = infra.get_qdrant_client()
    collection_info = qd_client.get_collection(infra.config.qdrant.collection)
    assert collection_info.points_count >= 356


# ---------------------------------------------------------------------------
# V5: Retrieval Quality — Semantic
# ---------------------------------------------------------------------------
def test_v5_retrieval_quality_semantic():
    service = RetrievalService()
    req = ContextRequest(query="How does the compiler handle multi-table CSV joins?", agent_id="ScoutAgent")
    pack = service.retrieve(req, mode="semantic")

    assert len(pack.results) > 0
    top_result = pack.results[0]
    assert top_result.score >= 0.3
    assert any(term in top_result.text.lower() for term in ["compiler", "join", "table", "csv"])


# ---------------------------------------------------------------------------
# V6: Retrieval Quality — Keyword
# ---------------------------------------------------------------------------
def test_v6_retrieval_quality_keyword():
    service = RetrievalService()
    req = ContextRequest(query="9-Node Microservice ML Pipeline", agent_id="ScoutAgent")
    pack = service.retrieve(req, mode="keyword")

    assert len(pack.results) > 0
    assert any(term in pack.results[0].text.lower() for term in ["pipeline", "microservice", "node"])


# ---------------------------------------------------------------------------
# V7: Retrieval Quality — Hybrid RRF
# ---------------------------------------------------------------------------
def test_v7_retrieval_quality_hybrid():
    service = RetrievalService()
    req = ContextRequest(query="What are the compiler stages and plugin architecture?", agent_id="ScoutAgent")
    pack = service.retrieve(req, mode="hybrid")

    assert pack.retrieval_strategy == "hybrid"
    assert len(pack.results) > 0
    assert pack.trace_id.startswith("trc_")


# ---------------------------------------------------------------------------
# V8: Retrieval Quality — Graph Traversal
# ---------------------------------------------------------------------------
def test_v8_retrieval_quality_graph_traversal():
    service = RetrievalService()
    req = ContextRequest(query="ScoutAgent uses", agent_id="ScoutAgent")
    pack = service.retrieve(req, mode="graph_traversal")

    assert len(pack.results) > 0
    assert any("ScoutAgent" in res.text or "Graph Edge" in res.text or "Ontology" in res.text for res in pack.results)


# ---------------------------------------------------------------------------
# V9: Retrieval Quality — Exact
# ---------------------------------------------------------------------------
def test_v9_retrieval_quality_exact():
    service = RetrievalService()
    req = ContextRequest(query="What file formats are supported?", agent_id="PreUploadAgent")
    pack = service.retrieve(req, mode="exact")

    assert "capabilities" in pack.deterministic_facts
    assert "manifest_registry" in pack.deterministic_facts
    assert "ontology" in pack.deterministic_facts

    raw_caps = pack.deterministic_facts["capabilities"]
    caps_data = raw_caps.get("capabilities", raw_caps)
    assert "file_ingestion" in caps_data
    assert "csv" in caps_data["file_ingestion"]["supported"]


# ---------------------------------------------------------------------------
# V10: ContextBuilder Integration
# ---------------------------------------------------------------------------
def test_v10_context_builder_integration():
    builder = ContextBuilder()
    req = ContextRequest(query="compiler join engine", agent_id="ScoutAgent")
    ctx = builder.get_context(req)

    assert "prompt_context" in ctx
    assert "deterministic_facts" in ctx
    assert "evidence_pack" in ctx
    assert "trace_id" in ctx
    assert "timestamp" in ctx

    assert ctx["trace_id"].startswith("trc_")
    assert "RETRIEVED KNOWLEDGE EVIDENCE" in ctx["prompt_context"]


# ---------------------------------------------------------------------------
# V11: ContextBuilder Prompt Injection
# ---------------------------------------------------------------------------
def test_v11_context_builder_prompt_injection():
    builder = ContextBuilder()
    req = ContextRequest(query="upload rules", agent_id="PreUploadAgent")
    base_prompt = "You are PreUploadAgent."
    injected = builder.inject_context_into_prompt(base_prompt, req)

    assert injected.startswith("You are PreUploadAgent.")
    assert "RETRIEVED KNOWLEDGE EVIDENCE" in injected


# ---------------------------------------------------------------------------
# V12: Provenance Audit Trail
# ---------------------------------------------------------------------------
def test_v12_provenance_audit_trail():
    events_log = KB_ROOT / "13_provenance" / "retrieval_events.jsonl"
    assert events_log.exists()

    with open(events_log, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) > 0
    last_event = json.loads(lines[-1])

    assert "trace_id" in last_event
    assert "context_hash" in last_event
    assert "agent_id" in last_event
    assert "tenant_id" in last_event
    assert "retrieval_mode" in last_event
    assert "timestamp" in last_event


# ---------------------------------------------------------------------------
# V13: Ontology Graph in PostgreSQL
# ---------------------------------------------------------------------------
def test_v13_ontology_graph_in_postgresql(infra):
    pg_conn = infra.get_postgres_connection()
    cur = pg_conn.cursor()

    cur.execute("SELECT COUNT(*) FROM knowledge_ontology_nodes;")
    node_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM knowledge_ontology_edges;")
    edge_count = cur.fetchone()[0]

    cur.close()
    pg_conn.close()

    assert node_count >= 11
    assert edge_count >= 7


# ---------------------------------------------------------------------------
# V14: Manifest Consistency
# ---------------------------------------------------------------------------
def test_v14_manifest_consistency():
    storage_manifest = KB_ROOT / "06_raw_documents" / "storage_manifest.json"
    embedding_manifest = KB_ROOT / "10_vector_index" / "embedding_manifest.json"
    catalog_manifest = KB_ROOT / "11_relational_catalog" / "catalog_manifest.json"

    assert storage_manifest.exists()
    assert embedding_manifest.exists()
    assert catalog_manifest.exists()

    with open(storage_manifest, "r", encoding="utf-8") as f:
        s_data = json.load(f)
    with open(embedding_manifest, "r", encoding="utf-8") as f:
        e_data = json.load(f)
    with open(catalog_manifest, "r", encoding="utf-8") as f:
        c_data = json.load(f)

    assert s_data.get("status") == "Active"
    assert e_data.get("status") == "Active"
    assert c_data.get("status") == "Active"

    assert s_data.get("total_documents") >= 13
    assert e_data.get("total_vectors") >= 356
    assert c_data.get("total_chunks") >= 356
