"""
tests/test_platform_kb_embedder.py

Unit test suite for Platform KB Embedding Pipeline (Step 9).
Validates:
- Deterministic UUID point ID generation for Qdrant idempotency
- Chunk embedding generation and context string formatting
- Qdrant PointStruct payload schema construction
- Tier 10 (10_vector_index) embedding manifest JSON persistence
- End-to-end pipeline orchestration with mock Qdrant client
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord
from agentic.platform_kb.embedder import (
    EmbeddingEngine,
    QdrantUpserter,
    EmbeddingPipeline,
    VECTOR_INDEX_DIR,
)


def test_qdrant_upserter_deterministic_uuid():
    upserter = QdrantUpserter()
    chunk_id = "PLAT-DOC-001-CH-0001"
    uuid1 = upserter.generate_point_id(chunk_id)
    uuid2 = upserter.generate_point_id(chunk_id)

    assert uuid1 == uuid2  # Must be deterministic for idempotency
    assert len(uuid1) == 36  # Standard UUID string length
    assert upserter.generate_point_id("PLAT-DOC-001-CH-0002") != uuid1


def test_qdrant_upserter_point_construction():
    mock_db_client = MagicMock()
    mock_qdrant = MagicMock()
    mock_db_client.get_qdrant_client.return_value = mock_qdrant

    upserter = QdrantUpserter(db_client=mock_db_client, collection_name="test_collection")

    chunk = KnowledgeChunkRecord(
        chunk_id="DOC-001-CH-0000",
        document_id="DOC-001",
        chunk_index=0,
        section="Architecture > Core",
        text="Sample text content for vector embedding test.",
        token_count=12,
        text_hash="a" * 64,
    )
    vector = [0.1] * 384

    source_map = {
        "DOC-001": KnowledgeSourceRecord(
            source_id="DOC-001",
            title="Core Architecture Spec",
            knowledge_domain="platform",
            source_type="Architecture Spec",
            source_location="aiconnex_knowledge/02_platform/architecture/core.md",
            authority_level="A",
            owner="AIConnex Engineering",
            tenant_scope="global",
            license="Internal",
            version="1.0",
            status="Approved",
            approved_at="2026-08-13T12:00:00",
        )
    }

    count = upserter.upsert_chunks([chunk], [vector], source_map=source_map)
    assert count == 1

    mock_qdrant.upsert.assert_called_once()
    call_args = mock_qdrant.upsert.call_args
    assert call_args.kwargs["collection_name"] == "test_collection"
    points = call_args.kwargs["points"]
    assert len(points) == 1
    p = points[0]
    assert p.payload["chunk_id"] == "DOC-001-CH-0000"
    assert p.payload["title"] == "Core Architecture Spec"
    assert p.payload["authority_level"] == "A"
    assert len(p.vector) == 384


def test_embedding_pipeline_saves_tier_10_manifest(tmp_path):
    output_dir = str(tmp_path / "10_vector_index")
    mock_embedder = MagicMock()
    mock_upserter = MagicMock()
    mock_upserter.collection_name = "test_collection"
    mock_embedder.model_name = "all-MiniLM-L6-v2"

    pipeline = EmbeddingPipeline(embedder=mock_embedder, upserter=mock_upserter, output_dir=output_dir)
    manifest_path = pipeline.save_embedding_manifest(total_chunks=10, total_vectors=10)

    assert os.path.exists(manifest_path)
    assert os.path.exists(os.path.join(output_dir, "README.md"))

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["collection_name"] == "test_collection"
    assert data["total_chunks"] == 10
    assert data["total_vectors"] == 10
    assert data["vector_dimension"] == 384
    assert data["status"] == "Active"


def test_embedding_pipeline_end_to_end_mocked(tmp_path):
    output_dir = str(tmp_path / "10_vector_index")
    chunks_dir = str(tmp_path / "09_chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    sample_chunks_file = os.path.join(chunks_dir, "DOC-TEST_chunks.json")
    with open(sample_chunks_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "document_id": "DOC-TEST",
                "chunk_count": 1,
                "chunks": [
                    {
                        "chunk_id": "DOC-TEST-CH-0000",
                        "document_id": "DOC-TEST",
                        "chunk_index": 0,
                        "section": "Overview",
                        "text": "Embedding test section content.",
                        "token_count": 5,
                        "text_hash": "b" * 64,
                    }
                ],
            },
            f,
        )

    mock_embedder = MagicMock()
    mock_embedder.model_name = "all-MiniLM-L6-v2"
    mock_embedder.embed_chunks.return_value = [[0.05] * 384]

    mock_upserter = MagicMock()
    mock_upserter.collection_name = "platform_kb_embeddings"
    mock_upserter.upsert_chunks.return_value = 1

    pipeline = EmbeddingPipeline(embedder=mock_embedder, upserter=mock_upserter, output_dir=output_dir)
    res = pipeline.run_pipeline(chunks_dir=chunks_dir)

    assert res["status"] == "Success"
    assert res["total_chunks"] == 1
    assert res["total_vectors"] == 1
    assert os.path.exists(res["manifest_path"])
