"""
start_server.py — AIConnex Persistent Production Server with Heartbeat
"""
import os
import sys
import time
import threading
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ["PORT"] = "5000"

def start_backend():
    from backend.app import app
    from waitress import serve
    print("[ServerManager] Waitress WSGI Server starting on http://0.0.0.0:5000 (threads=8)...", flush=True)
    serve(app, host="0.0.0.0", port=5000, threads=8)

if __name__ == "__main__":
    t = threading.Thread(target=start_backend, daemon=True)
    t.start()
    
    # Keep main thread alive with periodic heartbeat
    while True:
        time.sleep(30)
        print("[Heartbeat] AIConnex Backend port 5000 is active and listening.", flush=True)
