# AIConnex — Complete Agentic Flow (User Typing → Model Ready)

Every node, agent, and component in the current system, in plain words.

---

## The Big Picture (10 Phases)

```text
 USER TYPES                                                           MODEL READY
    │                                                                      ▲
    ▼                                                                      │
 ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐
 │  P1  │──►│  P2  │──►│  P3  │──►│  P4  │──►│  P5  │──►│  P6  │──►│  P7  │──►│  P8  │──►│  P9  │──►│ P10  │
 │ Chat │   │ Plan │   │ Data │   │Scout │   │ HITL │   │ DIC  │   │ Gate │   │Manif.│   │  ML  │   │Board │
 └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘
```

---

## Phase-by-Phase Walkthrough

### Phase 1 — CUC Chat (Conversation Understanding)

```text
 ┌────────────────────────────────────────────────────────┐
 │  USER types: "I have pharma wastewater, predict TDS"   │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │  Conversation Parser Agent                             │
 │  ├─ PromptBuilder        → formats prompt for LLM     │
 │  ├─ ContextManager       → tracks multi-turn history   │
 │  ├─ SemanticExtractor    → Qwen 32B extracts intent   │
 │  ├─ StructuredOutputValidator → validates JSON output  │
 │  ├─ ConfidenceScorer     → scores 0.0 → 1.0           │
 │  └─ ClarificationGenerator → asks follow-ups if <0.85 │
 └───────────────────────┬────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
        Confidence < 0.85     Confidence ≥ 0.85
              │                     │
              ▼                     ▼
     ┌─────────────────┐    ┌─────────────────┐
     │ Clarification    │    │  CUC Contract   │
     │ "What type of    │    │  LOCKED ✅       │
     │  prediction?"   │    │  domain: ETP     │
     │ (loops back)     │    │  target: TDS     │
     └─────────────────┘    │  task: regression │
                            └────────┬────────┘
                                     │
                                     ▼
```

**Who**: `pre_upload_flow.py` → `aiconnex_agent/parser/` (6 sub-modules)
**LLM**: Qwen 32B via OpenRouter
**Output**: `CUC` JSON contract (domain, target, goal type, confidence)

---

### Phase 2 — Planner (Execution Plan)

```text
 ┌────────────────────────────────────────────────────────┐
 │  Planning Engine                                       │
 │                                                        │
 │  Takes CUC contract → builds 7-step execution plan:    │
 │                                                        │
 │    Step 1: Acquire Data           → scout agent        │
 │    Step 2: Dataset Intelligence   → scout agent        │
 │    Step 3: HITL Clarification     → hitl agent         │
 │    Step 4: Feature Engineering    → platform agent     │
 │    Step 5: Parallel Model Training→ platform agent     │
 │    Step 6: Evaluation & Selection → platform agent     │
 │    Step 7: MLflow Experiment Log  → telemetry          │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
```

**Who**: `aiconnex_agent/planning/planning_engine.py`
**Output**: Ordered `plan_steps[]` list with agent assignments

---

### Phase 3 — Dataset Resolution

```text
 ┌────────────────────────────────────────────────────────┐
 │  Dataset Resolution                                    │
 │                                                        │
 │  Locates the raw dataset file on disk:                 │
 │  ├─ User uploads via UI (📎 button / drag-drop)        │
 │  ├─ OR static path: data/raw/HTDS-v1.csv              │
 │                                                        │
 │  Validates: file exists, readable, size > 0            │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
```

**Who**: `terminal_runner.py → resolve_dataset()` or `/api/upload` endpoint
**Output**: Verified file path (e.g. `data/raw/HTDS-v1.csv`)

---

### Phase 4 — Scout Agent (Dataset Compilation)

```text
 ┌────────────────────────────────────────────────────────────────────┐
 │  Scout Agent                                                       │
 │                                                                    │
 │  Step A: Strategy Peek (read-only, lightweight)                    │
 │  ├─ peek_dataset_card_and_options()                                │
 │  ├─ Sniffs headers, detects encoding, counts tables                │
 │  └─ If 2+ strategies found → HITL interrupt (ask user to choose)   │
 │                                                                    │
 │  Step B: UnifiedCompiler (heavy, writes to disk)                   │
 │  ├─ Stage 1 (Discovery)   → probe ZIP/CSV/XLSX structures         │
 │  ├─ Stage 2 (Parser)      → read tables, snake_case headers       │
 │  ├─ Stage 3 (Assembler)   → join multi-sensor tables              │
 │  ├─ Stage 4 (Harvester)   → compute group stats & quality         │
 │  └─ Stage 5 (Normalizer)  → export all_groups_combined.csv        │
 │                                                                    │
 │  Step C: Recipe Catalog Builder                                    │
 │  ├─ Analyzes compiled CSV columns                                  │
 │  ├─ Identifies target candidates (TDS, COD, PH...)                 │
 │  ├─ Proposes problem types (regression, classification, anomaly)   │
 │  └─ Generates branching hints & recipe suggestions                 │
 │                                                                    │
 │  Step D: DIC Validator                                             │
 │  └─ Validates completeness of Dataset Intelligence Contract        │
 └───────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
```

