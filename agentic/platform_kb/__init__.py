"""
AIConnex Platform Knowledge Base Engine
"""

from agentic.platform_kb.schemas import (
    KnowledgeSourceRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
    ContextRequest,
    EvidenceItem,
    EvidencePack,
    PlatformCapabilities,
    ManifestRegistryEntry,
    EquipmentRecord,
    StandardRecord,
    TenantRecord,
    ProjectRecord,
    TenantAssetRecord,
    TenantContext,
)
from agentic.platform_kb.source_register import SourceRegisterManager
from agentic.platform_kb.config import KBConfig, get_kb_config
from agentic.platform_kb.db_client import KBInfraClient, CriticalDependencyError
from agentic.platform_kb.normalizer import MarkdownNormalizer, NormalizedSection
from agentic.platform_kb.chunker import HierarchicalChunker, estimate_token_count, compute_sha256
from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter, EmbeddingPipeline
from agentic.platform_kb.document_store import MinIODocumentStore, MinIOStoragePipeline, compute_file_sha256
from agentic.platform_kb.deterministic_store import DeterministicStore, CatalogPipeline
from agentic.platform_kb.retrieval_service import RetrievalService
from agentic.platform_kb.equipment_service import EquipmentService
from agentic.platform_kb.standards_service import StandardsService
from agentic.platform_kb.tenant_service import TenantService
from agentic.platform_kb.context_builder import ContextBuilder

__all__ = [
    "KnowledgeSourceRecord",
    "KnowledgeDocumentRecord",
    "KnowledgeChunkRecord",
    "ContextRequest",
    "EvidenceItem",
    "EvidencePack",
    "PlatformCapabilities",
    "ManifestRegistryEntry",
    "EquipmentRecord",
    "StandardRecord",
    "TenantRecord",
    "ProjectRecord",
    "TenantAssetRecord",
    "TenantContext",
    "SourceRegisterManager",
    "KBConfig",
    "get_kb_config",
    "KBInfraClient",
    "CriticalDependencyError",
    "MarkdownNormalizer",
    "NormalizedSection",
    "HierarchicalChunker",
    "estimate_token_count",
    "compute_sha256",
    "EmbeddingEngine",
    "QdrantUpserter",
    "EmbeddingPipeline",
    "MinIODocumentStore",
    "MinIOStoragePipeline",
    "compute_file_sha256",
    "DeterministicStore",
    "CatalogPipeline",
    "RetrievalService",
    "EquipmentService",
    "StandardsService",
    "TenantService",
    "ContextBuilder",
]




