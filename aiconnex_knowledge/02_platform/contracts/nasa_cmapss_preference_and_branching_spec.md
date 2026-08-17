# 📘 NASA C-MAPSS Turbofan Engine Dataset — Preference & Branching Specification (Final)

> **Scope**: Regression + Anomaly + Hybrid Families Only  
> **Audience**: Non-Data-Science Site/Fleet Engineers  
> **Purpose**: Agent Intent Extraction + Compiler Parsing Assistance + HITL Question Blueprint

---

## 📌 Section 1: Dataset Summary (In Simple Words)

### What is this data?
The **NASA C-MAPSS** dataset tracks a fleet of **commercial aircraft turbofan jet engines** from brand-new healthy condition through progressive wear until engine failure.

Think of it like a car odometer — but instead of miles, it counts **flight cycles** (takeoff → cruise → landing = 1 cycle). And instead of just an odometer, there are **21 sensors** measuring temperatures, pressures, speeds, and fuel flow inside the engine at every flight cycle.

**4 Sub-Datasets with Increasing Complexity:**

| Sub-Dataset | Flight Conditions | Fault Types Present | Engines | Total Records |
|---|---|---|---|---|
| `FD001` | 1 (Sea Level) | 1 (HPC Wear Only) | 100 | 20,631 |
| `FD002` | 6 (Varying Altitude/Speed) | 1 (HPC Wear Only) | 260 | 53,759 |
| `FD003` | 1 (Sea Level) | 2 (HPC + Fan Wear) | 100 | 24,720 |
| `FD004` | 6 (Varying Altitude/Speed) | 2 (HPC + Fan Wear) | 249 | 61,249 |

**21 Sensor Channels (Simplified Names):**

| Sensor Group | Channels | What They Measure (Plain English) |
|---|---|---|
| **Temperatures** | `s2`, `s3`, `s4`, `s9` | How hot is the air at each compression stage inside the engine |
| **Pressures** | `s6`, `s7`, `s11`, `s13`, `s14` | How much the air is being squeezed at each stage |
| **Speeds** | `s8`, `s9`, `s15` | How fast the fan blades and turbine shafts are spinning |
| **Fuel & Combustion** | `s12`, `s16` | How much fuel is being burned and the fuel-air mixing ratio |
| **Airflow & Bypass** | `s1`, `s5`, `s10`, `s17`, `s20`, `s21` | How air flows through and around the engine core |

---

## 🌳 Section 2: Complete Model Branching Tree (Regression + Anomaly + Hybrid)

```
                            NASA C-MAPSS TURBOFAN ENGINE DATASET
                                              │
          ┌───────────────────────────────────┼───────────────────────────────────┐
          ▼                                   ▼                                   ▼
    FAMILY A:                           FAMILY B:                           FAMILY C:
    REGRESSION                          ANOMALY DETECTION                   HYBRID
    (Predict Numbers)                   (Catch Abnormal Behavior)           (Combined Approach)
          │                                   │                                   │
    ├── A1. Engine Life Countdown       ├── B1. Single Unified Monitor      ├── C1. Smart Auto-Activate
    │   ├── A1.1 Standard Countdown     │   (Catches ALL fault types)       │   (Silent until wear begins,
    │   ├── A1.2 Full Life Countdown    │                                   │    then starts countdown)
    │   ├── A1.3 Accelerated Wear       ├── B2. Per-Component Monitors      │
    │   │       Countdown               │   ├── B2.1 Compressor Wear       ├── C2. Two-Stage Assessment
    │   └── A1.4 Wear-Onset Anchored    │   ├── B2.2 Fan Blade Damage      │   (First classify health tier,
    │           Countdown               │   └── B2.3 Fuel System Drift     │    then predict life for
    │                                   │                                   │    non-healthy engines only)
    ├── A2. Future Sensor Forecasting   ├── B3. Degradation Onset Alert     │
    │   ├── A2.1 Predict sensor values  │   (Detects exact cycle where      ├── C3. Enriched Prediction
    │   │       10-30 flights ahead     │    healthy operation ends)        │   (Anomaly score fed as
    │   └── A2.2 Predict rate of        │                                   │    extra input to life
    │           performance loss         ├── B4. Root Cause Fault Classifier │    countdown model)
    │                                   │   (HPC vs Fan vs Combined)       │
    ├── A3. Health Score Regression      │                                   └── C4. Multi-Output Joint
    │   (Continuous 100% → 0%)          └── B5. Critical Replacement Alert       (1 model outputs life
    │                                       (Alert when < 30 flights left)       countdown + anomaly score
    └── A4. Maintenance Window                                                    + fault type together)
            Classification
        (Safe / Schedule Soon /
         Replace Immediately)
```

