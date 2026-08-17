"""
aiconnex_agent/platform_kb/retrieval_service.py

Unified Knowledge Retrieval Router and EvidencePack Builder for Platform Knowledge Base (Step 12).
Implements exact, semantic (Qdrant), keyword (PostgreSQL pg_trgm), and hybrid (Reciprocal Rank Fusion)
retrieval modes, authority-aware scoring, trace ID audit logging, and Tier 13
'13_provenance/retrieval_events.jsonl' event recording.
"""

import os
import re
import yaml
import json
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal

from agentic.platform_kb.config import QdrantConfig
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter
from agentic.platform_kb.deterministic_store import DeterministicStore
from agentic.platform_kb.schemas import (
    ContextRequest,
    EvidenceItem,
    EvidencePack,
    KnowledgeSourceRecord,
)
from agentic.platform_kb.source_register import SourceRegisterManager

logger = logging.getLogger(__name__)

PROVENANCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "13_provenance",
)
DETERMINISTIC_REGISTRIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "03_deterministic",
    "registries",
)

AUTHORITY_WEIGHTS = {
    "A": 1.2,
    "B": 1.0,
    "C": 0.8,
}

TENANT_PRIORITY_WEIGHT = 1.35


def _get_item_weight(authority: str, is_tenant_scoped: bool = False) -> float:
    """
    Computes ranking multiplier prioritizing Tenant Knowledge over Global Reference Knowledge.
    Tenant custom rules strictly outrank generic global standards.
    """
    base_w = AUTHORITY_WEIGHTS.get(authority, 1.0)
    return base_w * (TENANT_PRIORITY_WEIGHT if is_tenant_scoped else 1.0)


