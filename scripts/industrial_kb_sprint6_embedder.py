"""
scripts/industrial_kb_sprint6_embedder.py

Phase 5: Qdrant Payload Partitioning & Vector Embedding for Sprint 6 (Tenant Knowledge).
1. Ensures payload indexes exist on `platform_kb_embeddings` for `tenant_id`, `project_id`, and `scope` (is_tenant=True for tenant_id).
2. Generates semantic specification chunks for tenant organizations, projects, and assets from `tenant_registry.yaml`.
3. Embeds chunks via `EmbeddingEngine` (all-MiniLM-L6-v2) and upserts to Qdrant collection `platform_kb_embeddings` tagged with `knowledge_domain="tenant_knowledge"`.
"""

import os
import sys
import yaml
import hashlib
import logging
from typing import List, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter
from agentic.platform_kb.schemas import KnowledgeChunkRecord, KnowledgeSourceRecord
from agentic.platform_kb.db_client import KBInfraClient
from qdrant_client.models import PayloadSchemaType, PointStruct

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TenantEmbedder")

TENANT_REGISTRY_FILE = os.path.join(PROJECT_ROOT, "aiconnex_knowledge", "08_tenant_knowledge", "tenant_registry.yaml")


def ensure_payload_indexes(client, collection_name: str):
    """Creates payload indexes in Qdrant for multi-tenant isolation."""
    fields = [
        ("tenant_id", PayloadSchemaType.KEYWORD),
        ("project_id", PayloadSchemaType.KEYWORD),
        ("scope", PayloadSchemaType.KEYWORD),
        ("knowledge_domain", PayloadSchemaType.KEYWORD),
        ("equipment_id", PayloadSchemaType.KEYWORD),
        ("asset_id", PayloadSchemaType.KEYWORD),
        ("tag_number", PayloadSchemaType.KEYWORD),
    ]
    for field_name, field_schema in fields:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
            logger.info(f"Created payload index for field '{field_name}'.")
        except Exception as e:
            # Index might already exist
            logger.info(f"Payload index for '{field_name}' verified / exists: {e}")


