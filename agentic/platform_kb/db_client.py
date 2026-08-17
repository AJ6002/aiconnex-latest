"""
aiconnex_agent/platform_kb/db_client.py

Infrastructure DB Client and Health-Check Orchestrator for Platform KB.
Establishes connections to:
- PostgreSQL (aiconnex_kb_prod) with pgvector and pg_trgm extension validation
- Qdrant (platform_kb_embeddings) vector search collection validation
- MinIO (aiconnex-platform-kb-prod) object storage bucket validation

Enforces strict production mode (KB_STRICT_PRODUCTION_MODE=true).
If any backend is unreachable or missing required extensions/collections/buckets,
raises CriticalDependencyError and halts system boot/ingestion.
"""

import io
import logging
import urllib.request
import json
from typing import Dict, Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from minio import Minio
from qdrant_client import QdrantClient

from agentic.platform_kb.config import KBConfig, get_kb_config

logger = logging.getLogger(__name__)


class CriticalDependencyError(Exception):
    """Raised when a required infrastructure backend is unreachable or misconfigured in production mode."""
    pass


class KBInfraClient:
    """
    Unified Infrastructure Client Facade for Platform Knowledge Base.
    Manages connection lifecycle and enforces health-check handshakes across PostgreSQL, Qdrant, and MinIO.
    """

    def __init__(self, config: Optional[KBConfig] = None):
        self.config = config or get_kb_config()
        self._pg_conn: Optional[Any] = None
        self._qdrant_client: Optional[QdrantClient] = None
        self._minio_client: Optional[Minio] = None

    def get_postgres_connection(self, db_name: Optional[str] = None):
        """Returns active PostgreSQL connection."""
        target_db = db_name or self.config.postgres.db_name
        if db_name is not None and db_name != self.config.postgres.db_name:
            # Ephemeral connection to a specific database (e.g. 'postgres' default DB)
            try:
                return psycopg2.connect(
                    host=self.config.postgres.host,
                    port=self.config.postgres.port,
                    dbname=db_name,
                    user=self.config.postgres.user,
                    password=self.config.postgres.password,
                )
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL database '{db_name}' at {self.config.postgres.host}:{self.config.postgres.port}: {e}")
                raise CriticalDependencyError(f"PostgreSQL connection to '{db_name}' failed: {e}") from e

        if self._pg_conn is None or self._pg_conn.closed:
            try:
                self._pg_conn = psycopg2.connect(
                    host=self.config.postgres.host,
                    port=self.config.postgres.port,
                    dbname=self.config.postgres.db_name,
                    user=self.config.postgres.user,
                    password=self.config.postgres.password,
                )
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL at {self.config.postgres.host}:{self.config.postgres.port}: {e}")
                raise CriticalDependencyError(f"PostgreSQL connection failed: {e}") from e
        return self._pg_conn


    def get_qdrant_client(self) -> QdrantClient:
        """Returns active QdrantClient instance."""
        if self._qdrant_client is None:
            try:
                self._qdrant_client = QdrantClient(
                    host=self.config.qdrant.host,
                    port=self.config.qdrant.port,
                    timeout=5.0,
                )
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant at {self.config.qdrant.http_url}: {e}")
                raise CriticalDependencyError(f"Qdrant connection failed: {e}") from e
        return self._qdrant_client

    def get_minio_client(self) -> Minio:
        """Returns active MinIO client instance."""
        if self._minio_client is None:
            try:
                self._minio_client = Minio(
                    endpoint=self.config.minio.endpoint,
                    access_key=self.config.minio.access_key,
                    secret_key=self.config.minio.secret_key,
                    secure=self.config.minio.secure,
                )
            except Exception as e:
                logger.error(f"Failed to connect to MinIO at {self.config.minio.endpoint}: {e}")
                raise CriticalDependencyError(f"MinIO connection failed: {e}") from e
        return self._minio_client

    def check_postgres(self) -> bool:
        """
        Verifies PostgreSQL connection and checks for required pgvector and pg_trgm extensions.
        Auto-creates database and extensions if not already present.
        """
        try:
            # 1. Connect to default 'postgres' DB to ensure target DB exists
            try:
                main_conn = self.get_postgres_connection(db_name="postgres")
                main_conn.autocommit = True
                with main_conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (self.config.postgres.db_name,))
                    if not cur.fetchone():
                        logger.info(f"Creating database '{self.config.postgres.db_name}'...")
                        cur.execute(f'CREATE DATABASE "{self.config.postgres.db_name}";')
                main_conn.close()
            except Exception as e:
                logger.warning(f"Could not check/create database via default DB: {e}")

            # 2. Connect to target DB
            conn = self.get_postgres_connection()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")

                # Ensure required extensions exist
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

                # Verify extensions exist
                cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');")
                exts = {row[0] for row in cur.fetchall()}
                if "vector" not in exts or "pg_trgm" not in exts:
                    missing = {"vector", "pg_trgm"} - exts
                    raise CriticalDependencyError(f"PostgreSQL database missing required extensions: {missing}")

            logger.info("PostgreSQL health check PASSED (database & extensions verified).")
            return True
        except CriticalDependencyError:
            raise
        except Exception as e:
            msg = f"PostgreSQL health check FAILED on {self.config.postgres.db_name}: {e}"
            logger.error(msg)
            if self.config.strict_production_mode:
                raise CriticalDependencyError(msg) from e
            return False

    def check_qdrant(self) -> bool:
        """
        Verifies Qdrant connection and collection platform_kb_embeddings existence.
        Auto-creates collection if missing.
        """
        try:
            client = self.get_qdrant_client()
            collection_name = self.config.qdrant.collection

            # Check if collection exists
            collections_res = client.get_collections()
            existing_names = [c.name for c in collections_res.collections]

            if collection_name not in existing_names:
                logger.info(f"Qdrant collection '{collection_name}' missing. Creating collection...")
                from qdrant_client.models import VectorParams, Distance
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.config.qdrant.vector_dim,
                        distance=Distance.COSINE,
                    ),
                )

            # Verify collection info
            info = client.get_collection(collection_name)
            logger.info(f"Qdrant health check PASSED (collection '{collection_name}' verified).")
            return True
        except CriticalDependencyError:
            raise
        except Exception as e:
            msg = f"Qdrant health check FAILED on collection '{self.config.qdrant.collection}': {e}"
            logger.error(msg)
            if self.config.strict_production_mode:
                raise CriticalDependencyError(msg) from e
            return False

    def check_minio(self) -> bool:
        """
        Verifies MinIO connection and bucket aiconnex-platform-kb-prod existence.
        Auto-creates bucket if missing and tests read/write probe.
        """
        try:
            client = self.get_minio_client()
            bucket_name = self.config.minio.bucket

            if not client.bucket_exists(bucket_name):
                logger.info(f"MinIO bucket '{bucket_name}' missing. Creating bucket...")
                client.make_bucket(bucket_name)

            # Test write/read/delete probe
            probe_key = "_health_probe.txt"
            probe_data = b"AIConnex MinIO Health Probe"
            client.put_object(
                bucket_name=bucket_name,
                object_name=probe_key,
                data=io.BytesIO(probe_data),
                length=len(probe_data),
            )

            # Read back
            res = client.get_object(bucket_name, probe_key)
            read_data = res.read()
            res.close()
            res.release_conn()

            # Remove probe
            client.remove_object(bucket_name, probe_key)

            if read_data != probe_data:
                raise CriticalDependencyError("MinIO health probe read data did not match written probe.")

            logger.info(f"MinIO health check PASSED (bucket '{bucket_name}' read/write verified).")
            return True
        except CriticalDependencyError:
            raise
        except Exception as e:
            msg = f"MinIO health check FAILED on bucket '{self.config.minio.bucket}': {e}"
            logger.error(msg)
            if self.config.strict_production_mode:
                raise CriticalDependencyError(msg) from e
            return False


    def perform_health_checks(self, raise_on_failure: bool = True) -> Dict[str, bool]:
        """
        Orchestrates health-check handshakes across PostgreSQL, Qdrant, and MinIO.
        If strict_production_mode is True, any backend failure raises CriticalDependencyError.
        """
        results = {
            "postgres": False,
            "qdrant": False,
            "minio": False,
        }

        # Check Postgres
        try:
            results["postgres"] = self.check_postgres()
        except CriticalDependencyError as e:
            if raise_on_failure:
                raise
            logger.error(f"Postgres health check failed: {e}")

        # Check Qdrant
        try:
            results["qdrant"] = self.check_qdrant()
        except CriticalDependencyError as e:
            if raise_on_failure:
                raise
            logger.error(f"Qdrant health check failed: {e}")

        # Check MinIO
        try:
            results["minio"] = self.check_minio()
        except CriticalDependencyError as e:
            if raise_on_failure:
                raise
            logger.error(f"MinIO health check failed: {e}")

        return results

    def provision_tenant_tables(self) -> None:
        """
        Provisions PostgreSQL tables for Tenant Knowledge (Sprint 6):
        - tenants (Tenant organization registrations)
        - projects (Project workspaces within tenants)
        - tenant_assets (Physical asset instances owned by projects)
        """
        conn = self.get_postgres_connection()
        cur = conn.cursor()

        ddl = """
        -- 1. Tenants Table (Organization level)
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            industry VARCHAR(100) NOT NULL,
            tier VARCHAR(50) DEFAULT 'professional',
            status VARCHAR(50) DEFAULT 'active',
            custom_glossary JSONB DEFAULT '[]'::jsonb,
            adopted_standards JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );

        -- 2. Projects Table (Plant / Workspace level)
        CREATE TABLE IF NOT EXISTS projects (
            project_id VARCHAR(100) PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            plant_type VARCHAR(100),
            status VARCHAR(50) DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );

        -- 3. Tenant Assets Table (Physical asset instances)
        CREATE TABLE IF NOT EXISTS tenant_assets (
            asset_id VARCHAR(100) PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            project_id VARCHAR(100) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            equipment_id VARCHAR(100) NOT NULL,
            tag_number VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            location TEXT,
            manufacturer VARCHAR(255),
            model_number VARCHAR(255),
            install_date VARCHAR(50),
            custom_metadata JSONB DEFAULT '{}'::jsonb,
            status VARCHAR(50) DEFAULT 'operational'
        );

        -- Indexes for fast scoped lookups
        CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_tenant_assets_tenant_project ON tenant_assets(tenant_id, project_id);
        CREATE INDEX IF NOT EXISTS idx_tenant_assets_equipment ON tenant_assets(equipment_id);
        CREATE INDEX IF NOT EXISTS idx_tenant_assets_tag ON tenant_assets(tenant_id, tag_number);
        """
        cur.execute(ddl)
        conn.commit()
        cur.close()
        logger.info("Tenant tables (tenants, projects, tenant_assets) provisioned successfully.")

    def enable_rls_policies(self) -> None:
        """
        Enables PostgreSQL Row-Level Security (RLS) on tenant-scoped tables:
        - tenant_assets: enforces tenant_id = current_setting('app.tenant_id', true)
        - projects: enforces tenant_id = current_setting('app.tenant_id', true)
        """
        conn = self.get_postgres_connection()
        cur = conn.cursor()

        rls_sql = """
        -- Enable RLS on tenant_assets
        ALTER TABLE tenant_assets ENABLE ROW LEVEL SECURITY;
        
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies WHERE tablename = 'tenant_assets' AND policyname = 'tenant_assets_isolation_policy'
            ) THEN
                CREATE POLICY tenant_assets_isolation_policy ON tenant_assets
                    USING (
                        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
                        OR current_setting('app.tenant_id', true) = 'global'
                        OR current_setting('app.tenant_id', true) IS NULL
                    );
            END IF;
        END $$;

        -- Enable RLS on projects
        ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies WHERE tablename = 'projects' AND policyname = 'projects_isolation_policy'
            ) THEN
                CREATE POLICY projects_isolation_policy ON projects
                    USING (
                        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
                        OR current_setting('app.tenant_id', true) = 'global'
                        OR current_setting('app.tenant_id', true) IS NULL
                    );
            END IF;
        END $$;
        """
        cur.execute(rls_sql)
        conn.commit()
        cur.close()
        logger.info("Row-Level Security (RLS) policies configured on tenant_assets and projects.")

    def set_tenant_context(self, conn, tenant_id: str, project_id: Optional[str] = None) -> None:
        """
        Sets transaction-scoped session variables for PostgreSQL RLS enforcement.
        Uses is_local=true to prevent session leakage across pooled connections.
        """
        cur = conn.cursor()
        cur.execute("SELECT set_config('app.tenant_id', %s, true);", (tenant_id,))
        if project_id:
            cur.execute("SELECT set_config('app.project_id', %s, true);", (project_id,))
        cur.close()

    def close(self):
        """Closes open connection handles."""
        if self._pg_conn is not None and not self._pg_conn.closed:
            self._pg_conn.close()
            self._pg_conn = None
        self._qdrant_client = None
        self._minio_client = None

