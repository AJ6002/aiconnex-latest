"""
tests/test_platform_kb_normalizer.py

Unit test suite for Platform KB MarkdownNormalizer.
Validates:
- Heading hierarchy and breadcrumb generation
- Code block extraction and language tagging
- Markdown table extraction
- Real document normalization from aiconnex_knowledge/02_platform/
- Tier 07 (07_normalized_documents) output directory creation and JSON persistence
"""

import os
import json
import pytest
from agentic.platform_kb.normalizer import MarkdownNormalizer, NormalizedSection, NORMALIZED_DOCS_DIR


SAMPLE_MARKDOWN = """# Master Architecture Document

Overview of the system architecture.

## 1. Compiler Component

The compiler handles data ingestion and schema validation.

### 1.1 Relational Join Engine

Handles cartesian guards and composite joins.

```python
def check_join_condition(left_id, right_id):
    return left_id == right_id
```

### 1.2 Table Schema Matrix

| Property | Type | Description |
| --- | --- | --- |
| PLANT_ID | int | Unique plant ID |
| DATE_TIME | timestamp | Measurement time |

## 2. ML Engine

Defines training and evaluation protocols.
"""


def test_markdown_normalizer_section_hierarchy():
    normalizer = MarkdownNormalizer()
    sections = normalizer.parse_markdown(SAMPLE_MARKDOWN, document_id="DOC-TEST-001")

    assert len(sections) >= 4

    # Check breadcrumb paths
    paths = [s.section_path for s in sections]
    assert any("Master Architecture Document" in p for p in paths)
    assert any("Compiler Component" in p for p in paths)
    assert any("Relational Join Engine" in p for p in paths)
    assert any("Table Schema Matrix" in p for p in paths)


def test_markdown_normalizer_code_blocks():
    normalizer = MarkdownNormalizer()
    sections = normalizer.parse_markdown(SAMPLE_MARKDOWN, document_id="DOC-TEST-001")

    # Find section with code block
    code_sections = [s for s in sections if s.code_blocks]
    assert len(code_sections) >= 1

    sec = code_sections[0]
    assert sec.code_blocks[0]["language"] == "python"
    assert "check_join_condition" in sec.code_blocks[0]["code"]
    assert sec.content_type in ("code", "mixed")


def test_markdown_normalizer_tables():
    normalizer = MarkdownNormalizer()
    sections = normalizer.parse_markdown(SAMPLE_MARKDOWN, document_id="DOC-TEST-001")

    # Find section with table
    table_sections = [s for s in sections if s.tables]
    assert len(table_sections) >= 1

    sec = table_sections[0]
    assert "PLANT_ID" in sec.tables[0]
    assert "DATE_TIME" in sec.tables[0]
    assert sec.content_type in ("table", "mixed")


def test_markdown_normalizer_real_file():
    target_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "aiconnex_knowledge",
        "02_platform",
        "compiler",
        "multi_table_zip_dataset_audit.md",
    )
    if os.path.exists(target_file):
        normalizer = MarkdownNormalizer()
        sections = normalizer.normalize_file(target_file, document_id="DOC-COMPILER-001")
        assert len(sections) >= 3
        for sec in sections:
            assert sec.document_id == "DOC-COMPILER-001"
            assert sec.section_id.startswith("SEC-")


def test_markdown_normalizer_saves_tier_07(tmp_path):
    output_dir = str(tmp_path / "07_normalized_documents")
    normalizer = MarkdownNormalizer(output_dir=output_dir)
    sections = normalizer.parse_markdown(SAMPLE_MARKDOWN, document_id="DOC-TEST-SAVE")

    output_path = normalizer.save_normalized_document(sections, document_id="DOC-TEST-SAVE")

    assert os.path.exists(output_path)
    assert os.path.exists(os.path.join(output_dir, "README.md"))

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["document_id"] == "DOC-TEST-SAVE"
    assert data["section_count"] == len(sections)
    assert len(data["sections"]) == len(sections)
