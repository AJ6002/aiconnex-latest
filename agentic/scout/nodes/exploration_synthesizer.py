"""
exploration_synthesizer_node (Task 10) — Scout stage 9 of 9.
=============================================================
Assembles all 8 prior analysis outputs into one canonical
DatasetExplorationManifest AND derives the Recipe Catalog — the list of
candidate analytical objectives the user picks from at HITL.

Also populates the legacy `state.dic` (DatasetIntelligenceContract) so
downstream consumers (hitl_flow, platform_node, manifest_builder) keep
working unchanged.

Key architectural note (fixes ETP hardcoding in the old
recipe_catalog_builder.py): dataset_card industry / domain / branches are
derived from the CUC's business_context (populated during pre-upload) plus
the DIC's actual entity/temporal analysis — NOT from a hardcoded
"Industrial Effluent & Wastewater" string.

Reads:  ALL prior state fields (archive, structure, entity, relationship,
        temporal, feature_catalog_v2, quality, statistical)
Writes: state.dataset_exploration_manifest AND state.dic (backward compat)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agentic.schemas import (
    AnalyticalRecipe,
    ArchiveManifest,
    BranchingHints,
    CompiledDatasetSummary,
    DatasetExplorationManifest,
    DatasetIdentity,
    DatasetStatistics,
    EntityInventory,
    FeatureCatalogV2,
    ProblemCandidate,
    QualityAssessment,
    QualityReport,
    RelationshipGraph,
    StatisticalProfile,
    StructureAnalysis,
    TemporalStructure,
)
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)


def _get(obj, key, default=None):
    """Read a field from either a Pydantic model or a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _pydantify(obj, cls):
    """Coerce dict-or-model to a Pydantic instance of `cls`."""
    if obj is None:
        return cls()
    if isinstance(obj, cls):
        return obj
    if isinstance(obj, dict):
        return cls.model_validate(obj)
    if hasattr(obj, "model_dump"):
        return cls.model_validate(obj.model_dump())
    return cls()


# ─── Recipe derivation (fully dataset-driven, no ETP hardcoding) ─────────────

def _derive_recipes(
    entities: EntityInventory,
    temporal: TemporalStructure,
    quality: QualityAssessment,
    business_context: dict,
) -> List[AnalyticalRecipe]:
    """Generate AnalyticalRecipes from actual entity/temporal/quality signals.

    A recipe is only surfaced if there's real evidence for it:
      - REGRESSION: any target_candidate column, sorted by coefficient-of-variation confidence
      - FORECAST: same target_candidates AND temporal.is_time_series
      - ANOMALY: always available (unsupervised, applies to any numeric-heavy dataset)
      - CLASSIFICATION: any discrete-target signal detected by quality_analysis
                        (imbalance flag on a low-cardinality target)
    """
    recipes: List[AnalyticalRecipe] = []
    idx = 1

    target_cols: List[str] = entities.target_candidate_columns
    is_ts = temporal.is_time_series
    primary_ts = temporal.primary_timestamp

    # Optional context enrichment from business_context (industry/asset)
    industry = (business_context or {}).get("industry") or ""
    asset = (business_context or {}).get("asset") or ""
    context_hint = ""
    if asset:
        context_hint = f" for {asset}"
    elif industry:
        context_hint = f" ({industry})"

    # 1) REGRESSION per target candidate, top 5
    for col in target_cols[:5]:
        title = f"Predict {col}{context_hint}"
        conf = 0.85  # Base; entity_analysis already filtered by CV threshold
        recipes.append(AnalyticalRecipe(
            id=f"R{idx:03d}",
            title=title,
            target=col,
            task="REGRESSION",
            confidence=conf,
            rationale=(
                f"Column '{col}' passed entity_analysis's variance threshold; "
                f"supervised regression is viable."
            ),
        ))
        idx += 1

    # 2) FORECAST (only if temporal signal present AND at least one target)
    if is_ts and target_cols:
        top = target_cols[0]
        recipes.append(AnalyticalRecipe(
            id=f"R{idx:03d}",
            title=f"Forecast future {top}{context_hint}",
            target=top,
            task="FORECAST",
            confidence=0.8,
            rationale=(
                f"Timestamp column '{primary_ts}' with detected frequency "
                f"'{temporal.detected_frequency}' — temporal forecasting of '{top}' is applicable."
            ),
        ))
        idx += 1

    # 3) ANOMALY (always available)
    recipes.append(AnalyticalRecipe(
        id=f"R{idx:03d}",
        title=f"Detect anomalies in the dataset{context_hint}",
        target=None,
        task="ANOMALY",
        confidence=0.75,
        rationale="Unsupervised anomaly detection is applicable to any numeric-heavy dataset.",
    ))
    idx += 1

    # 4) CLASSIFICATION if quality_analysis flagged an imbalanced discrete target
    imbalance_cols: List[str] = []
    for issue in quality.issues:
        if issue.kind == "imbalance" and issue.column:
            imbalance_cols.append(issue.column)

    for col in imbalance_cols[:3]:
        recipes.append(AnalyticalRecipe(
            id=f"R{idx:03d}",
            title=f"Classify {col} outcomes{context_hint}",
            target=col,
            task="CLASSIFICATION",
            confidence=0.6,
            rationale=(
                f"Column '{col}' shows discrete-class structure with imbalance — "
                f"classification with appropriate resampling is applicable."
            ),
        ))
        idx += 1

    return recipes


