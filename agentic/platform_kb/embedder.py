"""
aiconnex_agent/platform_kb/embedder.py

Embedding Pipeline and Qdrant Upserter for Platform Knowledge Base (Step 9).
Generates 384-dimensional vector embeddings using sentence-transformers (default: 'all-MiniLM-L6-v2'),
upserts vector payloads into Qdrant collection 'platform_kb_embeddings', and maintains Tier 10
'10_vector_index/embedding_manifest.json' metadata.
"""

import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from agentic.platform_kb.config import QdrantConfig
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord
from agentic.platform_kb.source_register import SourceRegisterManager

logger = logging.getLogger(__name__)

VECTOR_INDEX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "10_vector_index",
)
CHUNKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "09_chunks",
)

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_VECTOR_DIM = 384


class EmbeddingEngine:
    """
    Sentence-Transformers Vector Embedding Engine.
    Lazy-loads local transformer models and generates dense floating-point vector representations.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    def get_model(self):
        """Lazy loads sentence-transformers model instance."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading SentenceTransformer model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.error(f"Failed to load SentenceTransformer model '{self.model_name}': {e}")
                raise RuntimeError(f"EmbeddingEngine model initialization failed: {e}") from e
        return self._model

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generates dense vector embeddings for a list of text strings.
        """
        if not texts:
            return []

        model = self.get_model()
        logger.info(f"Generating embeddings for {len(texts)} text items (batch_size={batch_size})...")
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_chunks(self, chunks: List[KnowledgeChunkRecord], batch_size: int = 32) -> List[List[float]]:
        """
        Generates dense vector embeddings for a list of KnowledgeChunkRecord objects.
        Injects section breadcrumb header into text representation for context-aware embeddings.
        """
        texts = []
        for c in chunks:
            # Contextualized text combining breadcrumb path and content
            contextual_text = f"Section: {c.section}\nContent:\n{c.text}" if c.section else c.text
            texts.append(contextual_text)

        return self.embed_texts(texts, batch_size=batch_size)


class QdrantUpserter:
    """
    Qdrant Vector DB Upsert Manager.
    Maps KnowledgeChunkRecords + embeddings into Qdrant PointStructs and upserts into collection.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        collection_name: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.config = QdrantConfig()
        self.collection_name = collection_name or self.config.collection

    def generate_point_id(self, chunk_id: str) -> str:
        """
        Generates a deterministic UUID string from chunk_id (using UUIDv5 with DNS namespace).
        Ensures idempotent upserts in Qdrant.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def upsert_chunks(
        self,
        chunks: List[KnowledgeChunkRecord],
        embeddings: List[List[float]],
        source_map: Optional[Dict[str, KnowledgeSourceRecord]] = None,
    ) -> int:
        """
        Upserts chunk records and their corresponding vector embeddings into Qdrant.

        Args:
            chunks: List of KnowledgeChunkRecord objects.
            embeddings: List of 384-dimensional vector arrays.
            source_map: Optional dict mapping source_id -> KnowledgeSourceRecord for payload enrichment.

        Returns:
            Number of points successfully upserted.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch between chunk count ({len(chunks)}) and embedding count ({len(embeddings)})")

        if not chunks:
            return 0

        from qdrant_client.models import PointStruct

        qdrant = self.db_client.get_qdrant_client()
        points: List[PointStruct] = []

        for chunk, vector in zip(chunks, embeddings):
            point_id = self.generate_point_id(chunk.chunk_id)
            source_info = source_map.get(chunk.document_id) if source_map else None

            tenant_id = getattr(source_info, "tenant_scope", "global") if source_info else "global"
            scope = getattr(source_info, "scope", "global") if source_info else ("global" if tenant_id == "global" else "tenant")
            project_id = getattr(source_info, "project_id", "global") if source_info else "global"

            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "section": chunk.section,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "text_hash": chunk.text_hash,
                "title": source_info.title if source_info else "",
                "knowledge_domain": source_info.knowledge_domain if source_info else "platform",
                "source_type": source_info.source_type if source_info else "Spec",
                "authority_level": source_info.authority_level if source_info else "A",
                "owner": source_info.owner if source_info else "AIConnex Engineering",
                "tenant_scope": tenant_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "scope": scope,
                "version": source_info.version if source_info else "1.0",
                "status": source_info.status if source_info else "Approved",
            }

            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        logger.info(f"Upserting {len(points)} points into Qdrant collection '{self.collection_name}'...")
        qdrant.upsert(collection_name=self.collection_name, points=points)
        return len(points)


