"""
aiconnex_agent/scout/strategy_peek.py
========================================
Gap 7 fix: previously, UnifiedCompiler always silently auto-picked
options[0] whenever the compiler's internal IntentClassifier produced 2+
genuinely different compilation strategies (e.g. "one unified model across
all conditions" vs "one model per condition") - a real decision was being
made for the user without asking.

This module runs the SAME CardGenerator + IntentClassifier steps the
compiler runs internally, but standalone and BEFORE committing to a full
compile - so Scout can see how many real choices exist:
  - 1 option -> nothing to ask, proceed with the compiler's own default.
  - 2+ options -> a genuine fork only a human should resolve. Scout (in
    scout_node.py) raises a real LangGraph interrupt with these exact
    option labels, then passes the user's choice back into UnifiedCompiler
    as strategy_override so it is no longer silently decided for them.

This is read-only inspection (temp-extraction + header sniffing only) -
it never writes to output_dir and never runs the 5-stage plugin pipeline.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

from services.aiconnex_zip_compiler.intent.card_generator import CardGenerator
from services.aiconnex_zip_compiler.intent.classifier import IntentClassifier
from services.aiconnex_zip_compiler.intent.models import DatasetCard, IntentOption

logger = logging.getLogger(__name__)


def _extract_inventory(path: Path, temp_dir: Path) -> List[Dict]:
    """Lightweight, read-only file listing - no plugin pipeline, just a walk."""
    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(temp_dir)
        base = temp_dir
    elif path.is_dir():
        base = path
    else:
        # Single non-archive file (csv/xlsx/etc.)
        return [{
            "filepath": str(path),
            "relative_path": path.name,
            "format_ext": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
        }]

    inventory: List[Dict] = []
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() != ".zip":
            inventory.append({
                "filepath": str(p),
                "relative_path": str(p.relative_to(base)),
                "format_ext": p.suffix.lower(),
                "size_bytes": p.stat().st_size,
            })
    return inventory


def peek_dataset_card_and_options(path: Path) -> Tuple[DatasetCard, List[IntentOption]]:
    """Returns the real DatasetCard + real IntentOptions for a raw upload path,
    without running the full compile. Caller decides whether 2+ options means
    a real question is needed."""
    temp_dir = Path(tempfile.mkdtemp(prefix="aic_scout_peek_"))
    try:
        inventory = _extract_inventory(path, temp_dir)
        base_dir = path if path.is_dir() else None
        card = CardGenerator().generate(dataset_name=path.stem, inventory=inventory, base_dir=base_dir)
        options = IntentClassifier().classify(card)
        return card, options
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
