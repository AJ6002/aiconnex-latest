"""
scripts/industrial_kb_sprint4_graph_ingest.py

Phase 3: Neo4j Graph Ingestion for Sprint 4 Equipment & Asset KB.
Creates Equipment Nodes (:Equipment, :Subsystem, :Component, :Sensor, :FailureMode, :MaintenanceAction)
and establishes Option A relationships (:HAS_SUBSYSTEM, :HAS_COMPONENT, :MONITORED_BY, :HAS_FAILURE_MODE, :ADDRESSED_BY).
"""

import os
import yaml
import logging
from neo4j import GraphDatabase
from agentic.platform_kb.config import get_kb_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EquipmentGraphIngest")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(BASE_DIR, "aiconnex_knowledge", "06_equipment_asset", "canonical_equipment.yaml")


def ingest_equipment_graph():
    logger.info("=== Starting Neo4j Graph Ingestion for Equipment & Asset KB ===")

    if not os.path.exists(REGISTRY_FILE):
        logger.error(f"Registry file not found: {REGISTRY_FILE}")
        return

    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    equipments = data.get("canonical_equipment", [])

    cfg = get_kb_config().neo4j
    driver = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))
    session = driver.session()

    try:
        # 1. Create constraints & indexes
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Equipment) REQUIRE e.equipment_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (sub:Subsystem) REQUIRE sub.subsystem_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Component) REQUIRE c.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Sensor) REQUIRE s.sensor_type IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (fm:FailureMode) REQUIRE fm.failure_code IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (ma:MaintenanceAction) REQUIRE ma.name IS UNIQUE")

        nodes_created = 0
        edges_created = 0

        for eq in equipments:
            eq_id = eq["equipment_id"]
            eq_name = eq["name"]
            eq_class = eq["equipment_class"]
            eq_cat = eq["category"]
            std_ref = eq["standard_ref"]

            # Merge Equipment node
            session.run(
                """
                MERGE (e:Equipment {equipment_id: $equipment_id})
                SET e.name = $name,
                    e.equipment_class = $equipment_class,
                    e.category = $category,
                    e.standard_ref = $standard_ref,
                    e.authority = 'A',
                    e.knowledge_domain = 'equipment_asset'
                """,
                equipment_id=eq_id,
                name=eq_name,
                equipment_class=eq_class,
                category=eq_cat,
                standard_ref=std_ref
            )
            nodes_created += 1

            # Link to S1 CanonicalEntity {name: 'Equipment'}
            session.run(
                """
                MATCH (e:Equipment {equipment_id: $equipment_id})
                MERGE (ce:CanonicalEntity {name: 'Equipment'})
                MERGE (e)-[:INSTANCE_OF]->(ce)
                """,
                equipment_id=eq_id
            )
            edges_created += 1

            # 2. Subsystems & Components
            for sub in eq.get("subsystems", []):
                sub_id = sub["subsystem_id"]
                sub_name = sub["name"]
                session.run(
                    """
                    MERGE (sub:Subsystem {subsystem_id: $sub_id})
                    SET sub.name = $sub_name
                    WITH sub
                    MATCH (e:Equipment {equipment_id: $eq_id})
                    MERGE (e)-[:HAS_SUBSYSTEM]->(sub)
                    """,
                    sub_id=sub_id,
                    sub_name=sub_name,
                    eq_id=eq_id
                )
                nodes_created += 1
                edges_created += 1

                for comp_name in sub.get("components", []):
                    session.run(
                        """
                        MERGE (c:Component {name: $comp_name})
                        WITH c
                        MATCH (sub:Subsystem {subsystem_id: $sub_id})
                        MERGE (sub)-[:HAS_COMPONENT]->(c)
                        """,
                        comp_name=comp_name,
                        sub_id=sub_id
                    )
                    nodes_created += 1
                    edges_created += 1

            # 3. Direct Components
            for comp_name in eq.get("direct_components", []):
                session.run(
                    """
                    MERGE (c:Component {name: $comp_name})
                    WITH c
                    MATCH (e:Equipment {equipment_id: $eq_id})
                    MERGE (e)-[:HAS_COMPONENT]->(c)
                    """,
                    comp_name=comp_name,
                    eq_id=eq_id
                )
                nodes_created += 1
                edges_created += 1

            # 4. Monitored Sensors
            for s_info in eq.get("monitored_sensors", []):
                s_type = s_info["sensor_type"]
                m_prop = s_info["measurement_property"]
                t_unit = s_info.get("typical_unit", "")
                session.run(
                    """
                    MERGE (s:Sensor {sensor_type: $s_type})
                    SET s.measurement_property = $m_prop,
                        s.typical_unit = $t_unit
                    WITH s
                    MATCH (e:Equipment {equipment_id: $eq_id})
                    MERGE (e)-[:MONITORED_BY]->(s)
                    """,
                    s_type=s_type,
                    m_prop=m_prop,
                    t_unit=t_unit,
                    eq_id=eq_id
                )
                nodes_created += 1
                edges_created += 1

            # 5. Failure Modes & Maintenance Actions
            for fm in eq.get("failure_modes", []):
                fm_code = fm["failure_code"]
                fm_name = fm["name"]
                fm_mech = fm["mechanism"]
                iso_code = fm.get("iso_14224_code", "")
                maint = fm.get("typical_maintenance", "")

                session.run(
                    """
                    MERGE (fm:FailureMode {failure_code: $fm_code})
                    SET fm.name = $fm_name,
                        fm.mechanism = $fm_mech,
                        fm.iso_14224_code = $iso_code
                    WITH fm
                    MATCH (e:Equipment {equipment_id: $eq_id})
                    MERGE (e)-[:HAS_FAILURE_MODE]->(fm)
                    """,
                    fm_code=fm_code,
                    fm_name=fm_name,
                    fm_mech=fm_mech,
                    iso_code=iso_code,
                    eq_id=eq_id
                )
                nodes_created += 1
                edges_created += 1

                # Link failure mode to affected components
                for comp_name in fm.get("affected_components", []):
                    session.run(
                        """
                        MATCH (fm:FailureMode {failure_code: $fm_code})
                        MERGE (c:Component {name: $comp_name})
                        MERGE (c)-[:HAS_FAILURE_MODE]->(fm)
                        """,
                        fm_code=fm_code,
                        comp_name=comp_name
                    )
                    edges_created += 1

                # Link to MaintenanceAction
                if maint:
                    session.run(
                        """
                        MATCH (fm:FailureMode {failure_code: $fm_code})
                        MERGE (ma:MaintenanceAction {name: $maint})
                        MERGE (fm)-[:ADDRESSED_BY]->(ma)
                        """,
                        fm_code=fm_code,
                        maint=maint
                    )
                    nodes_created += 1
                    edges_created += 1

        logger.info(f"Successfully ingested Equipment Graph into Neo4j ({nodes_created} nodes/updates, {edges_created} relationships).")

    finally:
        session.close()
        driver.close()


if __name__ == "__main__":
    ingest_equipment_graph()
