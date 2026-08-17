"""
tests/test_platform_kb_document_store.py

Unit test suite for Platform KB MinIO Document Storage Engine (Step 10).
Validates:
- SHA-256 file content hash calculation
- Object key path cleaning and normalization
- Document upload and binary download methods with mocked MinIO client
- Tier 06 (06_raw_documents) storage manifest JSON persistence
- Storage pipeline orchestration
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from agentic.platform_kb.document_store import (
    MinIODocumentStore,
    MinIOStoragePipeline,
    compute_file_sha256,
    RAW_DOCS_DIR,
)


def test_compute_file_sha256(tmp_path):
    sample_file = tmp_path / "test_file.txt"
    sample_file.write_text("Hello AIConnex Platform KB MinIO test content", encoding="utf-8")

    hash_val = compute_file_sha256(str(sample_file))
    assert len(hash_val) == 64  # Hex SHA-256 string
    assert hash_val == compute_file_sha256(str(sample_file))


def test_clean_object_key():
    store = MinIODocumentStore()

    k1 = store.clean_object_key("aiconnex_knowledge/02_platform/architecture/doc.md")
    assert k1 == "platform/architecture/doc.md"

    k2 = store.clean_object_key("aiconnex_knowledge/02_platform/contracts/spec.md")
    assert k2 == "platform/contracts/spec.md"

    k3 = store.clean_object_key("custom/path/file.txt")
    assert k3 == "custom/path/file.txt"


def test_minio_document_store_upload_and_download_mock(tmp_path):
    sample_file = tmp_path / "doc.md"
    sample_file.write_text("# Master Spec\n\nContent here.", encoding="utf-8")

    mock_db_client = MagicMock()
    mock_minio = MagicMock()
    mock_db_client.get_minio_client.return_value = mock_minio
    mock_minio.bucket_exists.return_value = True

    # Mock get_object response
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"# Master Spec\n\nContent here."
    mock_minio.get_object.return_value = mock_resp

    store = MinIODocumentStore(db_client=mock_db_client, bucket_name="test-bucket")
    res = store.upload_document(str(sample_file), "aiconnex_knowledge/02_platform/architecture/doc.md")

    assert res["object_name"] == "platform/architecture/doc.md"
    assert res["storage_uri"] == "s3://test-bucket/platform/architecture/doc.md"
    assert res["size_bytes"] > 0
    assert len(res["content_hash"]) == 64

    mock_minio.fput_object.assert_called_once_with(
        bucket_name="test-bucket",
        object_name="platform/architecture/doc.md",
        file_path=str(sample_file),
    )

    downloaded = store.download_document("platform/architecture/doc.md")
    assert downloaded == b"# Master Spec\n\nContent here."


def test_minio_storage_pipeline_saves_manifest(tmp_path):
    output_dir = str(tmp_path / "06_raw_documents")
    mock_doc_store = MagicMock()
    mock_doc_store.bucket_name = "aiconnex-platform-kb-prod"

    pipeline = MinIOStoragePipeline(doc_store=mock_doc_store, output_dir=output_dir)

    docs = [
        {
            "source_id": "PLAT-DOC-001",
            "title": "Master Architecture",
            "object_name": "platform/architecture/doc.md",
            "storage_uri": "s3://aiconnex-platform-kb-prod/platform/architecture/doc.md",
            "size_bytes": 1024,
            "content_hash": "a" * 64,
        }
    ]

    manifest_path = pipeline.save_storage_manifest(total_docs=1, total_bytes=1024, documents=docs)

    assert os.path.exists(manifest_path)
    assert os.path.exists(os.path.join(output_dir, "README.md"))

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["bucket_name"] == "aiconnex-platform-kb-prod"
    assert data["total_documents"] == 1
    assert data["total_bytes"] == 1024
    assert len(data["documents"]) == 1
    assert data["status"] == "Active"
