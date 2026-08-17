"""
scripts/industrial_kb_phase1_governance.py

Phase 1 — Source Governance & Corpus Freeze for Industrial Domain KB.
Establishes exact source inventory, calculates document SHA256 checksums,
records authority levels & licenses, deduplicates archives, and generates
Phase 1 source register artifacts.
"""

import os
import json
import csv
import hashlib
from datetime import datetime, timezone

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_BASE_DIR = os.path.join(_PROJECT_ROOT, "knowledge", "Industrail_KB_raw_data")
REGISTER_DIR = os.path.join(_PROJECT_ROOT, "aiconnex_knowledge", "01_source_register")

# Master catalog metadata mapping
SOURCE_METADATA = [
    # --- 01 Ontologies ---
    {
        "source_id": "SRC-IND-ONT-001",
        "title": "Basic Formal Ontology 2020 (BFO 2020 - ISO/IEC 21838-2)",
        "knowledge_domain": "industrial",
        "source_type": "Formal Ontology (OWL/TTL)",
        "rel_path": r"01_ontologies_and_repositories\BFO-2020-master.zip",
        "authority_level": "A",
        "owner": "ISO/IEC & BFO Consortium",
        "tenant_scope": "global",
        "license": "BSD-3-Clause",
        "version": "2020",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-ONT-002",
        "title": "Basic Formal Ontology Legacy Repository (BFO Master)",
        "knowledge_domain": "industrial",
        "source_type": "Formal Ontology (OWL)",
        "rel_path": r"01_ontologies_and_repositories\BFO-master.zip",
        "authority_level": "B",
        "owner": "BFO Consortium",
        "tenant_scope": "global",
        "license": "BSD-3-Clause",
        "version": "1.1/2.0 Legacy",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-ONT-003",
        "title": "Circular Economy Ontology Catalogue (CEON)",
        "knowledge_domain": "industrial",
        "source_type": "Formal Ontology (RDF/TTL)",
        "rel_path": r"01_ontologies_and_repositories\Circular-Economy-Ontology-Catalogue-main.zip",
        "authority_level": "A",
        "owner": "CEON Project",
        "tenant_scope": "global",
        "license": "CC-BY-4.0",
        "version": "1.0",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-ONT-004",
        "title": "Industrial Ontology Foundry (IOF) Core & Maintenance Ontologies",
        "knowledge_domain": "industrial",
        "source_type": "Formal Ontology (RDF/OWL)",
        "rel_path": r"01_ontologies_and_repositories\IOF-ontology-master.zip",
        "authority_level": "A",
        "owner": "Industrial Ontology Foundry",
        "tenant_scope": "global",
        "license": "CC-BY-4.0",
        "version": "2024",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-ONT-005",
        "title": "ROMAIN Industrial Maintenance Ontology",
        "knowledge_domain": "industrial",
        "source_type": "Formal Ontology (OWL)",
        "rel_path": r"01_ontologies_and_repositories\ROMAIN-master.zip",
        "authority_level": "A",
        "owner": "ROMAIN Maintenance Group",
        "tenant_scope": "global",
        "license": "CC-BY-4.0",
        "version": "1.0",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    # Deprecated duplicates
    {
        "source_id": "SRC-IND-DEP-001",
        "title": "BFO-2020-master (1).zip (Duplicate Archive)",
        "knowledge_domain": "industrial",
        "source_type": "Archive Duplicate",
        "rel_path": r"01_ontologies_and_repositories\BFO-2020-master (1).zip",
        "authority_level": "C",
        "owner": "AIConnex System",
        "tenant_scope": "global",
        "license": "Internal",
        "version": "1.0",
        "status": "Deprecated",
        "rejection_reason": "Duplicate upload of BFO-2020-master.zip",
        "superseded_by": "SRC-IND-ONT-001"
    },
    {
        "source_id": "SRC-IND-DEP-002",
        "title": "IOF-ontology-master (1).zip (Duplicate Archive)",
        "knowledge_domain": "industrial",
        "source_type": "Archive Duplicate",
        "rel_path": r"01_ontologies_and_repositories\IOF-ontology-master (1).zip",
        "authority_level": "C",
        "owner": "AIConnex System",
        "tenant_scope": "global",
        "license": "Internal",
        "version": "1.0",
        "status": "Deprecated",
        "rejection_reason": "Duplicate upload of IOF-ontology-master.zip",
        "superseded_by": "SRC-IND-ONT-004"
    },

    # --- 02 Standards ---
    {
        "source_id": "SRC-IND-STD-001",
        "title": "IEC 60812:2018 Failure Modes and Effects Analysis (FMEA and FMECA)",
        "knowledge_domain": "industrial",
        "source_type": "International Standard",
        "rel_path": r"02_standards_and_guidelines\IEC_60812_2018_FMEA_FMECA.pdf",
        "authority_level": "A",
        "owner": "IEC / ISO",
        "tenant_scope": "global",
        "license": "IEC Copyright Standard",
        "version": "2018",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-STD-002",
        "title": "ISO 13379-1 Condition Monitoring and Diagnostics of Machines — General Guidelines",
        "knowledge_domain": "industrial",
        "source_type": "International Standard",
        "rel_path": r"02_standards_and_guidelines\ISO_13379_1_Data_Interpretation_Diagnostics.pdf",
        "authority_level": "A",
        "owner": "ISO",
        "tenant_scope": "global",
        "license": "ISO Copyright Standard",
        "version": "2012",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-STD-003",
        "title": "ISO 13381-1 Condition Monitoring and Diagnostics of Machines — Prognostics Part 1",
        "knowledge_domain": "industrial",
        "source_type": "International Standard",
        "rel_path": r"02_standards_and_guidelines\ISO_13381_1_Prognostics_RUL.pdf",
        "authority_level": "A",
        "owner": "ISO",
        "tenant_scope": "global",
        "license": "ISO Copyright Standard",
        "version": "2015",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-STD-004",
        "title": "ISO 14224:2016 Collection & Exchange of Reliability Data for Equipment",
        "knowledge_domain": "industrial",
        "source_type": "International Standard",
        "rel_path": r"02_standards_and_guidelines\ISO_14224_2016_Reliability_Data.pdf",
        "authority_level": "A",
        "owner": "ISO",
        "tenant_scope": "global",
        "license": "ISO Copyright Standard",
        "version": "2016",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-STD-005",
        "title": "ISO 55000:2024 Asset Management — Overview, Principles and Terminology",
        "knowledge_domain": "industrial",
        "source_type": "International Standard",
        "rel_path": r"02_standards_and_guidelines\ISO_55000_2024_Asset_Management.pdf",
        "authority_level": "A",
        "owner": "ISO",
        "tenant_scope": "global",
        "license": "ISO Copyright Standard",
        "version": "2024",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },

    # --- 03 NIST Frameworks ---
    {
        "source_id": "SRC-IND-NIST-001",
        "title": "NISTIR 8012 Standards for PHM in Manufacturing Applications",
        "knowledge_domain": "industrial",
        "source_type": "Federal Technical Report",
        "rel_path": r"03_nist_phm_frameworks\NISTIR_8012_PHM_Standards.pdf",
        "authority_level": "A",
        "owner": "NIST",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "2014",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NIST-002",
        "title": "NIST AMS 100-2 Measurement Science Roadmap for PHM in Manufacturing",
        "knowledge_domain": "industrial",
        "source_type": "Federal Roadmap Report",
        "rel_path": r"03_nist_phm_frameworks\NIST_AMS_100_2_PHM_Roadmap.pdf",
        "authority_level": "A",
        "owner": "NIST",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "2016",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NIST-003",
        "title": "NIST PHM Capabilities Review for Smart Manufacturing Systems",
        "knowledge_domain": "industrial",
        "source_type": "Federal Technical Report",
        "rel_path": r"03_nist_phm_frameworks\NIST_PHM_Capabilities_Review.pdf",
        "authority_level": "A",
        "owner": "NIST / NIH",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "2017",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NIST-004",
        "title": "NIST Standards and Techniques for PHM in Advanced Manufacturing",
        "knowledge_domain": "industrial",
        "source_type": "Federal Technical Report",
        "rel_path": r"03_nist_phm_frameworks\NIST_PHM_Manufacturing_Techniques.pdf",
        "authority_level": "A",
        "owner": "NIST",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "2020",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },

    # --- 04 NASA & PHM Reports ---
    {
        "source_id": "SRC-IND-NASA-001",
        "title": "NASA Technical Report 19740020847 Prognostics & System Reliability",
        "knowledge_domain": "industrial",
        "source_type": "NASA Technical Report",
        "rel_path": r"04_nasa_and_phm_technical_reports\NASA_TR_19740020847_Prognostics.pdf",
        "authority_level": "B",
        "owner": "NASA",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "1974",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NASA-002",
        "title": "NASA Technical Report 19970009840 Vibration Analysis and Machine Diagnostics",
        "knowledge_domain": "industrial",
        "source_type": "NASA Technical Report",
        "rel_path": r"04_nasa_and_phm_technical_reports\NASA_TR_19970009840_Vibration.pdf",
        "authority_level": "B",
        "owner": "NASA",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "1997",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NASA-003",
        "title": "NASA Technical Report 20100024368 C-MAPSS Turbofan Degradation Simulation",
        "knowledge_domain": "industrial",
        "source_type": "NASA Technical Report",
        "rel_path": r"04_nasa_and_phm_technical_reports\NASA_TR_20100024368_Propulsion_CMAPSS.pdf",
        "authority_level": "B",
        "owner": "NASA Ames Research Center",
        "tenant_scope": "global",
        "license": "US Public Domain",
        "version": "2010",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-NASA-004",
        "title": "Survey of Foundation Models for PHM & Industrial Diagnostics (2024)",
        "knowledge_domain": "industrial",
        "source_type": "Technical Literature Survey",
        "rel_path": r"04_nasa_and_phm_technical_reports\PHM_Foundation_Models_Survey_2024.pdf",
        "authority_level": "B",
        "owner": "arXiv / PHM Community",
        "tenant_scope": "global",
        "license": "Open Access (CC-BY-4.0)",
        "version": "2024",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },

    # --- 05 Research Papers ---
    {
        "source_id": "SRC-IND-PAPER-001",
        "title": "IOF Maintenance Working Group Modular Maintenance Ontology Paper",
        "knowledge_domain": "industrial",
        "source_type": "Peer-Reviewed Paper",
        "rel_path": r"05_ontology_research_papers\IOF_Maint_Modular_Ontology_Paper.pdf",
        "authority_level": "B",
        "owner": "IOF Maintenance WG",
        "tenant_scope": "global",
        "license": "Academic Open Access",
        "version": "2022",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-PAPER-002",
        "title": "Magnus et al. Unified Maintenance Data and Ontology Architecture",
        "knowledge_domain": "industrial",
        "source_type": "Peer-Reviewed Paper",
        "rel_path": r"05_ontology_research_papers\Magnus_Unified_Maintenance_Paper.pdf",
        "authority_level": "B",
        "owner": "Magnus et al.",
        "tenant_scope": "global",
        "license": "Academic Open Access",
        "version": "2024",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-PAPER-003",
        "title": "Polenghi et al. Knowledge Reuse for Asset Management & PHM",
        "knowledge_domain": "industrial",
        "source_type": "Peer-Reviewed Paper",
        "rel_path": r"05_ontology_research_papers\Polenghi_Knowledge_Reuse_Asset_Management.pdf",
        "authority_level": "B",
        "owner": "Polenghi et al.",
        "tenant_scope": "global",
        "license": "Academic Open Access",
        "version": "2023",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-PAPER-004",
        "title": "Semantic Interoperability in Industrial Maintenance-Related Systems",
        "knowledge_domain": "industrial",
        "source_type": "Peer-Reviewed Paper",
        "rel_path": r"05_ontology_research_papers\Semantic_Interoperability_Industrial_Maint.pdf",
        "authority_level": "B",
        "owner": "IFAC / IEEE",
        "tenant_scope": "global",
        "license": "Academic Open Access",
        "version": "2021",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },
    {
        "source_id": "SRC-IND-PAPER-005",
        "title": "Woods et al. (2023) An Ontology for Maintenance Activities & Data Quality",
        "knowledge_domain": "industrial",
        "source_type": "Peer-Reviewed Paper",
        "rel_path": r"05_ontology_research_papers\Woods_2023_Maintenance_Activity_Ontology.pdf",
        "authority_level": "B",
        "owner": "Woods et al. / Applied Ontology",
        "tenant_scope": "global",
        "license": "CC-BY-4.0",
        "version": "2023",
        "status": "Approved",
        "rejection_reason": None,
        "superseded_by": None
    },

    # --- 06 Rejected ---
    {
        "source_id": "SRC-IND-REJ-001",
        "title": "Generic Business Plan Template (Untracked)",
        "knowledge_domain": "industrial",
        "source_type": "Non-Technical Template",
        "rel_path": r"06_archive_and_untracked\business_plan_template.pdf",
        "authority_level": "C",
        "owner": "External",
        "tenant_scope": "global",
        "license": "Unknown",
        "version": "1.0",
        "status": "Rejected",
        "rejection_reason": "Out of scope — business plan template contains no PHM, ontology, or industrial engineering knowledge.",
        "superseded_by": None
    }
]


def calculate_sha256_and_size(file_path: str):
    """Computes exact size in bytes and SHA256 hex digest of a file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    size = os.path.getsize(file_path)
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return size, h.hexdigest()


def run_phase1_governance():
    print("=== Phase 1 — Source Governance & Corpus Freeze ===")
    
    records = []
    approved_records = []
    rejected_records = []
    deprecated_records = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for item in SOURCE_METADATA:
        full_path = os.path.join(RAW_BASE_DIR, item["rel_path"])
        size_bytes, sha256_hash = calculate_sha256_and_size(full_path)
        
        record = {
            "source_id": item["source_id"],
            "title": item["title"],
            "knowledge_domain": item["knowledge_domain"],
            "source_type": item["source_type"],
            "source_location": os.path.join("Industrail_KB_raw_data", item["rel_path"]).replace("\\", "/"),
            "authority_level": item["authority_level"],
            "owner": item["owner"],
            "tenant_scope": item["tenant_scope"],
            "license": item["license"],
            "version": item["version"],
            "status": item["status"],
            "size_bytes": size_bytes,
            "sha256_checksum": sha256_hash,
            "approved_at": now_iso if item["status"] == "Approved" else None,
            "rejection_reason": item["rejection_reason"],
            "superseded_by": item["superseded_by"]
        }
        
        records.append(record)
        
        if item["status"] == "Approved":
            approved_records.append(record)
        elif item["status"] == "Rejected":
            rejected_records.append(record)
        elif item["status"] == "Deprecated":
            deprecated_records.append(record)

    os.makedirs(REGISTER_DIR, exist_ok=True)

    # 1. Output industrial_source_register.json
    out_all_path = os.path.join(REGISTER_DIR, "industrial_source_register.json")
    with open(out_all_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"[OK] Wrote {len(records)} total records to: {out_all_path}")

    # 2. Output industrial_approved_sources.json
    out_app_path = os.path.join(REGISTER_DIR, "industrial_approved_sources.json")
    with open(out_app_path, "w", encoding="utf-8") as f:
        json.dump(approved_records, f, indent=2)
    print(f"[OK] Wrote {len(approved_records)} approved sources to: {out_app_path}")

    # 3. Output industrial_rejected_sources.json
    out_rej_path = os.path.join(REGISTER_DIR, "industrial_rejected_sources.json")
    with open(out_rej_path, "w", encoding="utf-8") as f:
        json.dump(rejected_records, f, indent=2)
    print(f"[OK] Wrote {len(rejected_records)} rejected sources to: {out_rej_path}")

    # 4. Output industrial_deprecated_sources.json
    out_dep_path = os.path.join(REGISTER_DIR, "industrial_deprecated_sources.json")
    with open(out_dep_path, "w", encoding="utf-8") as f:
        json.dump(deprecated_records, f, indent=2)
    print(f"[OK] Wrote {len(deprecated_records)} deprecated sources to: {out_dep_path}")

    # 5. Output raw data source_manifest.json
    manifest_data = {
        "title": "Industrial KB Raw Ingestion Manifest",
        "knowledge_domain": "industrial",
        "created_at": now_iso,
        "total_files_collected": len(records),
        "total_approved": len(approved_records),
        "total_rejected": len(rejected_records),
        "total_deprecated": len(deprecated_records),
        "approved_sources": [
            {
                "source_id": r["source_id"],
                "title": r["title"],
                "file_name": os.path.basename(r["source_location"]),
                "size_bytes": r["size_bytes"],
                "sha256": r["sha256_checksum"],
                "authority": r["authority_level"]
            }
            for r in approved_records
        ],
        "rejected_sources": [
            {
                "source_id": r["source_id"],
                "file_name": os.path.basename(r["source_location"]),
                "reason": r["rejection_reason"]
            }
            for r in rejected_records
        ],
        "deprecated_sources": [
            {
                "source_id": r["source_id"],
                "file_name": os.path.basename(r["source_location"]),
                "superseded_by": r["superseded_by"]
            }
            for r in deprecated_records
        ]
    }
    manifest_path = os.path.join(RAW_BASE_DIR, "source_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    print(f"[OK] Updated master manifest at: {manifest_path}")

    # 6. Update master source_register.csv & source_register.json for SourceRegisterManager integration
    csv_path = os.path.join(REGISTER_DIR, "source_register.csv")
    csv_headers = [
        "source_id", "title", "knowledge_domain", "source_type",
        "source_location", "authority_level", "owner", "tenant_scope",
        "license", "version", "status", "approved_at"
    ]
    
    # Read existing Platform KB rows if CSV exists
    existing_rows = []
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("knowledge_domain") != "industrial":
                    existing_rows.append(row)
                    
    # Append industrial approved records
    for r in approved_records:
        existing_rows.append({
            "source_id": r["source_id"],
            "title": r["title"],
            "knowledge_domain": r["knowledge_domain"],
            "source_type": r["source_type"],
            "source_location": r["source_location"],
            "authority_level": r["authority_level"],
            "owner": r["owner"],
            "tenant_scope": r["tenant_scope"],
            "license": r["license"],
            "version": r["version"],
            "status": r["status"],
            "approved_at": r["approved_at"]
        })

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(existing_rows)
    print(f"[OK] Updated master CSV source register at: {csv_path} (Total entries: {len(existing_rows)})")

    # Also rewrite master source_register.json
    master_json_path = os.path.join(REGISTER_DIR, "source_register.json")
    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(existing_rows, f, indent=2)
    print(f"[OK] Updated master JSON source register at: {master_json_path}")

    print("\nPhase 1 Governance Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase1_governance()
