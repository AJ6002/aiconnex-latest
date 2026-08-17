"""
scripts/industrial_kb_sprint5_embedder.py

Phase 5: Document AST Normalization, Chunking & Qdrant Vector Upsert for Sprint 5 (Standards & Regulatory KB).
1. Generates structured metadata specification chunks for all 40 canonical standards in `canonical_standards.yaml`.
2. Normalizes and chunks primary raw standards PDFs from `Industrail_KB_raw_data/02_standards_and_guidelines/` and `03_nist_phm_frameworks/`.
3. Embeds chunks via `EmbeddingEngine` (all-MiniLM-L6-v2) and upserts to Qdrant collection `platform_kb_embeddings` tagged with `knowledge_domain="standards_regulatory"`.
"""

import os
import sys
import glob
import json
import yaml
import hashlib
import logging
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import fitz  # PyMuPDF
from agentic.platform_kb.normalizer import MarkdownNormalizer
from agentic.platform_kb.chunker import HierarchicalChunker
from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter
from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("StandardsEmbedder")

STANDARDS_YAML = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "07_standards_regulatory", "canonical_standards.yaml")
STANDARDS_RAW_DIR = os.path.join(PROJECT_ROOT, "Industrail_KB_raw_data", "02_standards_and_guidelines")
NIST_RAW_DIR = os.path.join(PROJECT_ROOT, "Industrail_KB_raw_data", "03_nist_phm_frameworks")
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "07_normalized_documents")
CHUNKS_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "09_chunks")


def build_canonical_standard_chunks() -> List[KnowledgeChunkRecord]:
    """Builds rich semantic chunks directly from canonical_standards.yaml."""
    if not os.path.exists(STANDARDS_YAML):
        logger.warning(f"Standards YAML not found at: {STANDARDS_YAML}")
        return []

    with open(STANDARDS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    standards = data.get("canonical_standards", [])
    chunks: List[KnowledgeChunkRecord] = []

    for idx, std in enumerate(standards):
        std_id = std["standard_id"]
        desig = std["designation"]
        title = std["title"]
        body = std["issuing_body"]
        stype = std["standard_type"]
        scope = std["scope"]
        jurisdiction = std["jurisdiction"]
        app = ", ".join(std.get("applicability", []))
        concepts = ", ".join(std.get("key_concepts", []))

        text = (
            f"Standard Designation: {desig}\n"
            f"Standard Identifier: {std_id}\n"
            f"Title: {title}\n"
            f"Issuing Organization: {body}\n"
            f"Type: {stype} | Jurisdiction: {jurisdiction}\n"
            f"Scope and Overview: {scope}\n"
            f"Applicability Domains & Equipment: {app}\n"
            f"Key Governed Concepts & Requirements: {concepts}\n"
            f"Authority Level: {std.get('authority', 'A')} | Status: {std.get('status', 'Approved')}"
        )

        doc_id = f"DOC-STD-{std_id.replace('STD-', '')}"
        chunk_id = f"CH-STD-{idx+1:04d}"
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        token_count = len(text.split())

        chunks.append(
            KnowledgeChunkRecord(
                chunk_id=chunk_id,
                document_id=doc_id,
                version="1.0",
                section=f"Canonical Standards Registry -> {desig}",
                subsection=title[:100],
                page_start=1,
                page_end=1,
                chunk_index=0,
                text=text,
                text_hash=text_hash,
                token_count=token_count,
                authority_level=std.get("authority", "A"),
                status="Active",
            )
        )

    return chunks


def extract_pdf_markdown(file_path: str) -> str:
    """Extracts text content from PDF file."""
    doc = fitz.open(file_path)
    lines = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        lines.append(f"\n## Page {page_num + 1}\n")
        lines.append(text)
    doc.close()
    return "\n".join(lines)


def process_and_embed_standards_documents():
    logger.info("=== Starting Sprint 5 Standards Normalization, Chunking & Vector Upsert ===")

    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    normalizer = MarkdownNormalizer()
    chunker = HierarchicalChunker()
    embedder = EmbeddingEngine()
    upserter = QdrantUpserter()

    all_chunks: List[KnowledgeChunkRecord] = []

    # 1. Canonical YAML structured chunks
    canonical_chunks = build_canonical_standard_chunks()
    all_chunks.extend(canonical_chunks)
    logger.info(f"Generated {len(canonical_chunks)} semantic chunks from canonical standards YAML.")

    # 2. Raw Standards & Guidelines PDFs
    raw_files = glob.glob(os.path.join(STANDARDS_RAW_DIR, "*.pdf")) + glob.glob(os.path.join(NIST_RAW_DIR, "*.pdf"))
    logger.info(f"Found {len(raw_files)} raw standard and framework PDF documents.")

    for file_path in raw_files:
        base_name = os.path.basename(file_path)
        doc_id = f"DOC-STD-{os.path.splitext(base_name)[0].upper().replace('_', '-')}"
        logger.info(f"Processing standard document: {base_name} -> {doc_id}")

        try:
            md_content = extract_pdf_markdown(file_path)
            sections = normalizer.parse_markdown(md_content, document_id=doc_id)

            norm_path = os.path.join(NORMALIZED_DIR, f"{doc_id}_normalized.json")
            with open(norm_path, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in sections], f, indent=2)

            file_chunks = chunker.chunk_sections(sections=sections, document_id=doc_id)
            all_chunks.extend(file_chunks)

            chunk_path = os.path.join(CHUNKS_DIR, f"{doc_id}_chunks.json")
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in file_chunks], f, indent=2)

            logger.info(f"   -> Generated {len(sections)} sections and {len(file_chunks)} chunks.")
        except Exception as e:
            logger.error(f"Failed processing {base_name}: {e}")

    logger.info(f"Total standards chunks across all sources: {len(all_chunks)}")

    # 3. Vector Embeddings Generation & Qdrant Upsert
    if all_chunks:
        source_map = {}
        for c in all_chunks:
            if c.document_id not in source_map:
                source_map[c.document_id] = KnowledgeSourceRecord(
                    source_id=c.document_id,
                    title=f"Standards & Regulatory Reference ({c.document_id})",
                    knowledge_domain="standards_regulatory",
                    source_type="International / National / Industry Standard",
                    source_location=f"aiconnex_knowledge/07_standards_regulatory/{c.document_id}",
                    authority_level="A",
                    owner="Standards & Regulatory KB",
                    tenant_scope="global",
                    version="1.0",
                    status="Approved"
                )

        logger.info(f"Generating vector embeddings for {len(all_chunks)} standards chunks with all-MiniLM-L6-v2...")
        texts = [c.text for c in all_chunks]
        embeddings = embedder.embed_texts(texts)

        logger.info("Upserting standards vectors to Qdrant collection 'platform_kb_embeddings'...")
        res = upserter.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
            source_map=source_map
        )
        logger.info(f"Qdrant Upsert Result: {res} vectors upserted under knowledge_domain='standards_regulatory'.")
        return res

    return 0


if __name__ == "__main__":
    process_and_embed_standards_documents()
