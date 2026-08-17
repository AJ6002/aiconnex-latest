# aiconnex_agent/platform/mlflow_logger.py
"""
MLflow Logger — Backward-Compatible Facade
============================================
This module is now a thin facade that delegates to
``agentic.telemetry.emitters.PlatformEmitter``.

MLflow tracking has been promoted to a cross-cutting Telemetry
infrastructure service (aiconnex_agent/telemetry/) so that Planner,
Scout, Memory, and Platform nodes can all emit structured traces under
a single per-session experiment.

Public API is fully preserved for backward compatibility with any existing
callers (platform_node.py, tests, external scripts):

    from agentic.platform.mlflow_logger import log_experiment
    log_experiment(session_id, selection_result, scorer_reports, judge_reports)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from agentic.schemas import ScorerReport, JudgeReport, SelectionResult

logger = logging.getLogger(__name__)


def log_experiment(
    session_id: str,
    selection_result: SelectionResult,
    scorer_reports: List[ScorerReport],
    judge_reports: List[JudgeReport],
    ensemble_weights: Optional[np.ndarray] = None,
    model_artifact_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Log the full multi-candidate experiment to MLflow.

    Facade delegating to ``PlatformEmitter`` in the telemetry package.

    Args:
        session_id: Workflow session ID (wf_<hex>).
        selection_result: The Selector Agent's MCDA output with leaderboard.
        scorer_reports: All candidate Scorer reports.
        judge_reports: All candidate Judge reports.
        ensemble_weights: Non-negative Ridge meta-learner coefficients.
        model_artifact_path: Optional path to serialized model binary.

    Returns:
        Dict with ``run_id``, ``experiment_name``, ``tracking_uri``,
        and ``status`` keys.
    """
    try:
        from agentic.telemetry.emitters import PlatformEmitter
        emitter = PlatformEmitter()
        return emitter.log_experiment(
            session_id=session_id,
            selection_result=selection_result,
            scorer_reports=scorer_reports,
            judge_reports=judge_reports,
            ensemble_weights=ensemble_weights,
            model_artifact_path=model_artifact_path,
        )
    except Exception as exc:
        logger.warning(f"[MLflowLoggerFacade] PlatformEmitter failed: {exc}")
        return {"status": "error", "session_id": session_id, "error": str(exc)}
