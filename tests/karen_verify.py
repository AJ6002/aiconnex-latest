import os

print("=== 9. PostgreSQL ===")
from agentic.platform_kb.db_client import KBInfraClient
c = KBInfraClient()
conn = c.get_postgres_connection()
cur = conn.cursor()
cur.execute('SELECT count(*) FROM knowledge_standards')
print('PG rows:', cur.fetchone()[0])
cur.execute("SELECT standard_id, designation FROM knowledge_standards WHERE issuing_body = 'NIST'")
rows = cur.fetchall()
print('NIST in PG:', rows)
cur.close()
conn.close()

print("=== 10. Neo4j ===")
from neo4j import GraphDatabase
from agentic.platform_kb.config import get_kb_config
cfg = get_kb_config().neo4j
d = GraphDatabase.driver(cfg.bolt_uri, auth=(cfg.user, cfg.password))
s = d.session()
r1 = s.run('MATCH (s:Standard) RETURN count(s) as cnt').single()['cnt']
r2 = s.run('MATCH (ib:IssuingBody) RETURN count(ib) as cnt').single()['cnt']
r3 = s.run('MATCH (s:Standard)-[r]-() RETURN count(r) as cnt').single()['cnt']
r4 = s.run('MATCH (s:Standard)-[:APPLIES_TO]->(e:Equipment) RETURN count(DISTINCT s) as std_cnt, count(DISTINCT e) as eq_cnt').single()
r5 = s.run('MATCH (s:Standard)-[:GOVERNS]->(m:MLMethod) RETURN count(DISTINCT s) as cnt').single()['cnt']
r6 = s.run('MATCH (s:Standard)-[:SUPERSEDES]->(old:Standard) RETURN count(s) as cnt').single()['cnt']
print(f'Standard nodes: {r1}')
print(f'IssuingBody nodes: {r2}')
print(f'Total relationships: {r3}')
print(f'APPLIES_TO: {r4["std_cnt"]} stds -> {r4["eq_cnt"]} equipment')
print(f'GOVERNS MLMethod: {r5}')
print(f'SUPERSEDES lineage: {r6}')
s.close()
d.close()

print("=== A. Filesystem ===")
import yaml
with open('aiconnex_knowledge/07_standards_regulatory/canonical_standards.yaml') as f:
    data = yaml.safe_load(f)
    print("YAML standards count:", len(data.get('standards', [])))

print("schemas.py exists:", os.path.exists('aiconnex_agent/platform_kb/schemas.py'))
print("standards_service.py exists:", os.path.exists('aiconnex_agent/platform_kb/standards_service.py'))
print("context_builder.py exists:", os.path.exists('aiconnex_agent/platform_kb/context_builder.py'))
print("__init__.py exists:", os.path.exists('aiconnex_agent/platform_kb/__init__.py'))
