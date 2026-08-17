"""
aiconnex_agent/memory/backends/mem0_adapter.py
==================================================
Real production SemanticMemoryBackend, backed by mem0. LLM extraction reuses
the SAME Ollama model as the rest of the agent (OLLAMA_MODEL, e.g.
gpt-oss:120b-cloud) - quality over local latency, consistent with
aiconnex_agent/llm.py. Only the embedder is required to be a real Ollama
model (nomic-embed-text) since Ollama Cloud does not serve an embeddings
endpoint the same way - so a one-time `ollama pull nomic-embed-text` is
still needed, but no separate local LLM (e.g. llama3.1) is forced anymore.
Vector storage is an embedded on-disk Qdrant instance - no server, no
account. This module is only imported when AICONNEX_MEMORY_BACKEND=mem0
is explicitly set (see factory.py) - its absence must never break any
other part of the test suite.

Guarded import: `mem0ai` is an OPTIONAL dependency. If it is not installed,
Mem0Backend.__init__ raises a clear, actionable RuntimeError rather than
letting an ImportError propagate from module import time.

NOTE: telemetry is disabled defensively via MEM0_TELEMETRY before the mem0
import, since mem0 ships PostHog telemetry on by default (see
docs/superpowers/plans/2026-07-29-phase5a6-mem0-sprint2.md for the known
upstream issue where this env var alone does not always fully suppress
background telemetry threads).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

os.environ.setdefault("MEM0_TELEMETRY", "false")

try:
    from mem0 import Memory as _Mem0Memory
except ImportError:
    _Mem0Memory = None

from agentic.memory.backends.base import SemanticMemoryBackend

_DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_DEFAULT_EMBEDDER_MODEL = os.getenv("AICONNEX_MEM0_EMBEDDER_MODEL", "nomic-embed-text")
_DEFAULT_QDRANT_PATH = os.getenv("AICONNEX_MEM0_QDRANT_PATH", "./.mem0_qdrant")
_EMBEDDING_DIMS = 768  # nomic-embed-text output dimension


def _build_mem0_config() -> Dict[str, Any]:
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        llm_config = {
            "provider": "openai",
            "config": {
                "model": os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-coder-32b-instruct"),
                "api_key": openrouter_key,
                "openai_base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            },
        }
    else:
        llm_model = os.getenv("AICONNEX_MEM0_LLM_MODEL") or os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")
        llm_config = {
            "provider": "ollama",
            "config": {
                "model": llm_model,
                "ollama_base_url": _DEFAULT_OLLAMA_BASE_URL,
            },
        }

    return {
        "llm": llm_config,
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": _DEFAULT_EMBEDDER_MODEL,
                "ollama_base_url": _DEFAULT_OLLAMA_BASE_URL,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": _DEFAULT_QDRANT_PATH,
                "embedding_model_dims": _EMBEDDING_DIMS,
            },
        },
    }


class Mem0Backend(SemanticMemoryBackend):
    """Production semantic memory backend: mem0 + local Ollama + embedded Qdrant."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if _Mem0Memory is None:
            raise RuntimeError(
                "mem0ai is not installed. Install with: pip install mem0ai\n"
                "Also ensure Ollama is running locally and the embedder model is pulled: "
                f"ollama pull {_DEFAULT_EMBEDDER_MODEL}"
            )
        self._mem = _Mem0Memory.from_config(config or _build_mem0_config())

    def add(self, text: str, metadata: Dict[str, Any]) -> None:
        user_id = str(metadata.get("subject_id", "agent"))
        self._mem.add(
            [{"role": "system", "content": text}],
            user_id=user_id,
            metadata=metadata,
        )

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        raw = self._mem.search(query, limit=limit)
        results = raw.get("results", raw) if isinstance(raw, dict) else raw
        return [
            {
                "text": r.get("memory", r.get("text", "")),
                "metadata": {k: v for k, v in r.items() if k not in {"memory", "text", "score"}},
                "score": r.get("score", 0.0),
            }
            for r in (results or [])
        ]
