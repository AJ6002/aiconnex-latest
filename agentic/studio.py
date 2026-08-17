"""
aiconnex_agent/studio.py - LangGraph Studio Entrypoint
======================================================
Exports the compiled Master Agent StateGraph topology (`graph`) for
LangGraph Studio / LangStudio visualization, step-by-step execution,
and real-time state inspection.
"""

from agentic.graph import build_graph

# Compiled StateGraph instance for LangGraph Studio (built-in persistence)
graph = build_graph(with_checkpointer=False)

