# tests/test_langgraph_topology.py
import zipfile
import pandas as pd
import pytest
from agentic.graph import build_graph
from agentic.state import MasterAgentState


@pytest.fixture
def synthetic_upload_zip(tmp_path):
    """A real, single-table zip - only 1 IntentClassifier option, so Scout
    proceeds through the real UnifiedCompiler without needing a strategy
    clarification interrupt (Gap 7 does not fire for a plain single table)."""
    df = pd.DataFrame({"timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:01:00"], "value": [1.0, 2.0]})
    zip_path = tmp_path / "topology_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data.csv", df.to_csv(index=False))
    return str(zip_path)


def test_full_graph_execution_happy_path(synthetic_upload_zip):
    # Pre-upload flow parses conversation, extracts intent, and routes to response_writer
    graph = build_graph()
    initial_state = MasterAgentState(
        messages=[{"role": "user", "content": "train RUL regression model on NASA FD001"}],
        upload_path=synthetic_upload_zip,
    )
    config = {"configurable": {"thread_id": "test_thread_1"}}

    res = graph.invoke(initial_state, config=config)
    assert res["active_agent"] in ["upload_gate", "response_writer", "planner", "complete"]
    assert len(res["messages"]) >= 1


def test_full_graph_execution_compile_zip_two_step_plan(synthetic_upload_zip):
    # Ingest compilation conversation routes through pre-upload contract manager
    graph = build_graph()
    initial_state = MasterAgentState(
        messages=[{"role": "user", "content": "compile suyash2.zip"}],
        upload_path=synthetic_upload_zip,
    )
    config = {"configurable": {"thread_id": "test_thread_compile"}}

    res = graph.invoke(initial_state, config=config)
    assert res["active_agent"] in ["response_writer", "planner", "complete"]
    assert len(res["messages"]) >= 1


def test_full_graph_execution_ambiguous_hitl_interrupt():
    graph = build_graph()
    initial_state = MasterAgentState(messages=[{"role": "user", "content": "ambiguous prompt"}])
    config = {"configurable": {"thread_id": "test_thread_2"}}
    
    res_interrupt = graph.invoke(initial_state, config=config)
    assert res_interrupt["active_agent"] == "clarification" or "__interrupt__" in res_interrupt
