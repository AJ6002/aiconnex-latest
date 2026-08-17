# 🏛️ AIConnex Autonomous Agentic MLOps Platform — Final Master Architecture

---

## 1. Executive Overview & Design Principles

**AIConnex** is an end-to-end, domain-agnostic autonomous Machine Learning operating system and multi-table dataset compiler engineered specifically for industrial telemetry, predictive maintenance (PdM), prognostics and health management (PHM), digital twins, and SCADA automation.

### 🔑 Core Architectural Principles:
1. **Zero-Regression Guarantee**: The agentic supervisor and multi-candidate ensemble layer wrap *around* the core 9-node microservices and 1,993 DAG recipe catalog—preserving 100% of existing single-DAG microservice endpoints and CLI runners.
2. **Supervisor-Agent Mesh over Blackboard Memory**: A Master Supervisor Agent (driven by **LangGraph**) coordinates specialist agents (**Scout**, **Memory**, **Platform**, **Scorer**, **Judge**, **Selector**) over a shared Knowledge Blackboard (**Memory Agent** backed by `events.jsonl` and `mem0` / Qdrant vector store).
3. **H2O-Aligned Multi-Candidate Competition & Stacked Ensembling**: Replaces single-model guessing with multi-recipe competition. Resolves 3–5 complementary DAG IDs, trains them in parallel, and fits a **Ridge/GLM Stacked Ensemble Meta-Learner** that cancels out individual model errors.
4. **Dual-Evaluation Triad**: Combines hard mathematical metrics (**Scorer Agent**) with LLM-based qualitative risk reasoning (**Judge Agent**), evaluated by a **Selector Agent** against user intent.

---

## 2. Complete End-to-End Master System Architecture

```mermaid
graph TD
    User[User Prompt / Raw Dataset Archive] --> MasterAgent[1. Master LangGraph Supervisor Agent<br/>aiconnex_agent/graph.py]
    
    subgraph FrontDesk ["Front-Desk & Intent Parsing"]
        MasterAgent --> ConvParser[2. Conversation Parser<br/>aiconnex_agent/parser/]
        ConvParser --> ConfidenceCheck{Confidence >= 0.85?}
        ConfidenceCheck -- No --> ClarificationNode[HITL Clarification Node<br/>Real LLM Question Generation]
        ClarificationNode --> ConvParser
        ConfidenceCheck -- Yes --> CUCContract[CUC Contract Generated]
    end

    subgraph Planning ["Planning & Intelligence Retrieval"]
        CUCContract --> PlanningEngine[3. Planning Engine<br/>aiconnex_agent/planning/]
        PlanningEngine <--> ScoutAgent[4a. Scout Agent<br/>Exploration & Compiler Patches]
        PlanningEngine <--> MemoryAgent[4b. Memory Agent<br/>mem0 Vector Store & EventStore]
    end

    subgraph MultiRecipe ["Multi-Candidate Recipe Resolution"]
        PlanningEngine --> MultiResolver[5. Multi-DAG Candidate Resolver<br/>Node 2 & Node 3 Integration]
        MultiResolver --> RecipeCatalog[(6,760 Master Recipe JSONs<br/>aic/3_recipe_orchestrator/recipe/)]
        MultiResolver --> CandidateSet[Emits candidate_recipes[]]
    end

    subgraph ExecutionHarness ["Platform Agent: Parallel S.T.E.-M. Harness"]
        CandidateSet --> Worker1[Worker 1: DAG_414 LightGBM]
        CandidateSet --> Worker2[Worker 2: DAG_241 RandomForest]
        CandidateSet --> Worker3[Worker 3: DAG_906 XGBoost+Lags]
        
        Worker1 --> OOFCollector[OOF CV Predictions Collector]
        Worker2 --> OOFCollector
        Worker3 --> OOFCollector
        
        OOFCollector --> MetaLearner[Node 7: Stacked Ensemble Meta-Learner<br/>Ridge / GLM Ensembler]
    end

    subgraph Evaluation ["Evaluation Triad & Selection"]
        MetaLearner --> ScorerAgent[Scorer Agent<br/>R², RMSE, MAE, MAPE, Latency, Size]
        MetaLearner --> JudgeAgent[Judge Agent<br/>LLM Qualitative Risk & Rubrics]
        
        ScorerAgent --> SelectorAgent[Selector Agent<br/>Multi-Criteria Decision Analysis]
        JudgeAgent --> SelectorAgent
        
        SelectorAgent --> Winner[Winner Selected: Stacked Ensemble / Model ID]
    end

    subgraph Operations ["Deployment, MLflow & Drift Monitoring"]
        Winner --> DeployModule[REST Serving Endpoint :8001]
        Winner --> MLflowLogger[MLflow Tracking & Artifact Registry]
        Winner --> MemoryWriter[Memory Builder & EventStore Writer]
        DeployModule --> DriftMonitor[Scout Production Drift Monitor]
    end
```

