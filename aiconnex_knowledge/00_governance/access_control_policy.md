# Access Control Policy

## Access Interface Rules
- **Canonical Access Point**: AIConnex agents consume knowledge through `RetrievalService` via `ContextRequest` payloads emitting strongly-typed `EvidencePack` objects.
- **No Direct Query Bypasses**: Direct raw SQL queries against PostgreSQL `aiconnex_kb_prod` or raw vector queries against Qdrant `platform_kb_embeddings` by agents are strictly prohibited.
- **Audit Requirement**: All retrieval calls generate an immutable `EvidencePack` containing a unique `trace_id` logged to PostgreSQL `aiconnex_kb_prod` (`retrieval_audits`) and `13_provenance/retrieval_events.jsonl`.

## Agent RBAC & Domain Access Matrix

| Agent | Read Access Domains | Write Access | Scope Level |
|-------|--------------------|--------------|-------------|
| `ScoutAgent` | `platform`, `industrial`, `terminology`, `dataset`, `ml_methodology` | None (Read-only) | Tenant / Global |
| `PreUploadAgent` | `platform`, `terminology` | None (Read-only) | Tenant / Global |
| `WorkflowPlanner` | `platform`, `industrial`, `ml_methodology` | None (Read-only) | Tenant / Global |
| `PlatformAgent` | `platform`, `terminology`, `ml_methodology` | None (Read-only) | Tenant / Global |
| `MemoryAgent` | `platform`, `terminology` | Execution Lineage (`events.jsonl`) | Session / Workflow |
| `IngestionPipeline` | All Knowledge Domains | `aiconnex_kb_prod`, `platform_kb_embeddings`, `aiconnex-platform-kb-prod` | Global System |

## Tenant Isolation & Scoping
- Default access scope is `global`.
- Tenant-specific documents carry `tenant_scope = tenant_id`. Access without a matching valid `tenant_id` claim in `ContextRequest` is automatically rejected.