class RetrievalService:
    """
    Unified Retrieval Service and EvidencePack Orchestrator.
    Routes agent context requests across exact, semantic, keyword, and hybrid RRF retrieval modes.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        embedder: Optional[EmbeddingEngine] = None,
        store: Optional[DeterministicStore] = None,
        provenance_dir: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.embedder = embedder or EmbeddingEngine()
        self.store = store or DeterministicStore(db_client=self.db_client)
        self.upserter = QdrantUpserter(db_client=self.db_client)
        self.source_manager = SourceRegisterManager()
        self.provenance_dir = provenance_dir or PROVENANCE_DIR

    def _log_provenance_event(self, request: ContextRequest, pack: EvidencePack) -> None:
        """
        Appends retrieval event to Tier 13 (aiconnex_knowledge/13_provenance/retrieval_events.jsonl).
        """
        try:
            os.makedirs(self.provenance_dir, exist_ok=True)
            readme_path = os.path.join(self.provenance_dir, "README.md")
            if not os.path.exists(readme_path):
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(
                        "# Tier 13 — Retrieval Provenance & Audit Logs\n\n"
                        "Stores append-only JSONL audit event logs recording all agent knowledge retrieval requests and EvidencePacks.\n"
                    )

            event_path = os.path.join(self.provenance_dir, "retrieval_events.jsonl")
            # Compute SHA-256 hash of retrieved LLM context
            context_raw = "".join([f"{item.chunk_id}:{item.text}" for item in pack.results])
            context_hash = hashlib.sha256(context_raw.encode("utf-8")).hexdigest() if context_raw else "0" * 64

            event_record = {
                "trace_id": pack.trace_id,
                "timestamp": pack.timestamp,
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "tenant_id": request.tenant_id,
                "query": request.query,
                "retrieval_mode": pack.retrieval_mode,
                "result_count": len(pack.results),
                "top_score": pack.results[0].score if pack.results else 0.0,
                "context_hash": context_hash,
            }

            with open(event_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_record) + "\n")
        except Exception as e:
            logger.error(f"Failed to record retrieval provenance event: {e}")

    def load_deterministic_registries(self) -> Dict[str, Any]:
        """
        Reads deterministic YAML registries from 03_deterministic/registries/.
        """
        facts = {}
        if not os.path.exists(DETERMINISTIC_REGISTRIES_DIR):
            return facts

        for filename in os.listdir(DETERMINISTIC_REGISTRIES_DIR):
            if filename.endswith((".yaml", ".yml")):
                file_path = os.path.join(DETERMINISTIC_REGISTRIES_DIR, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        key = os.path.splitext(filename)[0]
                        facts[key] = yaml.safe_load(f)
                except Exception as e:
                    logger.error(f"Error reading YAML registry {filename}: {e}")

        return facts

    def retrieve_exact(self, request: ContextRequest, trace_id: str) -> EvidencePack:
        """
        Executes exact deterministic registry and PostgreSQL structured fact lookup.
        """
        facts = self.load_deterministic_registries()
        items: List[EvidenceItem] = []

        try:
            pg_conn = self.db_client.get_postgres_connection()
            cur = pg_conn.cursor()
            terms = [t.lower() for t in re.findall(r"\w+", request.query) if len(t) > 3]
            if terms:
                like_clause = " OR ".join(["LOWER(subject_entity) LIKE %s OR LOWER(object_entity) LIKE %s OR LOWER(relation_type) LIKE %s" for _ in terms])
                params = []
                for t in terms:
                    params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])

                query_sql = f"""
                    SELECT subject_entity, relation_type, object_entity, document_id, chunk_id, page_number, section
                    FROM knowledge_structured_facts
                    WHERE {like_clause}
                    LIMIT %s;
                """
                params.append(request.top_k)
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                for r in rows:
                    items.append(
                        EvidenceItem(
                            document_id=r[3],
                            source_id=r[3],
                            version="1.0",
                            section=r[6] or "Structured Facts",
                            chunk_id=r[4],
                            page=r[5],
                            text=f"Structured Fact: ({r[0]}) -[{r[1]}]-> ({r[2]})",
                            score=1.0,
                            authority="A"
                        )
                    )
            cur.close()
            pg_conn.close()
        except Exception as err:
            logger.warning(f"Exact PostgreSQL lookup error: {err}")

        return EvidencePack(
            query=request.query,
            knowledge_domain=request.knowledge_domain,
            retrieval_mode="exact",
            results=items,
            deterministic_facts=facts,
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve_graph_traversal(self, request: ContextRequest, trace_id: str) -> EvidencePack:
        """
        Executes live graph traversal across Neo4j Graph Database relationships.
        """
        items: List[EvidenceItem] = []
        matched_edges = []
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "neo4j_secret_password_2026"))
            with driver.session() as session:
                terms = [t.lower() for t in re.findall(r"\w+", request.query) if len(t) > 3]
                cypher = """
                MATCH (s:Entity)-[r]->(o:Entity)
                RETURN s.name AS subj, type(r) AS rel, o.name AS obj, r.document_id AS doc, r.page_number AS page, r.chunk_id AS chunk
                LIMIT 30
                """
                records = session.run(cypher).data()

                for rec in records:
                    s_name = str(rec["subj"])
                    r_type = str(rec["rel"])
                    o_name = str(rec["obj"])
                    is_match = any(t in s_name.lower() or t in o_name.lower() or t in r_type.lower() for t in terms)
                    if is_match or not items:
                        doc_id = rec.get("doc") or "NEO4J-GRAPH-IND-001"
                        chunk_id = rec.get("chunk") or f"GRAPH-EDGE-{len(items):04d}"
                        page_num = rec.get("page")

                        item = EvidenceItem(
                            document_id=doc_id,
                            source_id=doc_id,
                            version="1.0",
                            section="Neo4j Industrial Knowledge Graph",
                            chunk_id=chunk_id,
                            page=page_num,
                            text=f"Graph Edge: ({s_name}) -[:{r_type}]-> ({o_name})",
                            score=1.0 if is_match else 0.75,
                            authority="A",
                        )
                        items.append(item)
                        matched_edges.append({"source": s_name, "relationship": r_type, "target": o_name})

                        if len(items) >= request.top_k:
                            break
            driver.close()
        except Exception as e:
            logger.warning(f"Neo4j live graph traversal fallback: {e}")

        # Fallback to YAML if Neo4j returned no items
        if not items:
            facts = self.load_deterministic_registries()
            ontology = facts.get("ontology", {})
            edges = ontology.get("edges", [])
            q_lower = request.query.lower()
            yaml_matches = [
                e for e in edges
                if e["source"].lower() in q_lower or e["target"].lower() in q_lower or e["relationship"].lower() in q_lower
            ]
            for idx, edge in enumerate(yaml_matches or edges[:5]):
                edge_text = f"Ontology Relationship: {edge['source']} --[{edge['relationship']}]--> {edge['target']}"
                item = EvidenceItem(
                    document_id="ONTOLOGY-GRAPH-001",
                    source_id="ONTOLOGY-GRAPH-001",
                    version="1.0",
                    section="Platform Ontology Graph",
                    chunk_id=f"GRAPH-EDGE-{idx:04d}",
                    text=edge_text,
                    score=1.0 if edge in yaml_matches else 0.5,
                    authority="A",
                )
                items.append(item)

        return EvidencePack(
            query=request.query,
            knowledge_domain=request.knowledge_domain,
            retrieval_mode="graph_traversal",
            results=items,
            deterministic_facts={"ontology_matched_edges": matched_edges},
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve_semantic(self, request: ContextRequest, trace_id: str) -> EvidencePack:
        """
        Executes vector embedding similarity search against Qdrant collection 'platform_kb_embeddings'.
        """
        qdrant = self.db_client.get_qdrant_client()
        query_vector = self.embedder.embed_texts([request.query])[0]

        from qdrant_client import models

        # Build Qdrant domain and tenant/scope filter
        conditions = []
        if request.knowledge_domain != "all":
            conditions.append(
                models.FieldCondition(
                    key="knowledge_domain",
                    match=models.MatchValue(value=request.knowledge_domain),
                )
            )

        # Scoped Multi-Tenant Isolation
        if request.scope == "tenant" and request.tenant_id != "global":
            # Tenant org-level knowledge
            conditions.append(
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=request.tenant_id))
            )
        elif request.scope == "project" and request.project_id:
            # Project plant-level knowledge
            conditions.append(
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=request.tenant_id))
            )
            conditions.append(
                models.FieldCondition(key="project_id", match=models.MatchValue(value=request.project_id))
            )
        elif request.knowledge_domain == "tenant_knowledge" and request.tenant_id != "global":
            conditions.append(
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=request.tenant_id))
            )

        query_filter = models.Filter(must=conditions) if conditions else None

        search_results = []
        if hasattr(qdrant, "search"):
            try:
                res = qdrant.search(
                    collection_name=self.upserter.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=request.top_k * 2,
                    with_payload=True,
                )
                if isinstance(res, list):
                    search_results = res
            except Exception:
                pass

        if not search_results:
            try:
                from qdrant_client.http.models import SearchRequest
                search_req = SearchRequest(
                    vector=query_vector,
                    filter=query_filter,
                    limit=request.top_k * 2,
                    with_payload=True,
                )
                search_res = qdrant.http.search_api.search_points(
                    collection_name=self.upserter.collection_name,
                    search_request=search_req,
                )
                search_results = getattr(search_res, "result", []) or []
            except Exception:
                try:
                    res = qdrant.query_points(
                        collection_name=self.upserter.collection_name,
                        query=query_vector,
                        query_filter=query_filter,
                        limit=request.top_k * 2,
                        with_payload=True,
                    )
                    search_results = getattr(res, "points", res) or []
                except Exception as e:
                    logger.debug(f"[RetrievalService] Qdrant search fallback empty: {e}")
                    search_results = []

        items: List[EvidenceItem] = []
        for point in search_results:
            p = point.payload or {}
            authority = p.get("authority_level", "A")
            is_tenant = (
                p.get("knowledge_domain") == "tenant_knowledge"
                or (request.tenant_id != "global" and p.get("tenant_id") == request.tenant_id)
            )
            weight = _get_item_weight(authority, is_tenant_scoped=is_tenant)
            adjusted_score = min(1.0, float(point.score) * weight)

            if adjusted_score < request.min_score and len(items) >= request.top_k:
                continue

            item = EvidenceItem(
                document_id=p.get("document_id", "DOC-UNKNOWN"),
                source_id=p.get("source_id", p.get("document_id", "SRC-UNKNOWN")),
                version=p.get("version", "1.0"),
                section=p.get("section", "Overview"),
                chunk_id=p.get("chunk_id", str(point.id)),
                text=p.get("text", ""),
                score=round(adjusted_score, 4),
                authority=authority,
            )
            items.append(item)

        items.sort(key=lambda x: x.score, reverse=True)
        final_results = items[: request.top_k]

        deterministic_facts = self.load_deterministic_registries() if request.include_deterministic else {}

        return EvidencePack(
            query=request.query,
            knowledge_domain=request.knowledge_domain,
            retrieval_mode="semantic",
            results=final_results,
            deterministic_facts=deterministic_facts,
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve_keyword(self, request: ContextRequest, trace_id: str) -> EvidencePack:
        """
        Executes PostgreSQL trigram keyword similarity search (pg_trgm).
        """
        raw_results = self.store.search_chunks_keyword(
            query=request.query,
            top_k=request.top_k * 2,
            min_score=max(0.01, request.min_score / 3.0),
        )

        items: List[EvidenceItem] = []
        for r in raw_results:
            authority = r.get("authority_level", "A")
            is_tenant = (
                r.get("knowledge_domain") == "tenant_knowledge"
                or (request.tenant_id != "global" and r.get("tenant_id") == request.tenant_id)
            )
            weight = _get_item_weight(authority, is_tenant_scoped=is_tenant)
            adjusted_score = min(1.0, float(r["score"]) * weight)

            if adjusted_score < request.min_score and len(items) >= request.top_k:
                continue

            item = EvidenceItem(
                document_id=r.get("document_id", "DOC-UNKNOWN"),
                source_id=r.get("document_id", "SRC-UNKNOWN"),
                version="1.0",
                section=r.get("section", "Overview"),
                chunk_id=r.get("chunk_id", "CH-UNKNOWN"),
                text=r.get("text", ""),
                score=round(adjusted_score, 4),
                authority=authority,
            )
            items.append(item)

        items.sort(key=lambda x: x.score, reverse=True)
        final_results = items[: request.top_k]

        deterministic_facts = self.load_deterministic_registries() if request.include_deterministic else {}

        return EvidencePack(
            query=request.query,
            knowledge_domain=request.knowledge_domain,
            retrieval_mode="structured",
            results=final_results,
            deterministic_facts=deterministic_facts,
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve_hybrid(self, request: ContextRequest, trace_id: str, rrf_k: int = 60) -> EvidencePack:
        """
        Executes Reciprocal Rank Fusion (RRF) combining semantic (Qdrant) and keyword (PostgreSQL) search results.
        Formula: RRF_Score = 1.0 / (k + rank_semantic) + 1.0 / (k + rank_keyword)
        """
        # Execute both search paths with low min_score to gather candidates
        relaxed_request = request.model_copy(update={"min_score": 0.01, "top_k": request.top_k * 3})

        semantic_pack = self.retrieve_semantic(relaxed_request, trace_id=trace_id)
        keyword_pack = self.retrieve_keyword(relaxed_request, trace_id=trace_id)

        chunk_map: Dict[str, EvidenceItem] = {}
        rrf_scores: Dict[str, float] = {}

        # 1. Process semantic ranks
        for rank, item in enumerate(semantic_pack.results, start=1):
            chunk_map[item.chunk_id] = item
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (rrf_k + rank))

        # 2. Process keyword ranks
        for rank, item in enumerate(keyword_pack.results, start=1):
            if item.chunk_id not in chunk_map:
                chunk_map[item.chunk_id] = item
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (rrf_k + rank))

        # 3. Normalize RRF scores to 0.0 - 1.0 scale and create fused EvidenceItems
        max_rrf = (1.0 / (rrf_k + 1)) * 2.0  # Theoretical max when item is rank #1 in both
        fused_items: List[EvidenceItem] = []

        for chunk_id, raw_rrf in rrf_scores.items():
            base_item = chunk_map[chunk_id]
            norm_score = min(1.0, raw_rrf / max_rrf)
            is_tenant = (
                base_item.document_id.startswith("DOC-TENANT")
                or "tenant" in base_item.chunk_id.lower()
                or (request.tenant_id != "global" and request.tenant_id in base_item.document_id)
                or request.knowledge_domain == "tenant_knowledge"
            )
            weight = _get_item_weight(base_item.authority, is_tenant_scoped=is_tenant)
            final_score = round(min(1.0, norm_score * weight), 4)

            if final_score < request.min_score and len(fused_items) >= request.top_k:
                continue

            fused_item = base_item.model_copy(update={"score": final_score})
            fused_items.append(fused_item)

        fused_items.sort(key=lambda x: x.score, reverse=True)
        final_results = fused_items[: request.top_k]

        deterministic_facts = self.load_deterministic_registries() if request.include_deterministic else {}

        return EvidencePack(
            query=request.query,
            knowledge_domain=request.knowledge_domain,
            retrieval_mode="hybrid",
            results=final_results,
            deterministic_facts=deterministic_facts,
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve(
        self,
        request: ContextRequest,
        mode: Literal["exact", "semantic", "keyword", "hybrid", "graph_traversal"] = "hybrid",
    ) -> EvidencePack:
        """
        Main entry point for Knowledge Base Retrieval.
        Routes ContextRequest to requested mode, attaches trace_id, logs provenance event, and returns EvidencePack.
        """
        trace_id = f"trc_{uuid.uuid4().hex[:12]}"

        if mode == "exact":
            pack = self.retrieve_exact(request, trace_id=trace_id)
        elif mode == "semantic":
            pack = self.retrieve_semantic(request, trace_id=trace_id)
        elif mode == "keyword":
            pack = self.retrieve_keyword(request, trace_id=trace_id)
        elif mode == "hybrid":
            pack = self.retrieve_hybrid(request, trace_id=trace_id)
        elif mode == "graph_traversal":
            pack = self.retrieve_graph_traversal(request, trace_id=trace_id)
        else:
            raise ValueError(f"Unsupported retrieval mode: '{mode}'. Must be one of exact, semantic, keyword, hybrid, graph_traversal.")

        # Record provenance audit event
        self._log_provenance_event(request, pack)

        return pack
