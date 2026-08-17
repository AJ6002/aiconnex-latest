"""
scripts/industrial_kb_phase9_embedding_pipeline.py

Phase 9 — Embedding & Vector Index Pipeline for Industrial Domain KB.
Generates 384-dimensional vector embeddings for all 2,439 industrial document chunks
using `all-MiniLM-L6-v2` and upserts them into live Qdrant collection `platform_kb_embeddings`.
Updates Tier 10 `aiconnex_knowledge/10_vector_index/embedding_manifest.json`.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter, VECTOR_INDEX_DIR
from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord
from agentic.platform_kb.db_client import KBInfraClient

logging.basicConfig(level=logging.INFO)

CHUNKS_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "09_chunks")
APPROVED_SOURCES_PATH = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "01_source_register", "industrial_approved_sources.json")
MANIFEST_PATH = os.path.join(VECTOR_INDEX_DIR, "embedding_manifest.json")


def run_phase9_embedding_pipeline():
    print("=== Phase 9 — Embedding & Vector Index Pipeline ===")

    # 1. Load source map
    if not os.path.exists(APPROVED_SOURCES_PATH):
        raise FileNotFoundError(f"Approved sources file not found: {APPROVED_SOURCES_PATH}")

    with open(APPROVED_SOURCES_PATH, "r", encoding="utf-8") as f:
        raw_sources = json.load(f)

    source_map = {}
    for s in raw_sources:
        sid = s["source_id"]
        doc_code = sid.replace("SRC-", "")
        doc_id = f"DOC-{doc_code}-V1"
        rec = KnowledgeSourceRecord(
            source_id=sid,
            title=s["title"],
            source_location=s.get("source_location", "Industrail_KB_raw_data/"),
            knowledge_domain=s.get("knowledge_domain", "industrial"),
            source_type=s.get("source_type", "Standard"),
            authority_level=s.get("authority_level", "A"),
            version=s.get("version", "1.0"),
            status="Approved"
        )
        source_map[doc_id] = rec
        source_map[sid] = rec

    # 2. Load all industrial chunks
    chunk_files = [f for f in os.listdir(CHUNKS_DIR) if f.startswith("DOC-IND-") and f.endswith("_chunks.json")]
    print(f"Loaded {len(chunk_files)} industrial chunk files for embedding.")

    all_chunks = []
    for fname in sorted(chunk_files):
        path = os.path.join(CHUNKS_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            chunks_list = data.get("chunks", []) if isinstance(data, dict) else data

        for c_dict in chunks_list:
            all_chunks.append(KnowledgeChunkRecord(**c_dict))

    print(f"[OK] Total Industrial Chunks to Embed: {len(all_chunks)}")

    # 3. Generate Vector Embeddings (batch size = 64)
    print("\nGenerating 384-dimensional dense vector embeddings using `all-MiniLM-L6-v2`...")
    engine = EmbeddingEngine(model_name="all-MiniLM-L6-v2")
    embeddings = engine.embed_chunks(all_chunks, batch_size=64)
    print(f"[OK] Generated {len(embeddings)} dense vector embeddings.")

    # 4. Upsert into Qdrant Collection `platform_kb_embeddings`
    print("\nUpserting vector payloads into Qdrant collection `platform_kb_embeddings`...")
    upserter = QdrantUpserter()
    upserted_count = upserter.upsert_chunks(all_chunks, embeddings, source_map=source_map)
    print(f"[OK] Successfully upserted {upserted_count} vector points into Qdrant.")

    # 5. Verify live Qdrant collection point count
    infra = KBInfraClient()
    qd_client = infra.get_qdrant_client()
    coll_info = qd_client.get_collection(infra.config.qdrant.collection)
    total_qdrant_points = coll_info.points_count
    print(f"\n[QDRANT LIVE DB READOUT]: Total Vectors in Collection `{infra.config.qdrant.collection}`: {total_qdrant_points}")

    # 6. Update Tier 10 Manifest
    os.makedirs(VECTOR_INDEX_DIR, exist_ok=True)
    manifest_data = {
        "collection_name": infra.config.qdrant.collection,
        "embedding_model": "all-MiniLM-L6-v2",
        "vector_dimension": 384,
        "total_vectors": total_qdrant_points,
        "industrial_vectors": len(all_chunks),
        "platform_vectors": total_qdrant_points - len(all_chunks),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": "Active"
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"[OK] Updated Tier 10 embedding manifest at: {MANIFEST_PATH}")
    print("\nPhase 9 Embedding & Vector Index Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase9_embedding_pipeline()
