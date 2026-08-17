#!/usr/bin/env python3
"""
scripts/patch_html_reports.py
Applies the AIConnex Light Theme Master CSS to all generated EDA report files.
"""

import os
import glob
import re

master_light_css = """<style id="aiconnex-light-theme-master">
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap');

  :root {
    --bs-body-font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    --bs-body-bg: #F4F5F7 !important;
    --bs-body-color: #0F172A !important;
    --bs-border-color: #E2E8F0 !important;
    --bs-primary: #FF6B35 !important;
    --bs-primary-rgb: 255, 107, 53 !important;
    --bs-link-color: #FF6B35 !important;
    --bs-link-hover-color: #E85520 !important;
  }

  body, html {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: #F4F5F7 !important;
    color: #0F172A !important;
    font-size: 13px !important;
    line-height: 1.5 !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  .container, .container-fluid {
    background-color: transparent !important;
    max-width: 100% !important;
    padding: 16px 20px !important;
  }

  /* TOP NAVBAR */
  nav.navbar, .navbar {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E2E8F0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
    padding: 10px 20px !important;
  }

  .navbar-brand, .navbar-brand a {
    color: #0F172A !important;
    font-weight: 800 !important;
    font-size: 1.1rem !important;
    letter-spacing: -0.01em !important;
  }

  /* ALL SECTION ITEMS & CARDS (Pure White with 16px Radius) */
  .card, .section-items > .row, .tab-content, .variable, .overview, .correlations, .missing, .sample, .variable-card {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 16px !important;
    color: #0F172A !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px 0 rgba(0, 0, 0, 0.02) !important;
    margin-bottom: 20px !important;
    padding: 20px 24px !important;
    transition: all 0.2s ease !important;
  }

  /* COLLAPSE & EXPANDED INNER SECTIONS */
  .collapse, .collapsing, div[id^="bottom-"] {
    background-color: #FAFAFA !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 14px !important;
    padding: 16px !important;
    margin-top: 14px !important;
  }

  /* HEADINGS & VARIABLE TITLES */
  h1, .h1, .section-name, .page-header h1 {
    font-size: 1.35rem !important;
    font-weight: 800 !important;
    color: #0F172A !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.75rem !important;
  }

  h2, .h2, p.h4.item-header, .item-header {
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    letter-spacing: -0.01em !important;
    margin-top: 0.5rem !important;
    margin-bottom: 0.75rem !important;
  }

  h3, .h3, .variable-header, .variable-header a, .variable a {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    text-decoration: none !important;
  }

  /* NAVIGATION TABS & PILLS (Top & Nested More-Details Tabs) */
  nav.nav-pills, .nav-tabs, .nav-pills, ul.nav, .tab-nav {
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    display: flex !important;
    flex-wrap: wrap !important;
    margin-bottom: 14px !important;
  }

  .nav-link, .nav-pills .nav-link, .nav-tabs .nav-link, .tab-nav .nav-link {
    color: #64748B !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    padding: 6px 14px !important;
    border: none !important;
    background-color: transparent !important;
    transition: all 0.15s ease !important;
    cursor: pointer !important;
  }

  .nav-link:hover, .tab-nav .nav-link:hover {
    color: #0F172A !important;
    background-color: #E2E8F0 !important;
  }

  /* ACTIVE TAB PILL (Coral Orange Accent #FF6B35) */
  .nav-link.active, .nav-pills .nav-link.active, .nav-tabs .nav-link.active, .tab-nav .nav-link.active {
    background-color: #FF6B35 !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 6px rgba(255, 107, 53, 0.28) !important;
    border-color: #FF6B35 !important;
  }

  /* 'MORE DETAILS' & ACTION BUTTONS */
  button.btn, .btn, .btn-light, .btn-primary, .btn-secondary, button[data-bs-toggle="collapse"], .col-sm-12.text-end > button {
    background-color: #FFFFFF !important;
    color: #334155 !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 10px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    padding: 6px 14px !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
  }

  button.btn:hover, .btn:hover, .btn-light:hover, button[data-bs-toggle="collapse"]:hover, .col-sm-12.text-end > button:hover {
    background-color: #FFF7ED !important;
    color: #EA580C !important;
    border-color: #FFD8A8 !important;
    box-shadow: 0 2px 5px rgba(255, 107, 53, 0.15) !important;
  }

  /* TABLES & ZEBRA STRIPING */
  table, .table {
    color: #0F172A !important;
    font-size: 12px !important;
    border-collapse: separate !important;
    border-spacing: 0 !important;
    width: 100% !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    margin-bottom: 12px !important;
    background-color: #FFFFFF !important;
  }

  table th, .table th {
    background-color: #F8FAFC !important;
    color: #475569 !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    border-bottom: 1px solid #E2E8F0 !important;
    border-top: none !important;
    padding: 9px 14px !important;
  }

  table td, .table td {
    background-color: #FFFFFF !important;
    border-top: 1px solid #F1F5F9 !important;
    border-bottom: none !important;
    color: #0F172A !important;
    padding: 8px 14px !important;
    font-size: 12px !important;
  }

  table.table-striped > tbody > tr:nth-of-type(odd) > * {
    background-color: #FAFAFA !important;
    color: #0F172A !important;
  }

  .table-hover tbody tr:hover td {
    background-color: #FFF7ED !important;
  }

  /* PROGRESS BARS & FREQUENCY BARS (Coral Orange #FF6B35) */
  .progress {
    background-color: #F1F5F9 !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 9999px !important;
    height: 18px !important;
    overflow: hidden !important;
  }

  .progress-bar, .bar, .progress > div, [role="progressbar"], .freq .bar {
    background: linear-gradient(135deg, #FF8F5A 0%, #FF6B35 100%) !important;
    color: #FFFFFF !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    line-height: 18px !important;
    border-radius: 9999px !important;
    box-shadow: 0 1px 3px rgba(255, 107, 53, 0.25) !important;
  }

  /* BADGES */
  .badge {
    font-size: 10px !important;
    font-weight: 700 !important;
    border-radius: 6px !important;
    padding: 3px 8px !important;
    letter-spacing: 0.02em !important;
  }

  /* Alerts / Warning Badges */
  .badge.text-bg-warning, .badge-warning, .bg-warning {
    background-color: #FFF7ED !important;
    color: #C2410C !important;
    border: 1px solid #FFEDD5 !important;
  }

  /* Correlation / Secondary Badges */
  .badge.text-bg-secondary, .badge-secondary, .bg-secondary {
    background-color: #FFF7ED !important;
    color: #C2410C !important;
    border: 1px solid #FFEDD5 !important;
  }

  /* Imbalance / Primary Badges */
  .badge.text-bg-primary, .badge-primary, .bg-primary {
    background-color: #F5F3FF !important;
    color: #6D28D9 !important;
    border: 1px solid #EDE9FE !important;
  }

  /* Missing / Info Badges */
  .badge.text-bg-info, .badge-info, .bg-info {
    background-color: #EFF6FF !important;
    color: #1D4ED8 !important;
    border: 1px solid #DBEAFE !important;
  }

  /* Success Badges */
  .badge.text-bg-success, .badge-success, .bg-success {
    background-color: #ECFDF5 !important;
    color: #047857 !important;
    border: 1px solid #D1FAE5 !important;
  }

  /* ALL SVG HISTOGRAMS & PLOT RECTANGLES */
  svg rect[fill="#1f77b4"], svg rect[fill="rgb(31, 119, 180)"], 
  svg rect[fill="#0d6efd"], svg rect[fill="rgb(13, 110, 253)"], 
  svg rect[fill="#2563eb"], svg rect[fill="#007bff"],
  svg rect[fill="blue"], svg path[fill="#1f77b4"], svg path[fill="#0d6efd"] {
    fill: #FF6B35 !important;
  }

  svg rect[stroke="#1f77b4"], svg rect[stroke="#0d6efd"] {
    stroke: #E85520 !important;
  }

  svg text {
    fill: #475569 !important;
    font-family: 'Inter', sans-serif !important;
  }

  /* CODE & TOOLTIPS */
  code {
    color: #0F172A !important;
    background-color: #F1F5F9 !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 4px !important;
    padding: 1px 5px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
  }

  a {
    color: #FF6B35 !important;
    text-decoration: none !important;
  }
  a:hover {
    color: #E85520 !important;
    text-decoration: underline !important;
  }

  /* Universal scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #F8FAFC; }
  ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 9999px; }
  ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
</style>"""

files = glob.glob("services/workspace_data/**/*.html", recursive=True)
for fp in files:
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    
    # If old master css exists, replace it
    if '<style id="aiconnex-light-theme-master">' in content:
        content = re.sub(
            r'<style id="aiconnex-light-theme-master">.*?</style>',
            master_light_css,
            content,
            flags=re.DOTALL
        )
    elif "</head>" in content:
        content = content.replace("</head>", master_light_css + "\n</head>")
    else:
        content = master_light_css + "\n" + content

    with open(fp, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Patched: {fp}")

print(f"Successfully processed {len(files)} HTML report files.")
