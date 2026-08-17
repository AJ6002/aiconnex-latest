"""
tests/test_platform_kb_methodology.py

Sprint 3 Validation Test Suite for ML Methodology KB.
Tests:
1. MLMethodRecord Pydantic schema validation.
2. Canonical method registry loading & problem family query.
3. Applicability filtering & anti-pattern extraction.
4. Baseline recommendations.
5. ContextBuilder methodology context facade.
6. PostgreSQL table `knowledge_ml_methods` sync.
7. Qdrant vector retrieval for `knowledge_domain="ml_methodology"`.
"""

import pytest
from agentic.platform_kb.schemas import MLMethodRecord, ContextRequest
from agentic.platform_kb.methodology_service import MethodologyService
from agentic.platform_kb.context_builder import ContextBuilder
from agentic.platform_kb.retrieval_service import RetrievalService


@pytest.fixture
def ml_svc():
    return MethodologyService()


def test_01_ml_method_record_schema():
    """Verify MLMethodRecord Pydantic contract."""
    rec = MLMethodRecord(
        method_id="ML-PROG-WEIBULL",
        name="Weibull Hazard Model",
        problem_family="Prognostics",
        task_type="RUL estimation",
        lifecycle_phase="Modeling",
        required_data_structure=["time_series_regular"],
        minimum_sample_size="small_n_friendly",
        label_requirements="failure_timestamps",
        data_compatibility={"supports_multivariate": False},
        model_family="parametric_survival",
        capacity_level="baseline",
        interpretability="high",
        primary_metrics=["MAE_on_RUL"],
        canonical_baseline="linear_degradation"
    )
    assert rec.method_id == "ML-PROG-WEIBULL"
    assert rec.problem_family == "Prognostics"
    assert rec.interpretability == "high"


def test_02_registry_loading(ml_svc):
    """Verify canonical methods registry loading across 6 problem families."""
    assert len(ml_svc.methods) >= 6
    families = {m.problem_family for m in ml_svc.methods.values()}
    assert "Prognostics" in families
    assert "Forecasting" in families
    assert "Anomaly Detection" in families
    assert "Classification" in families
    assert "Regression" in families
    assert "Survival Analysis" in families


def test_03_applicability_filtering(ml_svc):
    """Verify data-compatibility filtering for method selection."""
    prog_methods = ml_svc.get_applicable_methods("Prognostics", {"is_multivariate": True})
    assert len(prog_methods) > 0
    assert any(m.method_id == "ML-PROG-LSTM-RUL" for m in prog_methods)


def test_04_anti_patterns_and_limitations(ml_svc):
    """Verify retrieval of explicit 'When NOT to use' anti-patterns."""
    lstm = ml_svc.get_method("ML-PROG-LSTM-RUL")
    assert lstm is not None
    assert "do_not_use_on_small_n_under_50_cycles" in lstm.anti_patterns
    assert "requires_hundreds_of_run_to_failure_cycles" in lstm.limitations


def test_05_baseline_recommendations(ml_svc):
    """Verify baseline algorithm recommendations."""
    baselines = ml_svc.recommend_baselines("Prognostics")
    assert len(baselines) > 0
    assert any("WEIBULL" in b or "linear" in b for b in baselines)


def test_06_context_builder_integration():
    """Verify ContextBuilder get_methodology_context facade."""
    builder = ContextBuilder()
    ctx = builder.get_methodology_context("Prognostics", {"is_multivariate": True})
    assert ctx["problem_family"] == "Prognostics"
    assert len(ctx["applicable_methods"]) > 0
    assert len(ctx["recommended_baselines"]) > 0


def test_07_postgres_ml_methods_sync(ml_svc):
    """Verify sync_to_postgres creates and populates knowledge_ml_methods table."""
    count = ml_svc.sync_to_postgres()
    assert count >= 6


def test_08_qdrant_ml_vector_retrieval():
    """Verify Qdrant vector retrieval for knowledge_domain='ml_methodology'."""
    service = RetrievalService()
    req = ContextRequest(
        query="CRISP-ML process model quality assurance and dataset verification",
        knowledge_domain="ml_methodology",
        top_k=3
    )
    pack = service.retrieve(req, mode="semantic")
    assert pack.retrieval_mode == "semantic"
    assert len(pack.results) > 0
    assert pack.results[0].score >= 0.50
