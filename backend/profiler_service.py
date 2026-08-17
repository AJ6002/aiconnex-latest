"""
profiler_service.py
====================
Fast statistical profiler for AIConnex Data Explorer.

Computes column-level quality metrics on pandas DataFrames:
  - Descriptive statistics (mean, std, min, 25/50/75%, max)
  - Skewness and kurtosis
  - Missingness ratio per column
  - Outlier density (IQR rule)
  - Pairwise correlation rank (top-5 pairs)
  - Aggregate quality signals for recommendation cards:
      max_skewness, most_skewed_col
      outlier_pct (row-level: any column is an outlier)
      max_missing_pct, most_missing_col

Sampling: Only uses the first MAX_ROWS rows to keep latency < 200ms even
for million-row files. The sample size is returned in the payload so the
UI can display it clearly.

Exposed helpers
---------------
profile_dataframe(df) -> dict          (raw profiling stats)
profile_from_path(file_path) -> dict   (reads CSV/parquet then profiles)
"""

from __future__ import annotations

import os
import io
import traceback
from typing import Optional

import numpy as np
import pandas as pd

# Maximum rows to profile (for speed — avoids multi-second latency on large files)
MAX_ROWS = 5_000


# ── Core profiler ──────────────────────────────────────────────────────────────

def profile_dataframe(df: pd.DataFrame) -> dict:
    """
    Profile a DataFrame and return a structured quality metrics dict.

    Returns
    -------
    dict with keys:
        rows_total     : int — total rows in original DataFrame
        rows_sampled   : int — rows used for profiling (capped at MAX_ROWS)
        columns        : int — total columns
        column_stats   : list[dict] — per-column statistics
        top_correlations : list[dict] — top 5 correlated numeric pairs
        max_skewness   : float — highest absolute skewness across numeric columns
        most_skewed_col: str — column name with highest absolute skewness
        outlier_pct    : float — % of rows with at least one IQR outlier
        max_missing_pct: float — highest missingness % across all columns
        most_missing_col: str — column name with highest missingness %
    """
    rows_total = len(df)
    sample = df.head(MAX_ROWS).copy()
    rows_sampled = len(sample)

    column_stats = []
    max_skewness = 0.0
    most_skewed_col = ""
    max_missing_pct = 0.0
    most_missing_col = ""
    outlier_flags = pd.Series(False, index=sample.index)

    numeric_cols = sample.select_dtypes(include=[np.number]).columns.tolist()

    for col in sample.columns:
        missing_count = int(sample[col].isna().sum())
        missing_pct = round(missing_count / rows_sampled * 100, 2)
        dtype = str(sample[col].dtype)

        stat: dict = {
            "column": col,
            "dtype": dtype,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
        }

        if col in numeric_cols:
            vals = pd.Series(sample[col].dropna().to_numpy(copy=True))
            if len(vals) > 1:
                q1 = float(vals.quantile(0.25))
                q3 = float(vals.quantile(0.75))
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr

                try:
                    skew = float(vals.skew())
                    if np.isnan(skew): skew = 0.0
                except Exception:
                    skew = 0.0

                try:
                    kurt = float(vals.kurtosis())
                    if np.isnan(kurt): kurt = 0.0
                except Exception:
                    kurt = 0.0

                outlier_mask = (sample[col] < lower) | (sample[col] > upper)
                outlier_count = int(outlier_mask.sum())
                outlier_flags |= outlier_mask.fillna(False)

                stat.update({
                    "mean": round(float(vals.mean()), 4) if not np.isnan(vals.mean()) else 0.0,
                    "std": round(float(vals.std()), 4) if not np.isnan(vals.std()) else 0.0,
                    "min": round(float(vals.min()), 4),
                    "p25": round(q1, 4),
                    "median": round(float(vals.median()), 4),
                    "p75": round(q3, 4),
                    "max": round(float(vals.max()), 4),
                    "skewness": round(skew, 4),
                    "kurtosis": round(kurt, 4),
                    "outlier_count": outlier_count,
                    "outlier_pct": round(outlier_count / rows_sampled * 100, 2),
                    "iqr": round(iqr, 4),
                    "lower_fence": round(lower, 4),
                    "upper_fence": round(upper, 4),
                })

                # Update aggregate skewness signal
                if abs(skew) > abs(max_skewness):
                    max_skewness = skew
                    most_skewed_col = col
            else:
                stat.update({
                    "mean": None, "std": None, "min": None,
                    "p25": None, "median": None, "p75": None,
                    "max": None, "skewness": None, "kurtosis": None,
                    "outlier_count": 0, "outlier_pct": 0.0, "iqr": None,
                    "lower_fence": None, "upper_fence": None,
                })

        # Update aggregate missingness signal
        if missing_pct > max_missing_pct:
            max_missing_pct = missing_pct
            most_missing_col = col

        column_stats.append(stat)

    # Row-level outlier density (any column has an IQR outlier)
    outlier_pct = round(float(outlier_flags.sum()) / rows_sampled * 100, 2)

    # Top 5 correlated numeric column pairs
    top_correlations: list[dict] = []
    if len(numeric_cols) >= 2:
        corr_matrix = sample[numeric_cols].corr().abs().fillna(0.0)
        corr_vals = corr_matrix.to_numpy(copy=True)
        np.fill_diagonal(corr_vals, 0.0)
        corr_df = pd.DataFrame(corr_vals, index=corr_matrix.index, columns=corr_matrix.columns)
        pairs = (
            corr_df.unstack()
            .sort_values(ascending=False)
            .drop_duplicates()
            .head(5)
        )
        for (col_a, col_b), val in pairs.items():
            if col_a != col_b:
                top_correlations.append({
                    "col_a": col_a,
                    "col_b": col_b,
                    "correlation": round(float(val), 4),
                })

    # Duplicate row calculation
    duplicate_rows = int(sample.duplicated().sum())
    duplicate_pct = round(duplicate_rows / rows_sampled * 100, 2)

    max_zero_pct = 0.0
    most_zero_col = ""
    constant_cols = []
    total_infinite_count = 0

    for col in sample.columns:
        zero_count = int((sample[col] == 0).sum())
        zero_pct = round(zero_count / rows_sampled * 100, 2)
        unique_cnt = int(sample[col].nunique(dropna=True))

        if unique_cnt <= 1 and rows_sampled > 1:
            constant_cols.append(col)

        if col in numeric_cols:
            inf_cnt = int(np.isinf(sample[col].dropna()).sum())
            total_infinite_count += inf_cnt

        if zero_pct > max_zero_pct:
            max_zero_pct = zero_pct
            most_zero_col = col

    # Lux-style Automated Visual Action Recommendations
    recommendations = []
    if max_skewness > 2.0:
        recommendations.append({
            "type": "SKEWNESS_ALERT",
            "column": most_skewed_col,
            "metric": f"Skewness={round(max_skewness, 2)}",
            "action": "Log/Yeo-Johnson Transform",
            "description": f"Column '{most_skewed_col}' exhibits severe non-Gaussian right skew. Apply power transformation."
        })
    if outlier_pct > 1.5:
        recommendations.append({
            "type": "OUTLIER_ALERT",
            "column": "dataset_global",
            "metric": f"Outliers={outlier_pct}%",
            "action": "Robust Scaling",
            "description": f"{outlier_pct}% of rows contain IQR outliers. Use RobustScaler (median+IQR) to prevent weight distortion."
        })
    if max_missing_pct > 5.0:
        recommendations.append({
            "type": "MISSINGNESS_ALERT",
            "column": most_missing_col,
            "metric": f"Missing={max_missing_pct}%",
            "action": "KNN Imputation",
            "description": f"Column '{most_missing_col}' missing ratio is {max_missing_pct}%. Apply multivariate KNN/forward-fill."
        })
    if max_zero_pct > 50.0:
        recommendations.append({
            "type": "SPARSITY_ALERT",
            "column": most_zero_col,
            "metric": f"ZeroRatio={max_zero_pct}%",
            "action": "Sparse Matrix Encoding",
            "description": f"Column '{most_zero_col}' has {max_zero_pct}% zero values. Consider scipy.sparse CSR format."
        })
    if len(top_correlations) > 0 and top_correlations[0]["correlation"] > 0.85:
        top_c = top_correlations[0]
        recommendations.append({
            "type": "COLLINEARITY_ALERT",
            "column": f"{top_c['col_a']} <-> {top_c['col_b']}",
            "metric": f"r={top_c['correlation']}",
            "action": "VIF / Feature Pruning",
            "description": f"High collinearity (r={top_c['correlation']}) between {top_c['col_a']} and {top_c['col_b']}. Prune one feature."
        })

    return {
        "rows_total": rows_total,
        "rows_sampled": rows_sampled,
        "columns": len(sample.columns),
        "column_stats": column_stats,
        "top_correlations": top_correlations,
        "duplicate_pct": duplicate_pct,
        "constant_cols": constant_cols,
        "infinite_count": total_infinite_count,
        # ── Aggregate signals for recommendation cards ──
        "max_skewness": round(abs(max_skewness), 4),
        "most_skewed_col": most_skewed_col,
        "outlier_pct": outlier_pct,
        "max_missing_pct": max_missing_pct,
        "most_missing_col": most_missing_col,
        "max_zero_pct": max_zero_pct,
        "most_zero_col": most_zero_col,
        "recommendations": recommendations
    }