---

## 3. Layer-by-Layer Technical Specifications

### Layer 0: Universal Relational Dataset Compiler (`aiconnex_zip_compiler`)
- **5-Stage Plugin Execution Engine (`aiconnex_zip_compiler/plugins/`)**:
  1. **Discovery Stage (`discovery.py`)**: Recursively navigates raw ZIP/CSV/MAT/HDF5 archives, detects text encodings (`utf-8`, `latin-1`), and discovers multi-table folder structures.
  2. **Parser Stage (`parser.py`)**: Extracts raw table streams, parses format headers, standardizes column names into `snake_case`, and detects temporal axes.
  3. **Assembler Stage (`assembler.py`)**: Performs side-by-side index-matching joins across parallel sensor channels (`collector_current`, `collector_voltage`, `package_temp`) while guarding against Cartesian row count explosions ($<5\%$ delta safety threshold).
  4. **Harvester Stage (`harvester.py`)**: Collects group-level metadata, detects operating regimes, and verifies schema consistency across multi-device fleets.
  5. **Normalizer Stage (`normalizer.py`)**: Concatenates aligned fleet groups into `all_groups_combined.csv` and outputs `unified_manifest.json` for downstream MLOps profiling.

---

### Layer 1: Core 9-Node MLOps Microservices Cascade (`aic/`)
- **Node 1 (`1_dataset_profiler`)**: FastApi profiler & format detector. Computes column distributions and generates `meta1.json`.
- **Node 2 (`2_dag`)**: Matches dataset profile against `dag_conditions_mapping.json` (1,993 DAG specifications across 10 ML domains).
- **Node 3 (`3_recipe_orchestrator`)**: Recipe engine accessing 6,760 pre-compiled stage recipe JSON files (`preparing`, `feature_engineering`, `splitting`, `training`).
- **Node 4 (`4_prepare`)**: Data cleaning, null imputation, scaling (`StandardScaler`, `RobustScaler`).
- **Node 5 (`5_feature_engineering`)**: Industrial rolling lag matrices ($t-1, t-5, t-10$), moving averages, rolling std, and spectral features.
- **Node 6 (`6_split`)**: Enforces zero-leakage group-chronological splitting (70/15/15 cut).
- **Node 7 (`7_train`)**: Multi-model production HPO trainer supporting 13 model families (LightGBM, XGBoost, Random Forest, SVR, SVC, IsolationForest, GLM, etc.).
- **Node 8 (`8_evaluate`)**: Industrial Validation Gates:
  - `VG_1`: Sanity gate (numerical stability, non-trivial $R^2$).
  - `VG_2`: Robustness gate (+20% noise injection & false-alarm-rate test).
- **Node 9 (`9_deploy_monitor`)**: Model serving REST endpoint (`:8001`) with Population Stability Index (PSI) feature drift monitoring.

---

