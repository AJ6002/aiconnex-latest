import pytest
import pandas as pd
from pathlib import Path

from services.aiconnex_zip_compiler.plugins.assemblers.relational_join_assembler import (
    RelationalJoinAssemblerPlugin,
    RelationalJoinAssembler,
)
from services.aiconnex_zip_compiler.plugins.context import PipelineContext
from services.aiconnex_zip_compiler.intent.models import CompilationStrategy


def test_cumulative_cartesian_guard_evaluates_per_iteration(monkeypatch):
    """
    Verifies that the Cartesian explosion guard evaluates current_rows at every iteration.
    Step 1: 100 rows -> 104 rows (1.04 <= 1.05, passes).
    Step 2: 104 rows -> 108 rows (108 / 104 = 1.038 <= 1.05, passes under cumulative guard).
    (Under old static guard: 108 / 100 = 1.08 > 1.05 would have failed).
    """
    assembler = RelationalJoinAssembler()
    context = PipelineContext(
        target_path=Path("/tmp"),
        temp_dir=Path("/tmp"),
        output_dir=Path("/tmp"),
    )

    df_primary = pd.DataFrame({"asset_id": [f"A{i}" for i in range(100)], "val": range(100)})
    df_dim1 = pd.DataFrame({"asset_id": [f"A{i}" for i in range(100)], "dim1": range(100)})
    df_dim2 = pd.DataFrame({"asset_id": [f"A{i}" for i in range(100)], "dim2": range(100)})

    tables = {
        "primary": df_primary,
        "dim1": df_dim1,
        "dim2": df_dim2,
    }

    call_count = 0

    def mock_merge(self, right, on=None, how="left", suffixes=("", "")):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First join: return 104 rows
            return pd.DataFrame({"asset_id": [f"A{i}" for i in range(104)], "val": range(104)})
        else:
            # Second join: return 108 rows
            return pd.DataFrame({"asset_id": [f"A{i}" for i in range(108)], "val": range(108)})

    monkeypatch.setattr(pd.DataFrame, "merge", mock_merge)

    result = assembler.assemble(tables, context)
    assert len(result) == 1
    assembled = next(iter(result.values()))
    assert len(assembled) == 108
    assert call_count == 2


def test_cumulative_cartesian_guard_triggers_on_step_explosion(monkeypatch):
    """
    Verifies that Cartesian explosion guard triggers when step growth exceeds 5% of current_rows.
    """
    assembler = RelationalJoinAssembler()
    context = PipelineContext(
        target_path=Path("/tmp"),
        temp_dir=Path("/tmp"),
        output_dir=Path("/tmp"),
    )

    df_primary = pd.DataFrame({"asset_id": [f"A{i}" for i in range(100)], "val": range(100)})
    df_dim1 = pd.DataFrame({"asset_id": [f"A{i}" for i in range(100)], "dim1": range(100)})

    tables = {
        "primary": df_primary,
        "dim1": df_dim1,
    }

    def mock_merge_explode(self, right, on=None, how="left", suffixes=("", "")):
        # 100 -> 120 rows (20% explosion)
        return pd.DataFrame({"asset_id": [f"A{i}" for i in range(120)], "val": range(120)})

    monkeypatch.setattr(pd.DataFrame, "merge", mock_merge_explode)

    with pytest.raises(RuntimeError, match="Cartesian Explosion Guard triggered"):
        assembler.assemble(tables, context)


def test_dynamic_rul_constraints_no_clip_by_default():
    """Without explicit clip_upper in domain_constraints, RUL is not hardcoded to clip at 125."""
    assembler = RelationalJoinAssembler()
    context = PipelineContext(
        target_path=Path("/tmp"),
        temp_dir=Path("/tmp"),
        output_dir=Path("/tmp"),
    )

    df = pd.DataFrame({
        "unit_id": [1] * 200,
        "cycle": list(range(1, 201)),
    })
    tables = {"fact": df}

    res = assembler.assemble(tables, context)
    assembled = next(iter(res.values()))
    assert "RUL" in assembled.columns
    # Cycle 1 should have RUL = 200 - 1 = 199 (not clipped to 125)
    assert assembled.iloc[0]["RUL"] == 199


def test_dynamic_rul_constraints_with_explicit_clip():
    """When clip_upper is specified in domain_constraints, RUL is clipped accordingly."""
    assembler = RelationalJoinAssembler()
    strategy = CompilationStrategy(
        intent_id="test",
        domain_constraints={"clip_upper": 125},
    )
    context = PipelineContext(
        target_path=Path("/tmp"),
        temp_dir=Path("/tmp"),
        output_dir=Path("/tmp"),
        strategy=strategy,
    )

    df = pd.DataFrame({
        "unit_id": [1] * 200,
        "cycle": list(range(1, 201)),
    })
    tables = {"fact": df}

    res = assembler.assemble(tables, context)
    assembled = next(iter(res.values()))
    assert "RUL" in assembled.columns
    # Cycle 1: 199 clipped to 125
    assert assembled.iloc[0]["RUL"] == 125
    # Cycle 150: 200 - 150 = 50 (unclipped because 50 < 125)
    assert assembled.iloc[149]["RUL"] == 50
