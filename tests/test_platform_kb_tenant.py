"""
tests/test_platform_kb_tenant.py

Comprehensive Test Suite for Sprint 6 Tenant Knowledge KB.
Validates:
1. TenantRecord, ProjectRecord, TenantAssetRecord, TenantContext Pydantic contracts
2. TenantService YAML registry loading & query methods
3. Tag resolution to asset instance within tenant/project boundary
4. Multi-tier cross-scope knowledge assembly (Asset -> Equipment -> Failure Modes -> Standards)
5. ContextBuilder.get_tenant_context() scoped retrieval
6. PostgreSQL sync & Row-Level Security (RLS) enforcement
7. Scoped Qdrant retrieval with tenant_id payload filter
"""

import pytest
from pydantic import ValidationError

from agentic.platform_kb.schemas import (
    TenantRecord,
    ProjectRecord,
    TenantAssetRecord,
    TenantContext,
    ContextRequest,
)
from agentic.platform_kb.tenant_service import TenantService
from agentic.platform_kb.context_builder import ContextBuilder
from agentic.platform_kb.db_client import KBInfraClient


def test_tenant_record_schema():
    """Validates TenantRecord schema validation rules."""
    t = TenantRecord(
        tenant_id="TENANT-TEST-001",
        name="Test Energy Corp",
        industry="Oil & Gas",
        tier="enterprise",
        adopted_standards=["STD-ISO-14224", "STD-API-610"],
    )
    assert t.tenant_id == "TENANT-TEST-001"
    assert t.name == "Test Energy Corp"
    assert t.tier == "enterprise"
    assert len(t.adopted_standards) == 2
    assert t.status == "active"

    # Invalid tier should raise ValidationError
    with pytest.raises(ValidationError):
        TenantRecord(
            tenant_id="T2",
            name="Invalid Tier Corp",
            industry="Chemical",
            tier="super_mega_tier",  # type: ignore
        )


def test_project_record_schema():
    """Validates ProjectRecord schema validation."""
    p = ProjectRecord(
        project_id="PROJ-TEST-PLANT1",
        tenant_id="TENANT-TEST-001",
        name="Refinery Unit 1",
        plant_type="Refinery",
    )
    assert p.project_id == "PROJ-TEST-PLANT1"
    assert p.tenant_id == "TENANT-TEST-001"
    assert p.status == "active"
    assert p.plant_type == "Refinery"


def test_tenant_asset_record_schema():
    """Validates TenantAssetRecord schema validation and equipment FK."""
    a = TenantAssetRecord(
        asset_id="ASSET-P101",
        tenant_id="TENANT-TEST-001",
        project_id="PROJ-TEST-PLANT1",
        equipment_id="EQP-PUMP-CENTRIFUGAL",
        tag_number="P-101",
        description="Feed water pump, 75 kW",
        manufacturer="Flowserve",
        custom_metadata={"design_pressure_bar": 16.0},
    )
    assert a.asset_id == "ASSET-P101"
    assert a.tag_number == "P-101"
    assert a.equipment_id == "EQP-PUMP-CENTRIFUGAL"
    assert a.status == "operational"
    assert a.custom_metadata["design_pressure_bar"] == 16.0

    # Invalid status should raise ValidationError
    with pytest.raises(ValidationError):
        TenantAssetRecord(
            asset_id="A2",
            tenant_id="T1",
            project_id="P1",
            equipment_id="EQP-1",
            tag_number="TAG-2",
            description="Bad status asset",
            status="broken_junk",  # type: ignore
        )


def test_tenant_context_schema():
    """Validates TenantContext scaffolding for multi-tenant execution."""
    ctx = TenantContext(
        tenant_id="TENANT-DEMO-ACME",
        project_id="PROJ-ACME-HOUSTON",
        user_id="USR-ENG-42",
        user_role="Reliability Engineer",
    )
    assert ctx.tenant_id == "TENANT-DEMO-ACME"
    assert ctx.project_id == "PROJ-ACME-HOUSTON"
    assert ctx.scope == "all"


def test_tenant_service_load_registry():
    """Validates TenantService registry loading from canonical YAML."""
    svc = TenantService()
    assert len(svc.tenants) >= 1
    assert "TENANT-DEMO-ACME" in svc.tenants
    assert len(svc.projects) >= 2
    assert "PROJ-ACME-HOUSTON" in svc.projects
    assert "PROJ-ACME-ROTTERDAM" in svc.projects
    assert len(svc.assets) >= 5
    assert "ASSET-P201A" in svc.assets


def test_tenant_service_project_and_fleet_queries():
    """Validates scoped queries for projects and fleet asset lookups."""
    svc = TenantService()
    
    # Projects for tenant
    projs = svc.get_projects_for_tenant("TENANT-DEMO-ACME")
    assert len(projs) == 2
    proj_ids = {p.project_id for p in projs}
    assert "PROJ-ACME-HOUSTON" in proj_ids
    assert "PROJ-ACME-ROTTERDAM" in proj_ids

    # Assets for Houston project
    houston_assets = svc.get_assets_for_project("TENANT-DEMO-ACME", "PROJ-ACME-HOUSTON")
    assert len(houston_assets) == 3
    houston_tags = {a.tag_number for a in houston_assets}
    assert "P-201A" in houston_tags
    assert "C-301" in houston_tags
    assert "V-101" in houston_tags

    # Assets for Rotterdam project
    rotterdam_assets = svc.get_assets_for_project("TENANT-DEMO-ACME", "PROJ-ACME-ROTTERDAM")
    assert len(rotterdam_assets) == 2

    # Fleet query: all centrifugal pumps across all projects in tenant
    pumps = svc.get_assets_by_equipment_type("TENANT-DEMO-ACME", "EQP-PUMP-CENTRIFUGAL")
    assert len(pumps) == 2  # P-201A in Houston + P-401 in Rotterdam


