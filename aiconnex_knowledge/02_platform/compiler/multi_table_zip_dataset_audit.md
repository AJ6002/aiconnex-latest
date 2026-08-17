# Engineering Audit & Caution Guide: Multi-Plant / Multi-Table ZIP Datasets

> **System Audit & Architectural Pre-Flight Check**
> **Target Dataset:** `Solar Power Generation Data.zip` (Plant 1 & Plant 2 Power Generation + Weather Sensor CSVs)
> **Engine Scope:** `aiconnex_ml` Industrial ML Package & 9-Node Microservice Architecture (`aic/`)

---

## 1. Executive Summary

When dealing with raw multi-table ZIP archives (such as solar generation + weather sensor data across multiple units), standard tabular ML pipelines fail silently or produce corrupted models. 

This document defines the **5 Critical Failure Modes** identified during engineering audit, evaluates our current system readiness, and establishes the **Mandatory Pre-Flight Data Preparation Protocol** required before executing end-to-end model training.

---

## 2. Deep Dive: 5 Critical Failure Modes

### 🚨 1. Relational Join Mismatch & Mismatched Granularity
> [!WARNING]
> **Cardinality Mismatch:** Generation data is recorded **per-inverter** (high cardinality: ~68,000 rows), while Weather sensor data is recorded **per-plant** (lower cardinality: ~3,180 rows).

* **The Failure Mode:**
  Joining tables on `DATE_TIME` alone without restricting by `PLANT_ID` creates a **Cartesian Cross-Join**, duplicating weather measurements from Plant 1 onto Plant 2 and quadrupling the row count.
* **Pipeline Safeguard:**
  Mandatory composite relational join condition: `ON (PLANT_ID, DATE_TIME)`.

---

### ⏰ 2. Timestamp Format & Timezone Divergence
> [!CAUTION]
> **Format Mismatch:** In raw industrial archives, different files often use different date string formats.
> * `Generation_Data.csv`: Uses `15-05-2020 00:00` (`DD-MM-YYYY HH:MM`)
> * `Weather_Sensor_Data.csv`: Uses `2020-05-15 00:00:00` (`YYYY-MM-DD HH:MM:SS`)

* **The Failure Mode:**
  Joining on raw string dates yields **0 matching rows** (`0%` join yield), causing the pipeline to process an empty DataFrame or crash during feature engineering.
* **Pipeline Safeguard:**
  Strict pre-join datetime parsing with format inference (`pd.to_datetime(..., dayfirst=True)`) before merging.

---

### 📉 3. Night-Time Interval Dropping & Rolling Lag Corruption
> [!IMPORTANT]
> **Gap Risk:** Solar generation drops to $0.0\text{ kW}$ at night ($19:00 - 05:30$). Some plant historians omit zero-power night rows entirely to reduce storage size.

* **The Failure Mode:**
  Non-contiguous timestamps break time-series rolling lag calculations. If the pipeline computes a $15$-minute rolling mean across a missing 10-hour night gap, morning features will be corrupted by previous evening values.
* **Pipeline Safeguard:**
  Time-grid reindexing (`asfreq('15min')`) to impute missing night intervals with $0.0\text{ kW}$ prior to computing rolling windows and lag features.

---

### 🔀 4. Multi-Operating Regime / Micro-Climate Concept Drift
> [!WARNING]
> **Regime Mixing:** Plant 1 and Plant 2 operate under different solar panel tilts, inverter hardware conversion efficiencies, and geographical micro-climates.

* **The Failure Mode:**
  Merging data from both plants without including `PLANT_ID` as an explicit categorical entity key blurs physical boundaries, causing the ML model to miscalculate baseline efficiency.
* **Pipeline Safeguard:**
  Explicit categorical encoding for `PLANT_ID` and `SOURCE_KEY` (Inverter ID) for group-level entity tracking.

---

### 🛑 5. Data Leakage via Random K-Fold Splitting
> [!CAUTION]
> **The Cardinal Sin:** Applying standard random splitting (`train_test_split(test_size=0.2, random_state=42)`).

* **The Failure Mode:**
  Consecutive 15-minute readings from the same solar inverter are highly auto-correlated. Random splitting leaks past and future timestamps of the *same inverter* into both train and test sets, yielding an artificial **$R^2 = 0.99$ in validation**, but **complete failure in live production**.
* **Pipeline Safeguard:**
  Enforce **Group-Chronological Splitting** grouped by `SOURCE_KEY` (Inverter ID) to validate on completely unseen inverters or future time windows.

---

## 3. System Audit vs. Architecture Baseline

| Audit Criterion | `aic/` Single CSV CLI Status | Required Pre-Processor Layer |
|---|:---:|---|
| **ZIP Extraction & Discarding** | Manual | Automated ZIP unzip + file discovery |
| **Relational Join Engine** | Expects single merged CSV | Automated `pd.merge(on=['PLANT_ID', 'DATE_TIME'])` |
| **DateTime Normalization** | Single ISO format expected | Flexible multi-format `pd.to_datetime` pre-processor |
| **Time-Grid Reindexing** | Done in `aiconnex_ml.features` | Verify zero-fill for night gaps |
| **Topology Split Enforcement** | ✅ Fully Enforced (`group_chronological`) | Topology policy correctly handles `SOURCE_KEY` |
| **Asymmetric Loss HPO** | ✅ Fully Supported | Prevents over-promising grid supply capacity |

---

## 4. Pre-Flight Verification Checklist

- [ ] Extract `Solar Power Generation Data.zip` to a temporary workspace buffer.
- [ ] Inspect raw headers and datetime formats across all 4 CSVs.
- [ ] Perform pre-merge validation check for duplicate timestamps or missing dates.
- [ ] Merge Generation + Weather Sensor datasets into unified single-table files (`solar_plant1_merged.csv`, `solar_plant2_merged.csv`).
- [ ] Confirm `run_pipeline.py` receives the unified, validated dataset.
