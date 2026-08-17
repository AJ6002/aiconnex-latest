# Retention Policy

## Knowledge Storage Retention Rules

### 1. Document & Spec Storage
- **Platform Specs & Architecture**: Retained indefinitely in Git repository (`aiconnex_knowledge/02_platform/`) and MinIO object storage (`aiconnex-platform-kb-prod`).
- **Metadata & Catalog Records**: Retained indefinitely in PostgreSQL database `aiconnex_kb_prod` tables (`knowledge_documents`, `knowledge_chunks`, `knowledge_sources`).

### 2. Audit Lineage & Provenance Logs
- **Audit Lineage**: Stored in PostgreSQL `aiconnex_kb_prod` table `retrieval_audits` and `13_provenance/` JSONL logs.
- **Retention Window**: Active online retention threshold of **365 days**.
- **Archive Schedule**: Event logs older than 365 days are archived to `13_archive/` on a monthly maintenance cycle.

### 3. Vector Index Data
- **Active Vectors**: Retained in Qdrant collection `platform_kb_embeddings` for all document versions with `status = Active`.
- **Superseded Vectors**: When a document version transitions to `Superseded` or `Archived`, corresponding vector points are pruned from Qdrant to maintain search precision and storage efficiency.

### 4. Versioning & Lifecycle Limits
- **Max Historical Versions**: Maximum of **5 active historical versions** preserved per document before legacy versions transition to `Archived` status.
- **Scout Inferences**: Active for the duration of the dataset lifecycle; archived upon dataset deletion.

