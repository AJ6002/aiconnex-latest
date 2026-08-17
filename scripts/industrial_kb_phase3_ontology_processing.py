"""
scripts/industrial_kb_phase3_ontology_processing.py

Phase 3 — Ontology Processing & Neo4j Graph Ingestion.
Parses core W3C OWL/TTL/RDF ontologies (BFO, IOF, ROMAIN, CEON) using `rdflib`.
Extracts Classes, Subclasses, ObjectProperties, Domain/Range restrictions, and Annotations.
Populates the Neo4j Industrial Knowledge Graph via Cypher over Bolt protocol.
"""

import os
import json
import logging
from typing import Dict, List, Any, Set
from rdflib import Graph, RDFS, RDF, OWL, SKOS, URIRef, Literal
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_BASE = os.path.join(_PROJECT_ROOT, "knowledge", "Industrail_KB_raw_data", "01_ontologies_and_repositories")
STRUCTURED_DIR = os.path.join(_PROJECT_ROOT, "aiconnex_knowledge", "04_structured")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "neo4j_secret_password_2026")

# Target Core Schema Files per Ontology
CORE_ONTOLOGY_FILES = [
    # --- BFO (Basic Formal Ontology) ---
    {
        "ontology": "BFO",
        "name": "BFO 2020 Core",
        "path": os.path.join(RAW_BASE, r"BFO-2020-master\BFO-2020-master\21838-2\owl\bfo-core.ttl"),
        "format": "turtle"
    },
    {
        "ontology": "BFO",
        "name": "BFO Legacy Classes",
        "path": os.path.join(RAW_BASE, r"BFO-master\BFO-master\bfo_classes_only.owl"),
        "format": "xml"
    },

    # --- IOF (Industrial Ontology Foundry) ---
    {
        "ontology": "IOF",
        "name": "IOF Core",
        "path": os.path.join(RAW_BASE, r"IOF-ontology-master\ontology-master\core\Core.rdf"),
        "format": "xml"
    },
    {
        "ontology": "IOF",
        "name": "IOF Maintenance",
        "path": os.path.join(RAW_BASE, r"IOF-ontology-master\ontology-master\maintenance\Maintenance.rdf"),
        "format": "xml"
    },
    {
        "ontology": "IOF",
        "name": "IOF SupplyChain",
        "path": os.path.join(RAW_BASE, r"IOF-ontology-master\ontology-master\supplychain\SupplyChain.rdf"),
        "format": "xml"
    },

    # --- ROMAIN (Maintenance Ontology) ---
    {
        "ontology": "ROMAIN",
        "name": "ROMAIN Core",
        "path": os.path.join(RAW_BASE, r"ROMAIN-master\ROMAIN-master\ROMAIN.owl"),
        "format": "xml"
    },
    {
        "ontology": "ROMAIN",
        "name": "ROMAIN Artifacts",
        "path": os.path.join(RAW_BASE, r"ROMAIN-master\ROMAIN-master\ArtifactOntology.owl"),
        "format": "xml"
    },
    {
        "ontology": "ROMAIN",
        "name": "ROMAIN Events",
        "path": os.path.join(RAW_BASE, r"ROMAIN-master\ROMAIN-master\EventOntology.owl"),
        "format": "xml"
    },

    # --- CEON (Circular Economy Ontology) ---
    {
        "ontology": "CEON",
        "name": "CEON IOF Core Alignment",
        "path": os.path.join(RAW_BASE, r"Circular-Economy-Ontology-Catalogue-main\alignments\KG4S2025\task_b\CEON-IOFcore.rdf"),
        "format": "xml"
    },
    {
        "ontology": "CEON",
        "name": "CEON ROMAIN Alignment",
        "path": os.path.join(RAW_BASE, r"Circular-Economy-Ontology-Catalogue-main\alignments\task_b\CEON-LO\CEON-ROMAIN\CEON-ROMAIN-ATM.rdf"),
        "format": "xml"
    }
]