**Who**: `aiconnex_agent/scout/scout_node.py` → `aiconnex_zip_compiler/compiler.py`
**Plugins**: 22 active plugins across 5 stages
**Output**: `all_groups_combined.csv` + `DIC` contract + `scout_enriched` metadata

---

### Phase 5 — HITL Clarification (Plant Manager Questions)

```text
 ┌────────────────────────────────────────────────────────────────────┐
 │  HITL Clarification Agent                                          │
 │                                                                    │
 │  Reads DIC contract (knows what columns exist in the data)         │
 │                                                                    │
 │  Asks NON-TECHNICAL questions to the plant manager:                │
 │                                                                    │
 │  💬 "I found TDS, COD, PH, Volume in your dataset.                │
 │      What is your operational goal?"                               │
 │      • Option A: Next-Day TDS Forecast                             │
 │      • Option B: 5-Day Trend Prediction                            │
 │      • Option C: Regulatory Breach Alert (TDS > 2500 mg/L)         │
 │                                                                    │
 │  💬 "What is your primary risk concern?"                           │
 │      • Under-predicting TDS spikes (penalty on misses)             │
 │      • Balanced overall accuracy                                   │
 │                                                                    │
 │  Captures into HITLContract:                                       │
 │  ├─ operational_goal      = "next_day_tds_forecast"                │
 │  ├─ primary_parameter     = "TDS"                                  │
 │  ├─ alert_sensitivity     = "penalty_on_underprediction"           │
 │  └─ display_format        = "daily_trend_chart"                    │
 │                                                                    │
 │  Resolves candidate DAG pool:                                      │
 │  └─ [DAG_414 LightGBM, DAG_491 RandomForest, DAG_654 XGBoost]     │
 └───────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
```

**Who**: `chatbot/backend/hitl_flow.py` → `hitl_extraction.py`
**LLM**: Qwen 32B generates questions dynamically from DIC context
**Output**: `HITLContract` + `resolved_dag_pool[]` + `target_column`

---

### Phase 6 — DIC Export & Summary

```text
 ┌────────────────────────────────────────────────────────┐
 │  DIC Export                                            │
 │                                                        │
 │  Combines Scout output + HITL decisions into:          │
 │  ├─ Dataset Identity (name, rows, columns)             │
 │  ├─ Selected Recipe (R001 — Predict TDS, REGRESSION)   │
 │  ├─ Compiled CSV path                                  │
 │  └─ Target column + DAG pool                           │
 │                                                        │
 │  Phase 1 Status: COMPLETE ✅                            │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
```

**Who**: `terminal_runner.py → print_dic_summary()`
**Output**: Combined `phase1_export` dict

---

### Phase 7 — Confirmation Gate (Human Approval)

```text
 ┌────────────────────────────────────────────────────────┐
 │  Confirmation Gate                                     │
 │                                                        │
 │  Shows the user exactly what will be trained:          │
 │  ├─ Recipe: R001 — Predict TDS                         │
 │  ├─ Task: REGRESSION                                   │
 │  ├─ Target: TDS                                        │
 │  └─ CSV: scratch/scout_output/wf_.../combined.csv      │
 │                                                        │
 │  "Proceed with ML model training? (Y/n)"               │
 │                                                        │
 │  User types Y → continues                              │
 │  User types N → pipeline stops here                    │
 └───────────────────────┬────────────────────────────────┘
                         │ (Y)
                         ▼
```

**Who**: `terminal_runner.py → run_confirmation_gate()`
**Output**: Boolean go/no-go decision

---

### Phase 8 — Manifest Generation (ML Bridge)

```text
 ┌────────────────────────────────────────────────────────────────────┐
 │  Manifest Builder                                                  │
 │                                                                    │
 │  Creates the authoritative manifest.json that drives ML execution: │
 │                                                                    │
 │  {                                                                 │
 │    "session_id": "wf_a1b2c3d4",                                    │
 │    "ml_task": "REGRESSION",                                        │
 │    "label_contract": { "target_column": "TDS" },                   │
 │    "schema_config": { "raw_features": ["PH","COD","Volume",...] }, │
 │    "candidate_algorithms": ["LightGBM","RandomForest","XGBoost"],  │
 │    "data_path": "scratch/scout_output/.../all_groups_combined.csv" │
 │  }                                                                 │
 │                                                                    │
 │  Saved to: outputs/wf_a1b2c3d4/manifest.json                      │
 └───────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
```

**Who**: `aiconnex_agent/platform/manifest_builder.py`
**Output**: `outputs/{session_id}/manifest.json`

---

### Phase 9 — ML Core Pipeline Execution (9-Node DAG)

