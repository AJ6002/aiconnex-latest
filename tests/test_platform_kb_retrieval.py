"""
tests/test_platform_kb_retrieval.py

Unit test suite for Platform KB Unified Retrieval Service (Step 12).
Validates:
- Exact deterministic fact lookups
- Vector semantic retrieval (Qdrant) with authority score weighting
- Trigram keyword retrieval (PostgreSQL pg_trgm)
- Reciprocal Rank Fusion (RRF) hybrid retrieval mode
- Trace ID generation and Tier 13 (13_provenance) JSONL audit logging
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from agentic.platform_kb.schemas import ContextRequest, EvidenceItem, EvidencePack
from agentic.platform_kb.retrieval_service import (
    RetrievalService,
    PROVENANCE_DIR,
)


def test_retrieval_exact_mode():
    service = RetrievalService()
    req = ContextRequest(query="What are the upload readiness rules?", include_deterministic=True)
    pack = service.retrieve(req, mode="exact")

    assert pack.retrieval_mode == "exact"
    assert pack.trace_id.startswith("trc_")
    assert isinstance(pack.deterministic_facts, dict)


def test_retrieval_semantic_mode_mock():
    mock_db_client = MagicMock()
    mock_qdrant = MagicMock()
    mock_embedder = MagicMock()

    mock_db_client.get_qdrant_client.return_value = mock_qdrant
    mock_embedder.embed_texts.return_value = [[0.1] * 384]

    mock_point = MagicMock()
    mock_point.id = "p-1"
    mock_point.score = 0.85
    mock_point.payload = {
        "chunk_id": "DOC-001-CH-0001",
        "document_id": "DOC-001",
        "section": "Architecture > Core",
        "text": "Semantic search result text content.",
        "authority_level": "A",
        "version": "1.0",
    }
    mock_qdrant.search.return_value = [mock_point]

    service = RetrievalService(db_client=mock_db_client, embedder=mock_embedder)
    req = ContextRequest(query="Tell me about core architecture", top_k=3, min_score=0.5)
    pack = service.retrieve(req, mode="semantic")

    assert pack.retrieval_mode == "semantic"
    assert len(pack.results) == 1
    res = pack.results[0]
    assert res.chunk_id == "DOC-001-CH-0001"
    assert res.score == 1.0  # 0.85 * 1.2 (Authority A) clamped to 1.0


def test_retrieval_keyword_mode_mock():
    mock_db_client = MagicMock()
    mock_store = MagicMock()

    mock_store.search_chunks_keyword.return_value = [
        {
            "chunk_id": "DOC-002-CH-0005",
            "document_id": "DOC-002",
            "section": "Compiler > Joins",
            "text": "Keyword match for relational join engine.",
            "token_count": 8,
            "authority_level": "B",
            "score": 0.70,
        }
    ]

    service = RetrievalService(db_client=mock_db_client, store=mock_store)
    req = ContextRequest(query="relational join engine", top_k=3, min_score=0.5)
    pack = service.retrieve(req, mode="keyword")

    assert pack.retrieval_mode == "structured"
    assert len(pack.results) == 1
    res = pack.results[0]
    assert res.chunk_id == "DOC-002-CH-0005"
    assert res.score == 0.70  # 0.70 * 1.0 (Authority B)


def test_retrieval_hybrid_rrf_mock():
    mock_db_client = MagicMock()
    mock_qdrant = MagicMock()
    mock_store = MagicMock()
    mock_embedder = MagicMock()

    mock_db_client.get_qdrant_client.return_value = mock_qdrant
    mock_embedder.embed_texts.return_value = [[0.1] * 384]

    # Semantic point
    mock_point = MagicMock()
    mock_point.id = "p-1"
    mock_point.score = 0.80
    mock_point.payload = {
        "chunk_id": "CH-HYBRID-001",
        "document_id": "DOC-HYBRID",
        "section": "Overview",
        "text": "Hybrid search text content.",
        "authority_level": "A",
    }
    mock_qdrant.search.return_value = [mock_point]

    # Keyword row
    mock_store.search_chunks_keyword.return_value = [
        {
            "chunk_id": "CH-HYBRID-001",
            "document_id": "DOC-HYBRID",
            "section": "Overview",
            "text": "Hybrid search text content.",
            "authority_level": "A",
            "score": 0.60,
        }
    ]

    service = RetrievalService(db_client=mock_db_client, embedder=mock_embedder, store=mock_store)
    req = ContextRequest(query="hybrid architecture query", top_k=3, min_score=0.1)
    pack = service.retrieve(req, mode="hybrid")

    assert pack.retrieval_mode == "hybrid"
    assert len(pack.results) == 1
    res = pack.results[0]
    assert res.chunk_id == "CH-HYBRID-001"
    assert res.score > 0.5  # Boosted by appearing in both RRF streams


def test_retrieval_provenance_logging(tmp_path):
    prov_dir = str(tmp_path / "13_provenance")
    service = RetrievalService(provenance_dir=prov_dir)

    req = ContextRequest(query="Audit test query", agent_id="ScoutAgent", session_id="sess_123")
    pack = service.retrieve(req, mode="exact")

    event_file = os.path.join(prov_dir, "retrieval_events.jsonl")
    assert os.path.exists(event_file)
    assert os.path.exists(os.path.join(prov_dir, "README.md"))

    with open(event_file, "r", encoding="utf-8") as f:
        line = f.readline()
        event = json.loads(line)

    assert event["trace_id"] == pack.trace_id
    assert event["agent_id"] == "ScoutAgent"
    assert event["query"] == "Audit test query"
    assert event["retrieval_mode"] == "exact"
    assert "context_hash" in event


def test_retrieval_graph_traversal_mode():
    service = RetrievalService()
    req = ContextRequest(query="ScoutAgent uses Compiler")
    pack = service.retrieve(req, mode="graph_traversal")

    assert pack.retrieval_mode == "graph_traversal"
    assert len(pack.results) > 0
    assert pack.results[0].document_id is not None

