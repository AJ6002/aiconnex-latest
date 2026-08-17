"""
aiconnex_agent/platform_kb/tenant_service.py

Unified Tenant Knowledge Service Facade for Sprint 6 Tenant Knowledge KB.
Implements Cognite Spaces Model & 3-Tier Multi-Tenant Knowledge Partitioning:
- Organization (Tenant) & Project (Plant/Site) workspace management
- Asset instance management linked to global reference taxonomies (:INSTANCE_OF)
- Scoped query methods with project and tag resolution
- `get_asset_with_global_context`: Full multi-tier cross-scope retrieval
- PostgreSQL multi-tenant sync with Row-Level Security (RLS) policies
"""

import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional

from agentic.platform_kb.schemas import (
    TenantRecord,
    ProjectRecord,
    TenantAssetRecord,
    TenantContext,
)
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.equipment_service import EquipmentService
from agentic.platform_kb.standards_service import StandardsService

logger = logging.getLogger(__name__)

TENANT_REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "08_tenant_knowledge",
    "tenant_registry.yaml",
)


class TenantService:
    """
    Unified Tenant Service Facade for AIConnex Multi-Tenant Architecture.
    Serves TenantRecord, ProjectRecord, and TenantAssetRecord contracts,
    and bridges project assets to global equipment taxonomies and standards.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        equipment_service: Optional[EquipmentService] = None,
        standards_service: Optional[StandardsService] = None,
        registry_file: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.equipment_service = equipment_service or EquipmentService(db_client=self.db_client)
        self.standards_service = standards_service or StandardsService(db_client=self.db_client)
        self.registry_file = registry_file or TENANT_REGISTRY_FILE

        self.tenants: Dict[str, TenantRecord] = {}
        self.projects: Dict[str, ProjectRecord] = {}
        self.assets: Dict[str, TenantAssetRecord] = {}

        self.reload_registry()

    def reload_registry(self) -> None:
        """Loads tenant organizations, projects, and assets from tenant_registry.yaml."""
        if not os.path.exists(self.registry_file):
            logger.warning(f"Tenant registry file not found at: {self.registry_file}")
            return

        with open(self.registry_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.tenants = {}
        self.projects = {}
        self.assets = {}

        for item in data.get("tenants", []):
            rec = TenantRecord(**item)
            self.tenants[rec.tenant_id] = rec

        for item in data.get("projects", []):
            rec = ProjectRecord(**item)
            self.projects[rec.project_id] = rec

        for item in data.get("assets", []):
            rec = TenantAssetRecord(**item)
            self.assets[rec.asset_id] = rec

        logger.info(
            f"Loaded Tenant Service Registry with {len(self.tenants)} tenants, "
            f"{len(self.projects)} projects, {len(self.assets)} assets."
        )

    # ── Tenant Operations ─────────────────────────────────────────────────────

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        """Retrieves a single TenantRecord by ID."""
        return self.tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantRecord]:
        """Lists all registered tenant organizations."""
        return list(self.tenants.values())

    # ── Project Operations ────────────────────────────────────────────────────

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        """Retrieves a single ProjectRecord by ID."""
        return self.projects.get(project_id)

    def get_projects_for_tenant(self, tenant_id: str) -> List[ProjectRecord]:
        """Lists all active projects owned by a specific tenant."""
        return [p for p in self.projects.values() if p.tenant_id == tenant_id]

    # ── Asset Operations ──────────────────────────────────────────────────────

    def get_asset(self, asset_id: str) -> Optional[TenantAssetRecord]:
        """Retrieves a single physical TenantAssetRecord by ID."""
        return self.assets.get(asset_id)

    def get_assets_for_project(self, tenant_id: str, project_id: str) -> List[TenantAssetRecord]:
        """Retrieves all asset instances located in a specific tenant project."""
        return [
            a for a in self.assets.values()
            if a.tenant_id == tenant_id and a.project_id == project_id
        ]

    def get_assets_by_equipment_type(self, tenant_id: str, equipment_id: str) -> List[TenantAssetRecord]:
        """Retrieves all assets of a specific canonical equipment type across a tenant's fleet."""
        return [
            a for a in self.assets.values()
            if a.tenant_id == tenant_id and a.equipment_id == equipment_id
        ]

    def resolve_tag_to_asset(
        self,
        tenant_id: str,
        tag_number: str,
        project_id: Optional[str] = None,
    ) -> Optional[TenantAssetRecord]:
        """
        Resolves a plant engineering tag (e.g. 'P-201A') to a TenantAssetRecord within a tenant.
        Optionally narrows to a specific project.
        """
        tag_clean = tag_number.strip().upper()
        for a in self.assets.values():
            if a.tenant_id == tenant_id and a.tag_number.upper() == tag_clean:
                if project_id is None or a.project_id == project_id:
                    return a
        return None

    # ── Cross-Scope Multi-Tier Knowledge Assembly ─────────────────────────────

    def get_asset_with_global_context(self, asset_id: str) -> Dict[str, Any]:
        """
        Assembles multi-tier knowledge for a tenant asset:
        1. Tenant Asset Instance (physical tag, serial, custom operating parameters)
        2. Global Equipment Reference (canonical class, ISO standard ref)
        3. ISO 14224 Failure Modes & Mechanisms
        4. Monitored Sensor Parameters & Engineering Units
        5. Governing Regulatory Standards

        Demonstrates the power of Cognite Spaces cross-scope linkage.
        """
        asset = self.get_asset(asset_id)
        if not asset:
            return {"asset_id": asset_id, "found": False}

        eq = self.equipment_service.get_equipment(asset.equipment_id)
        fms = self.equipment_service.get_failure_modes(asset.equipment_id)
        sensors = self.equipment_service.get_monitored_sensors(asset.equipment_id)
        stds = self.standards_service.get_applicable_standards(asset.equipment_id)

        project = self.get_project(asset.project_id)
        tenant = self.get_tenant(asset.tenant_id)

        return {
            "found": True,
            "asset": asset.model_dump(),
            "project": project.model_dump() if project else None,
            "tenant": {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "industry": tenant.industry,
            } if tenant else None,
            "global_equipment": eq.model_dump() if eq else None,
            "failure_modes": fms,
            "monitored_sensors": sensors,
            "applicable_standards": [s.model_dump() for s in stds],
        }

    # ── PostgreSQL Multi-Tenant Synchronization ───────────────────────────────

    def sync_to_postgres(self) -> int:
        """
        Provisions tables, enables RLS, and synchronizes all tenants, projects,
        and asset records into PostgreSQL.
        """
        self.db_client.provision_tenant_tables()
        self.db_client.enable_rls_policies()

        conn = self.db_client.get_postgres_connection()
        cur = conn.cursor()

        # Disable RLS temporarily or use admin context for synchronization
        cur.execute("SELECT set_config('app.tenant_id', 'global', true);")

        # 1. Upsert Tenants
        for t in self.tenants.values():
            cur.execute(
                """
                INSERT INTO tenants (tenant_id, name, industry, tier, status, custom_glossary, adopted_standards)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    industry = EXCLUDED.industry,
                    tier = EXCLUDED.tier,
                    status = EXCLUDED.status,
                    custom_glossary = EXCLUDED.custom_glossary,
                    adopted_standards = EXCLUDED.adopted_standards;
                """,
                (
                    t.tenant_id,
                    t.name,
                    t.industry,
                    t.tier,
                    t.status,
                    json.dumps(t.custom_glossary),
                    json.dumps(t.adopted_standards),
                ),
            )

        # 2. Upsert Projects
        for p in self.projects.values():
            cur.execute(
                """
                INSERT INTO projects (project_id, tenant_id, name, plant_type, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    name = EXCLUDED.name,
                    plant_type = EXCLUDED.plant_type,
                    status = EXCLUDED.status;
                """,
                (p.project_id, p.tenant_id, p.name, p.plant_type, p.status),
            )

        # 3. Upsert Assets
        for a in self.assets.values():
            cur.execute(
                """
                INSERT INTO tenant_assets (
                    asset_id, tenant_id, project_id, equipment_id,
                    tag_number, description, location, manufacturer,
                    model_number, install_date, custom_metadata, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (asset_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    project_id = EXCLUDED.project_id,
                    equipment_id = EXCLUDED.equipment_id,
                    tag_number = EXCLUDED.tag_number,
                    description = EXCLUDED.description,
                    location = EXCLUDED.location,
                    manufacturer = EXCLUDED.manufacturer,
                    model_number = EXCLUDED.model_number,
                    install_date = EXCLUDED.install_date,
                    custom_metadata = EXCLUDED.custom_metadata,
                    status = EXCLUDED.status;
                """,
                (
                    a.asset_id,
                    a.tenant_id,
                    a.project_id,
                    a.equipment_id,
                    a.tag_number,
                    a.description,
                    a.location,
                    a.manufacturer,
                    a.model_number,
                    a.install_date,
                    json.dumps(a.custom_metadata),
                    a.status,
                ),
            )

        conn.commit()
        cur.close()
        logger.info(
            f"Successfully synced {len(self.tenants)} tenants, {len(self.projects)} projects, "
            f"{len(self.assets)} assets to PostgreSQL."
        )
        return len(self.assets)
