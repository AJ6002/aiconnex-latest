"""
test_gaps_12_13_14.py - Unit tests for Gaps 12, 13 & 14 in AIConnex Zip Compiler
================================================================================
Tests:
  - Gap 12: Vertical stack assembler strategy check for 'keep_separate'
  - Gap 13: Column collision resolution during snake_case normalization
  - Gap 14: In-memory feature harvesting without re-reading disk files
"""

import pytest
import pandas as pd

from services.aiconnex_zip_compiler.plugins import PluginRegistry, PipelineContext
from services.aiconnex_zip_compiler.plugins.assemblers.vertical_stack_assembler import VerticalStackAssemblerPlugin
from services.aiconnex_zip_compiler.plugins.normalizers.canonical_schema_normalizer import CanonicalSchemaNormalizerPlugin
from services.aiconnex_zip_compiler.plugins.harvesters.signal_summary_harvester import SignalSummaryHarvesterPlugin
from services.aiconnex_zip_compiler.intent.models import CompilationStrategy


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton registry before each test."""
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


def test_gap_12_vertical_stack_strategy_keep_separate(tmp_path):
    """Gap 12: Check that vertical_stack_assembler respects strategy merge_rule 'keep_separate'."""
    plugin = VerticalStackAssemblerPlugin()
    
    # Context with keep_separate strategy
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path,
        output_dir=tmp_path,
        strategy=CompilationStrategy(intent_id="test", merge_rule="keep_separate"),
    )
    
    parsed_tables = {
        "t1": pd.DataFrame({"col1": [1, 2], "col2": [3, 4]}),
        "t2": pd.DataFrame({"col1": [5, 6], "col2": [7, 8]}),
    }
    context.parsed_tables = parsed_tables

    # Probe should return supported=False
    probe_res = plugin.probe(context)
    assert probe_res.supported is False

    # Assemble should raise an explicit incompatibility error (ValueError)
    with pytest.raises(ValueError, match="keep_separate"):
        plugin.assemble(parsed_tables, context)


def test_gap_13_column_collision_resolution(tmp_path):
    """Gap 13: Check that duplicate column names after snake_case normalization get suffix deduplicated."""
    plugin = CanonicalSchemaNormalizerPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path,
        output_dir=tmp_path,
    )

    df_colliding = pd.DataFrame({
        "Pressure (bar)": [1.0, 2.0],
        "Pressure_bar": [1.1, 2.1],
        "Temperature": [300, 305],
    })

    norm_df = plugin.normalize(df_colliding, context)

    # Columns must be deduplicated deterministically
    assert list(norm_df.columns) == ["pressure_bar_1", "pressure_bar_2", "temperature"]

    # Schema map / context should have warnings recorded
    assert hasattr(context, "schema_warnings") or len(context.audits) > 0
    warnings = getattr(context, "schema_warnings", [])
    if not warnings:
        warnings = [a["message"] for a in context.audits if isinstance(a, dict) and "message" in a]
    assert any("pressure_bar" in w.lower() for w in warnings)


def test_gap_14_in_memory_harvester_contract(tmp_path):
    """Gap 14: Check that signal_summary_harvester consumes in-memory tables without requiring disk reads."""
    plugin = SignalSummaryHarvesterPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path,
        output_dir=tmp_path,
        layout_type="snapshot_folder",
    )

    # In-memory DataFrames with high-frequency sensor signal columns
    df1 = pd.DataFrame({
        "time": [0.0, 0.1, 0.2, 0.3, 0.4],
        "sensor_a": [1.0, 2.0, 1.5, 2.5, 1.8],
        "sensor_b": [0.5, 0.6, 0.4, 0.7, 0.5],
    })
    df2 = pd.DataFrame({
        "time": [0.0, 0.1, 0.2, 0.3, 0.4],
        "sensor_a": [3.0, 4.0, 3.5, 4.5, 3.8],
        "sensor_b": [1.5, 1.6, 1.4, 1.7, 1.5],
    })

    in_memory_tables = {
        "acc_00001.csv": df1,
        "acc_00002.csv": df2,
    }

    # Execute harvest using in-memory tables dictionary directly (files do not exist on disk!)
    res = plugin.harvest(in_memory_tables, context)

    assert "bearing_snapshot_features" in res
    harvested_df = res["bearing_snapshot_features"]
    assert len(harvested_df) == 2
    assert "rul" in harvested_df.columns
    assert harvested_df["rul"].tolist() == [1.0, 0.0]