class EmbeddingPipeline:
    """
    End-to-End Platform KB Embedding Pipeline Orchestrator.
    Consumes Tier 09 chunks, generates vector embeddings, upserts to Qdrant,
    and updates Tier 10 vector index manifest.
    """

    def __init__(
        self,
        embedder: Optional[EmbeddingEngine] = None,
        upserter: Optional[QdrantUpserter] = None,
        output_dir: Optional[str] = None,
    ):
        self.embedder = embedder or EmbeddingEngine()
        self.upserter = upserter or QdrantUpserter()
        self.output_dir = output_dir or VECTOR_INDEX_DIR
        self.source_manager = SourceRegisterManager()

    def load_all_chunks(self, chunks_dir: str = CHUNKS_DIR) -> List[KnowledgeChunkRecord]:
        """
        Reads all chunk JSON files from Tier 09 directory.
        """
        if not os.path.exists(chunks_dir):
            logger.warning(f"Chunks directory not found at: {chunks_dir}")
            return []

        chunks: List[KnowledgeChunkRecord] = []
        json_files = [f for f in os.listdir(chunks_dir) if f.endswith(".json") and f != "README.md"]

        for filename in json_files:
            file_path = os.path.join(chunks_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for chunk_data in data.get("chunks", []):
                    chunks.append(KnowledgeChunkRecord(**chunk_data))
            except Exception as e:
                logger.error(f"Error reading chunk file {filename}: {e}")

        logger.info(f"Loaded {len(chunks)} chunk records from {len(json_files)} files in Tier 09.")
        return chunks

    def save_embedding_manifest(self, total_chunks: int, total_vectors: int) -> str:
        """
        Saves embedding metadata to Tier 10 (aiconnex_knowledge/10_vector_index/embedding_manifest.json).
        """
        os.makedirs(self.output_dir, exist_ok=True)
        readme_path = os.path.join(self.output_dir, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Tier 10 — Vector Index & Embeddings\n\n"
                    "Stores Qdrant vector index manifests, embedding model metadata, and vector index sync records.\n"
                )

        manifest_path = os.path.join(self.output_dir, "embedding_manifest.json")
        manifest_data = {
            "collection_name": self.upserter.collection_name,
            "total_chunks": total_chunks,
            "total_vectors": total_vectors,
            "vector_dimension": DEFAULT_VECTOR_DIM,
            "embedding_model": self.embedder.model_name,
            "last_upserted_at": datetime.now(timezone.utc).isoformat(),
            "status": "Active",
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        logger.info(f"Saved embedding manifest to: {manifest_path}")
        return manifest_path

    def run_pipeline(self, chunks_dir: str = CHUNKS_DIR, batch_size: int = 32) -> Dict[str, Any]:
        """
        Executes the full Step 9 embedding pipeline end-to-end.
        """
        # 1. Load approved source metadata map
        approved_sources = self.source_manager.get_approved_sources(domain="all")
        source_map = {src.source_id: src for src in approved_sources}

        # 2. Load all chunks from Tier 09
        chunks = self.load_all_chunks(chunks_dir=chunks_dir)
        if not chunks:
            logger.warning("No chunks found to embed.")
            return {"total_chunks": 0, "total_vectors": 0, "status": "No Chunks"}

        # 3. Generate vector embeddings
        embeddings = self.embedder.embed_chunks(chunks, batch_size=batch_size)

        # 4. Upsert vectors + payloads into Qdrant
        upserted_count = self.upserter.upsert_chunks(chunks, embeddings, source_map=source_map)

        # 5. Save Tier 10 embedding manifest
        manifest_path = self.save_embedding_manifest(total_chunks=len(chunks), total_vectors=upserted_count)

        return {
            "total_chunks": len(chunks),
            "total_vectors": upserted_count,
            "collection_name": self.upserter.collection_name,
            "embedding_model": self.embedder.model_name,
            "manifest_path": manifest_path,
            "status": "Success",
        }
