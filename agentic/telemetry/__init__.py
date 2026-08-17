"""
aiconnex_agent/telemetry/__init__.py
======================================
Cross-Cutting Telemetry & Observability Infrastructure.

Provides a single import surface for all telemetry needs across agent nodes:
  - AgentTelemetry: singleton MLflow run manager
  - get_telemetry(): factory returning the process-level singleton
  - Specialized emitters: PlannerEmitter, ScoutEmitter, PlatformEmitter, MemoryEmitter
  - init_llm_tracing(): LangChain autolog initializer

All calls degrade gracefully to no-ops when mlflow is not installed.
"""

from agentic.telemetry.tracker import AgentTelemetry, get_telemetry
from agentic.telemetry.llm_tracer import init_llm_tracing
from agentic.telemetry.emitters import (
    PlannerEmitter,
    ScoutEmitter,
    PlatformEmitter,
    MemoryEmitter,
)

__all__ = [
    "AgentTelemetry",
    "get_telemetry",
    "init_llm_tracing",
    "PlannerEmitter",
    "ScoutEmitter",
    "PlatformEmitter",
    "MemoryEmitter",
]
