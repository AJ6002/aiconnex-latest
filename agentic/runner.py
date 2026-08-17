"""
aiconnex_agent/runner.py - Execution & Event Streaming Harness for TUI
======================================================================
Provides helper functions for invoking the LangGraph StateGraph and streaming
node state events to the Terminal UI.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Generator
from langgraph.types import Command

from agentic.graph import build_graph
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

# Global compiled graph instance
_compiled_graph = build_graph()


def execute_and_stream(
    initial_state: MasterAgentState,
    thread_id: str = "default_session"
) -> Generator[Dict[str, Any], None, None]:
    """Execute LangGraph StateGraph and yield node transition telemetry events."""
    config = {"configurable": {"thread_id": thread_id}}
    
    # StateGraph stream returns a dict of {node_name: state_update}
    for event in _compiled_graph.stream(initial_state, config=config, stream_mode="updates"):
        if isinstance(event, dict):
            for node_name, state_update in event.items():
                yield {
                    "event": "node_update",
                    "node": node_name,
                    "state_update": state_update,
                    "thread_id": thread_id,
                }


def resume_with_user_input(
    user_input: str,
    thread_id: str = "default_session"
) -> Generator[Dict[str, Any], None, None]:
    """Resume a paused HITL interrupt node with user input."""
    config = {"configurable": {"thread_id": thread_id}}
    command = Command(resume=user_input)
    
    for event in _compiled_graph.stream(command, config=config, stream_mode="updates"):
        if isinstance(event, dict):
            for node_name, state_update in event.items():
                yield {
                    "event": "node_update",
                    "node": node_name,
                    "state_update": state_update,
                    "thread_id": thread_id,
                }


def run_agent_pipeline(user_prompt: str, upload_path: str = None, thread_id: str = "api_session") -> Dict[str, Any]:
    """Run full LangGraph StateGraph pipeline synchronously and return final state dict."""
    initial_state = MasterAgentState(
        messages=[{"role": "user", "content": user_prompt}],
        upload_path=upload_path
    )
    events = list(execute_and_stream(initial_state, thread_id=thread_id))
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = _compiled_graph.get_state(config)
    final_values = snapshot.values if hasattr(snapshot, "values") else {}
    return {
        "events": events,
        "final_state": final_values,
        "is_interrupted": bool(snapshot.next and "__interrupt__" in str(snapshot.next))
    }

