"""
schemas.py - Request and Response Pydantic Models for Compiler API
==================================================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CompilationJobRequest(BaseModel):
    user_intent: Optional[str] = Field(None, description="Industrialist natural language objective")
    strategy_override: Optional[str] = Field(None, description="Optional forced assembly strategy")
    interactive: bool = False
    enable_intelligence: bool = True


class CompilationJobStatusResponse(BaseModel):
    job_id: str
    state: str
    success: bool
    state_history: List[str]
    duration_seconds: float
    output_dir: str
    merged_files: List[str]
    combined_file: Optional[str] = None
    combined_parquet: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)


class FileInspectResponse(BaseModel):
    filename: str
    detected_format: str
    is_valid: bool
    details: Dict[str, Any] = Field(default_factory=dict)
