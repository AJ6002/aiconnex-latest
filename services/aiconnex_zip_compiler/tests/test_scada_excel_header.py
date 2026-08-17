"""
tests/test_scada_excel_header.py - Gap 9 SCADA Excel Header Detection Tests
===========================================================================
"""

import pandas as pd
import pytest
from pathlib import Path

from services.aiconnex_zip_compiler.plugins.parsers.scada_excel_parser import ScadaExcelParserPlugin
from services.aiconnex_zip_compiler.plugins.context import PipelineContext


def test_header_with_numeric_tokens(tmp_path: Path):
    """
    Test multi-level header where top row contains numeric tokens (e.g. '2026', 'Temp_1').
    Naive digit heuristics break by treating row 0 as data start.
    """
    excel_path = tmp_path / "scada_numeric_headers.xlsx"
    
    raw_data = [
        ["Tag", "2026", "Temp_1"],
        ["Unit", "m3/h", "degC"],
        ["TAG-01", 100.5, 23.4],
        ["TAG-02", 102.1, 24.0],
    ]
    df_raw = pd.DataFrame(raw_data)
    df_raw.to_excel(excel_path, header=False, index=False, sheet_name="DataSheet")

    plugin = ScadaExcelParserPlugin()
    context = PipelineContext(target_path=tmp_path, temp_dir=tmp_path, output_dir=tmp_path)
    
    results = plugin.parse(excel_path, context)
    table_key = f"{excel_path.stem}_DataSheet"
    assert table_key in results
    
    df_parsed = results[table_key]
    
    # Exactly 2 data rows should remain ("TAG-01" and "TAG-02")
    assert len(df_parsed) == 2, f"Expected 2 data rows, but got {len(df_parsed)} (unit header row was incorrectly included in data)"
    
    cols = list(df_parsed.columns)
    assert any("2026" in str(c) and "m3/h" in str(c) for c in cols), f"Expected combined column for '2026 m3/h', got {cols}"


def test_multilevel_header_with_numbers(tmp_path: Path):
    """
    Test multi-level headers where second level headers are numeric tokens ('2026', '2027', '2028').
    Naive digit heuristic sets data_start_idx = 1, incorrectly making row 1 a data row.
    """
    excel_path = tmp_path / "scada_multilevel_headers.xlsx"
    
    raw_data = [
        ["Station 100", "Station 100", "Station 200"],
        ["2026", "2027", "2028"],
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
    ]
    df_raw = pd.DataFrame(raw_data)
    df_raw.to_excel(excel_path, header=False, index=False, sheet_name="Sheet1")

    plugin = ScadaExcelParserPlugin()
    context = PipelineContext(target_path=tmp_path, temp_dir=tmp_path, output_dir=tmp_path)
    
    results = plugin.parse(excel_path, context)
    table_key = f"{excel_path.stem}_Sheet1"
    assert table_key in results
    
    df_parsed = results[table_key]
    assert len(df_parsed) == 2, f"Expected 2 data rows, but got {len(df_parsed)}"
    
    cols = list(df_parsed.columns)
    assert any("Station 100" in str(c) and "2026" in str(c) for c in cols), f"Expected combined column for 'Station 100 2026', got {cols}"
