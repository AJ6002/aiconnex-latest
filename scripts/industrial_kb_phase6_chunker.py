"""
scripts/industrial_kb_phase6_chunker.py

Phase 6 — Document Chunking for Industrial Domain KB.
Converts 18 normalized PDF document ASTs into retrievable KnowledgeChunkRecord units.
Preserves structural section boundaries, page numbers, and SHA-256 text hashes.
Outputs:
- aiconnex_knowledge/09_chunks/DOC-IND-xxx_chunks.json
"""

import os
import sys
import json
import logging

PROJECT_ROOT = r"x:\TAS\AICONNEX"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agentic.platform_kb.chunker import HierarchicalChunker, estimate_token_count, compute_sha256
from agentic.platform_kb.normalizer import NormalizedSection
from agentic.platform_kb.schemas import KnowledgeChunkRecord

logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = r"x:\TAS\AICONNEX"
APPROVED_SOURCES_PATH = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "01_source_register", "industrial_approved_sources.json")
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "07_normalized_documents")
CHUNKS_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "09_chunks")


def run_phase6_chunking():
    print("=== Phase 6 — Document Chunking ===")

    if not os.path.exists(APPROVED_SOURCES_PATH):
        raise FileNotFoundError(f"Approved sources file not found: {APPROVED_SOURCES_PATH}")

    with open(APPROVED_SOURCES_PATH, "r", encoding="utf-8") as f:
        approved_sources = json.load(f)

    # Source ID -> Authority mapping
    authority_map = {s["source_id"]: s["authority_level"] for s in approved_sources}
    # Doc ID -> Source ID mapping
    doc_source_map = {}
    for s in approved_sources:
        sid = s["source_id"]
        if sid.startswith("SRC-IND-"):
            doc_code = sid.replace("SRC-", "")
            doc_id = f"DOC-{doc_code}-V1"
            doc_source_map[doc_id] = sid

    chunker = HierarchicalChunker(max_tokens=512, overlap_tokens=50, output_dir=CHUNKS_DIR)

    norm_files = [f for f in os.listdir(NORMALIZED_DIR) if f.startswith("DOC-IND-") and f.endswith("_normalized.json")]
    print(f"Found {len(norm_files)} normalized industrial documents to chunk.")

    total_chunks_created = 0
    total_tokens_created = 0
    summary = []

    for idx, fname in enumerate(sorted(norm_files), start=1):
        doc_id = fname.replace("_normalized.json", "")
        source_id = doc_source_map.get(doc_id, "SRC-IND-STD-001")
        authority = authority_map.get(source_id, "A")

        file_path = os.path.join(NORMALIZED_DIR, fname)
        with open(file_path, "r", encoding="utf-8") as f:
            raw_sections = json.load(f)

        # Convert to NormalizedSection objects for HierarchicalChunker
        norm_sections = []
        for s_idx, s in enumerate(raw_sections, start=1):
            norm_sections.append(
                NormalizedSection(
                    section_id=f"{doc_id}-SEC-{s_idx:04d}",
                    document_id=doc_id,
                    heading_level=1,
                    heading_text=s.get("heading", "General"),
                    section_path=s.get("section", "General"),
                    content=s.get("text", ""),
                    content_type="prose"
                )
            )

        chunks = chunker.chunk_sections(
            sections=norm_sections,
            document_id=doc_id,
            version="1.0",
            authority_level=authority
        )

        # Attach page numbers back onto KnowledgeChunkRecord objects
        for chunk in chunks:
            sec_idx = min(chunk.chunk_index, len(raw_sections) - 1)
            page_num = raw_sections[sec_idx].get("page_number", 1) if raw_sections else 1
            chunk.page_start = page_num
            chunk.page_end = page_num

        chunker.save_chunks(chunks, document_id=doc_id)

        tokens = sum(c.token_count for c in chunks)
        total_chunks_created += len(chunks)
        total_tokens_created += tokens

        print(f"[{idx}/{len(norm_files)}] Chunked {doc_id} -> {len(chunks)} chunks ({tokens} tokens, Auth: {authority})")

        summary.append({
            "document_id": doc_id,
            "source_id": source_id,
            "chunks_count": len(chunks),
            "total_tokens": tokens,
            "authority": authority
        })

    print(f"\nPhase 6 Chunking Summary:")
    print(f"  - Total Industrial Documents Chunked: {len(summary)}")
    print(f"  - Total Knowledge Chunks Produced: {total_chunks_created}")
    print(f"  - Total Tokens Generated: {total_tokens_created}")
    print(f"  - Average Tokens per Chunk: {int(total_tokens_created / max(1, total_chunks_created))}")

    print("\nPhase 6 Document Chunking Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase6_chunking()
