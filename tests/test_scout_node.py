# tests/test_scout_node.py
"""
Tests for the real Scout Agent Node (Phase 5b) - verifies each of the
architecture-audit gaps it was built to close:
  Gap 1 - reads a REAL file path from state.upload_path, no hardcoded filename.
  Gap 2 - CompileResult is translated into real ScoutEnrichedContract/DIC fields.
  Gap 3 - compile failure retries once, then flags via a real clarification interrupt.
  Gap 4 - PreCompilerContract.compiler_request flags reach UnifiedCompiler.
  Gap 7 - 2+ real IntentOptions trigger a real clarification interrupt instead
          of silently letting the compiler auto-pick options[0].
"""
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from agentic.state import MasterAgentState
from agentic.scout.scout_node import real_scout_agent_node


@pytest.fixture(autouse=True)
def _cleanup_scout_output():
    yield
    shutil.rmtree(Path("scratch") / "scout_output", ignore_errors=True)


@pytest.fixture
def single_table_zip(tmp_path):
    """Only 1 IntentClassifier option (single_table -> auto_model) - no Gap 7 interrupt."""
    df = pd.DataFrame({"timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:01:00"], "value": [1.0, 2.0]})
    zip_path = tmp_path / "scout_single.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data.csv", df.to_csv(index=False))
    return zip_path


@pytest.fixture
def multi_condition_zip(tmp_path):
    """2+ operating conditions in filenames -> 2 real IntentOptions (Gap 7 fires)."""
    df = pd.DataFrame({"time_cycles": [1, 2], "sensor_1": [0.1, 0.2]})
    zip_path = tmp_path / "scout_multi_condition.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("FD001_train.csv", df.to_csv(index=False))
        zf.writestr("FD002_train.csv", df.to_csv(index=False))
    return zip_path


# --- Gap 1: real file path required, no hardcoded filename fallback ---

def test_scout_flags_missing_upload_path_instead_of_faking_data():
    state = MasterAgentState()  # no upload_path set
    with patch("agentic.scout.scout_node.interrupt", return_value="ok") as mock_interrupt:
        res = real_scout_agent_node(state)

    assert mock_interrupt.called
    assert "no dataset file" in mock_interrupt.call_args[0][0]["questions"][0]
    # Bug #1 fix: routes back to scout (not evaluator) and sets interrupt_reason
    assert res["active_agent"] == "scout"
    assert res["interrupt_reason"] == "missing_upload_path"


# --- Gap 2 + Gap 1 success path: real compile -> real contract fields ---

def test_scout_populates_real_contracts_from_real_file(single_table_zip):
    state = MasterAgentState(upload_path=str(single_table_zip))
    res = real_scout_agent_node(state)

    assert res["active_agent"] == "evaluator"
    assert res["scout_enriched"]["upload"]["archive_name"] == single_table_zip.name
    assert res["scout_enriched"]["upload"]["archive_type"] == "zip"
    assert res["scout_enriched"]["archive_discovery"]["total_files"] >= 1
    assert res["dic"]["compiled_dataset"]["rows"] == 2
    # 3, not 2 - the compiler's handoff layer legitimately tags the combined
    # CSV with an extra group_id column (see aiconnex_zip_compiler/handoff.py).
    assert res["dic"]["compiled_dataset"]["columns"] == 3


# --- Gap 3: compile failure retries once, then flags via real interrupt ---

def test_scout_retries_once_then_flags_failure(tmp_path):
    bad_zip = tmp_path / "corrupt.zip"
    bad_zip.write_bytes(b"not a real zip file")
    state = MasterAgentState(upload_path=str(bad_zip))

    with patch("agentic.scout.scout_node.interrupt", return_value="ok") as mock_interrupt:
        res = real_scout_agent_node(state)

    assert mock_interrupt.called
    payload = mock_interrupt.call_args[0][0]
    assert "couldn't process this file" in payload["questions"][0]
    # Bug #1 fix: routes back to scout (not evaluator) and sets interrupt_reason
    assert res["active_agent"] == "scout"
    assert res["interrupt_reason"] == "compile_failure"


def test_scout_compile_retry_actually_runs_compile_twice_on_failure(tmp_path):
    bad_zip = tmp_path / "corrupt2.zip"
    bad_zip.write_bytes(b"not a real zip file")
    state = MasterAgentState(upload_path=str(bad_zip))

    with patch("agentic.scout.scout_node.interrupt", return_value="ok"):
        with patch("aiconnex_zip_compiler.compiler.UnifiedCompiler.compile") as mock_compile:
            from services.aiconnex_zip_compiler.compiler import CompileResult
            from services.aiconnex_zip_compiler.handoff import HandoffArtifacts
            mock_compile.return_value = CompileResult(
                input_zip=str(bad_zip), output_dir="out", merged_files=[], combined_file=None,
                artifacts=HandoffArtifacts({}, None, Path(""), Path(""), Path(""), Path("")),
                audits=[], schema_map=MagicMock(), duration_seconds=0.0,
                success=False, error="simulated failure",
            )
            real_scout_agent_node(state)
            assert mock_compile.call_count == 2  # one retry, as designed


# --- Gap 4: CompilerRequest flags actually reach UnifiedCompiler ---

def test_scout_passes_compiler_request_flags_to_unified_compiler(single_table_zip):
    from agentic.schemas import PreCompilerContract, CompilerRequest

    state = MasterAgentState(
        upload_path=str(single_table_zip),
        pre_compiler=PreCompilerContract(compiler_request=CompilerRequest(infer_targets=False, infer_problem_candidates=False)),
    )

    with patch("aiconnex_zip_compiler.compiler.UnifiedCompiler.__init__", return_value=None) as mock_init:
        with patch("aiconnex_zip_compiler.compiler.UnifiedCompiler.compile") as mock_compile:
            from services.aiconnex_zip_compiler.compiler import CompileResult
            from services.aiconnex_zip_compiler.handoff import HandoffArtifacts
            mock_compile.return_value = CompileResult(
                input_zip=str(single_table_zip), output_dir="out", merged_files=[], combined_file=None,
                artifacts=HandoffArtifacts({}, None, Path(""), Path(""), Path(""), Path("")),
                audits=[], schema_map=MagicMock(), duration_seconds=0.0, success=True,
            )
            real_scout_agent_node(state)

    _, kwargs = mock_init.call_args
    # infer_targets=False and infer_problem_candidates=False -> enable_intelligence=False
    assert kwargs["enable_intelligence"] is False


# --- Gap 7: 2+ real strategy options trigger a real clarification interrupt ---

def test_scout_asks_user_when_multiple_real_strategies_exist(multi_condition_zip):
    state = MasterAgentState(upload_path=str(multi_condition_zip))

    with patch("agentic.scout.scout_node.interrupt", return_value="unified_all_conditions") as mock_interrupt:
        res = real_scout_agent_node(state)

    assert mock_interrupt.called
    payload = mock_interrupt.call_args[0][0]
    assert len(payload["options"]) >= 2
    option_ids = [o["option_id"] for o in payload["options"]]
    assert "unified_all_conditions" in option_ids
    assert "separate_per_condition" in option_ids
    assert res["active_agent"] == "evaluator"


def test_scout_does_not_ask_when_only_one_real_strategy_exists(single_table_zip):
    state = MasterAgentState(upload_path=str(single_table_zip))

    with patch("agentic.scout.scout_node.interrupt") as mock_interrupt:
        real_scout_agent_node(state)

    # Single-table zip -> IntentClassifier returns exactly 1 option -> no interrupt.
    assert not mock_interrupt.called