---

## 🔬 Section 3: Detailed Branch Descriptions (Non-Technical Language)

### 🟢 FAMILY A: REGRESSION — "Predict a Number"

Models that answer: *"How many more flights can this engine safely fly?"*

| Branch | What It Predicts | In Plain English |
|---|---|---|
| **A1.1 Standard Life Countdown** | Flights remaining (capped at 125) | *"This engine has about 45 more safe flights left."* Caps the maximum at 125 so the system doesn't waste effort scoring perfectly healthy engines. |
| **A1.2 Full Life Countdown** | Flights remaining (uncapped) | *"This engine has 312 flights remaining from today until projected failure."* Useful for long-term fleet planning and budgeting. |
| **A1.3 Accelerated Wear Countdown** | Flights remaining (accounts for wear speeding up near end) | *"This engine has ~40 flights left, but wear is accelerating — could fail sooner than linear prediction."* More realistic near end-of-life. |
| **A1.4 Wear-Onset Anchored Countdown** | Flights remaining from when wear actually started | *"Wear started at flight 180. Since then, 60 flights of wear have accumulated. ~25 remain."* Ignores the healthy early life entirely. |
| **A2.1 Future Sensor Forecast** | What sensor readings will look like 10-30 flights from now | *"In 20 flights, compressor outlet temperature will reach 620°C (currently 595°C)."* Gives mechanics a preview of deterioration. |
| **A2.2 Performance Loss Rate** | How fast sensors are degrading per 10 flights | *"Compressor efficiency is dropping 0.3% per 10 flights."* Identifies fast-degrading vs slow-degrading engines. |
| **A3.0 Health Score** | Continuous score from 100% (new) to 0% (failed) | *"Engine #47 is currently at 62% health."* Simple single number for fleet dashboards. |
| **A4.0 Maintenance Window** | Category: Safe / Schedule Soon / Replace Now | *"Engine #47: SCHEDULE MAINTENANCE within next 2 weeks."* Clear actionable bucket for maintenance planners. |

---

### 🔴 FAMILY B: ANOMALY — "Catch Something Wrong"

Models that answer: *"Is this engine behaving abnormally right now?"*

| Branch | What It Detects | In Plain English |
|---|---|---|
| **B1.0 Single Unified Monitor** | ANY abnormal behavior across ALL engine components, ALL flight speeds | *"Engine #23 showing abnormal readings — something is off. Recommend ground inspection."* One single alert system covering everything. No need to know which component — just "something is wrong." |
| **B2.1 Compressor Wear Monitor** | Abnormal temperatures/pressures in the High-Pressure Compressor (HPC) | *"Engine #23: Compressor section running hotter than expected. Possible blade erosion."* Isolates the problem to a specific section. |
| **B2.2 Fan Blade Damage Monitor** | Abnormal fan/turbine shaft speed ratios | *"Engine #23: Fan and turbine shaft speeds are mismatched. Possible blade damage or shaft friction."* |
| **B2.3 Fuel System Drift Monitor** | Abnormal fuel consumption patterns | *"Engine #23: Burning 8% more fuel than expected for this flight profile. Possible fuel injector clogging."* |
| **B3.0 Degradation Onset Alert** | The exact flight cycle where healthy operation transitions to wear | *"Engine #23 was healthy until flight cycle #142. Wear began at cycle #143."* Gives mechanics a precise start point for root cause investigation. |
| **B4.0 Root Cause Fault Classifier** | Which component is failing: Compressor, Fan, or Both | *"Engine #23 fault isolated to: HIGH-PRESSURE COMPRESSOR (confidence: 91%)."* Tells the mechanic exactly which module to open up. |
| **B5.0 Critical Replacement Alert** | Engine has fewer than 30 flights remaining | *"⚠️ ENGINE #23: CRITICAL — Fewer than 30 flights remaining. Schedule immediate replacement."* Binary high-priority alarm for fleet dispatch. |

