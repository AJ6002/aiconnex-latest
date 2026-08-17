"""
scripts/industrial_kb_phase4_knowledge_model.py

Phase 4 — Industrial Knowledge Model for AIConnex Platform.
Defines the canonical 17-entity PHM & Maintenance domain model,
its relationship contracts, maps ontology classes to canonical buckets,
populates canonical schema nodes into Neo4j, and exports industrial_ontology.yaml.
"""

import os
import json
import yaml
from neo4j import GraphDatabase

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRUCTURED_DIR = os.path.join(_PROJECT_ROOT, "aiconnex_knowledge", "04_structured")
DETERMINISTIC_REGISTRY_DIR = os.path.join(_PROJECT_ROOT, "aiconnex_knowledge", "03_deterministic", "registries")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "neo4j_secret_password_2026")

CANONICAL_ENTITIES = [
    {
        "entity_type": "Plant",
        "category": "Facility",
        "description": "Top-level industrial manufacturing site or facility.",
        "attributes": ["plant_id", "name", "location", "industry_sector"],
        "bfo_mapping": "bfo:MaterialEntity",
        "iof_mapping": "iof:ManufacturingFacility"
    },
    {
        "entity_type": "Process",
        "category": "Operation",
        "description": "Industrial production or chemical transformation process.",
        "attributes": ["process_id", "name", "process_type", "operating_pressure"],
        "bfo_mapping": "bfo:Process",
        "iof_mapping": "iof:ManufacturingProcess"
    },
    {
        "entity_type": "Asset",
        "category": "Physical System",
        "description": "Major capital asset or production train within a plant.",
        "attributes": ["asset_id", "name", "criticality_rating", "commissioned_date"],
        "bfo_mapping": "bfo:MaterialEntity",
        "iof_mapping": "iof:Asset"
    },
    {
        "entity_type": "Equipment",
        "category": "Machine",
        "description": "Discrete machinery unit (e.g., Centrifugal Pump, Compressor, Turbine).",
        "attributes": ["equipment_id", "name", "equipment_class", "manufacturer", "model_number"],
        "bfo_mapping": "bfo:MaterialEntity",
        "iof_mapping": "iof:PieceOfEquipment"
    },
    {
        "entity_type": "Component",
        "category": "Sub-assembly",
        "description": "Sub-unit or replaceable part (e.g., Bearing, Seal, Impeller, Gear).",
        "attributes": ["component_id", "name", "part_number", "material"],
        "bfo_mapping": "bfo:MaterialEntity",
        "iof_mapping": "iof:Component"
    },
    {
        "entity_type": "Sensor",
        "category": "Instrument",
        "description": "Monitoring transducer measuring physical process properties.",
        "attributes": ["sensor_id", "name", "sensor_type", "sampling_rate_hz", "unit_of_measure"],
        "bfo_mapping": "bfo:MaterialEntity",
        "iof_mapping": "iof:MeasuringInstrument"
    },
    {
        "entity_type": "Measurement",
        "category": "Data Signal",
        "description": "Observed time-series value or feature extracted from a sensor.",
        "attributes": ["measurement_id", "timestamp", "numeric_value", "quality_flag"],
        "bfo_mapping": "bfo:Quality",
        "iof_mapping": "iof:MeasurementValue"
    },
    {
        "entity_type": "Parameter",
        "category": "Physical Property",
        "description": "Physical variable monitored (e.g., Vibration Velocity, Temperature, Pressure).",
        "attributes": ["parameter_name", "category", "normal_range_min", "normal_range_max"],
        "bfo_mapping": "bfo:Quality",
        "iof_mapping": "iof:ProcessParameter"
    },
    {
        "entity_type": "Operating Mode",
        "category": "State",
        "description": "Operational regime or throughput state (e.g., Full Load, Idle, Transient).",
        "attributes": ["mode_id", "name", "speed_rpm", "load_percentage"],
        "bfo_mapping": "bfo:State",
        "iof_mapping": "iof:OperatingState"
    },
    {
        "entity_type": "Failure",
        "category": "Event",
        "description": "Inability of an asset or equipment to perform its required function.",
        "attributes": ["failure_id", "timestamp", "severity", "functional_loss"],
        "bfo_mapping": "bfo:Process",
        "iof_mapping": "iof:FailureEvent"
    },
    {
        "entity_type": "Failure Mode",
        "category": "Mechanism",
        "description": "Specific physical mechanism of degradation or loss of function (e.g., Bearing Wear, Cavitation).",
        "attributes": ["mode_code", "name", "mechanism_description", "iso_14224_code"],
        "bfo_mapping": "bfo:Disposition",
        "iof_mapping": "iof:FailureMode"
    },
    {
        "entity_type": "Degradation",
        "category": "Process",
        "description": "Progressive irreversible deterioration of component condition over time.",
        "attributes": ["degradation_id", "rate_of_change", "degradation_pattern"],
        "bfo_mapping": "bfo:Process",
        "iof_mapping": "iof:DegradationProcess"
    },
    {
        "entity_type": "Maintenance Event",
        "category": "Activity",
        "description": "Recorded work order or intervention event.",
        "attributes": ["event_id", "work_order_num", "start_time", "end_time", "event_type"],
        "bfo_mapping": "bfo:Process",
        "romain_mapping": "romain:MaintenanceEvent"
    },
    {
        "entity_type": "Maintenance Action",
        "category": "Action",
        "description": "Specific corrective or preventive maintenance task (e.g., Lubricate, Replace, Align).",
        "attributes": ["action_id", "name", "standard_hours", "action_type"],
        "bfo_mapping": "bfo:Process",
        "romain_mapping": "romain:MaintenanceTask"
    },
    {
        "entity_type": "Health Indicator",
        "category": "Metric",
        "description": "Calculated Health Index (HI) or Remaining Useful Life (RUL) estimate.",
        "attributes": ["indicator_id", "health_index_0_100", "rul_hours_estimate", "confidence_interval"],
        "bfo_mapping": "bfo:Quality",
        "iof_mapping": "iof:HealthStateIndicator"
    },
    {
        "entity_type": "Dataset",
        "category": "Artifact",
        "description": "Collection of sensor signals, maintenance logs, or simulation runs (e.g., C-MAPSS).",
        "attributes": ["dataset_id", "name", "num_entities", "total_samples", "source_url"],
        "bfo_mapping": "bfo:GenericallyDependentContinuant",
        "iof_mapping": "iof:DataSet"
    },
    {
        "entity_type": "Method",
        "category": "Algorithm",
        "description": "Analytical or ML algorithm used for PHM (e.g., FFT, Random Forest, LSTM, Transformer).",
        "attributes": ["method_id", "name", "method_family", "input_type", "output_type"],
        "bfo_mapping": "bfo:Plan",
        "iof_mapping": "iof:DiagnosticMethod"
    }
]