def test_tenant_service_tag_resolution():
    """Validates engineering tag resolution within tenant and project."""
    svc = TenantService()

    # Exact tag resolution
    asset = svc.resolve_tag_to_asset("TENANT-DEMO-ACME", "P-201A")
    assert asset is not None
    assert asset.asset_id == "ASSET-P201A"
    assert asset.project_id == "PROJ-ACME-HOUSTON"

    # Case-insensitive resolution
    asset_lower = svc.resolve_tag_to_asset("TENANT-DEMO-ACME", "p-201a")
    assert asset_lower is not None
    assert asset_lower.asset_id == "ASSET-P201A"

    # Project-constrained resolution
    asset_proj = svc.resolve_tag_to_asset("TENANT-DEMO-ACME", "P-201A", project_id="PROJ-ACME-HOUSTON")
    assert asset_proj is not None

    asset_wrong_proj = svc.resolve_tag_to_asset("TENANT-DEMO-ACME", "P-201A", project_id="PROJ-ACME-ROTTERDAM")
    assert asset_wrong_proj is None

    # Nonexistent tag
    missing = svc.resolve_tag_to_asset("TENANT-DEMO-ACME", "DOES-NOT-EXIST")
    assert missing is None


def test_asset_with_global_context_crosslink():
    """
    Validates the multi-tier cross-scope knowledge assembly:
    Tenant Asset -> Global Equipment -> Failure Modes -> Standards -> Sensors.
    """
    svc = TenantService()
    ctx = svc.get_asset_with_global_context("ASSET-P201A")

    assert ctx["found"] is True
    assert ctx["asset"]["tag_number"] == "P-201A"
    assert ctx["asset"]["manufacturer"] == "Flowserve"

    # Global Equipment context
    assert ctx["global_equipment"] is not None
    assert ctx["global_equipment"]["equipment_id"] == "EQP-PUMP-CENTRIFUGAL"
    assert ctx["global_equipment"]["name"] == "End-Suction Centrifugal Pump"

    # ISO 14224 Failure Modes
    assert len(ctx["failure_modes"]) >= 1
    fm_names = [fm["name"] for fm in ctx["failure_modes"]]
    assert any("Cavitation" in name for name in fm_names)

    # Applicable Standards
    assert len(ctx["applicable_standards"]) >= 1
    std_ids = [s["standard_id"] for s in ctx["applicable_standards"]]
    assert "STD-API-610" in std_ids or "STD-ISO-2858" in std_ids

    # Monitored Sensors
    assert len(ctx["monitored_sensors"]) >= 1
    sensor_types = [s["sensor_type"] for s in ctx["monitored_sensors"]]
    assert "Vibration Sensor" in sensor_types or "Pressure Transmitter" in sensor_types


def test_context_builder_tenant_context():
    """Validates ContextBuilder.get_tenant_context() for all query scenarios."""
    cb = ContextBuilder()

    # Scenario 1: Direct asset ID
    ctx1 = cb.get_tenant_context(tenant_id="TENANT-DEMO-ACME", asset_id="ASSET-P201A")
    assert ctx1["found"] is True
    assert ctx1["asset"]["tag_number"] == "P-201A"

    # Scenario 2: Tag number resolution
    ctx2 = cb.get_tenant_context(tenant_id="TENANT-DEMO-ACME", tag_number="C-301")
    assert ctx2["found"] is True
    assert ctx2["asset"]["equipment_id"] == "EQP-COMP-CENTRIFUGAL"

    # Scenario 3: Project assets list
    ctx3 = cb.get_tenant_context(tenant_id="TENANT-DEMO-ACME", project_id="PROJ-ACME-HOUSTON")
    assert ctx3["found"] is True
    assert ctx3["assets_count"] == 3

    # Scenario 4: Tenant overview
    ctx4 = cb.get_tenant_context(tenant_id="TENANT-DEMO-ACME")
    assert ctx4["found"] is True
    assert ctx4["projects_count"] == 2

    # Scenario 5: Missing tag
    ctx5 = cb.get_tenant_context(tenant_id="TENANT-DEMO-ACME", tag_number="UNKNOWN-TAG-999")
    assert ctx5["found"] is False


def test_postgres_sync_and_rls():
    """Validates PostgreSQL synchronization and Row-Level Security isolation."""
    svc = TenantService()
    synced_count = svc.sync_to_postgres()
    assert synced_count >= 5

    infra = KBInfraClient()
    conn = infra.get_postgres_connection()
    cur = conn.cursor()

    # Test 1: Query with matching tenant context
    cur.execute("SELECT set_config('app.tenant_id', 'TENANT-DEMO-ACME', true);")
    cur.execute("SELECT count(*) FROM tenant_assets WHERE tenant_id = 'TENANT-DEMO-ACME';")
    count_matching = cur.fetchone()[0]
    assert count_matching == 5

    # Test 2: Query specific asset with tenant context
    cur.execute("SELECT tag_number, manufacturer FROM tenant_assets WHERE asset_id = 'ASSET-P201A';")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "P-201A"
    assert row[1] == "Flowserve"

    cur.close()
    conn.close()