# ── File-path entry point ──────────────────────────────────────────────────────

def profile_from_path(file_path: str) -> dict:
    """
    Load a CSV or Parquet file from a local path and run profile_dataframe().

    Returns a profiling dict (same schema as profile_dataframe) plus:
        file_path : str — resolved absolute path
        error     : str | None — error message if loading failed
    """
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        return {
            "error": f"File not found: {abs_path}",
            "rows_total": 0,
            "rows_sampled": 0,
            "columns": 0,
            "column_stats": [],
            "top_correlations": [],
            "max_skewness": 0.0,
            "most_skewed_col": "",
            "outlier_pct": 0.0,
            "max_missing_pct": 0.0,
            "most_missing_col": "",
        }

    # Reject archive files — profiler requires pre-compiled CSV/Parquet
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in (".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"):
        return {
            "error": f"Cannot profile archive file ({ext}). Dataset must be compiled to CSV/Parquet first.",
            "rows_total": 0,
            "rows_sampled": 0,
            "columns": 0,
            "column_stats": [],
            "top_correlations": [],
            "max_skewness": 0.0,
            "most_skewed_col": "",
            "outlier_pct": 0.0,
            "max_missing_pct": 0.0,
            "most_missing_col": "",
        }

    try:
        if ext == ".parquet":
            df = pd.read_parquet(abs_path)
        elif ext == ".csv":
            df = pd.read_csv(abs_path, low_memory=False)
        else:
            # Try CSV as fallback
            df = pd.read_csv(abs_path, low_memory=False)
    except Exception as exc:
        return {
            "error": f"Failed to read file: {exc}",
            "rows_total": 0,
            "rows_sampled": 0,
            "columns": 0,
            "column_stats": [],
            "top_correlations": [],
            "max_skewness": 0.0,
            "most_skewed_col": "",
            "outlier_pct": 0.0,
            "max_missing_pct": 0.0,
            "most_missing_col": "",
        }

    result = profile_dataframe(df)
    result["file_path"] = abs_path
    result["error"] = None
    return result


