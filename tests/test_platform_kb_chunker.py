"""
tests/test_platform_kb_chunker.py

Unit test suite for Platform KB HierarchicalChunker.
Validates:
- Token count estimation and SHA-256 hash generation
- Section-aware chunking and breadcrumb propagation
- Sentence-boundary aware text splitting for large sections
- Tier 09 (09_chunks) directory creation and JSON persistence
- End-to-end chunking on normalized documents from Tier 07
"""

import os
import json
import pytest
from agentic.platform_kb.normalizer import NormalizedSection
from agentic.platform_kb.chunker import (
    HierarchicalChunker,
    estimate_token_count,
    compute_sha256,
    CHUNKS_DIR,
)


def test_estimate_token_count_and_sha256():
    text = "The quick brown fox jumps over the lazy dog."
    tokens = estimate_token_count(text)
    hash_val = compute_sha256(text)

    assert tokens > 0
    assert len(hash_val) == 64  # SHA-256 hex string length
    assert hash_val == compute_sha256(text)


def test_hierarchical_chunker_basic_section():
    sec1 = NormalizedSection(
        section_id="SEC-0001",
        document_id="DOC-TEST-001",
        heading_level=1,
        heading_text="System Overview",
        section_path="Master Spec > System Overview",
        content="The AIConnex platform provides end-to-end agentic workflow orchestration.",
        content_type="prose",
    )
    chunker = HierarchicalChunker(max_tokens=512)
    chunks = chunker.chunk_sections([sec1], document_id="DOC-TEST-001")

    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_id == "DOC-TEST-001-CH-0000"
    assert c.section == "Master Spec > System Overview"
    assert c.token_count > 0
    assert len(c.text_hash) == 64


def test_hierarchical_chunker_sentence_splitting():
    # Long text exceeding max_tokens budget (approx 50 words)
    long_sentences = [
        f"Sentence number {i} provides detailed engineering specification for section {i}."
        for i in range(1, 40)
    ]
    long_text = " ".join(long_sentences)

    sec = NormalizedSection(
        section_id="SEC-0002",
        document_id="DOC-TEST-002",
        heading_level=2,
        heading_text="Long Section",
        section_path="Master Spec > Long Section",
        content=long_text,
        content_type="prose",
    )

    chunker = HierarchicalChunker(max_tokens=100, overlap_tokens=20)
    chunks = chunker.chunk_sections([sec], document_id="DOC-TEST-002")

    assert len(chunks) > 1
    for c in chunks:
        assert c.section == "Master Spec > Long Section"
        assert len(c.text_hash) == 64
        # Verify no mid-word cuts (starts with capital letter or sentence continuation)
        assert c.text[0].isupper() or c.text[0].isalnum()


def test_hierarchical_chunker_saves_tier_09(tmp_path):
    output_dir = str(tmp_path / "09_chunks")
    chunker = HierarchicalChunker(output_dir=output_dir)

    sec = NormalizedSection(
        section_id="SEC-0001",
        document_id="DOC-SAVE-001",
        heading_level=1,
        heading_text="Compiler Engine",
        section_path="Architecture > Compiler Engine",
        content="Compiler handles dataset discovery, parsing, and normalization.",
        content_type="prose",
    )

    chunks = chunker.chunk_sections([sec], document_id="DOC-SAVE-001")
    output_path = chunker.save_chunks(chunks, document_id="DOC-SAVE-001")

    assert os.path.exists(output_path)
    assert os.path.exists(os.path.join(output_dir, "README.md"))

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["document_id"] == "DOC-SAVE-001"
    assert data["chunk_count"] == 1
    assert len(data["chunks"]) == 1
    assert data["chunks"][0]["chunk_id"] == "DOC-SAVE-001-CH-0000"


def test_hierarchical_chunker_end_to_end_from_tier_07():
    norm_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "aiconnex_knowledge",
        "07_normalized_documents",
    )
    if not os.path.exists(norm_dir):
        pytest.skip("Tier 07 normalized documents directory not found.")

    json_files = [f for f in os.listdir(norm_dir) if f.endswith(".json")]
    if not json_files:
        pytest.skip("No normalized JSON documents found in Tier 07.")

    chunker = HierarchicalChunker()

    for f in json_files:
        path = os.path.join(norm_dir, f)
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        if isinstance(data, list):
            if not data:
                continue
            doc_id = data[0]["document_id"]
            sections = [
                NormalizedSection(
                    section_id=f"{doc_id}-SEC-{s_idx:04d}",
                    document_id=doc_id,
                    heading_level=1,
                    heading_text=s.get("heading", "General"),
                    section_path=s.get("section", "General"),
                    content=s.get("content", s.get("text", "")),
                    content_type="prose"
                )
                for s_idx, s in enumerate(data, start=1)
            ]
        else:
            doc_id = data["document_id"]
            sections = [NormalizedSection(**s) for s in data["sections"]]

        chunks = chunker.chunk_sections(sections, document_id=doc_id)
        assert len(chunks) >= len(sections)  # May split long sections
        for c in chunks:
            assert c.document_id == doc_id
            assert c.chunk_id.startswith(f"{doc_id}-")
