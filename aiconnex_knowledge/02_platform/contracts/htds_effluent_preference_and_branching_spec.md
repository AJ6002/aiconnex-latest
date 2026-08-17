# 📘 HTDS Industrial Effluent Dataset — Preference & Branching Specification (Final)

> **Scope**: Multi-Model Generation + Multi-DAG Candidate Parallel Execution + Evaluation Triad  
> **Alignment**: `deep_system_audit.md` Architecture Standard (LangGraph Layer 1 + ML Engine Layer 2)  
> **Audience**: Non-Data-Science ETP Plant Managers, Process Engineers, & Agentic Platform Engineers  
> **Purpose**: Intent Extraction + Multi-DAG Resolution + MCDA Evaluation Triad + HITL Question Blueprint  

---

## 📌 Section 1: Dataset Summary (In Simple Words)

### What is this data?
The **HTDS Dataset** (`HTDS-v1.csv` / `HTDS-v1.xlsx`) tracks daily **industrial pharmaceutical wastewater discharges** from Laurus Labs Ltd (Unit-3) delivered to a central Effluent Treatment Plant (ETP) across 883 batch deliveries (January 1, 2024 to May 23, 2025).

Think of it like a medical blood test report — but for a chemical factory's liquid waste stream. Every day, as production batches finish (solvent extraction, reactor washing, mother liquor distillation), effluent tanks are sampled before being dispatched to the treatment facility.

**Dataset Profile & Dimensions:**
- **Total Batch Records:** `883` daily batch deliveries
- **Date Range:** `2024-01-01` to `2025-05-23` (883 temporal steps)
- **Primary Source:** Laurus Labs Ltd (Unit-3)-JNPC
- **Effluent Type:** `HTDS` (High Total Dissolved Solids)

**9 Parameter Channels (Plain English Descriptions):**

| Parameter Name | Data Type | What It Measures (Plain English) | Operational Importance |
|---|---|---|---|
| `Company Name` | Metadata | Manufacturing unit name (*Laurus Labs Unit-3*) | Facility identification |
| `Recived Date` | Datetime | Date batch was received at ETP | Temporal step tracking |
| `Effluent type` | Metadata | Stream category (*HTDS* vs *LTDS*) | Effluent classification |
| `Volume (m3)` | Numeric | Volume of wastewater delivered in cubic meters ($m^3$) | Hydraulic load on treatment tanks |
| `PH` | Numeric | Acidity / Alkalinity level ($1.0 \text{ acidic} \rightarrow 14.0 \text{ alkaline}$) | Indicates acid washes ($pH < 6.5$) or caustic rinses |
| `TDS` (Target) | Numeric | Total Dissolved Solids in milligrams per liter ($\text{mg/L}$) | **Primary target:** Salt & mineral concentration |
| `COD` | Numeric | Chemical Oxygen Demand in milligrams per liter ($\text{mg/L}$) | Organic chemical load & solvent content |
| `AN` | Numeric | Ammoniacal Nitrogen concentration ($\text{mg/L}$) | Nitrogenous compound byproduct load |
| `SS` | Numeric | Suspended Solids concentration ($\text{mg/L}$) | Undissolved particulate matter |

---

## 🌳 Section 2: Multi-Model Generation & DAG Candidate Pool Architecture

Per **`deep_system_audit.md` (Section 4)**, the AIConnex Platform Agent does not run a single static model. When `HTDS-v1.csv` is ingested, the system resolves a **Multi-DAG Candidate Pool (3 to 5 candidate recipes)** executed in parallel via `ThreadPoolExecutor`, followed by a **Stacked Ensemble Meta-Learner** and the **3-Judge Evaluation Triad**.

