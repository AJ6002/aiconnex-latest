"""
aiconnex_agent/platform_kb/terminology_service.py

Unified Terminology Lookup Engine & Semantic Normalization Service for AIConnex (Sprint 2).
Provides:
- Exact & Synonym Term Resolution (`resolve_term`)
- Dataset Column Pattern Normalization (`resolve_column`)
- Conversational Business Phrase Normalization (`resolve_phrase`)
- Typed Related Concept Traversal (`get_related_terms`)
- Multi-tier Storage Sync (YAML Registries, PostgreSQL `knowledge_terminology`, Neo4j, Qdrant)
"""

import os
import re
import yaml
import json
import logging
from typing import Dict, List, Any, Optional, Literal

from agentic.platform_kb.schemas import (
    TerminologyTermRecord,
    CanonicalTermRelation,
    CanonicalTermResolution,
    ContextRequest,
)
from agentic.platform_kb.db_client import KBInfraClient
from agentic.platform_kb.embedder import EmbeddingEngine, QdrantUpserter

logger = logging.getLogger(__name__)

TERMINOLOGY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "05_terminology",
)


class TerminologyService:
    """
    Unified Terminology Service Facade for AIConnex Agents.
    Resolves jargon, acronyms, column headers, and business phrasing into canonical concept IDs.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        embedder: Optional[EmbeddingEngine] = None,
        terminology_dir: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.embedder = embedder or EmbeddingEngine()
        self.terminology_dir = terminology_dir or TERMINOLOGY_DIR

        self.canonical_terms: Dict[str, TerminologyTermRecord] = {}
        self.synonyms_map: Dict[str, Dict[str, Any]] = {}
        self.related_concepts_map: Dict[str, Dict[str, Any]] = {}
        self.column_mappings: List[Dict[str, Any]] = []
        self.units_vocabulary: List[Dict[str, Any]] = []

        # Load deterministic YAML registries into memory
        self.reload_registries()

    def reload_registries(self) -> None:
        """Loads canonical terms, synonyms, column mappings, and units from 05_terminology/."""
        if not os.path.exists(self.terminology_dir):
            logger.warning(f"Terminology directory not found at: {self.terminology_dir}")
            return

        # 1. Load canonical terms
        ct_file = os.path.join(self.terminology_dir, "canonical_terms.yaml")
        if os.path.exists(ct_file):
            with open(ct_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for t in data.get("canonical_terms", []):
                    rec = TerminologyTermRecord(**t)
                    self.canonical_terms[rec.term_id] = rec

        # 2. Load synonyms & related maps
        syn_file = os.path.join(self.terminology_dir, "synonyms.yaml")
        if os.path.exists(syn_file):
            with open(syn_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.synonyms_map = data.get("synonyms_map", {})
                self.related_concepts_map = data.get("related_concepts_map", {})

        # 3. Load column mappings
        col_file = os.path.join(self.terminology_dir, "column_mappings.yaml")
        if os.path.exists(col_file):
            with open(col_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.column_mappings = data.get("column_mappings", [])

        # 4. Load units vocabulary
        unit_file = os.path.join(self.terminology_dir, "units_vocabulary.yaml")
        if os.path.exists(unit_file):
            with open(unit_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.units_vocabulary = data.get("units_vocabulary", [])

        logger.info(
            f"Loaded Terminology Service Registries: {len(self.canonical_terms)} canonical terms, "
            f"{len(self.synonyms_map)} synonyms, {len(self.column_mappings)} column patterns, "
            f"{len(self.units_vocabulary)} unit symbols."
        )

    def resolve_term(self, term_or_alias: str, domain: Optional[str] = None) -> CanonicalTermResolution:
        """
        Resolves an acronym or term alias deterministically into a CanonicalTermRecord.
        Example: 'RUL' -> Remaining Useful Life (PHM.RUL)
                 'TDS' -> Total Dissolved Solids (WQ.TDS)
        """
        query_clean = term_or_alias.strip().lower()

        # 1. Direct Term ID match
        if query_clean.upper() in self.canonical_terms:
            rec = self.canonical_terms[query_clean.upper()]
            unit_symbol = rec.unit.get("canonical") if rec.unit else None
            return CanonicalTermResolution(
                input_text=term_or_alias,
                match_type="exact",
                confidence=1.0,
                term=rec,
                suggested_unit=unit_symbol,
                suggested_entity_type="Measurement" if rec.term_type == "measurement" else "IndustrialConcept"
            )

        # 2. Synonym / Abbreviation map match
        if query_clean in self.synonyms_map:
            syn_entry = self.synonyms_map[query_clean]
            t_id = syn_entry["canonical_term_id"]
            if t_id in self.canonical_terms:
                rec = self.canonical_terms[t_id]
                unit_symbol = rec.unit.get("canonical") if rec.unit else None
                return CanonicalTermResolution(
                    input_text=term_or_alias,
                    match_type="alias",
                    confidence=0.98 if syn_entry.get("match_type") == "synonym" else 1.0,
                    term=rec,
                    suggested_unit=unit_symbol,
                    suggested_entity_type="Measurement" if rec.term_type == "measurement" else "IndustrialConcept"
                )

        # 3. Fallback: Search canonical names
        for rec in self.canonical_terms.values():
            if rec.canonical_name.lower() == query_clean:
                unit_symbol = rec.unit.get("canonical") if rec.unit else None
                return CanonicalTermResolution(
                    input_text=term_or_alias,
                    match_type="exact",
                    confidence=1.0,
                    term=rec,
                    suggested_unit=unit_symbol,
                    suggested_entity_type="Measurement" if rec.term_type == "measurement" else "IndustrialConcept"
                )

        return CanonicalTermResolution(
            input_text=term_or_alias,
            match_type="none",
            confidence=0.0,
            term=None
        )

    def resolve_column(self, column_name: str) -> CanonicalTermResolution:
        """
        Maps a raw dataset column header (e.g., 'tds_mg_l', 'cod_ppm', 'temp_c')
        to canonical term concept, unit, and inferred entity type.
        """
        col_clean = column_name.strip().lower()

        # 1. Exact match against pre-configured column patterns
        for item in self.column_mappings:
            pattern = item.get("pattern", "").lower()
            if pattern == col_clean or col_clean.startswith(pattern):
                t_id = item.get("canonical_id")
                rec = self.canonical_terms.get(t_id)
                unit_val = item.get("unit") or (rec.unit.get("canonical") if rec and rec.unit else None)
                return CanonicalTermResolution(
                    input_text=column_name,
                    match_type="column_pattern",
                    confidence=0.95,
                    term=rec,
                    suggested_unit=unit_val,
                    suggested_entity_type="Measurement"
                )

        # 2. Try generic term resolution
        res = self.resolve_term(col_clean)
        if res.match_type != "none":
            return res

        return CanonicalTermResolution(
            input_text=column_name,
            match_type="none",
            confidence=0.0,
            term=None
        )

    def resolve_phrase(self, phrase: str) -> List[CanonicalTermResolution]:
        """
        Normalizes conversational business phrases (e.g. 'predict when machine needs servicing')
        into candidate canonical concepts (predictive_maintenance, remaining_useful_life).
        """
        phrase_lower = phrase.lower()
        resolutions = []

        # Business phrase pattern mappings
        phrase_rules = [
            (r"predict|servicing|maintenance|service", "PHM.PDM"),
            (r"equipment health|machine condition|health score", "PHM.RUL"),
            (r"vibration|bearing|noise", "PARAM.VIB"),
            (r"dissolved solids|tds", "WQ.TDS"),
            (r"oxygen demand|cod|bod", "WQ.COD"),
            (r"scada|plc|dcs|hmi", "TERM-SCADA-SCADA")
        ]

        for pattern, t_id in phrase_rules:
            if re.search(pattern, phrase_lower):
                rec = self.canonical_terms.get(t_id)
                if rec:
                    unit_val = rec.unit.get("canonical") if rec.unit else None
                    resolutions.append(
                        CanonicalTermResolution(
                            input_text=phrase,
                            match_type="semantic",
                            confidence=0.88,
                            term=rec,
                            suggested_unit=unit_val,
                            suggested_entity_type="IndustrialConcept"
                        )
                    )

        return resolutions

    def get_related_terms(self, term_id: str, relation_type: Optional[str] = None) -> List[TerminologyTermRecord]:
        """
        Returns related concept terms while preserving distinction between synonyms and related concepts.
        """
        results = []
        rec = self.canonical_terms.get(term_id)
        if not rec:
            return results

        # Check related_concepts_map
        rel_info = self.related_concepts_map.get(rec.abbreviations[0] if rec.abbreviations else rec.canonical_name, {})
        for rel in rel_info.get("related_concepts", []):
            target_id = rel.get("term_id")
            if target_id and target_id in self.canonical_terms:
                results.append(self.canonical_terms[target_id])

        return results

    def sync_to_postgres(self) -> int:
        """
        Provisions PostgreSQL table `knowledge_terminology` and populates canonical terms.
        """
        conn = self.db_client.get_postgres_connection()
        cur = conn.cursor()

        ddl = """
        CREATE TABLE IF NOT EXISTS knowledge_terminology (
            term_id VARCHAR(64) PRIMARY KEY,
            canonical_name VARCHAR(255) NOT NULL,
            term_type VARCHAR(64) NOT NULL,
            definition TEXT NOT NULL,
            synonyms TEXT[],
            abbreviations TEXT[],
            domain TEXT[],
            unit VARCHAR(64),
            source VARCHAR(255),
            status VARCHAR(32) DEFAULT 'Approved',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_term_canonical_name ON knowledge_terminology(LOWER(canonical_name));
        """
        cur.execute(ddl)
        conn.commit()

        upsert_sql = """
        INSERT INTO knowledge_terminology (term_id, canonical_name, term_type, definition, synonyms, abbreviations, domain, unit, source, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (term_id) DO UPDATE SET
            canonical_name = EXCLUDED.canonical_name,
            definition = EXCLUDED.definition,
            synonyms = EXCLUDED.synonyms,
            abbreviations = EXCLUDED.abbreviations,
            domain = EXCLUDED.domain,
            unit = EXCLUDED.unit,
            updated_at = CURRENT_TIMESTAMP;
        """

        count = 0
        for t in self.canonical_terms.values():
            unit_val = t.unit.get("canonical") if t.unit else None
            src_val = t.source[0] if t.source else "Canonical Terminology Registry"
            cur.execute(
                upsert_sql,
                (
                    t.term_id,
                    t.canonical_name,
                    t.term_type,
                    t.definition,
                    t.synonyms,
                    t.abbreviations,
                    t.domain,
                    unit_val,
                    src_val,
                    t.status,
                ),
            )
            count += 1

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Successfully synced {count} canonical terms to PostgreSQL table 'knowledge_terminology'.")
        return count
