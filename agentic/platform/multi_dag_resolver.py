# aiconnex_agent/platform/multi_dag_resolver.py
"""
Multi-DAG Candidate Resolver (Phase 5c)
==========================================
Queries the 1,993-entry dag_conditions_mapping.json to resolve 3–5
complementary candidate DAG recipes for a given dataset profile.

Ensures diversity by selecting at most one DAG per unique algorithm name
within the matched family. Dynamically checks multiple key paths for algorithm
name extraction per Remediation Item 5.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from agentic.schemas import CandidateRecipe

logger = logging.getLogger(__name__)

_DAG_MAPPING_PATH = Path("services/1_dataset_profiler/dag_conditions_mapping.json")

# Maps user-facing problem_type strings to DAG family strings in the mapping file.
_FAMILY_MAP: Dict[str, str] = {
    "regression": "REGRESSION",
    "classification": "CLASSIFICATION",
    "anomaly_detection": "ANOMALY DETECTION",
    "clustering": "CLUSTERING",
    "time_series": "TIME-SERIES",
    "digital_twin": "DIGITAL TWIN",
    "nlp": "NLP/TEXT-CLASSIFICATION",
    "computer_vision": "COMPUTER VISION",
    "recommendation": "RECOMMENDATION",
    "reinforcement_learning": "REINFORCEMENT LEARNING",
}

_DEFAULT_FAMILY = "REGRESSION"


def _load_dag_mapping() -> Dict[str, Any]:
    """Load the DAG conditions mapping JSON. Cached after first call."""
    if not hasattr(_load_dag_mapping, "_cache"):
        path = _DAG_MAPPING_PATH
        if not path.exists():
            logger.warning(f"[MultiDAGResolver] Mapping not found at {path}, trying fallback paths")
            for candidate in [Path("dag_conditions_mapping.json")]:
                if candidate.exists():
                    path = candidate
                    break
        with open(path, "r", encoding="utf-8") as f:
            _load_dag_mapping._cache = json.load(f)
    return _load_dag_mapping._cache


def _extract_algorithm_name(dag_id: str, spec: Dict[str, Any]) -> str:
    """Extract algorithm name checking root, decision, pipeline_actions, and name (Remediation 5)."""
    if "algorithm" in spec and spec["algorithm"]:
        return str(spec["algorithm"])
    decision = spec.get("decision", {})
    pipeline_actions = decision.get("pipeline_actions", {})
    if "algorithm" in pipeline_actions and pipeline_actions["algorithm"]:
        return str(pipeline_actions["algorithm"])
    if "algo" in spec and spec["algo"]:
        return str(spec["algo"])
    if "name" in spec and spec["name"]:
        return str(spec["name"])
    return dag_id


def resolve_candidates(
    profile: Dict[str, Any],
    max_candidates: int = 5,
) -> List[CandidateRecipe]:
    """Resolve 3–5 complementary candidate DAG recipes for a dataset profile.

    Args:
        profile: Dict with at least ``problem_type`` (str). Optional: ``dataset_size``.
        max_candidates: Upper bound on candidate count (default 5).

    Returns:
        List of 3–max_candidates ``CandidateRecipe`` instances, each using a
        distinct algorithm within the matched family.
    """
    problem_type = profile.get("problem_type", "regression").lower().strip()
    family = _FAMILY_MAP.get(problem_type, _DEFAULT_FAMILY)

    dag_mapping = _load_dag_mapping()

    # Filter DAGs belonging to the target family
    family_dags = [
        (dag_id, spec)
        for dag_id, spec in dag_mapping.items()
        if spec.get("family", "").upper() == family
    ]

    if len(family_dags) < 3:
        logger.warning(f"[MultiDAGResolver] Only {len(family_dags)} DAGs for family '{family}', falling back to REGRESSION")
        family = _DEFAULT_FAMILY
        family_dags = [
            (dag_id, spec)
            for dag_id, spec in dag_mapping.items()
            if spec.get("family", "").upper() == family
        ]

    # Select one DAG per unique algorithm (diversity guarantee)
    seen_algorithms: Dict[str, tuple] = {}
    for dag_id, spec in family_dags:
        algo = _extract_algorithm_name(dag_id, spec)
        if algo not in seen_algorithms:
            seen_algorithms[algo] = (dag_id, spec)

    # Take up to max_candidates distinct algorithms
    selected = list(seen_algorithms.items())[:max_candidates]

    # Guarantee minimum of 3 — if fewer distinct algos exist, re-pick variants
    if len(selected) < 3:
        for dag_id, spec in family_dags:
            algo = _extract_algorithm_name(dag_id, spec)
            variant = spec.get("variant", spec.get("name", "Standard"))
            key = f"{algo}_{variant}"
            if key not in {s[0] for s in selected}:
                selected.append((key, (dag_id, spec)))
            if len(selected) >= 3:
                break

    candidates: List[CandidateRecipe] = []
    for algo_key, (dag_id, spec) in selected:
        decision = spec.get("decision", {})
        pipeline_actions = decision.get("pipeline_actions", {})
        algo_name = _extract_algorithm_name(dag_id, spec)

        candidates.append(CandidateRecipe(
            recipe_id=f"recipe_{dag_id.lower()}_{algo_key.lower().replace(' ', '_')}",
            dag_id=dag_id,
            algo_family=family,
            hyperparameters={
                "algorithm": algo_name,
                "variant": spec.get("variant", "Standard"),
                **{k: v for k, v in pipeline_actions.items() if k in ("scaling", "imputation", "outlier_handling")},
            },
            feature_config={
                k: v for k, v in pipeline_actions.items()
                if k in ("encoding", "feature_selection", "dimensionality_reduction")
            },
        ))

    logger.info(f"[MultiDAGResolver] Resolved {len(candidates)} candidates for family '{family}': "
                f"{[c.dag_id for c in candidates]}")
    return candidates
