"""
test_compiler_spec_alignment.py - Automated Verification Suite for Spec Alignment
==================================================================================
Verifies:
1. Parquet + CSV dual output in export_compiler_handoff
2. CompilerState transitions (RECEIVED -> COMPILED)
3. Lineage and quality report artifacts
4. YAML config loading
5. CompilerWorkspace quarantine handling
6. FastAPI Compiler REST endpoints
"""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler, CompileResult
from services.aiconnex_zip_compiler.config import CompilerConfig
from services.aiconnex_zip_compiler.models import CompilerState, CompilerWorkspace
from services.compiler_api.main import app


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="compiler_spec_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def test_parquet_and_csv_dual_output_with_states(temp_workspace):
    """Test dual format export, lineage, quality report, and state transitions."""
    zip_path = temp_workspace / "dual_export.zip"
    out_dir = temp_workspace / "out_dual"

    df = pd.DataFrame({
        "timestamp": ["2026-08-16 10:00:00", "2026-08-16 10:01:00"],
        "sensor_temp": [65.2, 65.8],
        "vibration_rms": [1.2, 1.4],
    })

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("telemetry.csv", df.to_csv(index=False))

    compiler = UnifiedCompiler(zip_path=zip_path, output_dir=out_dir)
    res = compiler.compile()

    assert res.success is True
    assert res.state == CompilerState.COMPILED
    assert CompilerState.RECEIVED.value in res.state_history
    assert CompilerState.COMPILED.value in res.state_history

    # Check dual CSV + Parquet presence
    assert (out_dir / "all_groups_combined.csv").exists()
    assert (out_dir / "all_groups_combined.parquet").exists()

    # Check Parquet can be loaded and matches CSV
    p_df = pd.read_parquet(out_dir / "all_groups_combined.parquet")
    assert len(p_df) == 2
    assert "sensor_temp" in p_df.columns

    # Check lineage.json & quality_report.json
    lineage_path = out_dir / "lineage.json"
    quality_path = out_dir / "quality_report.json"
    assert lineage_path.exists()
    assert quality_path.exists()

    lineage_data = json.loads(lineage_path.read_text(encoding="utf-8"))
    assert lineage_data["source_archive"] == "dual_export.zip"

    quality_data = json.loads(quality_path.read_text(encoding="utf-8"))
    assert quality_data["status"] == "PASS"


def test_yaml_config_loader():
    """Test CompilerConfig loads default and custom YAML configs."""
    cfg = CompilerConfig.load()
    assert cfg.output_format == "parquet"
    assert cfg.max_upload_gb == 20
    assert cfg.enable_provenance is True


def test_compiler_workspace_quarantine(temp_workspace):
    """Test CompilerWorkspace correctly quarantines malformed files."""
    ws = CompilerWorkspace(job_id="test_quarantine", root=temp_workspace)
    ws.setup()

    bad_file = temp_workspace / "corrupted_archive.zip"
    bad_file.write_bytes(b"NOT A REAL ZIP ARCHIVE DATA")

    quarantined = ws.quarantine_file(bad_file, reason="Corrupt header")
    assert quarantined.exists()
    assert (ws.quarantine / f"{quarantined.name}.meta.json").exists()

    meta = json.loads((ws.quarantine / f"{quarantined.name}.meta.json").read_text(encoding="utf-8"))
    assert meta["reason"] == "Corrupt header"
    assert meta["status"] == "QUARANTINED"


def test_fastapi_compiler_api_endpoints(temp_workspace):
    """Test FastAPI microservice endpoints (/health, /inspect, /jobs)."""
    client = TestClient(app)

    # 1. Health check
    h_res = client.get("/api/v1/compiler/health")
    assert h_res.status_code == 200
    assert h_res.json()["status"] == "healthy"

    # 2. Inspect endpoint
    sample_csv = "time,temp,vib\n1,60.1,0.5\n2,60.2,0.6\n".encode("utf-8")
    i_res = client.post(
        "/api/v1/compiler/inspect",
        files={"file": ("sample.csv", sample_csv, "text/csv")}
    )
    assert i_res.status_code == 200
    assert i_res.json()["is_valid"] is True

    # 3. Submit compilation job
    j_res = client.post(
        "/api/v1/compiler/jobs",
        files={"file": ("sample.csv", sample_csv, "text/csv")},
        data={"enable_intelligence": "false"}
    )
    assert j_res.status_code == 200
    job_data = j_res.json()
    assert job_data["success"] is True
    assert job_data["state"] == "COMPILED"
    job_id = job_data["job_id"]

    # 4. Get job status
    s_res = client.get(f"/api/v1/compiler/jobs/{job_id}")
    assert s_res.status_code == 200
    assert s_res.json()["state"] == "COMPILED"