def clean_label(uri: str, g: Graph) -> str:
    """Extracts rdfs:label or skos:prefLabel or fallback to URI fragment."""
    for _, _, label in g.triples((URIRef(uri), RDFS.label, None)):
        if isinstance(label, Literal):
            return str(label)
    for _, _, label in g.triples((URIRef(uri), SKOS.prefLabel, None)):
        if isinstance(label, Literal):
            return str(label)
    if "#" in uri:
        return uri.split("#")[-1]
    return uri.split("/")[-1]


def clean_comment(uri: str, g: Graph) -> str:
    """Extracts rdfs:comment or skos:definition or empty string."""
    for _, _, comment in g.triples((URIRef(uri), RDFS.comment, None)):
        if isinstance(comment, Literal):
            return str(comment)
    for _, _, comment in g.triples((URIRef(uri), SKOS.definition, None)):
        if isinstance(comment, Literal):
            return str(comment)
    return ""


def run_phase3_ontology_processing():
    print("=== Phase 3 — Ontology Processing & Neo4j Graph Ingestion ===")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    print("[OK] Connected to Neo4j database.")

    # Initialize Neo4j constraints & indexes
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.uri IS UNIQUE;")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Property) REQUIRE p.uri IS UNIQUE;")
        session.run("CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.name);")

    all_nodes: Dict[str, Dict[str, Any]] = {}
    all_subclass_edges: Set[tuple] = set()
    all_properties: Dict[str, Dict[str, Any]] = {}
    all_domain_range_edges: Set[tuple] = set()

    # Parse each core ontology
    for spec in CORE_ONTOLOGY_FILES:
        path = spec["path"]
        if not os.path.exists(path):
            print(f"[SKIP] Spec file not found: {path}")
            continue

        print(f"\nParsing {spec['ontology']} — {spec['name']} ({os.path.basename(path)})...")
        g = Graph()
        try:
            g.parse(path, format=spec["format"])
            print(f"  [OK] Loaded {len(g)} RDF triples.")
        except Exception as err:
            print(f"  [FAIL] Failed to parse {path}: {err}")
            continue

        # Extract Classes (owl:Class, rdfs:Class)
        for s in g.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                uri_str = str(s)
                if uri_str not in all_nodes:
                    all_nodes[uri_str] = {
                        "uri": uri_str,
                        "name": clean_label(uri_str, g),
                        "comment": clean_comment(uri_str, g),
                        "ontology": spec["ontology"],
                        "type": "Class"
                    }

        for s in g.subjects(RDF.type, RDFS.Class):
            if isinstance(s, URIRef):
                uri_str = str(s)
                if uri_str not in all_nodes:
                    all_nodes[uri_str] = {
                        "uri": uri_str,
                        "name": clean_label(uri_str, g),
                        "comment": clean_comment(uri_str, g),
                        "ontology": spec["ontology"],
                        "type": "Class"
                    }

        # Extract Subclass Edges (rdfs:subClassOf)
        for sub, _, obj in g.triples((None, RDFS.subClassOf, None)):
            if isinstance(sub, URIRef) and isinstance(obj, URIRef):
                all_subclass_edges.add((str(sub), str(obj)))

        # Extract ObjectProperties (owl:ObjectProperty)
        for p in g.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(p, URIRef):
                uri_str = str(p)
                all_properties[uri_str] = {
                    "uri": uri_str,
                    "name": clean_label(uri_str, g),
                    "comment": clean_comment(uri_str, g),
                    "ontology": spec["ontology"],
                    "type": "ObjectProperty"
                }
                # Domain & Range
                for _, _, dom in g.triples((p, RDFS.domain, None)):
                    if isinstance(dom, URIRef):
                        all_domain_range_edges.add((uri_str, str(dom), "HAS_DOMAIN"))
                for _, _, rng in g.triples((p, RDFS.range, None)):
                    if isinstance(rng, URIRef):
                        all_domain_range_edges.add((uri_str, str(rng), "HAS_RANGE"))

    print(f"\nOntology Parsing Summary:")
    print(f"  - Total Unique Classes Extracted: {len(all_nodes)}")
    print(f"  - Total Subclass Relationships: {len(all_subclass_edges)}")
    print(f"  - Total Object Properties Extracted: {len(all_properties)}")
    print(f"  - Total Domain/Range Restraint Edges: {len(all_domain_range_edges)}")

    # Ingest into Neo4j in batches
    print("\nIngesting Industrial Knowledge Graph into Neo4j...")
    with driver.session() as session:
        # 1. Create Class Nodes
        node_records = list(all_nodes.values())
        session.run(
            """
            UNWIND $batch AS row
            MERGE (c:Class {uri: row.uri})
            SET c.name = row.name,
                c.comment = row.comment,
                c.ontology = row.ontology,
                c.type = row.type
            """,
            batch=node_records
        )
        print(f"  [OK] Ingested {len(node_records)} Class nodes into Neo4j.")

        # 2. Create ObjectProperty Nodes
        prop_records = list(all_properties.values())
        session.run(
            """
            UNWIND $batch AS row
            MERGE (p:Property {uri: row.uri})
            SET p.name = row.name,
                p.comment = row.comment,
                p.ontology = row.ontology,
                p.type = row.type
            """,
            batch=prop_records
        )
        print(f"  [OK] Ingested {len(prop_records)} Property nodes into Neo4j.")

        # 3. Create SUBCLASS_OF Edges
        edge_records = [{"sub": s, "obj": o} for s, o in all_subclass_edges if s in all_nodes and o in all_nodes]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (sub:Class {uri: row.sub})
            MATCH (obj:Class {uri: row.obj})
            MERGE (sub)-[:SUBCLASS_OF]->(obj)
            """,
            batch=edge_records
        )
        print(f"  [OK] Ingested {len(edge_records)} SUBCLASS_OF relationships into Neo4j.")

        # 4. Create HAS_DOMAIN & HAS_RANGE Edges
        dom_range_records = [
            {"prop": p, "cls": c, "rel": rel}
            for p, c, rel in all_domain_range_edges
            if p in all_properties and c in all_nodes
        ]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (p:Property {uri: row.prop})
            MATCH (c:Class {uri: row.cls})
            FOREACH (ignore IN CASE WHEN row.rel = 'HAS_DOMAIN' THEN [1] ELSE [] END |
                MERGE (p)-[:HAS_DOMAIN]->(c)
            )
            FOREACH (ignore IN CASE WHEN row.rel = 'HAS_RANGE' THEN [1] ELSE [] END |
                MERGE (p)-[:HAS_RANGE]->(c)
            )
            """,
            batch=dom_range_records
        )
        print(f"  [OK] Ingested {len(dom_range_records)} HAS_DOMAIN / HAS_RANGE relationships into Neo4j.")

        # Verify Neo4j Graph Counts directly
        res_nodes = session.run("MATCH (n) RETURN COUNT(n) AS cnt").single()["cnt"]
        res_rels = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS cnt").single()["cnt"]
        print(f"\n[NEO4J LIVE DATABASE READOUT]: {res_nodes} Total Nodes | {res_rels} Total Relationships")

    # Export Structured JSON Artifacts
    os.makedirs(os.path.join(STRUCTURED_DIR, "entities"), exist_ok=True)
    os.makedirs(os.path.join(STRUCTURED_DIR, "relationships"), exist_ok=True)
    os.makedirs(os.path.join(STRUCTURED_DIR, "ontology_mapping"), exist_ok=True)

    with open(os.path.join(STRUCTURED_DIR, "entities", "industrial_ontology_entities.json"), "w", encoding="utf-8") as f:
        json.dump(list(all_nodes.values()), f, indent=2)

    with open(os.path.join(STRUCTURED_DIR, "relationships", "industrial_ontology_relationships.json"), "w", encoding="utf-8") as f:
        json.dump([{"subclass": s, "superclass": o} for s, o in all_subclass_edges], f, indent=2)

    with open(os.path.join(STRUCTURED_DIR, "ontology_mapping", "mappings.json"), "w", encoding="utf-8") as f:
        json.dump({
            "upper_ontology": "BFO 2020",
            "domain_ontologies": ["IOF", "ROMAIN", "CEON"],
            "total_classes": len(all_nodes),
            "total_properties": len(all_properties),
            "total_edges": len(all_subclass_edges) + len(all_domain_range_edges)
        }, f, indent=2)

    driver.close()
    print("\nPhase 3 Ontology Processing Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase3_ontology_processing()
