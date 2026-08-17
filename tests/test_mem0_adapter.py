# tests/test_mem0_adapter.py
"""
Tests for Mem0Backend (Phase 5a.6 Task 4).

These tests require the OPTIONAL `mem0ai` package plus a locally running
Ollama instance with the `nomic-embed-text` embedder pulled, and network
access to the OLLAMA_MODEL cloud model (default gpt-oss:120b-cloud, same
one the rest of the agent uses) with an active ollama.com sign-in.
None of that is installed/available in the default CI/dev environment for
this repo, so this file is EXPECTED TO SKIP via pytest.importorskip -
that is the correct, intended outcome, not a failure. See
docs/superpowers/plans/2026-07-29-phase5a6-mem0-sprint2.md Task 4.
"""
import os
import pytest

mem0 = pytest.importorskip("mem0", reason="mem0ai is an optional dependency - not installed by default")

from agentic.memory.backends.mem0_adapter import Mem0Backend, _build_mem0_config

# Second, independent gate for the live-network test below: importorskip only
# protects against mem0ai being ABSENT. Once mem0ai is actually installed
# (as happened during Phase 5a.6 verification), the roundtrip test would
# otherwise run unconditionally and hang/fail against a real Ollama+Qdrant
# connection in the default test suite. Require an explicit opt-in env var
# so this test only runs when someone deliberately wants to verify the real
# integration, never as a side effect of mem0ai simply being installed.
_LIVE_INTEGRATION_ENABLED = os.getenv("AICONNEX_RUN_LIVE_MEM0_TESTS") == "1"


def test_mem0_backend_config_uses_openrouter_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")
    config = _build_mem0_config()
    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["model"] == "qwen/qwen-2.5-coder-32b-instruct"
    assert config["llm"]["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
    assert config["embedder"]["provider"] == "ollama"
    assert config["vector_store"]["provider"] == "qdrant"
    assert config["embedder"]["config"]["model"] == "nomic-embed-text"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 768


def test_mem0_backend_config_falls_back_to_ollama_when_no_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = _build_mem0_config()
    assert config["llm"]["provider"] == "ollama"
    assert config["embedder"]["provider"] == "ollama"
    assert config["vector_store"]["provider"] == "qdrant"
    assert config["embedder"]["config"]["model"] == "nomic-embed-text"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 768


@pytest.mark.skipif(
    not _LIVE_INTEGRATION_ENABLED,
    reason="Live mem0+Ollama+Qdrant roundtrip - set AICONNEX_RUN_LIVE_MEM0_TESTS=1 to run explicitly",
)
def test_mem0_backend_add_and_search_roundtrip():
    """Requires nomic-embed-text pulled locally + OLLAMA_MODEL (cloud) reachable.
    Gated behind AICONNEX_RUN_LIVE_MEM0_TESTS=1 - never runs in the default suite,
    even with mem0ai installed, since this makes a real network/model call."""
    backend = Mem0Backend()
    backend.add(
        "dataset ds_nasa_fd001: DatasetCompiled {'rows': 26898}",
        {"subject_id": "ds_nasa_fd001", "subject_type": "dataset"},
    )
    results = backend.search("NASA FD001 dataset rows", limit=5)
    assert isinstance(results, list)
    if results:
        assert "text" in results[0]
        assert "score" in results[0]


def test_mem0_backend_without_install_raises_actionable_runtime_error(monkeypatch):
    """Simulates the mem0ai-absent path even when mem0ai IS installed in this env,
    by patching the module-level _Mem0Memory sentinel back to None."""
    import agentic.memory.backends.mem0_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "_Mem0Memory", None)
    with pytest.raises(RuntimeError) as excinfo:
        adapter_module.Mem0Backend()
    assert "mem0ai" in str(excinfo.value).lower()
    assert "pip install" in str(excinfo.value).lower()
