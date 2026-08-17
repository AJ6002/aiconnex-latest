# tests/test_graph_runner.py
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from agentic.runner import execute_and_stream
from agentic.state import MasterAgentState


@pytest.fixture(autouse=True)
def _cleanup_scout_output():
    yield
    shutil.rmtree(Path("scratch") / "scout_output", ignore_errors=True)


def test_execute_and_stream(tmp_path):
    # A real upload_path is required so Scout (Phase 5b) can genuinely compile
    # instead of correctly flagging a missing-file clarification interrupt.
    df = pd.DataFrame({"timestamp": ["2026-01-01 00:00:00"], "value": [1.0]})
    zip_path = tmp_path / "runner_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data.csv", df.to_csv(index=False))

    initial_state = MasterAgentState(
        messages=[{"role": "user", "content": "compile data"}],
        upload_path=str(zip_path),
    )
    events = list(execute_and_stream(initial_state, thread_id="runner_thread_1"))
    
    assert len(events) >= 3
    node_names = [e["node"] for e in events if "node" in e]
    assert "conversation_parser_node" in node_names
    assert "intent_extraction_node" in node_names
    assert "contract_manager_node" in node_names
