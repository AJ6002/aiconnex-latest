"""Scout 8-node split (Tasks 2-10 of the Upload→Platform Agent chain).

Each node is a real LangGraph node function producing one typed section of
the DatasetExplorationManifest. No stubs. See individual modules for detail.
"""

from agentic.scout.nodes.archive_discovery import archive_discovery_node
from agentic.scout.nodes.structure_analysis import structure_analysis_node
from agentic.scout.nodes.entity_analysis import entity_analysis_node
from agentic.scout.nodes.relationship_analysis import relationship_analysis_node
from agentic.scout.nodes.temporal_analysis import temporal_analysis_node
from agentic.scout.nodes.feature_analysis import feature_analysis_node
from agentic.scout.nodes.quality_analysis import quality_analysis_node
from agentic.scout.nodes.statistical_analysis import statistical_analysis_node
from agentic.scout.nodes.exploration_synthesizer import exploration_synthesizer_node

__all__ = [
    "archive_discovery_node",
    "structure_analysis_node",
    "entity_analysis_node",
    "relationship_analysis_node",
    "temporal_analysis_node",
    "feature_analysis_node",
    "quality_analysis_node",
    "statistical_analysis_node",
    "exploration_synthesizer_node",
]
