with open("services/workspace_data/global/reports/eda_report.html", "r", encoding="utf-8") as f:
    text = f.read()

print("Contains #FF6B35:", "#FF6B35" in text)
print("Count of #FF6B35 occurrences:", text.count("#FF6B35"))
print("Contains #0d6efd:", "#0d6efd" in text)
print("Count of #0d6efd occurrences:", text.count("#0d6efd"))
print("Contains aiconnex-light-theme-master:", "aiconnex-light-theme-master" in text)
