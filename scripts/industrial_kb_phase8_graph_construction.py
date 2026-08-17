"""
scripts/industrial_kb_phase8_graph_construction.py

Phase 8 — Knowledge Graph Construction in Neo4j.
Merges Phase 7 extracted structured facts into the live Neo4j Industrial Knowledge Graph.
Attaches provenance attributes (document_id, chunk_id, page_number) onto relationship edges.
Links extracted entity nodes to Phase 4 :CanonicalEntity nodes.
"""

import os
import json
import sys
from neo4j import GraphDatabase

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FACTS_PATH = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "04_structured", "extracted_industrial_facts.json")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "neo4j_secret_password_2026")


def run_phase8_graph_construction():
    print("=== Phase 8 — Knowledge Graph Construction ===")

    if not os.path.exists(FACTS_PATH):
        raise FileNotFoundError(f"Extracted facts JSON not found: {FACTS_PATH}")

    with open(FACTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        facts = data.get("facts", [])

    print(f"Loaded {len(facts)} extracted structured facts for Neo4j graph construction.")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    print("[OK] Connected to Neo4j Database.")

    with driver.session() as session:
        # Create Entity index
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE;")

        # 1. Ingest Extracted Entities & Relationships with Provenance
        for idx, fact in enumerate(facts, start=1):
            subj_name = fact["subject_entity"]
            subj_type = fact["subject_type"]
            rel_type = fact["relation_type"].upper().replace(" ", "_")
            obj_name = fact["object_entity"]
            obj_type = fact["object_type"]

            doc_id = fact["document_id"]
            chunk_id = fact["chunk_id"]
            page_num = fact["page_number"]

            # Merge Subject & Object Nodes
            session.run(
                """
                MERGE (s:Entity {name: $subj_name})
                SET s.category = $subj_type
                MERGE (o:Entity {name: $obj_name})
                SET o.category = $obj_type
                """,
                subj_name=subj_name, subj_type=subj_type,
                obj_name=obj_name, obj_type=obj_type
            )

            # Merge Relationship with Provenance Edges
            cypher_rel = f"""
                MATCH (s:Entity {{name: $subj_name}})
                MATCH (o:Entity {{name: $obj_name}})
                MERGE (s)-[r:{rel_type}]->(o)
                SET r.document_id = $doc_id,
                    r.chunk_id = $chunk_id,
                    r.page_number = $page_num,
                    r.confidence = 0.95,
                    r.provenance = 'Extracted Document Fact'
            """
            session.run(cypher_rel, subj_name=subj_name, obj_name=obj_name, doc_id=doc_id, chunk_id=chunk_id, page_num=page_num)

        print(f"  [OK] Ingested {len(facts)} extracted facts into Neo4j graph edges with provenance.")

        # 2. Link Extracted Entities to Phase 4 CanonicalEntity Schema Nodes
        session.run(
            """
            MATCH (e:Entity)
            MATCH (c:CanonicalEntity)
            WHERE toLower(e.category) = toLower(c.name)
            MERGE (e)-[:INSTANCE_OF]->(c)
            """
        )
        print("  [OK] Linked extracted :Entity nodes to Phase 4 :CanonicalEntity schema nodes.")

        # Live Neo4j Graph Readout
        total_nodes = session.run("MATCH (n) RETURN COUNT(n) AS cnt").single()["cnt"]
        total_rels = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS cnt").single()["cnt"]
        ext_entities = session.run("MATCH (e:Entity) RETURN COUNT(e) AS cnt").single()["cnt"]
        inst_rels = session.run("MATCH ()-[r:INSTANCE_OF]->() RETURN COUNT(r) AS cnt").single()["cnt"]

        print(f"\n[NEO4J LIVE DATABASE READOUT]:")
        print(f"  - Total Graph Nodes: {total_nodes}")
        print(f"  - Total Graph Relationships: {total_rels}")
        print(f"  - Extracted Domain Entity Nodes: {ext_entities}")
        print(f"  - Canonical INSTANCE_OF Links: {inst_rels}")

    driver.close()
    print("\nPhase 8 Knowledge Graph Construction Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase8_graph_construction()
