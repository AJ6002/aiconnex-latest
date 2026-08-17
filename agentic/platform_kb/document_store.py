"""
aiconnex_agent/platform_kb/document_store.py

MinIO Original Document Storage Engine for Platform Knowledge Base (Step 10).
Handles uploading raw source documents to MinIO S3 object storage bucket 'aiconnex-platform-kb-prod',
computing SHA-256 content hashes, retrieving objects, and maintaining Tier 06
'06_raw_documents/storage_manifest.json' metadata.
"""

import os
import io
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from agentic.platform_kb.config import MinIOConfig
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.schemas import KnowledgeSourceRecord
from agentic.platform_kb.source_register import SourceRegisterManager

logger = logging.getLogger(__name__)

RAW_DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "06_raw_documents",
)


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash string for a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class MinIODocumentStore:
    """
    MinIO S3 Object Store Manager.
    Uploads, downloads, and inspects binary raw documents in MinIO object store bucket.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        bucket_name: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.config = MinIOConfig()
        self.bucket_name = bucket_name or self.config.bucket

    def ensure_bucket_exists(self) -> None:
        """Ensures the configured MinIO bucket exists."""
        minio_client = self.db_client.get_minio_client()
        if not minio_client.bucket_exists(self.bucket_name):
            logger.info(f"Creating MinIO bucket '{self.bucket_name}'...")
            minio_client.make_bucket(self.bucket_name)

    def clean_object_key(self, source_location: str) -> str:
        """
        Normalizes git source location into a clean S3 object key.
        e.g. 'aiconnex_knowledge/02_platform/architecture/doc.md' -> 'platform/architecture/doc.md'
        """
        normalized = source_location.replace("\\", "/").strip("/")
        parts = normalized.split("/")

        # Strip redundant root directory prefixes
        if len(parts) > 2 and parts[0] == "aiconnex_knowledge" and parts[1].startswith("02_"):
            # e.g., ['aiconnex_knowledge', '02_platform', 'architecture', 'doc.md'] -> 'platform/architecture/doc.md'
            domain = parts[1].split("_", 1)[1] if "_" in parts[1] else parts[1]
            return "/".join([domain] + parts[2:])
        elif len(parts) > 1 and parts[0] == "aiconnex_knowledge":
            return "/".join(parts[1:])

        return normalized

    def upload_document(self, file_path: str, source_location: str) -> Dict[str, Any]:
        """
        Uploads a raw document from disk to MinIO S3 bucket.

        Args:
            file_path: Absolute local path to the raw file.
            source_location: Source location path from source register.

        Returns:
            Dict containing object_name, storage_uri, size_bytes, content_hash, and upload timestamp.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File to upload not found: {file_path}")

        self.ensure_bucket_exists()
        minio_client = self.db_client.get_minio_client()

        object_name = self.clean_object_key(source_location)
        content_hash = compute_file_sha256(file_path)
        file_size = os.path.getsize(file_path)

        logger.info(f"Uploading '{file_path}' ({file_size} bytes) to MinIO 's3://{self.bucket_name}/{object_name}'...")
        minio_client.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            file_path=file_path,
        )

        storage_uri = f"s3://{self.bucket_name}/{object_name}"
        return {
            "object_name": object_name,
            "storage_uri": storage_uri,
            "size_bytes": file_size,
            "content_hash": content_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

    def download_document(self, object_name: str) -> bytes:
        """
        Retrieves raw binary content of an object from MinIO S3 bucket.
        """
        minio_client = self.db_client.get_minio_client()
        response = None
        try:
            response = minio_client.get_object(self.bucket_name, object_name)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def list_documents(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        Lists stored document objects in the MinIO bucket.
        """
        minio_client = self.db_client.get_minio_client()
        if not minio_client.bucket_exists(self.bucket_name):
            return []

        objects = minio_client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
        results = []
        for obj in objects:
            results.append(
                {
                    "object_name": obj.object_name,
                    "size_bytes": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                    "storage_uri": f"s3://{self.bucket_name}/{obj.object_name}",
                }
            )

        return results


class MinIOStoragePipeline:
    """
    MinIO Original Document Storage Pipeline Orchestrator.
    Consumes approved sources from SourceRegisterManager, uploads raw original documents
    to MinIO, and updates Tier 06 storage manifest.
    """

    def __init__(
        self,
        doc_store: Optional[MinIODocumentStore] = None,
        output_dir: Optional[str] = None,
    ):
        self.doc_store = doc_store or MinIODocumentStore()
        self.output_dir = output_dir or RAW_DOCS_DIR
        self.source_manager = SourceRegisterManager()

    def save_storage_manifest(self, total_docs: int, total_bytes: int, documents: List[Dict[str, Any]]) -> str:
        """
        Saves storage metadata to Tier 06 (aiconnex_knowledge/06_raw_documents/storage_manifest.json).
        """
        os.makedirs(self.output_dir, exist_ok=True)
        readme_path = os.path.join(self.output_dir, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Tier 06 — Raw Documents & MinIO Storage Manifests\n\n"
                    "Stores original raw document metadata, MinIO S3 object storage keys, and content hashes.\n"
                )

        manifest_path = os.path.join(self.output_dir, "storage_manifest.json")
        manifest_data = {
            "bucket_name": self.doc_store.bucket_name,
            "total_documents": total_docs,
            "total_bytes": total_bytes,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "documents": documents,
            "status": "Active",
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        logger.info(f"Saved storage manifest to: {manifest_path}")
        return manifest_path

    def run_pipeline(self, repo_root: str = "x:\\TAS\\AICONNEX") -> Dict[str, Any]:
        """
        Executes the full Step 10 MinIO document storage pipeline end-to-end.
        """
        approved_sources = self.source_manager.get_approved_sources(domain="all")
        if not approved_sources:
            logger.warning("No approved sources found to upload to MinIO.")
            return {"total_documents": 0, "total_bytes": 0, "status": "No Sources"}

        uploaded_docs = []
        total_bytes = 0

        for src in approved_sources:
            abs_file_path = os.path.join(repo_root, src.source_location)
            if not os.path.exists(abs_file_path):
                logger.warning(f"Source file not found on disk: {abs_file_path}")
                continue

            doc_meta = self.doc_store.upload_document(abs_file_path, src.source_location)
            doc_meta["source_id"] = src.source_id
            doc_meta["title"] = src.title
            doc_meta["knowledge_domain"] = src.knowledge_domain

            uploaded_docs.append(doc_meta)
            total_bytes += doc_meta["size_bytes"]

        manifest_path = self.save_storage_manifest(
            total_docs=len(uploaded_docs),
            total_bytes=total_bytes,
            documents=uploaded_docs,
        )

        return {
            "total_documents": len(uploaded_docs),
            "total_bytes": total_bytes,
            "bucket_name": self.doc_store.bucket_name,
            "manifest_path": manifest_path,
            "status": "Success",
        }
