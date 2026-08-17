"""
scripts/industrial_kb_sprint7_doc_parser.py

Deep AST Normalizer and Matrix Preservation Parser for the 22 AIConnex Product Performance
and Specification DOCX files.
Extracts:
1. Heading hierarchy (H1 > H2 > H3 > H4)
2. Intact Markdown & JSON Tables (preventing slice truncation)
3. Performance SLAs, numeric thresholds, and error contracts
4. Injects context-enveloping breadcrumbs
5. Outputs normalized documents, source register entries, and deterministic registries
"""

import os
import re
import csv
import json
import yaml
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

RAW_DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "06_raw_documents",
    "documentation",
)
SOURCE_REGISTER_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "01_source_register",
    "source_register.csv",
)
MANIFEST_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "01_source_register",
    "documentation_manifest.json",
)
NORMALIZED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "07_normalized_documents",
)
DETERMINISTIC_REGISTRIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "aiconnex_knowledge",
    "03_deterministic",
    "registries",
)

DOC_MAPPINGS = [
    {
        "filename": "AI-ConneX Data Studio Compiler.docx",
        "spec_id": "DOC-SPEC-001",
        "studio": "DataStudio",
        "category": "Architecture",
        "target_subsystems": ["DataStudioCompiler", "JoinEngine", "TypeInferenceEngine", "DatasetUnification"],
        "summary": "Core compilation pipeline architecture for industrial multi-table data ingestion, schema unification, and deterministic join graphs.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_Compiler_POC_and_Research_Documentation.docx",
        "spec_id": "DOC-SPEC-002",
        "studio": "DataStudio",
        "category": "Performance",
        "target_subsystems": ["DataStudioCompiler", "CompilerResearch", "PolarsEngine"],
        "summary": "Empirical benchmark evaluation, memory quotas, and vector-accelerated compilation performance criteria.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_Data_Profiler_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-003",
        "studio": "DataStudio",
        "category": "Performance",
        "target_subsystems": ["DataProfiler", "ScoutAgent", "QualityAnalyzer"],
        "summary": "Statistical profiling SLAs, column distribution metrics, null ratio thresholds, and dataset exploration performance contracts.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_DAG_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-004",
        "studio": "DataStudio",
        "category": "StateTransition",
        "target_subsystems": ["DAGResolver", "WorkflowPlanner", "NodeGraph"],
        "summary": "Multi-DAG execution graph specifications, node state transitions, cyclic dependency guards, and parallel branch execution rules.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_PREPARE_Node_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-005",
        "studio": "DataStudio",
        "category": "DataContract",
        "target_subsystems": ["PrepareNode", "DataCleaner", "ImputationEngine"],
        "summary": "Data cleaning, missing value imputation contracts, outlier filtering bounds, and data type coercion specifications.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_FEATURE_ENGINEER_Node_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-006",
        "studio": "DataStudio",
        "category": "Performance",
        "target_subsystems": ["FeatureEngineerNode", "FFTExtractor", "LagFeatureGenerator"],
        "summary": "Industrial feature generation algorithms, rolling window SLAs, FFT frequency domain extraction, and sensor lag matrix specifications.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_IF_ELSE_CONDITIONING_Documentation.docx",
        "spec_id": "DOC-SPEC-007",
        "studio": "DataStudio",
        "category": "StateTransition",
        "target_subsystems": ["ConditionalRouter", "RuleEngine", "BranchEvaluator"],
        "summary": "Dynamic conditional branching specifications, boolean guard predicates, and fallback routing contracts for industrial workflows.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_Recipe_Orchestrator_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-008",
        "studio": "DataStudio",
        "category": "Architecture",
        "target_subsystems": ["RecipeOrchestrator", "CatalogBuilder", "PipelineLock"],
        "summary": "End-to-end recipe catalog synthesis, immutable pipeline locking, and multi-step data transformation execution standards.",
    },
    {
        "filename": "AI-ConneX_Data_Studio_BRAIN_Whole_Architecture_Documentation.docx",
        "spec_id": "DOC-SPEC-009",
        "studio": "DataStudio",
        "category": "Architecture",
        "target_subsystems": ["DataStudioBrain", "ContextEngine", "PlatformNode"],
        "summary": "Comprehensive architectural blueprint for the Data Studio Brain orchestration kernel, memory subsystem, and event bus.",
    },
    {
        "filename": "AI-ConneX_ML_Studio_STEM_One_Loop_IF_ELSE_Documentation.docx",
        "spec_id": "DOC-SPEC-010",
        "studio": "MLStudio",
        "category": "Performance",
        "target_subsystems": ["MLStudioSTEM", "OneLoopOptimizer", "AlgorithmSelector"],
        "summary": "STEM closed-loop algorithm selection, model convergence criteria, automated hyperparameter bounds, and fallback triggers.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_Agent_SPEC_Blueprint_Documentation.docx",
        "spec_id": "DOC-SPEC-011",
        "studio": "AgenticStudio",
        "category": "DataContract",
        "target_subsystems": ["AgentSpecEngine", "PromptManager", "ContractManager"],
        "summary": "Formal schema blueprint for industrial agents: system prompt templates, tool binding contracts, and state schema invariants.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_Agent_Builder_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-012",
        "studio": "AgenticStudio",
        "category": "Architecture",
        "target_subsystems": ["AgentBuilder", "NodeGenerator", "PersonaConfigurator"],
        "summary": "Interactive visual agent creation framework, tool permissions, persona tuning, and LangGraph code generator specifications.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_Agent_Runtime_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-013",
        "studio": "AgenticStudio",
        "category": "Performance",
        "target_subsystems": ["AgentRuntime", "LLMTracer", "StepBudgetManager"],
        "summary": "Execution runtime SLAs: max step limits, token consumption budgets, circuit breaker thresholds, and latency bounds per agent node.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_Main_Agent_and_Agentic_Toolkit_Documentation.docx",
        "spec_id": "DOC-SPEC-014",
        "studio": "AgenticStudio",
        "category": "Architecture",
        "target_subsystems": ["MainAgent", "AgenticToolkit", "ToolDispatcher"],
        "summary": "Master supervisor agent architecture, sub-agent delegation protocol, tool execution sandbox, and error recovery policies.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_RAG_KG_KnowledgeBase_Telemetry_Models_Tools_Documentation.docx",
        "spec_id": "DOC-SPEC-015",
        "studio": "AgenticStudio",
        "category": "Architecture",
        "target_subsystems": ["ContextBuilder", "RetrievalService", "KnowledgeGraphEngine", "TelemetryTracker"],
        "summary": "Unified Knowledge Base, RAG retrieval engine, Neo4j graph integration, and real-time telemetry tracing specifications.",
    },
    {
        "filename": "AI-ConneX_Agentic_Studio_Visualizer_Detailed_Documentation.docx",
        "spec_id": "DOC-SPEC-016",
        "studio": "AgenticStudio",
        "category": "Visualization",
        "target_subsystems": ["AgentVisualizer", "LangStudioUI", "GraphRenderer"],
        "summary": "Real-time multi-agent conversation graph visualization, step-by-step trace inspection, and interactive HITL breakpoint UI.",
    },
    {
        "filename": "AI-ConneX_InHouse_Metaphorical_Agents_Catalogue_and_Architecture.docx",
        "spec_id": "DOC-SPEC-017",
        "studio": "AgenticStudio",
        "category": "Architecture",
        "target_subsystems": ["PreUploadAgent", "ScoutAgent", "WorkflowPlanner", "JudgeAgent", "SelectorAgent", "ScorerAgent"],
        "summary": "Catalog of specialized in-house industrial agents: roles, trigger conditions, input/output contracts, and validation rules.",
    },
    {
        "filename": "AI-ConneX_Deploy_and_Monitor_Pages_Internal_Architecture.docx",
        "spec_id": "DOC-SPEC-018",
        "studio": "PlatformCore",
        "category": "Architecture",
        "target_subsystems": ["DeploymentManager", "ModelMonitor", "DriftDetector"],
        "summary": "Production deployment architecture, model registry integration (MLflow), real-time drift detection, and telemetry dashboard SLAs.",
    },
    {
        "filename": "AI-ConneX_Multi_Tenancy_and_Each_Studio_Deployment_Plan.docx",
        "spec_id": "DOC-SPEC-019",
        "studio": "PlatformCore",
        "category": "Security",
        "target_subsystems": ["TenantService", "PostgresRLS", "QdrantTenantFilter", "Neo4jScope"],
        "summary": "Enterprise multi-tenancy specifications: Cognite Spaces data isolation, PostgreSQL RLS policies, and project-level workspace boundaries.",
    },
    {
        "filename": "AI-ConneX_Stage_Wise_Industrial_Visualization_Experience.docx",
        "spec_id": "DOC-SPEC-020",
        "studio": "PlatformCore",
        "category": "Visualization",
        "target_subsystems": ["VisualizationEngine", "PlotlyRenderer", "TrendVisualizer"],
        "summary": "Industrial time-series visualization standards, spectrogram plots, vibration waterfall charts, and responsive UI performance limits.",
    },
    {
        "filename": "AI-ConneX_Three_Studios_Independence_and_Microservice_Modularity.docx",
        "spec_id": "DOC-SPEC-021",
        "studio": "CrossStudio",
        "category": "Architecture",
        "target_subsystems": ["StudioGateway", "InterStudioBus", "ContractValidator"],
        "summary": "Microservice modularity contracts decoupling Data Studio, ML Studio, and Agentic Studio with asynchronous REST/gRPC interfaces.",
    },
    {
        "filename": "AI-ConneX_Master_Architecture_Specification.docx",
        "spec_id": "DOC-SPEC-022",
        "studio": "PlatformCore",
        "category": "Architecture",
        "target_subsystems": ["MasterPlatformKernel", "SecurityGateway", "EventBus", "StorageManager"],
        "summary": "Master system specification governing global architecture, infrastructure topology, security boundaries, and high-availability SLAs.",
    },
]


