"""
test_intelligence_layer.py - Tests for the LLM-Driven Intelligence Layer
=======================================================================
Covers:
  - Deterministic stages (1, 2, 4) work with no LLM at all
  - LLM stages (3, 5, 6, 7) work against a mocked LLMClient
  - LLM hallucination guards reject unknown tables/columns/plugins
  - Dynamic HITL options replace the hardcoded menu
  - per_partition_batch emits one job directory per partition
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest

from services.aiconnex_zip_compiler.batch_writer import export_partition_batch
from services.aiconnex_zip_compiler.intelligence import (
    ArchiveExplorer,
    FormatDetector,
    MetadataExtractor,
    ParserAdvisor,
    ProblemDiscoverer,
    SchemaAnalyzer,
    SemanticAnalyzer,
)
if SemanticAnalyzer is None or ParserAdvisor is None:
    pytest.skip("Scout compiler LLM intelligence modules not present on this branch", allow_module_level=True)

try:
    from services.aiconnex_zip_compiler.intelligence.llm_client import LLMResponse

except ImportError:
    class LLMResponse:  # type: ignore
        def __init__(self, data=None, model_used="", raw_text="", duration_seconds=0.0):
            self.data = data
            self.model_used = model_used
            self.raw_text = raw_text
            self.duration_seconds = duration_seconds

from services.aiconnex_zip_compiler.intelligence.models import (
    IntelligenceReport,
    TableMetadata,
)



# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """Returns canned JSON payloads keyed by a marker in the system prompt."""

    def __init__(self, responses: Dict[str, Dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: List[str] = []

    def is_available(self, force_recheck: bool = False) -> bool:
        return True

    def complete_json(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        for marker, payload in self.responses.items():
            if marker.lower() in system_prompt.lower():
                self.calls.append(marker)
                return LLMResponse(
                    data=payload,
                    model_used="mock-model",
                    raw_text=json.dumps(payload),
                    duration_seconds=0.01,
                )
        raise AssertionError(f"MockLLM had no response for prompt: {system_prompt[:80]}")


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "unit_id": [1, 1, 1, 2, 2, 2],
        "cycle": [1, 2, 3, 1, 2, 3],
        "PT01": [4.1, 4.3, 4.6, 4.0, 4.2, 4.5],
        "TT01": [310.5, 311.2, 312.8, 309.9, 310.4, 311.9],
        "plant_tag": ["A", "A", "A", "A", "A", "A"],
    })


# ---------------------------------------------------------------------------
# Deterministic stages
# ---------------------------------------------------------------------------

def test_archive_explorer_unpacks_nested_archives(tmp_path):
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("deep_data.csv", "a,b\n1,2\n3,4\n")

    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, "nested/inner.zip")
        zf.writestr("top.csv", "x,y\n5,6\n7,8\n")

    tree = ArchiveExplorer().explore(outer, tmp_path / "extracted")

    paths = [n.relative_path for n in tree.nodes]
    assert tree.nested_archive_count == 1
    assert any("deep_data.csv" in p for p in paths), f"nested file not found in {paths}"
    assert any("top.csv" in p for p in paths)


def test_format_detector_identifies_formats_without_llm(tmp_path):
    (tmp_path / "table.csv").write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    (tmp_path / "matrix.txt").write_text("1 2 3\n4 5 6\n7 8 9\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Just prose, with one comma.\n", encoding="utf-8")

    tree = ArchiveExplorer().explore(tmp_path, tmp_path / "extract")
    fingerprints = FormatDetector(llm_client=None).detect(tree.nodes)
    by_name = {Path(f.relative_path).name: f.detected_format for f in fingerprints}

    assert by_name["table.csv"] == "csv"
    assert by_name["matrix.txt"] == "whitespace_delimited_text"
    assert by_name["notes.txt"] == "plain_text"


def test_metadata_extractor_computes_real_statistics(sample_df):
    metadata = MetadataExtractor().extract_table("sensors", sample_df)
    by_name = {c.name: c for c in metadata.columns}

    assert metadata.row_count == 6
    assert metadata.column_count == 5

    # Entity key: repeats, low cardinality
    assert by_name["unit_id"].inferred_dtype == "numeric_int"
    assert by_name["unit_id"].cardinality_ratio < 0.5

    # Continuous measurement: high cardinality
    assert by_name["PT01"].inferred_dtype == "numeric_float"
    assert by_name["PT01"].cardinality_ratio == 1.0

    # Constant column detected
    assert by_name["plant_tag"].is_constant is True


# ---------------------------------------------------------------------------
# LLM stages with mocked client
# ---------------------------------------------------------------------------

def test_schema_analyzer_assigns_roles_from_stats(sample_df):
    metadata = [MetadataExtractor().extract_table("sensors", sample_df)]

    mock = MockLLM({
        "data schema analyst": {
            "tables": [{
                "table_name": "sensors",
                "table_role": "fact",
                "grain_description": "one row per unit per cycle",
                "entity_key_columns": ["unit_id"],
                "time_index_columns": ["cycle"],
                "candidate_target_columns": [],
                "feature_columns": ["PT01", "TT01"],
                "metadata_columns": ["plant_tag"],
                "confidence": 0.92,
                "reasoning": "unit_id repeats with low cardinality; cycle increments within unit.",
            }]
        },
        "relational data architect": {"relationships": []},
    })

    roles, relationships = SchemaAnalyzer(mock).analyze(metadata)

    assert len(roles) == 1
    assert roles[0].entity_key_columns == ["unit_id"]
    assert roles[0].time_index_columns == ["cycle"]
    assert roles[0].table_role == "fact"


def test_schema_analyzer_rejects_hallucinated_columns(sample_df):
    metadata = [MetadataExtractor().extract_table("sensors", sample_df)]

    mock = MockLLM({
        "data schema analyst": {
            "tables": [{
                "table_name": "sensors",
                "table_role": "fact",
                "entity_key_columns": ["unit_id", "column_that_does_not_exist"],
                "time_index_columns": ["cycle"],
                "candidate_target_columns": [],
                "feature_columns": ["PT01", "TT01"],
                "metadata_columns": ["plant_tag"],
                "confidence": 0.9,
                "reasoning": "test",
            }]
        },
        "relational data architect": {"relationships": []},
    })

    roles, _ = SchemaAnalyzer(mock).analyze(metadata)
    assert roles[0].entity_key_columns == ["unit_id"], "hallucinated column must be dropped"


def test_semantic_analyzer_decodes_instrument_tags(sample_df):
    metadata = [MetadataExtractor().extract_table("sensors", sample_df)]

    mock = MockLLM({
        "instrumentation": {
            "labels": [
                {
                    "table_name": "sensors",
                    "column_name": "PT01",
                    "semantic_name": "Pressure Transmitter 01",
                    "measurement_type": "pressure",
                    "unit_guess": "bar",
                    "equipment_context": "compressor suction",
                    "confidence": 0.9,
                    "reasoning": "PT prefix is ISA-5.1 pressure transmitter; range 4-4.6 fits bar.",
                },
                {
                    "table_name": "sensors",
                    "column_name": "TT01",
                    "semantic_name": "Temperature Transmitter 01",
                    "measurement_type": "temperature",
                    "unit_guess": "degC",
                    "equipment_context": "compressor discharge",
                    "confidence": 0.9,
                    "reasoning": "TT prefix indicates temperature transmitter.",
                },
            ]
        }
    })

    labels = SemanticAnalyzer(mock).analyze(metadata)
    by_column = {label.column_name: label for label in labels}

    assert by_column["PT01"].measurement_type == "pressure"
    assert by_column["PT01"].unit_guess == "bar"
    assert by_column["TT01"].measurement_type == "temperature"


def test_problem_discoverer_generates_dynamic_options(sample_df):
    metadata = [MetadataExtractor().extract_table("sensors_fd001", sample_df)]

    mock = MockLLM({
        "ml solutions architect": {
            "domain": "gas compressor condition monitoring",
            "domain_confidence": 0.88,
            "dataset_purpose": "Track compressor degradation across operating regimes.",
            "structural_shape": "One table per operating condition.",
            "partition_dimension_name": "operating condition",
            "detected_partitions": [{
                "group_id": "FD001",
                "group_label": "Operating condition FD001",
                "member_tables": ["sensors_fd001"],
                "partition_dimension": "operating condition",
            }],
            "question_for_user": "What do you want this model to tell you about your compressor?",
            "intent_options": [
                {
                    "option_id": "predict_failure_combined",
                    "label": "Predict when the equipment will fail",
                    "description": "One model covering all operating conditions.",
                    "is_recommended": True,
                    "output_mode": "single_merged",
                    "merge_strategy": "vertical_stack",
                    "tables_to_include": [],
                    "tables_to_exclude": [],
                    "partition_by": None,
                    "target_column": None,
                    "target_synthesis": "Countdown of remaining cycles per unit.",
                },
                {
                    "option_id": "predict_failure_per_condition",
                    "label": "Build a separate model for each operating condition",
                    "description": "Specialised models when regimes behave differently.",
                    "is_recommended": False,
                    "output_mode": "per_partition_batch",
                    "merge_strategy": "none",
                    "tables_to_include": [],
                    "tables_to_exclude": [],
                    "partition_by": "operating condition",
                    "target_column": None,
                    "target_synthesis": None,
                },
            ],
            "reasoning": "Multiple operating conditions detected.",
        }
    })

    hypothesis = ProblemDiscoverer(mock).discover(None, metadata, [], [], [])

    assert hypothesis is not None
    assert hypothesis.domain == "gas compressor condition monitoring"
    assert "compressor" in hypothesis.question_for_user.lower()
    assert len(hypothesis.intent_options) == 2

    modes = {o.output_mode for o in hypothesis.intent_options}
    assert "single_merged" in modes
    assert "per_partition_batch" in modes

    # Exactly one recommended option
    assert sum(1 for o in hypothesis.intent_options if o.is_recommended) == 1


def test_problem_discoverer_option_ids_are_stable_across_llm_wording_changes(sample_df):
    """
    The LLM phrases the same underlying choice differently between calls (this
    happened in practice: 'per_partition_models' vs
    'per_partition_anomaly_detection' for the identical dataset). option_id
    must be derived from the STRUCTURAL fields (output_mode, merge_strategy,
    target_column), not from the LLM's free-text id or label, so automation
    scripts using --strategy <id> keep working across runs.
    """
    metadata = [MetadataExtractor().extract_table("sensors_fd001", sample_df)]

    def make_response(label_a: str, label_b: str) -> Dict[str, Any]:
        return {
            "ml solutions architect": {
                "domain": "gas compressor condition monitoring",
                "domain_confidence": 0.88,
                "dataset_purpose": "test",
                "structural_shape": "test",
                "partition_dimension_name": "operating condition",
                "detected_partitions": [],
                "question_for_user": "What do you want?",
                "intent_options": [
                    {
                        # Note: NO option_id field - the LLM no longer supplies one.
                        "label": label_a,
                        "description": "One model for everything.",
                        "is_recommended": True,
                        "output_mode": "single_merged",
                        "merge_strategy": "vertical_stack",
                        "tables_to_include": [],
                        "tables_to_exclude": [],
                        "partition_by": None,
                        "target_column": None,
                        "target_synthesis": None,
                    },
                    {
                        "label": label_b,
                        "description": "Separate models per condition.",
                        "is_recommended": False,
                        "output_mode": "per_partition_batch",
                        "merge_strategy": "none",
                        "tables_to_include": [],
                        "tables_to_exclude": [],
                        "partition_by": "operating condition",
                        "target_column": None,
                        "target_synthesis": None,
                    },
                ],
                "reasoning": "test",
            }
        }

    # Two "runs" where the LLM invents completely different wording for the
    # identical structural choices.
    mock_run_1 = MockLLM(make_response(
        "Predict overall failure risk", "Build a model per fault mode"
    ))
    mock_run_2 = MockLLM(make_response(
        "Detect anomalies across everything", "Separate anomaly detectors per condition"
    ))

    hypothesis_1 = ProblemDiscoverer(mock_run_1).discover(None, metadata, [], [], [])
    hypothesis_2 = ProblemDiscoverer(mock_run_2).discover(None, metadata, [], [], [])

    ids_1 = sorted(o.option_id for o in hypothesis_1.intent_options)
    ids_2 = sorted(o.option_id for o in hypothesis_2.intent_options)

    assert ids_1 == ids_2, (
        f"option_ids must be stable across runs regardless of LLM wording: "
        f"{ids_1} != {ids_2}"
    )

    # And they should be usable as automation selectors matching output_mode
    single_merged_id = next(
        o.option_id for o in hypothesis_1.intent_options if o.output_mode == "single_merged"
    )
    batch_id = next(
        o.option_id for o in hypothesis_1.intent_options if o.output_mode == "per_partition_batch"
    )
    assert single_merged_id != batch_id


def test_problem_discoverer_deduplicates_colliding_option_ids(sample_df):
    """Two options with identical structural fields must not collide on id."""
    metadata = [MetadataExtractor().extract_table("sensors_fd001", sample_df)]

    mock = MockLLM({
        "ml solutions architect": {
            "domain": "test",
            "domain_confidence": 0.8,
            "dataset_purpose": "test",
            "structural_shape": "test",
            "partition_dimension_name": None,
            "detected_partitions": [],
            "question_for_user": "What do you want?",
            "intent_options": [
                {
                    "label": "Option A",
                    "description": "First",
                    "is_recommended": True,
                    "output_mode": "single_merged",
                    "merge_strategy": "auto",
                    "tables_to_include": [],
                    "tables_to_exclude": [],
                    "partition_by": None,
                    "target_column": None,
                    "target_synthesis": None,
                },
                {
                    "label": "Option B (structurally identical to A)",
                    "description": "Second",
                    "is_recommended": False,
                    "output_mode": "single_merged",
                    "merge_strategy": "auto",
                    "tables_to_include": [],
                    "tables_to_exclude": [],
                    "partition_by": None,
                    "target_column": None,
                    "target_synthesis": None,
                },
            ],
            "reasoning": "test",
        }
    })

    hypothesis = ProblemDiscoverer(mock).discover(None, metadata, [], [], [])

    ids = [o.option_id for o in hypothesis.intent_options]
    assert len(ids) == len(set(ids)), f"option_ids must be unique, got duplicates: {ids}"


def test_safe_confidence_clamps_and_coerces():
    from services.aiconnex_zip_compiler.intelligence.validation import safe_confidence

    assert safe_confidence(0.5) == 0.5
    assert safe_confidence(1.5) == 1.0, "must clamp above 1.0"
    assert safe_confidence(-0.3) == 0.0, "must clamp below 0.0"
    assert safe_confidence("not a number", default=0.42) == 0.42
    assert safe_confidence(None, default=0.1) == 0.1
    assert safe_confidence(float("nan"), default=0.2) == 0.2


def test_safe_choice_falls_back_on_unexpected_value():
    from services.aiconnex_zip_compiler.intelligence.validation import safe_choice

    allowed = {"a", "b", "c"}
    assert safe_choice("b", allowed, default="a") == "b"
    assert safe_choice("not_in_set", allowed, default="a") == "a"
    assert safe_choice(None, allowed, default="a") == "a"


def test_parser_advisor_rejects_unknown_plugin_id():
    from services.aiconnex_zip_compiler.intelligence.models import FileFingerprint

    fingerprints = [
        FileFingerprint(
            relative_path="data.weird",
            extension=".weird",
            magic_bytes_hex="deadbeef",
            detected_format="mystery_binary",
            detection_method="llm",
            confidence=0.5,
            is_binary=True,
        )
    ]
    catalog = [{"plugin_id": "csv_parser", "stage": "parser", "handles_extensions": [".csv"]}]

    mock = MockLLM({
        "data ingestion architect": {
            "decisions": [{
                "detected_format": "mystery_binary",
                "chosen_plugin_id": "totally_made_up_parser",
                "requires_new_plugin": False,
                "proposed_plugin_stage": "parser",
                "proposed_approach": None,
                "fallback_chain": ["numpy.fromfile"],
                "confidence": 0.7,
                "reasoning": "test",
            }]
        }
    })

    decisions = ParserAdvisor(mock).advise(fingerprints, catalog)

    assert len(decisions) == 1
    assert decisions[0].chosen_plugin_id is None, "hallucinated plugin must be rejected"
    assert decisions[0].requires_new_plugin is True


# ---------------------------------------------------------------------------
# Partition batch output
# ---------------------------------------------------------------------------

def test_partition_batch_emits_one_job_per_partition(tmp_path, sample_df):
    tables = {
        "sensors_fd001": sample_df.copy(),
        "sensors_fd002": sample_df.copy(),
        "plant_lookup": pd.DataFrame({"plant_tag": ["A"], "site": ["Site1"]}),
    }
    partitions = [
        {"group_id": "FD001", "group_label": "Condition FD001", "member_tables": ["sensors_fd001"]},
        {"group_id": "FD002", "group_label": "Condition FD002", "member_tables": ["sensors_fd002"]},
    ]

    result = export_partition_batch(
        output_dir=tmp_path,
        tables=tables,
        partitions=partitions,
        partition_dimension="operating condition",
        dataset_name="test.zip",
    )

    assert result is not None
    assert len(result.job_specs) == 2

    manifest = json.loads((tmp_path / "batch_manifest.json").read_text())
    assert manifest["job_count"] == 2
    assert manifest["partition_dimension"] == "operating condition"

    # Each job has its own directory with a job_spec
    assert (tmp_path / "jobs" / "fd001" / "job_spec.json").exists()
    assert (tmp_path / "jobs" / "fd002" / "job_spec.json").exists()

    # Unclaimed lookup table goes to the shared job
    assert manifest["shared_tables"], "plant_lookup should be exposed as a shared table"
    assert any("plant_lookup" in k for k in manifest["shared_tables"])


def test_partition_batch_returns_none_without_partitions(tmp_path, sample_df):
    result = export_partition_batch(
        output_dir=tmp_path,
        tables={"sensors": sample_df},
        partitions=[],
    )
    assert result is None


# ---------------------------------------------------------------------------
# Bridge: intelligence report -> intent layer
# ---------------------------------------------------------------------------

def test_llm_bridge_maps_partition_batch_strategy(sample_df):
    from services.aiconnex_zip_compiler.intent import resolve_llm_strategy
    from services.aiconnex_zip_compiler.intelligence.models import (
        GeneratedIntentOption,
        PartitionGroup,
        ProblemHypothesis,
    )

    report = IntelligenceReport(archive_name="test.zip")
    report.table_metadata = [MetadataExtractor().extract_table("sensors_fd001", sample_df)]
    report.problem_hypothesis = ProblemHypothesis(
        domain="test domain",
        partition_dimension_name="operating condition",
        detected_partitions=[
            PartitionGroup(
                group_id="FD001",
                group_label="Condition FD001",
                member_tables=["sensors_fd001"],
            )
        ],
        question_for_user="What do you want?",
        intent_options=[
            GeneratedIntentOption(
                option_id="per_condition",
                label="One model per condition",
                description="Separate models.",
                output_mode="per_partition_batch",
                merge_strategy="none",
                partition_by="operating condition",
            )
        ],
    )

    strategy = resolve_llm_strategy("per_condition", report)

    assert strategy is not None
    assert strategy.output_mode == "per_partition_batch"
    assert strategy.generated_by_llm is True
    assert strategy.partition_by == "operating condition"
    assert len(strategy.partitions) == 1


def test_llm_bridge_returns_none_for_unknown_choice(sample_df):
    from services.aiconnex_zip_compiler.intent import resolve_llm_strategy
    from services.aiconnex_zip_compiler.intelligence.models import ProblemHypothesis

    report = IntelligenceReport(archive_name="test.zip")
    report.problem_hypothesis = ProblemHypothesis(domain="d", intent_options=[])

    assert resolve_llm_strategy("nonexistent_option", report) is None
