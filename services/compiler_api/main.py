"""
main.py - FastAPI Service for AIConnex Compiler
================================================
Exposes Section 55 REST endpoints for ingestion, compilation, provenance, and inspection.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
from services.aiconnex_zip_compiler.models import CompilerWorkspace
from .schemas import (
    CompilationJobStatusResponse,
    FileInspectResponse,
)

app = FastAPI(
    title="AIConnex Data Studio Compiler API",
    description="Dedicated microservice for industrial dataset ingestion, understanding, and compilation.",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active jobs memory cache
JOB_STORE: dict[str, dict] = {}


@app.get("/api/v1/compiler/health")
def health_check():
    return {"status": "healthy", "service": "AIConnex Compiler API", "version": "1.0.0"}


@app.post("/api/v1/compiler/jobs", response_model=CompilationJobStatusResponse)
async def submit_compilation_job(
    file: UploadFile = File(...),
    strategy_override: Optional[str] = Form(None),
    interactive: bool = Form(False),
    enable_intelligence: bool = Form(True),
):
    """
    POST /api/v1/compiler/jobs
    Uploads a dataset archive (.zip, .csv, .parquet, .mat, etc.) and compiles it.
    """
    job_id = uuid.uuid4().hex[:8]
    workspace = CompilerWorkspace(job_id=job_id)
    workspace.setup()

    # Save uploaded file to incoming/
    incoming_file = workspace.incoming / file.filename
    with open(incoming_file, "wb") as f:
        content = await file.read()
        f.write(content)

    output_dir = workspace.unified

    compiler = UnifiedCompiler(
        zip_path=incoming_file,
        output_dir=output_dir,
        strategy_override=strategy_override,
        interactive=interactive,
        enable_intelligence=enable_intelligence,
    )
    result = compiler.compile()

    response_data = {
        "job_id": job_id,
        "state": result.state.value if hasattr(result, "state") else ("COMPILED" if result.success else "FAILED"),
        "success": result.success,
        "state_history": getattr(result, "state_history", []),
        "duration_seconds": result.duration_seconds,
        "output_dir": str(output_dir),
        "merged_files": result.merged_files,
        "combined_file": result.combined_file,
        "combined_parquet": str(result.artifacts.combined_parquet) if result.artifacts and result.artifacts.combined_parquet else None,
        "error": result.error,
        "artifacts": result.artifacts.to_dict() if result.artifacts else {},
    }
    JOB_STORE[job_id] = response_data
    return response_data


@app.get("/api/v1/compiler/jobs/{job_id}", response_model=CompilationJobStatusResponse)
def get_job_status(job_id: str):
    """
    GET /api/v1/compiler/jobs/{job_id}
    Retrieves status, state history, and artifact links for a job.
    """
    if job_id not in JOB_STORE:
        workspace = CompilerWorkspace(job_id=job_id)
        report_path = workspace.reports / "compiler_report.json"
        if report_path.exists():
            data = json.loads(report_path.read_text(encoding="utf-8"))
            return {
                "job_id": job_id,
                "state": "COMPILED",
                "success": True,
                "state_history": ["RECEIVED", "COMPILED"],
                "duration_seconds": data.get("duration_seconds", 0.0),
                "output_dir": str(workspace.unified),
                "merged_files": data.get("output_files", {}).get("per_group_csv", []),
                "combined_file": data.get("output_files", {}).get("combined_csv"),
                "combined_parquet": data.get("output_files", {}).get("combined_parquet"),
                "error": None,
                "artifacts": {},
            }
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JOB_STORE[job_id]


@app.get("/api/v1/compiler/jobs/{job_id}/report")
def get_job_report(job_id: str):
    """
    GET /api/v1/compiler/jobs/{job_id}/report
    Returns compiler_report.json.
    """
    workspace = CompilerWorkspace(job_id=job_id)
    report_file = workspace.reports / "compiler_report.json"
    if not report_file.exists():
        report_file = workspace.unified / "compiler_report.json"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="compiler_report.json not found for job.")
    return JSONResponse(content=json.loads(report_file.read_text(encoding="utf-8")))


@app.get("/api/v1/compiler/jobs/{job_id}/lineage")
def get_job_lineage(job_id: str):
    """
    GET /api/v1/compiler/jobs/{job_id}/lineage
    Returns provenance lineage.json.
    """
    workspace = CompilerWorkspace(job_id=job_id)
    lineage_file = workspace.reports / "lineage.json"
    if not lineage_file.exists():
        lineage_file = workspace.unified / "lineage.json"
    if not lineage_file.exists():
        raise HTTPException(status_code=404, detail="lineage.json not found for job.")
    return JSONResponse(content=json.loads(lineage_file.read_text(encoding="utf-8")))


@app.get("/api/v1/compiler/jobs/{job_id}/output")
def download_compiled_output(job_id: str, format: str = "parquet"):
    """
    GET /api/v1/compiler/jobs/{job_id}/output?format=parquet|csv
    Downloads the primary compiled dataset file.
    """
    workspace = CompilerWorkspace(job_id=job_id)
    if format.lower() == "parquet":
        target = workspace.unified / "all_groups_combined.parquet"
        media = "application/octet-stream"
    else:
        target = workspace.unified / "all_groups_combined.csv"
        media = "text/csv"

    if not target.exists():
        # Fallback to first group file
        candidates = list(workspace.unified.glob(f"*.{format}"))
        if candidates:
            target = candidates[0]
        else:
            raise HTTPException(status_code=404, detail=f"No compiled .{format} output found for job {job_id}")

    return FileResponse(path=target, media_type=media, filename=target.name)


@app.post("/api/v1/compiler/inspect", response_model=FileInspectResponse)
async def inspect_file_format(file: UploadFile = File(...)):
    """
    POST /api/v1/compiler/inspect
    Fast schema and format inspection without full pipeline assembly.
    """
    from services.aiconnex_zip_compiler.schema_gate import SchemaGate
    import tempfile

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        gate = SchemaGate(tmp_path)
        decision = gate.evaluate()
        return {
            "filename": file.filename,
            "detected_format": decision.primary_route,
            "is_valid": decision.is_valid,
            "details": {
                "message": decision.gate_message,
                "file_count": decision.file_count,
                "detected_formats": decision.detected_formats,
            }
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
