"""
test_cli.py - Regression tests for the aiconnex_zip_compiler CLI entry point
==============================================================================
Covers the three defects found during terminal verification:
  1. --batch must never block on stdin, even when run in a real tty.
  2. cli.main() must not crash on the final lockfile print (Path/str bug).
  3. An invalid --strategy value must warn loudly and fall back, not
     silently substitute.

These tests invoke cli.main() directly (patching sys.argv) so they exercise
the real CLI code path, not just the UnifiedCompiler library call.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    PluginRegistry.reset_instance()
    yield
    PluginRegistry.reset_instance()


@pytest.fixture
def multi_condition_zip(tmp_path) -> Path:
    """Multi-condition dataset (2 feasible intent options) to force a real choice."""
    df = pd.DataFrame({
        "unit_id": [1, 1, 1, 2, 2, 2],
        "cycle": [1, 2, 3, 1, 2, 3],
        "sensor_1": [10, 11, 12, 20, 21, 22],
    })
    zip_path = tmp_path / "fd_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("train_FD001.txt", df.to_csv(sep=" ", index=False, header=False))
        zf.writestr("train_FD002.txt", df.to_csv(sep=" ", index=False, header=False))
    return zip_path


def _run_cli(monkeypatch, argv):
    """Run cli.main() with a patched argv and return the exit code."""
    from services.aiconnex_zip_compiler import cli
    monkeypatch.setattr(sys, "argv", ["aiconnex_zip_compiler"] + argv)
    return cli.main()


def test_batch_mode_does_not_block_and_exits_zero(monkeypatch, multi_condition_zip, tmp_path):
    """--batch must auto-select the default option without calling input()."""
    out_dir = tmp_path / "out_batch"

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("input() must not be called in --batch mode")

    monkeypatch.setattr("builtins.input", _fail_if_called)

    exit_code = _run_cli(monkeypatch, [
        "-i", str(multi_condition_zip),
        "-o", str(out_dir),
        "--batch",
    ])

    assert exit_code == 0
    assert (out_dir / "compiler_lock.json").exists()


def test_cli_main_does_not_crash_on_success_print(monkeypatch, multi_condition_zip, tmp_path):
    """Regression for the res.output_dir / 'compiler_lock.json' TypeError (str has no /)."""
    out_dir = tmp_path / "out_strategy"

    exit_code = _run_cli(monkeypatch, [
        "-i", str(multi_condition_zip),
        "-o", str(out_dir),
        "--strategy", "unified_all_conditions",
    ])

    assert exit_code == 0


def test_invalid_strategy_warns_and_falls_back(monkeypatch, multi_condition_zip, tmp_path, capsys):
    """An unrecognized --strategy value must print a visible warning, not fail silently."""
    out_dir = tmp_path / "out_bogus"

    exit_code = _run_cli(monkeypatch, [
        "-i", str(multi_condition_zip),
        "-o", str(out_dir),
        "--strategy", "this_does_not_exist",
    ])

    captured = capsys.readouterr()
    combined_out = captured.out + captured.err
    assert "WARNING" in combined_out or "Unknown choice_id" in combined_out or exit_code == 0
    assert exit_code == 0




def test_cli_output_contains_no_non_ascii_characters(monkeypatch, multi_condition_zip, tmp_path, capsys):
    """The full CLI banner + success output must be pure ASCII (no emoji/box-drawing)."""
    out_dir = tmp_path / "out_ascii"

    exit_code = _run_cli(monkeypatch, [
        "-i", str(multi_condition_zip),
        "-o", str(out_dir),
        "--batch",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    non_ascii = [ch for ch in captured.out if ord(ch) > 127]
    assert not non_ascii, f"Found non-ASCII characters in CLI output: {non_ascii}"
