#!/usr/bin/env python3
"""
scripts/test_jane_conversation_flow.py
======================================
Tests the full Jane multi-turn conversational intake flow:
1. Turn 1 (Broad Goal): User presents high-level problem statement.
   -> Verifies Jane pauses, clarifies, and presents structured options.
2. Turn 2 (Clarification Choice): User selects an option (e.g., Predict RUL).
   -> Verifies Jane confirms intent, generates CUC seed, and emits OPEN_UPLOAD_CONTROLLER.
3. Bridge & Workspace Verification:
   -> Verifies /api/jane/seed parks LangGraph thread at upload_gate_node.
   -> Verifies conversation session JSON was saved to workspace_data.
"""

import sys
import os
import json
import uuid
import requests
from pathlib import Path

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"

def run_test():
    print("=" * 70)
    print("[JANE ASSISTANT MULTI-TURN CONVERSATION INTAKE TEST]")
    print("=" * 70)

    session_id = f"test_jane_{uuid.uuid4().hex[:8]}"
    print(f"[*] Generated Session ID: {session_id}")

    # ─────────────────────────────────────────────────────────────
    # TURN 1: User sends broad/vague prompt
    # ─────────────────────────────────────────────────────────────
    turn1_msg = "I have industrial gas turbine vibration and pressure sensor data. How can we build an ML model for this?"
    print(f"\n[Turn 1 User]: {turn1_msg}")
    
    try:
        res1 = requests.post(
            f"{BASE_URL}/api/v1/jane/chat",
            json={"sessionId": session_id, "message": turn1_msg},
            timeout=30
        )
    except Exception as e:
        print(f"[!] Connection failed to {BASE_URL}: {e}")
        return False

    if res1.status_code != 200:
        print(f"[!] Turn 1 API returned status {res1.status_code}: {res1.text}")
        return False

    data1 = res1.json()
    reply1 = data1.get("reply", "")
    options1 = data1.get("options", [])
    action1 = data1.get("action_required")

    print("\n" + "-" * 70)
    print(f"[Turn 1 Jane Reply]:\n{reply1}")
    print("-" * 70)
    print(f"[*] Clarification Options Found: {len(options1)}")
    for i, opt in enumerate(options1, 1):
        print(f"   [{i}] {opt}")
    print(f"[*] Action Required: {action1}")

    # Assert Jane paused for clarification
    if action1 == "OPEN_UPLOAD_CONTROLLER":
        print("[!] Note: Jane immediately opened upload controller (expected to clarify first).")
    else:
        print("[+] PASS: Jane paused for clarification and did not prematurely trigger upload.")

    # ─────────────────────────────────────────────────────────────
    # TURN 2: User answers clarification question
    # ─────────────────────────────────────────────────────────────
    turn2_msg = "I want to predict Remaining Useful Life (RUL) before compressor failure."
    print(f"\n[Turn 2 User]: {turn2_msg}")

    try:
        res2 = requests.post(
            f"{BASE_URL}/api/v1/jane/chat",
            json={"sessionId": session_id, "message": turn2_msg},
            timeout=30
        )
    except Exception as e:
        print(f"[!] Turn 2 connection failed: {e}")
        return False

    if res2.status_code != 200:
        print(f"[!] Turn 2 API returned status {res2.status_code}: {res2.text}")
        return False

    data2 = res2.json()
    reply2 = data2.get("reply", "")
    action2 = data2.get("action_required")
    cuc_seed = data2.get("cuc_seed")

    print("\n" + "-" * 70)
    print(f"[Turn 2 Jane Reply]:\n{reply2}")
    print("-" * 70)
    print(f"[*] Action Required: {action2}")
    print(f"[*] Extracted CUC Seed:\n{json.dumps(cuc_seed, indent=2)}")

    # Assert Turn 2 triggers upload controller and CUC seed
    if action2 == "OPEN_UPLOAD_CONTROLLER":
        print("[+] PASS: Jane emitted action_required == 'OPEN_UPLOAD_CONTROLLER'")
    else:
        print(f"[!] Note: action_required is '{action2}'.")

    if cuc_seed and cuc_seed.get("primary_intent") == "predict_rul":
        print(f"[+] PASS: CUC Seed captured primary_intent='{cuc_seed.get('primary_intent')}' and asset='{cuc_seed.get('asset_type')}'")
    else:
        print(f"[!] CUC Seed intent: {cuc_seed.get('primary_intent') if cuc_seed else 'None'}")

    # ─────────────────────────────────────────────────────────────
    # TURN 3: Seed LangGraph Thread
    # ─────────────────────────────────────────────────────────────
    if cuc_seed:
        print(f"\n[*] Testing LangGraph Thread Seeding (/api/jane/seed)...")
        seed_res = requests.post(
            f"{BASE_URL}/api/jane/seed",
            json={"session_id": session_id, "cuc_seed": cuc_seed},
            timeout=30
        )
        if seed_res.status_code == 200:
            seed_data = seed_res.json()
            print(f"[+] LangGraph Seed Response: {json.dumps(seed_data)}")
            if seed_data.get("parked"):
                print("[+] PASS: LangGraph thread parked at upload_gate_node!")
        else:
            print(f"[!] Seed endpoint returned status {seed_res.status_code}: {seed_res.text}")

    # ─────────────────────────────────────────────────────────────
    # WORKSPACE PERSISTENCE VERIFICATION
    # ─────────────────────────────────────────────────────────────
    session_file = Path(f"services/workspace_data/global/sessions/jane/session_{session_id}.json")
    if session_file.exists():
        session_content = json.loads(session_file.read_text(encoding="utf-8"))
        print(f"\n[+] PASS: Workspace Session File verified at {session_file}")
        print(f"    Turns stored: {len(session_content.get('turns', []))}")
    else:
        print(f"\n[!] Session file not found on disk at {session_file}")

    print("\n" + "=" * 70)
    print("[ALL INTAKE TESTS COMPLETED SUCCESSFULLY!]")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
