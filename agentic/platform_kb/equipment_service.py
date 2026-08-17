"""
aiconnex_agent/platform_kb/equipment_service.py

Unified Equipment Service Facade for Sprint 4 Equipment & Asset KB.
Provides deterministic technical queries:
- `get_equipment`: Retrieve canonical EquipmentRecord details & subsystem trees.
- `get_applicable_equipment`: Query candidate equipment matching classification or category.
- `get_failure_modes`: Retrieve ISO 14224 failure modes and maintenance actions for equipment.
- `get_monitored_sensors`: Retrieve sensors and parameters monitoring equipment.
- `sync_to_postgres`: Provisions & populates PostgreSQL `knowledge_equipment` table.
"""

import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional

from agentic.platform_kb.schemas import EquipmentRecord
from agentic.platform_kb.db_client import KBInfraClient

logger = logging.getLogger(__name__)

EQUIPMENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "06_equipment_asset",
)


class EquipmentService:
    """
    Unified Equipment Service Facade for AIConnex Agents.
    Serves EquipmentRecord contracts and deterministic equipment topology lookups.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        registry_dir: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.registry_dir = registry_dir or EQUIPMENT_DIR
        self.equipments: Dict[str, EquipmentRecord] = {}

        self.reload_registry()

    def reload_registry(self) -> None:
        """Loads canonical equipment from aiconnex_knowledge/06_equipment_asset/canonical_equipment.yaml."""
        filepath = os.path.join(self.registry_dir, "canonical_equipment.yaml")
        if not os.path.exists(filepath):
            logger.warning(f"Equipment registry file not found at: {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            for item in data.get("canonical_equipment", []):
                rec = EquipmentRecord(**item)
                self.equipments[rec.equipment_id] = rec

        logger.info(f"Loaded Equipment Service Registry with {len(self.equipments)} canonical equipment records.")

    def get_equipment(self, equipment_id: str) -> Optional[EquipmentRecord]:
        """Retrieves a single EquipmentRecord by ID or equipment class."""
        eq = self.equipments.get(equipment_id.upper()) or self.equipments.get(equipment_id)
        if not eq:
            for item in self.equipments.values():
                if item.equipment_class.lower() == equipment_id.lower() or item.name.lower() == equipment_id.lower():
                    return item
        return eq

    def get_applicable_equipment(
        self,
        equipment_class: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[EquipmentRecord]:
        """Queries equipment matching equipment_class or general category."""
        results = list(self.equipments.values())

        if equipment_class:
            results = [e for e in results if e.equipment_class.lower() == equipment_class.lower()]

        if category:
            results = [e for e in results if category.lower() in e.category.lower()]

        return results

    def get_failure_modes(self, equipment_id: str) -> List[Dict[str, Any]]:
        """Returns ISO 14224 failure modes for a specified equipment."""
        eq = self.get_equipment(equipment_id)
        return eq.failure_modes if eq else []

    def get_monitored_sensors(self, equipment_id: str) -> List[Dict[str, str]]:
        """Returns sensors monitoring a specified equipment."""
        eq = self.get_equipment(equipment_id)
        return eq.monitored_sensors if eq else []

    def sync_to_postgres(self) -> int:
        """Provisions PostgreSQL table `knowledge_equipment` and populates records."""
        conn = self.db_client.get_postgres_connection()
        cur = conn.cursor()

        ddl = """
        CREATE TABLE IF NOT EXISTS knowledge_equipment (
            equipment_id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            equipment_class VARCHAR(64) NOT NULL,
            category VARCHAR(128) NOT NULL,
            standard_ref VARCHAR(255) NOT NULL,
            direct_components TEXT[],
            operating_modes TEXT[],
            authority VARCHAR(32) DEFAULT 'A',
            status VARCHAR(32) DEFAULT 'Approved',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_eqp_class ON knowledge_equipment(LOWER(equipment_class));
        """
        cur.execute(ddl)
        conn.commit()

        upsert_sql = """
        INSERT INTO knowledge_equipment (
            equipment_id, name, equipment_class, category, standard_ref,
            direct_components, operating_modes, authority, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (equipment_id) DO UPDATE SET
            name = EXCLUDED.name,
            equipment_class = EXCLUDED.equipment_class,
            category = EXCLUDED.category,
            standard_ref = EXCLUDED.standard_ref,
            direct_components = EXCLUDED.direct_components,
            operating_modes = EXCLUDED.operating_modes,
            updated_at = CURRENT_TIMESTAMP;
        """

        count = 0
        for eq in self.equipments.values():
            cur.execute(
                upsert_sql,
                (
                    eq.equipment_id,
                    eq.name,
                    eq.equipment_class,
                    eq.category,
                    eq.standard_ref,
                    eq.direct_components,
                    eq.operating_modes,
                    eq.authority,
                    eq.status,
                ),
            )
            count += 1

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Successfully synced {count} equipment records to PostgreSQL table 'knowledge_equipment'.")
        return count
