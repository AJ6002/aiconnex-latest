"""
test_stage3_4_plugins.py - Unit tests for Stage 3 Assemblers and Stage 4/5 Normalizers
========================================================================================
Tests:
  - MultiSourceUnionAssemblerPlugin
  - KeyedTimeJoinAssemblerPlugin
  - UnitStandardizerPlugin
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry
from services.aiconnex_zip_compiler.plugins.context import PipelineContext
from services.aiconnex_zip_compiler.plugins.assemblers.multi_source_union_assembler import MultiSourceUnionAssemblerPlugin
from services.aiconnex_zip_compiler.plugins.assemblers.keyed_time_join_assembler import KeyedTimeJoinAssemblerPlugin
from services.aiconnex_zip_compiler.plugins.normalizers.unit_standardizer import UnitStandardizerPlugin


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton registry before each test."""
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


def make_context(tmp_path: Path) -> PipelineContext:
    return PipelineContext(
        target_path=tmp_path,
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "out",
    )


def test_multi_source_union_assembler_probe(tmp_path):
    """Test MultiSourceUnionAssemblerPlugin probe behavior."""
    plugin = MultiSourceUnionAssemblerPlugin()
    
    # Empty context
    ctx_empty = make_context(tmp_path)
    res_empty = plugin.probe(ctx_empty)
    assert res_empty.supported is False

    # Single table
    ctx_single = make_context(tmp_path)
    ctx_single.parsed_tables["source1"] = pd.DataFrame({"col_a": [1, 2], "val": [10.0, 20.0]})
    res_single = plugin.probe(ctx_single)
    assert res_single.supported is False

    # Multiple tables with matching columns
    ctx_multi = make_context(tmp_path)
    ctx_multi.parsed_tables["plant_alpha"] = pd.DataFrame({"col_a": [1, 2], "val": [10.0, 20.0]})
    ctx_multi.parsed_tables["plant_beta"] = pd.DataFrame({"col_a": [3, 4], "val": [30.0, 40.0]})
    res_multi = plugin.probe(ctx_multi)
    assert res_multi.supported is True
    assert res_multi.confidence >= 0.80


def test_multi_source_union_assembler_execute(tmp_path):
    """Test MultiSourceUnionAssemblerPlugin adding source_id tags and vertically unioning tables."""
    plugin = MultiSourceUnionAssemblerPlugin()
    ctx = make_context(tmp_path)
    
    df1 = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00", "2026-01-01T01:00:00"], "sensor1": [10, 12]})
    df2 = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00", "2026-01-01T01:00:00"], "sensor1": [15, 18]})
    
    ctx.parsed_tables["plant_east"] = df1
    ctx.parsed_tables["plant_west"] = df2
    
    res_ctx = plugin.execute(ctx)
    assert "multi_source_union" in res_ctx.assembled_tables
    
    union_df = res_ctx.assembled_tables["multi_source_union"]
    assert len(union_df) == 4
    assert "source_id" in union_df.columns
    assert set(union_df["source_id"].unique()) == {"plant_east", "plant_west"}
    assert list(union_df["sensor1"]) == [10, 12, 15, 18]


def test_keyed_time_join_assembler_probe(tmp_path):
    """Test KeyedTimeJoinAssemblerPlugin probe behavior."""
    plugin = KeyedTimeJoinAssemblerPlugin()

    ctx = make_context(tmp_path)
    t1 = pd.DataFrame({"timestamp": ["2026-01-01 10:00", "2026-01-01 10:05"], "asset_id": ["A1", "A1"], "temp": [25.0, 26.0]})
    t2 = pd.DataFrame({"timestamp": ["2026-01-01 10:01", "2026-01-01 10:06"], "asset_id": ["A1", "A1"], "pressure": [101.3, 102.0]})
    
    ctx.parsed_tables["telemetry_temp"] = t1
    ctx.parsed_tables["telemetry_press"] = t2

    res = plugin.probe(ctx)
    assert res.supported is True
    assert res.confidence >= 0.85


def test_keyed_time_join_assembler_execute_asof(tmp_path):
    """Test KeyedTimeJoinAssemblerPlugin executing ASOF / time-aligned joins across multi-sensor tables."""
    plugin = KeyedTimeJoinAssemblerPlugin()
    ctx = make_context(tmp_path)

    df_temp = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01 10:00:00", "2026-01-01 10:10:00", "2026-01-01 10:20:00"]),
        "asset_id": ["DEV1", "DEV1", "DEV1"],
        "temperature": [20.0, 22.5, 25.0]
    })
    
    df_press = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01 10:01:00", "2026-01-01 10:11:00", "2026-01-01 10:19:00"]),
        "asset_id": ["DEV1", "DEV1", "DEV1"],
        "pressure": [1.0, 1.2, 1.5]
    })

    ctx.parsed_tables["temp_sensor"] = df_temp
    ctx.parsed_tables["press_sensor"] = df_press

    res_ctx = plugin.execute(ctx)
    assert "keyed_time_join" in res_ctx.assembled_tables
    
    joined_df = res_ctx.assembled_tables["keyed_time_join"]
    assert "temperature" in joined_df.columns
    assert "pressure" in joined_df.columns
    assert "asset_id" in joined_df.columns
    assert len(joined_df) > 0


def test_unit_standardizer_probe(tmp_path):
    """Test UnitStandardizerPlugin probe behavior."""
    plugin = UnitStandardizerPlugin()

    ctx = make_context(tmp_path)
    ctx.parsed_tables["sensor_data"] = pd.DataFrame({
        "pressure_psi": [14.7, 30.0],
        "temp_degF": [32.0, 212.0],
        "power_kW": [1.5, 3.0],
        "speed_mph": [60.0, 120.0],
        "status": ["OK", "WARN"]
    })

    res = plugin.probe(ctx)
    assert res.supported is True
    assert res.confidence >= 0.90


def test_unit_standardizer_execute(tmp_path):
    """Test UnitStandardizerPlugin unit standardization factors and suffix conversions."""
    plugin = UnitStandardizerPlugin()
    ctx = make_context(tmp_path)

    df_in = pd.DataFrame({
        "pressure_psi": [14.6959, 29.3918],
        "temp_degF": [32.0, 212.0],
        "power_kW": [2.5, 10.0],
        "speed_mph": [60.0, 0.0],
        "vibration_rms": [0.05, 0.08]
    })
    ctx.assembled_tables["telemetry"] = df_in

    res_ctx = plugin.execute(ctx)
    norm_df = res_ctx.normalized_tables["telemetry"]

    # Column name conversions
    assert "pressure_bar" in norm_df.columns
    assert "temp_degc" in norm_df.columns
    assert "power_w" in norm_df.columns
    assert "speed_m_s" in norm_df.columns
    assert "vibration_rms" in norm_df.columns  # Unchanged

    # Value conversions
    # 1 psi ~ 0.0689476 bar -> 14.6959 * 0.0689476 ~ 1.013 bar
    assert np.isclose(norm_df["pressure_bar"].iloc[0], 1.01325, atol=1e-3)

    # 32°F -> 0°C, 212°F -> 100°C
    assert np.isclose(norm_df["temp_degc"].iloc[0], 0.0, atol=1e-4)
    assert np.isclose(norm_df["temp_degc"].iloc[1], 100.0, atol=1e-4)

    # 2.5 kW -> 2500 W
    assert np.isclose(norm_df["power_w"].iloc[0], 2500.0, atol=1e-3)

    # 60 mph -> ~26.8224 m/s
    assert np.isclose(norm_df["speed_m_s"].iloc[0], 26.8224, atol=1e-3)
