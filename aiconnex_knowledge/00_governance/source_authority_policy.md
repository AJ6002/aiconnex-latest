# Source Authority Policy

## Authority Grading Scale
- **Authority A (Primary / Official System Truth)**: Official platform architecture documents, validated Pydantic schemas, ISO/IEEE standards, official dataset papers. Highest retrieval priority ($1.0\times$ weight boost).
- **Authority B (Secondary / Reputable)**: External technical literature, scikit-learn/H2O docs, peer-reviewed engineering papers. Standard retrieval priority ($0.8\times$ weight boost).
- **Authority C (Inferred / Internal / Scout-Generated)**: Inferred dataset characteristics from Scout Agent runs, internal notes, unverified drafts. Requires explicit review or threshold filtering ($0.6\times$ weight boost).
