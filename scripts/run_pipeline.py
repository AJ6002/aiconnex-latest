"""
run_pipeline.py  —  AIConnex Generic Pipeline Test Runner
==========================================================
Drives the full 9-node microservice architecture end-to-end for ANY dataset
passed via CLI or Python import.

Architecture coverage
---------------------
  Node 1 : Dataset Profiler      (port 8000) — profile, family detect, DAG mapping
  Node 2 : DAG Orchestrator      (port 8001) — pipeline run + status polling
  Node 3 : Recipe Orchestrator   (port 8002) — recipe compile (verified via status)
  Node 4 : Prepare API           (port 8003) — impute / encode / scale
  Node 5 : Feature Engineering   (port 8004) — lag, poly, PCA, select
  Node 6 : Split API             (port 8005) — train / val / test partition
  Node 7 : Train API             (port 8006) — aiconnex_ml HPO training
  Node 8 : Evaluate API          (port 8007) — VG_2 advisory gate + metrics
  Node 9 : Deploy API            (port 8008) — final_model copy + endpoint

Artifacts exported to --output directory
-----------------------------------------
  training_manifest_{run_id}.json   — full merged manifest
  splits/  train.csv, val.csv, test.csv
  model_{run_id}.pkl                — trained model
  scaler_{run_id}.pkl               — feature scaler (if present)
  predictions_{run_id}.csv          — test-set predictions + actuals
  report_{run_id}.md                — human-readable Markdown report

CLI Usage
---------
  # Single dataset
  python run_pipeline.py --dataset data/raw/insurance.csv --target charges --output workspace_data/insurance_run

  # House prices
  python run_pipeline.py --dataset testing_ds/house_prices_log.csv --target SalePrice_log --output workspace_data/house_prices_run

  # Insurance premiums
  python run_pipeline.py --dataset testing_ds/insurance.csv --target charges --output workspace_data/insurance_run

  # Manufacturing anomaly (no explicit target — auto-detected)
  python run_pipeline.py --dataset testing_ds/ds_3/manufacturing.csv --output workspace_data/manufacturing_run

  # Batch: run all built-in datasets
  python run_pipeline.py --batch

  # Dry-run: check services, parse args, do NOT execute
  python run_pipeline.py --dataset testing_ds/insurance.csv --dry-run

Python API Usage
----------------
  from run_pipeline import PipelineRunner

  runner = PipelineRunner(
      dataset_path="testing_ds/insurance.csv",
      target_column="charges",
      output_dir="workspace_data/insurance_run",
  )
  result = runner.run()   # returns PipelineResult dict
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import pickle
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ── Resolve paths relative to THIS script (aic/) ─────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent          # aic/
ROOT_DIR  = BASE_DIR.parent                          # project root (AICONNEX/)

# ── Service registry ──────────────────────────────────────────────────────────
SERVICES: Dict[str, int] = {
    "Dataset Profiler":        8000,
    "DAG Orchestrator":        8001,
    "Recipe Orchestrator":     8002,
    "Prepare API":             8003,
    "Feature Engineering API": 8004,
    "Split API":               8005,
    "Train API":               8006,
    "Evaluate API":            8007,
    "Deploy API":              8008,
}

# ── Built-in test dataset registry ───────────────────────────────────────────
# Paths are tried in order; first existing path wins.
def _pick(*paths: Path) -> str:
    """Return the first path that exists as a string, else the last as fallback."""
    for p in paths:
        if p.exists():
            return str(p)
    return str(paths[-1])

BUILTIN_DATASETS: List[Dict[str, Any]] = [
    # ── Manufacturing / Anomaly ───────────────────────────────────────────────
    {
        "name": "Manufacturing Process (Anomaly / Regression)",
        "path": _pick(
            BASE_DIR / "testing_ds" / "ds_3" / "manufacturing.csv",
            ROOT_DIR / "data" / "raw" / "Multi-stage continuous-flow manufacturing process.csv",
        ),
        "target": None,
        "output": "workspace_data/manufacturing_run",
    },
    {
        "name": "Equipment Anomaly Detection",
        "path": _pick(
            BASE_DIR / "testing_ds" / "ds_4" / "equipment_anomaly_data.csv",
        ),
        "target": None,
        "output": "workspace_data/equipment_anomaly_run",
    },
    # ── Regression benchmarks ─────────────────────────────────────────────────
    {
        "name": "Medical Insurance Premiums (Linear Regression)",
        "path": _pick(
            ROOT_DIR / "data" / "raw" / "insurance.csv",
            BASE_DIR / "testing_ds" / "insurance.csv",
        ),
        "target": "charges",
        "output": "workspace_data/insurance_run",
    },
    {
        "name": "House Prices Advanced Regression",
        "path": _pick(
            ROOT_DIR / "data" / "raw" / "house_prices" / "train.csv",
            BASE_DIR / "testing_ds" / "house_prices_train.csv",
        ),
        "target": "SalePrice",
        "output": "workspace_data/house_prices_run",
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# Console helpers
# ═════════════════════════════════════════════════════════════════════════════

def _p(msg: str) -> None:
    """Print with ASCII fallback for Windows consoles."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

