"""
scripts/industrial_kb_sprint3_graph_ingest.py

Phase 1: Neo4j Graph Ingestion for Sprint 3 ML Methodology KB.
Creates ML Methodology Nodes (:MLMethod, :ProblemFamily, :DataRequirement, :Metric)
and establishes relationships (:COMPETES_WITH, :DEPENDS_ON, :EXTENDS, :SUITABLE_FOR, :EVALUATED_BY).
"""

import os
import yaml
import logging
from neo4j import GraphDatabase
from agentic.platform_kb.config import get_kb_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MLGraphIngest")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(BASE_DIR, "aiconnex_knowledge", "06_ml_methodology", "canonical_methods.yaml")


def ingest_ml_methodology_graph():
    logger.info("=== Starting Neo4j Graph Ingestion for ML Methodology KB ===")

    if not os.path.exists(REGISTRY_FILE):
        logger.error(f"Registry file not found: {REGISTRY_FILE}")
        return

    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    methods = data.get("canonical_methods", [])

    cfg = get_kb_config().neo4j
    driver = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))
    session = driver.session()

    try:
        # 1. Create constraints & indexes
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:MLMethod) REQUIRE m.method_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (pf:ProblemFamily) REQUIRE pf.name IS UNIQUE")

        nodes_created = 0
        edges_created = 0

        for m in methods:
            m_id = m["method_id"]
            m_name = m["name"]
            p_fam = m["problem_family"]
            baseline = m.get("canonical_baseline")

            # Merge MLMethod node
            session.run(
                """
                MERGE (m:MLMethod {method_id: $method_id})
                SET m.name = $name,
                    m.task_type = $task_type,
                    m.model_family = $model_family,
                    m.capacity_level = $capacity_level,
                    m.interpretability = $interpretability,
                    m.canonical_baseline = $baseline,
                    m.authority = 'A'
                """,
                method_id=m_id,
                name=m_name,
                task_type=m["task_type"],
                model_family=m["model_family"],
                capacity_level=m["capacity_level"],
                interpretability=m["interpretability"],
                baseline=baseline
            )
            nodes_created += 1

            # Merge ProblemFamily node & relationship SUITABLE_FOR
            session.run(
                """
                MERGE (pf:ProblemFamily {name: $p_fam})
                WITH pf
                MATCH (m:MLMethod {method_id: $method_id})
                MERGE (m)-[:SUITABLE_FOR]->(pf)
                """,
                p_fam=p_fam,
                method_id=m_id
            )
            edges_created += 1

            # Link canonical baseline (EXTENDS / COMPETES_WITH)
            if baseline and baseline.startswith("ML-"):
                session.run(
                    """
                    MATCH (m1:MLMethod {method_id: $method_id})
                    MERGE (m2:MLMethod {method_id: $baseline})
                    MERGE (m1)-[:COMPETES_WITH]->(m2)
                    """,
                    method_id=m_id,
                    baseline=baseline
                )
                edges_created += 1

            # Link metrics (EVALUATED_BY)
            for metric in m.get("primary_metrics", []):
                session.run(
                    """
                    MERGE (met:Metric {name: $metric})
                    WITH met
                    MATCH (m:MLMethod {method_id: $method_id})
                    MERGE (m)-[:EVALUATED_BY]->(met)
                    """,
                    metric=metric,
                    method_id=m_id
                )
                edges_created += 1

        logger.info(f"Ingested {nodes_created} MLMethod nodes and {edges_created} relationships into Neo4j graph.")

    finally:
        session.close()
        driver.close()


if __name__ == "__main__":
    ingest_ml_methodology_graph()