---

### 🟣 FAMILY C: HYBRID — "Smart Combined Systems"

Models that combine anomaly detection and life prediction into a single intelligent workflow.

| Branch | How It Works | In Plain English |
|---|---|---|
| **C1.0 Smart Auto-Activate** | Runs a quiet anomaly monitor 24/7. When abnormality is detected → automatically activates the life countdown model. | *"Engine #23 has been running normally for 200 flights. [Silent.] At flight #201, anomaly detected. [Activating life countdown...] Estimated 38 flights remaining."* Most realistic for operations — no noise when everything is fine. |
| **C2.0 Two-Stage Assessment** | Stage 1: Classifies engine health tier (Healthy / Early Wear / Critical). Stage 2: Runs a tier-specific life countdown only for non-healthy engines. | *"Engine #23: Classified as EARLY WEAR. Running wear-specific life model... Estimated 65 flights remaining."* Different accuracy models for different health states. |
| **C3.0 Enriched Prediction** | Anomaly monitor produces a continuous "weirdness score" (0.0 to 1.0). That score is fed as an extra input into the life countdown model alongside raw sensors. | *"Engine #23: Anomaly score = 0.72. Life countdown model (with anomaly enrichment): 28 flights remaining."* The life model gets a synthetic "how weird is this engine" signal that improves accuracy. |
| **C4.0 Multi-Output Joint Model** | A single model that simultaneously outputs: (1) Life countdown, (2) Anomaly score, (3) Fault component class. | *"Engine #23: Life = 34 flights | Anomaly = 0.68 | Fault = HPC (87%)."* One model, three answers. Efficient and consistent. |

---

## 🧠 Section 4: What Else Can Be Extracted from User Intent

Beyond the explicit words the user types, the **Intent Extractor Agent** can mine these additional signals to help the Compiler and Scope Narrower make better decisions:

### 4A. Implicit Intent Signals (Extracted from User's Language)

| User Says (Example) | Implicit Signal Extracted | How It Helps the Compiler |
|---|---|---|
| *"I want to stop unexpected failures"* | `urgency: reactive`, `goal: prevention` | Routes toward **Anomaly** or **Hybrid C1** (alert-first, predict-second) |
| *"How many more flights can each engine do?"* | `goal: quantitative_prediction` | Routes toward **Regression A1** (life countdown) |
| *"Which engines need attention first?"* | `goal: fleet_ranking`, `scope: multi_engine` | Routes toward **Health Score A3** or **Maintenance Window A4** |
| *"Is something wrong with engine #23?"* | `scope: single_engine`, `goal: diagnosis` | Routes toward **Root Cause Classifier B4** or **Component Monitor B2** |
| *"We had 2 unplanned engine removals last quarter"* | `context: post_incident`, `urgency: high` | Activates **Critical Replacement Alert B5** + **Hybrid C1** |
| *"I want ONE system that handles everything"* | `architecture: unified`, `complexity: low` | Routes toward **Unified Monitor B1** or **Multi-Output Joint C4** |
| *"We need separate alerts for compressor vs fan issues"* | `architecture: per_component`, `granularity: high` | Routes toward **Per-Component Monitors B2.1/B2.2/B2.3** |

### 4B. Contextual Signals (Extracted from Dataset Structure)

