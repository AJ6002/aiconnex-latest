"""
Node 0 - Preflight Environment Check
=====================================
Runs before any pipeline step. Validates:
  1. Python version >= 3.9
  2. All critical packages are installed and meet minimum versions
  3. config.json exists and is valid JSON
  4. All required config schema keys are present

Writes: preflight_report.json
Exits with code 1 immediately if any check fails.

NOTE: ASCII-only output for Windows cp1252 terminal compatibility.
"""
import sys
import os
import json
import importlib
import platform
from datetime import datetime
from packaging import version

# Required library minimum versions
REQUIRED_PACKAGES = {
    "pandas":    "2.0.0",
    "numpy":     "1.24.0",
    "sklearn":   "1.2.0",
    "xgboost":   "1.7.0",
    "pyarrow":   "12.0.0",
    "boto3":     "1.26.0",
    "sagemaker": "2.140.0",
}

REQUIRED_CONFIG_KEYS = ["domain", "algorithm", "schema", "thresholds", "hyperparameters"]
REQUIRED_SCHEMA_KEYS = ["target_column", "features", "time_index", "identifier"]

CONFIG_PATH = os.environ.get(
    "PIPELINE_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "services", "sagemaker_pipeline", "config", "config.json"),
)


def _ok(flag: bool) -> str:
    return "[OK]" if flag else "[FAIL]"


def check_python_version() -> dict:
    current = sys.version_info
    ok = current >= (3, 9)
    return {
        "check":    "python_version",
        "required": ">=3.9",
        "actual":   f"{current.major}.{current.minor}.{current.micro}",
        "status":   "PASS" if ok else "FAIL",
    }


def check_package_versions() -> list:
    results = []
    for pkg_name, min_ver in REQUIRED_PACKAGES.items():
        try:
            module = importlib.import_module(pkg_name)
            actual_ver = getattr(module, "__version__", "unknown")
            ok = version.parse(actual_ver) >= version.parse(min_ver)
            status = "PASS" if ok else "FAIL"
        except ImportError:
            actual_ver = "NOT_INSTALLED"
            status = "FAIL"
        results.append({
            "check":    f"package:{pkg_name}",
            "required": f">={min_ver}",
            "actual":   actual_ver,
            "status":   status,
        })
    return results


def check_config_file(config_path: str) -> list:
    results = []
    exists = os.path.isfile(config_path)
    results.append({
        "check":  "config_exists",
        "path":   config_path,
        "status": "PASS" if exists else "FAIL",
    })
    if not exists:
        return results

    try:
        with open(config_path) as f:
            config = json.load(f)
        results.append({"check": "config_valid_json", "status": "PASS"})
    except Exception as e:
        results.append({"check": "config_valid_json", "status": "FAIL", "error": str(e)})
        return results

    for key in REQUIRED_CONFIG_KEYS:
        ok = key in config
        results.append({"check": f"config_key:{key}", "status": "PASS" if ok else "FAIL"})

    schema = config.get("schema", {})
    for key in REQUIRED_SCHEMA_KEYS:
        ok = key in schema
        results.append({"check": f"schema_key:{key}", "status": "PASS" if ok else "FAIL"})

    return results


def write_report(all_checks: list, output_path: str) -> dict:
    failed = [c for c in all_checks if c.get("status") == "FAIL"]
    report = {
        "timestamp":    datetime.utcnow().isoformat() + "Z",
        "platform":     platform.platform(),
        "python":       sys.version,
        "status":       "PASSED" if not failed else "FAILED",
        "total_checks": len(all_checks),
        "failed_count": len(failed),
        "checks":       all_checks,
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    return report


def main():
    print("=" * 60)
    print("  Node 0 - Preflight Environment Check")
    print("=" * 60)

    all_checks = []

    # 1. Python version
    py_check = check_python_version()
    all_checks.append(py_check)
    print(f"{_ok(py_check['status'] == 'PASS')} Python: {py_check['actual']} (required {py_check['required']})")

    # 2. Package versions
    pkg_checks = check_package_versions()
    all_checks.extend(pkg_checks)
    for pc in pkg_checks:
        print(f"{_ok(pc['status'] == 'PASS')} {pc['check']}: {pc['actual']} (required {pc['required']})")

    # 3. Config file
    config_checks = check_config_file(CONFIG_PATH)
    all_checks.extend(config_checks)
    for cc in config_checks:
        print(f"{_ok(cc['status'] == 'PASS')} {cc['check']}")

    # Write report
    report_path = os.path.join(os.path.dirname(__file__), "..", "preflight_report.json")
    write_report(all_checks, report_path)

    failed = [c for c in all_checks if c.get("status") == "FAIL"]
    print("\n" + "=" * 60)
    if failed:
        print(f"[FAIL] PREFLIGHT FAILED - {len(failed)} check(s) failed:")
        for f in failed:
            print(f"   - {f['check']}")
        print(f"Full report: {report_path}")
        sys.exit(1)
    else:
        print(f"[OK] PREFLIGHT PASSED - all {len(all_checks)} checks passed.")
        print(f"Full report: {report_path}")


if __name__ == "__main__":
    main()
