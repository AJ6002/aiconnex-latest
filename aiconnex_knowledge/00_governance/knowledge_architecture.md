# Knowledge Architecture Policy

## Architecture Framework
The AIConnex Knowledge Base is partitioned into 5 functional knowledge domains:
1. **Platform Knowledge**: Capabilities, manifest contracts, node definitions, plugin specs.
2. **Industrial Domain Knowledge**: Telemetry semantics, SCADA ontologies, PHM standards.
3. **Business & Industrial Terminology**: Synonym maps, acronyms, canonical term definitions.
4. **Dataset Knowledge**: Dataset documentation, papers, and Scout Agent post-compile analysis.
5. **ML Methodology Knowledge**: Model properties, metrics, feature engineering rules.

## Access Routing
- **Deterministic**: Exact lookup of YAML/JSON registries via `aiconnex_agent/platform_kb/`.
- **Structured**: PostgreSQL catalog queries for lineage, versions, and entities.
- **Semantic**: Qdrant vector similarity search (`platform_kb_embeddings`).