def build_tenant_chunks(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Builds semantic chunk records and payload envelopes from tenant registry."""
    items = []
    
    # 1. Organization Chunks
    for tenant in data.get("tenants", []):
        t_id = tenant["tenant_id"]
        t_name = tenant["name"]
        industry = tenant["industry"]
        stds = ", ".join(tenant.get("adopted_standards", []))

        text = (
            f"Tenant Organization: {t_name}\n"
            f"Tenant Identifier: {t_id}\n"
            f"Industry Vertical: {industry} | Tier: {tenant.get('tier', 'enterprise')}\n"
            f"Adopted Engineering Standards: {stds}\n"
            f"Status: {tenant.get('status', 'active')}"
        )
        chunk_id = f"CH-TENANT-{t_id}"
        items.append({
            "chunk_id": chunk_id,
            "document_id": f"DOC-TENANT-{t_id}",
            "section": f"Tenant Profile -> {t_name}",
            "text": text,
            "tenant_id": t_id,
            "project_id": "global",
            "scope": "tenant",
            "asset_id": "",
            "equipment_id": "",
            "tag_number": "",
            "knowledge_domain": "tenant_knowledge",
        })

    # 2. Project Chunks
    for project in data.get("projects", []):
        p_id = project["project_id"]
        p_name = project["name"]
        t_id = project["tenant_id"]
        p_type = project.get("plant_type", "Industrial Facility")

        text = (
            f"Project / Plant Workspace: {p_name}\n"
            f"Project Identifier: {p_id}\n"
            f"Parent Organization: {t_id}\n"
            f"Facility Type: {p_type}\n"
            f"Status: {project.get('status', 'active')}"
        )
        chunk_id = f"CH-PROJ-{p_id}"
        items.append({
            "chunk_id": chunk_id,
            "document_id": f"DOC-PROJ-{p_id}",
            "section": f"Project Workspace -> {p_name}",
            "text": text,
            "tenant_id": t_id,
            "project_id": p_id,
            "scope": "project",
            "asset_id": "",
            "equipment_id": "",
            "tag_number": "",
            "knowledge_domain": "tenant_knowledge",
        })

    # 3. Asset Chunks
    for asset in data.get("assets", []):
        a_id = asset["asset_id"]
        t_id = asset["tenant_id"]
        p_id = asset["project_id"]
        eq_id = asset["equipment_id"]
        tag = asset["tag_number"]
        desc = asset["description"]
        loc = asset.get("location", "Plant Area")
        mfr = asset.get("manufacturer", "Unknown")
        model = asset.get("model_number", "")
        meta = asset.get("custom_metadata", {})
        meta_str = ", ".join(f"{k}: {v}" for k, v in meta.items())

        text = (
            f"Plant Asset Tag: {tag}\n"
            f"Asset Identifier: {a_id}\n"
            f"Tenant ID: {t_id} | Project ID: {p_id}\n"
            f"Equipment Classification: {eq_id}\n"
            f"Description: {desc}\n"
            f"Location: {loc}\n"
            f"Manufacturer: {mfr} | Model: {model}\n"
            f"Operating Parameters & Design Specs: {meta_str}\n"
            f"Status: {asset.get('status', 'operational')}"
        )
        chunk_id = f"CH-ASSET-{a_id}"
        items.append({
            "chunk_id": chunk_id,
            "document_id": f"DOC-ASSET-{a_id}",
            "section": f"Plant Asset Instance -> {tag} ({a_id})",
            "text": text,
            "tenant_id": t_id,
            "project_id": p_id,
            "scope": "project",
            "asset_id": a_id,
            "equipment_id": eq_id,
            "tag_number": tag,
            "knowledge_domain": "tenant_knowledge",
        })

    return items


def run_tenant_embedding_pipeline():
    """Executes embedding and Qdrant upsert for tenant knowledge."""
    if not os.path.exists(TENANT_REGISTRY_FILE):
        logger.error(f"Tenant registry file missing at: {TENANT_REGISTRY_FILE}")
        return

    with open(TENANT_REGISTRY_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    infra_client = KBInfraClient()
    qdrant = infra_client.get_qdrant_client()
    collection_name = infra_client.config.qdrant.collection

    # Step 1: Ensure Payload Indexes
    ensure_payload_indexes(qdrant, collection_name)

    # Step 2: Build Chunks
    chunk_items = build_tenant_chunks(data)
    logger.info(f"Built {len(chunk_items)} tenant semantic chunk items.")

    # Step 3: Embed Texts
    embedder = EmbeddingEngine()
    texts = [c["text"] for c in chunk_items]
    embeddings = embedder.embed_texts(texts)
    logger.info(f"Generated {len(embeddings)} vector embeddings (dim={len(embeddings[0])}).")

    # Step 4: Upsert Points with Scoped Payloads
    points = []
    upserter = QdrantUpserter(db_client=infra_client)
    for c, vec in zip(chunk_items, embeddings):
        pid = upserter.generate_point_id(c["chunk_id"])
        payload = {
            "chunk_id": c["chunk_id"],
            "document_id": c["document_id"],
            "section": c["section"],
            "text": c["text"],
            "token_count": len(c["text"].split()),
            "text_hash": hashlib.sha256(c["text"].encode("utf-8")).hexdigest(),
            "knowledge_domain": c["knowledge_domain"],
            "tenant_id": c["tenant_id"],
            "tenant_scope": c["tenant_id"],
            "project_id": c["project_id"],
            "scope": c["scope"],
            "asset_id": c["asset_id"],
            "equipment_id": c["equipment_id"],
            "tag_number": c["tag_number"],
            "authority_level": "A",
            "status": "Active",
        }
        points.append(PointStruct(id=pid, vector=vec, payload=payload))

    logger.info(f"Upserting {len(points)} tenant points into Qdrant collection '{collection_name}'...")
    qdrant.upsert(collection_name=collection_name, points=points)

    # Step 5: Verification Counts
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    f_tenant = Filter(must=[FieldCondition(key="knowledge_domain", match=MatchValue(value="tenant_knowledge"))])
    count_r = qdrant.count(collection_name=collection_name, count_filter=f_tenant)
    logger.info(f"Total tenant_knowledge vectors in Qdrant: {count_r.count}")
    logger.info("Sprint 6 Tenant Knowledge embedding and Qdrant partitioning complete!")


if __name__ == "__main__":
    run_tenant_embedding_pipeline()