```text
 ┌────────────────────────────────────────────────────────────────────┐
 │  PipelineRunner (aiconnex_ml/runner.py)                            │
 │                                                                    │
 │  Reads manifest.json → executes 9-node microservices cascade:      │
 │                                                                    │
 │  ┌─────────┐   ┌─────────┐   ┌─────────┐                          │
 │  │ Node 1  │──►│ Node 2  │──►│ Node 3  │                          │
 │  │Profiler │   │  DAG    │   │ Recipe  │                          │
 │  │(schema) │   │(match)  │   │(resolve)│                          │
 │  └─────────┘   └─────────┘   └─────────┘                          │
 │       │                                                            │
 │       ▼                                                            │
 │  ┌─────────┐   ┌─────────┐   ┌─────────┐                          │
 │  │ Node 4  │──►│ Node 5  │──►│ Node 6  │                          │
 │  │Prepare  │   │Feature  │   │ Split   │                          │
 │  │(clean,  │   │Engineer │   │(chrono  │                          │
 │  │ scale)  │   │(lags,   │   │ 70/15/  │                          │
 │  │         │   │ rolling)│   │  15)    │                          │
 │  └─────────┘   └─────────┘   └─────────┘                          │
 │       │                                                            │
 │       ▼                                                            │
 │  ┌─────────┐   ┌─────────┐   ┌─────────┐                          │
 │  │ Node 7  │──►│ Node 8  │──►│ Node 9  │                          │
 │  │ Train   │   │Evaluate │   │ Deploy  │                          │
 │  │(LightGBM│   │(VG_1    │   │(REST    │                          │
 │  │ XGB, RF)│   │ VG_2    │   │ :8001   │                          │
 │  │         │   │ gates)  │   │ + drift)│                          │
 │  └─────────┘   └─────────┘   └─────────┘                          │
 │                                                                    │
 │  Node 4: Cleans nulls, imputes, scales (StandardScaler)            │
 │  Node 5: Builds lag features (t-1, t-3, t-7), rolling mean/std    │
 │  Node 6: Chronological 70/15/15 train/val/test split              │
 │  Node 7: Trains 3-5 candidates in parallel (ThreadPoolExecutor)    │
 │           + fits Stacked Ensemble Meta-Learner                     │
 │  Node 8: VG_1 sanity gate (R² > 0, no NaN predictions)            │
 │           VG_2 robustness gate (+20% noise injection test)         │
 │  Node 9: Deploys winner to REST endpoint http://localhost:8001     │
 │           + monitors PSI feature drift                             │
 └───────────────────────┬────────────────────────────────────────────┘
```

**Who**: `aiconnex_ml/runner.py` → `aic/` (9 microservice directories)
**Output**: Trained `model.pkl` + `scaler.pkl` + `predictions.csv` + validation reports

---

### Phase 10 — Leaderboard & Model Export

```text
 ┌────────────────────────────────────────────────────────────────────┐
 │  Leaderboard & Final Selection                                     │
 │                                                                    │
 │  ┌─────────────────────────────────────────────────────────────┐    │
 │  │  🏆 Rank 1 (WINNER): LightGBM      R²=0.9017  MAE=2961    │    │
 │  │     Rank 2:          XGBoost        R²=0.8847  MAE=3201    │    │
 │  │     Rank 3:          Random Forest  R²=0.8717  MAE=3451    │    │
 │  └─────────────────────────────────────────────────────────────┘    │
 │                                                                    │
 │  Evaluation Triad:                                                 │
 │  ├─ Scorer Agent  (50%) → R², RMSE, MAE, MAPE, latency, size      │
 │  ├─ Judge Agent   (30%) → LLM qualitative risk reasoning           │
 │  └─ Selector Agent(20%) → MCDA combining scorer + judge + intent   │
 │                                                                    │
 │  Final Outputs:                                                    │
 │  ├─ model.pkl            → trained model binary                    │
 │  ├─ scaler.pkl           → fitted data scaler                     │
 │  ├─ predictions.csv      → holdout test predictions                │
 │  ├─ training_manifest.json → full run metadata                    │
 │  └─ MLflow experiment    → ./mlruns (open with: mlflow ui)         │
 │                                                                    │
 │  REST Endpoint Live:                                               │
 │  └─ POST http://localhost:8001/api/v1/predict/run_<id>             │
 │                                                                    │
 │  ✅ MODEL READY                                                    │
 └────────────────────────────────────────────────────────────────────┘
```

**Who**: `terminal_runner.py → run_leaderboard_and_export_phase()`
**Telemetry**: `aiconnex_agent/telemetry/emitters.py` → MLflow `./mlruns`

---

## Cross-Cutting Services (Running Throughout)

```text
 ┌──────────────────────────────────────────────────────────────┐
 │  MEMORY AGENT (runs after every phase)                       │
 │  ├─ EventStore        → workspace_data/events.jsonl          │
 │  ├─ MemoryBuilder     → projects events into 4 memory layers │
 │  └─ mem0 / Qdrant     → ./.mem0_qdrant/ (semantic recall)    │
 ├──────────────────────────────────────────────────────────────┤
 │  MLFLOW TELEMETRY (runs after every phase)                   │
 │  ├─ Logs params, metrics, artifacts per node                 │
 │  └─ Stores in ./mlruns (local file store)                    │
 ├──────────────────────────────────────────────────────────────┤
 │  LANGGRAPH CHECKPOINTER (snapshots after every node)         │
 │  └─ SqliteSaver → workspace_data/checkpoints.db              │
 └──────────────────────────────────────────────────────────────┘
```
