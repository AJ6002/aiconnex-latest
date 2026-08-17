# Ingestion Policy

## Gatekeeper Rule
No file or document may be ingested, parsed, chunked, or embedded without an active record in `01_source_register/source_register.csv` having `status = Approved`.

## Strict Production Mode Policy (`KB_STRICT_PRODUCTION_MODE`)
- The system operates under strict production enforcement (`KB_STRICT_PRODUCTION_MODE=true` by default).
- Prior to any ingestion or retrieval run, all three production infrastructure backends must pass live health-check handshakes:
  1. PostgreSQL (`aiconnex_kb_prod` with `pgvector` and `pg_trgm` extensions enabled).
  2. Qdrant Vector DB (`platform_kb_embeddings` collection, 384-dim Cosine).
  3. MinIO Object Storage (`aiconnex-platform-kb-prod` bucket).
- **No Mock Fallbacks**: Mock databases, SQLite fallbacks, or in-memory bypasses are strictly prohibited in production mode. Any missing or unreachable backend raises `CriticalDependencyError` and hard-halts ingestion immediately.

## Ingestion Pipeline Stages
1. **Source Check**: Verify `status == Approved` in Source Register.
2. **Raw Storage**: Upload original file to MinIO bucket `aiconnex-platform-kb-prod`.
3. **Normalization**: Extract section hierarchy, code blocks, and markdown tables.
4. **Chunking**: Section-aware chunking preserving parent section metadata.
5. **Embedding**: Generate vectors and upsert to Qdrant collection `platform_kb_embeddings`.
6. **Catalog Registration**: Register document and chunk metadata in PostgreSQL database `aiconnex_kb_prod`.

