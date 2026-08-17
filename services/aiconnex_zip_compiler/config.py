"""
config.py - Compiler Configuration Loader
==========================================
Loads external YAML configurations with Pydantic validation and fallbacks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic import BaseModel
import yaml


class CompilerConfig(BaseModel):
    output_format: str = "parquet"
    preserve_original: bool = True
    enable_provenance: bool = True
    enable_parquet_export: bool = True
    max_upload_gb: int = 20
    max_archive_gb: int = 20
    max_uncompressed_gb: int = 100
    max_files: int = 10000
    max_archive_depth: int = 5
    max_expansion_factor: int = 10
    require_key_validation: bool = True
    allow_many_to_many: bool = False
    auto_execute_threshold: float = 0.90
    confirmation_threshold: float = 0.75
    canonical_timezone: str = "UTC"
    workspace_root: str = "data/compiler"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "CompilerConfig":
        # Check root configs/compiler.yaml or relative configs
        candidate_paths = [
            Path(__file__).resolve().parents[2] / "configs" / "compiler.yaml",
            Path(__file__).resolve().parents[1] / "configs" / "compiler.yaml",
            Path("configs/compiler.yaml").resolve(),
        ]
        default_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
        target_path = path or default_path
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                flat = {
                    **raw.get("compiler", {}),
                    **raw.get("security", {}),
                    **raw.get("join", {}),
                    **raw.get("agent", {}),
                    **raw.get("time", {}),
                    **raw.get("storage", {}),
                }
                return cls(**flat)
            except Exception:
                return cls()
        return cls()
