"""
tests/test_agent_contracts.py - Unit Test Suite for 5-Stage Contract Pipeline Pydantic Models
================================================================-----------------------------
Verifies:
  1. Pre-Upload ConversationUnderstandingContract (CUC)
  2. ScoutEnrichedContract (During Upload)
  3. PreCompilerContract (Input to UnifiedCompiler)
  4 & 5. DatasetIntelligenceContract (DIC - NASA Example)
"""

import pytest
from agentic.schemas import (
    ConversationUnderstandingContract,
    ScoutEnrichedContract,
    UploadMetadata,
    ArchiveDiscovery,
    FileInventoryItem,
    ParserSelection,
    PreCompilerContract,
    CompilerRequest,
    DatasetIntelligenceContract,
    DatasetIdentity,
    CompiledDatasetSummary,
    DatasetStatistics,
    QualityReport,
    ProblemCandidate,
    BranchingHints,
)


def test_1_pre_upload_cuc():
    cuc = ConversationUnderstandingContract(
        conversation={"session_id": "sess_101", "timestamp": "2026-07-29T00:15:00Z"},
        goal={"raw_prompt": "Run RUL regression on turbofan data", "primary_intent": "train_rul"},
        observed={"mentioned_files": ["train_FD001.txt"], "mentioned_columns": ["unit_id", "cycle"]},
        inferred={"domain": "Aerospace / Turbofan Engine Prognostics", "expected_target": "RUL"},
        constraints={"missing_value_tolerance": 0.1},
        dataset_expectation={"expected_format": "zip", "multi_table": True},
        clarifications_required=["Should we calculate piecewise RUL limit?"],
        planning_hints={"recommended_agent": "ScoutAgent"},
    )
    data = cuc.model_dump() if hasattr(cuc, "model_dump") else cuc.dict()
    assert data["goal"]["primary_intent"] == "train_rul"
    assert data["inferred"]["expected_target"] == "RUL"
    assert len(data["clarifications_required"]) == 1


def test_2_scout_enriched_contract():
    cuc = ConversationUnderstandingContract(
        goal={"primary_intent": "train_rul"}
    )
    scout_contract = ScoutEnrichedContract(
        conversation_contract=cuc,
        upload=UploadMetadata(
            status="uploaded",
            upload_time="2026-07-29T00:15:30Z",
            archive_name="NASA_CMAPSS.zip",
            archive_type="zip",
            archive_size="12.4 MB",
            checksum="a1b2c3d4e5f6",
        ),
        archive_discovery=ArchiveDiscovery(
            root_structure=["CMAPSSData/"],
            files_detected=["CMAPSSData/train_FD001.txt", "CMAPSSData/test_FD001.txt", "CMAPSSData/RUL_FD001.txt"],
            directories=["CMAPSSData"],
            total_files=3,
        ),
        file_inventory=[
            FileInventoryItem(filename="CMAPSSData/train_FD001.txt", type="txt", role="fact_table", parser_candidate="text_delimited_autodetect_parser"),
            FileInventoryItem(filename="CMAPSSData/test_FD001.txt", type="txt", role="test_table", parser_candidate="text_delimited_autodetect_parser"),
        ],
        parser_selection=ParserSelection(
            selected_parsers=["text_delimited_autodetect_parser"],
            unsupported_files=[],
            confidence=0.98,
        ),
    )
    data = scout_contract.model_dump() if hasattr(scout_contract, "model_dump") else scout_contract.dict()
    assert data["upload"]["archive_name"] == "NASA_CMAPSS.zip"
    assert data["archive_discovery"]["total_files"] == 3
    assert len(data["file_inventory"]) == 2
    assert data["parser_selection"]["confidence"] == 0.98


def test_3_pre_compiler_contract():
    pre_compiler = PreCompilerContract(
        compiler_request=CompilerRequest(
            compile_mode="automatic",
            canonical_schema=True,
            generate_dataset_card=True,
            generate_statistics=True,
            infer_problem_candidates=True,
            infer_targets=True,
            generate_quality_report=True,
        )
    )
    data = pre_compiler.model_dump() if hasattr(pre_compiler, "model_dump") else pre_compiler.dict()
    assert data["compiler_request"]["compile_mode"] == "automatic"
    assert data["compiler_request"]["canonical_schema"] is True


def test_4_and_5_post_compiler_dic():
    dic = DatasetIntelligenceContract(
        dataset_identity=DatasetIdentity(
            name="NASA C-MAPSS",
            family="Aircraft Engine Prognostics",
            domain="Aerospace",
        ),
        compiled_dataset=CompiledDatasetSummary(
            tables=3,
            rows=20631,
            columns=26,
            combined_csv_path="data/compiled/all_groups_combined.csv",
        ),
        schema_map={
            "engine_id": "integer",
            "cycle": "integer",
            "setting_1": "float",
            "s2": "float",
        },
        statistics=DatasetStatistics(
            missing_values={"s1": 0, "s2": 0},
            duplicates=0,
            sampling="per_cycle",
        ),
        quality_report=QualityReport(
            constant_columns=["s1", "s5"],
            warnings=[],
            cartesian_guard_passed=True,
        ),
        derived_features=["rul_piecewise", "normalized_cycle", "health_label", "regime_cluster"],
        problem_candidates=[
            ProblemCandidate(family="Regression", confidence=0.94),
            ProblemCandidate(family="Anomaly", confidence=0.88),
            ProblemCandidate(family="Hybrid", confidence=0.81),
        ],
        target_candidates=["rul_piecewise"],
        branching_hints=BranchingHints(available_branches=["A1", "B1", "C1"]),
        clarifications_required=["Should separate models be built for each fault type?"],
    )
    data = dic.model_dump() if hasattr(dic, "model_dump") else dic.dict()
    assert data["dataset_identity"]["name"] == "NASA C-MAPSS"
    assert data["compiled_dataset"]["rows"] == 20631
    assert "rul_piecewise" in data["derived_features"]
    assert len(data["problem_candidates"]) == 3
    assert data["problem_candidates"][0]["family"] == "Regression"
    assert data["branching_hints"]["available_branches"] == ["A1", "B1", "C1"]
