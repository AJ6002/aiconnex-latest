"""
aiconnex_agent/platform_kb/standards_service.py

Unified Standards & Regulatory Service Facade for Sprint 5.
Provides authoritative standards and regulatory queries:
- `get_standard`: Retrieve canonical StandardRecord details, scope, and key concepts.
- `get_applicable_standards`: Query candidate standards governing equipment, processes, or systems.
- `get_standards_by_body`: Filter standards by issuing organization (ISO, IEC, NIST, EPA, API, etc.).
- `get_standards_by_domain`: Query standards relevant to a specific domain or lifecycle phase.
- `get_governing_standards`: Identify standards defining or governing specific concepts (e.g. failure_mode, RUL).
- `sync_to_postgres`: Provisions & populates PostgreSQL `knowledge_standards` table.
"""

import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional

from agentic.platform_kb.schemas import StandardRecord
from agentic.platform_kb.db_client import KBInfraClient

logger = logging.getLogger(__name__)

STANDARDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "07_standards_regulatory",
)

# Canonical mapping of equipment IDs / classes to applicable standards
EQUIPMENT_TO_STANDARDS = {
    "EQP-PUMP-CENTRIFUGAL": [
        "STD-ISO-2858", "STD-ISO-5199", "STD-API-610", "STD-DOE-PUMP-SRC",
        "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-ISO-13379-1", "STD-ISO-13381-1"
    ],
    "EQP-COMP-CENTRIFUGAL": [
        "STD-ISO-5390", "STD-API-617", "STD-ISO-14224", "STD-ISO-55000",
        "STD-IEC-60812", "STD-ISO-13379-1", "STD-ISO-13381-1"
    ],
    "EQP-COMP-SCREW": [
        "STD-ISO-5390", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812",
        "STD-ISO-13379-1", "STD-ISO-13381-1"
    ],
    "EQP-MOTOR-INDUCTION": [
        "STD-IEC-60034-1", "STD-IEC-60034-7", "STD-OPC-UA-POWERTRAIN",
        "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-ISO-13379-1", "STD-ISO-13381-1"
    ],
    "EQP-HEX-SHELLTUBE": [
        "STD-ISO-16812", "STD-TEMA-10TH", "STD-ISO-14224", "STD-ISO-55000",
        "STD-IEC-60812", "STD-ISO-13381-1"
    ],
    "EQP-VALVE-GLOBE": [
        "STD-ISA-75", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-OPC-UA-PART110"
    ],
    "EQP-VALVE-GATE": [
        "STD-ISO-6002", "STD-API-600", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-OPC-UA-PART110"
    ],
    "EQP-CONV-BELT": [
        "STD-ISO-5284", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-ISO-13379-1", "STD-OPC-UA-MACHINERY"
    ],
    "EQP-TANK-STORAGE": [
        "STD-API-650", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812", "STD-OPC-UA-PART110"
    ],
    "EQP-WWTP-PACKAGE": [
        "STD-EPA-WW-PACKAGE", "STD-EPA-WW-MANUAL", "STD-ISO-14224", "STD-ISO-55000", "STD-IEC-60812"
    ],
}


