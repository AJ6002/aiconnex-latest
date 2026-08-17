"""
aiconnex_agent/telemetry/llm_tracer.py
========================================
Extracted LangChain/MLflow autolog initializer.

Previously embedded inside aiconnex_agent/llm.py (_enable_mlflow_tracing),
this is now a proper cross-cutting service so the tracing bootstrap is
owned by the telemetry layer and not by the LLM factory.

Usage:
    from agentic.telemetry.llm_tracer import init_llm_tracing
    init_llm_tracing()   # idempotent — safe to call multiple times
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False
_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "./mlruns")


def init_llm_tracing(tracking_uri: str | None = None) -> None:
    """Enable MLflow Tracing SDK for LangChain LLM calls.

    Enables ``mlflow.langchain.autolog()`` so that every LangChain invoke()
    call (OpenRouter Qwen, Ollama, OpenAI) is automatically captured as a
    trace span in the local MLflow file store.

    Args:
        tracking_uri: Override the MLflow tracking URI. Defaults to the
                      ``MLFLOW_TRACKING_URI`` env-var or ``./mlruns``.

    This function is idempotent — repeated calls are silently ignored.
    All exceptions are swallowed so LLM usage never fails due to missing
    observability infrastructure.
    """
    global _TRACING_INITIALIZED
    if _TRACING_INITIALIZED:
        return

    try:
        import mlflow

        uri = tracking_uri or _TRACKING_URI
        os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
        mlflow.set_tracking_uri(uri)

        if hasattr(mlflow, "langchain") and hasattr(mlflow.langchain, "autolog"):
            # log_traces=False: span-per-LLM-call traces are disabled because
            # LangGraph interrupt/resume splits a single "conversation turn" across
            # multiple HTTP requests. MLflow opens a span in request-1 and cannot
            # find it in request-2, causing noisy "Span not found" WARNINGs.
            # Metrics & params are still captured via AgentTelemetry.tracker.
            mlflow.langchain.autolog(log_traces=False, disable=False)
            logger.info(
                "[LLMTracer] mlflow.langchain.autolog() enabled (traces disabled) — "
                f"metrics/params → {uri}"
            )
        else:
            logger.debug("[LLMTracer] mlflow.langchain.autolog not available in this mlflow version.")

        _TRACING_INITIALIZED = True

    except ImportError:
        logger.debug("[LLMTracer] mlflow not installed — skipping LLM autolog.")
    except Exception as exc:
        logger.debug(f"[LLMTracer] Could not enable autolog: {exc}")


def reset_llm_tracing() -> None:
    """Reset initialization flag. For testing purposes only."""
    global _TRACING_INITIALIZED
    _TRACING_INITIALIZED = False