### Layer 2: Master Supervisor & State Machine (`aiconnex_agent/graph.py`)
- **LangGraph `StateGraph`**: Coordinates execution across nodes via a strongly-typed `MasterAgentState`.
- **Checkpointer (`MemorySaver`)**: Persists state turn-by-turn enabling Human-in-the-Loop (HITL) interrupts.
- **Rich Terminal UI (`agentic_terminla_UI/tui_app.py`)**: Multi-pane live terminal dashboard streaming real-time graph execution telemetry.

---

### Layer 3: Specialized Agent Mesh
- **Conversation Parser (`aiconnex_agent/parser/`)**: 6 modular sub-modules (`PromptBuilder`, `ContextManager`, `SemanticExtractor`, `StructuredOutputValidator`, `ConfidenceScorer`, `ClarificationGenerator`) producing `ConversationUnderstandingContract` (CUC).
- **Planning Engine (`aiconnex_agent/planning/`)**: `IntentPlanMapper` mapping intent to execution steps and multi-candidate recipes.
- **Scout Agent (`aiconnex_agent/scout/`)**: Integrates with `UnifiedCompiler`, executes Strategy Peeks, monitors model zoo, and detects production drift.
- **Memory Agent (`aiconnex_agent/memory/`)**:
  - `EventStore`: Append-only immutable event log (`workspace_data/events.jsonl`).
  - `MemoryPolicyEngine`: Data retention & privacy rules.
  - `MemoryBuilder`: Re-projects events into audit memory products.
  - `mem0` Vector Memory: Embedded Qdrant database (`./.mem0_qdrant/`) for semantic recall of past experiments & user preferences.

---

### Layer 4: Platform Agent & H2O-Aligned Ensemble Engine (`aiconnex_agent/platform/`)
- **Multi-DAG Candidate Resolver**: Resolves candidate set of 3–5 complementary DAG IDs for the dataset profile.
- **Parallel Training Harness**: Spawns parallel worker threads via `ThreadPoolExecutor` running Nodes 4–7 for all candidate recipes simultaneously.
- **Stacked Ensemble Meta-Learner (`aiconnex_ml/shared/ensemble.py`)**: Fits a non-negative Ridge Meta-Learner on out-of-fold cross-validation predictions:
  $$\hat{y} = \sum_{k=1}^{K} w_k \cdot \text{Model}_k \quad \text{s.t. } w_k \ge 0$$
- **Evaluation Triad**:
  - **Scorer Agent**: Deterministic metrics ($R^2$, RMSE, MAE, MAPE, latency, size).
  - **Judge Agent**: LLM-based qualitative evaluation (out-of-bounds risks, physical realism).
  - **Selector Agent**: Multi-Criteria Decision Analysis (MCDA) combining Scorer + Judge + CUC Intent + Memory preferences to pick the Winner.

---

### Layer 5: MLflow Tracking & Production Monitoring
- **MLflow Tracking (`aiconnex_agent/platform/mlflow_logger.py`)**: Logs parameters, metrics, leaderboard table, and model binaries (`.pkl`).
- **REST Serving (`:8001`)**: Deploys the winning model or Stacked Ensemble.
- **Drift Monitoring**: Scout Agent monitors incoming inference payloads for PSI drift and triggers retraining.

---

## 4. Pydantic State & Contract Schemas

```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class CandidateRecipe(BaseModel):
    recipe_id: str
    dag_id: str
    algo_family: str
    hyperparameters: Dict[str, Any]
    feature_config: Dict[str, Any]

class ScorerReport(BaseModel):
    recipe_id: str
    r2_score: float
    rmse: float
    mae: float
    mape: float
    latency_ms: float
    model_size_mb: float

class JudgeReport(BaseModel):
    recipe_id: str
    qualitative_score: float
    rubric_ratings: Dict[str, float]
    reasoning: str
    risk_assessment: str

class LeaderboardEntry(BaseModel):
    rank: int
    model_id: str
    dag_id: str
    algo_name: str
    composite_score: float
    r2_score: float
    rmse: float
    mae: float
    is_winner: bool

class SelectionResult(BaseModel):
    winner_model_id: str
    winner_dag_id: str
    is_ensemble: bool
    selection_rationale: str
    leaderboard: List[LeaderboardEntry]
```