def _c(color: str, msg: str) -> str:
    return f"{color}{msg}{RESET}"

def _banner(title: str, width: int = 60) -> None:
    _p("")
    _p(_c(BOLD, "=" * width))
    _p(_c(BOLD, f"  {title}"))
    _p(_c(BOLD, "=" * width))

def _step(n: int, total: int, msg: str) -> None:
    _p(f"\n{_c(CYAN, f'[{n}/{total}]')} {_c(BOLD, msg)}")

def _ok(msg: str)   -> None: _p(f"  {_c(GREEN,  '[OK]')}  {msg}")
def _warn(msg: str) -> None: _p(f"  {_c(YELLOW, '[WARN]')} {msg}")
def _fail(msg: str) -> None: _p(f"  {_c(RED,    '[FAIL]')} {msg}")
def _info(msg: str) -> None: _p(f"         {msg}")


# ═════════════════════════════════════════════════════════════════════════════
# PipelineResult  — structured return from a run
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineResult:
    dataset_path:      str
    target_column:     Optional[str]
    output_dir:        str

    # Node outputs
    run_id:            str             = ""
    dag_id:            str             = ""
    algorithm_family:  str             = ""
    suggested_task:    str             = ""
    detected_target:   Optional[str]   = None

    profile:           Dict[str, Any]  = field(default_factory=dict)
    manifest_path:     Optional[str]   = None

    # Split paths
    train_path:        Optional[str]   = None
    val_path:          Optional[str]   = None
    test_path:         Optional[str]   = None

    # Artifact paths
    model_path:        Optional[str]   = None
    scaler_path:       Optional[str]   = None
    predictions_path:  Optional[str]   = None
    report_path:       Optional[str]   = None

    # Metrics
    metrics:           Dict[str, Any]  = field(default_factory=dict)
    vg2_advisory:      Dict[str, Any]  = field(default_factory=dict)
    deployed_file:     Optional[str]   = None
    endpoint_url:      Optional[str]   = None

    # Status
    success:           bool            = False
    error:             Optional[str]   = None
    duration_seconds:  float           = 0.0
    node_timings:      Dict[str, float] = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════════════
# PipelineRunner
# ═════════════════════════════════════════════════════════════════════════════

