# aiconnex_agent/platform/scorer_agent.py
"""
Scorer Agent (Phase 5c)
========================
Computes hard quantitative metrics for a trained candidate model.
Pure math — zero LLM calls, zero I/O.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

from agentic.schemas import ScorerReport


def score_candidate(
    recipe_id: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    latency_ms: float = 0.0,
    model_size_mb: float = 0.0,
) -> ScorerReport:
    """Score a single candidate model's predictions against ground truth.

    Args:
        recipe_id: Identifier of the candidate recipe.
        y_true: Ground truth target values, shape (N,).
        y_pred: Model predictions, shape (N,).
        latency_ms: Inference latency in milliseconds.
        model_size_mb: Serialized model size in MB.

    Returns:
        ScorerReport with all computed metrics.
    """
    r2 = float(r2_score(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))

    # MAPE — guard against division by zero
    nonzero_mask = np.abs(y_true) > 1e-8
    if nonzero_mask.sum() > 0:
        mape = float(np.mean(np.abs((y_true[nonzero_mask] - y_pred[nonzero_mask]) / y_true[nonzero_mask])) * 100)
    else:
        mape = 0.0

    return ScorerReport(
        recipe_id=recipe_id,
        r2_score=r2,
        rmse=rmse,
        mae=mae,
        mape=mape,
        latency_ms=latency_ms,
        model_size_mb=model_size_mb,
    )