```
                         HTDS DATASET INTELLIGENCE CONTRACT (DIC)
                                           │
                                           ▼
                    ┌─────────────────────────────────────────────┐
                    │ PLATFORM AGENT: MULTI-DAG RESOLVER         │
                    │ Resolves 3 to 5 Parallel Candidate Recipes  │
                    └──────────────────────┬──────────────────────┘
                                           │
       ┌───────────────────────────────────┼───────────────────────────────────┐
       ▼                                   ▼                                   ▼
 CANDIDATE 1 (DAG_414):             CANDIDATE 2 (DAG_415):             CANDIDATE 3 (DAG_654):
 LightGBM Regressor                 XGBoost / HistGradient             Isolation Forest Anomaly
 (Adaptive k=30 Lags)              (Target Differenced Δy_t)           (Unified Discharge Monitor)
       │                                   │                                   │
       └───────────────────────────────────┼───────────────────────────────────┘
                                           │
                                           ▼
                    ┌─────────────────────────────────────────────┐
                    │ CANDIDATE 4: STACKED ENSEMBLE META-LEARNER  │
                    │ Combines Candidates 1-3 Predictions         │
                    └──────────────────────┬──────────────────────┘
                                           │
                                           ▼
                    ┌─────────────────────────────────────────────┐
                    │       3-JUDGE EVALUATION TRIAD (MCDA)       │
                    │  50% Quantitative Scorer (R², MAE, MAPE)    │
                    │  30% LLM Qualitative Judge (Physical Rules) │
                    │  20% User Intent & Constraint Match         │
                    └──────────────────────┬──────────────────────┘
                                           │
                                           ▼
                    ┌─────────────────────────────────────────────┐
                    │  WINNER SELECTION & LEADERBOARD ENTRY       │
                    │  Logs Winner to MLflow + Deploys REST API   │
                    └─────────────────────────────────────────────┘
```

---

## 🔬 Section 3: The 19 Model Branches Across 3 Families

### 🟢 FAMILY A: REGRESSION — "Predict a Number"

Models that answer: *"What will our effluent concentration or volume be tomorrow?"*

| Branch ID | Branch Name | Candidate DAG | Primary Output | In Plain English |
|---|---|---|---|---|
| **A1.1** | **Next-Day TDS Forecast** | `DAG_414` | Next-day TDS ($\text{mg/L}$) | *"Tomorrow's effluent TDS will be ~39,960 mg/L."* Primary operational forecast for evaporator & RO plant planning. |
| **A1.2** | **Multi-Day TDS Trend** | `DAG_414_horizon` | 3–7 day TDS trajectory | *"TDS will average 42,500 mg/L over the next 3 days."* Useful for chemical inventory & salt recovery planning. |
| **A1.3** | **COD Organic Load Forecast** | `DAG_414_cod` | Next-day COD ($\text{mg/L}$) | *"Tomorrow's organic COD load will be ~84,800 mg/L."* Helps biological treatment operators prepare aeration basins. |
| **A1.4** | **Effluent Volume Forecast** | `DAG_414_vol` | Next-day Volume ($m^3$) | *"Tomorrow's incoming volume will be 150 m³."* Assists hydraulic tank storage management. |
| **A2.1** | **Legal Margin Predictor** | `DAG_414_margin` | Compliance buffer ($\text{mg/L}$) | *"Tomorrow's TDS will be 10,040 mg/L below the 50,000 mg/L legal compliance ceiling."* |
| **A2.2** | **Salt Accumulation Rate** | `DAG_414_diff` | Daily $\Delta \text{TDS}$ ($\text{mg/L/day}$) | *"Salinity is accumulating at +1,200 mg/L per day across this manufacturing campaign."* |
| **A3.0** | **ETP Compliance Health Index** | `DAG_414_index` | Score $100\% \rightarrow 0\%$ | *"Overall effluent compliance score for today's batch is 88/100."* Single score for plant dashboards. |
| **A4.0** | **Discharge Status Classifier** | `DAG_414_cls` | Category: Normal/Watch/Alert | *"Today's batch status: NORMAL — safe for standard ETP processing."* Clear bucket for plant operators. |

---

### 🔴 FAMILY B: ANOMALY — "Catch Something Wrong"

Models that answer: *"Is this wastewater batch abnormal or contaminated compared to historical patterns?"*

| Branch ID | Branch Name | Candidate DAG | Primary Output | In Plain English |
|---|---|---|---|---|
| **B1.0** | **Single Unified ETP Monitor** | `DAG_654` | Anomaly Score ($0.0 \rightarrow 1.0$) | *"Batch #883 showing abnormal chemical composition — recommend holding tank isolation."* One alert covering all contamination types. |
| **B2.1** | **High-Salinity Shock Monitor** | `DAG_654_tds` | Salt Shock Flag | *"High-salinity shock detected: TDS is running 12,000 mg/L above normal baseline."* Isolates salt shocks for evaporator protection. |
| **B2.2** | **Organic COD Spill Monitor** | `DAG_654_cod` | COD Spill Flag | *"Organic solvent spill detected: COD surged to 112,000 mg/L. Risk of killing biological ETP bacteria."* |
| **B2.3** | **Acidic Stream Intrusion Monitor** | `DAG_654_ph` | Acid Intrusion Flag | *"Acidic stream intrusion detected: pH dropped to 6.5. High risk of equipment corrosion."* |
| **B3.0** | **Campaign Onset Alert** | `DAG_654_onset` | Change-point step $t$ | *"Effluent baseline shifted on May 18th — new chemical manufacturing campaign started."* |
| **B4.0** | **Shock Root-Cause Classifier** | `DAG_654_cat` | Fault Category | *"Shock isolated to: ORGANIC SOLVENT SPILL (confidence: 94%)."* Tells operators which plant line caused the spill. |
| **B5.0** | **Legal Violation Alert** | `DAG_654_limit` | Binary Legal Alert | *"⚠️ CRITICAL: TDS exceeding legal discharge limit of 50,000 mg/L. Divert to emergency holding tank."* |

