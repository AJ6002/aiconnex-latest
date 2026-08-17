"""
scripts/industrial_kb_sprint7_graph_ingest.py

Neo4j Knowledge Graph Ingestion Script for Documentation KB (Sprint 7).
Populates:
- :SpecDocument nodes (22 authoritative specification documents)
- :SystemComponent nodes (all target subsystems)
- :PerformanceSLA nodes (quantifiable performance SLAs and budgets)
- :StateTransition nodes (deterministic agent/node state machines)
- :ErrorContract nodes (error codes and recovery actions)
- Relationships: :DEFINES_SLA, :MUST_MEET, :SPECIFIES_TRANSITION, :IMPLEMENTS_TRANSITION,
                 :EMITS_ERROR, :GOVERNS_COMPONENT, :CROSS_REFERENCES
"""

import os
import sys
import yaml
import logging
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase
from agentic.platform_kb.config import get_kb_config
from agentic.platform_kb.db_client import KBInfraClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SPECS_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "03_deterministic",
    "registries",
    "documentation_specs.yaml",
)


def ingest_documentation_graph():
    if not os.path.exists(SPECS_YAML):
        raise FileNotFoundError(f"Documentation specs YAML not found at: {SPECS_YAML}")

    with open(SPECS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    specs = data.get("specs", [])
    logger.info(f"Loaded {len(specs)} specification records from YAML.")

    cfg = get_kb_config().neo4j
    try:
        driver = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))
        with driver.session() as session:
            # 1. Create Constraints and Indexes
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:SpecDocument) REQUIRE d.spec_id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:SystemComponent) REQUIRE c.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:PerformanceSLA) REQUIRE s.sla_id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:StateTransition) REQUIRE t.transition_id IS UNIQUE")
            logger.info("Constraints and indexes created in Neo4j.")
    except Exception as e:
        logger.warning(f"Neo4j is not currently reachable at {cfg.bolt_uri} ({e}). Skipping live graph ingestion (YAML deterministic fallback is active).")
        return

        total_nodes = 0
        total_rels = 0

        for spec in specs:
            spec_id = spec["spec_id"]
            title = spec["title"]
            studio = spec.get("studio", "PlatformCore")
            category = spec.get("category", "Performance")
            summary = spec.get("summary", "")
            doc_path = spec.get("source_document_path", "")

            # Merge :SpecDocument node
            session.run(
                """
                MERGE (d:SpecDocument {spec_id: $spec_id})
                SET d.title = $title,
                    d.studio = $studio,
                    d.category = $category,
                    d.summary = $summary,
                    d.source_path = $doc_path,
                    d.authority = 'A',
                    d.status = 'Approved'
                """,
                spec_id=spec_id,
                title=title,
                studio=studio,
                category=category,
                summary=summary,
                doc_path=doc_path,
            )
            total_nodes += 1

            # Merge Target Components & :GOVERNS_COMPONENT
            for comp in spec.get("target_subsystems", []):
                session.run(
                    """
                    MERGE (c:SystemComponent {name: $comp})
                    WITH c
                    MATCH (d:SpecDocument {spec_id: $spec_id})
                    MERGE (d)-[:GOVERNS_COMPONENT]->(c)
                    """,
                    comp=comp,
                    spec_id=spec_id,
                )
                total_nodes += 1
                total_rels += 1

            # Merge SLAs & :DEFINES_SLA, :MUST_MEET
            for sla in spec.get("governing_slas", []):
                sla_id = sla["sla_id"]
                comp_name = sla["component_name"]
                session.run(
                    """
                    MERGE (s:PerformanceSLA {sla_id: $sla_id})
                    SET s.metric_name = $metric_name,
                        s.target_value = $target_value,
                        s.unit = $unit,
                        s.comparison_op = $comparison_op,
                        s.condition = $condition,
                        s.severity = $severity,
                        s.source_spec_id = $spec_id
                    WITH s
                    MATCH (d:SpecDocument {spec_id: $spec_id})
                    MERGE (d)-[:DEFINES_SLA]->(s)
                    WITH s
                    MERGE (c:SystemComponent {name: $comp_name})
                    MERGE (c)-[:MUST_MEET]->(s)
                    """,
                    sla_id=sla_id,
                    metric_name=sla.get("metric_name", ""),
                    target_value=float(sla.get("target_value", 0.0)),
                    unit=sla.get("unit", ""),
                    comparison_op=sla.get("comparison_op", "<="),
                    condition=sla.get("workload_condition", ""),
                    severity=sla.get("severity_on_breach", "critical"),
                    spec_id=spec_id,
                    comp_name=comp_name,
                )
                total_nodes += 1
                total_rels += 2

            # Merge State Transitions & :SPECIFIES_TRANSITION, :IMPLEMENTS_TRANSITION
            for trans in spec.get("state_transitions", []):
                t_id = trans["transition_id"]
                feat_name = trans["feature_or_agent"]
                session.run(
                    """
                    MERGE (t:StateTransition {transition_id: $t_id})
                    SET t.from_state = $from_state,
                        t.to_state = $to_state,
                        t.trigger = $trigger,
                        t.guard = $guard,
                        t.is_terminal = $is_terminal,
                        t.source_spec_id = $spec_id
                    WITH t
                    MATCH (d:SpecDocument {spec_id: $spec_id})
                    MERGE (d)-[:SPECIFIES_TRANSITION]->(t)
                    WITH t
                    MERGE (c:SystemComponent {name: $feat_name})
                    MERGE (c)-[:IMPLEMENTS_TRANSITION]->(t)
                    """,
                    t_id=t_id,
                    from_state=trans.get("from_state", ""),
                    to_state=trans.get("to_state", ""),
                    trigger=trans.get("trigger_event", ""),
                    guard=trans.get("guard_condition", ""),
                    is_terminal=bool(trans.get("is_terminal", False)),
                    spec_id=spec_id,
                    feat_name=feat_name,
                )
                total_nodes += 1
                total_rels += 2

            # Merge Error Contracts
            for err in spec.get("error_contracts", []):
                err_code = err.get("error_code", f"ERR-{spec_id}")
                session.run(
                    """
                    MERGE (e:ErrorContract {code: $err_code})
                    SET e.description = $desc,
                        e.action = $action,
                        e.source_spec_id = $spec_id
                    WITH e
                    MATCH (d:SpecDocument {spec_id: $spec_id})
                    MERGE (d)-[:DECLARES_ERROR]->(e)
                    """,
                    err_code=err_code,
                    desc=err.get("description", ""),
                    action=err.get("action", ""),
                    spec_id=spec_id,
                )
                total_nodes += 1
                total_rels += 1

            # Merge Cross References
            for ref_id in spec.get("cross_references", []):
                session.run(
                    """
                    MATCH (d1:SpecDocument {spec_id: $spec_id})
                    MERGE (d2:SpecDocument {spec_id: $ref_id})
                    MERGE (d1)-[:CROSS_REFERENCES]->(d2)
                    """,
                    spec_id=spec_id,
                    ref_id=ref_id,
                )
                total_rels += 1

        # Verification stats
        res = session.run(
            """
            MATCH (d:SpecDocument)
            OPTIONAL MATCH (d)-[r]->()
            RETURN count(DISTINCT d) as doc_count, count(r) as rel_count
            """
        ).single()

        logger.info(
            f"Successfully ingested Documentation Graph! Neo4j Stats: "
            f"{res['doc_count']} SpecDocument nodes, {res['rel_count']} relationships."
        )

    driver.close()


if __name__ == "__main__":
    ingest_documentation_graph()
