"""
test_prompter_tui.py - Unit tests for expanded HITL TerminalPrompter TUI box & DatasetCard subdomains
"""

from pathlib import Path
from services.aiconnex_zip_compiler.intent.models import DatasetCard, IntentOption
from services.aiconnex_zip_compiler.intent.card_generator import CardGenerator
from services.aiconnex_zip_compiler.intent.classifier import IntentClassifier
from services.aiconnex_zip_compiler.intent.prompter import TerminalPrompter


def test_dataset_card_subdomains_and_molding():
    inventory = [
        {"relative_path": "PNB950657_DPR_January-2026.xlsx", "format_ext": ".xlsx", "size_bytes": 1000, "filepath": "dummy"},
        {"relative_path": "PNB950657_DPR_February-2026.xlsx", "format_ext": ".xlsx", "size_bytes": 1000, "filepath": "dummy"},
    ]
    gen = CardGenerator()
    card = gen.generate(dataset_name="Dataset-TAS.zip", inventory=inventory, base_dir=Path("Dataset-TAS"))
    card.detected_sheets = ["DPR Report", "Reco-Inflow Data"]

    assert card.dataset_name in ("Dataset-TAS.zip", "Dataset-TAS")
    assert len(card.detected_subdomains) > 0
    assert len(card.molding_capabilities) > 0


def test_terminal_prompter_batch_mode():
    card = DatasetCard(
        dataset_name="Dataset-TAS.zip",
        domain="industrial_sensor_telemetry",
        dataset_type="multi_sheet_excel_workbook",
        detected_sheets=["DPR Report", "Reco-Inflow Data"],
        detected_subdomains=["Compressor Telemetry", "Sales Reconciliation"],
        molding_capabilities=["Dual-Model Export", "Single Combined Fleet Dataset"],
        summary="SCADA readings workbook with 2 data sheets",
    )
    options = [
        IntentOption(
            option_id="separate_per_condition",
            label="Separate per operating condition / sheet group",
            description="Exports separate condition CSVs for independent model training",
            is_default=True,
            output_mode="keep_separate",
            pipeline_type="dual_multi_model",
        ),
        IntentOption(
            option_id="unified_all_conditions",
            label="Unified all conditions into one fleet dataset",
            description="Stacks all sheets into a single fleet table",
            is_default=False,
            output_mode="single_merged",
            pipeline_type="unified_fleet",
        ),
    ]

    prompter = TerminalPrompter(force_batch=True)
    chosen = prompter.prompt(card, options, question="How do you want to mold this dataset?")
    assert chosen == "separate_per_condition"
