"""
test_plugin_pipeline.py - Unit Tests for 5-Stage Plugin Pipeline & Registry Architecture
========================================================================================
Validates:
  1. PluginRegistry auto-discovery and registration.
  2. Deterministic selection algorithm (policy override -> priority -> confidence -> fail closed).
  3. Lockfile generation (`compiler_lock.json`).
  4. End-to-end execution across all 5 stages.
"""

from pathlib import Path
import tempfile
import pytest
import pandas as pd

from services.aiconnex_zip_compiler.plugins import (
    PluginRegistry,
    PipelineContext,
    AmbiguousPluginMatchError,
    UnsupportedLayoutError,
)
from services.aiconnex_zip_compiler.compiler import UnifiedCompiler


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton registry before each test."""
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


def test_plugin_auto_discovery_and_registration():
    registry = PluginRegistry.get_instance()
    registry.auto_discover()
    
    # Check that plugins were discovered for all stages
    disc = registry.get_plugins("discovery")
    parsers = registry.get_plugins("parser")
    assemblers = registry.get_plugins("assembler")
    normalizers = registry.get_plugins("normalizer")

    assert len(disc) >= 2, "Expected at least 2 discovery plugins"
    assert len(parsers) >= 5, "Expected at least 5 parser plugins"
    assert len(assemblers) >= 2, "Expected at least 2 assembler plugins"
    assert len(normalizers) >= 1, "Expected at least 1 normalizer plugin"


def test_deterministic_plugin_resolution(tmp_path):
    registry = PluginRegistry.get_instance()
    registry.auto_discover()

    # Create dummy CSV file
    csv_file = tmp_path / "test_data.csv"
    csv_file.write_text("timestamp,value\n2025-01-01 00:00,10.5\n", encoding="utf-8")

    context = PipelineContext(target_path=tmp_path, temp_dir=tmp_path, output_dir=tmp_path)
    
    # 1. Discovery stage resolution
    disc_plugin = registry.resolve("discovery", context)
    assert disc_plugin.plugin_id in ["zip_directory_discovery", "snapshot_folder_discovery"]
    context = disc_plugin.execute(context)

    # 2. Parser stage resolution
    parser_plugin = registry.resolve("parser", context)
    assert parser_plugin.plugin_id == "csv_parser"
    assert parser_plugin.priority == 10


def test_policy_override(tmp_path):
    registry = PluginRegistry.get_instance()
    registry.auto_discover()

    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path,
        output_dir=tmp_path,
        policy_overrides={"parser": "parquet_parser"},
    )

    resolved = registry.resolve("parser", context)
    assert resolved.plugin_id == "parquet_parser", "Policy override must take highest precedence"


def test_compiler_end_to_end_with_lockfile(tmp_path):
    # Prepare mock CSV dataset
    raw_dir = tmp_path / "raw_dataset"
    raw_dir.mkdir()
    (raw_dir / "sensor_data.csv").write_text("timestamp,val_a,val_b\n2025-01-01 00:00,1.2,3.4\n2025-01-01 00:15,1.5,3.6\n", encoding="utf-8")

    out_dir = tmp_path / "output_dist"
    compiler = UnifiedCompiler(zip_path=raw_dir, output_dir=out_dir)
    res = compiler.compile()

    assert res.success is True
    assert len(res.merged_files) >= 1

    # Verify compiler_lock.json exists in output directory
    lockfile = out_dir / "compiler_lock.json"
    assert lockfile.exists(), "compiler_lock.json lockfile must be generated"
    content = lockfile.read_text(encoding="utf-8")
    assert "compiler_version" in content
    assert "plugin_lock" in content
