# AIConnex Knowledge Governance — Overview & Architecture

## Overview
This directory governs the lifecycle, authority, retention, versioning, access control, and tenant isolation policies for the AIConnex Knowledge Base (KB).

## Key Principles
1. **Source Register Gatekeeper**: Nothing enters the KB without passing through the `01_source_register/` approval workflow (`status = Approved`).
2. **Deterministic Provenance**: Every retrieved fact is wrapped in an `EvidencePack` citing document ID, version, section, page, and chunk.
3. **Three-Tier Storage Strategy**: Exact rules in YAML/JSON, relational catalog in PostgreSQL, dense semantic search in Qdrant.
