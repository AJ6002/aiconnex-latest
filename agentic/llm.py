"""
aiconnex_agent/llm.py - Unified Multi-Backend LLM Engine
==========================================================
Provides a single entry point, get_llm(), that returns the configured LLM
client for LangGraph agent node calls. Backends:

  AICONNEX_LLM_BACKEND=openrouter (default primary) - OpenRouter Qwen 2.5 Coder 32B Instruct
  AICONNEX_LLM_BACKEND=ollama                       - local/cloud Ollama fallback
  AICONNEX_LLM_BACKEND=openai                       - standard OpenAI client

MLflow LangChain autolog tracing is bootstrapped via the cross-cutting
telemetry service: agentic.telemetry.llm_tracer.init_llm_tracing().
This module is now a pure LLM factory — it does not own observability.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load local .env if present
load_dotenv()

def _enable_mlflow_tracing() -> None:
    """Bootstrap LangChain autolog via the cross-cutting telemetry service.

    Delegates to agentic.telemetry.llm_tracer.init_llm_tracing().
    Kept for backward compatibility — internal calls use this shim.
    """
    try:
        from agentic.telemetry.llm_tracer import init_llm_tracing
        init_llm_tracing()
    except Exception as exc:
        logger.debug(f"[LLM] Could not init LLM tracing: {exc}")



def get_openrouter_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """
    Returns an initialized ChatOpenAI client connected to OpenRouter Qwen API.
    Primary SOTA backend for AIConnex agents (OpenRouter Qwen 2.5 Coder 32B).
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-openai is not installed. Install with: pip install langchain-openai\n"
                "Also set OPENROUTER_API_KEY in your .env."
            ) from exc

    model_name = model or os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-coder-32b-instruct")
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    url = base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env or environment "
            "before using AICONNEX_LLM_BACKEND=openrouter."
        )

    logger.info(f"[OpenRouterLLM] Initializing OpenRouter client model='{model_name}' url='{url}'")
    
    # Initialize MLflow Tracing SDK
    _enable_mlflow_tracing()

    max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "1000"))
    # No timeout was previously set here, so a slow/unresponsive OpenRouter
    # endpoint could hang the calling Flask request (and any graph node that
    # invokes this LLM) indefinitely. Bound it with a sane default.
    timeout_s = float(os.getenv("OPENROUTER_TIMEOUT_S", "20"))

    return ChatOpenAI(
        model=model_name,
        openai_api_key=key,
        openai_api_base=url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_s,
        default_headers={"HTTP-Referer": "https://aiconnex.ai", "X-Title": "AIConnex MLOps OS"},
    )


def get_ollama_llm(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """Returns an initialized LangChain Ollama LLM client for offline fallback."""
    from langchain_community.llms import Ollama
    model_name = model or os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")
    host_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    logger.info(f"[OllamaLLM] Initializing Ollama client model='{model_name}' host='{host_url}'")
    _enable_mlflow_tracing()
    return Ollama(
        model=model_name,
        base_url=host_url,
        temperature=temperature,
    )


def get_openai_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    """Returns an initialized LangChain ChatOpenAI client."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Install with: pip install langchain-openai"
        ) from exc

    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    logger.info(f"[OpenAILLM] Initializing ChatOpenAI client model='{model_name}'")
    _enable_mlflow_tracing()
    return ChatOpenAI(
        model=model_name,
        api_key=key,
        temperature=temperature,
    )


def get_llm(**kwargs: Any) -> Any:
    """
    Returns the configured LLM client per AICONNEX_LLM_BACKEND.
    Default: "openrouter" (OpenRouter Qwen 2.5 Coder 32B).
    """
    backend = os.getenv("AICONNEX_LLM_BACKEND", "openrouter").strip().lower()

    if backend in ("openrouter", "qwen", "openrouter_qwen"):
        return get_openrouter_llm(**kwargs)
    if backend == "ollama":
        return get_ollama_llm(**kwargs)
    if backend == "openai":
        return get_openai_llm(**kwargs)

    logger.warning(f"Unknown AICONNEX_LLM_BACKEND='{backend}', defaulting to OpenRouter Qwen.")
    return get_openrouter_llm(**kwargs)

