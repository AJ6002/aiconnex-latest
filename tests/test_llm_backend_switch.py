# tests/test_llm_backend_switch.py
"""
Tests for the AICONNEX_LLM_BACKEND switch (aiconnex_agent/llm.py).
Ollama is the default backend and requires no credentials to construct a
client object (LangChain's Ollama class does not connect at construction
time). The OpenAI path is exercised with a fake API key - no real network
calls are made in these tests, since ChatOpenAI also does not connect at
construction time either.
"""
import os
import pytest

from agentic.llm import get_llm, get_ollama_llm, get_openai_llm
from langchain_community.llms import Ollama


@pytest.fixture(autouse=True)
def _clean_env():
    for key in ("AICONNEX_LLM_BACKEND", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "OLLAMA_MODEL", "OLLAMA_BASE_URL"):
        os.environ.pop(key, None)
    yield
    for key in ("AICONNEX_LLM_BACKEND", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "OLLAMA_MODEL", "OLLAMA_BASE_URL"):
        os.environ.pop(key, None)


def test_get_llm_defaults_to_openrouter_when_unset(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")
    llm = get_llm()
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "qwen/qwen-2.5-coder-32b-instruct"


def test_get_llm_uses_ollama_when_explicitly_set():
    os.environ["AICONNEX_LLM_BACKEND"] = "ollama"
    llm = get_llm()
    assert isinstance(llm, Ollama)


def test_get_ollama_llm_defaults_to_cloud_model():
    llm = get_ollama_llm()
    assert llm.model == "gpt-oss:120b-cloud"
    assert llm.base_url == "http://localhost:11434"


def test_get_ollama_llm_respects_env_overrides():
    os.environ["OLLAMA_MODEL"] = "llama3.1"
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:9999"
    llm = get_ollama_llm()
    assert llm.model == "llama3.1"
    assert llm.base_url == "http://localhost:9999"


def test_get_llm_uses_openai_when_configured():
    os.environ["AICONNEX_LLM_BACKEND"] = "openai"
    os.environ["OPENAI_API_KEY"] = "sk-test-fake-key-not-real"
    llm = get_llm()
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "gpt-4o-mini"


def test_get_openai_llm_raises_clear_error_without_api_key():
    with pytest.raises(RuntimeError) as excinfo:
        get_openai_llm()
    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_get_openai_llm_raises_actionable_error_when_dependency_missing(monkeypatch):
    """Simulates langchain-openai being absent, even though it IS installed
    in this environment, by making the import fail inside get_openai_llm()."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langchain_openai":
            raise ImportError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError) as excinfo:
        get_openai_llm(api_key="sk-test-fake-key")
    assert "langchain-openai" in str(excinfo.value).lower()
    assert "pip install" in str(excinfo.value).lower()


def test_get_llm_defaults_to_openrouter_on_unknown_backend(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")
    os.environ["AICONNEX_LLM_BACKEND"] = "some_unsupported_provider"
    llm = get_llm()
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "qwen/qwen-2.5-coder-32b-instruct"


def test_get_llm_backend_selection_is_case_insensitive():
    os.environ["AICONNEX_LLM_BACKEND"] = "OLLAMA"
    llm = get_llm()
    assert isinstance(llm, Ollama)
