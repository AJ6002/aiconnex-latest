"""
test_markdown_formatter.py - Verification for Mistune Industrial Markdown Engine
================================================================================
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent / "chatbot" / "backend"))
from markdown_formatter import render_markdown_html


def test_table_rendering():
    raw_md = (
        "| Component | Limit | Status |\n"
        "| :--- | :--- | :--- |\n"
        "| Bearing 1 | 4.5 | Normal |\n"
        "| Bearing 2 | 6.0 | Warning |\n"
    )
    html = render_markdown_html(raw_md)
    assert "<table" in html
    assert "<thead" in html
    assert "<tbody" in html
    assert "Bearing 1" in html
    assert "divide-y" in html


def test_code_block_rendering():
    raw_md = "```python\nimport pandas as pd\ndf = pd.DataFrame()\n```"
    html = render_markdown_html(raw_md)
    assert "<pre" in html
    assert "<code" in html
    assert "language-python" in html
    assert "code-badge" in html


def test_alert_callout_rendering():
    raw_md = "> [!WARNING]\n> High vibration detected on pump shaft."
    html = render_markdown_html(raw_md)
    assert "border-amber-500" in html
    assert "WARNING" in html
    assert "High vibration detected" in html


def test_tip_callout_rendering():
    raw_md = "> [!TIP]\n> Use FFT spectral analysis for early bearing diagnosis."
    html = render_markdown_html(raw_md)
    assert "border-emerald-500" in html
    assert "TIP" in html
    assert "FFT spectral analysis" in html


def test_empty_string_safety():
    assert render_markdown_html("") == ""
    assert render_markdown_html(None) == ""
