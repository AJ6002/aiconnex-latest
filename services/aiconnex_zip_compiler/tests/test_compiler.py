"""
test_compiler.py - Unit Tests for AIConnex Plugin Pipeline Compiler
====================================================================
Tests the 5-stage plugin pipeline on synthetic multi-file ZIP archives.
"""

import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler, CompileResult
from services.aiconnex_zip_compiler.plugins import PluginRegistry, PipelineContext


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton registry before each test."""
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


@pytest.fixture
def synthetic_zip(tmp_path) -> Path:
    """Create a synthetic multi-table ZIP (Fact + Dimension)."""
    fact_data = {
        "DATE_TIME": ["15-05-2020 00:00", "15-05-2020 00:15", "15-05-2020 00:30"] * 10,
        "PLANT_ID": [101] * 30,
        "SOURCE_KEY": [f"INV_{i%3}" for i in range(30)],
        "AC_POWER": [100.0 + i for i in range(30)],
    }
    dim_data = {
        "DATE_TIME": ["2020-05-15 00:00:00", "2020-05-15 00:15:00", "2020-05-15 00:30:00"] * 10,
        "PLANT_ID": [101] * 30,
        "SOURCE_KEY": ["WEATHER_SENSOR_1"] * 30,
        "IRRADIATION": [0.5 + i * 0.01 for i in range(30)],
    }

    fact_df = pd.DataFrame(fact_data)
    dim_df = pd.DataFrame(dim_data)

    fact_csv = tmp_path / "Fact_Telemetry.csv"
    dim_csv = tmp_path / "Dimension_Weather.csv"

    fact_df.to_csv(fact_csv, index=False)
    dim_df.to_csv(dim_csv, index=False)

    zip_path = tmp_path / "synthetic_data.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(fact_csv, arcname="Fact_Telemetry.csv")
        zf.write(dim_csv, arcname="Dimension_Weather.csv")

    return zip_path


def test_plugin_discovery_and_parsing(synthetic_zip, tmp_path):
    """Test that plugin pipeline discovers and parses CSV files from a ZIP."""
    registry = PluginRegistry.get_instance()
    registry.auto_discover()

    context = PipelineContext(
        target_path=synthetic_zip,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
    )
    (tmp_path / "temp").mkdir()

    # Stage 1: Discovery
    disc_plugin = registry.resolve("discovery", context)
    context = disc_plugin.execute(context)
    assert len(context.inventory) == 2
    assert context.layout_type == "zip_directory"

    # Stage 2: Parser
    parser_plugin = registry.resolve("parser", context)
    context = parser_plugin.execute(context)
    assert len(context.parsed_tables) == 2


def test_schema_normalizer_plugin(tmp_path):
    """Test that the normalizer plugin applies snake_case and timestamp parsing."""
    registry = PluginRegistry.get_instance()
    registry.auto_discover()

    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path,
        output_dir=tmp_path,
    )

    # Pre-populate assembled_tables
    context.assembled_tables = {
        "test_table": pd.DataFrame({
            "DATE_TIME": ["15-05-2020 00:00", "15-05-2020 00:15"],
            "AC_POWER": [100.0, 105.0],
        })
    }

    normalizer = registry.resolve("normalizer", context)
    context = normalizer.execute(context)

    assert "test_table" in context.normalized_tables
    norm_df = context.normalized_tables["test_table"]
    assert "date_time" in norm_df.columns
    assert "ac_power" in norm_df.columns


def test_full_compiler_pipeline(synthetic_zip, tmp_path):
    """Test end-to-end compiler with plugin pipeline produces correct artifacts."""
    out_dir = tmp_path / "compiled_output"
    compiler = UnifiedCompiler(synthetic_zip, out_dir)
    res: CompileResult = compiler.compile()

    assert res.success is True
    assert len(res.merged_files) >= 1
    assert Path(res.artifacts.join_audit_json).exists()
    assert Path(res.artifacts.schema_map_json).exists()
    assert Path(res.artifacts.compiler_report_json).exists()

    # Verify lockfile was generated
    lockfile = out_dir / "compiler_lock.json"
    assert lockfile.exists()

    # Check merged CSV content
    merged_csv = Path(res.merged_files[0])
    merged_df = pd.read_csv(merged_csv)

    assert "date_time" in merged_df.columns
    assert "ac_power" in merged_df.columns
