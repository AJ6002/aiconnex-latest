"""
scripts/industrial_kb_sprint4_embedder.py

Phase 4: Document AST Normalization, Chunking & Qdrant Vector Upsert for Sprint 4 (Equipment & Asset KB).
1. Extracts text from raw PDFs and Markdown files in `aiconnex_knowledge/06_raw_documents/equipment_asset/`.
2. Parses section structures with `MarkdownNormalizer`.
3. Hierarchically chunks normalized sections into `aiconnex_knowledge/09_chunks/`.
4. Embeds chunks via `EmbeddingEngine` (all-MiniLM-L6-v2) and upserts to Qdrant `platform_kb_embeddings` tagged with `knowledge_domain="equipment_asset"`.
"""

import os
import glob
import json
import logging
from typing import List

import fitz  # PyMuPDF
from agentic.platform_kb.normalizer import MarkdownNormalizer
from agentic.platform_kb.chunker import HierarchicalChunker
from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter
from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EquipmentEmbedder")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_EQP_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "06_raw_documents", "equipment_asset")
NORMALIZED_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "07_normalized_documents")
CHUNKS_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "09_chunks")


def extract_file_markdown(file_path: str) -> str:
    """Extracts text content from PDF or reads Markdown file."""
    if file_path.endswith(".pdf"):
        doc = fitz.open(file_path)
        lines = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            lines.append(f"\n## Page {page_num + 1}\n")
            lines.append(text)
        doc.close()
        return "\n".join(lines)
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


def process_and_embed_equipment_documents():
    logger.info("=== Starting Sprint 4 Document Normalization, Chunking & Vector Upsert ===")

    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    normalizer = MarkdownNormalizer()
    chunker = HierarchicalChunker()
    embedder = EmbeddingEngine()
    upserter = QdrantUpserter()

    all_files = glob.glob(os.path.join(RAW_EQP_DIR, "*.*"))
    logger.info(f"Found {len(all_files)} equipment asset raw files for processing.")

    all_chunks: List[KnowledgeChunkRecord] = []
    processed_count = 0

    for idx, file_path in enumerate(all_files, start=1):
        filename = os.path.basename(file_path)
        doc_id = f"DOC-EQP-{idx:03d}"
        logger.info(f"[{idx}/{len(all_files)}] Processing {filename} -> {doc_id}...")

        try:
            # 1. Extract content and parse markdown sections
            raw_text = extract_file_markdown(file_path)
            sections = normalizer.parse_markdown(raw_text, document_id=doc_id)

            norm_out = os.path.join(NORMALIZED_DIR, f"{doc_id}_normalized.json")
            with open(norm_out, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in sections], f, indent=2)

            # 2. Chunk normalized sections
            chunks = chunker.chunk_sections(sections=sections, document_id=doc_id)
            chunk_out = os.path.join(CHUNKS_DIR, f"{doc_id}_chunks.json")
            with open(chunk_out, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in chunks], f, indent=2)

            all_chunks.extend(chunks)
            processed_count += 1
            logger.info(f"   -> Generated {len(sections)} sections and {len(chunks)} chunks.")

        except Exception as e:
            logger.error(f"Failed processing {filename}: {e}")

    # 3. Vector Embeddings & Qdrant Upsert
    if all_chunks:
        source_map = {}
        for c in all_chunks:
            if c.document_id not in source_map:
                source_map[c.document_id] = KnowledgeSourceRecord(
                    source_id=c.document_id,
                    title=f"Equipment & Asset Knowledge Reference ({c.document_id})",
                    knowledge_domain="equipment_asset",
                    source_type="Standard / Technical Guide / Spec",
                    source_location=f"aiconnex_knowledge/06_raw_documents/equipment_asset/{c.document_id}",
                    authority_level="A",
                    owner="Equipment Asset KB",
                    tenant_scope="global",
                    version="1.0",
                    status="Approved"
                )

        logger.info(f"Generating vector embeddings for {len(all_chunks)} equipment asset chunks...")
        texts = [c.text for c in all_chunks]
        embeddings = embedder.embed_texts(texts)

        logger.info("Upserting equipment vectors to Qdrant collection 'platform_kb_embeddings'...")
        res = upserter.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
            source_map=source_map
        )
        logger.info(f"Qdrant Upsert Result: {res} vectors upserted.")

    logger.info(f"=== Phase 4 Document Processing Complete! ({processed_count} files, {len(all_chunks)} chunks embedded) ===")


if __name__ == "__main__":
    process_and_embed_equipment_documents()
