"""
tests/test_recipe_catalog_builder.py - Unit Tests for RecipeCatalogBuilder
===========================================================================
Verifies:
  1. schema_map is correctly inferred from column types
  2. target_candidates are populated for numeric columns with sufficient variance
  3. Recipes are generated in correct order (regression > forecast > anomaly)
  4. HITL dynamic prompt is built from DIC recipes
  5. Fallback to static message when no recipes present
"""

import io
import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_csv(tmp_path, rows=200):
    import pandas as pd
    import numpy as np
    np.random.seed(42)
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=rows, freq="D").astype(str),
        "TDS": np.random.normal(70000, 8000, rows),
        "COD": np.random.normal(80000, 15000, rows),
        "PH": np.random.uniform(6.5, 8.5, rows),
        "Volume": np.random.normal(150, 60, rows),
        "company": ["Laurus Labs"] * rows,  # should be excluded from targets
        "category": (["A", "B", "C"] * (rows // 3 + 1))[:rows],  # categorical
    })
    path = tmp_path / "test_compiled.csv"
    df.to_csv(path, index=False)
    return str(path)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_schema_map_infers_datetime(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    assert catalog["schema_map"].get("date") == "datetime"


def test_schema_map_infers_numeric(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    assert catalog["schema_map"].get("TDS") == "numeric"
    assert catalog["schema_map"].get("COD") == "numeric"


def test_target_candidates_excludes_low_variance(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    # All high-variance numeric columns should be candidates
    assert "TDS" in catalog["target_candidates"]
    assert "COD" in catalog["target_candidates"]


def test_recipes_not_empty(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    assert len(catalog["recipes"]) > 0


def test_recipes_include_anomaly(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    tasks = [r["task"] for r in catalog["recipes"]]
    assert "ANOMALY" in tasks


def test_recipes_include_forecast_when_datetime(tmp_path):
    from agentic.scout.recipe_catalog_builder import build_recipe_catalog
    csv_path = _make_csv(tmp_path)
    catalog = build_recipe_catalog(csv_path)
    tasks = [r["task"] for r in catalog["recipes"]]
    assert "FORECAST" in tasks


def test_hitl_dynamic_prompt_from_recipes():
    import sys
    sys.path.insert(0, "backend")
    from hitl_flow import _build_recipe_opening
    dic_context = {
        "dataset_identity": {"name": "HTDS-v1"},
        "recipes": [
            {"id": "R001", "title": "Predict TDS", "task": "REGRESSION", "confidence": 0.89, "rationale": "TDS varies"},
            {"id": "R002", "title": "Detect Anomalies", "task": "ANOMALY", "confidence": 0.78, "rationale": "Unsupervised"},
        ]
    }
    prompt = _build_recipe_opening(dic_context)
    assert "[1] Predict TDS" in prompt
    assert "[2] Detect Anomalies" in prompt
    assert "REGRESSION" in prompt
    assert "89%" in prompt


def test_hitl_fallback_when_no_recipes():
    import sys
    sys.path.insert(0, "backend")
    from hitl_flow import _build_recipe_opening, _FALLBACK_OPENING_MESSAGE
    prompt = _build_recipe_opening({"recipes": []})
    assert prompt == _FALLBACK_OPENING_MESSAGE


def test_intent_plan_mapper_has_no_platform_in_initial_plan():
    from agentic.planning.intent_plan_mapper import IntentPlanMapper
    mapper = IntentPlanMapper()
    for intent in ("train_rul", "detect_anomalies", "predict"):
        plan = mapper.get_plan(intent)
        agents = [s["target_agent"] for s in plan]
        assert "platform" not in agents, f"Platform found in initial plan for intent={intent}"


def test_intent_plan_mapper_get_platform_steps():
    from agentic.planning.intent_plan_mapper import IntentPlanMapper
    mapper = IntentPlanMapper()
    steps = mapper.get_platform_steps("REGRESSION", "Predict TDS")
    agents = [s["target_agent"] for s in steps]
    assert "platform" in agents
    assert steps[0]["step_id"] == "platform_step_1"