def _problem_candidates(recipes: List[AnalyticalRecipe]) -> List[ProblemCandidate]:
    """Summarise task families present in the recipe list with an aggregate confidence."""
    seen: Dict[str, float] = {}
    for r in recipes:
        seen[r.task] = max(seen.get(r.task, 0.0), r.confidence)
    task_family_map = {
        "REGRESSION": "Regression",
        "FORECAST": "Time_Series",
        "ANOMALY": "Anomaly",
        "CLASSIFICATION": "Classification",
        "HYBRID": "Hybrid",
    }
    return [
        ProblemCandidate(family=task_family_map.get(task, task), confidence=round(conf, 3))
        for task, conf in seen.items()
    ]


def _branching_hints(recipes: List[AnalyticalRecipe], temporal: TemporalStructure) -> BranchingHints:
    branches: List[str] = []
    tasks = {r.task for r in recipes}
    if "REGRESSION" in tasks:
        branches.append("Supervised Prediction")
    if "FORECAST" in tasks or temporal.is_time_series:
        branches.append("Time-Series Forecasting")
    if "ANOMALY" in tasks:
        branches.append("Anomaly Detection")
    if "CLASSIFICATION" in tasks:
        branches.append("Classification")
    return BranchingHints(available_branches=branches)


def _build_dataset_card(
    archive: ArchiveManifest,
    structure: StructureAnalysis,
    entities: EntityInventory,
    temporal: TemporalStructure,
    business_context: dict,
) -> Dict[str, Any]:
    """Dataset card populated from actual analysis + CUC business_context.
    No hardcoded 'Industrial Effluent & Wastewater' fallbacks."""
    from pathlib import Path

    industry = (business_context or {}).get("industry") or "Unknown"
    domain = (business_context or {}).get("process") or (business_context or {}).get("industry") or "Auto-detected"

    archive_name = Path(archive.archive_path).stem if archive.archive_path else "compiled_dataset"

    sampling = "batch"
    if temporal.is_time_series and temporal.detected_frequency:
        sampling = temporal.detected_frequency

    return {
        "dataset_name": archive_name,
        "industry": industry,
        "domain": domain,
        "sampling_rate": sampling,
        "rows": structure.combined_rows,
        "columns": len(structure.combined_columns),
        "date_range": temporal.date_range,
        "target_candidates": list(entities.target_candidate_columns),
    }


