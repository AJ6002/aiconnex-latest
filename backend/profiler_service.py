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
            vals = sample[col].dropna()
            if len(vals) > 1:
                q1 = float(vals.quantile(0.25))
                q3 = float(vals.quantile(0.75))
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr

                skew = float(vals.skew())
                kurt = float(vals.kurtosis())
                outlier_mask = (sample[col] < lower) | (sample[col] > upper)
                outlier_count = int(outlier_mask.sum())
                outlier_flags |= outlier_mask.fillna(False)

                stat.update({
                    "mean": round(float(vals.mean()), 4),
                    "std": round(float(vals.std()), 4),
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
        corr_matrix = sample[numeric_cols].corr().abs()
        np.fill_diagonal(corr_matrix.values, 0)
        pairs = (
            corr_matrix.unstack()
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
