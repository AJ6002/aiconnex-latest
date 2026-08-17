"""
aiconnex_agent/platform_kb/chunker.py

Hierarchical Section-Aware Chunker for Platform Knowledge Base.
Converts NormalizedSection objects into retrievable KnowledgeChunkRecord instances.

Features:
- Section-boundary preservation (keeps section hierarchy breadcrumbs attached to every chunk)
- Sentence-boundary aware text splitting (prevents mid-sentence cuts)
- SHA-256 text hashing for duplicate detection and change tracking
- Token count estimation and overlap budget management
- Saves output JSON records under Tier `aiconnex_knowledge/09_chunks/`
"""

import os
import re
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional

from agentic.platform_kb.schemas import KnowledgeChunkRecord
from agentic.platform_kb.normalizer import NormalizedSection

logger = logging.getLogger(__name__)

CHUNKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "09_chunks",
)


def estimate_token_count(text: str) -> int:
    """Estimates token count for text (rough heuristic ~ 1 token per 4 characters or 0.75 words)."""
    words = len(text.split())
    chars = len(text)
    return max(1, int((words * 1.3 + chars / 4.0) / 2.0))


def compute_sha256(text: str) -> str:
    """Computes SHA-256 hash hex string of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class HierarchicalChunker:
    """
    Hierarchical Section-Aware Chunker.
    Splits normalized Markdown sections into retrievable KnowledgeChunkRecord items.
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 50,
        output_dir: Optional[str] = None,
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.output_dir = output_dir or CHUNKS_DIR

    def _split_text_by_sentences(self, text: str, max_tokens: int) -> List[str]:
        """Splits a long string into sentence-bounded chunks without breaking mid-sentence."""
        sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
        chunks: List[str] = []
        current_sentences: List[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = estimate_token_count(sentence)
            if current_tokens + sentence_tokens > max_tokens and current_sentences:
                chunks.append(" ".join(current_sentences))
                # Keep last sentence for overlap if possible
                overlap_text = current_sentences[-1] if self.overlap_tokens > 0 else ""
                current_sentences = [overlap_text, sentence] if overlap_text else [sentence]
                current_tokens = estimate_token_count(" ".join(current_sentences))
            else:
                current_sentences.append(sentence)
                current_tokens += sentence_tokens

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks or [text]

    def chunk_sections(
        self,
        sections: List[NormalizedSection],
        document_id: str,
        version: str = "1.0",
        authority_level: str = "A",
    ) -> List[KnowledgeChunkRecord]:
        """
        Converts a list of NormalizedSection records into KnowledgeChunkRecord objects.
        """
        chunks: List[KnowledgeChunkRecord] = []
        chunk_index = 0

        for sec in sections:
            sec_text = sec.content.strip()
            if sec.tables and not sec_text:
                sec_text = "\n\n".join(sec.tables).strip()
            elif sec.tables and sec_text:
                sec_text = sec_text + "\n\n" + "\n\n".join(sec.tables).strip()

            if not sec_text:
                continue

            sec_tokens = estimate_token_count(sec_text)

            # Case A: Section fits within max_tokens budget
            if sec_tokens <= self.max_tokens:
                c_id = f"{document_id}-CH-{chunk_index:04d}"
                record = KnowledgeChunkRecord(
                    chunk_id=c_id,
                    document_id=document_id,
                    version=version,
                    section=sec.section_path,
                    subsection=sec.heading_text if sec.heading_text != sec.section_path else None,
                    chunk_index=chunk_index,
                    text=sec_text,
                    text_hash=compute_sha256(sec_text),
                    token_count=sec_tokens,
                    authority_level=authority_level,  # type: ignore
                    status="Active",
                )
                chunks.append(record)
                chunk_index += 1

            # Case B: Section exceeds max_tokens budget — split by sentences
            else:
                split_texts = self._split_text_by_sentences(sec_text, self.max_tokens)
                for part in split_texts:
                    part_text = part.strip()
                    if not part_text:
                        continue

                    c_id = f"{document_id}-CH-{chunk_index:04d}"
                    part_tokens = estimate_token_count(part_text)
                    record = KnowledgeChunkRecord(
                        chunk_id=c_id,
                        document_id=document_id,
                        version=version,
                        section=sec.section_path,
                        subsection=sec.heading_text if sec.heading_text != sec.section_path else None,
                        chunk_index=chunk_index,
                        text=part_text,
                        text_hash=compute_sha256(part_text),
                        token_count=part_tokens,
                        authority_level=authority_level,  # type: ignore
                        status="Active",
                    )
                    chunks.append(record)
                    chunk_index += 1

        return chunks

    def save_chunks(self, chunks: List[KnowledgeChunkRecord], document_id: str) -> str:
        """
        Saves KnowledgeChunkRecord items as a JSON file under Tier 09 (aiconnex_knowledge/09_chunks/).
        Creates Tier 09 directory on demand if it does not exist.
        """
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            readme_path = os.path.join(self.output_dir, "README.md")
            if not os.path.exists(readme_path):
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write("# Tier 09 — Chunks\n\nContains hierarchical section-aware chunks with parent breadcrumb metadata, SHA-256 text hashes, and token estimates.\n")

        output_filename = f"{document_id}_chunks.json"
        output_path = os.path.join(self.output_dir, output_filename)

        data = {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "total_tokens": sum(c.token_count for c in chunks),
            "chunks": [c.model_dump() for c in chunks],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(chunks)} chunks to: {output_path}")
        return output_path