# ── Exhaustive Interactive HTML Report Generator (fg-data-profiling) ──────────

import sys

def generate_exhaustive_html_report(file_path: str, output_html_path: str, title: str = "AIConnex Data Profiling Report") -> dict:
    """
    Generate an exhaustive interactive HTML EDA report using fg-data-profiling.
    Saves the output HTML to output_html_path and returns a status dict.
    """
    abs_input = os.path.abspath(file_path)
    abs_output = os.path.abspath(output_html_path)

    if not os.path.exists(abs_input):
        return {"success": False, "error": f"Input file not found: {abs_input}"}

    os.makedirs(os.path.dirname(abs_output), exist_ok=True)

    # Ensure vendor path is registered in sys.path
    vendor_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "fg-data-profiling", "src"))
    if vendor_src not in sys.path:
        sys.path.insert(0, vendor_src)

    try:
        ext = os.path.splitext(abs_input)[1].lower()
        if ext == ".parquet":
            df = pd.read_parquet(abs_input)
        else:
            df = pd.read_csv(abs_input, low_memory=False)

        # Cap at 10,000 rows for sub-5 second compilation and lightweight <2MB report size
        if len(df) > 10000:
            df = df.head(10000)

        # Fast lightweight configuration with AI-Connex Coral Orange plotting palette
        report_kwargs = {
            "title": title,
            "minimal": False,
            "explorative": False,
            "interactions": {"continuous": False},
            "correlations": {
                "pearson": {"calculate": True},
                "spearman": {"calculate": True},
                "kendall": {"calculate": False},
                "phi_k": {"calculate": False},
                "cramers": {"calculate": False},
            },
            "missing_diagrams": {
                "bar": True,
                "matrix": True,
                "heatmap": True,
            },
            "samples": {"head": 5, "tail": 5},
            "html": {
                "style": {
                    "theme": None,
                    "primary_colors": ["#FF6B35", "#E85520", "#FF8F5A"],
                }
            },
            "plot": {
                "cat_frequency": {
                    "colors": ["#FF6B35", "#FF8F5A", "#FFAA80", "#FFC4A6", "#FFE0D0"]
                }
            }
        }

        try:
            from data_profiling import ProfileReport
            profile = ProfileReport(df, **report_kwargs)
            profile.to_file(abs_output)
            _apply_aiconnex_theme_to_html(abs_output)
            return {"success": True, "output_path": abs_output, "rows_analyzed": len(df)}
        except Exception as report_err:
            from ydata_profiling import ProfileReport
            profile = ProfileReport(df, **report_kwargs)
            profile.to_file(abs_output)
            _apply_aiconnex_theme_to_html(abs_output)
            return {"success": True, "output_path": abs_output, "rows_analyzed": len(df)}

    except Exception as exc:
        traceback.print_exc()
        return {"success": False, "error": str(exc)}


