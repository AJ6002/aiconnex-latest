"""
aiconnex_agent/platform_kb/deterministic_store.py

PostgreSQL Relational Catalog and Keyword Search Store for Platform Knowledge Base (Step 11).
Manages PostgreSQL schema DDL, relational catalog persistence (knowledge_sources, knowledge_documents, knowledge_chunks),
trigram index keyword similarity search (pg_trgm), and Tier 11 '10_relational_catalog/catalog_manifest.json' metadata.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.schemas import (
    KnowledgeSourceRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
)
from agentic.platform_kb.source_register import SourceRegisterManager

logger = logging.getLogger(__name__)

CATALOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "11_relational_catalog",
)
CHUNKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "09_chunks",
)
STORAGE_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "06_raw_documents",
    "storage_manifest.json",
)


DDL_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    knowledge_domain VARCHAR(64) NOT NULL DEFAULT 'platform',
    source_type VARCHAR(64) NOT NULL,
    source_location TEXT NOT NULL,
    authority_level VARCHAR(8) NOT NULL DEFAULT 'A',
    owner VARCHAR(128) NOT NULL DEFAULT 'AIConnex Engineering',
    tenant_scope VARCHAR(64) NOT NULL DEFAULT 'global',
    license VARCHAR(64) NOT NULL DEFAULT 'Internal',
    version VARCHAR(32) NOT NULL DEFAULT '1.0',
    status VARCHAR(32) NOT NULL DEFAULT 'Approved',
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id VARCHAR(64) PRIMARY KEY,
    source_id VARCHAR(64) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE,
    document_type VARCHAR(32) NOT NULL DEFAULT 'markdown',
    title TEXT NOT NULL,
    version VARCHAR(32) NOT NULL DEFAULT '1.0',
    content_hash CHAR(64) NOT NULL,
    storage_uri TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    effective_from TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    effective_to TIMESTAMP WITH TIME ZONE,
    language VARCHAR(8) NOT NULL DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    version VARCHAR(32) NOT NULL DEFAULT '1.0',
    section TEXT NOT NULL,
    subsection TEXT,
    chunk_index INT NOT NULL,
    text TEXT NOT NULL,
    text_hash CHAR(64) NOT NULL,
    token_count INT NOT NULL,
    authority_level VARCHAR(8) NOT NULL DEFAULT 'A',
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_ontology_nodes (
    node_id VARCHAR(64) PRIMARY KEY,
    node_type VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_ontology_edges (
    edge_id SERIAL PRIMARY KEY,
    source_node_id VARCHAR(64) REFERENCES knowledge_ontology_nodes(node_id) ON DELETE CASCADE,
    relationship_type VARCHAR(64) NOT NULL,
    target_node_id VARCHAR(64) REFERENCES knowledge_ontology_nodes(node_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_edge UNIQUE (source_node_id, relationship_type, target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_trgm ON knowledge_chunks USING gin (text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_docs_source_id ON knowledge_documents(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_ontology_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_ontology_edges(target_node_id);
"""


