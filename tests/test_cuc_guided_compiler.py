import os
import sys
import pytest
from pathlib import Path

from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
from services.aiconnex_zip_compiler.intent.models import DatasetCard, IntentOption, IntentDecision
from services.aiconnex_zip_compiler.intent.resolver import IntentResolver

def test_unified_compiler_cuc_intent_anomaly():
    # Test that CUC intent with anomaly detection overrides default and sets anomaly strategy
    cuc_anomaly = {
        "primary_intent": "anomaly_detection",
        "task_family": "anomaly_detection",
        "target_hint": "anomaly_score",
        "asset_type": "wind_turbine"
    }
    
    compiler = UnifiedCompiler(
        zip_path="dummy.zip",
        output_dir="dummy_out",
        batch=True,
        cuc_intent=cuc_anomaly
    )
    assert compiler.cuc_intent["primary_intent"] == "anomaly_detection"
    assert compiler.cuc_intent["target_hint"] == "anomaly_score"

def test_unified_compiler_cuc_intent_rul():
    # Test that CUC intent with RUL sets target_column_hint to RUL
    cuc_rul = {
        "primary_intent": "predict_rul",
        "task_family": "regression",
        "target_hint": "RUL_cycles",
        "asset_type": "compressor"
    }
    
    compiler = UnifiedCompiler(
        zip_path="dummy.zip",
        output_dir="dummy_out",
        batch=True,
        cuc_intent=cuc_rul
    )
    assert compiler.cuc_intent["primary_intent"] == "predict_rul"
    assert compiler.cuc_intent["target_hint"] == "RUL_cycles"

def test_intent_resolver_with_target_hint():
    card = DatasetCard(dataset_name="test_dataset", dataset_type="single_table", domain="industrial_scada")
    strategy = IntentResolver().resolve("failure_prediction", card)
    assert strategy.intent_id == "failure_prediction"
    assert strategy.target_column_hint == "RUL"