---

## 5. Zero-Regression Guarantee Summary

| Component | Status | Guarantee |
| :--- | :---: | :--- |
| **9-Node Microservices (`aic/`)** | Intact | Existing REST endpoints (`:8000`..`:8008`) and `start_all.py` remain 100% operational. |
| **1,993 DAG Catalog & 6,760 Recipes** | Intact | Read in read-only mode by Node 3 for multi-recipe resolution. |
| **Single-DAG CLI Runner (`run_pipeline.py`)** | Intact | Command-line execution continues working without modification. |
| **Phases 1–5b Agent Modules** | Integrated | LangGraph graph, Conv Parser, Rich TUI, Scout, and Memory Agent are preserved and extended. |

---

## 6. Phase 5c Critical Design Decisions & Operational Guardrails

To prevent silent failures, resource contention, and ad-hoc architecture drift during Phase 5c implementation, the following 9 operational guardrails are locked into the system design:

### 1. Unified Session Identity Model (`workflow_id`)
- Every candidate recipe execution, OOF prediction matrix, scorer metric, judge report, and leaderboard entry MUST trace back to `state.session_id` (`wf_<hex>`).
- The `workflow_id` is passed as a single immutable key across all worker threads and Memory Agent event store appends to preserve 100% audit correlation.

### 2. Candidate-Level Partial Failure Semantics
- Individual worker failures (e.g. XGBoost OOM, recipe shape mismatch) do NOT crash the parent ensemble pipeline or trigger silent fallthroughs.
- Failed workers emit a `CandidateFailedEvent`, get excluded from the candidate pool, and the Stacked Ensemble Meta-Learner proceeds using the remaining successful candidates ($K \ge 2$).

### 3. Concurrency Ceiling & CPU-Bound Process Management
- Parallel worker execution uses `ProcessPoolExecutor` (or bounded `ThreadPoolExecutor` capped at **`max_workers = min(3, os.cpu_count())`**) to prevent CPU thrashing and RAM exhaustion during heavy multi-model training.

### 4. Standardized Judge LLM Call Pattern
- The Judge Agent follows the standard AIConnex LLM pattern: primary LLM call via `get_llm()`, strict Pydantic response validation, and a deterministic fallback (`"qualitative_unavailable"`) on network/API failure.

### 5. Independent Evaluator Fail-Soft Logic
- The Selector Agent functions independently of the Judge Agent. If LLM qualitative evaluation fails or is disabled, Selector selects the winning model using Scorer Agent hard mathematical metrics ($R^2$, RMSE, MAE, MAPE) alone.

### 6. Single-Owner Drift Monitoring Boundary
- Node 9 (`9_deploy_monitor`) strictly owns production Population Stability Index (PSI) and feature drift detection on live REST payloads (`:8001`). Scout Agent acts as a downstream consumer of Node 9 drift alerts.

### 7. Local-First MLflow Tracking URI (`./mlruns`)
- MLflow experiment tracking uses local file store persistence at `./mlruns` (zero external server dependencies), matching the offline local-first design of mem0/Qdrant (`./.mem0_qdrant`).

### 8. Empirical DAG & Recipe Inventory Verification
- All multi-candidate routing logic dynamically inspects actual on-disk counts in `dag_conditions_mapping.json` (1,993 DAG specifications) and `aic/3_recipe_orchestrator/recipe/` (6,760 pre-compiled stage JSON recipes) at runtime.

### 9. Empirical Test-Driven Zero-Regression Verification
- Zero-regression is verified empirically by running full microservice regression test suites (`pytest tests/`) pre-implementation and post-implementation, confirming zero test failures.

---

*Document Version: v3.1 (Master Final Architecture - Guardrails Locked)*  
*Authoritative Status: APPROVED & LOCKED FOR PHASE 5C EXECUTION*