class StandardsService:
    """
    Unified Standards & Regulatory Service Facade for AIConnex Agents.
    Serves StandardRecord contracts, equipment-to-standard lookups, and compliance metadata.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        registry_dir: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.registry_dir = registry_dir or STANDARDS_DIR
        self.standards: Dict[str, StandardRecord] = {}

        self.reload_registry()

    def reload_registry(self) -> None:
        """Loads canonical standards from aiconnex_knowledge/07_standards_regulatory/canonical_standards.yaml."""
        filepath = os.path.join(self.registry_dir, "canonical_standards.yaml")
        if not os.path.exists(filepath):
            logger.warning(f"Standards registry file not found at: {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            for item in data.get("canonical_standards", []):
                rec = StandardRecord(**item)
                self.standards[rec.standard_id] = rec

        logger.info(f"Loaded Standards Service Registry with {len(self.standards)} canonical standards.")

    def get_standard(self, standard_id: str) -> Optional[StandardRecord]:
        """Retrieves a single StandardRecord by standard_id, designation, or title."""
        std = self.standards.get(standard_id.upper()) or self.standards.get(standard_id)
        if not std:
            q_lower = standard_id.lower().replace(" ", "-").replace(":", "-")
            for item in self.standards.values():
                if (
                    item.standard_id.lower() == q_lower
                    or item.designation.lower() == standard_id.lower()
                    or item.title.lower() == standard_id.lower()
                    or standard_id.lower() in item.designation.lower()
                ):
                    return item
        return std

    def get_applicable_standards(self, equipment_id: str) -> List[StandardRecord]:
        """
        Retrieves all standards governing a given equipment ID or class.
        """
        std_ids = EQUIPMENT_TO_STANDARDS.get(equipment_id.upper(), [])
        if not std_ids:
            # Fallback search by applicability keyword
            q = equipment_id.lower()
            return [
                s for s in self.standards.values()
                if any(q in app.lower() for app in s.applicability)
            ]

        results = []
        for s_id in std_ids:
            rec = self.get_standard(s_id)
            if rec:
                results.append(rec)
        return results

    def get_standards_by_body(self, issuing_body: str) -> List[StandardRecord]:
        """Filters standards by issuing organization (e.g. 'ISO', 'IEC', 'NIST', 'EPA', 'API')."""
        body_upper = issuing_body.upper()
        return [
            s for s in self.standards.values()
            if body_upper in s.issuing_body.upper()
        ]

    def get_standards_by_domain(self, domain: str) -> List[StandardRecord]:
        """Filters standards matching an applicability domain tag."""
        d_lower = domain.lower()
        return [
            s for s in self.standards.values()
            if any(d_lower in app.lower() for app in s.applicability)
        ]

    def get_governing_standards(self, concept: str) -> List[StandardRecord]:
        """Finds standards defining or governing a specific concept (e.g. 'failure_mode', 'RUL', 'FMEA')."""
        c_lower = concept.lower()
        results = []
        for s in self.standards.values():
            in_concepts = any(c_lower in kc.lower() for kc in s.key_concepts)
            in_scope = c_lower in s.scope.lower()
            in_app = any(c_lower in app.lower() for app in s.applicability)
            if in_concepts or in_scope or in_app:
                results.append(s)
        return results

    def sync_to_postgres(self) -> int:
        """Provisions PostgreSQL table `knowledge_standards` and populates records."""
        conn = self.db_client.get_postgres_connection()
        cur = conn.cursor()

        ddl = """
        CREATE TABLE IF NOT EXISTS knowledge_standards (
            standard_id VARCHAR(64) PRIMARY KEY,
            designation VARCHAR(128) NOT NULL,
            title VARCHAR(512) NOT NULL,
            issuing_body VARCHAR(64) NOT NULL,
            standard_type VARCHAR(64) NOT NULL,
            version VARCHAR(32) NOT NULL,
            publication_date VARCHAR(32),
            scope TEXT NOT NULL,
            applicability TEXT[],
            jurisdiction VARCHAR(64) NOT NULL,
            key_concepts TEXT[],
            supersedes VARCHAR(64),
            superseded_by VARCHAR(64),
            document_available BOOLEAN DEFAULT TRUE,
            authority VARCHAR(32) DEFAULT 'A',
            status VARCHAR(32) DEFAULT 'Approved',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_std_body ON knowledge_standards(LOWER(issuing_body));
        CREATE INDEX IF NOT EXISTS idx_std_type ON knowledge_standards(LOWER(standard_type));
        """
        cur.execute(ddl)
        conn.commit()

        upsert_sql = """
        INSERT INTO knowledge_standards (
            standard_id, designation, title, issuing_body, standard_type,
            version, publication_date, scope, applicability, jurisdiction,
            key_concepts, supersedes, superseded_by, document_available,
            authority, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (standard_id) DO UPDATE SET
            designation = EXCLUDED.designation,
            title = EXCLUDED.title,
            issuing_body = EXCLUDED.issuing_body,
            standard_type = EXCLUDED.standard_type,
            version = EXCLUDED.version,
            publication_date = EXCLUDED.publication_date,
            scope = EXCLUDED.scope,
            applicability = EXCLUDED.applicability,
            jurisdiction = EXCLUDED.jurisdiction,
            key_concepts = EXCLUDED.key_concepts,
            supersedes = EXCLUDED.supersedes,
            superseded_by = EXCLUDED.superseded_by,
            document_available = EXCLUDED.document_available,
            authority = EXCLUDED.authority,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP;
        """

        count = 0
        for std in self.standards.values():
            cur.execute(
                upsert_sql,
                (
                    std.standard_id,
                    std.designation,
                    std.title,
                    std.issuing_body,
                    std.standard_type,
                    std.version,
                    std.publication_date,
                    std.scope,
                    std.applicability,
                    std.jurisdiction,
                    std.key_concepts,
                    std.supersedes,
                    std.superseded_by,
                    std.document_available,
                    std.authority,
                    std.status,
                ),
            )
            count += 1

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Successfully synced {count} standards records to PostgreSQL table 'knowledge_standards'.")
        return count