| Signal Detected by Compiler | What It Means | How It Helps |
|---|---|---|
| User uploaded `FD001` only | Single operating condition, single fault mode | Simpler model, no regime normalization needed |
| User uploaded `FD001` + `FD003` together | Mixed fault modes (1-fault + 2-fault) | Agent should ask: *"Should we build separate models per fault scenario or one combined model?"* |
| User uploaded ALL of `FD001` to `FD004` | Full complexity, multi-regime multi-fault | Agent should suggest **Hybrid C4 (Multi-Output Joint)** or **Unified B1** |
| `train_FD00x.txt` has 100+ unique engine IDs | Fleet-scale analysis | Agent should ask: *"Do you want per-engine tracking or fleet-wide averages?"* |
| `RUL_FD00x.txt` file is present | Ground truth RUL labels available | Enables supervised regression (Family A). Without it, only anomaly (Family B) is possible. |

### 4C. Role-Based Signals (Who is the User?)

| If the User Seems Like... | Agent Adjusts Toward... |
|---|---|
| **Fleet Operations Manager** (*"Which engines need attention?"*) | Fleet ranking, maintenance windows, dashboard health scores |
| **Maintenance Planner** (*"When should we schedule overhauls?"*) | Life countdown, maintenance window classification |
| **Safety / Compliance Officer** (*"Are we meeting airworthiness standards?"*) | Critical alerts, anomaly thresholds, regulatory compliance reporting |
| **Engineering / R&D Analyst** (*"What's causing the HPC degradation?"*) | Root cause fault classification, sensor trajectory analysis, component isolation |

---

## 🔧 Section 5: Compiler Parsing Assistance Hints

The following structural hints help the **Compiler** parse the NASA C-MAPSS raw `.txt` files more precisely:

### 5A. File Structure Recognition Rules

| Compiler Check | Detection Logic | Action |
|---|---|---|
| File starts with `train_FD0` | Training set with full run-to-failure trajectories | Parse as space-delimited, no header row. Assign canonical column names: `[engine_id, cycle, setting_1, setting_2, setting_3, s1, s2, ..., s21]` |
| File starts with `test_FD0` | Test set with truncated trajectories (cut before failure) | Same parsing as train, but flag `is_truncated: true` |
| File starts with `RUL_FD0` | Ground truth remaining life labels for test engines | Single column, one value per engine. Map to `test_FD0xx` by engine order. |
| File is `Damage Propagation Modeling.pdf` | Reference documentation | Skip during compilation, but extract metadata (title, fault description) for `dataset_card.json` |
| Column count = 26 | Standard C-MAPSS format | Map columns 1-26 to `[engine_id, cycle, s1, s2, s3, ..., setting_1, setting_2, setting_3, s4, ..., s21]` |

### 5B. Schema Enrichment the Compiler Should Auto-Generate

| Derived Feature | Formula | Why the Compiler Should Create It |
|---|---|---|
| `max_cycle_per_engine` | `GROUP BY engine_id → MAX(cycle)` | Needed to compute RUL labels for train set: `RUL = max_cycle - current_cycle` |
| `normalized_cycle` | `cycle / max_cycle_per_engine` | Normalizes lifecycle position to `[0.0, 1.0]` regardless of engine lifespan length |
| `rul_piecewise` | `MIN(125, max_cycle - cycle)` | Standard capped RUL target used in most published research |
| `regime_cluster` | K-Means on `[setting_1, setting_2, setting_3]` | Groups flight cycles into operating regimes for normalization (critical for FD002/FD004) |
| `health_label` | `0` if RUL > 90, `1` if 30 < RUL ≤ 90, `2` if RUL ≤ 30 | Bucketed health tier label for classification models |

### 5C. Quality Checks the Compiler Should Run Automatically

