import os
import tempfile
import json
from pathlib import Path
import pandas as pd
import zipfile

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler, CompileResult
from services.aiconnex_zip_compiler.discovery import run_discovery

def test_excel_and_json_compilation():
    temp_dir = Path(tempfile.mkdtemp(prefix="test_multi_format_"))
    
    try:
        # 1. Create a synthetic Excel file
        df_excel = pd.DataFrame({
            "DATE_TIME": ["2026-07-23 10:00:00", "2026-07-23 10:15:00"],
            "PLANT_ID": [101, 101],
            "AC_POWER": [200.0, 210.0]
        })
        excel_path = temp_dir / "Fact_Excel.xlsx"
        df_excel.to_excel(excel_path, index=False)

        # 2. Create a synthetic JSON file
        df_json = pd.DataFrame({
            "DATE_TIME": ["2026-07-23 10:00:00", "2026-07-23 10:15:00"],
            "PLANT_ID": [101, 101],
            "AMBIENT_TEMP": [25.0, 25.5]
        })
        json_path = temp_dir / "Dim_Json.json"
        df_json.to_json(json_path, orient="records")

        # 3. Create a ZIP containing both the Excel and JSON files
        zip_path = temp_dir / "multi_format_archive.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(excel_path, arcname="Fact_Excel.xlsx")
            zf.write(json_path, arcname="Dim_Json.json")

        # Run compilation on the ZIP containing Excel and JSON
        out_dir_zip = temp_dir / "compiled_zip_output"
        compiler_zip = UnifiedCompiler(zip_path, out_dir_zip)
        res_zip = compiler_zip.compile()

        assert res_zip.success is True, f"ZIP compilation failed: {res_zip.error}"
        all_cols = set()
        for f in res_zip.merged_files:
            all_cols.update(pd.read_csv(f).columns)
        assert "ac_power" in all_cols


        # 4. Run compilation directly on a single Excel file (non-zip)
        out_dir_single = temp_dir / "compiled_single_output"
        compiler_single = UnifiedCompiler(excel_path, out_dir_single)
        res_single = compiler_single.compile()

        assert res_single.success is True, f"Single file compilation failed: {res_single.error}"
        assert len(res_single.merged_files) >= 1
        merged_df_single = pd.read_csv(res_single.merged_files[0])
        assert "ac_power" in merged_df_single.columns
        assert "plant_id" in merged_df_single.columns

        print("All multi-format tests passed successfully!")
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_excel_and_json_compilation()
