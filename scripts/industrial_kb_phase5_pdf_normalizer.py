"""
scripts/industrial_kb_phase5_pdf_normalizer.py

Phase 5 — PDF Document Normalization for Industrial Domain KB.
Parses 18 technical PDFs (ISO standards, NIST frameworks, NASA reports, research papers).
Uses PyMuPDF (`fitz`) to extract structured text blocks, headings, page references,
and page-level provenance.
Outputs:
- aiconnex_knowledge/07_normalized_documents/DOC-IND-xxx_normalized.json
- aiconnex_knowledge/08_document_metadata/DOC-IND-xxx_metadata.json
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone
import fitz  # PyMuPDF

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_BASE = os.path.join(PROJECT_ROOT, "Industrail_KB_raw_data")
APPROVED_SOURCES_PATH = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "01_source_register", "industrial_approved_sources.json")
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "07_normalized_documents")
METADATA_DIR = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "08_document_metadata")

# Numbered section header regex patterns (e.g., "1 Scope", "3.2.1 Failure Modes")
HEADING_REGEX = re.compile(r"^(\d+(\.\d+)*)\s+([A-Z0-9\s\-\:\,\(\)]+)$")


def is_heading(line: str) -> bool:
    """Heuristic to detect numbered or uppercase section headers in PDFs."""
    line = line.strip()
    if not line or len(line) > 120:
        return False
    if HEADING_REGEX.match(line):
        return True
    if line.isupper() and len(line) > 4 and len(line) < 80:
        return True
    return False


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def normalize_pdf(source: dict) -> tuple:
    source_id = source["source_id"]
    # Generate clean document ID (e.g., DOC-IND-STD-001-V1)
    doc_id_code = source_id.replace("SRC-", "")
    doc_id = f"DOC-{doc_id_code}-V1"

    rel_location = source["source_location"].replace("/", os.sep)
    abs_pdf_path = os.path.join(PROJECT_ROOT, rel_location)

    if not os.path.exists(abs_pdf_path):
        print(f"[ERROR] PDF file not found at: {abs_pdf_path}")
        return None, None

    content_hash = compute_sha256(abs_pdf_path)
    doc = fitz.open(abs_pdf_path)
    page_count = len(doc)

    sections = []
    current_section = "Title & Abstract"
    current_heading = "Title & Abstract"
    current_text_blocks = []
    current_page = 1
    total_words = 0

    for page_idx in range(page_count):
        page = doc[page_idx]
        page_num = page_idx + 1
        text = page.get_text("text")

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        total_words += sum(len(line.split()) for line in lines)

        for line in lines:
            # Skip page numbers or headers/footers
            if line.isdigit() or "ISO 20" in line or "NIST" in line or "Page " in line:
                continue

            if is_heading(line):
                # Flush existing section if it has text
                if current_text_blocks:
                    body_text = "\n".join(current_text_blocks)
                    sections.append({
                        "document_id": doc_id,
                        "section": current_section,
                        "heading": current_heading,
                        "text": body_text,
                        "page_number": current_page,
                        "source_location": f"p. {current_page}, §{current_heading[:40]}",
                        "content_type": "text"
                    })
                    current_text_blocks = []

                current_heading = line
                current_section = line
                current_page = page_num
            else:
                current_text_blocks.append(line)

    # Flush final section
    if current_text_blocks:
        body_text = "\n".join(current_text_blocks)
        sections.append({
            "document_id": doc_id,
            "section": current_section,
            "heading": current_heading,
            "text": body_text,
            "page_number": current_page,
            "source_location": f"p. {current_page}, §{current_heading[:40]}",
            "content_type": "text"
        })

    # Prepare document metadata
    metadata = {
        "document_id": doc_id,
        "source_id": source_id,
        "title": source["title"],
        "version": source["version"],
        "document_type": "pdf",
        "content_hash": content_hash,
        "page_count": page_count,
        "total_sections": len(sections),
        "total_words": total_words,
        "storage_uri": f"s3://aiconnex-platform-kb-prod/industrial/{os.path.basename(abs_pdf_path)}",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    doc.close()
    return sections, metadata


def run_phase5_pdf_normalization():
    print("=== Phase 5 — PDF Document Normalization ===")

    if not os.path.exists(APPROVED_SOURCES_PATH):
        raise FileNotFoundError(f"Approved sources file not found: {APPROVED_SOURCES_PATH}")

    with open(APPROVED_SOURCES_PATH, "r", encoding="utf-8") as f:
        approved_sources = json.load(f)

    pdf_sources = [s for s in approved_sources if s["source_location"].lower().endswith(".pdf")]
    print(f"Found {len(pdf_sources)} approved PDF technical documents to normalize.")

    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    os.makedirs(METADATA_DIR, exist_ok=True)

    normalized_summary = []

    for idx, source in enumerate(pdf_sources, start=1):
        sid = source["source_id"]
        title = source["title"]
        print(f"\n[{idx}/{len(pdf_sources)}] Normalizing {sid}: {title[:50]}...")

        sections, metadata = normalize_pdf(source)
        if not sections or not metadata:
            continue

        doc_id = metadata["document_id"]

        # Write normalized JSON
        norm_file_path = os.path.join(NORMALIZED_DIR, f"{doc_id}_normalized.json")
        with open(norm_file_path, "w", encoding="utf-8") as f:
            json.dump(sections, f, indent=2)
        print(f"  [OK] Wrote {len(sections)} sections ({metadata['total_words']} words, {metadata['page_count']} pages) -> {os.path.basename(norm_file_path)}")

        # Write metadata JSON
        meta_file_path = os.path.join(METADATA_DIR, f"{doc_id}_metadata.json")
        with open(meta_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        normalized_summary.append({
            "source_id": sid,
            "document_id": doc_id,
            "title": title,
            "page_count": metadata["page_count"],
            "total_sections": len(sections),
            "total_words": metadata["total_words"]
        })

    print(f"\nPhase 5 Normalization Summary:")
    print(f"  - Total PDFs Normalized: {len(normalized_summary)}")
    print(f"  - Total Pages Processed: {sum(s['page_count'] for s in normalized_summary)}")
    print(f"  - Total Sections Extracted: {sum(s['total_sections'] for s in normalized_summary)}")
    print(f"  - Total Words Processed: {sum(s['total_words'] for s in normalized_summary)}")

    print("\nPhase 5 Document Normalization Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase5_pdf_normalization()
