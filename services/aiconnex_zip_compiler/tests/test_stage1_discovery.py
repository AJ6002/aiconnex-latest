"""
test_stage1_discovery.py - Unit tests for Stage 1 Discovery Plugins
===================================================================
Tests:
  - ArchiveManifestDiscoveryPlugin
  - SchemaFingerprintDiscoveryPlugin (same_schema_batch, relational_schema_bundle, heterogeneous_mixed_archive)
  - MixedArchiveRouterPlugin
"""

import pytest
import pandas as pd
from pathlib import Path

from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry
from services.aiconnex_zip_compiler.plugins.context import PipelineContext, FileInventoryItem
from services.aiconnex_zip_compiler.plugins.discovery.archive_manifest_discovery import ArchiveManifestDiscoveryPlugin
from services.aiconnex_zip_compiler.plugins.discovery.schema_fingerprint_discovery import SchemaFingerprintDiscoveryPlugin
from services.aiconnex_zip_compiler.plugins.discovery.mixed_archive_router import MixedArchiveRouterPlugin


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton registry before each test."""
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


def test_archive_manifest_discovery(tmp_path):
    """Test ArchiveManifestDiscoveryPlugin cataloging files, formats, sizes, and inner dirs."""
    sub1 = tmp_path / "sub1"
    sub2 = tmp_path / "sub2"
    sub1.mkdir()
    sub2.mkdir()

    f1 = tmp_path / "data1.csv"
    f2 = sub1 / "data2.xlsx"
    f3 = sub2 / "info.txt"
    f4 = tmp_path / "config.json"

    f1.write_text("col1,col2\n1,2\n3,4", encoding="utf-8")
    f2.write_bytes(b"dummy excel content")
    f3.write_text("sample log info", encoding="utf-8")
    f4.write_text('{"setting": "val"}', encoding="utf-8")

    plugin = ArchiveManifestDiscoveryPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
    )

    probe_res = plugin.probe(context)
    assert probe_res.supported is True
    assert probe_res.confidence >= 0.70

    res_context = plugin.discover(tmp_path, context)
    assert len(res_context.inventory) == 4

    rel_paths = {item.relative_path for item in res_context.inventory}
    assert "data1.csv" in rel_paths
    assert str(Path("sub1") / "data2.xlsx") in rel_paths or "sub1/data2.xlsx" in [p.replace("\\", "/") for p in rel_paths]
    assert str(Path("sub2") / "info.txt") in rel_paths or "sub2/info.txt" in [p.replace("\\", "/") for p in rel_paths]
    assert "config.json" in rel_paths

    # Audit check
    manifest_audits = [a for a in res_context.audits if a.get("plugin_id") == "archive_manifest_discovery"]
    assert len(manifest_audits) == 1
    audit = manifest_audits[0]
    assert audit["file_count"] == 4
    assert set(audit["formats"]) == {".csv", ".xlsx", ".txt", ".json"}
    assert "sub1" in audit["inner_directories"]
    assert "sub2" in audit["inner_directories"]


def test_schema_fingerprint_same_schema_batch(tmp_path):
    """Test SchemaFingerprintDiscoveryPlugin classifying identical headers as same_schema_batch."""
    f1 = tmp_path / "part1.csv"
    f2 = tmp_path / "part2.csv"
    content = "timestamp,sensor_1,sensor_2,unit_id\n2026-01-01,1.0,2.0,101\n"
    f1.write_text(content, encoding="utf-8")
    f2.write_text(content, encoding="utf-8")

    plugin = SchemaFingerprintDiscoveryPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
        inventory=[
            FileInventoryItem(filepath=f1, relative_path="part1.csv", size_bytes=f1.stat().st_size, format_ext=".csv"),
            FileInventoryItem(filepath=f2, relative_path="part2.csv", size_bytes=f2.stat().st_size, format_ext=".csv"),
        ],
    )

    res_context = plugin.execute(context)
    assert res_context.layout_type == "same_schema_batch"

    audit = [a for a in res_context.audits if a.get("plugin_id") == "schema_fingerprint_discovery"][0]
    assert audit["layout_type"] == "same_schema_batch"
    assert audit["mean_jaccard_distance"] == 0.0


def test_schema_fingerprint_relational_schema_bundle(tmp_path):
    """Test SchemaFingerprintDiscoveryPlugin classifying schemas with shared join keys as relational_schema_bundle."""
    f1 = tmp_path / "measurements.csv"
    f2 = tmp_path / "metadata.csv"
    
    f1.write_text("unit_id,timestamp,temp,vibration\n1,2026-01-01,50.0,0.1\n", encoding="utf-8")
    f2.write_text("unit_id,machine_type,location,operator\n1,Turbine,PlantA,John\n", encoding="utf-8")

    plugin = SchemaFingerprintDiscoveryPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
        inventory=[
            FileInventoryItem(filepath=f1, relative_path="measurements.csv", size_bytes=f1.stat().st_size, format_ext=".csv"),
            FileInventoryItem(filepath=f2, relative_path="metadata.csv", size_bytes=f2.stat().st_size, format_ext=".csv"),
        ],
    )

    res_context = plugin.execute(context)
    assert res_context.layout_type == "relational_schema_bundle"

    audit = [a for a in res_context.audits if a.get("plugin_id") == "schema_fingerprint_discovery"][0]
    assert audit["layout_type"] == "relational_schema_bundle"
    assert "unit_id" in audit["join_key_candidates"]


def test_schema_fingerprint_heterogeneous_mixed_archive(tmp_path):
    """Test SchemaFingerprintDiscoveryPlugin classifying disjoint schemas without join keys as heterogeneous_mixed_archive."""
    f1 = tmp_path / "table_a.csv"
    f2 = tmp_path / "table_b.csv"
    
    f1.write_text("alpha,beta,gamma\n1,2,3\n", encoding="utf-8")
    f2.write_text("delta,epsilon,zeta\n4,5,6\n", encoding="utf-8")

    plugin = SchemaFingerprintDiscoveryPlugin()
    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
        inventory=[
            FileInventoryItem(filepath=f1, relative_path="table_a.csv", size_bytes=f1.stat().st_size, format_ext=".csv"),
            FileInventoryItem(filepath=f2, relative_path="table_b.csv", size_bytes=f2.stat().st_size, format_ext=".csv"),
        ],
    )

    res_context = plugin.execute(context)
    assert res_context.layout_type == "heterogeneous_mixed_archive"


def test_mixed_archive_router(tmp_path):
    """Test MixedArchiveRouterPlugin assigning parser routes per file extension/type."""
    f1 = tmp_path / "raw_1.csv"
    f2 = tmp_path / "scada.xlsx"
    f3 = tmp_path / "signals.h5"
    f4 = tmp_path / "vib.mat"
    f5 = tmp_path / "logs.parquet"
    f6 = tmp_path / "notes.txt"

    for f in [f1, f2, f3, f4, f5, f6]:
        f.write_text("dummy", encoding="utf-8")

    inventory = [
        FileInventoryItem(filepath=f1, relative_path="raw_1.csv", size_bytes=10, format_ext=".csv"),
        FileInventoryItem(filepath=f2, relative_path="scada.xlsx", size_bytes=10, format_ext=".xlsx"),
        FileInventoryItem(filepath=f3, relative_path="signals.h5", size_bytes=10, format_ext=".h5"),
        FileInventoryItem(filepath=f4, relative_path="vib.mat", size_bytes=10, format_ext=".mat"),
        FileInventoryItem(filepath=f5, relative_path="logs.parquet", size_bytes=10, format_ext=".parquet"),
        FileInventoryItem(filepath=f6, relative_path="notes.txt", size_bytes=10, format_ext=".txt"),
    ]

    context = PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
        layout_type="heterogeneous_mixed_archive",
        inventory=inventory,
    )

    router = MixedArchiveRouterPlugin()
    probe_res = router.probe(context)
    assert probe_res.supported is True

    res_context = router.execute(context)
    
    routes_audit = [a for a in res_context.audits if a.get("plugin_id") == "mixed_archive_router"][0]
    routes = routes_audit["routes"]

    assert routes["raw_1.csv"] == "csv_parser"
    assert routes["scada.xlsx"] == "scada_excel_parser"
    assert routes["signals.h5"] == "hdf5_parser"
    assert routes["vib.mat"] == "mat_parser"
    assert routes["logs.parquet"] == "parquet_parser"
    assert routes["notes.txt"] == "txt_parser"


def test_stage1_plugins_auto_registration():
    """Verify that auto_discover registers all stage 1 discovery plugins."""
    reg = PluginRegistry.get_instance()
    reg.auto_discover()

    discovery_plugins = reg.get_plugins("discovery")
    plugin_ids = {p.plugin_id for p in discovery_plugins}

    assert "archive_manifest_discovery" in plugin_ids
    assert "schema_fingerprint_discovery" in plugin_ids
    assert "mixed_archive_router" in plugin_ids
