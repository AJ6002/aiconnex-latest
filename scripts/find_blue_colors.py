with open("services/workspace_data/global/reports/eda_report.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "#0d6efd" in line or "#2563eb" in line or "#1f77b4" in line:
        print(f"Line {i+1}: {line[:120].strip()}")
