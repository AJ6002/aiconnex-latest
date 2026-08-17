# Tenant Isolation Policy

## Design Resolution
- In V1 target tree, tenant is **omitted as a top-level directory tier** to avoid directory explosion.
- Tenant isolation is strictly enforced via **metadata filtering** (`tenant_scope` field in Source Register, PostgreSQL metadata queries, and Qdrant payload filters).
- `tenant_scope = 'global'` indicates platform-wide shared knowledge accessible by all tenants.
