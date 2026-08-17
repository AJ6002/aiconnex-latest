"""
aiconnex_agent/memory/backends/factory.py
=============================================
Backend selection: reads AICONNEX_MEMORY_BACKEND ("local_fake" default,
"mem0" opt-in) and returns a module-level singleton SemanticMemoryBackend.
Mirrors the get_event_store()/reset_event_store() singleton pattern from
Phase 5a.1, for the same test-isolation reasons.

mem0 is never imported unless AICONNEX_MEMORY_BACKEND=mem0 is explicitly
set - local_fake and factory have zero transitive dependency on mem0ai.
"""

from __future__ import annotations

import os
from typing import Optional

from agentic.memory.backends.base import SemanticMemoryBackend
from agentic.memory.backends.local_fake import LocalFakeBackend

_default_backend: Optional[SemanticMemoryBackend] = None


def _build_backend() -> SemanticMemoryBackend:
    backend_name = os.getenv("AICONNEX_MEMORY_BACKEND", "local_fake")

    if backend_name == "local_fake":
        return LocalFakeBackend()

    if backend_name == "mem0":
        # Lazy import: mem0_adapter.py itself guards the `mem0ai` dependency
        # and raises a clear RuntimeError if it isn't installed.
        from agentic.memory.backends.mem0_adapter import Mem0Backend
        return Mem0Backend()

    raise ValueError(
        f"Unknown AICONNEX_MEMORY_BACKEND='{backend_name}'. Expected 'local_fake' or 'mem0'."
    )


def get_semantic_backend() -> SemanticMemoryBackend:
    """Return the process-wide default SemanticMemoryBackend singleton."""
    global _default_backend
    if _default_backend is None:
        _default_backend = _build_backend()
    return _default_backend


def reset_semantic_backend() -> None:
    """Reset the default singleton so the next get_semantic_backend() rebuilds it fresh."""
    global _default_backend
    _default_backend = None
