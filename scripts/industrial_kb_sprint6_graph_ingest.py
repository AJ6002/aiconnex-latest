"""
scripts/industrial_kb_sprint6_graph_ingest.py

Phase 4: Neo4j Graph Ingestion for Sprint 6 Tenant Knowledge.
Creates Tenant, Project, and Asset nodes (:Tenant, :Project, :Asset)
and establishes relationships:
- (:Tenant)-[:OWNS_PROJECT]->(:Project)
- (:Asset)-[:BELONGS_TO]->(:Project)
- (:Asset)-[:INSTANCE_OF]->(:Equipment)  <-- Cognite Spaces Cross-Scope Link
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
logger = logging.getLogger("TenantGraphIngest")

REGISTRY_FILE = os.path.join(BASE_DIR, "aiconnex_knowledge", "08_tenant_knowledge", "tenant_registry.yaml")


def ingest_tenant_knowledge_graph():
    """Ingests tenant organizations, projects, and asset instances into Neo4j."""
    cfg = get_kb_config().neo4j
    driver = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))

    if not os.path.exists(REGISTRY_FILE):
        logger.error(f"Tenant registry file not found at: {REGISTRY_FILE}")
        return

    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tenants = data.get("tenants", [])
    projects = data.get("projects", [])
    assets = data.get("assets", [])

    logger.info(f"Loaded {len(tenants)} tenants, {len(projects)} projects, {len(assets)} assets from registry.")

    with driver.session() as session:
        # Step 1: Create Constraints
        logger.info("Setting up Neo4j uniqueness constraints...")
        constraints = [
            "CREATE CONSTRAINT tenant_id_unique IF NOT EXISTS FOR (t:Tenant) REQUIRE t.tenant_id IS UNIQUE",
            "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
            "CREATE CONSTRAINT asset_id_unique IF NOT EXISTS FOR (a:Asset) REQUIRE a.asset_id IS UNIQUE",
        ]
        for c in constraints:
            session.run(c)

        # Step 2: Merge Tenant Nodes
        logger.info("Merging :Tenant nodes...")
        tenant_cypher = """
        UNWIND $tenants AS t
        MERGE (tn:Tenant {tenant_id: t.tenant_id})
        SET tn.name = t.name,
            tn.industry = t.industry,
            tn.tier = t.tier,
            tn.status = t.status,
            tn.scope = 'tenant',
            tn.adopted_standards = t.adopted_standards
        RETURN count(tn) as count
        """
        res = session.run(tenant_cypher, tenants=tenants).single()
        logger.info(f"Merged {res['count']} :Tenant nodes.")

        # Step 3: Merge Project Nodes and Link to Tenants
        logger.info("Merging :Project nodes and (:Tenant)-[:OWNS_PROJECT]->(:Project)...")
        project_cypher = """
        UNWIND $projects AS p
        MERGE (pr:Project {project_id: p.project_id})
        SET pr.name = p.name,
            pr.plant_type = p.plant_type,
            pr.status = p.status,
            pr.tenant_id = p.tenant_id,
            pr.scope = 'project'
        WITH pr, p
        MATCH (t:Tenant {tenant_id: p.tenant_id})
        MERGE (t)-[:OWNS_PROJECT]->(pr)
        RETURN count(pr) as count
        """
        res = session.run(project_cypher, projects=projects).single()
        logger.info(f"Merged {res['count']} :Project nodes with OWNS_PROJECT edges.")

        # Step 4: Merge Asset Nodes and Link to Project & Global Equipment
        logger.info("Merging :Asset nodes with (:Asset)-[:BELONGS_TO]->(:Project) and (:Asset)-[:INSTANCE_OF]->(:Equipment)...")
        asset_cypher = """
        UNWIND $assets AS a
        MERGE (ast:Asset {asset_id: a.asset_id})
        SET ast.tag_number = a.tag_number,
            ast.description = a.description,
            ast.location = a.location,
            ast.manufacturer = a.manufacturer,
            ast.model_number = a.model_number,
            ast.install_date = a.install_date,
            ast.status = a.status,
            ast.tenant_id = a.tenant_id,
            ast.project_id = a.project_id,
            ast.equipment_id = a.equipment_id,
            ast.scope = 'project'
        WITH ast, a
        MATCH (p:Project {project_id: a.project_id})
        MERGE (ast)-[:BELONGS_TO]->(p)
        WITH ast, a
        MATCH (eq:Equipment {equipment_id: a.equipment_id})
        MERGE (ast)-[:INSTANCE_OF]->(eq)
        RETURN count(ast) as count
        """
        res = session.run(asset_cypher, assets=assets).single()
        logger.info(f"Merged {res['count']} :Asset nodes with BELONGS_TO and INSTANCE_OF edges.")

        # Step 5: Verification Queries
        logger.info("Verifying Neo4j Tenant Graph Statistics...")
        t_count = session.run("MATCH (t:Tenant) RETURN count(t) as c").single()["c"]
        p_count = session.run("MATCH (p:Project) RETURN count(p) as c").single()["c"]
        a_count = session.run("MATCH (a:Asset) RETURN count(a) as c").single()["c"]
        inst_count = session.run("MATCH (a:Asset)-[:INSTANCE_OF]->(e:Equipment) RETURN count(a) as c").single()["c"]
        belongs_count = session.run("MATCH (a:Asset)-[:BELONGS_TO]->(p:Project) RETURN count(a) as c").single()["c"]

        logger.info(f"=== S6 Graph Ingest Verification ===")
        logger.info(f"Tenant Nodes: {t_count}")
        logger.info(f"Project Nodes: {p_count}")
        logger.info(f"Asset Nodes: {a_count}")
        logger.info(f"Asset -> Equipment (:INSTANCE_OF) Edges: {inst_count}")
        logger.info(f"Asset -> Project (:BELONGS_TO) Edges: {belongs_count}")

    driver.close()
    logger.info("Sprint 6 Tenant Knowledge Graph Ingestion complete!")


if __name__ == "__main__":
    ingest_tenant_knowledge_graph()
