"""
scripts/industrial_kb_sprint5_graph_ingest.py

Phase 4: Neo4j Graph Ingestion for Sprint 5 Standards & Regulatory Knowledge.
Creates Standard and IssuingBody Nodes (:Standard, :IssuingBody)
and establishes relationships (:PUBLISHES, :APPLIES_TO, :DEFINES, :GOVERNS, :SUPERSEDES, :INSTANCE_OF).
"""

import os
import sys
import yaml
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from neo4j import GraphDatabase
from agentic.platform_kb.config import get_kb_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("StandardsGraphIngest")

REGISTRY_FILE = os.path.join(BASE_DIR, "aiconnex_knowledge", "07_standards_regulatory", "canonical_standards.yaml")

EQUIPMENT_APPLICABILITY_MAP = {
    "STD-ISO-14224": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE", "EQP-VALVE-GLOBE",
        "EQP-VALVE-GATE", "EQP-CONV-BELT", "EQP-TANK-STORAGE", "EQP-WWTP-PACKAGE"
    ],
    "STD-ISO-55000": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE", "EQP-VALVE-GLOBE",
        "EQP-VALVE-GATE", "EQP-CONV-BELT", "EQP-TANK-STORAGE", "EQP-WWTP-PACKAGE"
    ],
    "STD-ISO-55001": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE", "EQP-VALVE-GLOBE",
        "EQP-VALVE-GATE", "EQP-CONV-BELT", "EQP-TANK-STORAGE", "EQP-WWTP-PACKAGE"
    ],
    "STD-IEC-60812": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE", "EQP-VALVE-GLOBE",
        "EQP-VALVE-GATE", "EQP-CONV-BELT", "EQP-TANK-STORAGE", "EQP-WWTP-PACKAGE"
    ],
    "STD-ISO-13379-1": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-CONV-BELT"
    ],
    "STD-ISO-13381-1": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE"
    ],
    "STD-ISO-17359": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-CONV-BELT"
    ],
    "STD-ISO-2858": ["EQP-PUMP-CENTRIFUGAL"],
    "STD-ISO-5199": ["EQP-PUMP-CENTRIFUGAL"],
    "STD-API-610": ["EQP-PUMP-CENTRIFUGAL"],
    "STD-DOE-PUMP-SRC": ["EQP-PUMP-CENTRIFUGAL"],
    "STD-ISO-5390": ["EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW"],
    "STD-API-617": ["EQP-COMP-CENTRIFUGAL"],
    "STD-IEC-60034-1": ["EQP-MOTOR-INDUCTION"],
    "STD-IEC-60034-7": ["EQP-MOTOR-INDUCTION"],
    "STD-OPC-UA-POWERTRAIN": ["EQP-MOTOR-INDUCTION"],
    "STD-ISO-16812": ["EQP-HEX-SHELLTUBE"],
    "STD-TEMA-10TH": ["EQP-HEX-SHELLTUBE"],
    "STD-ISA-75": ["EQP-VALVE-GLOBE"],
    "STD-ISO-6002": ["EQP-VALVE-GATE"],
    "STD-API-600": ["EQP-VALVE-GATE"],
    "STD-ISO-5284": ["EQP-CONV-BELT"],
    "STD-API-650": ["EQP-TANK-STORAGE"],
    "STD-EPA-WW-PACKAGE": ["EQP-WWTP-PACKAGE"],
    "STD-EPA-WW-MANUAL": ["EQP-WWTP-PACKAGE"],
    "STD-OPC-UA-PART110": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-HEX-SHELLTUBE", "EQP-VALVE-GLOBE",
        "EQP-VALVE-GATE", "EQP-CONV-BELT", "EQP-TANK-STORAGE", "EQP-WWTP-PACKAGE"
    ],
    "STD-OPC-UA-MACHINERY": [
        "EQP-PUMP-CENTRIFUGAL", "EQP-COMP-CENTRIFUGAL", "EQP-COMP-SCREW",
        "EQP-MOTOR-INDUCTION", "EQP-CONV-BELT"
    ],
}

ML_GOVERNANCE_MAP = {
    "STD-CRISP-MLQ": [
        "ML-PROG-WEIBULL", "ML-PROG-LSTM-RUL", "ML-ANOM-IFOREST",
        "ML-FCST-SARIMAX", "ML-CLASS-XGBOOST", "ML-SURV-COX",
        "ML-REG-LGBM", "ML-REG-ELASTICNET"
    ],
    "STD-CRISP-DM": [
        "ML-PROG-WEIBULL", "ML-PROG-LSTM-RUL", "ML-ANOM-IFOREST",
        "ML-FCST-SARIMAX", "ML-CLASS-XGBOOST", "ML-SURV-COX",
        "ML-REG-LGBM", "ML-REG-ELASTICNET"
    ],
    "STD-IEEE-TKDE-DS": ["ML-SURV-COX", "ML-FCST-SARIMAX"],
    "STD-NISTIR-8012": ["ML-PROG-WEIBULL", "ML-PROG-LSTM-RUL"],
    "STD-NIST-AI-100-1": [
        "ML-PROG-WEIBULL", "ML-PROG-LSTM-RUL", "ML-ANOM-IFOREST",
        "ML-FCST-SARIMAX", "ML-CLASS-XGBOOST", "ML-SURV-COX",
        "ML-REG-LGBM", "ML-REG-ELASTICNET"
    ],
}


