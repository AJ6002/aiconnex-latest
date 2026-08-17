"""
aiconnex_agent/platform_kb/methodology_service.py

Unified Methodology Service Facade for Sprint 3 ML Methodology KB.
Provides data-science-grounded technical queries:
- `get_applicable_methods`: Query methods matching problem family & dataset characteristics.
- `get_method`: Retrieve canonical MLMethodRecord details & anti-patterns.
- `recommend_baselines`: Retrieve canonical baseline algorithms for a problem family.
- `sync_to_postgres`: Provisions & populates PostgreSQL `knowledge_ml_methods` table.
"""

import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional

from agentic.platform_kb.schemas import MLMethodRecord, ContextRequest
from agentic.platform_kb.db_client import KBInfraClient

logger = logging.getLogger(__name__)

ML_METHODOLOGY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "aiconnex_knowledge",
    "06_ml_methodology",
)


class MethodologyService:
    """
    Unified Methodology Service Facade for AIConnex Agents.
    Serves MLMethodRecord contracts and technical applicability rules.
    """

    def __init__(
        self,
        db_client: Optional[KBInfraClient] = None,
        registry_dir: Optional[str] = None,
    ):
        self.db_client = db_client or KBInfraClient()
        self.registry_dir = registry_dir or ML_METHODOLOGY_DIR
        self.methods: Dict[str, MLMethodRecord] = {}

        self.reload_registry()

    def reload_registry(self) -> None:
        """Loads canonical ML methods from aiconnex_knowledge/06_ml_methodology/canonical_methods.yaml."""
        filepath = os.path.join(self.registry_dir, "canonical_methods.yaml")
        if not os.path.exists(filepath):
            logger.warning(f"ML methodology registry file not found at: {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            for item in data.get("canonical_methods", []):
                rec = MLMethodRecord(**item)
                self.methods[rec.method_id] = rec

        logger.info(f"Loaded Methodology Service Registry with {len(self.methods)} canonical ML methods.")

    def get_method(self, method_id: str) -> Optional[MLMethodRecord]:
        """Retrieves a single MLMethodRecord by ID."""
        return self.methods.get(method_id.upper()) or self.methods.get(method_id)

    def get_applicable_methods(
        self,
        problem_family: str,
        data_characteristics: Optional[Dict[str, Any]] = None,
    ) -> List[MLMethodRecord]:
        """
        Queries candidate ML methods matching a problem family (e.g. 'Prognostics')
        and filters against dataset capability requirements.
        """
        candidates = [
            m for m in self.methods.values()
            if m.problem_family.lower() == problem_family.lower()
        ]

        if not data_characteristics:
            return candidates

        filtered = []
        for m in candidates:
            # Check multivariate requirement
            if data_characteristics.get("is_multivariate") and not m.data_compatibility.get("supports_multivariate", True):
                continue
            # Check irregular sampling
            if data_characteristics.get("is_irregular_sampling") and not m.data_compatibility.get("handles_irregular_sampling", True):
                continue
            # Check sample size constraints
            if data_characteristics.get("sample_size_category") == "small_n" and m.minimum_sample_size == "data_hungry":
                continue

            filtered.append(m)

        return filtered or candidates

    def recommend_baselines(self, problem_family: str) -> List[str]:
        """Returns baseline methods for a problem family (e.g., 'Prognostics' -> ['linear_degradation', 'ML-PROG-WEIBULL'])."""
        baselines = []
        for m in self.methods.values():
            if m.problem_family.lower() == problem_family.lower():
                if m.capacity_level == "baseline" or m.canonical_baseline:
                    baselines.append(m.name)
                    if m.canonical_baseline:
                        baselines.append(m.canonical_baseline)
        return list(dict.fromkeys(baselines))

    def sync_to_postgres(self) -> int:
        """Provisions PostgreSQL table `knowledge_ml_methods` and populates records."""
        conn = self.db_client.get_postgres_connection()
        cur = conn.cursor()

        ddl = """
        CREATE TABLE IF NOT EXISTS knowledge_ml_methods (
            method_id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            problem_family VARCHAR(64) NOT NULL,
            task_type VARCHAR(128) NOT NULL,
            lifecycle_phase VARCHAR(64) NOT NULL,
            model_family VARCHAR(64) NOT NULL,
            capacity_level VARCHAR(32) NOT NULL,
            interpretability VARCHAR(32) NOT NULL,
            canonical_baseline VARCHAR(255),
            primary_metrics TEXT[],
            assumptions TEXT[],
            limitations TEXT[],
            anti_patterns TEXT[],
            status VARCHAR(32) DEFAULT 'Approved',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ml_problem_family ON knowledge_ml_methods(LOWER(problem_family));
        """
        cur.execute(ddl)
        conn.commit()

        upsert_sql = """
        INSERT INTO knowledge_ml_methods (
            method_id, name, problem_family, task_type, lifecycle_phase,
            model_family, capacity_level, interpretability, canonical_baseline,
            primary_metrics, assumptions, limitations, anti_patterns, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (method_id) DO UPDATE SET
            name = EXCLUDED.name,
            problem_family = EXCLUDED.problem_family,
            task_type = EXCLUDED.task_type,
            primary_metrics = EXCLUDED.primary_metrics,
            assumptions = EXCLUDED.assumptions,
            limitations = EXCLUDED.limitations,
            anti_patterns = EXCLUDED.anti_patterns,
            updated_at = CURRENT_TIMESTAMP;
        """

        count = 0
        for m in self.methods.values():
            cur.execute(
                upsert_sql,
                (
                    m.method_id,
                    m.name,
                    m.problem_family,
                    m.task_type,
                    m.lifecycle_phase,
                    m.model_family,
                    m.capacity_level,
                    m.interpretability,
                    m.canonical_baseline,
                    m.primary_metrics,
                    m.assumptions,
                    m.limitations,
                    m.anti_patterns,
                    m.status,
                ),
            )
            count += 1

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Successfully synced {count} ML method records to PostgreSQL table 'knowledge_ml_methods'.")
        return count