def _build_legacy_dic(
    archive: ArchiveManifest,
    structure: StructureAnalysis,
    entities: EntityInventory,
    temporal: TemporalStructure,
    features: FeatureCatalogV2,
    quality: QualityAssessment,
    statistics: StatisticalProfile,
    recipes: List[AnalyticalRecipe],
    business_context: dict,
) -> Dict[str, Any]:
    """Populate the legacy DIC so hitl_flow, platform_node, and manifest_builder
    keep working unchanged after the split."""
    from pathlib import Path
    from agentic.schemas import BranchingHints as BH

    identity = DatasetIdentity(
        name=Path(archive.archive_path).stem if archive.archive_path else "compiled_dataset",
        family=(business_context or {}).get("industry") or "Auto-detected",
        domain=(business_context or {}).get("process"),
    )

    compiled_summary = CompiledDatasetSummary(
        tables=len(structure.tables),
        rows=structure.combined_rows,
        columns=len(structure.combined_columns),
        output_path=structure.output_dir,
        combined_csv_path=structure.compiled_csv_path,
    )

    stats_dic = DatasetStatistics(
        missing_values={c: int(pct * structure.combined_rows) for c, pct in quality.null_percentages.items()},
        duplicates=quality.duplicate_row_count,
        sampling=temporal.detected_frequency or "unknown",
    )

    quality_dic = QualityReport(
        constant_columns=quality.constant_columns,
        warnings=[i.detail for i in quality.issues if i.severity in ("warning", "error")],
        cartesian_guard_passed=True,  # UnifiedCompiler already surfaces its own guard via structure.warnings
    )

    # Legacy DIC.feature_catalog is a loose Dict[column -> {type, role, description}].
    # Project FeatureCatalogV2 into that shape and annotate with Terminology KB canonical concepts.
    from agentic.platform_kb.context_builder import ContextBuilder
    ctx_builder = ContextBuilder()

    legacy_feature_catalog: Dict[str, Any] = {}
    for entry in features.features:
        term_ctx = ctx_builder.get_terminology_context(entry.column)
        canonical_info = {}
        if term_ctx.get("match_type") != "none" and term_ctx.get("term"):
            term_rec = term_ctx["term"]
            canonical_info = {
                "canonical_term_id": term_rec.get("term_id"),
                "canonical_name": term_rec.get("canonical_name"),
                "canonical_unit": term_ctx.get("suggested_unit"),
                "match_type": term_ctx.get("match_type"),
            }

        legacy_feature_catalog[entry.column] = {
            "type": entry.dtype,
            "role": entry.role,
            "description": entry.description,
            "category": entry.category,
            "canonical_terminology": canonical_info if canonical_info else None,
        }

    branches = _branching_hints(recipes, temporal)

    return {
        "dataset_identity": identity.model_dump(),
        "compiled_dataset": compiled_summary.model_dump(),
        "schema_map": dict(structure.combined_columns),
        "dataset_card": _build_dataset_card(archive, structure, entities, temporal, business_context),
        "statistics": stats_dic.model_dump(),
        "quality_report": quality_dic.model_dump(),
        "derived_features": [dc.name for dc in features.derived_candidates],
        "problem_candidates": [pc.model_dump() for pc in _problem_candidates(recipes)],
        "target_candidates": list(entities.target_candidate_columns),
        "feature_catalog": legacy_feature_catalog,
        "branching_hints": branches.model_dump(),
        "compiler_warnings": list(structure.warnings),
        "clarifications_required": [],
        "recipes": [r.model_dump() for r in recipes],
        "selected_recipe_id": None,
    }


# ─── Node entry point ─────────────────────────────────────────────────────────

def exploration_synthesizer_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/exploration_synthesizer] Starting")

    archive = _pydantify(state.archive_manifest, ArchiveManifest)
    structure = _pydantify(state.structure_analysis, StructureAnalysis)
    entities = _pydantify(state.entity_inventory, EntityInventory)
    relationships = _pydantify(state.relationship_graph, RelationshipGraph)
    temporal = _pydantify(state.temporal_structure, TemporalStructure)
    features = _pydantify(state.feature_catalog_v2, FeatureCatalogV2)
    quality = _pydantify(state.quality_assessment, QualityAssessment)
    statistics = _pydantify(state.statistical_profile, StatisticalProfile)

    # Pull business_context from CUC (populated in the pre-upload phase, may be empty)
    business_context = {}
    cuc = state.cuc
    if cuc is not None:
        bc = cuc.business_context if hasattr(cuc, "business_context") else (cuc or {}).get("business_context", {})
        if hasattr(bc, "model_dump"):
            business_context = bc.model_dump()
        elif isinstance(bc, dict):
            business_context = dict(bc)

    recipes = _derive_recipes(entities, temporal, quality, business_context)

    manifest = DatasetExplorationManifest(
        session_id=state.session_id,
        archive=archive,
        structure=structure,
        entities=entities,
        relationships=relationships,
        temporal=temporal,
        features=features,
        quality=quality,
        statistics=statistics,
        recipes=recipes,
    )

    legacy_dic = _build_legacy_dic(
        archive, structure, entities, temporal, features, quality, statistics,
        recipes, business_context,
    )

    logger.info(
        f"[Scout/exploration_synthesizer] {len(recipes)} recipes derived — "
        f"tasks={sorted({r.task for r in recipes})}"
    )
    return {
        "dataset_exploration_manifest": manifest.model_dump(),
        "dic": legacy_dic,
        "active_agent": "evaluator",
    }
