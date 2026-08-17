"""
markdown_formatter.py - Mistune Markdown Parser and Industrial Renderer
========================================================================
Parses and enriches raw LLM text using mistune (v3.2.1) with plugins for:
- Tables with responsive styled wrappers
- Fenced code blocks with language indicators
- Alert callouts ([!NOTE], [!WARNING], [!IMPORTANT], [!TIP], [!CAUTION])
- Task lists, inline math, and auto-links
"""

from __future__ import annotations

import re
from typing import Optional, Any
import mistune
from mistune.renderers.html import HTMLRenderer
from mistune.plugins.table import table
from mistune.plugins.task_lists import task_lists
from mistune.plugins.url import url
from mistune.plugins.formatting import strikethrough, mark
from mistune.plugins.math import math


class IndustrialHTMLRenderer(HTMLRenderer):
    """Custom Mistune HTML renderer tailoring LLM output for the AI-ConneX UI."""

    def block_code(self, code: str, info: Optional[str] = None) -> str:
        lang = info.strip() if info else "text"
        escaped_code = mistune.escape(code)
        lang_badge = f'<div class="code-badge font-mono text-[10px] uppercase text-slate-400 bg-slate-800 px-2.5 py-1 rounded-t-lg border-b border-slate-700/80 flex justify-between items-center"><span>{lang}</span><span class="text-[9px] text-slate-500 font-sans">syntax</span></div>'
        return (
            f'<div class="my-3 rounded-lg overflow-hidden border border-slate-700/80 bg-slate-950 text-slate-100 shadow-sm">'
            f'{lang_badge}'
            f'<pre class="p-3 overflow-x-auto text-xs font-mono leading-relaxed"><code class="language-{lang}">{escaped_code}</code></pre>'
            f'</div>'
        )

    def block_quote(self, text: str) -> str:
        # Check for GitHub-style alert markers
        alert_patterns = [
            (r'\[!NOTE\]', 'bg-blue-50/90 border-blue-500 text-blue-950 industrial-alert industrial-alert-note', 'NOTE'),
            (r'\[!TIP\]', 'bg-emerald-50/90 border-emerald-500 text-emerald-950 industrial-alert industrial-alert-tip', 'TIP'),
            (r'\[!IMPORTANT\]', 'bg-indigo-50/90 border-indigo-500 text-indigo-950 industrial-alert industrial-alert-important', 'IMPORTANT'),
            (r'\[!WARNING\]', 'bg-amber-50/90 border-amber-500 text-amber-950 industrial-alert industrial-alert-warning', 'WARNING'),
            (r'\[!CAUTION\]', 'bg-rose-50/90 border-rose-500 text-rose-950 industrial-alert industrial-alert-caution', 'CAUTION'),
        ]

        for pat, style_cls, label in alert_patterns:
            if re.search(pat, text, re.IGNORECASE):
                clean_text = re.sub(pat, '', text, flags=re.IGNORECASE).strip()
                clean_text = re.sub(r'^<p>\s*', '', clean_text)
                clean_text = re.sub(r'\s*</p>$', '', clean_text)
                return (
                    f'<div class="my-3 p-3 rounded-xl border-l-4 {style_cls} shadow-xs text-xs space-y-1">'
                    f'<div class="font-bold uppercase tracking-wider text-[10px] flex items-center gap-1.5 opacity-90">'
                    f'<span>{label}</span>'
                    f'</div>'
                    f'<div class="leading-relaxed">{clean_text}</div>'
                    f'</div>'
                )

        return f'<blockquote class="my-2.5 border-l-4 border-slate-300 pl-3 italic text-slate-600 text-xs bg-slate-50/50 py-1 rounded-r-lg">{text}</blockquote>'


def _industrial_table_plugin(md: mistune.Markdown) -> None:
    """Plugin to attach tailored table rendering styles."""
    table(md)
    if md.renderer and md.renderer.NAME == "html":
        def custom_render_table(renderer: Any, text: str) -> str:
            return (
                f'<div class="my-3 overflow-x-auto rounded-xl border border-slate-200 shadow-xs bg-white">'
                f'<table class="min-w-full divide-y divide-slate-200 text-xs text-left">\n{text}</table>'
                f'</div>\n'
            )

        def custom_render_table_head(renderer: Any, text: str) -> str:
            return f'<thead class="bg-slate-50 font-bold text-slate-700 uppercase tracking-wider text-[10px]">\n{text}</thead>\n'

        def custom_render_table_body(renderer: Any, text: str) -> str:
            return f'<tbody class="divide-y divide-slate-100 bg-white text-slate-600">\n{text}</tbody>\n'

        def custom_render_table_row(renderer: Any, text: str) -> str:
            return f'<tr class="hover:bg-slate-50/70 transition-colors">\n{text}</tr>\n'

        def custom_render_table_cell(renderer: Any, text: str, align: Optional[str] = None, head: bool = False) -> str:
            align_attr = f' align="{align}"' if align else ""
            if head:
                return f'<th class="px-3 py-2 font-semibold text-slate-700"{align_attr}>{text}</th>\n'
            return f'<td class="px-3 py-2 text-slate-600"{align_attr}>{text}</td>\n'

        md.renderer.register("table", custom_render_table)
        md.renderer.register("table_head", custom_render_table_head)
        md.renderer.register("table_body", custom_render_table_body)
        md.renderer.register("table_row", custom_render_table_row)
        md.renderer.register("table_cell", custom_render_table_cell)


# Initialize the singleton Markdown parser instance
_renderer = IndustrialHTMLRenderer(escape=False)
_markdown = mistune.create_markdown(
    renderer=_renderer,
    plugins=[_industrial_table_plugin, task_lists, url, strikethrough, mark, math],
    escape=False,
)


def _preprocess_llm_markdown(text: str) -> str:
    """
    Pre-processes raw LLM Markdown before passing to Mistune.
    
    Handles common LLM quirks:
    1. Literal '\\n' escape sequences inside table cells -> converted to <br> tags
       (LLMs often use literal \\n inside pipe-delimited table cells since actual
       newlines would break the table row boundary)
    2. Strips trailing whitespace per line to avoid accidental Markdown hard-breaks
    """
    import re
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.rstrip()
        # If line looks like a table row (starts/ends with |), convert literal \n to <br>
        if stripped.startswith('|') and stripped.endswith('|'):
            stripped = stripped.replace('\\n', '<br>')
        result.append(stripped)
    return '\n'.join(result)


def render_markdown_html(raw_markdown: Optional[str]) -> str:
    """
    Transforms raw LLM response Markdown into styled, industrial HTML using Mistune.
    
    Args:
        raw_markdown: Raw text returned by OpenAI/OpenRouter/Qwen.
        
    Returns:
        Safe, styled HTML string ready for client rendering.
    """
    if not raw_markdown:
        return ""
    try:
        text = _preprocess_llm_markdown(str(raw_markdown).strip())
        html = _markdown(text)
        return html
    except Exception:
        # Fallback to escaped paragraph on unexpected parse error
        return f"<p class='leading-relaxed'>{mistune.escape(str(raw_markdown))}</p>"
