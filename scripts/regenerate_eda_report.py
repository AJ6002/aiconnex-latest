#!/usr/bin/env python3
"""
scripts/regenerate_eda_report.py
Generates a fresh, lightweight, 100% AI-Connex Coral Orange EDA report for the compiled dataset.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))
from backend.profiler_service import generate_exhaustive_html_report

compiled_csv = "services/workspace_data/global/runs/run_4d9a27ef/all_groups_combined.csv"
if not os.path.exists(compiled_csv):
    compiled_csv = "services/workspace_data/global/runs/run_dda8f22f/all_groups_combined.csv"

out_dir = "services/workspace_data/global/reports"
os.makedirs(out_dir, exist_ok=True)

targets = [
    os.path.join(out_dir, "eda_report.html"),
    os.path.join(out_dir, "eda_run_20250115_143022.html"),
    os.path.join(out_dir, "eda_run_4d9a27ef.html"),
]

print(f"Generating fresh Coral Orange EDA report from: {compiled_csv}")
res = generate_exhaustive_html_report(
    file_path=os.path.abspath(compiled_csv),
    output_html_path=os.path.abspath(targets[0]),
    title="AIConnex Data Profiling Report"
)
print("Result:", res)

if res.get("success"):
    import shutil
    for t in targets[1:]:
        shutil.copyfile(targets[0], t)
        print(f"Copied to: {t}")
    file_size_mb = os.path.getsize(targets[0]) / (1024 * 1024)
    print(f"✅ Generated report file size: {file_size_mb:.2f} MB (Ultra fast load)")
