"""
scripts/industrial_kb_phase2_classification.py

Phase 2 — Knowledge Mechanism Classification for Industrial Domain KB.
Maps each approved source to its explicit knowledge ingestion mechanism:
- Deterministic Rules / Canonical System Truth
- Structured Entities, Attributes & Relations
- Knowledge Graph (Neo4j OWL / Entity Triples)
- Unstructured Document / RAG (Qdrant Semantic Embeddings)
"""

import os
import json

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGISTER_DIR = os.path.join(_PROJECT_ROOT, "aiconnex_knowledge", "01_source_register")
APPROVED_SOURCES_PATH = os.path.join(REGISTER_DIR, "industrial_approved_sources.json")
OUTPUT_MAPPING_PATH = os.path.join(REGISTER_DIR, "source_knowledge_mapping.json")

# Ingestion mechanism strategies for all 23 approved sources
CLASSIFICATION_STRATEGY = {
    # --- Formal Ontologies ---
    "SRC-IND-ONT-001": { # BFO 2020
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Supporting",
        "target_stores": ["Neo4j Graph (BFO Upper Taxonomy)", "PostgreSQL Relational Catalog", "Qdrant Vector Index (Supporting)"],
        "ingestion_role": "Upper ontology foundation for all industrial processes, spatial/temporal entities, and occurrents."
    },
    "SRC-IND-ONT-002": { # BFO Legacy
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Supporting",
        "target_stores": ["Neo4j Graph (BFO Legacy Classes)", "Qdrant Vector Index (Supporting)"],
        "ingestion_role": "Historical class hierarchy references and relation definitions."
    },
    "SRC-IND-ONT-003": { # CEON
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Supporting",
        "target_stores": ["Neo4j Graph (Circular Economy & Material Flows)", "Qdrant Vector Index (Supporting)"],
        "ingestion_role": "Circular economy, material composition, degradation, and asset lifecycle state ontology."
    },
    "SRC-IND-ONT-004": { # IOF
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Supporting",
        "target_stores": ["Neo4j Graph (Industrial Manufacturing Core & Maintenance)", "Qdrant Vector Index (Supporting)"],
        "ingestion_role": "Core manufacturing process, equipment, component, and maintenance activity ontology."
    },
    "SRC-IND-ONT-005": { # ROMAIN
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Supporting",
        "target_stores": ["Neo4j Graph (ROMAIN Maintenance Concepts)", "Qdrant Vector Index (Supporting)"],
        "ingestion_role": "Industrial maintenance activity taxonomy, failure modes, and repair action relations."
    },

    # --- Standards & Guidelines ---
    "SRC-IND-STD-001": { # IEC 60812 FMEA
        "deterministic": True, # Canonical FMEA methodology & risk matrix
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Primary",
        "target_stores": ["PostgreSQL Deterministic Rules", "Neo4j Graph (FMEA Failure-Effect Edges)", "Qdrant Vector Index"],
        "ingestion_role": "Standardized FMEA/FMECA procedure, failure mode effect relations, and criticality formulas."
    },
    "SRC-IND-STD-002": { # ISO 13379-1 Condition Monitoring
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Primary",
        "target_stores": ["Neo4j Graph (Diagnostic Feature Relations)", "Qdrant Vector Index"],
        "ingestion_role": "Machine condition monitoring, diagnostic descriptors, and symptom-to-fault mapping."
    },
    "SRC-IND-STD-003": { # ISO 13381-1 Prognostics RUL
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Primary",
        "target_stores": ["Neo4j Graph (Prognostic Model & Degradation Chains)", "Qdrant Vector Index"],
        "ingestion_role": "Remaining Useful Life (RUL) estimation principles, degradation trends, and confidence bounds."
    },
    "SRC-IND-STD-004": { # ISO 14224 Reliability Data
        "deterministic": True, # Equipment Taxonomy & Failure Codes are Canonical System Truth
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Primary",
        "target_stores": ["PostgreSQL Deterministic Taxonomy", "Neo4j Graph (Equipment Hierarchy)", "Qdrant Vector Index"],
        "ingestion_role": "Canonical equipment taxonomy (Plant->Unit->Equipment->Sub-system->Component) & standardized failure codes."
    },
    "SRC-IND-STD-005": { # ISO 55000 Asset Management
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Neo4j Graph (Asset Management Policy Nodes)", "Qdrant Vector Index"],
        "ingestion_role": "Asset management terminology, lifecycle cost principles, and governance concepts."
    },

    # --- NIST PHM Frameworks ---
    "SRC-IND-NIST-001": { # NISTIR 8012 PHM Standards
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index", "Neo4j Graph (Standards Interoperability Edges)"],
        "ingestion_role": "Manufacturing PHM standards synthesis, data exchange protocols, and architecture guidelines."
    },
    "SRC-IND-NIST-002": { # NIST AMS 100-2 PHM Roadmap
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Measurement science roadmap, sensor placement strategies, and PHM capability levels."
    },
    "SRC-IND-NIST-003": { # NIST PHM Capabilities Review
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Smart manufacturing PHM capabilities, verification metrics, and deployment patterns."
    },
    "SRC-IND-NIST-004": { # NIST PHM Manufacturing Techniques
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Manufacturing degradation tracking techniques, feature extraction algorithms, and case studies."
    },

    # --- NASA Reports ---
    "SRC-IND-NASA-001": { # NASA TR 19740020847 Prognostics
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Foundational NASA aerospace prognostics algorithms, reliability statistics, and failure theory."
    },
    "SRC-IND-NASA-002": { # NASA TR 19970009840 Vibration Analysis
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Vibration signal diagnostics, bearing/gear failure frequency formulas, and spectral signatures."
    },
    "SRC-IND-NASA-003": { # NASA TR 20100024368 CMAPSS Simulation
        "deterministic": False,
        "structured": "Primary",
        "knowledge_graph": "Primary",
        "document_rag": "Primary",
        "target_stores": ["PostgreSQL Contract Store (C-MAPSS Dataset Spec)", "Neo4j Graph (Turbofan Component Graph)", "Qdrant Vector Index"],
        "ingestion_role": "C-MAPSS turbofan engine degradation dataset specification, operating condition regimes, and sensor descriptions."
    },
    "SRC-IND-NASA-004": { # PHM Foundation Models Survey 2024
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Modern deep learning & foundation model architectures for industrial time-series & diagnostics."
    },

    # --- Research Papers ---
    "SRC-IND-PAPER-001": { # IOF Modular Maintenance Paper
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Modular maintenance ontology architecture design, BFO alignment rules, and usage examples."
    },
    "SRC-IND-PAPER-002": { # Magnus Unified Maintenance Paper
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Unified maintenance data models, industrial IoT schema integration, and ontology interoperability."
    },
    "SRC-IND-PAPER-003": { # Polenghi Knowledge Reuse Asset Management
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Knowledge reuse methodologies, asset management decision support, and PHM integration."
    },
    "SRC-IND-PAPER-004": { # Semantic Interoperability Industrial Maintenance
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Semantic interoperability frameworks, industrial standards mapping, and middleware patterns."
    },
    "SRC-IND-PAPER-005": { # Woods 2023 Maintenance Activity Ontology
        "deterministic": False,
        "structured": "Supporting",
        "knowledge_graph": "Supporting",
        "document_rag": "Primary",
        "target_stores": ["Qdrant Vector Index"],
        "ingestion_role": "Maintenance activity breakdown, data quality assessment metrics, and work order ontology."
    }
}


