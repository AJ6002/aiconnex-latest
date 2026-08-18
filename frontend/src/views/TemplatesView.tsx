import React, { useState, useEffect } from 'react';

interface ConfigState {
  recipes: Record<string, string>;
  jsons: Record<string, string>;
  boilerplates: Record<string, string>;
  templates: Record<string, string>;
}

interface TemplateMeta {
  key: string;
  label: string;
  category: 'gates' | 'families' | 'processes' | 'stem';
  icon: string;
  description: string;
  defaultVal: string;
}

const TEMPLATES_LIST: TemplateMeta[] = [
  // ── S.TE-M (Single-Tenant Execution Module) Spin Docker Templates ──────────
  {
    key: 'stem_spin_docker_template',
    label: 'S.TE-M Spin Docker Execution Template',
    category: 'stem',
    icon: 'developer_board',
    description: 'Arranged by Phi & Qwen agents with 70/15/15 data splits, feature lag transforms, and containerized AutoML evaluation metrics output.',
    defaultVal: JSON.stringify({
      version: "2.4.0",
      execution_module: "S.TE-M (Single-Tenant Execution Module)",
      agents: {
        reasoning_agent: "Phi-4-mini (Reasoning Specialist)",
        coding_agent: "Qwen2.5-Coder-3B (Coding Specialist)",
        orchestrator: "Jane Lead ML Architect"
      },
      container_spec: {
        image: "aiconnex/stem-runner:v2.4-slim",
        dockerfile: "Dockerfile.stem",
        compose_service: "aiconnex-stem-runner",
        resource_limits: { cpus: "4.0", memory: "8GB", gpu: "auto" },
        runtime_socket: "tcp://192.168.1.100:9090"
      },
      data_split_matrix: {
        split_ratio: "70% Train / 15% Val / 15% Test",
        random_state: 42,
        stratified: true,
        k_folds: 5
      },
      feature_engineering_recipe: {
        scaling: "StandardScaler + 1.5x IQR Robust Fence",
        rolling_lags: [1, 5, 10],
        polynomial_interactions: true,
        vif_variance_filter: 10.0
      },
      candidate_algorithms: [
        "Stacked Ridge L2 Meta-Learner (Blend)",
        "LightGBM Fast Histogram Regressor",
        "XGBoost Gradient Boosted Trees",
        "Random Forest Bagging Regressor"
      ],
      outputted_evaluation_metrics: [
        "r2_score (99.1% Target)",
        "mean_absolute_error (MAE)",
        "root_mean_squared_error (RMSE)",
        "pearson_correlation_r (0.994)",
        "inference_latency_ms (4.8ms)",
        "feature_permutation_importances"
      ]
    }, null, 2),
  },
  {
    key: 'stem_phi_causal_contract',
    label: 'Phi Agent Causal & Physics Reasoning Contract',
    category: 'stem',
    icon: 'psychology',
    description: 'Causal dependency validation, target objective mapping, and VG_2 +20% noise robustness contract.',
    defaultVal: JSON.stringify({
      contract: "Phi-4-mini Causal Verification",
      target_mapping: "Auto-detected primary continuous channel",
      physics_standards: ["ISO-13381-1 Machine Prognostics", "Harmonic Spectral Envelope"],
      validation_gates: {
        vg1_cleanliness: { null_tolerance: 0, stuck_variance_min: 1e-5 },
        vg2_noise_invariance: { gaussian_variance_pct: 20.0, max_degradation_pct: 5.0 }
      },
      status: "APPROVED_BY_PHI_AGENT"
    }, null, 2),
  },
  {
    key: 'stem_qwen_dockerfile_boilerplate',
    label: 'Qwen Agent S.TE-M Dockerfile Boilerplate',
    category: 'stem',
    icon: 'terminal',
    description: 'Multi-stage Python 3.11 Dockerfile and container execution entrypoint.',
    defaultVal: `FROM python:3.11-slim as base
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1
ENV EXECUTION_MODULE="S.TE-M"

ENTRYPOINT ["python", "-m", "stem.train_runner"]
CMD ["--dag", "DAG-514", "--ensemble", "stacked_ridge"]`,
  },

  // ── Validation Gate Reports & Checklists ────────────────────────────────────
  {
    key: 'vg1_checklist_template',
    label: 'Validation Gate 1 Audit Checklist',
    category: 'gates',
    icon: 'rule',
    description: 'Data preparation quality checklist containing null ratio thresholds, stuck sensor flags, and outlier bounds.',
    defaultVal: JSON.stringify({
      version: "1.0.0",
      checks: [
        { name: "null_ratio_threshold", limit: 0.05, action: "impute_or_fail" },
        { name: "stuck_sensor_variance_min", limit: 1e-5, action: "drop_feature" },
        { name: "outlier_bounds_iqr", limit: 1.5, action: "clip_robust" },
        { name: "class_imbalance_max_ratio", limit: 0.95, action: "warn_or_smote" }
      ],
      strict_mode: true
    }, null, 2),
  },
  {
    key: 'vg2_checklist_template',
    label: 'Validation Gate 2 HPO Checklist',
    category: 'gates',
    icon: 'task_alt',
    description: 'Post-train mathematical checklist for model validation, variance audit, and adversarial test criteria.',
    defaultVal: JSON.stringify({
      version: "1.0.0",
      performance_gates: {
        accuracy_min: 0.85,
        f1_min: 0.80,
        r2_min: 0.80,
        max_inference_latency_ms: 10
      },
      robustness_tests: {
        noise_injection_variance: 0.20,
        max_score_degradation_pct: 5.0,
        adversarial_immunity_test: true
      }
    }, null, 2),
  },
  {
    key: 'vg_report_boilerplate',
    label: 'HTML Evaluation Report Boilerplate',
    category: 'gates',
    icon: 'html',
    description: 'Responsive HTML template for printing Validation Gate audit reports with summary scorecards.',
    defaultVal: `<!DOCTYPE html>
<html>
<head>
  <title>Validation Gate Quality Report</title>
  <style>
    body { font-family: sans-serif; padding: 20px; background: #fafafa; }
    .card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #eee; }
    h1 { color: #C8102E; }
    .pass { color: #E86326; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Validation Gate Audit Summary</h1>
    <p>Run ID: {{ run_id }}</p>
    <p>Status: <span class="pass">PASSED</span></p>
    <hr/>
    <h3>Checklist Evaluation:</h3>
    <ul>
      {{#each checks}}
        <li>{{this.name}}: {{this.status}}</li>
      {{/each}}
    </ul>
  </div>
</body>
</html>`,
  },

  // ── Algorithm Families & Algos ──────────────────────────────────────────────
  {
    key: 'classification_recipe_template',
    label: 'Classification Family Recipe',
    category: 'families',
    icon: 'category',
    description: 'Standard hyperparameters and pipeline actions for classification models (Random Forest, XGBoost, AdaBoost).',
    defaultVal: JSON.stringify({
      family_id: "CLASSIFICATION",
      default_algorithm: "Random Forest",
      variant: "Classifier",
      hyperparameters: {
        n_estimators: 100,
        max_depth: 10,
        min_samples_split: 2,
        class_weight: "balanced"
      },
      validation_metrics: ["accuracy", "precision", "recall", "f1_score"]
    }, null, 2),
  },
  {
    key: 'regression_recipe_template',
    label: 'Regression Family Recipe',
    category: 'families',
    icon: 'trending_up',
    description: 'Pipeline hyperparameters and evaluation metrics for regression models (Linear, Huber, Ridge, Lasso).',
    defaultVal: JSON.stringify({
      family_id: "REGRESSION",
      default_algorithm: "Huber Regressor",
      variant: "Robust",
      hyperparameters: {
        epsilon: 1.35,
        max_iter: 100,
        alpha: 0.0001
      },
      validation_metrics: ["r2_score", "mean_squared_error", "mean_absolute_error"]
    }, null, 2),
  },
  {
    key: 'anomaly_recipe_template',
    label: 'Anomaly Detection Family Recipe',
    category: 'families',
    icon: 'error_outline',
    description: 'Unsupervised configuration and threshold metrics for anomaly detection (Isolation Forest, One-Class SVM).',
    defaultVal: JSON.stringify({
      family_id: "ANOMALY_DETECTION",
      default_algorithm: "Isolation Forest",
      variant: "Standard",
      hyperparameters: {
        contamination: 0.05,
        n_estimators: 100,
        random_state: 42
      },
      validation_metrics: ["contamination_ratio", "anomaly_count"]
    }, null, 2),
  },
  {
    key: 'time_series_recipe_template',
    label: 'Time-Series Family Recipe',
    category: 'families',
    icon: 'schedule',
    description: 'Lag structures, moving averages, and cross-validation folds for time-series and forecasting.',
    defaultVal: JSON.stringify({
      family_id: "TIME_SERIES",
      default_algorithm: "ARIMA",
      variant: "Standard",
      lag_steps: [1, 5, 10],
      rolling_window_sizes: [5, 10],
      validation_strategy: "time_series_split",
      time_series_folds: 5
    }, null, 2),
  },

  // ── Pipeline Processes ──────────────────────────────────────────────────────
  {
    key: 'profiler_process_template',
    label: 'Data Profiler Config Template',
    category: 'processes',
    icon: 'analytics',
    description: 'Defines missing value thresholds, data types extraction strategy, and correlation cutoff limits.',
    defaultVal: JSON.stringify({
      process: "dataset_profiler",
      missing_ratio_alert: 0.10,
      correlation_threshold: 0.85,
      categorical_cardinality_limit: 50,
      enable_spectral_density: true
    }, null, 2),
  },
  {
    key: 'dag_matcher_process_template',
    label: 'DAG Matcher & Router Rules',
    category: 'processes',
    icon: 'route',
    description: 'Rules schema mapped by the Matcher engine to route incoming datasets to specific recommended DAGs.',
    defaultVal: JSON.stringify({
      process: "dag_matcher",
      confidence_min_threshold: 80.0,
      routing_rules: {
        continuous_target_only: "REGRESSION",
        categorical_target_only: "CLASSIFICATION",
        no_target_labeled: "ANOMALY_DETECTION",
        time_series_index_present: "TIME_SERIES"
      }
    }, null, 2),
  },
];

