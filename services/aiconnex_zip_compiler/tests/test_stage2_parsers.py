"""
tests/test_stage2_parsers.py - Unit tests for Stage 2 Parser Plugins
======================================================================
Tests TDMS, JSON/JSONL, SQLite, XML, and Text Delimited Autodetect parsers.
"""

import sys
import sqlite3
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services.aiconnex_zip_compiler.plugins.context import PipelineContext, FileInventoryItem
from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry
from services.aiconnex_zip_compiler.plugins.parsers.tdms_parser import TdmsParserPlugin
from services.aiconnex_zip_compiler.plugins.parsers.json_parser import JsonParserPlugin
from services.aiconnex_zip_compiler.plugins.parsers.sqlite_parser import SqliteParserPlugin
from services.aiconnex_zip_compiler.plugins.parsers.xml_parser import XmlParserPlugin
from services.aiconnex_zip_compiler.plugins.parsers.text_delimited_autodetect_parser import (
    TextDelimitedAutodetectParserPlugin,
)


@pytest.fixture(autouse=True)
def reset_registry():
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


def make_context(target_path: Path, inventory=None) -> PipelineContext:
    return PipelineContext(
        target_path=target_path,
        temp_dir=target_path / "temp",
        output_dir=target_path / "out",
        inventory=inventory or [],
    )


# ---------------------------------------------------------------------------
# 1. TDMS Parser Plugin Tests
# ---------------------------------------------------------------------------
def test_tdms_parser_metadata_and_probe():
    plugin = TdmsParserPlugin()
    assert plugin.plugin_id == "tdms_parser"
    assert plugin.stage == "parser"
    assert plugin.priority == 15

    # Probe without tdms
    ctx_empty = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/data.csv"), relative_path="data.csv", format_ext=".csv", size_bytes=100)],
    )
    res_empty = plugin.probe(ctx_empty)
    assert not res_empty.supported
    assert res_empty.confidence == 0.0

    # Probe with tdms
    ctx_tdms = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/signal.tdms"), relative_path="signal.tdms", format_ext=".tdms", size_bytes=500)],
    )
    res_tdms = plugin.probe(ctx_tdms)
    assert res_tdms.supported
    assert res_tdms.confidence == 0.95
    assert res_tdms.detected_family == "tdms"


def test_tdms_parser_missing_nptdms_graceful(tmp_path):
    plugin = TdmsParserPlugin()
    tdms_file = tmp_path / "sensor.tdms"
    tdms_file.write_bytes(b"dummy tdms content")

    # Force nptdms import to fail
    with patch.dict(sys.modules, {"nptdms": None}):
        ctx = make_context(tmp_path)
        tables = plugin.parse(tdms_file, ctx)
        assert tables == {}


def test_tdms_parser_mocked_nptdms(tmp_path):
    plugin = TdmsParserPlugin()
    tdms_file = tmp_path / "sensor.tdms"
    tdms_file.write_bytes(b"dummy tdms content")

    mock_df = pd.DataFrame({"time": [1, 2, 3], "vibration": [0.1, 0.4, 0.2]})
    mock_tdms_obj = MagicMock()
    mock_tdms_obj.as_dataframe.return_value = mock_df

    mock_nptdms = MagicMock()
    mock_nptdms.TdmsFile.read.return_value = mock_tdms_obj

    with patch.dict(sys.modules, {"nptdms": mock_nptdms}):
        ctx = make_context(tmp_path)
        tables = plugin.parse(tdms_file, ctx)
        assert "sensor" in tables
        pd.testing.assert_frame_equal(tables["sensor"], mock_df)


# ---------------------------------------------------------------------------
# 2. JSON Parser Plugin Tests
# ---------------------------------------------------------------------------
def test_json_parser_metadata_and_probe():
    plugin = JsonParserPlugin()
    assert plugin.plugin_id == "json_parser"
    assert plugin.stage == "parser"
    assert plugin.priority == 12

    ctx = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/metrics.jsonl"), relative_path="metrics.jsonl", format_ext=".jsonl", size_bytes=200)],
    )
    res = plugin.probe(ctx)
    assert res.supported
    assert res.confidence == 0.90
    assert res.detected_family == "json"


def test_json_parser_standard_and_lines(tmp_path):
    plugin = JsonParserPlugin()

    # Standard JSON array of objects
    json_path = tmp_path / "records.json"
    records = [{"id": 1, "val": 10.5}, {"id": 2, "val": 20.1}]
    json_path.write_text(json.dumps(records), encoding="utf-8")

    # JSON lines (.jsonl)
    jsonl_path = tmp_path / "stream.jsonl"
    jsonl_path.write_text('{"sensor": "A", "reading": 1.1}\n{"sensor": "B", "reading": 2.2}\n', encoding="utf-8")

    ctx = make_context(
        target_path=tmp_path,
        inventory=[
            FileInventoryItem(filepath=json_path, relative_path="records.json", format_ext=".json", size_bytes=100),
            FileInventoryItem(filepath=jsonl_path, relative_path="stream.jsonl", format_ext=".jsonl", size_bytes=100),
        ],
    )

    ctx = plugin.execute(ctx)
    assert "records" in ctx.parsed_tables
    assert len(ctx.parsed_tables["records"]) == 2
    assert "stream" in ctx.parsed_tables
    assert len(ctx.parsed_tables["stream"]) == 2