class PipelineRunner:
    """
    Drives the full 9-node AIConnex pipeline for a single dataset.

    Parameters
    ----------
    dataset_path : str | Path
        Absolute or relative path to the input file (CSV, TXT, JSON).
        Relative paths are resolved from BASE_DIR (aic/).
    target_column : str, optional
        Override the auto-detected target column.
    output_dir : str | Path
        Directory where all exported artifacts will be written.
    poll_timeout : int
        Maximum seconds to wait for the pipeline to complete (default 600).
    poll_interval : int
        Seconds between status polls (default 3).
    dry_run : bool
        If True, skip execution; only validate services and print plan.
    verbose : bool
        Print per-step log entries from the DAG orchestrator.
    """

    TOTAL_STEPS = 9   # matches 9-node architecture

    def __init__(
        self,
        dataset_path: str | Path,
        target_column: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
        poll_timeout: int = 600,
        poll_interval: int = 3,
        dry_run: bool = False,
        verbose: bool = True,
        family_override: Optional[str] = None,
    ) -> None:
        # Resolve paths
        ds = Path(dataset_path)
        if not ds.is_absolute():
            if (BASE_DIR / ds).exists():
                ds = BASE_DIR / ds
            elif (ROOT_DIR / ds).exists():
                ds = ROOT_DIR / ds
            elif ds.exists():
                ds = ds.resolve()
            else:
                ds = BASE_DIR / ds
        self.dataset_path   = ds.resolve()
        self.target_column  = target_column
        self.poll_timeout   = poll_timeout
        self.poll_interval  = poll_interval
        self.dry_run        = dry_run
        self.verbose        = verbose
        self.family_override = family_override

        # Output directory
        if output_dir is None:
            stem = self.dataset_path.stem.replace(" ", "_")
            output_dir = BASE_DIR / "workspace_data" / f"{stem}_run"
        out = Path(output_dir)
        if not out.is_absolute():
            out = BASE_DIR / out
        self.output_dir = out

        # Internal state
        self._result: PipelineResult = PipelineResult(
            dataset_path=str(self.dataset_path),
            target_column=target_column,
            output_dir=str(self.output_dir),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def run(self) -> PipelineResult:
        """Execute the full pipeline and return a PipelineResult."""
        t0 = time.time()
        _banner(f"AIConnex Pipeline Runner  —  {self.dataset_path.name}")

        try:
            # ── Pre-Step: Universal ZIP Compiler for .zip input archives ──────
            if self.dataset_path.suffix.lower() == ".zip":
                _p(_c(CYAN, f"\n[ZIP Ingestion] Detected .zip archive → invoking aiconnex_zip_compiler..."))
                try:
                    from services.aiconnex_zip_compiler import UnifiedCompiler
                except ImportError:
                    sys.path.insert(0, str(ROOT_DIR))
                    from services.aiconnex_zip_compiler import UnifiedCompiler

                compiled_dir = self.output_dir / "compiled"
                compiler = UnifiedCompiler(self.dataset_path, compiled_dir)
                comp_res = compiler.compile()

                if not comp_res.success or not comp_res.merged_files:
                    raise PipelineError(f"ZIP Compiler failed: {comp_res.error}")

                _ok(f"ZIP compiled in {comp_res.duration_seconds}s → {len(comp_res.merged_files)} group dataset(s)")
                _info(f"Join Audit: {comp_res.artifacts.join_audit_json}")
                _info(f"Schema Map: {comp_res.artifacts.schema_map_json}")

                # Use the first merged CSV as the dataset input for the 9-node pipeline
                self.dataset_path = Path(comp_res.merged_files[0])
                self._result.dataset_path = str(self.dataset_path)

            self._step1_health_check()
            if self.dry_run:
                _p(_c(YELLOW, "\n  [DRY-RUN] Services healthy. Skipping execution."))
                self._result.success = True
                return self._result

            self._step2_profile_dataset()
            self._step3_override_target()
            self._step4_start_pipeline()
            self._step5_poll_pipeline()
            self._step6_export_artifacts()
            self._step7_generate_report()

            self._result.success = True

        except PipelineError as exc:
            _fail(str(exc))
            self._result.error = str(exc)

        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            _fail(f"Unexpected error: {exc}")
            _p(tb)
            self._result.error = str(exc)

        finally:
            self._result.duration_seconds = round(time.time() - t0, 2)
            _banner("Run Complete")
            self._print_summary()

        return self._result

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: Health check all 9 nodes
    # ──────────────────────────────────────────────────────────────────────────

    def _step1_health_check(self) -> None:
        _step(1, self.TOTAL_STEPS, "Health Check — all 9 nodes")
        all_up = True
        for name, port in SERVICES.items():
            t0 = time.time()
            try:
                r = requests.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=3)
                elapsed = round(time.time() - t0, 3)
                if r.status_code == 200:
                    _ok(f"{name:<26} ::{port}  ({elapsed}s)")
                else:
                    _warn(f"{name:<26} ::{port}  HTTP {r.status_code}")
                    all_up = False
            except requests.exceptions.ConnectionError:
                _fail(f"{name:<26} ::{port}  OFFLINE")
                all_up = False

        if not all_up:
            raise PipelineError(
                "One or more services are OFFLINE.\n"
                "  Start them first:  python start_all.py"
            )
        _ok("All 9 nodes are online.")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2: Profile dataset  (Node 1 — port 8000)
    # ──────────────────────────────────────────────────────────────────────────

    def _step2_profile_dataset(self) -> None:
        _step(2, self.TOTAL_STEPS, f"Dataset Profiler (node 1, :8000) — {self.dataset_path.name}")
        t0 = time.time()

        if not self.dataset_path.exists():
            raise PipelineError(f"Dataset not found: {self.dataset_path}")

        mime = "text/plain" if self.dataset_path.suffix == ".txt" else "text/csv"

        with open(self.dataset_path, "rb") as fh:
            resp = requests.post(
                "http://127.0.0.1:8000/api/v1/profile",
                files={"file": (self.dataset_path.name, fh, mime)},
                timeout=60,
            )

        if resp.status_code != 200:
            raise PipelineError(
                f"Profiler failed ({resp.status_code}): {resp.text[:400]}"
            )

        data    = resp.json()
        profile = data["profile"]
        self._result.profile          = profile
        self._result.detected_target  = profile.get("detected_target")
        self._result.algorithm_family = profile.get("algorithm_family", "?")
        self._result.suggested_task   = profile.get("suggested_task", "?")
        self._result.dag_id           = profile.get("recommended_dag_id", "?")

        elapsed = round(time.time() - t0, 2)
        self._result.node_timings["profiler"] = elapsed

        num_rows = profile.get("dataset_info", {}).get("num_rows", profile.get("num_rows", "?"))
        num_cols = profile.get("dataset_info", {}).get("num_columns", profile.get("num_columns", "?"))
        _ok(f"Profiled in {elapsed}s")
        _info(f"Rows:   {num_rows}  |  Cols: {num_cols}")
        _info(f"Family: {self._result.algorithm_family}")
        _info(f"DAG:    {self._result.dag_id}")
        _info(f"Task:   {self._result.suggested_task}")
        _info(f"Target: {self._result.detected_target or '(auto)'}")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3: Inject target override if user supplied one
    # ──────────────────────────────────────────────────────────────────────────

    def _step3_override_target(self) -> None:
        if self.family_override:
            _step(3, self.TOTAL_STEPS, f"Family Override → '{self.family_override}'")
            _warn(f"Overriding algorithm family to '{self.family_override}'")
            self._result.profile["algorithm_family"] = self.family_override
            self._result.algorithm_family = self.family_override
            
            # Assign a fallback default DAG ID for that family
            fallback_ids = {
                "Classification": "DAG_001",
                "Regression": "DAG_414",
                "Anomaly Detection": "DAG_573",
                "Clustering": "DAG_820",
                "Time-Series": "DAG_1059",
            }
            if self.family_override in fallback_ids:
                self._result.profile["recommended_dag_id"] = fallback_ids[self.family_override]
                self._result.dag_id = fallback_ids[self.family_override]
                _ok(f"Assigned default DAG for {self.family_override}: {self._result.dag_id}")
            return

        if not self.target_column:
            return

        _step(3, self.TOTAL_STEPS, f"Target Override → '{self.target_column}'")
        if self._result.detected_target != self.target_column:
            _warn(
                f"Profiler detected '{self._result.detected_target}', "
                f"overriding with '{self.target_column}'"
            )
            self._result.profile["detected_target"] = self.target_column
            self._result.detected_target = self.target_column
        else:
            _ok(f"Target '{self.target_column}' matches profiler detection.")

        # Update family and suggested task to Supervised Regression
        self._result.profile["algorithm_family"] = "Regression"
        self._result.profile["suggested_task"]   = "Regression"
        self._result.profile["recommended_dag_id"] = "DAG_414"
        self._result.algorithm_family = "Regression"
        self._result.suggested_task   = "Regression"
        self._result.dag_id           = "DAG_414"
        _ok("Updated ML track to Supervised Regression (DAG_414)")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4: Start pipeline  (Node 2 — port 8001)
    # ──────────────────────────────────────────────────────────────────────────

    def _step4_start_pipeline(self) -> None:
        _step(4, self.TOTAL_STEPS, "DAG Orchestrator (node 2, :8001) — launching pipeline")
        t0 = time.time()

        resp = requests.post(
            "http://127.0.0.1:8001/api/v1/pipeline/run",
            json={"profile": self._result.profile},
            timeout=15,
        )

        if resp.status_code != 200:
            raise PipelineError(
                f"Pipeline start failed ({resp.status_code}): {resp.text[:400]}"
            )

        data = resp.json()
        self._result.run_id = data["dag_id"]
        elapsed = round(time.time() - t0, 2)
        self._result.node_timings["orchestrator_start"] = elapsed

        _ok(f"Pipeline accepted in {elapsed}s")
        _info(f"run_id: {self._result.run_id}")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5: Poll pipeline until completion (nodes 3-9 execute server-side)
    # ──────────────────────────────────────────────────────────────────────────

    def _step5_poll_pipeline(self) -> None:
        _step(5, self.TOTAL_STEPS,
              f"Polling pipeline  (timeout={self.poll_timeout}s, interval={self.poll_interval}s)")

        url      = f"http://127.0.0.1:8001/api/v1/pipeline/{self._result.run_id}/status"
        logged   = 0
        deadline = time.time() + self.poll_timeout
        last_pct = 0

        while time.time() < deadline:
            try:
                r = requests.get(url, timeout=10)
            except requests.exceptions.RequestException as exc:
                _warn(f"Poll error: {exc}")
                time.sleep(self.poll_interval)
                continue

            if r.status_code != 200:
                _warn(f"Status poll returned HTTP {r.status_code}")
                time.sleep(self.poll_interval)
                continue

            data     = r.json()
            status   = data.get("status")
            pct      = data.get("progress_pct", 0)
            step_now = data.get("current_step", "")
            logs     = data.get("logs", [])

            # Print new log lines from the server
            if self.verbose:
                for entry in logs[logged:]:
                    lvl = entry.get("level", "INFO")
                    msg = entry.get("message", "")
                    ts  = entry.get("timestamp", "")
                    color = GREEN if lvl == "SUCCESS" else (YELLOW if lvl == "WARNING" else "")
                    _p(f"     {_c(color, f'[{lvl}]')} {ts}  {msg}")
            logged = len(logs)

            # Progress bar
            if pct != last_pct:
                bar_len = 30
                filled  = int(bar_len * pct / 100)
                bar     = "#" * filled + "-" * (bar_len - filled)
                _p(f"\r  [{bar}] {pct}%  {step_now:<40}", )
                last_pct = pct

            if status == "completed":
                results = data.get("results", {})
                _p("")
                _ok(f"Pipeline COMPLETED at {pct}%")
                _info(f"Model:    {results.get('model_name', '?')}")
                _info(f"Deployed: {results.get('deployed_file', '?')}")

                # Stash server results into our result object
                self._result.metrics       = results.get("metrics", {})
                self._result.deployed_file = results.get("deployed_file")
                self._result.endpoint_url  = results.get("endpoint_url")

                # Collect paths from final server state
                self._result.train_path   = data.get("train_path")
                self._result.val_path     = data.get("val_path")
                self._result.test_path    = data.get("test_path")
                self._result.model_path   = data.get("model_path")
                self._result.scaler_path  = data.get("scaler_path")
                self._result.manifest_path = data.get("manifest_path")

                # Also check inside run.results for path overrides
                if not self._result.model_path:
                    self._result.model_path = results.get("model_path")

                # Grab VG2 advisory from evaluation if available
                self._result.vg2_advisory = results.get("vg2_advisory", {})
                self._result.node_timings["pipeline_total"] = round(
                    time.time() - (deadline - self.poll_timeout), 2
                )
                return

            if status == "failed":
                _p("")
                raise PipelineError(
                    f"Pipeline FAILED at step: {step_now}\n"
                    f"  Check the logs above for the root cause."
                )

            time.sleep(self.poll_interval)

        _p("")
        _warn(f"Timed out after {self.poll_timeout}s at {last_pct}% progress.")
        _info("Partial results may be available in workspace_data/")
        # Don't raise — allow partial artifact export
        self._result.error = f"Poll timeout after {self.poll_timeout}s"

    # ──────────────────────────────────────────────────────────────────────────
    # Step 6: Collect + export all artifacts to output_dir
    # ──────────────────────────────────────────────────────────────────────────

    def _step6_export_artifacts(self) -> None:
        _step(6, self.TOTAL_STEPS, f"Exporting artifacts → {self.output_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "splits").mkdir(exist_ok=True)

        run_id = self._result.run_id

        # ── 6a: Copy manifest ─────────────────────────────────────────────────
        manifest_path = self._resolve_manifest_path(run_id)
        if manifest_path and Path(manifest_path).exists():
            dst = self.output_dir / f"training_manifest_{run_id}.json"
            shutil.copy(manifest_path, dst)
            self._result.manifest_path = str(dst)
            _ok(f"Manifest  → {dst.name}")
        else:
            _warn("Manifest not found, skipping.")

        # ── 6b: Copy splits ───────────────────────────────────────────────────
        for split_label in ("train", "val", "test"):
            path_attr = f"{split_label}_path"
            src_path  = getattr(self._result, path_attr, None)

            # Fallback: search workspace_data for this run
            if not src_path or not Path(src_path).exists():
                src_path = self._find_workspace_file(f"{split_label}_run_{run_id[:8]}.csv")

            if src_path and Path(src_path).exists():
                dst = self.output_dir / "splits" / f"{split_label}.csv"
                shutil.copy(src_path, dst)
                setattr(self._result, path_attr, str(dst))
                _ok(f"{split_label.capitalize()} split → splits/{split_label}.csv")
            else:
                _warn(f"{split_label.capitalize()} split not found.")

        # ── 6c: Copy model ────────────────────────────────────────────────────
        model_src = self._result.model_path
        if not model_src or not Path(model_src).exists():
            model_src = self._find_workspace_file(f"model_run_{run_id[:8]}.pkl")

        if model_src and Path(model_src).exists():
            dst = self.output_dir / f"model_{run_id}.pkl"
            shutil.copy(model_src, dst)
            self._result.model_path = str(dst)
            _ok(f"Model     → {dst.name}  ({Path(model_src).stat().st_size // 1024} KB)")
        else:
            _warn("Model file not found, skipping.")

        # ── 6d: Copy scaler ───────────────────────────────────────────────────
        scaler_src = self._result.scaler_path
        if not scaler_src or not Path(scaler_src).exists():
            scaler_src = self._find_workspace_file(f"scaler_run_{run_id[:8]}.pkl")

        if scaler_src and Path(scaler_src).exists():
            dst = self.output_dir / f"scaler_{run_id}.pkl"
            shutil.copy(scaler_src, dst)
            self._result.scaler_path = str(dst)
            _ok(f"Scaler    → {dst.name}")
        else:
            _info("No scaler artifact found (may not be present for all tasks).")

        # ── 6e: Generate predictions CSV ─────────────────────────────────────
        self._generate_predictions_csv(run_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Step 7: Write Markdown report
    # ──────────────────────────────────────────────────────────────────────────

    def _step7_generate_report(self) -> None:
        _step(7, self.TOTAL_STEPS, "Generating Markdown report")
        r    = self._result
        now  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path = self.output_dir / f"report_{r.run_id}.md"

        def fmt_metric(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.6f}"
            return str(v)

        metrics_md = "\n".join(
            f"| `{k}` | {fmt_metric(v)} |"
            for k, v in r.metrics.items()
        ) if r.metrics else "| — | no metrics recorded |"

        timing_md = "\n".join(
            f"| {k} | {v}s |"
            for k, v in r.node_timings.items()
        ) if r.node_timings else "| — | — |"

        vg2 = r.vg2_advisory
        vg2_md = (
            f"**Score:** {vg2.get('score', 'N/A')}  |  "
            f"**Passed:** {'YES' if vg2.get('passed') else 'NO'}  |  "
            f"**Mode:** {vg2.get('mode', 'advisory')}\n\n"
            + ("\n".join(f"- {w}" for w in vg2.get("warnings", [])) or "_No warnings_")
        ) if vg2 else "_VG_2 advisory data not available._"

        splits_md = (
            f"| Train | `{r.train_path or 'N/A'}` |\n"
            f"| Val   | `{r.val_path   or 'N/A'}` |\n"
            f"| Test  | `{r.test_path  or 'N/A'}` |"
        )

        report = f"""# AIConnex Pipeline Run Report

> **Generated:** {now}

---

## Run Summary

| Field           | Value |
|----------------|-------|
| **Run ID**      | `{r.run_id}` |
| **Dataset**     | `{r.dataset_path}` |
| **Target**      | `{r.target_column or r.detected_target or 'auto'}` |
| **DAG ID**      | `{r.dag_id}` |
| **Family**      | {r.algorithm_family} |
| **Task**        | {r.suggested_task} |
| **Duration**    | {r.duration_seconds}s |
| **Status**      | {'SUCCESS' if r.success else 'FAILED'} |

---

## Evaluation Metrics

| Metric | Value |
|--------|-------|
{metrics_md}

---

## Advisory VG_2 Gate

{vg2_md}

---

## Data Splits

| Split | Path |
|-------|------|
{splits_md}

---

## Artifacts

| Artifact | Path |
|----------|------|
| Manifest  | `{r.manifest_path or 'N/A'}` |
| Model     | `{r.model_path    or 'N/A'}` |
| Scaler    | `{r.scaler_path   or 'N/A'}` |
| Predictions | `{r.predictions_path or 'N/A'}` |
| Report    | `{path}` |

---

## Deployment

| Field | Value |
|-------|-------|
| Deployed File | `{r.deployed_file or 'N/A'}` |
| Endpoint URL  | {r.endpoint_url  or 'N/A'} |

---

## Node Timings

| Node | Duration |
|------|---------|
{timing_md}

---

## Architecture Coverage

The following 9-node architecture was exercised:

```
[1] Dataset Profiler      :8000  — column stats, family detect, DAG map
[2] DAG Orchestrator      :8001  — pipeline run dispatch + status polling
[3] Recipe Orchestrator   :8002  — compile prepare / feat / split / train recipes
[4] Prepare API           :8003  — impute, encode, scale
[5] Feature Engineering   :8004  — lag, poly, PCA, select
[6] Split API             :8005  — train / val / test partition
[7] Train API             :8006  — aiconnex_ml HPO training + VG_1 gate
[8] Evaluate API          :8007  — metrics + VG_2 advisory gate
[9] Deploy API            :8008  — final_model copy + endpoint registration
```

---

*Generated by `run_pipeline.py` — AIConnex Generic Pipeline Test Runner*
"""

        path.write_text(report, encoding="utf-8")
        self._result.report_path = str(path)
        _ok(f"Report    → {path.name}")

    # ──────────────────────────────────────────────────────────────────────────
    # Artifact helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_manifest_path(self, run_id: str) -> Optional[str]:
        """Try multiple locations where the manifest might be written."""
        candidates = [
            BASE_DIR / "services" / "workspace_data" / run_id / f"training_manifest_{run_id}.json",
            BASE_DIR / "workspace_data" / run_id / f"training_manifest_{run_id}.json",
            BASE_DIR / "services" / "workspace_data" / run_id / "manifest.json",
            BASE_DIR / "workspace_data" / run_id / "manifest.json",
            BASE_DIR / "workspace_data" / f"training_manifest_{run_id}.json",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        # Search recursively
        for p in (BASE_DIR / "services" / "workspace_data").rglob(f"training_manifest_{run_id}*.json"):
            return str(p)
        for p in (BASE_DIR / "workspace_data").rglob(f"training_manifest_{run_id}*.json"):
            return str(p)
        for p in (BASE_DIR / "services" / "workspace_data").rglob("manifest.json"):
            if run_id in str(p):
                return str(p)
        return None

    def _find_workspace_file(self, name: str) -> Optional[str]:
        """Search workspace_data recursively for a file by name or run_id pattern."""
        # Normalize name to find split label
        split_label = None
        for label in ("train", "val", "test"):
            if label in name:
                split_label = label
                break

        run_id = self._result.run_id
        
        # Search paths
        search_dirs = [
            BASE_DIR / "services" / "workspace_data",
            BASE_DIR / "workspace_data",
        ]
        
        # 1. Search inside run_id directory
        for sd in search_dirs:
            run_dir = sd / run_id
            if run_dir.exists():
                if split_label:
                    for p in run_dir.glob(f"*split_{split_label}_*.csv"):
                        return str(p)
                    for p in run_dir.glob(f"*{split_label}*.csv"):
                        return str(p)
                if "model" in name:
                    for p in run_dir.glob("trained_*.pkl"):
                        return str(p)
                    for p in run_dir.glob("model_*.pkl"):
                        return str(p)
                if "scaler" in name:
                    for p in run_dir.glob("scaler_*.pkl"):
                        return str(p)

        # 2. General search
        for sd in search_dirs:
            if not sd.exists():
                continue
            if (sd / name).exists():
                return str(sd / name)
            for p in sd.rglob(name):
                if p.is_file():
                    return str(p)
            # Pattern search
            parts = name.split("_run_")
            if len(parts) == 2:
                prefix, run_part = parts[0], parts[1].replace(".csv", "").replace(".pkl", "")
                # Map prefix to new unified names
                mapped_prefixes = [prefix]
                if prefix in ("train", "val", "test"):
                    mapped_prefixes.append(f"split_{prefix}")
                elif prefix == "model":
                    mapped_prefixes.append("trained")
                
                for mp in mapped_prefixes:
                    for p in sd.rglob(f"*{mp}*"):
                        if p.is_file() and (run_id in str(p) or run_part in str(p)):
                            return str(p)
        return None

    def _generate_predictions_csv(self, run_id: str) -> None:
        """Load test split + model, run predict, save predictions_{run_id}.csv."""
        test_src = self._result.test_path
        model_src = self._result.model_path

        if not (test_src and Path(test_src).exists()):
            _warn("Test split not available — skipping predictions export.")
            return
        if not (model_src and Path(model_src).exists()):
            _warn("Model file not available — skipping predictions export.")
            return

        try:
            import pandas as pd
            import numpy as np

            df = pd.read_csv(test_src)
            target = self._result.target_column or self._result.detected_target

            X = df.drop(columns=[target], errors="ignore") if target else df.copy()
            X = X.select_dtypes(include=[np.number]).fillna(0)

            # Apply scaler if present
            scaler_src = self._result.scaler_path
            if scaler_src and Path(scaler_src).exists():
                with open(scaler_src, "rb") as fh:
                    scaler = pickle.load(fh)
                X_arr = scaler.transform(X)
            else:
                X_arr = X.values

            with open(model_src, "rb") as fh:
                model = pickle.load(fh)

            y_pred = model.predict(X_arr)

            out_df = df.copy()
            out_df["_predicted"] = y_pred

            dst = self.output_dir / f"predictions_{run_id}.csv"
            out_df.to_csv(dst, index=False)
            self._result.predictions_path = str(dst)
            _ok(f"Predictions → {dst.name}  ({len(out_df)} rows)")

        except Exception as exc:
            _warn(f"Predictions export skipped: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # Summary printer
    # ──────────────────────────────────────────────────────────────────────────

    def _print_summary(self) -> None:
        r = self._result
        status_line = (
            _c(GREEN, "[PASS]  Pipeline run SUCCEEDED")
            if r.success
            else _c(RED, "[FAIL]  Pipeline run FAILED")
        )
        _p(status_line)
        _info(f"Dataset  : {r.dataset_path}")
        _info(f"Output   : {r.output_dir}")
        _info(f"Run ID   : {r.run_id}")
        _info(f"Duration : {r.duration_seconds}s")
        if r.metrics:
            _info(f"Metrics  : " + "  |  ".join(
                f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                for k, v in list(r.metrics.items())[:6]
            ))
        if r.report_path:
            _info(f"Report   : {r.report_path}")
        if r.error:
            _warn(f"Error    : {r.error}")
        _p("")


# ═════════════════════════════════════════════════════════════════════════════
# Custom exception
# ═════════════════════════════════════════════════════════════════════════════

class PipelineError(Exception):
    """Raised when any pipeline node returns an unrecoverable error."""


# ═════════════════════════════════════════════════════════════════════════════
# Batch mode
# ═════════════════════════════════════════════════════════════════════════════

def run_batch(
    extra_datasets: Optional[List[Dict[str, Any]]] = None,
    poll_timeout: int = 600,
    verbose: bool = True,
) -> List[PipelineResult]:
    """
    Run all built-in test datasets sequentially.

    Parameters
    ----------
    extra_datasets : list[dict], optional
        Additional datasets to append. Each dict must have 'path' key;
        'target' and 'output' are optional.
    poll_timeout : int
        Per-dataset timeout (seconds).

    Returns
    -------
    list[PipelineResult]
    """
    all_ds = list(BUILTIN_DATASETS)
    if extra_datasets:
        all_ds.extend(extra_datasets)

    # Filter to only existing files
    runnable = [d for d in all_ds if Path(d["path"]).exists()]
    skipped  = [d for d in all_ds if not Path(d["path"]).exists()]

    if skipped:
        _p(_c(YELLOW, f"\n[BATCH] Skipping {len(skipped)} missing datasets:"))
        for s in skipped:
            _p(f"  - {s['path']}")

    _banner(f"AIConnex Batch Pipeline  —  {len(runnable)} datasets")

    results: List[PipelineResult] = []
    for i, ds in enumerate(runnable, 1):
        _p(_c(CYAN, f"\n{'=' * 60}"))
        _p(_c(CYAN, f"  [{i}/{len(runnable)}] {ds.get('name', ds['path'])}"))
        _p(_c(CYAN, f"{'=' * 60}"))

        runner = PipelineRunner(
            dataset_path=ds["path"],
            target_column=ds.get("target"),
            output_dir=ds.get("output"),
            poll_timeout=poll_timeout,
            verbose=verbose,
        )
        result = runner.run()
        results.append(result)

        # Brief cooldown between runs so services aren't overwhelmed
        if i < len(runnable):
            _p(_c(YELLOW, "  Pausing 5s before next run..."))
            time.sleep(5)

    # ── Batch summary table ───────────────────────────────────────────────────
    _banner("Batch Run Summary")
    _p(f"  {'Dataset':<40} {'Status':<10} {'Duration':>10}  {'Key Metric'}")
    _p("  " + "-" * 80)
    for res in results:
        status = _c(GREEN, "PASS") if res.success else _c(RED, "FAIL")
        ds_name = Path(res.dataset_path).name[:38]
        dur     = f"{res.duration_seconds}s"
        metric  = ""
        if res.metrics:
            first_k, first_v = next(iter(res.metrics.items()))
            metric = f"{first_k}={first_v:.4f}" if isinstance(first_v, float) else f"{first_k}={first_v}"
        _p(f"  {ds_name:<40} {status:<10} {dur:>10}  {metric}")

    passed = sum(1 for r in results if r.success)
    _p(_c(BOLD, f"\n  {passed}/{len(results)} datasets passed."))
    return results


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description=(
            "AIConnex Generic Pipeline Test Runner\n"
            "Drives the full 9-node architecture end-to-end for any dataset."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py --dataset data/raw/insurance.csv --target charges --output workspace_data/insurance_run
  python run_pipeline.py --dataset testing_ds/insurance.csv --target charges --output workspace_data/insurance_run
  python run_pipeline.py --dataset testing_ds/house_prices_log.csv --target SalePrice_log --output workspace_data/house_run
  python run_pipeline.py --batch
  python run_pipeline.py --dataset testing_ds/insurance.csv --dry-run
        """,
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dataset", metavar="PATH",
        help="Path to dataset file (CSV, TXT, JSON). Relative to aic/ directory.",
    )
    mode.add_argument(
        "--batch", action="store_true",
        help="Run all built-in test datasets sequentially.",
    )

    p.add_argument(
        "--target", metavar="COLUMN",
        help="Override the auto-detected target column name.",
    )
    p.add_argument(
        "--output", metavar="DIR",
        help="Output directory for artifacts. Relative to aic/. Default: workspace_data/<stem>_run",
    )
    p.add_argument(
        "--timeout", type=int, default=600, metavar="SECONDS",
        help="Max seconds to wait for pipeline to complete (default: 600).",
    )
    p.add_argument(
        "--interval", type=int, default=3, metavar="SECONDS",
        help="Polling interval in seconds (default: 3).",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-step log lines from the DAG orchestrator.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Check services and validate args only — do NOT execute the pipeline.",
    )
    p.add_argument(
        "--list-datasets", action="store_true",
        help="List all registered built-in datasets and exit.",
    )
    p.add_argument(
        "--family", metavar="FAMILY",
        help="Override the detected algorithm family (e.g. Regression, Classification, Anomaly Detection).",
    )

    return p


def main() -> int:
    # Windows UTF-8 fix
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = _build_parser()
    args   = parser.parse_args()

    # ── --list-datasets ───────────────────────────────────────────────────────
    if args.list_datasets:
        _banner("Built-in Test Datasets")
        for i, ds in enumerate(BUILTIN_DATASETS, 1):
            exists  = Path(ds["path"]).exists()
            status  = _c(GREEN, "[FOUND]") if exists else _c(RED, "[MISSING]")
            _p(f"  {i}. {status} {ds.get('name', ds['path'])}")
            _p(f"       Path:   {ds['path']}")
            _p(f"       Target: {ds.get('target', 'auto-detect')}")
            _p(f"       Output: {ds.get('output', 'auto')}")
        return 0

    # ── --batch ───────────────────────────────────────────────────────────────
    if args.batch:
        results = run_batch(
            poll_timeout=args.timeout,
            verbose=not args.quiet,
        )
        return 0 if all(r.success for r in results) else 1

    # ── single dataset ────────────────────────────────────────────────────────
    if not args.dataset:
        parser.print_help()
        return 1

    runner = PipelineRunner(
        dataset_path=args.dataset,
        target_column=args.target,
        output_dir=args.output,
        poll_timeout=args.timeout,
        poll_interval=args.interval,
        dry_run=args.dry_run,
        verbose=not args.quiet,
        family_override=args.family,
    )
    result = runner.run()
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
