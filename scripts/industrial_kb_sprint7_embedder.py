"""
scripts/industrial_kb_sprint7_embedder.py

Hierarchical Chunker and Qdrant Vector Embedding Pipeline for Documentation KB (Sprint 7).
Processes all 22 normalized specification documents, chunks text with parent breadcrumb injection,
generates 384-dimensional dense vectors, and upserts them into Qdrant collection 'platform_kb_embeddings'.
"""

import os
import sys
import json
import uuid
import hashlib
import logging
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.chunker import HierarchicalChunker, estimate_token_count, compute_sha256
from agentic.platform_kb.schemas import KnowledgeChunkRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NORMALIZED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "07_normalized_documents",
)
CHUNKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "09_chunks",
)


def embed_documentation_kb():
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    norm_files = [f for f in os.listdir(NORMALIZED_DIR) if f.startswith("DOC-SPEC-") and f.endswith(".json")]
    logger.info(f"Found {len(norm_files)} normalized specification files to chunk and embed.")

    infra = KBInfraClient()
    embedder = EmbeddingEngine()
    upserter = QdrantUpserter(db_client=infra)

    all_chunks: List[KnowledgeChunkRecord] = []
    chunk_payloads: List[Dict[str, Any]] = []

    for fname in sorted(norm_files):
        fpath = os.path.join(NORMALIZED_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            doc_data = json.load(f)

        doc_id = doc_data["document_id"]
        source_id = doc_data["source_id"]
        title = doc_data["title"]
        studio = doc_data.get("studio", "PlatformCore")
        category = doc_data.get("category", "Performance")
        subsystems = doc_data.get("target_subsystems", [])

        doc_chunks = []
        chunk_idx = 0

        for sec in doc_data.get("sections", []):
            sec_title = sec.get("title", "Section")
            content_blocks = sec.get("content", [])
            tables = sec.get("tables", [])

            # Combine paragraphs
            full_sec_text = "\n\n".join(content_blocks)
            if tables:
                full_sec_text += "\n\n" + "\n\n".join(tables)

            if not full_sec_text.strip():
                continue

            # Context Enveloping Header
            breadcrumb_header = (
                f"[Document: {doc_id} | Title: {title} | Studio: {studio} | "
                f"Category: {category} | Section: {sec_title} | Authority: A]\n"
                f"[Governed Subsystems: {', '.join(subsystems)}]\n\n"
            )

            # Split into ~400 token chunks
            paragraphs = full_sec_text.split("\n\n")
            current_chunk_text = breadcrumb_header
            current_tokens = estimate_token_count(breadcrumb_header)

            for para in paragraphs:
                para_tokens = estimate_token_count(para)
                if current_tokens + para_tokens > 450 and current_tokens > estimate_token_count(breadcrumb_header):
                    # Save current chunk
                    chunk_id = f"CH-{source_id}-{chunk_idx:04d}"
                    c_rec = KnowledgeChunkRecord(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        version="1.0",
                        section=sec_title,
                        subsection=None,
                        chunk_index=chunk_idx,
                        text=current_chunk_text.strip(),
                        text_hash=compute_sha256(current_chunk_text.strip()),
                        token_count=current_tokens,
                        authority_level="A",
                        status="Active",
                    )
                    doc_chunks.append(c_rec)
                    all_chunks.append(c_rec)

                    chunk_payloads.append({
                        "chunk_id": chunk_id,
                        "document_id": doc_id,
                        "source_id": source_id,
                        "knowledge_domain": "documentation",
                        "studio": studio,
                        "category": category,
                        "section": sec_title,
                        "target_subsystems": subsystems,
                        "text": current_chunk_text.strip(),
                        "authority_level": "A",
                        "tenant_id": "global",
                        "project_id": "global",
                        "scope": "global",
                        "is_tenant": False,
                    })

                    chunk_idx += 1
                    current_chunk_text = breadcrumb_header + para + "\n\n"
                    current_tokens = estimate_token_count(breadcrumb_header) + para_tokens
                else:
                    current_chunk_text += para + "\n\n"
                    current_tokens += para_tokens

            if current_chunk_text.strip() != breadcrumb_header.strip():
                chunk_id = f"CH-{source_id}-{chunk_idx:04d}"
                c_rec = KnowledgeChunkRecord(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    version="1.0",
                    section=sec_title,
                    subsection=None,
                    chunk_index=chunk_idx,
                    text=current_chunk_text.strip(),
                    text_hash=compute_sha256(current_chunk_text.strip()),
                    token_count=current_tokens,
                    authority_level="A",
                    status="Active",
                )
                doc_chunks.append(c_rec)
                all_chunks.append(c_rec)

                chunk_payloads.append({
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "source_id": source_id,
                    "knowledge_domain": "documentation",
                    "studio": studio,
                    "category": category,
                    "section": sec_title,
                    "target_subsystems": subsystems,
                    "text": current_chunk_text.strip(),
                    "authority_level": "A",
                    "tenant_id": "global",
                    "project_id": "global",
                    "scope": "global",
                    "is_tenant": False,
                })
                chunk_idx += 1

        # Save doc chunks JSON
        chunks_json_path = os.path.join(CHUNKS_DIR, f"{source_id}.json")
        with open(chunks_json_path, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in doc_chunks], f, indent=2, ensure_ascii=False)

        logger.info(f"Created {len(doc_chunks)} chunks for {doc_id} -> {chunks_json_path}")

    logger.info(f"Total chunks created across all 22 documents: {len(all_chunks)}")

    # 2. Vector Embedding & Qdrant Upsert
    try:
        qdrant = infra.get_qdrant_client()
        texts_to_embed = [p["text"] for p in chunk_payloads]
        logger.info(f"Generating embeddings for {len(texts_to_embed)} chunks via {embedder.model_name}...")
        vectors = embedder.embed_texts(texts_to_embed, batch_size=32)

        from qdrant_client.http.models import PointStruct

        points = []
        for idx, (payload, vec) in enumerate(zip(chunk_payloads, vectors)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, payload["chunk_id"]))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=payload,
                )
            )

        # Batch upsert in groups of 100
        batch_size = 100
        total_upserted = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            qdrant.upsert(
                collection_name=upserter.collection_name,
                points=batch,
            )
            total_upserted += len(batch)
            logger.info(f"Upserted batch {i//batch_size + 1}: {total_upserted}/{len(points)} points into Qdrant.")

        logger.info(f"Successfully upserted {total_upserted} Documentation vectors into Qdrant collection '{upserter.collection_name}'!")
    except Exception as e:
        logger.warning(f"Qdrant embedding upsert skipped or encountered issue: {e}")

    return len(all_chunks)


if __name__ == "__main__":
    embed_documentation_kb()