| Check | What It Catches | Action |
|---|---|---|
| Constant sensor columns (zero variance) | Sensors `s1`, `s5`, `s10`, `s16`, `s18`, `s19` are near-constant in FD001 | Flag as `low_information: true` in schema. Don't remove — let the profiler decide. |
| Engine trajectory length outliers | Some engines fail at cycle 128, others at cycle 362 | Flag min/max/median lifespan in `dataset_card.json` for user awareness |
| Missing `RUL_FD0xx.txt` for a given `test_FD0xx.txt` | Cannot compute supervised RUL for test set | Surface HITL: *"Ground truth labels not found for this test set. Only anomaly models (no life countdown) are possible."* |
| FD003/FD004 contain mixed fault modes | Two fault types in same dataset | Surface HITL: *"This dataset contains engines with two different types of wear. Should we build one model for both or separate models?"* |

---

## 💬 Section 6: Non-Technical HITL Question Blueprint

All questions written for a **Fleet Operations Manager or Maintenance Lead** — zero data science jargon.

---

### Question 1: Primary Goal
> *"What would you like this system to do for your aircraft engine fleet?"*
> - **[A] Tell me how many flights each engine has left** *(Life countdown for maintenance scheduling)*
> - **[B] Alert me when any engine starts acting abnormally** *(Safety monitoring that catches any problem automatically)*
> - **[C] Stay quiet when engines are healthy, but activate a life countdown as soon as wear begins** *(Smart combined system — recommended for most operations)*

---

### Question 2: Model Scope *(Only if user uploaded FD003 or FD004)*
> *"Your dataset contains engines with two types of internal wear (compressor blades and fan blades). How should we handle this?"*
> - **[A] One single system that catches both types together** *(Simpler to manage, one dashboard)*
> - **[B] Separate dedicated monitors for each type of wear** *(More detailed, tells you exactly which part is wearing)*

---

### Question 3: Fleet vs Individual *(Only if > 50 engines detected)*
> *"Your dataset contains [N] individual engines. How would you like the results organized?"*
> - **[A] Individual engine tracking** *(Separate life countdown and health score per engine — recommended for active fleet management)*
> - **[B] Fleet-wide averages and trends** *(Overall fleet health summary — useful for executive reporting)*

---

### Question 4: Alert Sensitivity *(Only if user chose Option B or C in Question 1)*
> *"How early should the system flag a potential problem?"*
> - **[A] Early warning — flag at the first subtle sign of wear** *(More alerts, but catches problems earlier)*
> - **[B] Confirmed warning only — flag only when wear is clearly progressing** *(Fewer alerts, but higher confidence per alert)*

---

### Question 5: Maintenance Window Preference *(Only if user chose Option A in Question 1)*
> *"How should we present the maintenance timeline?"*
> - **[A] Exact flight count remaining** *(e.g., "Engine #23: 47 flights remaining")*
> - **[B] Traffic light categories** *(GREEN = Safe, YELLOW = Schedule Soon, RED = Replace Immediately)*
> - **[C] Both — exact count plus traffic light category**

---

## 🎯 Section 7: Summary

### Branch Count (Final)

| Family | Branches | Description |
|---|---|---|
| **A: Regression** | 8 | Life countdown variants, sensor forecasting, health scores, maintenance windows |
| **B: Anomaly** | 7 | Unified monitor, per-component monitors, onset detection, fault classification, critical alerts |
| **C: Hybrid** | 4 | Smart auto-activate, two-stage cascade, enriched prediction, multi-output joint |
| **TOTAL** | **19** | **All possible model branches (Regression + Anomaly + Hybrid)** |

### Key Architectural Principles

1. **Zero algorithms in this document** — Algorithm selection belongs to the downstream Dataset Profiler and DAG Orchestrator.
2. **Zero technical questions to the user** — Every HITL question is framed in operational aviation outcomes.
3. **Compiler assists with structure** — Auto-generates derived columns (`rul_piecewise`, `regime_cluster`, `health_label`), runs quality checks, and surfaces data-aware HITL questions.
4. **Intent extraction goes deeper** — Mines implicit signals (urgency, scope, role), contextual signals (which FD00x files uploaded), and adjusts routing accordingly.
