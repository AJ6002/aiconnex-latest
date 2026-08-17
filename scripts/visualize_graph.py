"""
scripts/visualize_graph.py - AIConnex LangStudio Visualizer Generator
=====================================================================
Generates interactive visualizers, Mermaid diagrams, and PNG artifacts
for the AIConnex Master Supervisor LangGraph architecture.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agentic.graph import build_graph


def export_visualization():
    output_dir = Path("docs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    app = build_graph()
    
    # 1. Export Mermaid MMD File
    mermaid_code = app.get_graph().draw_mermaid()
    mmd_path = output_dir / "architecture_graph.mmd"
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(mermaid_code)
    print(f"[LangStudio Visualizer] Saved Mermaid diagram: {mmd_path}")
    
    # 2. Export PNG if pygraphviz / grandalf or mermaid API available
    try:
        png_bytes = app.get_graph().draw_mermaid_png()
        png_path = output_dir / "architecture_graph.png"
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        print(f"[LangStudio Visualizer] Saved PNG visualization: {png_path}")
    except Exception as e:
        print(f"[LangStudio Visualizer] Note: PNG generation skipped ({e}) — Mermaid HTML provided.")

    # 3. Export Standalone Interactive HTML LangStudio Visualizer
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIConnex MLOps OS — LangStudio Architecture Visualizer</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #38bdf8;
            --border-color: #334155;
            --highlight-color: #818cf8;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        h1 {{
            color: var(--accent-color);
            margin-bottom: 5px;
            font-size: 2.2rem;
        }}
        p.subtitle {{
            color: #94a3b8;
            font-size: 1.1rem;
            margin-top: 0;
        }}
        .badge-container {{
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-bottom: 20px;
        }}
        .badge {{
            background: #334155;
            color: #e2e8f0;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .main-container {{
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 20px;
            width: 100%;
            max-width: 1400px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }}
        .diagram-card {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 500px;
            background: #0f172a;
            border: 1px solid var(--border-color);
        }}
        .mermaid {{
            width: 100%;
            display: flex;
            justify-content: center;
        }}
        .inspector-title {{
            color: var(--accent-color);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .node-item {{
            margin-bottom: 15px;
            background: #0f172a;
            padding: 12px;
            border-radius: 8px;
            border-left: 4px solid var(--accent-color);
        }}
        .node-name {{
            font-weight: bold;
            color: #f1f5f9;
            margin-bottom: 4px;
        }}
        .node-desc {{
            font-size: 0.88rem;
            color: #94a3b8;
        }}
        footer {{
            margin-top: 40px;
            color: #64748b;
            font-size: 0.9rem;
        }}
        code {{
            background: #020617;
            color: #38bdf8;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <header>
        <h1>AIConnex MLOps OS</h1>
        <p class="subtitle">LangStudio Architecture & StateGraph Visualizer</p>
        <div class="badge-container">
            <span class="badge">LangGraph v0.2+</span>
            <span class="badge">Qwen 2.5 Coder 32B</span>
            <span class="badge">MLflow Tracing SDK</span>
            <span class="badge">7 Autonomous Agents</span>
        </div>
    </header>

    <div class="main-container">
        <div class="card diagram-card">
            <pre class="mermaid">
{mermaid_code}
            </pre>
        </div>

        <div class="card">
            <h3 class="inspector-title">⚡ Graph Topology Inspector</h3>
            
            <div class="node-item" style="border-left-color: #38bdf8;">
                <div class="node-name">1. Conversation Parser Node</div>
                <div class="node-desc">Executes 6-stage NLP parser pipeline emitting CUC contract via Qwen 2.5 Coder.</div>
            </div>

            <div class="node-item" style="border-left-color: #f59e0b;">
                <div class="node-name">2. Clarification Node (HITL)</div>
                <div class="node-desc">Triggered on low confidence (&lt;0.85). Interrupts graph to query user.</div>
            </div>

            <div class="node-item" style="border-left-color: #818cf8;">
                <div class="node-name">3. Planning Engine Node</div>
                <div class="node-desc">Maps primary intent to candidate DAG execution plans (`TaskStep`).</div>
            </div>

            <div class="node-item" style="border-left-color: #10b981;">
                <div class="node-name">4. Platform Agent Node</div>
                <div class="node-desc">Phase 5c parallel harness, non-negative Ridge Stacked Ensemble, Scorer/Judge/Selector triad.</div>
            </div>

            <div class="node-item" style="border-left-color: #ec4899;">
                <div class="node-name">5. Memory Agent Node</div>
                <div class="node-desc">Thread-safe EventStore logging &amp; mem0 Qdrant vector memory lookups.</div>
            </div>

            <div class="node-item" style="border-left-color: #a855f7;">
                <div class="node-name">6. Scout Agent Node</div>
                <div class="node-desc">Plugin pipeline compiler in Docker sandbox (`aiconnex-sandbox:latest`).</div>
            </div>

            <h3 class="inspector-title" style="margin-top: 25px;">🚀 Run in LangGraph Studio</h3>
            <p style="font-size: 0.88rem; color: #94a3b8;">
                To launch full interactive GUI debugging in LangGraph Studio:
            </p>
            <p><code>pip install langgraph-cli</code></p>
            <p><code>langgraph dev</code></p>
        </div>
    </div>

    <footer>
        Generated automatically by AIConnex LangStudio Visualizer Generator &bull; Master Architecture v3.1
    </footer>

    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
    </script>
</body>
</html>
"""
    html_path = output_dir / "langstudio_visualizer.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[LangStudio Visualizer] Saved interactive HTML visualizer: {html_path}")

if __name__ == "__main__":
    export_visualization()
