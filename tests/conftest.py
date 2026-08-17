"""
conftest.py - Root pytest configuration
=======================================
Applies to every test directory in the repository.
Disables the LLM-driven intelligence layer for the whole test suite when present.
"""

from __future__ import annotations

import sys
import importlib
import pytest

class PackageAliasLoader:
    ALIASES = {
        "aiconnex_agent": "agentic",
        "aiconnex_zip_compiler": "services.aiconnex_zip_compiler",
        "aiconnex_ml": "services.aiconnex_ml",
    }
    @classmethod
    def find_module(cls, fullname, path=None):
        for prefix, target_prefix in cls.ALIASES.items():
            if fullname == prefix or fullname.startswith(prefix + "."):
                return cls
        return None

    @classmethod
    def load_module(cls, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        for prefix, target_prefix in cls.ALIASES.items():
            if fullname == prefix or fullname.startswith(prefix + "."):
                real_name = fullname.replace(prefix, target_prefix, 1)
                real_mod = importlib.import_module(real_name)
                sys.modules[fullname] = real_mod
                return real_mod
        raise ImportError(fullname)

if PackageAliasLoader not in sys.meta_path:
    sys.meta_path.insert(0, PackageAliasLoader)

try:
    from services.aiconnex_zip_compiler.intelligence.llm_client import (
        DISABLE_ENV_VAR,
        reset_availability_cache,
    )
    HAS_LLM_CLIENT = True
except Exception:
    try:
        from aiconnex_zip_compiler.intelligence.llm_client import (
            DISABLE_ENV_VAR,
            reset_availability_cache,
        )
        HAS_LLM_CLIENT = True
    except Exception:
        HAS_LLM_CLIENT = False


@pytest.fixture(autouse=True)
def _disable_llm_for_tests(monkeypatch):
    """Force the intelligence layer into deterministic-only mode for all tests when available."""
    if HAS_LLM_CLIENT:
        monkeypatch.setenv(DISABLE_ENV_VAR, "1")
        reset_availability_cache()
        yield
        reset_availability_cache()
    else:
        yield