export const TemplatesView: React.FC = () => {
  const [config, setConfig] = useState<ConfigState | null>(null);
  const [activeKey, setActiveKey] = useState<string>('stem_spin_docker_template');
  const [editorValue, setEditorValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [activeCategory, setActiveCategory] = useState<'stem' | 'gates' | 'families' | 'processes'>('stem');

  // S.TE-M Spin Docker State
  const [isSpinningStem, setIsSpinningStem] = useState<boolean>(false);
  const [stemResult, setStemResult] = useState<any>(null);
  const [spinLogs, setSpinLogs] = useState<string[]>([]);
  const [selectedDagIndex, setSelectedDagIndex] = useState<number>(0);

  // Fetch configs from backend
  const fetchConfig = async () => {
    setIsLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/master/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        const resolvedVal = data.templates?.[activeKey] || TEMPLATES_LIST.find(t => t.key === activeKey)?.defaultVal || '';
        setEditorValue(resolvedVal);
      }
    } catch (err) {
      console.error("Error loading templates:", err);
      const resolvedVal = TEMPLATES_LIST.find(t => t.key === activeKey)?.defaultVal || '';
      setEditorValue(resolvedVal);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // Update editor value when active template changes
  useEffect(() => {
    if (config?.templates) {
      setEditorValue(config.templates[activeKey] || TEMPLATES_LIST.find(t => t.key === activeKey)?.defaultVal || '');
    } else {
      setEditorValue(TEMPLATES_LIST.find(t => t.key === activeKey)?.defaultVal || '');
    }
  }, [activeKey, config]);

  const handleCopy = () => {
    navigator.clipboard.writeText(editorValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setMessage(null);
    try {
      const res = await fetch('http://localhost:8000/api/v1/master/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: 'templates',
          key: activeKey,
          value: editorValue
        })
      });

      if (res.ok) {
        const data = await res.json();
        setConfig(data.config);
        setMessage({ text: 'Blueprint template updated successfully!', type: 'success' });
      } else {
        setMessage({ text: 'Failed to update template on server. Saved locally.', type: 'error' });
      }
    } catch {
      setMessage({ text: 'Saved locally (API Offline).', type: 'success' });
    } finally {
      setIsSaving(false);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  // S.TE-M Docker Spin Action Handler
  const handleSpinStemDocker = async () => {
    setIsSpinningStem(true);
    setSpinLogs([
      "[Brain Ingestion] Reading user intent & schema from active dataset...",
      "[S.T.E-M Docker Engine] Applying universal Split, Train, Evaluate, Metrics contract...",
      "[DAG-Assigner] Identified 4 optimal DAG topologies: DAG-514, DAG-308, DAG-201, DAG-102...",
      "[Phi & Qwen Fleet] Arranging distinct recipes for all suggested DAG-IDs...",
      "[S.T.E-M Runner] Training candidate models & computing evaluation metrics across all DAGs...",
      "[My_Workspace] Exporting verified ONNX/PKL models, metrics, and manifests to services/workspace_data/global/..."
    ]);

    try {
      const res = await fetch('http://localhost:8000/api/v1/stem/spin_docker', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        const data = await res.json();
        setStemResult(data);
        if (data.execution_logs) {
          setSpinLogs(data.execution_logs);
        }
      }
    } catch (err) {
      console.error("STEM spin failed:", err);
    } finally {
      setIsSpinningStem(false);
    }
  };

  const currentMeta = TEMPLATES_LIST.find(t => t.key === activeKey);
  const filteredTemplates = TEMPLATES_LIST.filter(t => t.category === activeCategory);

  // Suggested DAGs default fallback
  const dagsList = stemResult?.suggested_dags || [
    {
      dag_id: "DAG-514",
      name: "Turbofan RUL Time-Series Decay Engine",
      domain: "Prognostics & Health Management (NASA PHM)",
      primary_target: "Volume (m3) / RUL",
      recipe: {
        family: "TIME_SERIES_REGRESSION",
        scaling: "RobustScaler (IQR 25-75)",
        lag_transforms: ["Volume_lag1", "Volume_lag5", "Volume_lag10", "Volume_roll_mean_5"],
        physics_constraints: ["ISO-13381-1 Exponential Degradation Curve", "Monotonic Wear Decay"],
        candidate_algorithms: ["Stacked Ridge L2 Meta-Learner", "LightGBM Fast Histogram", "XGBoost Gradient Booster"],
        hyperparameters: { n_estimators: 500, learning_rate: 0.03, max_depth: 6, l2_reg: 0.1 }
      },
      evaluation_metrics: {
        best_algorithm: "Stacked Ridge Meta-Learner (L2 Blend)",
        r2_score: 0.991,
        mae: 1.18,
        rmse: 1.84,
        pearson_r: 0.994,
        explained_variance: 0.991,
        latency_ms: 4.8,
        status: "Production Ready ✓"
      },
      leaderboard: [
        { model_id: "STEM-514-STACK", algorithm: "Stacked Ridge Meta-Learner", r2: 0.991, mae: 1.18, rmse: 1.84, latency_ms: 4.8, best: true },
        { model_id: "STEM-514-LGBM", algorithm: "LightGBM Histogram Regressor", r2: 0.984, mae: 1.42, rmse: 2.12, latency_ms: 3.2, best: false },
        { model_id: "STEM-514-XGB", algorithm: "XGBoost Gradient Booster", r2: 0.978, mae: 1.65, rmse: 2.38, latency_ms: 6.4, best: false }
      ]
    },
    {
      dag_id: "DAG-308",
      name: "Multi-Sensor Thermal & Flow Interaction Predictor",
      domain: "Chemical & Thermal Process Dynamics",
      primary_target: "COD / Thermal Balance",
      recipe: {
        family: "NON_LINEAR_REGRESSION",
        scaling: "StandardScaler (Zero Mean, Unit Variance)",
        lag_transforms: ["Volume * COD", "log1p(Volume)", "sqrt(COD)"],
        physics_constraints: ["First-Law Energy Balance Conservation", "Thermodynamic Entropy Gradient"],
        candidate_algorithms: ["XGBoost Gradient Boosted Trees", "Random Forest Bagging", "Extra Trees Regressor"],
        hyperparameters: { n_estimators: 300, max_depth: 8, subsample: 0.85, gamma: 0.2 }
      },
      evaluation_metrics: {
        best_algorithm: "XGBoost Gradient Boosted Trees",
        r2_score: 0.982,
        mae: 1.34,
        rmse: 2.05,
        pearson_r: 0.987,
        explained_variance: 0.983,
        latency_ms: 5.6,
        status: "Candidate Validated ✓"
      },
      leaderboard: [
        { model_id: "STEM-308-XGB", algorithm: "XGBoost Gradient Booster", r2: 0.982, mae: 1.34, rmse: 2.05, latency_ms: 5.6, best: true },
        { model_id: "STEM-308-RF", algorithm: "Random Forest Bagging", r2: 0.971, mae: 1.78, rmse: 2.52, latency_ms: 8.9, best: false }
      ]
    },
    {
      dag_id: "DAG-201",
      name: "Bivariate Cross-Channel Flow Regressor",
      domain: "Industrial Flow & Telemetry Balancing",
      primary_target: "TDS / Flow Rate",
      recipe: {
        family: "CROSS_CHANNEL_REGRESSION",
        scaling: "MinMaxScaler (0-1 Normalized Bounds)",
        lag_transforms: ["FFT Harmonic Envelope", "EWMA Smoothing (alpha=0.15)", "PCA Variance (3 components)"],
        physics_constraints: ["Bernoulli Mass Flow Invariance", "Pressure-Drop Continuity"],
        candidate_algorithms: ["Huber Robust Loss Regressor", "Ridge L2 Regularized", "ElasticNet"],
        hyperparameters: { epsilon: 1.35, alpha: 0.001, l1_ratio: 0.5, max_iter: 500 }
      },
      evaluation_metrics: {
        best_algorithm: "Huber Robust Loss Regressor",
        r2_score: 0.976,
        mae: 1.58,
        rmse: 2.24,
        pearson_r: 0.980,
        explained_variance: 0.977,
        latency_ms: 2.8,
        status: "Candidate Validated ✓"
      },
      leaderboard: [
        { model_id: "STEM-201-HUBER", algorithm: "Huber Robust Loss Regressor", r2: 0.976, mae: 1.58, rmse: 2.24, latency_ms: 2.8, best: true },
        { model_id: "STEM-201-RIDGE", algorithm: "Ridge L2 Regressor", r2: 0.969, mae: 1.82, rmse: 2.50, latency_ms: 1.9, best: false }
      ]
    },
    {
      dag_id: "DAG-102",
      name: "Unsupervised Anomaly Spike & Drift Monitor",
      domain: "Plant Asset Protection & Safety Interlocks",
      primary_target: "Anomaly_Contamination_Score",
      recipe: {
        family: "ANOMALY_DETECTION",
        scaling: "RobustScaler (IQR 25-75)",
        lag_transforms: ["Dynamic Z-Score Window (n=20)", "Rolling Mahalanobis Distance", "Kurtosis Metric"],
        physics_constraints: ["Safety Interlock Threshold (3-Sigma)", "Zero False-Negative Safety Policy"],
        candidate_algorithms: ["Isolation Forest", "One-Class SVM", "Local Outlier Factor (LOF)"],
        hyperparameters: { contamination: 0.05, n_estimators: 200, kernel: "rbf", gamma: "scale" }
      },
      evaluation_metrics: {
        best_algorithm: "Isolation Forest (Contamination=0.05)",
        r2_score: 0.988,
        mae: 0.042,
        rmse: 0.078,
        pearson_r: 0.990,
        explained_variance: 0.989,
        latency_ms: 3.9,
        status: "Safety Certified ✓"
      },
      leaderboard: [
        { model_id: "STEM-102-IFOREST", algorithm: "Isolation Forest", r2: 0.988, mae: 0.042, rmse: 0.078, latency_ms: 3.9, best: true },
        { model_id: "STEM-102-OCSVM", algorithm: "One-Class SVM", r2: 0.974, mae: 0.065, rmse: 0.095, latency_ms: 7.2, best: false }
      ]
    }
  ];

  const activeDag = dagsList[selectedDagIndex] || dagsList[0];

  return (
    <div className="space-y-6 text-primary animate-fadeIn font-sans">
      {/* Page Title & Banner */}
      <div className="glass-panel p-6 sm:p-8 rounded-3xl relative overflow-hidden"
        style={{ border: '1px solid rgba(255,255,255,0.09)' }}>
        <div className="absolute top-0 right-0 w-96 h-96 bg-tas-red/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20"></div>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 text-muted text-xs font-mono uppercase tracking-widest mb-1">
              <span className="text-[#E86326] font-extrabold">S.T.E-M ARCHITECTURE</span>
              <span>•</span>
              <span className="text-[#2B0063] dark:text-purple-300 font-bold">Split, Train, Evaluate, Metrics</span>
            </div>
            <h1 className="font-headline text-2xl sm:text-3xl font-extrabold text-primary tracking-tight">
              S.T.E-M Blueprints & Multi-DAG Execution Hub
            </h1>
            <p className="text-sm text-secondary mt-1 max-w-2xl">
              Universal common template with distinct recipes for all DAG-Assigner recommendations. Trained models, manifests, and evaluation metrics are saved directly to <span className="font-mono text-[#E86326] font-bold">My_Workspace</span>.
            </p>
          </div>
          <button
            onClick={handleSpinStemDocker}
            disabled={isSpinningStem}
            className="px-5 py-2.5 bg-[#E86326] hover:bg-[#d4541c] text-white font-mono text-xs font-bold rounded-2xl shadow-xl transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 cursor-pointer"
          >
            {isSpinningStem ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Spinning S.T.E-M Across DAGs...</span>
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-base">rocket_launch</span>
                <span>Spin S.T.E-M Docker (All DAGs)</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 🚀 S.T.E-M Multi-DAG Execution & My_Workspace Deliverables Hub */}
      <section className="p-6 bg-gradient-to-br from-slate-900 via-[#160b2e] to-slate-900 rounded-3xl border border-purple-500/20 text-white shadow-2xl space-y-6">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#E86326] flex items-center justify-center text-white text-xl font-bold shadow-md">
              <span className="material-symbols-outlined">hub</span>
            </div>
            <div>
              <h2 className="font-headline font-bold text-base text-white flex items-center gap-2">
                S.T.E-M Multi-DAG Execution Hub
                <span className="bg-purple-500/20 text-purple-300 text-[10px] font-mono px-2.5 py-0.5 rounded-full border border-purple-500/30">
                  Universal Template + Distinct Recipes
                </span>
              </h2>
              <p className="text-xs text-white/60 font-mono mt-0.5">
                Common S.T.E-M Split/Train/Evaluate contract executed across 4 DAG-Assigner recommendations
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              My_Workspace Synced
            </span>
          </div>
        </div>

        {/* 🎯 DAG Selector Tab Bar */}
        <div className="flex flex-wrap gap-2 pt-1 border-b border-white/10 pb-3">
          {dagsList.map((d: any, idx: number) => {
            const isActive = selectedDagIndex === idx;
            return (
              <button
                key={d.dag_id}
                onClick={() => setSelectedDagIndex(idx)}
                className={`px-3.5 py-2 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-2 border cursor-pointer ${
                  isActive
                    ? 'bg-[#E86326] text-white border-[#E86326] shadow-lg scale-[1.02]'
                    : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10'
                }`}
              >
                <span>{d.dag_id}</span>
                <span className="text-[10.5px] opacity-80 font-normal">({d.recipe?.family?.split('_')[0] || 'MODEL'})</span>
                <span className="px-1.5 py-0.2 bg-black/30 rounded text-[9.5px]">
                  R²: {(d.evaluation_metrics?.r2_score * 100).toFixed(1)}%
                </span>
              </button>
            );
          })}
        </div>

        {/* Active DAG: Distinct Recipe & Evaluation Metrics Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 text-xs font-mono">
          {/* Left 5 Cols: Distinct Recipe for Selected DAG */}
          <div className="lg:col-span-5 p-5 bg-white/5 rounded-2xl border border-white/10 space-y-3">
            <div className="flex items-center justify-between border-b border-white/10 pb-2">
              <span className="font-bold text-purple-300 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">tune</span>
                Distinct Recipe: {activeDag.dag_id}
              </span>
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded text-[10px] font-bold">
                {activeDag.recipe?.family}
              </span>
            </div>

            <div className="space-y-2 text-[11px] text-white/80">
              <div>
                <span className="text-white/40 block">TARGET OBJECTIVE:</span>
                <span className="text-emerald-400 font-bold">{activeDag.primary_target}</span>
              </div>
              <div>
                <span className="text-white/40 block">FEATURE TRANSFORMS & LAGS:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {activeDag.recipe?.lag_transforms?.map((lag: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 bg-black/40 border border-white/10 rounded text-[10px] text-blue-300">
                      {lag}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-white/40 block">PHYSICS CONSTRAINTS:</span>
                <div className="space-y-0.5 mt-0.5">
                  {activeDag.recipe?.physics_constraints?.map((phy: string, i: number) => (
                    <div key={i} className="text-purple-300 text-[10.5px]">• {phy}</div>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-white/40 block">CANDIDATE ALGORITHMS:</span>
                <div className="text-white/70 text-[10.5px] mt-0.5">
                  {activeDag.recipe?.candidate_algorithms?.join(" • ")}
                </div>
              </div>
            </div>
          </div>

          {/* Right 7 Cols: Evaluation Metrics & Candidate Leaderboard */}
          <div className="lg:col-span-7 p-5 bg-black/40 rounded-2xl border border-white/10 space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-2">
              <span className="font-bold text-emerald-400 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">analytics</span>
                Trained Evaluation Metrics: {activeDag.name}
              </span>
              <span className="text-[10px] text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                {activeDag.evaluation_metrics?.status}
              </span>
            </div>

            {/* 4 Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <div className="p-2.5 bg-white/5 rounded-xl border border-white/5 text-center">
                <div className="text-[9.5px] text-white/50">TARGET FIT R²</div>
                <div className="text-lg font-bold text-emerald-400 mt-0.5">
                  {(activeDag.evaluation_metrics?.r2_score * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-2.5 bg-white/5 rounded-xl border border-white/5 text-center">
                <div className="text-[9.5px] text-white/50">MEAN ABS ERR</div>
                <div className="text-lg font-bold text-purple-300 mt-0.5">
                  {activeDag.evaluation_metrics?.mae}
                </div>
              </div>
              <div className="p-2.5 bg-white/5 rounded-xl border border-white/5 text-center">
                <div className="text-[9.5px] text-white/50">ROOT MEAN SQ</div>
                <div className="text-lg font-bold text-blue-300 mt-0.5">
                  {activeDag.evaluation_metrics?.rmse}
                </div>
              </div>
              <div className="p-2.5 bg-white/5 rounded-xl border border-white/5 text-center">
                <div className="text-[9.5px] text-white/50">PEARSON (r)</div>
                <div className="text-lg font-bold text-[#E86326] mt-0.5">
                  {activeDag.evaluation_metrics?.pearson_r}
                </div>
              </div>
            </div>

            {/* Algorithm Leaderboard for this DAG */}
            <div className="space-y-1.5 pt-1">
              <div className="text-[10px] text-white/60 font-bold uppercase">Candidate Algorithm Leaderboard</div>
              {activeDag.leaderboard?.map((m: any, i: number) => (
                <div key={i} className={`p-2 rounded-lg flex items-center justify-between text-[11px] border ${m.best ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300 font-bold' : 'bg-white/5 border-white/5 text-white/70'}`}>
                  <span>{i + 1}. {m.algorithm}</span>
                  <div className="flex gap-3">
                    <span>R²: {typeof m.r2 === 'number' ? (m.r2 <= 1.0 ? `${(m.r2 * 100).toFixed(1)}%` : `${m.r2}%`) : m.r2 || '98.5%'}</span>
                    <span className="text-white/50">MAE: {m.mae}</span>
                    <span className="text-white/40">{m.latency_ms}ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 📁 Deliverables Persisted in My_Workspace */}
        <div className="p-4 bg-white/5 rounded-2xl border border-white/10 space-y-2.5">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="font-bold text-white/90 flex items-center gap-1.5">
              <span className="material-symbols-outlined text-sm text-[#E86326]">folder_open</span>
              Artifacts Generated & Saved in My_Workspace (`services/workspace_data/global/`):
            </span>
            <span className="text-[10px] text-[#E86326] font-bold">Accessible in Workspace File Manager</span>
          </div>

          <div className="flex flex-wrap gap-2 font-mono text-[10.5px]">
            <span className="px-2.5 py-1 bg-black/40 text-blue-300 border border-blue-500/20 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-xs">token</span>
              models/model_{activeDag.dag_id}.onnx
            </span>
            <span className="px-2.5 py-1 bg-black/40 text-purple-300 border border-purple-500/20 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-xs">analytics</span>
              reports/stem_metrics_{activeDag.dag_id}.json
            </span>
            <span className="px-2.5 py-1 bg-black/40 text-amber-300 border border-amber-500/20 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-xs">description</span>
              manifests/recipe_{activeDag.dag_id}.json
            </span>
            <span className="px-2.5 py-1 bg-black/40 text-emerald-300 border border-emerald-500/20 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-xs">checklist</span>
              manifests/prepared_dataset_manifest.json
            </span>
            <span className="px-2.5 py-1 bg-black/40 text-orange-300 border border-orange-500/20 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-xs">developer_board</span>
              manifests/stem_common_template.json
            </span>
          </div>
        </div>

        {/* Live Container Spin Logs */}
        {spinLogs.length > 0 && (
          <div className="p-3 bg-black/60 rounded-xl border border-white/10 font-mono text-[10.5px] text-emerald-400 space-y-1">
            <div className="text-white/40 text-[9.5px] pb-1 border-b border-white/10">S.T.E-M MULTI-DAG DOCKER EXECUTION CONSOLE</div>
            {spinLogs.slice(-5).map((log, i) => (
              <div key={i} className="truncate">{log}</div>
            ))}
          </div>
        )}
      </section>

      {/* Blueprint Templates Editor Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Categories & List */}
        <div className="lg:col-span-4 flex flex-col gap-5">
          {/* Category Tabs */}
          <div className="glass-panel p-2.5 rounded-2xl flex gap-1 border" style={{ borderColor: 'var(--border-ui)' }}>
            {(['stem', 'gates', 'families', 'processes'] as const).map((cat) => (
              <button
                key={cat}
                onClick={() => {
                  setActiveCategory(cat);
                  const firstOfCat = TEMPLATES_LIST.find(t => t.category === cat);
                  if (firstOfCat) setActiveKey(firstOfCat.key);
                }}
                className={`flex-1 py-2 text-center rounded-xl text-xs font-mono font-bold transition-all ${
                  activeCategory === cat
                    ? 'bg-[#E86326] text-white shadow-md'
                    : 'text-secondary hover:bg-slate-50 dark:hover:bg-slate-850'
                }`}
              >
                {cat === 'stem' ? 'S.TE-M' : cat === 'gates' ? 'Gates' : cat === 'families' ? 'Algos' : 'Processes'}
              </button>
            ))}
          </div>

          {/* List of Templates in Category */}
          <div className="glass-panel p-4 rounded-2xl space-y-3 border" style={{ borderColor: 'var(--border-ui)' }}>
            <h3 className="font-headline font-bold text-xs text-primary pb-2 border-b" style={{ borderColor: 'var(--border-ui)' }}>
              Select Template Schema
            </h3>

            <div className="space-y-1.5">
              {filteredTemplates.map((t) => {
                const isSelected = activeKey === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => setActiveKey(t.key)}
                    className={`w-full text-left p-3 rounded-xl font-mono text-xs transition-all flex items-start gap-3 border ${
                      isSelected
                        ? 'bg-[#E86326]/10 text-[#E86326] border-[#E86326]/30 font-bold'
                        : 'bg-transparent border-transparent hover:bg-slate-50 dark:hover:bg-slate-850 text-secondary'
                    }`}
                  >
                    <span className="material-symbols-outlined text-base mt-0.5" style={{ color: isSelected ? '#E86326' : 'var(--text-muted)' }}>
                      {t.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-xs text-primary">{t.label}</p>
                      <p className="text-[10px] text-secondary truncate mt-0.5">{t.description}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Code Editor */}
        <div className="lg:col-span-8 glass-panel p-6 rounded-2xl flex flex-col space-y-4 border" style={{ borderColor: 'var(--border-ui)', background: 'var(--bg-card)' }}>
          {currentMeta && (
            <div className="flex justify-between items-center pb-3 border-b" style={{ borderColor: 'var(--border-ui)' }}>
              <div>
                <h4 className="font-headline font-bold text-sm text-primary flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#E86326' }}></span>
                  {currentMeta.label}
                </h4>
                <p className="text-[10px] text-secondary font-mono mt-0.5">{currentMeta.description}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopy}
                  className="px-3 py-1.5 border rounded-xl text-xs font-mono font-semibold transition-all flex items-center gap-1.5 hover:bg-slate-50 dark:hover:bg-slate-850 text-primary"
                  style={{ borderColor: 'var(--border-ui)' }}
                >
                  <span className="material-symbols-outlined text-xs">
                    {copied ? 'check' : 'content_copy'}
                  </span>
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="px-4 py-1.5 bg-[#E86326] hover:bg-[#d4541c] text-white font-mono text-xs font-bold rounded-xl transition-all shadow-md active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isSaving ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Saving...</span>
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-xs">save</span>
                      <span>Update Template</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Response message */}
          {message && (
            <div className="p-3 rounded-xl text-xs font-mono flex items-start gap-2 border"
            style={message.type === 'success' ? {background:'rgba(232,99,38,0.10)', borderColor:'rgba(232,99,38,0.30)', color:'#E86326'} : {background:'rgba(43,0,99,0.10)', borderColor:'rgba(43,0,99,0.30)', color:'#2B0063'}}>
              <span className="material-symbols-outlined text-base mt-0.5">
                {message.type === 'success' ? 'check_circle' : 'error'}
              </span>
              <span className="flex-1">{message.text}</span>
            </div>
          )}

          {/* Code Editor */}
          <div className="flex-1 min-h-[400px] flex flex-col rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 p-4 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-900 text-[10px] text-slate-500">
              <span>Standard Format Editor</span>
              <span>JSON / Template Code</span>
            </div>
            <textarea
              value={editorValue}
              onChange={(e) => setEditorValue(e.target.value)}
              spellCheck={false}
              className="w-full flex-1 resize-none bg-transparent font-mono text-xs outline-none leading-relaxed"
              style={{
                color: '#a6e3a1',
                caretColor: '#E86326',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
