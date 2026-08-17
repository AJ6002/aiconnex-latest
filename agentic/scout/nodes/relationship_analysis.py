"""
relationship_analysis_node (Task 5) — Scout stage 4 of 9.
==========================================================
Detects foreign-key candidates and entity linkages between tables.

For single-file uploads (structure_analysis.tables has <=1 entry), the graph
is trivially empty — the node runs but produces is_multi_table=False and
zero edges, cleanly and without error.

Detection heuristics for multi-table archives:
  1. Column-name similarity (identical or one is a suffix of the other)
  2. Dtype compatibility (both numeric or both string-y)
  3. Value-set overlap (>= 30% of "from" values present in "to")

Reads:  state.structure_analysis (per-table schemas), state.entity_inventory
Writes: state.relationship_graph
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Set

from agentic.schemas import RelationshipEdge, RelationshipGraph
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_MIN_OVERLAP = 0.3
_MAX_VALUES_SAMPLED = 5000


def _load_column_values(csv_path: Path, column: str) -> Set:
    import pandas as pd
    try:
        s = pd.read_csv(csv_path, low_memory=False, usecols=[column], nrows=_MAX_VALUES_SAMPLED)
        return set(s[column].dropna().unique().tolist())
    except Exception as exc:
        logger.debug(f"[Scout/relationship_analysis] Could not read {column} from {csv_path.name}: {exc}")
        return set()


def _dtypes_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    numeric = {"integer", "float"}
    if a in numeric and b in numeric:
        return True
    return False


def _column_names_similar(a: str, b: str) -> bool:
    if a == b:
        return True
    al, bl = a.lower(), b.lower()
    if al == bl:
        return True
    # One is a suffix of the other (e.g. "unit_id" and "id")
    return al.endswith("_" + bl) or bl.endswith("_" + al)


def relationship_analysis_node(state: MasterAgentState) -> Dict[str, Any]:
    logger.info("[Scout/relationship_analysis] Starting")

    if state.structure_analysis is None:
        return {"relationship_graph": RelationshipGraph().model_dump()}

    sa = state.structure_analysis
    # Support both Pydantic-model and dict shapes (LangGraph deserialises to dict via msgpack)
    tables_iter = sa.tables if hasattr(sa, "tables") else sa.get("tables", [])
    tables = list(tables_iter or [])

    if len(tables) < 2:
        graph = RelationshipGraph(is_multi_table=False, table_count=len(tables))
        logger.info(f"[Scout/relationship_analysis] Single-table upload — empty graph")
        return {"relationship_graph": graph.model_dump()}

    # Extract per-table (filename -> columns:{col->dtype}, row_count)
    def _table_columns(t) -> Dict[str, str]:
        if hasattr(t, "columns"):
            return dict(t.columns or {})
        return dict((t or {}).get("columns") or {})

    def _table_name(t) -> str:
        return getattr(t, "filename", None) or (t or {}).get("filename", "unknown")

    # We need the per-table CSV paths to sample values. structure_analysis's
    # tables entries store filenames only; we reconstruct paths from output_dir.
    output_dir = sa.output_dir if hasattr(sa, "output_dir") else (sa or {}).get("output_dir")
    if not output_dir:
        graph = RelationshipGraph(is_multi_table=True, table_count=len(tables))
        logger.warning("[Scout/relationship_analysis] No output_dir on structure_analysis — cannot sample values")
        return {"relationship_graph": graph.model_dump()}

    output_root = Path(output_dir)

    # Enumerate candidate (table_a, col_a, table_b, col_b) pairs where names look similar
    candidates: List[tuple] = []
    for i, t_a in enumerate(tables):
        for j, t_b in enumerate(tables):
            if i >= j:
                continue
            name_a, name_b = _table_name(t_a), _table_name(t_b)
            cols_a, cols_b = _table_columns(t_a), _table_columns(t_b)
            for col_a, dt_a in cols_a.items():
                for col_b, dt_b in cols_b.items():
                    if not _column_names_similar(col_a, col_b):
                        continue
                    if not _dtypes_compatible(dt_a, dt_b):
                        continue
                    candidates.append((name_a, col_a, name_b, col_b))

    # For each candidate, compute value overlap
    edges: List[RelationshipEdge] = []
    for name_a, col_a, name_b, col_b in candidates:
        path_a = output_root / name_a
        path_b = output_root / name_b
        if not path_a.exists() or not path_b.exists():
            continue
        vals_a = _load_column_values(path_a, col_a)
        vals_b = _load_column_values(path_b, col_b)
        if not vals_a or not vals_b:
            continue
        overlap = len(vals_a & vals_b) / max(len(vals_a), 1)
        if overlap >= _MIN_OVERLAP:
            edges.append(
                RelationshipEdge(
                    from_table=name_a, from_column=col_a,
                    to_table=name_b, to_column=col_b,
                    edge_type="fk_candidate",
                    overlap_score=round(overlap, 3),
                    reason=(
                        f"Name similarity + dtype compatibility; "
                        f"{len(vals_a & vals_b)}/{len(vals_a)} sampled '{col_a}' values found in '{col_b}'"
                    ),
                )
            )

    graph = RelationshipGraph(edges=edges, is_multi_table=True, table_count=len(tables))
    logger.info(
        f"[Scout/relationship_analysis] {len(tables)} tables, "
        f"{len(candidates)} candidate pairs, {len(edges)} edges retained "
        f"(threshold overlap >= {_MIN_OVERLAP})"
    )
    return {
        "relationship_graph": graph.model_dump(),
        "active_agent": "scout",
    }
