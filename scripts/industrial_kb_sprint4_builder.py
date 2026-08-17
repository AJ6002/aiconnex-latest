"""
scripts/industrial_kb_sprint4_builder.py

Phase 2: Canonical Equipment & Asset Model Builder for Sprint 4.
Compiles 10 canonical equipment models adhering to the Option A hierarchy (Plant -> Asset -> Equipment -> Subsystem -> Component)
and exports them to `aiconnex_knowledge/06_equipment_asset/canonical_equipment.yaml`.
"""

import os
import yaml
import logging
from typing import List, Dict, Any
from agentic.platform_kb.schemas import EquipmentRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EquipmentBuilder")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "aiconnex_knowledge", "06_equipment_asset")


def get_canonical_equipment_definitions() -> List[Dict[str, Any]]:
    """Returns structured canonical definitions for 10 equipment families."""
    return [
        # 1. CENTRIFUGAL PUMP
        {
            "equipment_id": "EQP-PUMP-CENTRIFUGAL",
            "name": "End-Suction Centrifugal Pump",
            "equipment_class": "Pump",
            "category": "Rotating Equipment",
            "standard_ref": "ISO 2858 / ISO 5199 / API 610",
            "subsystems": [
                {
                    "subsystem_id": "SUB-PUMP-HYDRAULIC",
                    "name": "Hydraulic Liquid End",
                    "components": ["Impeller", "Volute Casing", "Wear Ring", "Suction Nozzle", "Discharge Nozzle"]
                },
                {
                    "subsystem_id": "SUB-PUMP-ROTATING",
                    "name": "Rotating Assembly",
                    "components": ["Pump Shaft", "Radial Bearing", "Thrust Bearing", "Shaft Sleeve", "Coupling"]
                },
                {
                    "subsystem_id": "SUB-PUMP-SEALING",
                    "name": "Shaft Sealing System",
                    "components": ["Mechanical Seal", "Stuffing Box", "Gland Packing", "Lantern Ring", "Seal Flush Plan"]
                }
            ],
            "direct_components": ["Baseplate", "Drain Plug", "Oil Sight Glass"],
            "monitored_sensors": [
                {"sensor_type": "Vibration Sensor", "measurement_property": "Overall Vibration RMS", "typical_unit": "mm/s"},
                {"sensor_type": "Temperature Sensor", "measurement_property": "Bearing Housing Temperature", "typical_unit": "°C"},
                {"sensor_type": "Pressure Transmitter", "measurement_property": "Discharge Pressure", "typical_unit": "bar"},
                {"sensor_type": "Flow Meter", "measurement_property": "Flow Rate", "typical_unit": "m³/h"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-PUMP-CAVITATION",
                    "name": "Cavitation Erosion",
                    "mechanism": "Net positive suction head deficit causing vapor bubble collapse against impeller vanes",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Impeller", "Volute Casing", "Wear Ring"],
                    "typical_maintenance": "Inspect hydraulic condition, adjust suction valve, replace impeller"
                },
                {
                    "failure_code": "FM-PUMP-BEARING-WEAR",
                    "name": "Bearing Fatigue and Lubrication Degradation",
                    "mechanism": "Contaminated lubricant or unbalance causing micro-spalling on bearing races",
                    "iso_14224_code": "SER",
                    "affected_components": ["Radial Bearing", "Thrust Bearing"],
                    "typical_maintenance": "Re-grease bearing housing, balance rotor, replace bearings"
                },
                {
                    "failure_code": "FM-PUMP-SEAL-LEAK",
                    "name": "Mechanical Seal Failure",
                    "mechanism": "Dry running, thermal shock, or face distortion leading to fluid leakage",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Mechanical Seal", "Shaft Sleeve"],
                    "typical_maintenance": "Replace mechanical seal faces, verify seal flush plan flow"
                }
            ],
            "operating_modes": ["Continuous Duty", "Parallel Operation", "Intermittent Standby"],
            "source_documents": ["PLAT-DOC-EQP-004", "PLAT-DOC-001"],
            "authority": "A",
            "status": "Approved"
        },

        # 2. CENTRIFUGAL COMPRESSOR
        {
            "equipment_id": "EQP-COMP-CENTRIFUGAL",
            "name": "Multi-Stage Centrifugal Gas Compressor",
            "equipment_class": "Compressor",
            "category": "Rotating Equipment",
            "standard_ref": "ISO 5390 / ISO TR 12942 / API 617",
            "subsystems": [
                {
                    "subsystem_id": "SUB-COMP-COMPRESSION",
                    "name": "Compression Aero Core",
                    "components": ["Impellers", "Diffusers", "Inlet Guide Vanes", "Diaphragms", "Rotor Shaft"]
                },
                {
                    "subsystem_id": "SUB-COMP-LUBE",
                    "name": "Lube Oil Subsystem",
                    "components": ["Main Oil Pump", "Oil Cooler", "Oil Filter", "Reservoir", "Pressure Regulator"]
                },
                {
                    "subsystem_id": "SUB-COMP-SEAL",
                    "name": "Dry Gas Seal Subsystem",
                    "components": ["Primary Seal", "Secondary Seal", "Separation Seal", "Gas Seal Panel"]
                }
            ],
            "direct_components": ["Casing", "Tilt-Pad Thrust Bearing", "Journal Bearings", "Coupling"],
            "monitored_sensors": [
                {"sensor_type": "Radial Proximity Probe", "measurement_property": "Shaft Radial Displacement", "typical_unit": "μm pk-pk"},
                {"sensor_type": "Axial Position Probe", "measurement_property": "Thrust Shaft Position", "typical_unit": "mm"},
                {"sensor_type": "RTD Temperature Sensor", "measurement_property": "Journal Bearing Temp", "typical_unit": "°C"},
                {"sensor_type": "Differential Pressure Transmitter", "measurement_property": "Filter Differential Pressure", "typical_unit": "kPa"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-COMP-SURGE",
                    "name": "Compressor Surge / Aerodynamic Instability",
                    "mechanism": "Flow reversal caused by operating below minimum stable flow limit",
                    "iso_14224_code": "OEO",
                    "affected_components": ["Impellers", "Inlet Guide Vanes", "Thrust Bearing"],
                    "typical_maintenance": "Calibrate anti-surge valve, verify surge margin, inspect thrust bearings"
                },
                {
                    "failure_code": "FM-COMP-SEAL-DEGRADATION",
                    "name": "Dry Gas Seal Contamination",
                    "mechanism": "Liquid or particulate ingress into seal faces causing elevated secondary vent pressure",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Primary Seal", "Secondary Seal"],
                    "typical_maintenance": "Flush dry gas seal panel, overhaul seal assembly"
                }
            ],
            "operating_modes": ["Base Load", "Part Load / Turndown", "Recirculation Anti-Surge"],
            "source_documents": ["PLAT-DOC-EQP-001", "PLAT-DOC-EQP-006"],
            "authority": "A",
            "status": "Approved"
        },

        # 3. ROTARY SCREW COMPRESSOR
        {
            "equipment_id": "EQP-COMP-SCREW",
            "name": "Oil-Injected Rotary Screw Air Compressor",
            "equipment_class": "Compressor",
            "category": "Rotating Equipment",
            "standard_ref": "ISO 5390 / ISO TR 12942",
            "subsystems": [
                {
                    "subsystem_id": "SUB-SCREW-AIREND",
                    "name": "Rotary Screw Airend",
                    "components": ["Male Rotor", "Female Rotor", "Compression Housing", "Timing Gears"]
                },
                {
                    "subsystem_id": "SUB-SCREW-SEPARATION",
                    "name": "Oil Separation & Cooling",
                    "components": ["Oil Separator Element", "Oil Cooler", "Thermostatic Valve", "Minimum Pressure Valve"]
                }
            ],
            "direct_components": ["Air Intake Filter", "Unloader Valve", "Drive Belt / Coupling"],
            "monitored_sensors": [
                {"sensor_type": "Pressure Sensor", "measurement_property": "Discharge Air Pressure", "typical_unit": "bar"},
                {"sensor_type": "Temperature Sensor", "measurement_property": "Airend Discharge Temperature", "typical_unit": "°C"},
                {"sensor_type": "Hour Meter", "measurement_property": "Run Hours", "typical_unit": "hours"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-SCREW-OVERTEMP",
                    "name": "High Airend Discharge Temperature",
                    "mechanism": "Fouled oil cooler or degraded coolant lubricant causing thermal trip",
                    "iso_14224_code": "OHS",
                    "affected_components": ["Oil Cooler", "Thermostatic Valve"],
                    "typical_maintenance": "Clean oil cooler fins, replace lubricant filter, flush oil circuit"
                }
            ],
            "operating_modes": ["Load / Unload", "Variable Speed Drive (VSD)", "Auto-Stop"],
            "source_documents": ["PLAT-DOC-EQP-001"],
            "authority": "A",
            "status": "Approved"
        },

        # 4. ELECTRIC MOTOR
        {
            "equipment_id": "EQP-MOTOR-INDUCTION",
            "name": "Three-Phase AC Induction Motor",
            "equipment_class": "Electric Motor",
            "category": "Electrical / Driver",
            "standard_ref": "IEC 60034-1 / IEC 60034-7 / OPC UA Powertrain",
            "subsystems": [
                {
                    "subsystem_id": "SUB-MOTOR-STATOR",
                    "name": "Stator Assembly",
                    "components": ["Stator Core", "Copper Windings", "Insulation Varnish", "Terminal Box"]
                },
                {
                    "subsystem_id": "SUB-MOTOR-ROTOR",
                    "name": "Rotor Assembly",
                    "components": ["Squirrel Cage Rotor", "Rotor Bars", "Motor Shaft", "Cooling Fan"]
                }
            ],
            "direct_components": ["Drive-End Bearing", "Non-Drive-End Bearing", "Frame Housing", "End Shields"],
            "monitored_sensors": [
                {"sensor_type": "Current Transformer", "measurement_property": "Phase Current RMS", "typical_unit": "A"},
                {"sensor_type": "Voltage Sensor", "measurement_property": "Line-to-Line Voltage", "typical_unit": "V"},
                {"sensor_type": "RTD Winding Sensor", "measurement_property": "Stator Winding Temp", "typical_unit": "°C"},
                {"sensor_type": "Vibration Sensor", "measurement_property": "DE Bearing Vibration", "typical_unit": "mm/s"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-MOTOR-WINDING-INSULATION",
                    "name": "Stator Winding Insulation Breakdown",
                    "mechanism": "Thermal aging, moisture, or over-voltage spikes degrading winding dielectric strength",
                    "iso_14224_code": "STP",
                    "affected_components": ["Copper Windings", "Insulation Varnish"],
                    "typical_maintenance": "Perform Megger insulation test, rewind stator"
                },
                {
                    "failure_code": "FM-MOTOR-BEARING-FLUTING",
                    "name": "VFD Shaft Current Electrical Fluting",
                    "mechanism": "Induced shaft voltage discharging across bearing oil film causing micro-pitting",
                    "iso_14224_code": "SER",
                    "affected_components": ["Drive-End Bearing", "Non-Drive-End Bearing"],
                    "typical_maintenance": "Install insulated bearing / shaft grounding ring, replace bearings"
                }
            ],
            "operating_modes": ["Direct-On-Line (DOL)", "VFD Speed Regulated", "Soft Starter"],
            "source_documents": ["PLAT-DOC-EQP-002", "PLAT-DOC-EQP-007"],
            "authority": "A",
            "status": "Approved"
        },

        # 5. SHELL & TUBE HEAT EXCHANGER
        {
            "equipment_id": "EQP-HEX-SHELLTUBE",
            "name": "Fixed Tubesheet Shell-and-Tube Heat Exchanger",
            "equipment_class": "Heat Exchanger",
            "category": "Static / Thermal Equipment",
            "standard_ref": "ISO 16812:2019 / TEMA Standard",
            "subsystems": [
                {
                    "subsystem_id": "SUB-HEX-BUNDLE",
                    "name": "Tube Bundle Assembly",
                    "components": ["Tubes", "Tubesheet", "Segmental Baffles", "Tie Rods", "Spacers"]
                },
                {
                    "subsystem_id": "SUB-HEX-SHELL",
                    "name": "Shell Side Vessel",
                    "components": ["Shell Cylinder", "Shell Nozzles", "Impingement Plate", "Expansion Joint"]
                }
            ],
            "direct_components": ["Channel Cover", "Pass Partition Plate", "Gaskets", "Channel Nozzles"],
            "monitored_sensors": [
                {"sensor_type": "Temperature Sensor", "measurement_property": "Hot Side Inlet Temp", "typical_unit": "°C"},
                {"sensor_type": "Temperature Sensor", "measurement_property": "Cold Side Outlet Temp", "typical_unit": "°C"},
                {"sensor_type": "Differential Pressure Transmitter", "measurement_property": "Tube Side Pressure Drop", "typical_unit": "kPa"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-HEX-FOULING",
                    "name": "Tube Side Scaling and Fouling",
                    "mechanism": "Deposition of mineral scale or biological sludge reducing overall heat transfer coefficient",
                    "iso_14224_code": "OEO",
                    "affected_components": ["Tubes"],
                    "typical_maintenance": "Chemical circulation wash, hydro-jetting tube interior"
                },
                {
                    "failure_code": "FM-HEX-TUBE-LEAK",
                    "name": "Flow-Induced Tube Vibration and Erosion",
                    "mechanism": "Shell-side fluid crossflow causing tube-to-baffle fretting wear and puncture",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Tubes", "Tubesheet"],
                    "typical_maintenance": "Eddy current inspection, plug damaged tubes"
                }
            ],
            "operating_modes": ["Counter-Current Flow", "Co-Current Flow"],
            "source_documents": ["PLAT-DOC-EQP-003"],
            "authority": "A",
            "status": "Approved"
        },

        # 6. CONTROL GLOBE VALVE
        {
            "equipment_id": "EQP-VALVE-GLOBE",
            "name": "Pneumatic Actuated Globe Control Valve",
            "equipment_class": "Valve",
            "category": "Piping / Flow Control",
            "standard_ref": "ISO 23.060 / ISA-75 Series",
            "subsystems": [
                {
                    "subsystem_id": "SUB-VALVE-TRIM",
                    "name": "Valve Trim Assembly",
                    "components": ["Valve Plug", "Seat Ring", "Valve Stem", "Cage Guide", "Packing Gland"]
                },
                {
                    "subsystem_id": "SUB-VALVE-ACTUATOR",
                    "name": "Pneumatic Diaphragm Actuator",
                    "components": ["Diaphragm Casing", "Actuator Spring", "Stem Connector", "Digital Positioner"]
                }
            ],
            "direct_components": ["Valve Body", "Bonnet", "Air Filter Regulator", "Limit Switches"],
            "monitored_sensors": [
                {"sensor_type": "Position Transmitter", "measurement_property": "Valve Position Percentage", "typical_unit": "%"},
                {"sensor_type": "Pressure Sensor", "measurement_property": "Actuator Air Pressure", "typical_unit": "bar"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-VALVE-PACKING-LEAK",
                    "name": "Stem Packing Degradation",
                    "mechanism": "Friction wear of PTFE/Graphite packing rings causing process medium leakage",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Packing Gland", "Valve Stem"],
                    "typical_maintenance": "Tighten gland nuts, replace packing set"
                }
            ],
            "operating_modes": ["Throttling Flow Control", "Fail-Closed (FC)", "Fail-Open (FO)"],
            "source_documents": ["PLAT-DOC-EQP-005"],
            "authority": "A",
            "status": "Approved"
        },

        # 7. STEEL GATE VALVE
        {
            "equipment_id": "EQP-VALVE-GATE",
            "name": "Bolted Bonnet Wedge Gate Valve",
            "equipment_class": "Valve",
            "category": "Piping / Isolation",
            "standard_ref": "ISO 6002:2021 / API 600",
            "subsystems": [
                {
                    "subsystem_id": "SUB-GATE-CLOSURE",
                    "name": "Gate Closure Mechanism",
                    "components": ["Flexible Wedge Gate", "Body Seat Rings", "Rising Stem", "Yoke Nut"]
                }
            ],
            "direct_components": ["Valve Body", "Bolted Bonnet", "Handwheel", "Packing Nut"],
            "monitored_sensors": [
                {"sensor_type": "Limit Switch", "measurement_property": "Open/Closed Status", "typical_unit": "binary"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-GATE-SEAT-PASSING",
                    "name": "Internal Seat Passing / Passing Leakage",
                    "mechanism": "Solid debris erosion on seating surfaces preventing tight shut-off",
                    "iso_14224_code": "LKI",
                    "affected_components": ["Flexible Wedge Gate", "Body Seat Rings"],
                    "typical_maintenance": "Lap valve seats, replace gate"
                }
            ],
            "operating_modes": ["Fully Open", "Fully Closed"],
            "source_documents": ["PLAT-DOC-EQP-005"],
            "authority": "A",
            "status": "Approved"
        },

        # 8. BELT CONVEYOR
        {
            "equipment_id": "EQP-CONV-BELT",
            "name": "Heavy Duty Industrial Belt Conveyor",
            "equipment_class": "Conveyor",
            "category": "Material Handling Equipment",
            "standard_ref": "ISO 5284 / ISO 5048",
            "subsystems": [
                {
                    "subsystem_id": "SUB-CONV-DRIVE",
                    "name": "Drive Pulley Subsystem",
                    "components": ["Drive Pulley", "Snub Pulley", "Gear Reducer", "Drive Motor", "Backstop"]
                },
                {
                    "subsystem_id": "SUB-CONV-CARRYING",
                    "name": "Carrying & Return Support",
                    "components": ["Conveyor Belt", "Troughing Idlers", "Return Idlers", "Impact Idlers"]
                }
            ],
            "direct_components": ["Gravity Take-Up Unit", "Chute Skirting", "Pull-Cord Switch"],
            "monitored_sensors": [
                {"sensor_type": "Speed Encoder", "measurement_property": "Belt Speed", "typical_unit": "m/s"},
                {"sensor_type": "Misalignment Switch", "measurement_property": "Belt Tracking Angle", "typical_unit": "degrees"},
                {"sensor_type": "Zero Speed Switch", "measurement_property": "Motion Status", "typical_unit": "binary"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-CONV-BELT-MISALIGNMENT",
                    "name": "Belt Mistracking and Edge Damage",
                    "mechanism": "Uneven material loading or seized idlers pushing belt off center",
                    "iso_14224_code": "AIR",
                    "affected_components": ["Conveyor Belt", "Troughing Idlers"],
                    "typical_maintenance": "Re-align idler frames, adjust chute loading"
                }
            ],
            "operating_modes": ["Continuous Material Transfer", "Intermittent Batch Load"],
            "source_documents": ["PLAT-DOC-EQP-005"],
            "authority": "A",
            "status": "Approved"
        },

        # 9. STORAGE TANK
        {
            "equipment_id": "EQP-TANK-STORAGE",
            "name": "Above-Ground Vertical Storage Tank",
            "equipment_class": "Tank",
            "category": "Static / Storage Equipment",
            "standard_ref": "ISO 23.020 / API 650",
            "subsystems": [
                {
                    "subsystem_id": "SUB-TANK-CONTAINMENT",
                    "name": "Primary Containment Vessel",
                    "components": ["Bottom Plate", "Shell Rings", "Fixed Cone Roof", "Roof Structure"]
                }
            ],
            "direct_components": ["Manway Door", "Flame Arrester", "Breather Valve", "Sample Port"],
            "monitored_sensors": [
                {"sensor_type": "Radar Level Transmitter", "measurement_property": "Liquid Level Height", "typical_unit": "m"},
                {"sensor_type": "Temperature Sensor", "measurement_property": "Bulk Liquid Temp", "typical_unit": "°C"},
                {"sensor_type": "High-Level Switch", "measurement_property": "Overfill Alarm", "typical_unit": "binary"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-TANK-CORROSION",
                    "name": "Bottom Plate Soil-Side Corrosion",
                    "mechanism": "Pitting corrosion on bottom steel plates due to moisture ingress",
                    "iso_14224_code": "ELU",
                    "affected_components": ["Bottom Plate"],
                    "typical_maintenance": "Ultrasonic thickness measurement, patch welding, cathodic protection check"
                }
            ],
            "operating_modes": ["Filling", "Discharging", "Static Hold"],
            "source_documents": ["PLAT-DOC-EQP-005"],
            "authority": "A",
            "status": "Approved"
        },

        # 10. WASTEWATER PACKAGE TREATMENT UNIT
        {
            "equipment_id": "EQP-WWTP-PACKAGE",
            "name": "Extended Aeration Package Wastewater Treatment Plant",
            "equipment_class": "Package Plant",
            "category": "Domain Equipment (Wastewater)",
            "standard_ref": "U.S. EPA Wastewater Package Plants Guide / EPA Process Design Manual",
            "subsystems": [
                {
                    "subsystem_id": "SUB-WWTP-AERATION",
                    "name": "Biological Aeration Basin",
                    "components": ["Coarse Bar Screen", "Air Blower", "Fine Bubble Diffusers", "Air Distribution Piping"]
                },
                {
                    "subsystem_id": "SUB-WWTP-CLARIFIER",
                    "name": "Secondary Clarification & Sludge Return",
                    "components": ["Clarifier Hopper", "Sludge Scraper", "Effluent Weir", "Airlift Return Pump"]
                }
            ],
            "direct_components": ["Equalization Basin", "Disinfection Contact Chamber", "Trash Trap"],
            "monitored_sensors": [
                {"sensor_type": "Dissolved Oxygen (DO) Probe", "measurement_property": "Dissolved Oxygen Level", "typical_unit": "mg/L"},
                {"sensor_type": "pH Sensor", "measurement_property": "Effluent pH", "typical_unit": "pH"},
                {"sensor_type": "Turbidity Meter", "measurement_property": "Effluent Turbidity", "typical_unit": "NTU"}
            ],
            "failure_modes": [
                {
                    "failure_code": "FM-WWTP-BLOWER-TRIP",
                    "name": "Aeration Blower Mechanical Trip",
                    "mechanism": "Over-heating or motor failure causing loss of dissolved oxygen and biological die-off",
                    "iso_14224_code": "STP",
                    "affected_components": ["Air Blower", "Fine Bubble Diffusers"],
                    "typical_maintenance": "Restart standby blower, clean air intake filters, inspect diffusers"
                },
                {
                    "failure_code": "FM-WWTP-WEIR-FOULING",
                    "name": "Effluent Weir Algae Accumulation",
                    "mechanism": "Algal growth blocking V-notch weir causing uneven basin overflow",
                    "iso_14224_code": "OEO",
                    "affected_components": ["Effluent Weir"],
                    "typical_maintenance": "Manual brushing of weir notches, chlorine rinse"
                }
            ],
            "operating_modes": ["Continuous Biological Treatment", "Peak Flow Over-Aeration"],
            "source_documents": ["PLAT-DOC-EQP-009", "PLAT-DOC-EQP-010"],
            "authority": "A",
            "status": "Approved"
        }
    ]


def build_canonical_equipment_yaml():
    logger.info("=== Compiling Sprint 4 Equipment & Asset Canonical Registry ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    raw_defs = get_canonical_equipment_definitions()
    validated_records = []

    for item in raw_defs:
        # Validate through Pydantic schema contract
        record = EquipmentRecord(**item)
        validated_records.append(record.model_dump())

    out_file = os.path.join(OUTPUT_DIR, "canonical_equipment.yaml")
    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump({"canonical_equipment": validated_records}, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Successfully compiled {len(validated_records)} canonical equipment records to {out_file}")


if __name__ == "__main__":
    build_canonical_equipment_yaml()