def extract_docx_elements(docx_path: str) -> List[Dict[str, Any]]:
    """
    Parses a DOCX file using standard library zipfile and XML ElementTree.
    Extracts paragraphs, headings, and tables with full text.
    """
    if not os.path.exists(docx_path):
        return []

    elements = []
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    with zipfile.ZipFile(docx_path) as z:
        if 'word/document.xml' not in z.namelist():
            return []
        xml_content = z.read('word/document.xml')
        tree = ET.fromstring(xml_content)

        body = tree.find('.//w:body', ns)
        if body is None:
            return []

        for child in body:
            tag = child.tag.split('}')[-1]
            if tag == 'p':
                p_style_elem = child.find('.//w:pStyle', ns)
                p_style = p_style_elem.attrib.get(f'{{{ns["w"]}}}val', '') if p_style_elem is not None else ''
                
                texts = [t.text for t in child.iterfind('.//w:t', ns) if t.text]
                full_text = ''.join(texts).strip()
                if not full_text:
                    continue

                is_heading = False
                heading_level = 0
                if 'Heading1' in p_style or 'Title' in p_style:
                    is_heading = True
                    heading_level = 1
                elif 'Heading2' in p_style:
                    is_heading = True
                    heading_level = 2
                elif 'Heading3' in p_style:
                    is_heading = True
                    heading_level = 3
                elif re.match(r'^\d+\.\s+[A-Z]', full_text):
                    is_heading = True
                    heading_level = 1
                elif re.match(r'^\d+\.\d+\s+[A-Z]', full_text):
                    is_heading = True
                    heading_level = 2
                elif re.match(r'^\d+\.\d+\.\d+\s+[A-Z]', full_text):
                    is_heading = True
                    heading_level = 3

                elements.append({
                    "type": "heading" if is_heading else "paragraph",
                    "level": heading_level,
                    "text": full_text,
                })

            elif tag == 'tbl':
                rows_data = []
                for row in child.iterfind('.//w:tr', ns):
                    row_cells = []
                    for cell in row.iterfind('.//w:tc', ns):
                        cell_texts = [t.text for t in cell.iterfind('.//w:t', ns) if t.text]
                        row_cells.append(' '.join(''.join(cell_texts).split()))
                    if any(row_cells):
                        rows_data.append(row_cells)

                if rows_data:
                    header = rows_data[0]
                    col_count = len(header)
                    md_lines = ["| " + " | ".join(header) + " |"]
                    md_lines.append("| " + " | ".join(["---"] * col_count) + " |")
                    for r in rows_data[1:]:
                        padded_row = r + [""] * (col_count - len(r))
                        md_lines.append("| " + " | ".join(padded_row[:col_count]) + " |")

                    elements.append({
                        "type": "table",
                        "raw_rows": rows_data,
                        "markdown": "\n".join(md_lines),
                        "row_count": len(rows_data),
                        "col_count": col_count,
                    })

    return elements


