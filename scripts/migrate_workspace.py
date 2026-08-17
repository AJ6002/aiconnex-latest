import os
import shutil
import sqlite3
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_DATA = os.path.join(BASE_DIR, "services", "workspace_data")
SCRATCH_UPLOADS = os.path.join(BASE_DIR, "scratch", "uploads")
SESSION_DB = os.path.join(BASE_DIR, "backend", "session_store.db")

TENANT_ID = "global"
TENANT_DIR = os.path.join(WORKSPACE_DATA, TENANT_ID)

def migrate():
    print(f"[Migrate] Initializing unified workspace at: {TENANT_DIR}")
    
    # Subdirectories
    subdirs = [
        "runs",
        "uploads",
        "manifests",
        "sessions/jane",
        "sessions/langgraph",
        "models",
        "reports"
    ]
    for sub in subdirs:
        os.makedirs(os.path.join(TENANT_DIR, sub), exist_ok=True)
        
    # 1. Move run_* directories into global/runs/
    if os.path.exists(WORKSPACE_DATA):
        for item in os.listdir(WORKSPACE_DATA):
            if item == TENANT_ID:
                continue
            src = os.path.join(WORKSPACE_DATA, item)
            if os.path.isdir(src) and item.startswith("run_"):
                dest = os.path.join(TENANT_DIR, "runs", item)
                if not os.path.exists(dest):
                    print(f"  Moving run dir: {item} -> global/runs/{item}")
                    shutil.move(src, dest)
                else:
                    print(f"  Destination already exists: {dest}")

    # 2. Move scratch/uploads into global/uploads/
    if os.path.exists(SCRATCH_UPLOADS):
        for f in os.listdir(SCRATCH_UPLOADS):
            src = os.path.join(SCRATCH_UPLOADS, f)
            dest = os.path.join(TENANT_DIR, "uploads", f)
            if os.path.isfile(src):
                print(f"  Moving upload: {f} -> global/uploads/{f}")
                shutil.copy2(src, dest)
                os.remove(src)
        # Delete scratch/uploads folder per Q3
        try:
            shutil.rmtree(SCRATCH_UPLOADS)
            print("  Deleted legacy scratch/uploads/ directory.")
        except Exception as e:
            print(f"  Warning deleting scratch/uploads: {e}")

    # 3. Export existing session history from session_store.db to global/sessions/jane/
    if os.path.exists(SESSION_DB):
        try:
            conn = sqlite3.connect(SESSION_DB)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT session_id FROM chat_history")
            sessions = [r[0] for r in cur.fetchall()]
            for sid in sessions:
                cur.execute("SELECT role, content, timestamp FROM chat_history WHERE session_id = ? ORDER BY id ASC", (sid,))
                turns = [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in cur.fetchall()]
                out_file = os.path.join(TENANT_DIR, "sessions", "jane", f"session_{sid}.json")
                with open(out_file, "w", encoding="utf-8") as out_f:
                    json.dump({"session_id": sid, "tenant_id": TENANT_ID, "turns": turns}, out_f, indent=2)
                print(f"  Exported session {sid} ({len(turns)} turns) -> sessions/jane/")
            conn.close()
        except Exception as e:
            print(f"  Warning exporting session store: {e}")

    print("[Migrate] Workspace migration complete!")

if __name__ == "__main__":
    migrate()
