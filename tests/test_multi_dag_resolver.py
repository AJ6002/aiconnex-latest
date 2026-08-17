# tests/test_multi_dag_resolver.py
"""Tests for Multi-DAG Candidate Resolver (Phase 5c)."""

from __future__ import annotations
import pytest
from agentic.platform.multi_dag_resolver import resolve_candidates
from agentic.schemas import CandidateRecipe


def test_regression_profile_returns_3_to_5_candidates():
    """A regression dataset profile should yield 3-5 distinct candidates."""
    profile = {"problem_type": "regression", "dataset_size": "medium"}
    candidates = resolve_candidates(profile, max_candidates=5)

    assert 3 <= len(candidates) <= 5
    for c in candidates:
        assert isinstance(c, CandidateRecipe)
        assert c.dag_id.startswith("DAG_")
        assert c.algo_family == "REGRESSION"


def test_candidates_have_distinct_algorithms():
    """Each candidate should use a different algorithm (no duplicates)."""
    profile = {"problem_type": "regression", "dataset_size": "medium"}
    candidates = resolve_candidates(profile, max_candidates=5)

    algo_names = [c.hyperparameters.get("algorithm", c.dag_id) for c in candidates]
    assert len(set(algo_names)) == len(algo_names), f"Duplicate algorithms: {algo_names}"


def test_classification_profile():
    """Classification profile should yield CLASSIFICATION family candidates."""
    profile = {"problem_type": "classification", "dataset_size": "medium"}
    candidates = resolve_candidates(profile, max_candidates=4)

    assert len(candidates) >= 3
    for c in candidates:
        assert c.algo_family == "CLASSIFICATION"


def test_anomaly_detection_profile():
    """Anomaly detection profile should yield ANOMALY DETECTION family candidates."""
    profile = {"problem_type": "anomaly_detection", "dataset_size": "medium"}
    candidates = resolve_candidates(profile, max_candidates=4)

    assert len(candidates) >= 3
    for c in candidates:
        assert c.algo_family == "ANOMALY DETECTION"


def test_unknown_profile_falls_back_to_regression():
    """Unknown problem types should fall back to REGRESSION candidates."""
    profile = {"problem_type": "unknown_domain", "dataset_size": "small"}
    candidates = resolve_candidates(profile, max_candidates=3)

    assert len(candidates) >= 3
    for c in candidates:
        assert c.algo_family == "REGRESSION"


def test_recipe_ids_are_unique():
    """All recipe_ids within a candidate set must be unique."""
    profile = {"problem_type": "regression", "dataset_size": "large"}
    candidates = resolve_candidates(profile, max_candidates=5)

    ids = [c.recipe_id for c in candidates]
    assert len(set(ids)) == len(ids)