def run_phase2_classification():
    print("=== Phase 2 — Knowledge Mechanism Classification ===")
    
    if not os.path.exists(APPROVED_SOURCES_PATH):
        raise FileNotFoundError(f"Approved sources file not found: {APPROVED_SOURCES_PATH}")

    with open(APPROVED_SOURCES_PATH, "r", encoding="utf-8") as f:
        approved_sources = json.load(f)

    print(f"Loaded {len(approved_sources)} approved industrial sources for classification.")

    mappings = []
    summary_counts = {
        "deterministic_sources": 0,
        "structured_primary": 0,
        "structured_supporting": 0,
        "knowledge_graph_primary": 0,
        "knowledge_graph_supporting": 0,
        "document_rag_primary": 0,
        "document_rag_supporting": 0
    }

    for source in approved_sources:
        sid = source["source_id"]
        if sid not in CLASSIFICATION_STRATEGY:
            raise KeyError(f"Source ID '{sid}' missing from Phase 2 classification strategy!")
            
        strat = CLASSIFICATION_STRATEGY[sid]
        
        mapping_record = {
            "source_id": sid,
            "title": source["title"],
            "authority_level": source["authority_level"],
            "knowledge_domain": source["knowledge_domain"],
            "ingestion_strategy": {
                "deterministic": strat["deterministic"],
                "structured": strat["structured"],
                "knowledge_graph": strat["knowledge_graph"],
                "document_rag": strat["document_rag"]
            },
            "target_stores": strat["target_stores"],
            "ingestion_role": strat["ingestion_role"]
        }
        mappings.append(mapping_record)

        if strat["deterministic"]:
            summary_counts["deterministic_sources"] += 1
        if strat["structured"] == "Primary":
            summary_counts["structured_primary"] += 1
        elif strat["structured"] == "Supporting":
            summary_counts["structured_supporting"] += 1
            
        if strat["knowledge_graph"] == "Primary":
            summary_counts["knowledge_graph_primary"] += 1
        elif strat["knowledge_graph"] == "Supporting":
            summary_counts["knowledge_graph_supporting"] += 1

        if strat["document_rag"] == "Primary":
            summary_counts["document_rag_primary"] += 1
        elif strat["document_rag"] == "Supporting":
            summary_counts["document_rag_supporting"] += 1

    # Save output mapping
    with open(OUTPUT_MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "title": "Industrial KB Source Knowledge Mechanism Mapping",
            "total_mapped_sources": len(mappings),
            "summary": summary_counts,
            "mappings": mappings
        }, f, indent=2)

    print(f"[OK] Wrote source knowledge mapping to: {OUTPUT_MAPPING_PATH}")
    print("\nSummary Distribution across Knowledge Mechanisms:")
    print(f"  - Deterministic System Truth: {summary_counts['deterministic_sources']} sources (ISO 14224, IEC 60812)")
    print(f"  - Structured Entities Primary: {summary_counts['structured_primary']} sources | Supporting: {summary_counts['structured_supporting']} sources")
    print(f"  - Knowledge Graph (Neo4j) Primary: {summary_counts['knowledge_graph_primary']} sources | Supporting: {summary_counts['knowledge_graph_supporting']} sources")
    print(f"  - Document / RAG (Qdrant) Primary: {summary_counts['document_rag_primary']} sources | Supporting: {summary_counts['document_rag_supporting']} sources")
    print("\nPhase 2 Classification Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase2_classification()
