"""
tests/test_platform_kb_db_client.py

Unit and Integration test suite for Platform KB infrastructure client and health checks.
Validates:
- KBConfig environment variable loading
- Live health-check handshakes against PostgreSQL, Qdrant, and MinIO Docker containers
- Strict production mode CriticalDependencyError enforcement on unreachable backends
- Non-strict mode fallback behavior
"""

import pytest
from agentic.platform_kb.config import KBConfig, PostgresConfig, QdrantConfig, MinIOConfig
from agentic.platform_kb.db_client import KBInfraClient, CriticalDependencyError


def test_kb_config_defaults():
    config = KBConfig()
    assert config.strict_production_mode is True
    assert config.postgres.db_name == "aiconnex_kb_prod"
    assert config.qdrant.collection == "platform_kb_embeddings"
    assert config.minio.bucket == "aiconnex-platform-kb-prod"


def test_kb_infra_client_live_health_checks():
    """Integration test against live Docker containers."""
    client = KBInfraClient()
    try:
        results = client.perform_health_checks(raise_on_failure=True)
        assert results["postgres"] is True
        assert results["qdrant"] is True
        assert results["minio"] is True
    finally:
        client.close()


def test_kb_infra_client_strict_mode_raises_on_unreachable():
    """Verifies CriticalDependencyError is raised when strict mode is active and DB is unreachable."""
    bad_config = KBConfig(
        strict_production_mode=True,
        postgres=PostgresConfig(port=9999),  # Unreachable port
    )
    client = KBInfraClient(config=bad_config)
    try:
        with pytest.raises(CriticalDependencyError, match="PostgreSQL connection failed"):
            client.perform_health_checks(raise_on_failure=True)
    finally:
        client.close()


def test_kb_infra_client_non_strict_mode_returns_false():
    """Verifies health check returns False when strict mode is disabled."""
    bad_config = KBConfig(
        strict_production_mode=False,
        postgres=PostgresConfig(port=9999),
    )
    client = KBInfraClient(config=bad_config)
    try:
        results = client.perform_health_checks(raise_on_failure=False)
        assert results["postgres"] is False
    finally:
        client.close()
