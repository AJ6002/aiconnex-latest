# Knowledge Lifecycle Policy

## Document Lifecycle States
1. **Pending**: Registered in Source Register; awaiting human/automated review.
2. **Approved**: Verified for authority and relevance; ready for normalization and ingestion.
3. **Parsed / Normalized**: Transformed into structured AST JSON representation preserving section hierarchy.
4. **Chunked & Embedded**: Indexed into Qdrant vector database (`platform_kb_embeddings`).
5. **Active**: Live for retrieval by AIConnex agents.
6. **Superseded / Deprecated**: Retained for historical audit trails but excluded from default active retrieval.
7. **Archived**: Permanently stored in S3/MinIO cold storage.
