"""
test_config.py - Unit tests for Pydantic manifest validation
"""

import pytest
from services.aiconnex_ml.config import Manifest, LabelContract, SplitPolicy


def _base_manifest_dict(**overrides):
    base = {
        "pipeline_run_id": "test_001",
        "ml_task": "regression",
        "label_contract": {
            "regime": "continuous",
            "target_column": "RUL",
        },
    }
    base.update(overrides)
    return base


def test_valid_regression_manifest():
    m = Manifest(**_base_manifest_dict())
    assert m.ml_task == "regression"
    assert m.pipeline_run_id == "test_001"


def test_continuous_regime_requires_target():
    with pytest.raises(Exception):
        Manifest(**_base_manifest_dict(
            label_contract={"regime": "continuous", "target_column": None}
        ))


def test_curated_normal_requires_normal_period():
    with pytest.raises(Exception):
        Manifest(**_base_manifest_dict(
            ml_task="anomaly",
            label_contract={
                "regime": "curated_normal",
                "supervision_mode": "semi_supervised",
                "normal_period": None,
            }
        ))


def test_fault_labeled_requires_fault_column():
    with pytest.raises(Exception):
        Manifest(**_base_manifest_dict(
            ml_task="anomaly",
            label_contract={
                "regime": "fault_labeled",
                "fault_label_column": None,
            }
        ))


def test_split_policy_defaults():
    m = Manifest(**_base_manifest_dict())
    assert m.split_policy.train_ratio == 0.70
    assert m.split_policy.val_ratio == 0.15


def test_anomaly_manifest_with_threshold():
    data = _base_manifest_dict(
        ml_task="anomaly",
        label_contract={
            "regime": "curated_normal",
            "supervision_mode": "semi_supervised",
            "normal_period": {"start": "2026-01-01", "end": "2026-03-01"},
        },
        threshold_config={
            "method": "percentile",
            "percentile": 99.0,
        }
    )
    m = Manifest(**data)
    assert m.threshold_config.method == "percentile"