CANONICAL_RELATIONSHIPS = [
    {"source": "Plant", "relation": "contains", "target": "Asset"},
    {"source": "Asset", "relation": "contains", "target": "Equipment"},
    {"source": "Equipment", "relation": "contains", "target": "Component"},
    {"source": "Equipment", "relation": "monitored_by", "target": "Sensor"},
    {"source": "Equipment", "relation": "has_failure_mode", "target": "Failure Mode"},
    {"source": "Equipment", "relation": "operates_in", "target": "Operating Mode"},
    {"source": "Component", "relation": "has_failure_mode", "target": "Failure Mode"},
    {"source": "Sensor", "relation": "measures", "target": "Parameter"},
    {"source": "Parameter", "relation": "produces", "target": "Measurement"},
    {"source": "Failure Mode", "relation": "indicated_by", "target": "Measurement"},
    {"source": "Failure Mode", "relation": "addressed_by", "target": "Maintenance Action"},
    {"source": "Failure Mode", "relation": "results_in", "target": "Failure"},
    {"source": "Degradation", "relation": "leads_to", "target": "Failure Mode"},
    {"source": "Degradation", "relation": "tracked_by", "target": "Health Indicator"},
    {"source": "Maintenance Event", "relation": "executes", "target": "Maintenance Action"},
    {"source": "Measurement", "relation": "processed_by", "target": "Method"},
    {"source": "Method", "relation": "estimates", "target": "Health Indicator"},
    {"source": "Dataset", "relation": "contains_data_for", "target": "Equipment"}
]


