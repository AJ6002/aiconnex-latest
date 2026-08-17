"""
test_split_policy.py - Tests for topology-enforced splitting
"""

import pytest
import numpy as np
import pandas as pd
from services.aiconnex_ml.shared.splitter.policy import (
    enforce_split, _chronological_split, _group_chronological_split, _random_split
)


def _make_timeseries_df(n: int = 200, entities: int = 10) -> pd.DataFrame:
    entity_ids = np.repeat(np.arange(entities), n // entities)
    timestamps = pd.date_range("2026-01-01", periods=n, freq="10min")
    return pd.DataFrame({
        "engine_id": entity_ids[:n],
        "timestamp": timestamps,
        "sensor_1": np.random.rand(n),
        "target": np.random.rand(n) * 100,
    })


def _make_manifest(topology: str, entity_col=None) -> dict:
    return {
        "data_topology": topology,
        "split_policy": {"train_ratio": 0.70, "val_ratio": 0.15, "random_state": 42},
        "schema_config": {"entity_column": entity_col, "timestamp_column": "timestamp"},
    }


def test_chronological_split_no_shuffle():
    df = _make_timeseries_df(200, entities=1)
    manifest = _make_manifest("time_series")
    df_train, df_val, df_test, _ = enforce_split(df, manifest)
    # Train should contain first 70%, test should contain last 15%
    assert len(df_train) == 140
    assert len(df_test) == 30


def test_group_chronological_no_entity_leakage():
    df = _make_timeseries_df(200, entities=10)
    manifest = _make_manifest("multi_entity_time_series", entity_col="engine_id")
    df_train, df_val, df_test, _ = enforce_split(df, manifest)

    train_entities = set(df_train["engine_id"])
    val_entities = set(df_val["engine_id"])
    test_entities = set(df_test["engine_id"])

    # No entity should appear in more than one split
    assert len(train_entities & val_entities) == 0
    assert len(train_entities & test_entities) == 0
    assert len(val_entities & test_entities) == 0


def test_tabular_split_sizes():
    df = pd.DataFrame({"feat": np.random.rand(1000), "label": np.random.rand(1000)})
    manifest = _make_manifest("tabular")
    df_train, df_val, df_test, _ = enforce_split(df, manifest)
    total = len(df_train) + len(df_val) + len(df_test)
    assert total == 1000


def test_split_preserves_total_rows():
    df = _make_timeseries_df(300, entities=15)
    manifest = _make_manifest("multi_entity_time_series", entity_col="engine_id")
    df_train, df_val, df_test, _ = enforce_split(df, manifest)
    assert len(df_train) + len(df_val) + len(df_test) == 300
