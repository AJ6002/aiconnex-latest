"""
run_local_verification.py
=========================
Master runner for the full 8-layer local verification gate.
Run this script before any cloud pipeline trigger.
# Note: ASCII-only output for Windows cp1252 compatibility.

Usage:
    python run_local_verification.py

Gates (in order):
  0. Preflight     — Python version, packages, config
  1. Syntax        — py_compile on all pipeline scripts
  2. Lint          — ruff check
  3. Unit tests    — pytest tests/unit/
  4. Contract tests— pytest tests/contracts/
  5. Integration   — pytest tests/integration/

All 6 gates must pass before returning exit code 0.
"""
import os
import sys
import subprocess
import time

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR     = os.path.join(BASE_DIR, "services", "sagemaker_pipeline", "src")
VENV_PYTHON = os.path.join(BASE_DIR, "ai-connex", ".venv", "Scripts", "python.exe")
PYTHON      = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
PYTEST      = os.path.join(BASE_DIR, "ai-connex", ".venv", "Scripts", "pytest.exe")
if not os.path.exists(PYTEST):
    PYTEST = "pytest"

PIPELINE_SCRIPTS = [
    "preprocess.py", "validate_raw.py", "split.py",
    "feature_engineer.py", "validate_engineered.py",
    "train.py", "evaluate.py", "explain.py",
    "stress.py", "register_model.py",
]

GATE_RESULTS = {}


def _run(cmd: list, label: str) -> bool:
    print(f"\n{'-'*60}")
    print(f"  Running: {label}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'-'*60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"\n  {icon}  ({elapsed:.1f}s)")
    GATE_RESULTS[label] = ok
    return ok


def gate0_preflight():
    return _run(
        [PYTHON, os.path.join(BASE_DIR, "scripts", "preflight_env_check.py")],
        "Gate 0 - Preflight Environment Check"
    )


def gate1_syntax():
    cmds = [PYTHON, "-m", "py_compile"]
    for script in PIPELINE_SCRIPTS:
        cmds.append(os.path.join(SRC_DIR, script))
    return _run(cmds, "Gate 1 — Syntax Check (py_compile)")


def gate2_lint():
    return _run(
        [PYTHON, "-m", "ruff", "check", SRC_DIR, "tests/"],
        "Gate 2 — Lint (ruff)"
    )


def gate3_unit():
    return _run(
        [PYTEST, "tests/unit/", "-v", "--tb=short"],
        "Gate 3 — Unit Tests (pytest)"
    )


def gate4_contracts():
    return _run(
        [PYTEST, "tests/contracts/", "-v", "--tb=short"],
        "Gate 4 — Contract Tests (pytest)"
    )


def gate5_integration():
    return _run(
        [PYTEST, "tests/integration/", "-v", "--tb=short"],
        "Gate 5 — Integration Smoke Test (pytest)"
    )


def main():
    print("=" * 60)
    print("  LOCAL VERIFICATION SUITE - Pre-Cloud Pipeline Gate")
    print("=" * 60)

    gates = [gate0_preflight, gate1_syntax, gate2_lint,
             gate3_unit, gate4_contracts, gate5_integration]

    for gate_fn in gates:
        passed = gate_fn()
        if not passed:
            print(f"\n[STOP] Gate failed: {gate_fn.__name__}. Stopping early.")
            break

    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    all_passed = True
    for label, ok in GATE_RESULTS.items():
        icon = "[PASS]" if ok else "[FAIL]"
        print(f"  {icon}  {label}")
        if not ok:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("  [OK] ALL GATES PASSED - Safe to trigger cloud pipeline.")
        sys.exit(0)
    else:
        print("  [X] ONE OR MORE GATES FAILED - Fix issues before cloud run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
