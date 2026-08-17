"""
aiconnex_agent/platform_kb/source_register.py

Master Source Register gatekeeper for the Platform Knowledge Base.
Parses aiconnex_knowledge/01_source_register/source_register.csv,
validates records against KnowledgeSourceRecord schema, and enforces the
strict `status == 'Approved'` ingestion gate.
"""

import os
import csv
import logging
from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from agentic.platform_kb.schemas import KnowledgeSourceRecord

logger = logging.getLogger(__name__)

DEFAULT_REGISTER_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "01_source_register",
    "source_register.csv",
)


class SourceRegisterManager:
    """
    Gatekeeper Manager for the Master Source Register.
    Controls access to knowledge sources and enforces approval status filtering.
    """

    def __init__(self, register_path: Optional[str] = None):
        self.register_path = register_path or DEFAULT_REGISTER_CSV
        self._records_cache: Optional[List[KnowledgeSourceRecord]] = None

    def clear_cache(self) -> None:
        """Invalidates the in-memory source record cache."""
        self._records_cache = None

    def load_all_sources(self, force_reload: bool = False) -> List[KnowledgeSourceRecord]:
        """
        Loads and validates all source records from CSV with in-memory caching.
        
        Args:
            force_reload: If True, bypasses in-memory cache and re-reads CSV from disk.
        """
        if self._records_cache is not None and not force_reload:
            return self._records_cache

        if not os.path.exists(self.register_path):
            raise FileNotFoundError(f"Source register CSV not found at: {self.register_path}")

        records: List[KnowledgeSourceRecord] = []
        with open(self.register_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line_num, row in enumerate(reader, start=2):
                # Clean empty string fields to None for optional Pydantic field validation
                cleaned_row = {
                    k: (v.strip() if v and v.strip() != "" else None)
                    for k, v in row.items()
                    if k is not None
                }
                try:
                    record = KnowledgeSourceRecord(**cleaned_row)
                    records.append(record)
                except ValidationError as err:
                    logger.error(f"Row {line_num} in {self.register_path} failed validation: {err}")
                    raise ValueError(f"Invalid record at line {line_num} in source register CSV: {err}") from err

        self._records_cache = records
        return records

    def get_approved_sources(self, domain: str = "platform") -> List[KnowledgeSourceRecord]:
        """
        Enforces the Gatekeeper Rule:
        Only returns source records where status == 'Approved' and matching domain.
        """
        all_sources = self.load_all_sources()
        approved = [
            s for s in all_sources
            if s.status == "Approved" and (domain == "all" or s.knowledge_domain == domain)
        ]
        return approved

    def get_source_by_id(self, source_id: str) -> Optional[KnowledgeSourceRecord]:
        """Retrieves a single source record by source_id. Returns None if not found."""
        for s in self.load_all_sources():
            if s.source_id == source_id:
                return s
        return None