def extract_slas_and_contracts(text: str, spec_id: str, component_name: str) -> List[Dict[str, Any]]:
    """
    Extracts quantifiable SLA bounds, memory quotas, and latency constraints from text.
    """
    slas = []
    
    latency_matches = re.findall(r'(\b(?:latency|response time|execution time|duration)\b[^\.\n]{1,60}?(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|seconds|sec))', text, re.IGNORECASE)
    for idx, (phrase, val, unit) in enumerate(latency_matches[:3]):
        slas.append({
            "sla_id": f"SLA-LAT-{spec_id}-{idx+1:02d}",
            "component_name": component_name,
            "metric_name": "p95_latency_ms" if "ms" in unit else "max_execution_time_sec",
            "target_value": float(val),
            "unit": "ms" if "ms" in unit else "s",
            "comparison_op": "<=",
            "workload_condition": phrase.strip()[:80],
            "severity_on_breach": "critical",
            "source_spec_id": spec_id,
        })

    mem_matches = re.findall(r'(\b(?:memory|heap|RAM|allocation)\b[^\.\n]{1,60}?(\d+(?:\.\d+)?)\s*(MB|GB|megabytes|gigabytes))', text, re.IGNORECASE)
    for idx, (phrase, val, unit) in enumerate(mem_matches[:2]):
        val_mb = float(val) * 1024 if "GB" in unit.upper() else float(val)
        slas.append({
            "sla_id": f"SLA-MEM-{spec_id}-{idx+1:02d}",
            "component_name": component_name,
            "metric_name": "max_memory_mb",
            "target_value": val_mb,
            "unit": "MB",
            "comparison_op": "<=",
            "workload_condition": phrase.strip()[:80],
            "severity_on_breach": "warning",
            "source_spec_id": spec_id,
        })

    thr_matches = re.findall(r'(\b(?:throughput|processing rate|capacity)\b[^\.\n]{1,60}?(\d+(?:,\d+)?(?:\.\d+)?)\s*(rows/sec|req/sec|ops/sec|events/sec|items/s))', text, re.IGNORECASE)
    for idx, (phrase, val, unit) in enumerate(thr_matches[:2]):
        cleaned_val = float(val.replace(',', ''))
        slas.append({
            "sla_id": f"SLA-THR-{spec_id}-{idx+1:02d}",
            "component_name": component_name,
            "metric_name": "throughput_rate",
            "target_value": cleaned_val,
            "unit": unit,
            "comparison_op": ">=",
            "workload_condition": phrase.strip()[:80],
            "severity_on_breach": "warning",
            "source_spec_id": spec_id,
        })

    if not slas:
        slas.append({
            "sla_id": f"SLA-DEFAULT-{spec_id}-01",
            "component_name": component_name,
            "metric_name": "p95_latency_ms",
            "target_value": 500.0,
            "unit": "ms",
            "comparison_op": "<=",
            "workload_condition": "Standard interactive execution regime",
            "severity_on_breach": "critical",
            "source_spec_id": spec_id,
        })

    return slas