class DeterministicStore:
    """
    PostgreSQL Relational Catalog and Keyword Store Manager.
    Executes DDL migrations, inserts catalog entries, and performs trigram keyword searches.
    """

    def __init__(self, db_client: Optional[KBInfraClient] = None):
        self.db_client = db_client or KBInfraClient()

    def init_db_schema(self) -> None:
        """
        Executes DDL migration script creating tables and trigram indexes in PostgreSQL.
        Idempotent design.
        """
        logger.info("Initializing PostgreSQL schema and trigram indexes...")
        conn = self.db_client.get_postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(DDL_SCHEMA_SQL)
            conn.commit()
            logger.info("PostgreSQL DDL schema initialization complete.")
        finally:
            conn.close()

    def register_sources(self, sources: List[KnowledgeSourceRecord]) -> int:
        """
        Upserts source records into knowledge_sources table.
        """
        if not sources:
            return 0

        self.init_db_schema()
        conn = self.db_client.get_postgres_connection()

        sql = """
        INSERT INTO knowledge_sources (
            source_id, title, knowledge_domain, source_type, source_location,
            authority_level, owner, tenant_scope, license, version, status, approved_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id) DO UPDATE SET
            title = EXCLUDED.title,
            knowledge_domain = EXCLUDED.knowledge_domain,
            source_type = EXCLUDED.source_type,
            source_location = EXCLUDED.source_location,
            authority_level = EXCLUDED.authority_level,
            owner = EXCLUDED.owner,
            tenant_scope = EXCLUDED.tenant_scope,
            license = EXCLUDED.license,
            version = EXCLUDED.version,
            status = EXCLUDED.status,
            approved_at = EXCLUDED.approved_at,
            updated_at = CURRENT_TIMESTAMP;
        """

        try:
            with conn.cursor() as cur:
                for s in sources:
                    cur.execute(
                        sql,
                        (
                            s.source_id,
                            s.title,
                            s.knowledge_domain,
                            s.source_type,
                            s.source_location,
                            s.authority_level,
                            s.owner,
                            s.tenant_scope,
                            s.license,
                            s.version,
                            s.status,
                            s.approved_at,
                        ),
                    )
            conn.commit()
            logger.info(f"Registered {len(sources)} sources in PostgreSQL.")
            return len(sources)
        finally:
            conn.close()

    def register_documents(self, documents: List[KnowledgeDocumentRecord]) -> int:
        """
        Upserts document records into knowledge_documents table.
        """
        if not documents:
            return 0

        self.init_db_schema()
        conn = self.db_client.get_postgres_connection()

        sql = """
        INSERT INTO knowledge_documents (
            document_id, source_id, document_type, title, version,
            content_hash, storage_uri, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (document_id) DO UPDATE SET
            source_id = EXCLUDED.source_id,
            document_type = EXCLUDED.document_type,
            title = EXCLUDED.title,
            version = EXCLUDED.version,
            content_hash = EXCLUDED.content_hash,
            storage_uri = EXCLUDED.storage_uri,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP;
        """

        try:
            with conn.cursor() as cur:
                for d in documents:
                    cur.execute(
                        sql,
                        (
                            d.document_id,
                            d.source_id,
                            d.document_type,
                            d.title,
                            d.version,
                            d.content_hash,
                            d.storage_uri,
                            d.status,
                        ),
                    )
            conn.commit()
            logger.info(f"Registered {len(documents)} documents in PostgreSQL.")
            return len(documents)
        finally:
            conn.close()

    def register_chunks(self, chunks: List[KnowledgeChunkRecord]) -> int:
        """
        Upserts chunk records into knowledge_chunks table.
        """
        if not chunks:
            return 0

        self.init_db_schema()
        conn = self.db_client.get_postgres_connection()

        sql = """
        INSERT INTO knowledge_chunks (
            chunk_id, document_id, version, section, subsection,
            chunk_index, text, text_hash, token_count, authority_level, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chunk_id) DO UPDATE SET
            document_id = EXCLUDED.document_id,
            version = EXCLUDED.version,
            section = EXCLUDED.section,
            subsection = EXCLUDED.subsection,
            chunk_index = EXCLUDED.chunk_index,
            text = EXCLUDED.text,
            text_hash = EXCLUDED.text_hash,
            token_count = EXCLUDED.token_count,
            authority_level = EXCLUDED.authority_level,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP;
        """

        try:
            with conn.cursor() as cur:
                for c in chunks:
                    cur.execute(
                        sql,
                        (
                            c.chunk_id,
                            c.document_id,
                            c.version,
                            c.section,
                            c.subsection,
                            c.chunk_index,
                            c.text,
                            c.text_hash,
                            c.token_count,
                            c.authority_level,
                            c.status,
                        ),
                    )
            conn.commit()
            logger.info(f"Registered {len(chunks)} chunks in PostgreSQL.")
            return len(chunks)
        finally:
            conn.close()

    def search_chunks_keyword(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Performs trigram keyword similarity search (pg_trgm) on knowledge_chunks.text.

        Returns:
            List of result dicts containing chunk details and similarity score.
        """
        conn = self.db_client.get_postgres_connection()
        sql = """
        SELECT c.chunk_id, c.document_id, c.section, c.chunk_index, c.text, c.token_count, c.authority_level,
               s.title, s.knowledge_domain, s.source_type,
               similarity(c.text, %s) AS score
        FROM knowledge_chunks c
        JOIN knowledge_documents d ON c.document_id = d.document_id
        JOIN knowledge_sources s ON d.source_id = s.source_id
        WHERE similarity(c.text, %s) >= %s
        ORDER BY score DESC
        LIMIT %s;
        """

        try:
            with conn.cursor() as cur:
                cur.execute(sql, (query, query, min_score, top_k))
                rows = cur.fetchall()

            results = []
            for r in rows:
                results.append(
                    {
                        "chunk_id": r[0],
                        "document_id": r[1],
                        "section": r[2],
                        "chunk_index": r[3],
                        "text": r[4],
                        "token_count": r[5],
                        "authority_level": r[6],
                        "title": r[7],
                        "knowledge_domain": r[8],
                        "source_type": r[9],
                        "score": float(r[10]),
                    }
                )

            return results
        finally:
            conn.close()

    def register_ontology_graph(self, nodes: List[Dict[str, str]], edges: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Populates knowledge_ontology_nodes and knowledge_ontology_edges in PostgreSQL.
        """
        self.init_db_schema()
        conn = self.db_client.get_postgres_connection()

        sql_node = """
        INSERT INTO knowledge_ontology_nodes (node_id, node_type)
        VALUES (%s, %s)
        ON CONFLICT (node_id) DO UPDATE SET node_type = EXCLUDED.node_type;
        """

        sql_edge = """
        INSERT INTO knowledge_ontology_edges (source_node_id, relationship_type, target_node_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (source_node_id, relationship_type, target_node_id) DO NOTHING;
        """

        try:
            with conn.cursor() as cur:
                for n in nodes:
                    cur.execute(sql_node, (n["id"], n["type"]))
                for e in edges:
                    cur.execute(sql_edge, (e["source"], e["relationship"], e["target"]))
            conn.commit()
            logger.info(f"Registered {len(nodes)} ontology nodes and {len(edges)} edges in PostgreSQL.")
            return {"nodes": len(nodes), "edges": len(edges)}
        finally:
            conn.close()


class CatalogPipeline:
    """
    PostgreSQL Catalog Pipeline Orchestrator.
    Consumes approved sources, Tier 06 storage manifest, and Tier 09 chunks to populate
    knowledge_sources, knowledge_documents, and knowledge_chunks relational tables,
    and updates Tier 11 catalog_manifest.json.
    """

    def __init__(
        self,
        store: Optional[DeterministicStore] = None,
        output_dir: Optional[str] = None,
    ):
        self.store = store or DeterministicStore()
        self.output_dir = output_dir or CATALOG_DIR
        self.source_manager = SourceRegisterManager()

    def save_catalog_manifest(
        self,
        total_sources: int,
        total_documents: int,
        total_chunks: int,
    ) -> str:
        """
        Saves metadata manifest to Tier 11 (aiconnex_knowledge/11_relational_catalog/catalog_manifest.json).
        """
        os.makedirs(self.output_dir, exist_ok=True)
        readme_path = os.path.join(self.output_dir, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Tier 11 — Relational Catalog & Deterministic Search\n\n"
                    "Stores PostgreSQL database relational catalog manifests, DDL state, and keyword index statistics.\n"
                )

        manifest_path = os.path.join(self.output_dir, "catalog_manifest.json")
        manifest_data = {
            "database_name": self.store.db_client.config.postgres.db_name,
            "total_sources": total_sources,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "status": "Active",
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        logger.info(f"Saved catalog manifest to: {manifest_path}")
        return manifest_path

    def run_pipeline(
        self,
        chunks_dir: str = CHUNKS_DIR,
        storage_manifest_path: str = STORAGE_MANIFEST_PATH,
    ) -> Dict[str, Any]:
        """
        Executes the full Step 11 PostgreSQL catalog pipeline end-to-end.
        """
        # 1. Initialize schema
        self.store.init_db_schema()

        # 2. Register sources
        approved_sources = self.source_manager.get_approved_sources(domain="all")
        sources_count = self.store.register_sources(approved_sources)

        # 3. Register documents from storage manifest
        documents: List[KnowledgeDocumentRecord] = []
        registered_doc_ids = set()

        if os.path.exists(storage_manifest_path):
            with open(storage_manifest_path, "r", encoding="utf-8") as f:
                storage_data = json.load(f)

            for doc in storage_data.get("documents", []):
                src_id = doc["source_id"]
                doc_id = f"DOC-{src_id}-V1" if not src_id.startswith("DOC-") else src_id
                doc_record = KnowledgeDocumentRecord(
                    document_id=doc_id,
                    source_id=src_id,
                    document_type="markdown",
                    title=doc["title"],
                    version="1.0",
                    content_hash=doc["content_hash"],
                    storage_uri=doc["storage_uri"],
                    status="Active",
                )
                documents.append(doc_record)
                registered_doc_ids.add(doc_id)

        # 4. Register chunks from Tier 09 & collect missing parent docs
        chunks: List[KnowledgeChunkRecord] = []
        if os.path.exists(chunks_dir):
            json_files = [f for f in os.listdir(chunks_dir) if f.endswith(".json") and f != "README.md"]
            for filename in json_files:
                file_path = os.path.join(chunks_dir, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for chunk_data in data.get("chunks", []):
                    c_record = KnowledgeChunkRecord(**chunk_data)
                    chunks.append(c_record)

                    # Ensure parent document entry exists in knowledge_documents for FK constraint
                    if c_record.document_id not in registered_doc_ids:
                        src_id = c_record.document_id.replace("DOC-", "").replace("-V1", "")
                        # Find source title if available
                        src_info = next((s for s in approved_sources if s.source_id == src_id or s.source_id in c_record.document_id), None)
                        fallback_doc = KnowledgeDocumentRecord(
                            document_id=c_record.document_id,
                            source_id=src_info.source_id if src_info else (approved_sources[0].source_id if approved_sources else "PLAT-DOC-001"),
                            document_type="markdown",
                            title=src_info.title if src_info else c_record.document_id,
                            version="1.0",
                            content_hash="0" * 64,
                            storage_uri=f"s3://aiconnex-platform-kb-prod/platform/documents/{c_record.document_id}.md",
                            status="Active",
                        )
                        documents.append(fallback_doc)
                        registered_doc_ids.add(c_record.document_id)

        docs_count = self.store.register_documents(documents)
        chunks_count = self.store.register_chunks(chunks)

        # 5. Register Ontology Graph in PostgreSQL
        ontology_yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "aiconnex_knowledge",
            "03_deterministic",
            "registries",
            "ontology.yaml",
        )
        graph_stats = {"nodes": 0, "edges": 0}
        if os.path.exists(ontology_yaml_path):
            import yaml
            with open(ontology_yaml_path, "r", encoding="utf-8") as f:
                ont_data = yaml.safe_load(f)
            graph_stats = self.store.register_ontology_graph(
                nodes=ont_data.get("nodes", []),
                edges=ont_data.get("edges", []),
            )

        # 6. Save Tier 11 catalog manifest
        manifest_path = self.save_catalog_manifest(
            total_sources=sources_count,
            total_documents=docs_count,
            total_chunks=chunks_count,
        )

        return {
            "total_sources": sources_count,
            "total_documents": docs_count,
            "total_chunks": chunks_count,
            "ontology_nodes": graph_stats["nodes"],
            "ontology_edges": graph_stats["edges"],
            "database": self.store.db_client.config.postgres.db_name,
            "manifest_path": manifest_path,
            "status": "Success",
        }
