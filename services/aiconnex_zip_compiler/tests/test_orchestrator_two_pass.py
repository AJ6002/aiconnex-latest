"""
tests/test_orchestrator_two_pass.py
====================================
Unit tests verifying Gap 10 (Decoupled Observability Telemetry) and
Gap 11 (Two-Pass Joint Intelligence Fusion) in IntelligenceOrchestrator.
"""

from unittest.mock import MagicMock
import pandas as pd
import pytest

from services.aiconnex_zip_compiler.intelligence.models import (
    IntelligenceReport,
    ProblemHypothesis,
    SchemaRoles,
    SemanticLabel,
    TableMetadata,
)
from services.aiconnex_zip_compiler.intelligence.orchestrator import IntelligenceOrchestrator


def test_decoupled_telemetry_headless_mode():
    """Verify Gap 10: When LLM is disabled, execution_mode is 'deterministic_headless' and degraded is False."""
    orch = IntelligenceOrchestrator(enable_llm=False)
    df = pd.DataFrame({"temp_c": [20.0, 25.0], "pressure_bar": [1.0, 2.5]})
    report = orch.run_post_parse({"sensor_table": df})

    assert report.execution_mode == "deterministic_headless"
    assert report.llm_available is False
    assert report.degraded is False


def test_decoupled_telemetry_llm_mode():
    """Verify Gap 10: When LLM is available, execution_mode is 'llm_enhanced' and degraded is False."""
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True

    orch = IntelligenceOrchestrator(llm_client=mock_llm, enable_llm=True)
    df = pd.DataFrame({"temp_c": [20.0, 25.0]})
    report = orch.run_post_parse({"sensor_table": df})

    assert report.execution_mode == "llm_enhanced"
    assert report.llm_available is True
    assert report.degraded is False


def test_degraded_flag_set_on_stage_exception():
    """Verify Gap 10: degraded is True ONLY when an actual exception occurs during a stage."""
    orch = IntelligenceOrchestrator(enable_llm=False)
    orch._metadata_extractor.extract_all = MagicMock(side_effect=RuntimeError("Metadata failure"))

    df = pd.DataFrame({"val": [1, 2]})
    report = orch.run_post_parse({"data": df})

    assert report.degraded is True


def test_two_pass_domain_hint_propagation():
    """Verify Gap 11: Stage 7 runs first (Pass 1) to set domain, allowing Stage 6 to consume domain_hint (Pass 2)."""
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True

    orch = IntelligenceOrchestrator(llm_client=mock_llm, enable_llm=True)

    # Track calls to discover and analyze
    call_order = []

    def mock_discover(*args, **kwargs):
        call_order.append(("discover", kwargs))
        return ProblemHypothesis(
            domain="gas_turbines",
            question_for_user="Predict turbine degradation?",
            domain_confidence=0.9,
        )

    def mock_analyze(*args, **kwargs):
        call_order.append(("analyze", kwargs))
        return [
            SemanticLabel(
                table_name="sensors",
                column_name="t1",
                semantic_name="Turbine Temp",
                confidence=0.95,
            )
        ]

    orch._problem_discoverer.discover = MagicMock(side_effect=mock_discover)
    orch._semantic_analyzer.analyze = MagicMock(side_effect=mock_analyze)

    df = pd.DataFrame({"t1": [300.0, 310.0]})
    report = orch.run_post_parse({"sensors": df})

    # Verify call order: discover must run before analyze
    assert len(call_order) >= 2
    assert call_order[0][0] == "discover"
    assert call_order[1][0] == "analyze"

    # Verify domain_hint passed to analyze was established by discover
    analyze_kwargs = call_order[1][1]
    assert analyze_kwargs.get("domain_hint") == "gas_turbines"