def _apply_aiconnex_theme_to_html(html_path: str, theme: str = "light"):
    """Inject AIConnex dual Light & Dark theme typography, font sizes, and card styling into generated HTML."""
    if not os.path.exists(html_path):
        return

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        style_block = """
<style id="aiconnex-light-theme-master">
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap');

  :root {
    --bs-body-font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    --bs-body-bg: #F4F5F7 !important;
    --bs-body-color: #0F172A !important;
    --bs-border-color: #E2E8F0 !important;
    --bs-primary: #FF6B35 !important;
    --bs-primary-rgb: 255, 107, 53 !important;
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

  /* Cards & Section Containers */
  .card, .section-items > .row, .tab-content, .variable, .overview, .correlations, .missing, .sample {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 16px !important;
    color: #0F172A !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px 0 rgba(0, 0, 0, 0.02) !important;
    margin-bottom: 20px !important;
    padding: 18px 22px !important;
    transition: all 0.2s ease !important;
  }

  /* Headings & Titles */
  h1, .h1, .page-header h1, a.anchor-link, .variable-header a {
    font-size: 1.35rem !important;
    font-weight: 800 !important;
    color: #0F172A !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.75rem !important;
    text-decoration: none !important;
  }

  h2, .h2 {
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    letter-spacing: -0.01em !important;
    margin-top: 1rem !important;
    margin-bottom: 0.75rem !important;
  }

  h3, .h3, .variable-header {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
  }

  h4, h5, h6 {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    color: #475569 !important;
  }

  /* Navigation & Tabs (Overview, Variables, Correlations, Missing, Sample, Histogram, etc.) */
  nav.navbar, nav.nav-pills, .nav-tabs, .nav-pills, ul.nav, .tab-nav {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 14px !important;
    padding: 6px !important;
    gap: 4px !important;
    display: flex !important;
    flex-wrap: wrap !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
  }

  .nav-link, .nav-pills .nav-link, .nav-tabs .nav-link {
    color: #64748B !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    padding: 7px 16px !important;
    border: none !important;
    background-color: transparent !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
  }

  .nav-link:hover {
    color: #0F172A !important;
    background-color: #F1F5F9 !important;
  }

  .nav-link.active, .nav-pills .nav-link.active, .nav-tabs .nav-link.active, .tab-nav .nav-link.active {
    background-color: #FF6B35 !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(255, 107, 53, 0.28) !important;
  }

  /* More Details & Action Buttons */
  button.btn, .btn, .btn-primary, .btn-outline-primary, .btn-secondary, .btn-light, a.btn, button[data-bs-toggle="collapse"] {
    background-color: #FFFFFF !important;
    color: #475569 !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    padding: 6px 12px !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
  }

  button.btn:hover, .btn:hover, .btn-light:hover, a.btn:hover, button[data-bs-toggle="collapse"]:hover {
    background-color: #FFF7ED !important;
    color: #EA580C !important;
    border-color: #FFD8A8 !important;
  }

  .btn-primary, button.btn-primary {
    background-color: #FF6B35 !important;
    color: #FFFFFF !important;
    border: 1px solid #FF6B35 !important;
    box-shadow: 0 2px 6px rgba(255, 107, 53, 0.25) !important;
  }

  /* Progress Bars */
  .progress {
    background-color: #F1F5F9 !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 9999px !important;
    height: 18px !important;
    overflow: hidden !important;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.03) !important;
  }

  .progress-bar, .bar, .progress > div, [role="progressbar"] {
    background: linear-gradient(135deg, #FF8F5A 0%, #FF6B35 100%) !important;
    color: #FFFFFF !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    line-height: 18px !important;
    border-radius: 9999px !important;
    box-shadow: 0 1px 3px rgba(255, 107, 53, 0.3) !important;
  }

  /* Stat Tables */
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
    padding: 10px 14px !important;
  }

  table td, .table td {
    background-color: #FFFFFF !important;
    border-top: 1px solid #F1F5F9 !important;
    border-bottom: none !important;
    color: #0F172A !important;
    padding: 9px 14px !important;
    font-size: 12px !important;
  }

  table.table-striped > tbody > tr:nth-of-type(odd) > * {
    background-color: #FAFAFA !important;
    color: #0F172A !important;
  }

  .table-hover tbody tr:hover td {
    background-color: #FFF7ED !important;
  }

  /* Badges */
  .badge {
    font-size: 10px !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
    padding: 4px 8px !important;
    letter-spacing: 0.02em !important;
  }

  .badge-warning, .bg-warning, .badge-danger, .bg-danger, [class*="badge"][class*="correlation"], [class*="badge"][class*="alert"] {
    background-color: #FFF7ED !important;
    color: #C2410C !important;
    border: 1px solid #FFEDD5 !important;
  }

  .badge-primary, .bg-primary, [class*="badge"][class*="categorical"] {
    background-color: #F5F3FF !important;
    color: #6D28D9 !important;
    border: 1px solid #EDE9FE !important;
  }

  .badge-success, .bg-success, [class*="badge"][class*="numeric"] {
    background-color: #ECFDF5 !important;
    color: #047857 !important;
    border: 1px solid #D1FAE5 !important;
  }

  .badge-secondary, .bg-secondary {
    background-color: #F1F5F9 !important;
    color: #475569 !important;
    border: 1px solid #E2E8F0 !important;
  }

  /* SVG Graphics & Histograms */
  svg rect[fill="#1f77b4"], svg rect[fill="rgb(31, 119, 180)"], svg rect[fill="#0d6efd"], svg rect[fill="rgb(13, 110, 253)"], svg rect[fill="#2563eb"], svg path.bar {
    fill: #FF6B35 !important;
  }

  svg text {
    fill: #475569 !important;
    font-family: 'Inter', sans-serif !important;
  }
</style>
"""

        if "aiconnex-light-theme-master" in content:
            import re
            content = re.sub(r'<style id="aiconnex-light-theme-master">.*?</style>', style_block, content, flags=re.DOTALL)
        elif "</head>" in content:
            content = content.replace("</head>", f"{style_block}\n</head>")
        else:
            content = f"{style_block}\n{content}"

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Theme injection error: {e}")

