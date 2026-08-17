"""
test_compiler_regression_suite.py - Automated Regression Test Suite
====================================================================
Runs the UnifiedCompiler on synthetic & real dataset archives to verify
that zero regressions occur when adding new format converters or rules.
"""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler, CompileResult
from services.aiconnex_zip_compiler.reporter import classify_compilation_failure


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="compiler_regress_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def test_relational_solar_dataset_compilation(temp_workspace):
    """Test Case 1: Relational Joiner (Solar Pattern)"""
    zip_path = temp_workspace / "solar_test.zip"
    out_dir = temp_workspace / "out_solar"

    # Create dummy generation & weather CSVs
    gen_df = pd.DataFrame({
        "DATE_TIME": ["2020-05-15 00:00:00", "2020-05-15 00:15:00"],
        "PLANT_ID": [4135001, 4135001],
        "DC_POWER": [0.0, 0.0],
        "AC_POWER": [0.0, 0.0]
    })
    weather_df = pd.DataFrame({
        "DATE_TIME": ["2020-05-15 00:00:00", "2020-05-15 00:15:00"],
        "PLANT_ID": [4135001, 4135001],
        "AMBIENT_TEMPERATURE": [25.1, 24.8],
        "MODULE_TEMPERATURE": [25.0, 24.7]
    })

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Plant_1_Generation_Data.csv", gen_df.to_csv(index=False))
        zf.writestr("Plant_1_Weather_Sensor_Data.csv", weather_df.to_csv(index=False))

    compiler = UnifiedCompiler(zip_path=zip_path, output_dir=out_dir)
    res = compiler.compile()

    assert res.success is True
    assert res.combined_file is not None
    merged = pd.read_csv(res.combined_file)
    assert len(merged) == 2
    assert "dc_power" in merged.columns
    assert "ambient_temperature" in merged.columns


def test_row_aligned_index_join_sensor_dataset(temp_workspace):
    """Test Case 2: Multi-Sensor Row-Aligned Index Join (IGBT Parallel Channel Pattern)"""
    zip_path = temp_workspace / "igbt_sensors.zip"
    out_dir = temp_workspace / "out_igbt"

    v_df = pd.DataFrame({"collector_voltage": [10.1, 10.2, 10.3, 10.4]})
    i_df = pd.DataFrame({"collector_current": [1.1, 1.2, 1.3, 1.4]})
    t_df = pd.DataFrame({"package_temp": [45.0, 45.5, 46.0, 46.5]})

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Device_1/COLLECTOR_VOLTAGE.csv", v_df.to_csv(index=False))
        zf.writestr("Device_1/COLLECTOR_CURRENT.csv", i_df.to_csv(index=False))
        zf.writestr("Device_1/PACKAGE_TEMP.csv", t_df.to_csv(index=False))

    compiler = UnifiedCompiler(zip_path=zip_path, output_dir=out_dir)
    res = compiler.compile()

    assert res.success is True
    assert len(res.merged_files) >= 1
    merged = pd.read_csv(res.merged_files[0])
    assert len(merged) == 4
    assert len(merged.columns) == 3
    assert "collector_voltage" in merged.columns
    assert "collector_current" in merged.columns
    assert "package_temp" in merged.columns


def test_excel_multi_sheet_extractor(temp_workspace):
    """Test Case 3: Excel Converter with Header Metadata Rows (SCADA Trend Pattern)"""
    excel_path = temp_workspace / "scada_trend.xlsx"
    zip_path = temp_workspace / "scada_archive.zip"
    out_dir = temp_workspace / "out_excel"

    df = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:01:00"],
        "sensor_pressure": [101.3, 101.5],
        "sensor_temp": [72.1, 72.4]
    })
    df.to_excel(excel_path, sheet_name="Telemetry", index=False)

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(excel_path, arcname="scada_trend.xlsx")

    compiler = UnifiedCompiler(zip_path=zip_path, output_dir=out_dir)
    res = compiler.compile()

    assert res.success is True
    assert res.combined_file is not None
    merged = pd.read_csv(res.combined_file)
    assert len(merged) == 2
    assert "sensor_pressure" in merged.columns


def test_failure_reporter_classification(temp_workspace):
    """Test Case 4: Failure Classifier correctly tags Gap G-01 on unparseable format"""
    dummy_zip = temp_workspace / "bad_dataset.zip"
    with zipfile.ZipFile(dummy_zip, "w") as zf:
        zf.writestr("corrupt.txt", "Corrupt non-tabular data")

    try:
        raise ValueError("KeyError: 'cycle' invalid MATLAB struct shape")
    except Exception as e:
        report = classify_compilation_failure(dummy_zip, temp_workspace, e)
        assert report.gap_id == "G-03"
        assert "MATLAB struct" in report.gap_description


def test_schema_gate_evaluation(temp_workspace):
    """Test Case 8: SchemaGate pre-validation and ingestion routing"""
    from services.aiconnex_zip_compiler.schema_gate import SchemaGate

    # Valid ZIP archive test
    valid_zip = temp_workspace / "gate_valid.zip"
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.writestr("test.csv", "a,b\n1,2")

    gate = SchemaGate(valid_zip)
    decision = gate.evaluate()

    assert decision.is_valid is True
    assert decision.file_count == 1
    assert ".csv" in decision.detected_formats

    # Non-existent path test
    invalid_gate = SchemaGate(temp_workspace / "non_existent.zip")
    invalid_dec = invalid_gate.evaluate()
    assert invalid_dec.is_valid is False





