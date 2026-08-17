import urllib.request

try:
    url = "http://localhost:8000/api/v1/reports/run_20250115_143022/eda_report.html?theme=light"
    req = urllib.request.urlopen(url)
    html = req.read().decode("utf-8")
    print(f"HTTP Status: {req.status}")
    print(f"Contains 'aiconnex-light-theme-master': {'aiconnex-light-theme-master' in html}")
    print(f"Contains Coral Orange '#FF6B35': {'#FF6B35' in html}")
    print(f"Contains theme-light on body: {'theme-light' in html}")
except Exception as e:
    print(f"Error: {e}")