---

### 🟣 FAMILY C: HYBRID — "Smart Combined Systems"

Models that combine anomaly detection and quantitative forecasting into a single intelligent workflow.

| Branch ID | Branch Name | Candidate Architecture | How It Works | In Plain English |
|---|---|---|---|---|
| **C1.0** | **Smart Auto-Activate** | `DAG_654` $\rightarrow$ `DAG_414` | Quiet `DAG_654` monitor runs 24/7. When shock is detected $\rightarrow$ automatically activates `DAG_414` Next-Day TDS forecast. | *"Batch running normally for 40 days. [Silent.] Shock detected on Day #41. [Activating forecast...] Next-Day TDS predicted to reach 47,500 mg/L."* |
| **C2.0** | **Two-Stage Assessment** | `DAG_Classifier` + `DAG_414_Regime` | Stage 1: Classifies discharge regime (Routine vs Shock). Stage 2: Runs a regime-specific forecast model. | *"Batch classified as CHEMICAL SHOCK REGIME. Running shock-tuned forecast model... Predicted TDS: 46,200 mg/L."* |
| **C3.0** | **Anomaly-Enriched Forecast** | `DAG_654` score $\rightarrow$ `DAG_414` feature | `DAG_654` anomaly score ($0.0 \rightarrow 1.0$) is fed as an extra input feature into the `DAG_414` TDS forecaster. | *"Anomaly score = 0.82 (High Shock). Forecaster with anomaly enrichment: Next-Day TDS = 44,100 mg/L."* |
| **C4.0** | **Multi-Output Joint ETP Engine** | `DAG_414_StackedEnsemble` | Single multi-head model that simultaneously outputs: (1) Next-Day TDS, (2) Anomaly Score, (3) Shock Category. | *"Next-Day TDS = 39,960 mg/L \| Anomaly Score = 0.14 \| Status = NORMAL."* One model, complete ETP intelligence. |

---

## ⚖️ Section 4: 3-Judge Evaluation Triad & MCDA Scoring (Per Audit Standard)

Per **`deep_system_audit.md` (Section 4, Page 12)**, candidate models generated across Families A, B, and C are evaluated using the **Multi-Criteria Decision Analysis (MCDA)** framework:

```
                            MCDA WEIGHTING FORMULA
                                      │
 ┌────────────────────────────────────┼────────────────────────────────────┐
 ▼                                    ▼                                    ▼
50% QUANTITATIVE SCORER              30% LLM QUALITATIVE JUDGE            20% USER INTENT MATCH
(R², MAE, MAPE, Latency)             (Physical Constraint Check)          (Constraint & Urgency)
```

### MCDA Scorecard Calculation

$$\text{MCDA Score} = 0.50 \times \text{Score}_{\text{Quantitative}} + 0.30 \times \text{Score}_{\text{LLM\_Judge}} + 0.20 \times \text{Score}_{\text{Intent\_Match}}$$

| Evaluation Component | Weight | Metric / Evaluation Criteria | HTDS Performance Benchmark |
|---|---|---|---|
| **1. Quantitative Scorer Agent** | **50%** | $R^2 \ge 0.90$, $\text{MAE} \le 3,000 \text{ mg/L}$, $\text{MAPE} \le 15\%$, Inference Latency $< 50\text{ms}$ | $R^2 = 0.9017$, $\text{MAE} = 2,961\text{ mg/L}$, $\text{MAPE} = 13.83\%$ (PASS) |
| **2. LLM Qualitative Judge Agent** | **30%** | Validates physical constraints (no negative TDS predictions, `{target}_lag1` protected from `SelectKBest` dropping, no undefined log transforms) | Verified 100% compliance with physical ETP constraints (PASS) |
| **3. User Intent Matcher** | **20%** | Matches extracted `ConversationUnderstandingContract` (CUC) user goals (e.g. Next-Day TDS vs Solvent Spill Alert) | Matches user operational intent (PASS) |

---

## 🔗 Section 5: 5-Stage Contract Pipeline Integration