# ---------------------------------------------------------------------------
# 3. SQLite Parser Plugin Tests
# ---------------------------------------------------------------------------
def test_sqlite_parser_metadata_and_probe():
    plugin = SqliteParserPlugin()
    assert plugin.plugin_id == "sqlite_parser"
    assert plugin.stage == "parser"
    assert plugin.priority == 15

    ctx = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/db.sqlite3"), relative_path="db.sqlite3", format_ext=".sqlite3", size_bytes=1024)],
    )
    res = plugin.probe(ctx)
    assert res.supported
    assert res.confidence == 0.95
    assert res.detected_family == "sqlite"


def test_sqlite_parser_extract_tables(tmp_path):
    plugin = SqliteParserPlugin()
    db_path = tmp_path / "telemetry.db"

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE pressure (timestamp INTEGER, val REAL)")
    conn.execute("INSERT INTO pressure VALUES (100, 45.2), (101, 45.8)")
    conn.execute("CREATE TABLE temperature (timestamp INTEGER, val REAL)")
    conn.execute("INSERT INTO temperature VALUES (100, 22.1), (101, 22.4)")
    conn.commit()
    conn.close()

    ctx = make_context(
        target_path=tmp_path,
        inventory=[FileInventoryItem(filepath=db_path, relative_path="telemetry.db", format_ext=".db", size_bytes=2048)],
    )

    ctx = plugin.execute(ctx)
    assert "telemetry_pressure" in ctx.parsed_tables
    assert "telemetry_temperature" in ctx.parsed_tables
    assert len(ctx.parsed_tables["telemetry_pressure"]) == 2
    assert len(ctx.parsed_tables["telemetry_temperature"]) == 2


# ---------------------------------------------------------------------------
# 4. XML Parser Plugin Tests
# ---------------------------------------------------------------------------
def test_xml_parser_metadata_and_probe():
    plugin = XmlParserPlugin()
    assert plugin.plugin_id == "xml_parser"
    assert plugin.stage == "parser"
    assert plugin.priority == 10

    ctx = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/export.xml"), relative_path="export.xml", format_ext=".xml", size_bytes=500)],
    )
    res = plugin.probe(ctx)
    assert res.supported
    assert res.confidence == 0.85
    assert res.detected_family == "xml"


def test_xml_parser_parse_export(tmp_path):
    plugin = XmlParserPlugin()
    xml_path = tmp_path / "plc_export.xml"

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <HistorianData>
        <Record timestamp="2026-01-01T00:00:00" tag="P_001" value="101.3" status="GOOD"/>
        <Record timestamp="2026-01-01T00:01:00" tag="P_001" value="101.5" status="GOOD"/>
    </HistorianData>
    """
    xml_path.write_text(xml_content, encoding="utf-8")

    ctx = make_context(
        target_path=tmp_path,
        inventory=[FileInventoryItem(filepath=xml_path, relative_path="plc_export.xml", format_ext=".xml", size_bytes=300)],
    )

    ctx = plugin.execute(ctx)
    assert "plc_export" in ctx.parsed_tables
    df = ctx.parsed_tables["plc_export"]
    assert len(df) == 2
    assert "tag" in df.columns
    assert list(df["tag"]) == ["P_001", "P_001"]


# ---------------------------------------------------------------------------
# 5. Text Delimited Autodetect Parser Plugin Tests
# ---------------------------------------------------------------------------
def test_text_delimited_autodetect_metadata_and_probe():
    plugin = TextDelimitedAutodetectParserPlugin()
    assert plugin.plugin_id == "text_delimited_autodetect_parser"
    assert plugin.stage == "parser"
    assert plugin.priority == 8

    ctx = make_context(
        target_path=Path("/tmp/test"),
        inventory=[FileInventoryItem(filepath=Path("/tmp/test/dump.dat"), relative_path="dump.dat", format_ext=".dat", size_bytes=400)],
    )
    res = plugin.probe(ctx)
    assert res.supported
    assert res.confidence == 0.80
    assert res.detected_family == "text_delimited"


def test_text_delimited_autodetect_various_delimiters(tmp_path):
    plugin = TextDelimitedAutodetectParserPlugin()

    # Pipe delimited .dat
    dat_path = tmp_path / "sensor.dat"
    dat_path.write_text("# Sensor dump header\n# timestamp|channel|value\n1000|ch1|42.1\n1001|ch1|42.5\n", encoding="utf-8")

    # Tab delimited .asc
    asc_path = tmp_path / "vibration.asc"
    asc_path.write_text("time\taccel_x\taccel_y\n0.0\t0.01\t0.02\n0.1\t0.03\t0.04\n", encoding="utf-8")

    ctx = make_context(
        target_path=tmp_path,
        inventory=[
            FileInventoryItem(filepath=dat_path, relative_path="sensor.dat", format_ext=".dat", size_bytes=200),
            FileInventoryItem(filepath=asc_path, relative_path="vibration.asc", format_ext=".asc", size_bytes=200),
        ],
    )

    ctx = plugin.execute(ctx)
    assert "sensor" in ctx.parsed_tables
    assert "vibration" in ctx.parsed_tables

    df_dat = ctx.parsed_tables["sensor"]
    assert len(df_dat) == 2
    assert "channel" in df_dat.columns

    df_asc = ctx.parsed_tables["vibration"]
    assert len(df_asc) == 2
    assert "accel_x" in df_asc.columns
