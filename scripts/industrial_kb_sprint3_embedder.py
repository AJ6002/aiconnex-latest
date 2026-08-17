"""
scripts/industrial_kb_sprint3_embedder.py

Phase 2: Document AST Normalization, Chunking & Qdrant Vector Upsert for Sprint 3 (ML Methodology KB).
1. Extracts text from 10 ML methodology PDFs in `aiconnex_knowledge/06_raw_documents/ml_methodology/`.
2. Parses section structures with `MarkdownNormalizer`.
3. Hierarchically chunks normalized sections into `aiconnex_knowledge/09_chunks/`.
4. Embeds chunks via `EmbeddingEngine` (all-MiniLM-L6-v2) and upserts to Qdrant `platform_kb_embeddings` tagged with `knowledge_domain="ml_methodology"`.
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
from agentic.platform_kb.schemas import KnowledgeChunkRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MLEmbedder")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_ML_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "06_raw_documents", "ml_methodology")
NORMALIZED_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "07_normalized_documents")
CHUNKS_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "09_chunks")


def extract_pdf_markdown(pdf_path: str) -> str:
    """Extracts clean text with heading approximations from PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    lines = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        lines.append(f"\n## Page {page_num + 1}\n")
        lines.append(text)
    doc.close()
    return "\n".join(lines)


def process_and_embed_ml_documents():
    logger.info("=== Starting Sprint 3 Document Normalization, Chunking & Vector Upsert ===")

    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    normalizer = MarkdownNormalizer()
    chunker = HierarchicalChunker()
    embedder = EmbeddingEngine()
    upserter = QdrantUpserter()

    pdf_files = glob.glob(os.path.join(RAW_ML_DIR, "*.pdf"))
    logger.info(f"Found {len(pdf_files)} ML methodology PDF files for processing.")

    all_chunks: List[KnowledgeChunkRecord] = []
    processed_count = 0

    for idx, pdf_path in enumerate(pdf_files, start=1):
        filename = os.path.basename(pdf_path)
        doc_id = f"DOC-ML-{idx:03d}"
        logger.info(f"[{idx}/{len(pdf_files)}] Processing {filename} -> {doc_id}...")

        try:
            # 1. Extract PDF content and parse markdown sections
            raw_text = extract_pdf_markdown(pdf_path)
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
        from agentic.platform_kb.schemas import KnowledgeSourceRecord

        source_map = {}
        for c in all_chunks:
            if c.document_id not in source_map:
                source_map[c.document_id] = KnowledgeSourceRecord(
                    source_id=c.document_id,
                    title=f"ML Methodology Reference ({c.document_id})",
                    knowledge_domain="ml_methodology",
                    source_type="Academic Paper / Standard",
                    source_location=f"aiconnex_knowledge/06_raw_documents/ml_methodology/{c.document_id}",
                    authority_level="A",
                    owner="ML Methodology KB",
                    tenant_scope="global",
                    version="1.0",
                    status="Approved"
                )

        logger.info(f"Generating vector embeddings for {len(all_chunks)} ML methodology chunks...")
        texts = [c.text for c in all_chunks]
        embeddings = embedder.embed_texts(texts)

        logger.info("Upserting ML methodology vectors to Qdrant collection 'platform_kb_embeddings'...")
        res = upserter.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
            source_map=source_map
        )
        logger.info(f"Qdrant Upsert Result: {res} vectors upserted.")

    logger.info(f"=== Phase 2 Document Processing Complete! ({processed_count} PDFs, {len(all_chunks)} chunks embedded) ===")


if __name__ == "__main__":
    process_and_embed_ml_documents()