def ingest_standards_graph():
    logger.info("=== Starting Neo4j Graph Ingestion for Standards & Regulatory Knowledge ===")

    if not os.path.exists(REGISTRY_FILE):
        logger.error(f"Registry file not found: {REGISTRY_FILE}")
        return

    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    standards = data.get("canonical_standards", [])

    cfg = get_kb_config().neo4j
    driver = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))
    session = driver.session()

    try:
        # 1. Create constraints & indexes
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Standard) REQUIRE s.standard_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (ib:IssuingBody) REQUIRE ib.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (ce:CanonicalEntity) REQUIRE ce.name IS UNIQUE")

        # Ensure CanonicalEntity 'Standard' exists
        session.run("MERGE (ce:CanonicalEntity {name: 'Standard'}) SET ce.domain = 'standards_regulatory'")

        # Pass 1: MERGE all Standard and IssuingBody nodes
        for std in standards:
            session.run(
                """
                MERGE (s:Standard {standard_id: $standard_id})
                SET s.designation = $designation,
                    s.title = $title,
                    s.issuing_body = $issuing_body,
                    s.standard_type = $standard_type,
                    s.version = $version,
                    s.scope = $scope,
                    s.jurisdiction = $jurisdiction,
                    s.document_available = $document_available,
                    s.authority = $authority,
                    s.status = $status,
                    s.updated_at = datetime()
                """,
                standard_id=std["standard_id"],
                designation=std["designation"],
                title=std["title"],
                issuing_body=std["issuing_body"],
                standard_type=std["standard_type"],
                version=std["version"],
                scope=std["scope"],
                jurisdiction=std["jurisdiction"],
                document_available=std.get("document_available", True),
                authority=std.get("authority", "A"),
                status=std.get("status", "Approved"),
            )
            session.run(
                """
                MERGE (ib:IssuingBody {name: $issuing_body})
                """,
                issuing_body=std["issuing_body"],
            )

        # Pass 2: Establish relationships
        for std in standards:
            std_id = std["standard_id"]
            body = std["issuing_body"]

            # IssuingBody -> PUBLISHES -> Standard
            session.run(
                """
                MATCH (ib:IssuingBody {name: $issuing_body})
                MATCH (s:Standard {standard_id: $standard_id})
                MERGE (ib)-[:PUBLISHES]->(s)
                """,
                issuing_body=body,
                standard_id=std_id,
            )

            # Standard -> INSTANCE_OF -> CanonicalEntity 'Standard'
            session.run(
                """
                MATCH (s:Standard {standard_id: $standard_id})
                MATCH (ce:CanonicalEntity {name: 'Standard'})
                MERGE (s)-[:INSTANCE_OF]->(ce)
                """,
                standard_id=std_id,
            )

            # Version Lineage: SUPERSEDES
            supersedes = std.get("supersedes")
            if supersedes:
                session.run(
                    """
                    MATCH (s:Standard {standard_id: $standard_id})
                    MATCH (old:Standard {standard_id: $supersedes})
                    MERGE (s)-[:SUPERSEDES]->(old)
                    """,
                    standard_id=std_id,
                    supersedes=supersedes,
                )

            # Equipment Applicability Relationships: (:Standard)-[:APPLIES_TO]->(:Equipment)
            eq_targets = EQUIPMENT_APPLICABILITY_MAP.get(std_id, [])
            for eq_id in eq_targets:
                session.run(
                    """
                    MATCH (s:Standard {standard_id: $standard_id})
                    MATCH (e:Equipment {equipment_id: $equipment_id})
                    MERGE (s)-[:APPLIES_TO]->(e)
                    """,
                    standard_id=std_id,
                    equipment_id=eq_id,
                )

            # ML Methodology Governance Relationships: (:Standard)-[:GOVERNS]->(:MLMethod)
            ml_targets = ML_GOVERNANCE_MAP.get(std_id, [])
            for method_id in ml_targets:
                session.run(
                    """
                    MATCH (s:Standard {standard_id: $standard_id})
                    MATCH (m:MLMethod {method_id: $method_id})
                    MERGE (s)-[:GOVERNS]->(m)
                    """,
                    standard_id=std_id,
                    method_id=method_id,
                )

        # Standard to FailureMode Relationships: (:Standard)-[:DEFINES]->(:FailureMode)
        session.run(
            """
            MATCH (s:Standard {standard_id: 'STD-ISO-14224'})
            MATCH (fm:FailureMode)
            MERGE (s)-[:DEFINES]->(fm)
            """
        )
        session.run(
            """
            MATCH (s:Standard {standard_id: 'STD-IEC-60812'})
            MATCH (fm:FailureMode)
            MERGE (s)-[:DEFINES]->(fm)
            """
        )

        # Asset Governance Relationship: (:Standard {standard_id: 'STD-ISO-55000'})-[:GOVERNS]->(:Asset)
        session.run(
            """
            MATCH (s:Standard {standard_id: 'STD-ISO-55000'})
            MATCH (a:Asset)
            MERGE (s)-[:GOVERNS]->(a)
            """
        )

        # Verification stats
        res_std = session.run("MATCH (s:Standard) RETURN count(s) as cnt").single()["cnt"]
        res_ib = session.run("MATCH (ib:IssuingBody) RETURN count(ib) as cnt").single()["cnt"]
        res_rel = session.run("MATCH (s:Standard)-[r]-() RETURN count(r) as cnt").single()["cnt"]

        logger.info(f"Graph Status: {res_std} :Standard nodes, {res_ib} :IssuingBody nodes, {res_rel} associated relationships.")

    except Exception as e:
        logger.error(f"Error during Neo4j ingestion: {e}", exc_info=True)
    finally:
        session.close()
        driver.close()


if __name__ == "__main__":
    ingest_standards_graph()
