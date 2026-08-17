"""
tests/test_scout_p1_remediation.py - Unit Test Suite for Phase 1 P1 Remediation
===================================================================================
Verifies:
  1. InterruptPayload & InterruptOption typed models (Issue 5)
  2. DICValidator completeness validation post-compile (Issue 6)
"""

import pytest
from agentic.schemas import InterruptPayload, InterruptOption
from agentic.scout.dic_validator import DICValidator


def test_interrupt_payload_serialization():
    payload = InterruptPayload(
        interrupt_type="strategy_choice",
        questions=["Which processing strategy would you like?"],
        options=[
            InterruptOption(option_id="opt_1", label="Default Strategy", description="Standard pipeline"),
            InterruptOption(option_id="opt_2", label="Aggressive Strategy", description="Aggressive feature generation"),
        ],
        reason="Multiple valid strategies found"
    )
    dumped = payload.model_dump()
    assert dumped["interrupt_type"] == "strategy_choice"
    assert len(dumped["options"]) == 2
    assert dumped["options"][0]["option_id"] == "opt_1"


def test_dic_validator_valid_contract():
    validator = DICValidator()
    valid_dic = {
        "dataset_identity": {"name": "turbofan_fd001"},
        "compiled_dataset": {"rows": 1000, "tables": 1},
        "statistics": {"missing_values": {"cycle": 0}},
        "quality_report": {"cartesian_guard_passed": True},
    }
    is_valid, warnings = validator.validate(valid_dic)
    assert is_valid is True
    assert len(warnings) == 0


def test_dic_validator_zero_rows_invalid():
    validator = DICValidator()
    invalid_dic = {
        "dataset_identity": {"name": "empty_dataset"},
        "compiled_dataset": {"rows": 0, "tables": 0},
        "statistics": {},
        "quality_report": {},
    }
    is_valid, warnings = validator.validate(invalid_dic)
    assert is_valid is False
    assert any("0 rows" in w for w in warnings)