To guarantee seamless interaction across all 4 system layers, the HTDS specification maps directly to the **5-Stage Contract Pipeline** in `deep_system_audit.md`:

```
 Stage 1: ConversationUnderstandingContract (CUC)
 └─► User Intent: "Predict tomorrow's salinity level to prevent ETP overflow"
      │
 Stage 2: ScoutEnrichedContract
 └─► Upload Metadata: HTDS-v1.csv (883 rows, 9 columns, duplicate date grain detected)
      │
 Stage 3: PreCompilerContract
 └─► Compiler Setup: Temporal sorting, scale skewness flag, protected lag rule
      │
 Stage 4: DatasetIntelligenceContract (DIC)
 └─► Schema: [Recived Date, PH, Volume (m3), COD, AN, SS, TDS] | Task: Regression (DAG_414)
      │
 Stage 5: SelectionResult + LeaderboardEntry[]
 └─► Winner: Candidate 4 (LightGBM DAG_414 + Adaptive k=30) | MCDA Score: 0.925 -> Deployed
```

---

## 💬 Section 6: Non-Technical HITL Question Blueprint

All questions framed for an **ETP Plant Manager or Environmental Engineer** — zero data science jargon.

---

### Question 1: Primary Operational Goal
> *"What is the main task you would like AIConnex to perform for your effluent treatment plant?"*
> - **[A] Predict tomorrow's TDS salinity level** *(Forecast Next-Day TDS in mg/L for evaporator & RO plant planning)*
> - **[B] Alert me when a high-salinity shock or organic solvent spill occurs** *(Real-time contamination monitoring)*
> - **[C] Keep a quiet monitor running 24/7, but activate a TDS forecast as soon as a chemical shock is detected** *(Smart combined system — recommended for plant operations)*

---

### Question 2: Specific Parameter Focus
> *"Which chemical parameter is your highest priority to track?"*
> - **[A] Total Dissolved Solids (TDS)** *(Primary focus on salt concentration and evaporator capacity)*
> - **[B] Chemical Oxygen Demand (COD)** *(Primary focus on organic solvent loads and biological treatment safety)*
> - **[C] Both TDS and COD together** *(Multi-parameter plant monitoring)*

---

### Question 3: Alert Sensitivity Preference *(Only if user chose Option B or C in Question 1)*
> *"How sensitive should the chemical shock alarm be?"*
> - **[A] High Sensitivity** *(Early warning — flags subtle pH drops or mild COD surges)*
> - **[B] Balanced Sensitivity** *(Flags confirmed chemical shocks — recommended)*
> - **[C] Critical Alerts Only** *(Flags only severe legal limit breaches > 50,000 mg/L TDS or > 110,000 mg/L COD)*

---

### Question 4: Forecast Presentation Format *(Only if user chose Option A in Question 1)*
> *"How should tomorrow's forecast be displayed on your control room dashboard?"*
> - **[A] Exact predicted number in mg/L** *(e.g., "Tomorrow's TDS: 39,960 mg/L")*
> - **[B] Traffic Light Status** *(GREEN = Normal, YELLOW = Watchlist, RED = Emergency Holding Tank)*
> - **[C] Both — exact number plus traffic light status**

---

## 🎯 Section 7: Summary & Principles

### Branch Count Summary

| Family | Branches | Description |
|---|---|---|
| **A: Regression** | 8 | Next-Day TDS, Multi-Day Trend, COD Load, Volume, Legal Margin, Accumulation Rate, Health Index, Status Classifier |
| **B: Anomaly** | 7 | Unified Monitor, Salinity Shock, Organic Spill, Acidic Intrusion, Campaign Onset, Root Cause Classifier, Legal Violation Alert |
| **C: Hybrid** | 4 | Smart Auto-Activate, Two-Stage Assessment, Anomaly-Enriched Forecast, Multi-Output Joint ETP Engine |
| **TOTAL** | **19** | **Complete Model Branching Specification for HTDS Effluent Data** |

### Key Architectural Principles (Per `deep_system_audit.md`)

1. **Multi-DAG Parallel Resolution:** 3 to 5 candidate recipes (`DAG_414`, `DAG_415`, `DAG_654`) run in parallel via `ThreadPoolExecutor`.
2. **Stacked Ensemble Meta-Learner:** Combines top candidate predictions into a unified meta-model.
3. **MCDA 3-Judge Evaluation Triad:** Winner selected using 50% Quantitative Scorer + 30% LLM Qualitative Judge + 20% User Intent Match.
4. **5-Stage Contract Pipeline Flow:** Guarantees strict data contract handoffs from CUC $\rightarrow$ DIC $\rightarrow$ SelectionResult leaderboard.
