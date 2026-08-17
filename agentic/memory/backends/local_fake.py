"""
aiconnex_agent/memory/backends/local_fake.py
================================================
Deterministic, zero-LLM, zero-network test double for SemanticMemoryBackend.
Ranks stored texts by token-overlap ratio against the query - no embeddings,
no vector math, no external service. This is the default backend
(AICONNEX_MEMORY_BACKEND unset or "local_fake") and is what every existing
test in this repo exercises. It is never meant to be the production
recall engine - that is Mem0Backend (see mem0_adapter.py) - but it proves
the write/read wiring is correct before any real dependency is introduced.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from agentic.memory.backends.base import SemanticMemoryBackend


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class LocalFakeBackend(SemanticMemoryBackend):
    """In-memory keyword-overlap semantic search stand-in."""

    def __init__(self):
        self._records: List[Dict[str, Any]] = []

    def add(self, text: str, metadata: Dict[str, Any]) -> None:
        self._records.append({"text": text, "metadata": dict(metadata)})

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for record in self._records:
            record_tokens = _tokenize(record["text"])
            if not record_tokens:
                continue
            overlap = len(query_tokens & record_tokens)
            score = overlap / len(query_tokens | record_tokens) if overlap else 0.0
            scored.append({"text": record["text"], "metadata": record["metadata"], "score": score})

        scored.sort(key=lambda r: r["score"], reverse=True)
        return [r for r in scored if r["score"] > 0][:limit]
