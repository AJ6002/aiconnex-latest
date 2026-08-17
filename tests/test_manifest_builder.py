"""
tests/test_manifest_builder.py - Unit Tests for ManifestBuilder
================================================================
Verifies:
  1. DIC + selected recipe produces a valid manifest dict
  2. target_column and ml_task map properly from recipe
  3. Numeric features are correctly filtered from schema_map
  4. Timestamp and entity columns are extracted
  5. Manifest serialization to file works cleanly
"""

import json
import pytest
from pathlib import Path

from agentic.platform.manifest_builder import build_manifest, save_manifest_to_file


@pytest.fixture
def sample_dic():
    return {
        "dataset_identity": {"name": "HTDS-v1"},
        "dataset_card": {
            "dataset_name": "HTDS-v1",
            "industry": "Industrial Effluent & Wastewater",
            "domain": "Water Quality",
        },
        "schema_map": {
            "Company Name": "categorical",
            "Recived Date": "datetime",
            "Volume (m3)": "numeric",
            "PH": "numeric",
            "TDS": "numeric",
            "COD": "numeric",
            "SS": "numeric",
        },
        "feature_catalog": {
            "Company Name": {"role": "Metadata / Identity"},
            "Recived Date": {"role": "Feature"},
            "Volume (m3)": {"role": "Target Candidate"},
            "PH": {"role": "Feature"},
            "TDS": {"role": "Target Candidate"},
            "COD": {"role": "Target Candidate"},
            "SS": {"role": "Target Candidate"},
        },
        "target_candidates": ["TDS", "COD", "SS"],
    }


def test_build_manifest_regression(sample_dic, tmp_path):
    recipe = {
        "id": "R002",
        "title": "Predict TDS",
        "target": "TDS",
        "task": "REGRESSION",
        "confidence": 0.89,
    }
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("Company Name,Recived Date,Volume (m3),PH,TDS,COD,SS\nLaurus,2024-01-01,150,7.2,40000,80000,500\n")

    manifest = build_manifest(sample_dic, recipe, str(csv_file), "test_session_123")

    assert manifest["ml_task"] == "regression"
    assert manifest["label_contract"]["target_column"] == "TDS"
    assert manifest["schema_config"]["timestamp_column"] == "Recived Date"
    assert manifest["schema_config"]["entity_column"] == "Company Name"
    assert "TDS" not in manifest["schema_config"]["raw_features"]
    assert "PH" in manifest["schema_config"]["raw_features"]
    assert manifest["dag_id"] == "R002"


def test_build_manifest_anomaly(sample_dic, tmp_path):
    recipe = {
        "id": "R007",
        "title": "Detect Dataset Anomalies",
        "target": None,
        "task": "ANOMALY",
        "confidence": 0.78,
    }
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("Company Name,Recived Date,Volume (m3),PH,TDS,COD,SS\nLaurus,2024-01-01,150,7.2,40000,80000,500\n")

    manifest = build_manifest(sample_dic, recipe, str(csv_file), "test_session_456")

    assert manifest["ml_task"] == "anomaly"
    assert manifest["candidate_algorithms"] == ["IsolationForest", "OneClassSVM"]


def test_save_manifest_to_file(sample_dic, tmp_path):
    recipe = {"id": "R001", "title": "Predict SS", "target": "SS", "task": "REGRESSION"}
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b\n1,2\n")
    manifest = build_manifest(sample_dic, recipe, str(csv_file), "sess_789")

    out_json = tmp_path / "manifest.json"
    saved_path = save_manifest_to_file(manifest, str(out_json))

    assert Path(saved_path).exists()
    data = json.loads(Path(saved_path).read_text(encoding="utf-8"))
    assert data["pipeline_run_id"] == "run_sess_789"
