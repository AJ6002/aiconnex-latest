"""
dependencies.py - Dependency Injection for Compiler API
========================================================
"""

from __future__ import annotations

from pathlib import Path
from services.aiconnex_zip_compiler.config import CompilerConfig
from services.aiconnex_zip_compiler.models import CompilerWorkspace


def get_compiler_config() -> CompilerConfig:
    return CompilerConfig.load()


def get_workspace(job_id: str) -> CompilerWorkspace:
    ws = CompilerWorkspace(job_id=job_id)
    ws.setup()
    return ws