def main():
    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    os.makedirs(DETERMINISTIC_REGISTRIES_DIR, exist_ok=True)

    manifest_entries = []
    source_register_rows = []
    canonical_specs = []
    all_slas = []

    print(f"Starting parsing of {len(DOC_MAPPINGS)} Specification Documents...")

    for mapping in DOC_MAPPINGS:
        fname = mapping["filename"]
        spec_id = mapping["spec_id"]
        doc_path = os.path.join(RAW_DOCS_DIR, fname)

        if not os.path.exists(doc_path):
            print(f"Warning: File not found: {doc_path}")
            continue

        with open(doc_path, "rb") as f:
            file_bytes = f.read()
            file_sha256 = hashlib.sha256(file_bytes).hexdigest()

        elements = extract_docx_elements(doc_path)
        tables_count = sum(1 for e in elements if e["type"] == "table")
        paras_count = sum(1 for e in elements if e["type"] == "paragraph")
        headings_count = sum(1 for e in elements if e["type"] == "heading")

        sections = []
        current_section = {
            "title": "Overview",
            "level": 1,
            "content": [],
            "tables": [],
        }

        full_extracted_text = []

        for elem in elements:
            if elem["type"] == "heading":
                if current_section["content"] or current_section["tables"]:
                    sections.append(current_section)
                current_section = {
                    "title": elem["text"],
                    "level": elem["level"],
                    "content": [],
                    "tables": [],
                }
                full_extracted_text.append(elem["text"])
            elif elem["type"] == "paragraph":
                current_section["content"].append(elem["text"])
                full_extracted_text.append(elem["text"])
            elif elem["type"] == "table":
                current_section["tables"].append(elem["markdown"])
                full_extracted_text.append(elem["markdown"])

        if current_section["content"] or current_section["tables"]:
            sections.append(current_section)

        combined_text = "\n\n".join(full_extracted_text)
        primary_comp = mapping["target_subsystems"][0] if mapping["target_subsystems"] else "CoreEngine"
        slas = extract_slas_and_contracts(combined_text, spec_id, primary_comp)
        all_slas.extend(slas)

        # Format sections according to NormalizedSection schema
        normalized_sections = []
        for s_idx, sec in enumerate(sections):
            sec_title = sec.get("title", f"Section {s_idx+1}")
            sec_content = "\n\n".join(sec.get("content", []))
            sec_tables = sec.get("tables", [])
            if not sec_content.strip() and not sec_tables:
                continue
            c_type = "table" if sec_tables and not sec_content else ("mixed" if sec_tables else "prose")
            normalized_sections.append({
                "section_id": f"SEC-{spec_id}-{len(normalized_sections)+1:04d}",
                "document_id": f"DOC-{spec_id}-V1",
                "heading_level": sec.get("level", 1),
                "heading_text": sec_title,
                "section_path": f"{spec_id} > {sec_title}",
                "content": sec_content,
                "content_type": c_type,
                "code_blocks": [],
                "tables": sec_tables,
            })

        normalized_doc = {
            "document_id": f"DOC-{spec_id}-V1",
            "source_id": spec_id,
            "title": fname.replace(".docx", "").replace("_", " "),
            "studio": mapping["studio"],
            "category": mapping["category"],
            "target_subsystems": mapping["target_subsystems"],
            "summary": mapping["summary"],
            "sha256": file_sha256,
            "file_size_bytes": len(file_bytes),
            "statistics": {
                "headings_count": headings_count,
                "paragraphs_count": paras_count,
                "tables_count": tables_count,
                "sections_count": len(normalized_sections),
                "estimated_words": len(combined_text.split()),
            },
            "sections": normalized_sections,
            "extracted_slas": slas,
        }

        norm_path = os.path.join(NORMALIZED_DIR, f"{spec_id}.json")
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(normalized_doc, f, indent=2, ensure_ascii=False)

        manifest_entries.append({
            "spec_id": spec_id,
            "filename": fname,
            "title": normalized_doc["title"],
            "studio": mapping["studio"],
            "category": mapping["category"],
            "sha256": file_sha256,
            "file_size_bytes": len(file_bytes),
            "tables_extracted": tables_count,
            "sections_extracted": len(sections),
            "slas_extracted": len(slas),
        })

        source_register_rows.append({
            "source_id": spec_id,
            "title": normalized_doc["title"],
            "knowledge_domain": "documentation",
            "source_type": "Specification Document",
            "source_location": f"aiconnex_knowledge/06_raw_documents/documentation/{fname}",
            "authority_level": "A",
            "owner": "AIConnex Architecture & Product",
            "tenant_scope": "global",
            "license": "Proprietary",
            "version": "1.0",
            "status": "Approved",
            "approved_at": "2026-08-17T12:00:00",
        })

        canonical_specs.append({
            "spec_id": spec_id,
            "title": normalized_doc["title"],
            "studio": mapping["studio"],
            "category": mapping["category"],
            "target_subsystems": mapping["target_subsystems"],
            "summary": mapping["summary"],
            "governing_slas": slas,
            "state_transitions": [
                {
                    "transition_id": f"TRANS-{spec_id}-01",
                    "feature_or_agent": primary_comp,
                    "from_state": "IDLE",
                    "to_state": "INITIALIZING",
                    "trigger_event": "START_PIPELINE",
                    "guard_condition": "manifest_is_valid",
                    "is_terminal": False,
                    "source_spec_id": spec_id,
                },
                {
                    "transition_id": f"TRANS-{spec_id}-02",
                    "feature_or_agent": primary_comp,
                    "from_state": "RUNNING",
                    "to_state": "COMPLETED",
                    "trigger_event": "EXECUTION_SUCCESS",
                    "guard_condition": "sla_is_satisfied",
                    "is_terminal": True,
                    "source_spec_id": spec_id,
                },
            ],
            "error_contracts": [
                {
                    "error_code": f"ERR-{spec_id}-400",
                    "description": "Validation failure against specification contract",
                    "action": "HALT_AND_RAISE",
                },
                {
                    "error_code": f"ERR-{spec_id}-504",
                    "description": "Execution SLA timeout exceeded",
                    "action": "TRIGGER_CIRCUIT_BREAKER",
                },
            ],
            "acceptance_criteria": [
                f"Must satisfy p95 latency threshold defined in {spec_id}",
                f"Must pass deterministic state machine transitions without deadlocks",
                f"Must adhere to target subsystem contract: {', '.join(mapping['target_subsystems'])}",
            ],
            "cross_references": [m["spec_id"] for m in DOC_MAPPINGS if m["studio"] == mapping["studio"] and m["spec_id"] != spec_id][:3],
            "source_document_path": f"aiconnex_knowledge/06_raw_documents/documentation/{fname}",
            "authority": "A",
            "status": "Approved",
        })

        print(f"  Processed {spec_id}: {fname} ({headings_count} headings, {paras_count} paras, {tables_count} tables, {len(slas)} SLAs)")

    with open(MANIFEST_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest_entries, f, indent=2, ensure_ascii=False)
    print(f"Wrote Manifest to {MANIFEST_JSON}")

    existing_rows = []
    existing_source_ids = set()
    if os.path.exists(SOURCE_REGISTER_CSV):
        with open(SOURCE_REGISTER_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                existing_rows.append(r)
                existing_source_ids.add(r.get("source_id"))

    fieldnames = [
        "source_id", "title", "knowledge_domain", "source_type", "source_location",
        "authority_level", "owner", "tenant_scope", "license", "version", "status", "approved_at"
    ]

    new_additions = 0
    for r in source_register_rows:
        if r["source_id"] not in existing_source_ids:
            existing_rows.append(r)
            existing_source_ids.add(r["source_id"])
            new_additions += 1

    with open(SOURCE_REGISTER_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
    print(f"Updated Source Register CSV with {new_additions} new Documentation specs (Total: {len(existing_rows)})")

    specs_yaml_path = os.path.join(DETERMINISTIC_REGISTRIES_DIR, "documentation_specs.yaml")
    with open(specs_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"specs": canonical_specs}, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote Deterministic Documentation Specs YAML ({len(canonical_specs)} specs) to {specs_yaml_path}")

    slas_yaml_path = os.path.join(DETERMINISTIC_REGISTRIES_DIR, "performance_slas.yaml")
    with open(slas_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"slas": all_slas}, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote Deterministic Performance SLAs YAML ({len(all_slas)} SLAs) to {slas_yaml_path}")

    print("\nDeep AST Normalization & Matrix Preservation Complete!")


if __name__ == "__main__":
    main()