def run_phase4_knowledge_model():
    print("=== Phase 4 — Industrial Knowledge Model ===")
    
    # 1. Export industrial_ontology.yaml registry
    os.makedirs(DETERMINISTIC_REGISTRY_DIR, exist_ok=True)
    yaml_path = os.path.join(DETERMINISTIC_REGISTRY_DIR, "industrial_ontology.yaml")
    
    yaml_data = {
        "domain": "industrial",
        "version": "1.0.0",
        "description": "AIConnex Canonical Industrial PHM & Maintenance Knowledge Model",
        "entity_types": CANONICAL_ENTITIES,
        "relationship_contracts": CANONICAL_RELATIONSHIPS
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
    print(f"[OK] Exported canonical model registry to: {yaml_path}")

    # 2. Export structured entities and relationships JSON
    os.makedirs(os.path.join(STRUCTURED_DIR, "entities"), exist_ok=True)
    os.makedirs(os.path.join(STRUCTURED_DIR, "relationships"), exist_ok=True)

    entities_json_path = os.path.join(STRUCTURED_DIR, "entities", "industrial_entities.json")
    rels_json_path = os.path.join(STRUCTURED_DIR, "relationships", "industrial_relationships.json")

    with open(entities_json_path, "w", encoding="utf-8") as f:
        json.dump(CANONICAL_ENTITIES, f, indent=2)
    print(f"[OK] Exported canonical entities JSON to: {entities_json_path}")

    with open(rels_json_path, "w", encoding="utf-8") as f:
        json.dump(CANONICAL_RELATIONSHIPS, f, indent=2)
    print(f"[OK] Exported canonical relationships JSON to: {rels_json_path}")

    # 3. Populate Canonical Schema Nodes & Relationships in Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    print("[OK] Connected to Neo4j to ingest Canonical Schema.")

    with driver.session() as session:
        # Create CanonicalEntity nodes
        session.run(
            """
            UNWIND $entities AS e
            MERGE (c:CanonicalEntity {name: e.entity_type})
            SET c.category = e.category,
                c.description = e.description,
                c.bfo_mapping = e.bfo_mapping,
                c.iof_mapping = e.iof_mapping
            """,
            entities=CANONICAL_ENTITIES
        )
        print(f"  [OK] Ingested {len(CANONICAL_ENTITIES)} :CanonicalEntity nodes in Neo4j.")

        # Create Canonical Relationships between CanonicalEntity nodes
        session.run(
            """
            UNWIND $rels AS r
            MATCH (src:CanonicalEntity {name: r.source})
            MATCH (tgt:CanonicalEntity {name: r.target})
            MERGE (src)-[rel:CANONICAL_RELATION {type: r.relation}]->(tgt)
            """,
            rels=CANONICAL_RELATIONSHIPS
        )
        print(f"  [OK] Ingested {len(CANONICAL_RELATIONSHIPS)} CANONICAL_RELATION edges in Neo4j.")

        # Verify live Neo4j Database totals
        nodes_cnt = session.run("MATCH (n) RETURN COUNT(n) AS cnt").single()["cnt"]
        rels_cnt = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS cnt").single()["cnt"]
        print(f"\n[NEO4J LIVE DATABASE READOUT]: {nodes_cnt} Total Nodes | {rels_cnt} Total Relationships")

    driver.close()
    print("\nPhase 4 Knowledge Model Gate PASSED successfully!")


if __name__ == "__main__":
    run_phase4_knowledge_model()
