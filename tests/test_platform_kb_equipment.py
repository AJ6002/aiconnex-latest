"""
tests/test_platform_kb_equipment.py

Comprehensive Unit & Competency Test Suite for Sprint 4 Equipment & Asset KB.
Validates:
1. EquipmentRecord schema contract
2. Canonical equipment registry loading across 10 families
3. Equipment topology & subsystem queries
4. ISO 14224 failure modes & maintenance actions
5. Sensor & parameter monitoring queries
6. ContextBuilder integration
7. PostgreSQL table sync
8. Qdrant vector retrieval
9. Competency questions (Hierarchy, Sensors, Failure, Relationships, Domain)
10. Runtime boundary validation (Client asset non-fabrication guardrail)
"""

import pytest
from agentic.platform_kb.schemas import EquipmentRecord, ContextRequest
from agentic.platform_kb.equipment_service import EquipmentService
from agentic.platform_kb.context_builder import ContextBuilder


@pytest.fixture
def eq_svc():
    """Provides a fresh EquipmentService instance."""
    return EquipmentService()


@pytest.fixture
def ctx_builder():
    """Provides a fresh ContextBuilder instance."""
    return ContextBuilder()


def test_01_schema_validation():
    """Verify EquipmentRecord Pydantic contract validation."""
    record = EquipmentRecord(
        equipment_id="EQP-TEST-PUMP",
        name="Test Centrifugal Pump",
        equipment_class="Pump",
        category="Rotating Equipment",
        standard_ref="ISO 2858",
        subsystems=[{"subsystem_id": "SUB-1", "name": "Hydraulic End", "components": ["Impeller"]}],
        direct_components=["Baseplate"],
        monitored_sensors=[{"sensor_type": "Vibration Sensor", "measurement_property": "Vibration RMS"}],
        failure_modes=[{"failure_code": "FM-1", "name": "Cavitation", "mechanism": "Vapor bubble collapse"}],
        operating_modes=["Continuous"],
        source_documents=["PLAT-DOC-EQP-001"]
    )
    assert record.equipment_id == "EQP-TEST-PUMP"
    assert len(record.subsystems) == 1
    assert record.authority == "A"


def test_02_registry_loading(eq_svc):
    """Verify canonical equipment registry loading across all 10 families."""
    assert len(eq_svc.equipments) == 10
    classes = {e.equipment_class for e in eq_svc.equipments.values()}
    assert "Pump" in classes
    assert "Compressor" in classes
    assert "Electric Motor" in classes
    assert "Heat Exchanger" in classes
    assert "Valve" in classes
    assert "Conveyor" in classes
    assert "Tank" in classes
    assert "Package Plant" in classes


def test_03_equipment_lookup(eq_svc):
    """Verify equipment lookup by ID, name, and class."""
    pump = eq_svc.get_equipment("EQP-PUMP-CENTRIFUGAL")
    assert pump is not None
    assert pump.name == "End-Suction Centrifugal Pump"

    motor = eq_svc.get_equipment("Electric Motor")
    assert motor is not None
    assert motor.equipment_id == "EQP-MOTOR-INDUCTION"


def test_04_failure_modes_query(eq_svc):
    """Verify retrieval of ISO 14224 failure modes and maintenance actions."""
    fms = eq_svc.get_failure_modes("EQP-PUMP-CENTRIFUGAL")
    assert len(fms) >= 3
    codes = [fm["failure_code"] for fm in fms]
    assert "FM-PUMP-CAVITATION" in codes
    assert "FM-PUMP-BEARING-WEAR" in codes
    assert "FM-PUMP-SEAL-LEAK" in codes


def test_05_monitored_sensors_query(eq_svc):
    """Verify sensor monitoring relationships for equipment."""
    sensors = eq_svc.get_monitored_sensors("EQP-COMP-CENTRIFUGAL")
    assert len(sensors) >= 3
    types = [s["sensor_type"] for s in sensors]
    assert "Radial Proximity Probe" in types
    assert "RTD Temperature Sensor" in types


def test_06_context_builder_integration(ctx_builder):
    """Verify ContextBuilder.get_equipment_context returns full payload."""
    ctx = ctx_builder.get_equipment_context("EQP-MOTOR-INDUCTION")
    assert ctx["found"] is True
    assert ctx["equipment"]["name"] == "Three-Phase AC Induction Motor"
    assert len(ctx["failure_modes"]) >= 2
    assert len(ctx["monitored_sensors"]) >= 3


def test_07_postgres_sync(eq_svc):
    """Verify sync_to_postgres provisions table and upserts 10 records."""
    count = eq_svc.sync_to_postgres()
    assert count == 10


def test_08_qdrant_equipment_vector_retrieval(ctx_builder):
    """Verify semantic vector retrieval against Qdrant for equipment_asset domain."""
    req = ContextRequest(
        query="What are the components and maintenance of centrifugal pumps?",
        knowledge_domain="equipment_asset",
        top_k=3,
        min_score=0.30
    )
    res = ctx_builder.get_context(req, mode="semantic")
    assert res["evidence_pack"] is not None
    assert len(res["evidence_pack"].results) > 0


def test_09_competency_questions(eq_svc, ctx_builder):
    """Verify competency questions across Hierarchy, Sensors, Failure, Relationships, and Domain."""
    # 1. Hierarchy: What components belong to a compressor?
    comp = eq_svc.get_equipment("EQP-COMP-CENTRIFUGAL")
    subsystems = [s["name"] for s in comp.subsystems]
    assert "Compression Aero Core" in subsystems
    assert "Lube Oil Subsystem" in subsystems

    # 2. Sensors: Which sensors monitor rotating equipment?
    sensors = eq_svc.get_monitored_sensors("EQP-PUMP-CENTRIFUGAL")
    sensor_names = [s["sensor_type"] for s in sensors]
    assert "Vibration Sensor" in sensor_names

    # 3. Failure: What failure modes affect heat exchangers?
    hex_fms = eq_svc.get_failure_modes("EQP-HEX-SHELLTUBE")
    hex_fm_codes = [fm["failure_code"] for fm in hex_fms]
    assert "FM-HEX-FOULING" in hex_fm_codes

    # 4. Domain: What equipment belongs to wastewater package plants?
    wwtp = eq_svc.get_equipment("EQP-WWTP-PACKAGE")
    wwtp_subsystems = [s["name"] for s in wwtp.subsystems]
    assert "Biological Aeration Basin" in wwtp_subsystems


def test_10_runtime_boundary_validation(eq_svc, ctx_builder):
    """Verify runtime boundary guardrail: Global Equipment KB must NOT fabricate client assets."""
    # Query non-existent client-specific asset
    client_asset = eq_svc.get_equipment("Client_X_Pump_P204")
    assert client_asset is None

    # Context query for unknown client asset
    ctx = ctx_builder.get_equipment_context("Client_X_Pump_P204")
    assert ctx["found"] is False
