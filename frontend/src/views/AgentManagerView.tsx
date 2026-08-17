import React, { useState, useEffect, useRef } from 'react';
import { ViewMode } from '../types';

export interface AgentConfig {
  id: string;
  name: string;
  avatar: string;
  title: string;
  role: string;
  endpoint: string;
  status: 'Active' | 'Inactive' | 'Maintenance';
  modelProvider: string;
  temperature: number;
  maxTokens: number;
  latencySlaMs: number;
  assignedPort: string;
  calledByPages: string[];
  systemPrompt: string;
  apiKeyMasked: string;
  totalCallsToday: number;
  successRate: number;
  tokenUsageTokens: number;
  ragDocsCount: number;
  vectorDbStatus: string;
  concurrencyLimit: number;
  replicas: number;
}

interface ApiTelemetryCall {
  id: string;
  timestamp: string;
  agentName: string;
  endpoint: string;
  targetNode: string;
  nodePort: string;
  taskDescription: string;
  latencyMs: number;
  status: '200 OK' | '201 Created' | '202 Queued';
  payloadSize: string;
}

interface NodeAgentMapping {
  nodeId: string;
  nodeName: string;
  port: string;
  primaryAgent: string;
  task: string;
  status: 'Healthy' | 'Active Traffic' | 'Idle';
  activeCalls: number;
}

interface AgentManagerViewProps {
  onSelectView?: (view: ViewMode) => void;
}

export const AgentManagerView: React.FC<AgentManagerViewProps> = ({ onSelectView }) => {
  const [agents, setAgents] = useState<AgentConfig[]>([
    {
      id: 'agent_qwen3_4b',
      name: 'PRIMARY (Qwen3-4B)',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=Qwen3Architect&backgroundColor=280B43',
      title: 'Primary / General MLOps Model',
      role: 'Autonomous Fleet Orchestration, Intent Mapping & DAG Topology Composition',
      endpoint: '/api/v1/tri_agent/execute',
      status: 'Active',
      modelProvider: 'Qwen3-4B-Instruct (Local GGUF)',
      temperature: 0.2,
      maxTokens: 4096,
      latencySlaMs: 45,
      assignedPort: ':8000',
      calledByPages: ['Hero Page', 'Data Explorer', 'DAG Orchestrator'],
      systemPrompt: 'You are Qwen 3-4B, Primary MLOps Orchestrator. Coordinate multi-agent tasks, compose DAG topologies (DAG-514 Turbofan RUL Engine), and map operational intent.',
      apiKeyMasked: 'local_gguf_models/qwen3-4b-instruct-q4_k_m.gguf',
      totalCallsToday: 2410,
      successRate: 100.0,
      tokenUsageTokens: 184500,
      ragDocsCount: 18,
      vectorDbStatus: 'SQLite Foreign Key DB (Connected)',
      concurrencyLimit: 16,
      replicas: 4,
    },
    {
      id: 'agent_phi4_mini',
      name: 'REASONING (Phi-4-mini)',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=Phi4MiniReasoning&backgroundColor=3C1053',
      title: 'Reasoning & Deep Logic Specialist',
      role: 'Physics Degradation Hypotheses, Causal Chain Verification & Multi-Step Fault Logic',
      endpoint: '/api/v1/physics/transform',
      status: 'Active',
      modelProvider: 'Phi-4-mini-Instruct (Local GGUF)',
      temperature: 0.1,
      maxTokens: 3072,
      latencySlaMs: 35,
      assignedPort: ':8000',
      calledByPages: ['Physics Gateway', 'Evaluator Studio', 'Fault Diagnostics'],
      systemPrompt: 'Perform rigorous causal logic analysis on multi-stage sensor metrics. Formulate degradation hypotheses and validate temporal causal chains.',
      apiKeyMasked: 'local_gguf_models/Phi-4-mini-instruct-Q4_K_M.gguf',
      totalCallsToday: 4210,
      successRate: 100.0,
      tokenUsageTokens: 218000,
      ragDocsCount: 15,
      vectorDbStatus: 'SQLite Foreign Key DB (Connected)',
      concurrencyLimit: 20,
      replicas: 4,
    },
    {
      id: 'agent_qwen2_5_3b',
      name: 'CODING & SQL (Qwen 2.5-Coder 3B)',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=Qwen3BCode&backgroundColor-[#E86326]',
      title: 'Coding & SQL Specialist',
      role: 'SQL Telemetry Aggregation Queries, Sliding Lag Matrices & AutoML Model Fitting',
      endpoint: '/api/v1/train_models',
      status: 'Active',
      modelProvider: 'Qwen2.5-Coder-3B-Instruct (Local GGUF)',
      temperature: 0.1,
      maxTokens: 2048,
      latencySlaMs: 28,
      assignedPort: ':8000',
      calledByPages: ['Model Explorer', 'ML Studio', 'Feature Engineer'],
      systemPrompt: 'Generate high-performance SQL sliding window queries, fit XGBoost/LightGBM ensembles, and construct the Sankey Flow matrix.',
      apiKeyMasked: 'local_gguf_models/qwen2.5-coder-3b-instruct-q4_k_m.gguf',
      totalCallsToday: 3820,
      successRate: 100.0,
      tokenUsageTokens: 294100,
      ragDocsCount: 12,
      vectorDbStatus: 'SQLite Foreign Key DB (Connected)',
      concurrencyLimit: 24,
      replicas: 6,
    },
    {
      id: 'agent_scout',
      name: 'ScoutCompilerAgent',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=ScoutCompiler&backgroundColor=1A0530',
      title: 'Node 1: Universal Compiler Agent',
      role: 'Unzips archives, resolves schemas, and merges sub-files into compiled datasets',
      endpoint: '/api/v1/compile',
      status: 'Active',
      modelProvider: 'Node Executor (Python DSA)',
      temperature: 0.0,
      maxTokens: 1024,
      latencySlaMs: 15,
      assignedPort: ':8000',
      calledByPages: ['Upload Controller', 'Compiler Studio'],
      systemPrompt: 'Inspect multi-sub-file CSV archives. Detect primary keys, resolve entity IDs, and compile target dataset.',
      apiKeyMasked: 'backend/unified_compiler.py',
      totalCallsToday: 12940,
      successRate: 100.0,
      tokenUsageTokens: 98000,
      ragDocsCount: 8,
      vectorDbStatus: 'SQLite DB (Connected)',
      concurrencyLimit: 20,
      replicas: 4,
    },
    {
      id: 'agent_profiler',
      name: 'DataQualityAgent',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=DataQuality&backgroundColor=FF6B35',
      title: 'Node 2: Data Quality & Profiler Agent',
      role: '4-layer statistical profiling, null waterfall, KS drift, and SHAP correlations',
      endpoint: '/api/v1/profile',
      status: 'Active',
      modelProvider: 'Node Executor (Python DSA)',
      temperature: 0.0,
      maxTokens: 1024,
      latencySlaMs: 18,
      assignedPort: ':8000',
      calledByPages: ['Data Explorer', 'Pre-Prepare Tab'],
      systemPrompt: 'Compute missing value ratios, skewness meters, feature correlations, and recommend MLOps DAG IDs.',
      apiKeyMasked: 'backend/profiler_service.py',
      totalCallsToday: 11200,
      successRate: 100.0,
      tokenUsageTokens: 85000,
      ragDocsCount: 15,
      vectorDbStatus: 'SQLite DB (Connected)',
      concurrencyLimit: 16,
      replicas: 4,
    },
    {
      id: 'agent_automl',
      name: 'AutoMLTrainerAgent',
      avatar: 'https://api.dicebear.com/7.x/bottts/svg?seed=AutoMLTrainer&backgroundColor=280B43',
      title: 'Node 4 & 5: AutoML & Model Ledger Agent',
      role: 'Competitive multi-model training across 5 algorithm families & Sankey matrix',
      endpoint: '/api/v1/train_models',
      status: 'Active',
      modelProvider: 'Node Executor (Scikit-Learn / NumPy)',
      temperature: 0.1,
      maxTokens: 2048,
      latencySlaMs: 40,
      assignedPort: ':8000',
      calledByPages: ['Model Explorer', 'ML Studio'],
      systemPrompt: 'Fit XGBoost, LightGBM, Transformer, Isolation Forest ensembles and rank models by intent match score.',
      apiKeyMasked: 'backend/automl_engine.py',
      totalCallsToday: 8940,
      successRate: 99.8,
      tokenUsageTokens: 310000,
      ragDocsCount: 24,
      vectorDbStatus: 'SQLite DB (Connected)',
      concurrencyLimit: 12,
      replicas: 3,
    },
  ]);

  const nodeMappings: NodeAgentMapping[] = [
    { nodeId: 'node_1', nodeName: 'Node 1: Dataset Profiler', port: ':8000', primaryAgent: 'VICTOR', task: 'Schema Ingestion & Primary Key Detection', status: 'Active Traffic', activeCalls: 124 },
    { nodeId: 'node_2', nodeName: 'Node 2: DAG Matcher', port: ':8001', primaryAgent: 'ALEXA', task: 'DAG Recipe Matching & Selection', status: 'Healthy', activeCalls: 86 },
    { nodeId: 'node_3', nodeName: 'Node 3: Recipe Orchestrator', port: ':8002', primaryAgent: 'JANE', task: 'Flowchart Pipeline Plan Compilation', status: 'Active Traffic', activeCalls: 210 },
    { nodeId: 'node_4', nodeName: 'Node 4: Data Prepare', port: ':8003', primaryAgent: 'VICTOR', task: 'Imputation & Time Axis Alignment', status: 'Healthy', activeCalls: 98 },
    { nodeId: 'node_5', nodeName: 'Node 5: Feature Engineering', port: ':8004', primaryAgent: 'MARCUS', task: 'Rolling Lag & FFT Feature Synthesis', status: 'Active Traffic', activeCalls: 312 },
    { nodeId: 'node_6', nodeName: 'Node 6: Validation Gate 1', port: ':8005', primaryAgent: 'ELENA', task: 'Zero Cartesian Guard & Variance Audit', status: 'Healthy', activeCalls: 45 },
    { nodeId: 'node_7', nodeName: 'Node 7: Train API', port: ':8006', primaryAgent: 'ALEXA', task: 'Parallel XGBoost/LSTM Model Training', status: 'Active Traffic', activeCalls: 178 },
    { nodeId: 'node_8', nodeName: 'Node 8: Validation Gate 2', port: ':8007', primaryAgent: 'ELENA', task: 'Advisory Gate Robustness Sanity Test', status: 'Healthy', activeCalls: 62 },
    { nodeId: 'node_9', nodeName: 'Node 9: Deploy API', port: ':8008', primaryAgent: 'DAVID', task: 'INT8 ONNX Containerization & REST Export', status: 'Active Traffic', activeCalls: 140 },
  ];

  // Initial Telemetry Call logs
  const [telemetryLogs, setTelemetryLogs] = useState<ApiTelemetryCall[]>([
    { id: 'call-101', timestamp: new Date().toLocaleTimeString(), agentName: 'VICTOR', endpoint: '/api/v1/agents/victor-ingest', targetNode: 'Node 1: Profiler', nodePort: ':8000', taskDescription: 'Extracted 5 telemetry tables & verified timestamp column unit_id', latencyMs: 18, status: '200 OK', payloadSize: '4.2 KB' },
    { id: 'call-102', timestamp: new Date(Date.now() - 1500).toLocaleTimeString(), agentName: 'JANE', endpoint: '/api/v1/agents/jane-copilot', targetNode: 'Node 3: Orchestrator', nodePort: ':8002', taskDescription: 'Synthesized user query context for Turbofan RUL forecasting', latencyMs: 24, status: '200 OK', payloadSize: '1.8 KB' },
    { id: 'call-103', timestamp: new Date(Date.now() - 3000).toLocaleTimeString(), agentName: 'MARCUS', endpoint: '/api/v1/agents/marcus-features', targetNode: 'Node 5: Feature Eng', nodePort: ':8004', taskDescription: 'Computed t-1..t-10 rolling lag derivatives without target leakage', latencyMs: 14, status: '200 OK', payloadSize: '12.6 KB' },
    { id: 'call-104', timestamp: new Date(Date.now() - 4500).toLocaleTimeString(), agentName: 'ELENA', endpoint: '/api/v1/agents/elena-hpo', targetNode: 'Node 7: Train API', nodePort: ':8006', taskDescription: 'Executed Optuna trial #14: learning_rate=0.035, max_depth=6', latencyMs: 145, status: '200 OK', payloadSize: '8.1 KB' },
  ]);

  const [isStreaming, setIsStreaming] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('agent_jane');
  const [isInspectModalOpen, setIsInspectModalOpen] = useState(false);
  const [activeInspectTab, setActiveInspectTab] = useState<'graphs' | 'knowledge' | 'builder' | 'scaling'>('graphs');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  // Live Prompt Test Sandbox State inside Inspect Modal
  const [sandboxPrompt, setSandboxPrompt] = useState('Analyze sensor_11 temperature drift and explain recipe decision.');
  const [sandboxResponse, setSandboxResponse] = useState<string | null>(null);
  const [isSandboxRunning, setIsSandboxRunning] = useState(false);

  // New Agent Registration Form
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentTitle, setNewAgentTitle] = useState('');
  const [newAgentRole, setNewAgentRole] = useState('');
  const [newAgentEndpoint, setNewAgentEndpoint] = useState('/api/v1/agents/custom-agent');
  const [newAgentProvider, setNewAgentProvider] = useState('Gemini 1.5 Pro (Industrial Mesh)');
  const [newAgentAvatar, setNewAgentAvatar] = useState('https://api.dicebear.com/7.x/bottts/svg?seed=CustomAgent&backgroundColor=280B43');

  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Streaming live API telemetry generator
  useEffect(() => {
    if (!isStreaming) return;

    const possibleTasks = [
      { agent: 'VICTOR', end: '/api/v1/agents/victor-ingest', node: 'Node 1: Profiler', port: ':8000', task: 'Verified snake_case columns and time_cycle index bounds', size: '3.4 KB' },
      { agent: 'ALEXA', end: '/api/v1/agents/alexa-automl', node: 'Node 2: DAG Matcher', port: ':8001', task: 'Matched sensor profile against DAG_514 XGBoost Pipeline', size: '2.1 KB' },
      { agent: 'JANE', end: '/api/v1/agents/jane-copilot', node: 'Node 3: Orchestrator', port: ':8002', task: 'Generated automated pipeline diagnostic for user session', size: '5.6 KB' },
      { agent: 'MARCUS', end: '/api/v1/agents/marcus-features', node: 'Node 5: Feature Eng', port: ':8004', task: 'Synthesized 27 rolling statistical features for SCADA stream', size: '14.2 KB' },
      { agent: 'ELENA', end: '/api/v1/agents/elena-hpo', node: 'Node 6: VG 1 Gate', port: ':8005', task: 'Executed zero row explosion sanity check on 21,705 sensor rows', size: '1.2 KB' },
      { agent: 'DAVID', end: '/api/v1/agents/david-onnx', node: 'Node 9: Deploy API', port: ':8008', task: 'Compiled INT8 quantized ONNX runtime binary payload', size: '48.9 KB' },
    ];

    const interval = setInterval(() => {
      const randomItem = possibleTasks[Math.floor(Math.random() * possibleTasks.length)];
      const newCall: ApiTelemetryCall = {
        id: `call-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        agentName: randomItem.agent,
        endpoint: randomItem.end,
        targetNode: randomItem.node,
        nodePort: randomItem.port,
        taskDescription: randomItem.task,
        latencyMs: Math.floor(12 + Math.random() * 45),
        status: '200 OK',
        payloadSize: randomItem.size,
      };

      setTelemetryLogs((prev) => [newCall, ...prev.slice(0, 24)]);
    }, 2800);

    return () => clearInterval(interval);
  }, [isStreaming]);

  const handleToggleStatus = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setAgents((prev) =>
      prev.map((agent) => {
        if (agent.id === id) {
          const nextStatus = agent.status === 'Active' ? 'Inactive' : 'Active';
          return { ...agent, status: nextStatus };
        }
        return agent;
      })
    );
  };

  const handleOpenInspect = (agentId: string) => {
    setSelectedAgentId(agentId);
    setSandboxResponse(null);
    setIsInspectModalOpen(true);
  };

  const handleRunSandboxTest = () => {
    if (!sandboxPrompt.trim()) return;
    setIsSandboxRunning(true);
    setSandboxResponse(null);

    setTimeout(() => {
      setIsSandboxRunning(false);
      setSandboxResponse(
        `🤖 [${selectedAgent.name} Response • SLA ${selectedAgent.latencySlaMs - 8}ms]\n\nBased on vector index retrieval (${selectedAgent.vectorDbStatus}):\n• Sensor 11 temperature drift (1.82°C/hr) triggers Node 4 IQR clipping.\n• Recommend applying Log-transform before training on XGBoost (DAG_514).\n• Vector Similarity Score: 98.4% match on CMAPSS Turbofan Spec.`
      );
    }, 900);
  };

  const handleCreateAgent = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAgentName.trim()) return;

    const newAgent: AgentConfig = {
      id: `agent_${Date.now()}`,
      name: newAgentName.toUpperCase(),
      avatar: newAgentAvatar,
      title: newAgentTitle || 'Custom Industrial AI Specialist',
      role: newAgentRole || 'Custom Pipeline Agent',
      endpoint: newAgentEndpoint,
      status: 'Active',
      modelProvider: newAgentProvider,
      temperature: 0.2,
      maxTokens: 2048,
      latencySlaMs: 120,
      assignedPort: ':8009',
      calledByPages: ['Custom Pipeline Pages'],
      systemPrompt: 'You are a custom industrial AI agent configured by the administrator for TAS AI-ConneX.',
      apiKeyMasked: `aic_live_sk_••••••••••••${Math.floor(1000 + Math.random() * 9000)}`,
      totalCallsToday: 0,
      successRate: 100.0,
      tokenUsageTokens: 0,
      ragDocsCount: 5,
      vectorDbStatus: 'ChromaDB Local Engine (Connected)',
      concurrencyLimit: 16,
      replicas: 2,
    };

    setAgents((prev) => [...prev, newAgent]);
    setSelectedAgentId(newAgent.id);
    setIsCreateModalOpen(false);
    setNewAgentName('');
    setNewAgentTitle('');
    setNewAgentRole('');
  };

  return (
    <div className="space-y-6 text-[#333333] dark:text-white animate-fadeIn pb-16">
      
      {/* Top Header Banner */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 glass-panel p-6 sm:p-8 rounded-3xl relative overflow-hidden border border-[#2B0063]/20 dark:border-white/20 bg-white/90 dark:bg-[#3C1053]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5 relative z-10">
          <div className="w-14 h-14 rounded-2xl bg-[#2B0063] flex items-center justify-center text-[#FF6B35] shadow-lg border border-[#FF6B35]/30">
            <span className="material-symbols-outlined text-3xl font-bold">supervisor_account</span>
          </div>
          <div>
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest mb-1 text-[#FF6B35] font-bold">
              <span>ADMINISTRATOR CONTROL SUITE</span>
              <span>•</span>
              <span>LIVE AGENT FLEET & INTERCEPT MATRIX</span>
            </div>
            <h1 className="font-headline text-2xl sm:text-3xl font-extrabold text-[#2B0063] dark:text-white tracking-tight flex items-center gap-3">
              <span>AI Agent Manager & Scaling Studio</span>
              <span className="px-3 py-0.5 bg-[#FF6B35]/20 text-[#FF6B35] border border-[#FF6B35]/40 rounded-full text-xs font-mono font-bold flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#FF6B35] animate-pulse"></span>
                <span>{agents.filter(a => a.status === 'Active').length} Active Agents</span>
              </span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3 relative z-10 shrink-0">
          <button
            onClick={() => setIsStreaming(!isStreaming)}
            className={`px-4 py-2.5 font-mono text-xs font-bold rounded-2xl transition-all flex items-center gap-2 border cursor-pointer ${
              isStreaming
                ? 'bg-[#2B0063] text-white border-[#FF6B35]'
                : 'bg-gray-200 dark:bg-slate-800 text-[#333333] dark:text-white border-transparent'
            }`}
          >
            <span className={`material-symbols-outlined text-base ${isStreaming ? 'text-[#FF6B35] animate-spin' : ''}`}>
              {isStreaming ? 'sync' : 'pause'}
            </span>
            <span>{isStreaming ? 'Pause Live Telemetry' : 'Resume Telemetry Stream'}</span>
          </button>

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-5 py-2.5 bg-[#FF6B35] hover:bg-[#E85520] text-white font-mono text-xs font-bold rounded-2xl transition-all flex items-center gap-2 shadow-md active:scale-95 cursor-pointer"
          >
            <span className="material-symbols-outlined text-base">add_circle</span>
            <span>Deploy New Agent</span>
          </button>
        </div>
      </div>

      {/* SECTION 1: AGENT FLEET PROFILES GRID (NAME, REAL HUMAN PHOTO, STATUS, METRICS) */}
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#FF6B35] text-xl font-bold">badge</span>
            <h2 className="font-headline font-bold text-lg text-[#2B0063] dark:text-white">
              Configured Agent Fleet ({agents.length} Profiles)
            </h2>
          </div>
          <span className="text-xs font-mono text-secondary">Click any Agent Profile Card to Build, Manage &amp; Scale</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => {
            const isActive = agent.status === 'Active';
            return (
              <div
                key={agent.id}
                onClick={() => handleOpenInspect(agent.id)}
                className={`glass-card p-6 rounded-3xl border transition-all cursor-pointer relative overflow-hidden group flex flex-col justify-between gap-5 hover:shadow-2xl hover:scale-[1.01] ${
                  isActive
                    ? 'border-gray-200 dark:border-white/15 bg-white dark:bg-[#3C1053]'
                    : 'border-gray-300 dark:border-white/5 bg-gray-50 dark:bg-[#2B0063]/30 opacity-75'
                }`}
              >
                {/* Accent top glowing line */}
                <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-[#FF6B35] via-[#FF8F5A] to-[#2B0063] opacity-80 group-hover:opacity-100 transition-opacity" />

                {/* Card Header: Profile Photo Avatar, Name, Title & Status */}
                <div className="flex items-start gap-4">
                  <div className="relative shrink-0">
                    <img
                      src={agent.avatar}
                      alt={agent.name}
                      className="w-16 h-16 rounded-2xl object-cover border-2 border-[#FF6B35]/40 shadow-md group-hover:scale-105 transition-transform"
                    />
                    <span
                      className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-white dark:border-[#3C1053] ${
                        isActive ? 'bg-[#FF6B35] animate-pulse' : 'bg-gray-400'
                      }`}
                      title={agent.status}
                    />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="font-headline font-extrabold text-xl text-[#2B0063] dark:text-white tracking-tight flex items-center gap-2 truncate">
                        <span>{agent.name}</span>
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#FF6B35]/15 text-[#FF6B35]">
                          {agent.assignedPort}
                        </span>
                      </h3>
                      <button
                        onClick={(e) => handleToggleStatus(agent.id, e)}
                        className={`text-[9px] font-mono font-bold px-2.5 py-1 rounded-full uppercase transition-colors shrink-0 ${
                          isActive ? 'bg-[#FF6B35] text-white' : 'bg-gray-300 dark:bg-slate-700 text-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {agent.status}
                      </button>
                    </div>

                    <p className="text-xs font-bold text-[#FF6B35] line-clamp-1 mt-0.5">{agent.title}</p>
                    <p className="text-[11px] text-secondary line-clamp-2 mt-1 font-mono leading-tight">{agent.role}</p>
                  </div>
                </div>

                {/* Performance KPI Pills */}
                <div className="grid grid-cols-3 gap-2 py-2 border-y border-gray-100 dark:border-white/10 text-center font-mono">
                  <div className="p-2 bg-[#F7F7F7] dark:bg-[#2B0063]/60 rounded-xl">
                    <span className="text-[9px] text-muted uppercase block">SLA Latency</span>
                    <span className="text-xs font-extrabold text-[#FF6B35]">{agent.latencySlaMs}ms</span>
                  </div>
                  <div className="p-2 bg-[#F7F7F7] dark:bg-[#2B0063]/60 rounded-xl">
                    <span className="text-[9px] text-muted uppercase block">Success Rate</span>
                    <span className="text-xs font-extrabold text-[#FF6B35]">{agent.successRate}%</span>
                  </div>
                  <div className="p-2 bg-[#F7F7F7] dark:bg-[#2B0063]/60 rounded-xl">
                    <span className="text-[9px] text-muted uppercase block">Calls Today</span>
                    <span className="text-xs font-extrabold text-primary">{(agent.totalCallsToday / 1000).toFixed(1)}k</span>
                  </div>
                </div>

                {/* Card Footer: Model Provider & Action CTA */}
                <div className="flex items-center justify-between text-xs gap-2 pt-2 border-t border-gray-100 dark:border-white/10">
                  <span className="text-[10px] font-mono text-muted truncate max-w-[140px]">
                    🧠 {agent.modelProvider}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        fetch('http://localhost:8000/api/v1/tri_agent/execute', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ file_name: 'diagnostic_test.csv' }),
                        })
                          .then((res) => res.json())
                          .then((data) => {
                            const newLog: ApiTelemetryCall = {
                              id: `call-${Date.now()}`,
                              timestamp: new Date().toLocaleTimeString(),
                              agentName: agent.name.split(' ')[0],
                              endpoint: agent.endpoint,
                              targetNode: agent.title,
                              nodePort: agent.assignedPort,
                              taskDescription: `Executed live diagnostic test on model ${agent.modelProvider}`,
                              latencyMs: Math.floor(Math.random() * 15) + 12,
                              status: '200 OK',
                              payloadSize: '2.4 KB',
                            };
                            setTelemetryLogs((prev) => [newLog, ...prev]);
                          })
                          .catch(() => {});
                      }}
                      className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-mono text-[10px] font-bold rounded-xl transition-all shadow-sm flex items-center gap-1 cursor-pointer"
                    >
                      <span>🧪 Test Agent</span>
                    </button>
                    <button className="px-2.5 py-1 bg-[#2B0063] hover:bg-[#FF6B35] text-white font-mono text-[10px] font-bold rounded-xl transition-all shadow-sm flex items-center gap-1 cursor-pointer">
                      <span>Manage</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 2: LIVE AGENT API TELEMETRY TERMINAL & TOPOLOGY MATRIX */}
      <div className="glass-card p-6 space-y-4 bg-white dark:bg-[#3C1053] border border-gray-200 dark:border-white/10 rounded-3xl shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-gray-200 dark:border-white/10">
          <div className="flex items-center gap-2.5">
            <span className="material-symbols-outlined text-[#FF6B35] text-xl font-bold">terminal</span>
            <h2 className="font-headline font-bold text-base text-[#2B0063] dark:text-white">
              Live Agent API Intercept Terminal (Real-Time API Calls Across 9 Nodes)
            </h2>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="flex items-center gap-1.5 text-[#FF6B35] font-bold">
              <span className="w-2 h-2 rounded-full bg-[#FF6B35] animate-ping"></span>
              <span>STREAMING WEBSOCKET ACTIVE</span>
            </span>
            <button
              onClick={() => setTelemetryLogs([])}
              className="px-2.5 py-1 bg-gray-100 dark:bg-[#2B0063] hover:bg-gray-200 text-xs font-bold rounded-lg border border-gray-300 dark:border-white/20"
            >
              Clear Logs
            </button>
          </div>
        </div>

        {/* Streaming Logs Terminal Table */}
        <div className="bg-[#1A0530] text-white p-4 rounded-2xl font-mono text-xs overflow-x-auto shadow-inner space-y-2 border border-[#FF6B35]/30 max-h-52 overflow-y-auto">
          {telemetryLogs.length === 0 ? (
            <div className="text-center py-6 text-white/50">No API call telemetry logged. Stream is active...</div>
          ) : (
            telemetryLogs.map((log) => (
              <div key={log.id} className="flex items-start sm:items-center justify-between gap-4 py-1.5 border-b border-white/10 hover:bg-white/5 px-2 rounded-lg transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-[#FF6B35] font-bold text-[11px] whitespace-nowrap">[{log.timestamp}]</span>
                  <span className="px-2 py-0.5 bg-[#FF6B35]/20 text-[#FF6B35] border border-[#FF6B35]/40 rounded text-[10px] font-bold whitespace-nowrap">
                    {log.agentName}
                  </span>
                  <span className="material-symbols-outlined text-xs text-white/40">arrow_right_alt</span>
                  <span className="text-white font-bold whitespace-nowrap">{log.targetNode} ({log.nodePort})</span>
                  <span className="text-white/60 text-[11px] truncate hidden md:inline">{log.taskDescription}</span>
                </div>
                <div className="flex items-center gap-3 text-[11px] shrink-0">
                  <span className="text-white/40">{log.payloadSize}</span>
                  <span className="text-[#FF6B35] font-bold">{log.latencyMs}ms</span>
                  <span className="px-1.5 py-0.5 bg-[#FF6B35]/20 text-[#FF6B35] rounded text-[10px] font-bold">
                    {log.status}
                  </span>
                </div>
              </div>
            ))
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>

      {/* SECTION 3: 9 MICROSERVICE NODE <-> AGENT INTERCEPT MATRIX */}
      <div className="glass-card p-6 space-y-4 bg-white dark:bg-[#3C1053] border border-gray-200 dark:border-white/10 rounded-3xl shadow-xl">
        <div className="flex justify-between items-center pb-3 border-b border-gray-200 dark:border-white/10">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#FF6B35] text-xl font-bold">hub</span>
            <h2 className="font-headline font-bold text-base text-[#2B0063] dark:text-white">
              9-Node Microservice API Intercept Matrix (Ports :8000–:8008)
            </h2>
          </div>
          <span className="text-xs font-mono font-bold text-[#FF6B35]">
            All 9 Microservices Assigned Primary Agent
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-3 gap-4">
          {nodeMappings.map((node) => (
            <div
              key={node.nodeId}
              className="p-4 rounded-2xl border border-gray-200 dark:border-white/10 bg-[#F7F7F7] dark:bg-[#2B0063]/50 hover:border-[#FF6B35] transition-all space-y-2.5 relative group"
            >
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-mono font-bold text-[#FF6B35] px-2 py-0.5 bg-[#FF6B35]/10 rounded-md">
                  {node.port}
                </span>
                <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-[#FF6B35]">
                  <span className="w-2 h-2 rounded-full bg-[#FF6B35] animate-pulse"></span>
                  {node.activeCalls} req/min
                </span>
              </div>

              <h3 className="font-bold text-xs text-[#2B0063] dark:text-white font-mono">{node.nodeName}</h3>
              
              <div className="p-2.5 bg-white dark:bg-[#2B0063] rounded-xl border border-gray-200 dark:border-white/10 text-[11px] font-mono space-y-1">
                <p className="text-secondary text-[10px]">ASSIGNED AGENT:</p>
                <p className="font-extrabold text-[#FF6B35]">{node.primaryAgent}</p>
                <p className="text-[10px] text-muted mt-1 line-clamp-1">{node.task}</p>
              </div>

              <button
                onClick={() => {
                  alert(`Dispatched test intercept API request to ${node.nodeName} (${node.port}) via Agent ${node.primaryAgent}`);
                }}
                className="w-full py-1.5 bg-[#2B0063] hover:bg-[#FF6B35] text-white text-[10px] font-mono font-bold rounded-xl transition-all shadow-sm flex items-center justify-center gap-1"
              >
                <span className="material-symbols-outlined text-xs text-white">send</span>
                <span>Test Node Intercept</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* MODAL: DEEP AGENT INSPECTION, CONFIGURATION & SCALING SUITE */}
      {isInspectModalOpen && selectedAgent && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto animate-fadeIn">
          <div className="bg-white dark:bg-[#3C1053] border border-gray-200 dark:border-white/20 rounded-3xl max-w-5xl w-full max-h-[92vh] overflow-y-auto shadow-2xl flex flex-col my-auto">
            
            {/* Modal Header */}
            <div className="p-6 bg-[#2B0063] text-white rounded-t-3xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-white/10">
              <div className="flex items-center gap-4">
                <img
                  src={selectedAgent.avatar}
                  alt={selectedAgent.name}
                  className="w-16 h-16 rounded-2xl object-cover border-2 border-[#FF6B35]"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-headline font-extrabold text-2xl tracking-tight text-white">{selectedAgent.name}</h2>
                    <span className="px-2.5 py-0.5 bg-[#FF6B35] text-white text-[10px] font-mono font-bold rounded-full">
                      {selectedAgent.assignedPort}
                    </span>
                    <span className={`px-2.5 py-0.5 text-[10px] font-mono font-bold rounded-full ${
                      selectedAgent.status === 'Active' ? 'bg-[#FF6B35]/20 text-[#FF6B35] border border-[#FF6B35]/40' : 'bg-gray-600 text-gray-200'
                    }`}>
                      {selectedAgent.status}
                    </span>
                  </div>
                  <p className="text-xs font-bold text-[#FF6B35] mt-0.5">{selectedAgent.title}</p>
                  <p className="text-[11px] text-white/70 font-mono mt-0.5">{selectedAgent.endpoint}</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={(e) => handleToggleStatus(selectedAgent.id, e)}
                  className={`px-4 py-2 font-mono text-xs font-bold rounded-xl shadow-sm transition-all ${
                    selectedAgent.status === 'Active' ? 'bg-[#FF6B35] text-white hover:bg-[#E85520]' : 'bg-gray-700 text-white'
                  }`}
                >
                  {selectedAgent.status === 'Active' ? 'Deactivate Agent' : 'Activate Agent'}
                </button>
                <button
                  onClick={() => setIsInspectModalOpen(false)}
                  className="w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center font-bold text-base transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal Navigation Tabs */}
            <div className="flex border-b border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-[#1A0530] px-6">
              {[
                { id: 'graphs', label: 'Telemetry & Graphs', icon: 'monitoring' },
                { id: 'knowledge', label: 'Knowledge Base & RAG', icon: 'menu_book' },
                { id: 'builder', label: 'Prompt & Model Studio', icon: 'tune' },
                { id: 'scaling', label: 'Scaling & Replicas', icon: 'hub' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveInspectTab(tab.id as any)}
                  className={`px-5 py-3 font-mono text-xs font-bold flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
                    activeInspectTab === tab.id
                      ? 'border-[#FF6B35] text-[#FF6B35] bg-white dark:bg-[#3C1053]'
                      : 'border-transparent text-secondary hover:text-primary'
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">{tab.icon}</span>
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            {/* Modal Body Content */}
            <div className="p-6 space-y-6 flex-1">
              
              {/* TAB 1: TELEMETRY & GRAPHS */}
              {activeInspectTab === 'graphs' && (
                <div className="space-y-6 animate-fadeIn">
                  {/* KPI Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono">
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10">
                      <span className="text-[10px] text-muted uppercase block font-bold">Total Tokens Processed</span>
                      <span className="text-xl font-extrabold text-[#FF6B35]">{(selectedAgent.tokenUsageTokens / 1000).toFixed(1)}k</span>
                      <span className="text-[9px] text-secondary block mt-1">Prompt: 68% | Completion: 32%</span>
                    </div>
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10">
                      <span className="text-[10px] text-muted uppercase block font-bold">Target SLA Latency</span>
                      <span className="text-xl font-extrabold text-[#FF6B35]">{selectedAgent.latencySlaMs}ms</span>
                      <span className="text-[9px] text-secondary block mt-1">Actual Avg: {selectedAgent.latencySlaMs - 14}ms</span>
                    </div>
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10">
                      <span className="text-[10px] text-muted uppercase block font-bold">Task Accuracy Score</span>
                      <span className="text-xl font-extrabold text-[#FF6B35]">{selectedAgent.successRate}%</span>
                      <span className="text-[9px] text-secondary block mt-1">Pass Rate over 10k calls</span>
                    </div>
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10">
                      <span className="text-[10px] text-muted uppercase block font-bold">Calls Processed Today</span>
                      <span className="text-xl font-extrabold text-primary">{(selectedAgent.totalCallsToday).toLocaleString()}</span>
                      <span className="text-[9px] text-secondary block mt-1">Peak: 42 req/sec</span>
                    </div>
                  </div>

                  {/* SVG Latency & Token Usage Telemetry Trend Chart */}
                  <div className="p-5 glass-card rounded-2xl border border-gray-200 dark:border-white/10 space-y-3">
                    <div className="flex justify-between items-center font-mono">
                      <h4 className="font-bold text-xs text-[#2B0063] dark:text-white flex items-center gap-2">
                        <span className="material-symbols-outlined text-[#FF6B35]">show_chart</span>
                        <span>Agent Live Response SLA Latency Trend (ms over past 60 mins)</span>
                      </h4>
                      <span className="text-[10px] text-[#FF6B35] font-bold">SLA Target: &lt;{selectedAgent.latencySlaMs}ms</span>
                    </div>

                    <div className="h-40 w-full bg-[#1A0530] rounded-xl p-3 relative overflow-hidden border border-[#FF6B35]/30">
                      <svg className="w-full h-full" viewBox="0 0 500 120" preserveAspectRatio="none">
                        <line x1="0" y1="30" x2="500" y2="30" stroke="#FF6B35" strokeWidth="1" strokeDasharray="4" opacity="0.6" />
                        <text x="440" y="24" fill="#FF6B35" fontSize="9" fontWeight="bold" fontFamily="JetBrains Mono">SLA MAX ({selectedAgent.latencySlaMs}ms)</text>
                        <path
                          d="M 0 90 Q 50 60, 100 70 T 200 40 T 300 65 T 400 50 T 500 45"
                          fill="none"
                          stroke="#FF6B35"
                          strokeWidth="2.5"
                        />
                        <circle cx="500" cy="45" r="4" fill="#FF6B35" className="animate-ping" />
                      </svg>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: KNOWLEDGE BASE & VECTOR RAG MANAGER */}
              {activeInspectTab === 'knowledge' && (
                <div className="space-y-6 animate-fadeIn">
                  <div className="p-4 bg-[#FF6B35]/10 border border-[#FF6B35]/30 rounded-2xl flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-[#FF6B35]">database</span>
                      <div>
                        <p className="font-bold text-[#2B0063] dark:text-white">Active Vector Index: {selectedAgent.vectorDbStatus}</p>
                        <p className="text-[10px] text-secondary mt-0.5">{selectedAgent.ragDocsCount} Managed Knowledge Documents Indexing Active</p>
                      </div>
                    </div>
                    <button
                      onClick={() => alert(`Synchronized vector index for ${selectedAgent.name}. All ${selectedAgent.ragDocsCount} documents re-embedded.`)}
                      className="px-3.5 py-1.5 bg-[#2B0063] text-white hover:bg-[#FF6B35] font-bold rounded-xl transition-colors"
                    >
                      Sync Embeddings
                    </button>
                  </div>

                  {/* Document Inventory */}
                  <div className="space-y-3">
                    <h4 className="font-mono font-bold text-xs text-[#2B0063] dark:text-white uppercase tracking-wider">
                      Indexed Knowledge Documents ({selectedAgent.ragDocsCount} Files)
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-xs">
                      {[
                        { title: 'NASA_CMAPSS_Turbofan_Spec.pdf', chunks: '240 chunks', similarity: '98.4%', size: '4.2 MB' },
                        { title: 'OPC_UA_Telemetry_Standard_2025.pdf', chunks: '180 chunks', similarity: '95.1%', size: '3.1 MB' },
                        { title: 'VG1_Zero_Leakage_Guardrails.md', chunks: '45 chunks', similarity: '99.2%', size: '512 KB' },
                        { title: 'Industrial_Sensor_Fault_Ontology.json', chunks: '310 chunks', similarity: '96.8%', size: '8.4 MB' },
                      ].map((doc, idx) => (
                        <div key={idx} className="p-3 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-xl border border-gray-200 dark:border-white/10 flex items-center justify-between">
                          <div>
                            <p className="font-bold text-primary truncate max-w-[200px]">{doc.title}</p>
                            <span className="text-[10px] text-muted">{doc.chunks} • {doc.size}</span>
                          </div>
                          <span className="text-[10px] font-bold text-[#FF6B35] bg-[#FF6B35]/10 px-2 py-0.5 rounded">
                            {doc.similarity} Match
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: PROMPT & MODEL STUDIO */}
              {activeInspectTab === 'builder' && (
                <div className="space-y-6 animate-fadeIn">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs">
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10 space-y-2">
                      <label className="font-bold text-muted uppercase block">Model Provider Backend</label>
                      <select
                        value={selectedAgent.modelProvider}
                        onChange={(e) => {
                          const val = e.target.value;
                          setAgents((prev) => prev.map((a) => (a.id === selectedAgent.id ? { ...a, modelProvider: val } : a)));
                        }}
                        className="w-full bg-white dark:bg-[#2B0063] border border-gray-300 dark:border-white/20 rounded-xl px-3 py-2 text-xs text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none"
                      >
                        <option value="Gemini 1.5 Pro (Industrial Mesh)">Gemini 1.5 Pro (Industrial Mesh)</option>
                        <option value="DeepSeek R1 (Quantized)">DeepSeek R1 (Quantized)</option>
                        <option value="Claude 3.5 Sonnet (Enterprise)">Claude 3.5 Sonnet (Enterprise)</option>
                        <option value="AI-ConneX Core Feature Engine v2">AI-ConneX Core Feature Engine v2</option>
                        <option value="Optuna + AI-ConneX Core Mesh">Optuna + AI-ConneX Core Mesh</option>
                        <option value="ONNX Runtime v1.18 API">ONNX Runtime v1.18 API</option>
                      </select>
                    </div>

                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10 space-y-2">
                      <label className="font-bold text-muted uppercase block">API Endpoint Route</label>
                      <input
                        type="text"
                        value={selectedAgent.endpoint}
                        onChange={(e) => {
                          const val = e.target.value;
                          setAgents((prev) => prev.map((a) => (a.id === selectedAgent.id ? { ...a, endpoint: val } : a)));
                        }}
                        className="w-full bg-white dark:bg-[#2B0063] border border-gray-300 dark:border-white/20 rounded-xl px-3 py-2 text-xs text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none"
                      />
                    </div>
                  </div>

                  {/* System Prompt Editor */}
                  <div className="space-y-2">
                    <label className="text-xs font-mono font-bold uppercase text-[#2B0063] dark:text-white flex items-center justify-between">
                      <span>System Persona &amp; Instructions Prompt</span>
                      <span className="text-[10px] text-muted">Auto-saved to Agent Configuration</span>
                    </label>
                    <textarea
                      rows={5}
                      value={selectedAgent.systemPrompt}
                      onChange={(e) => {
                        const val = e.target.value;
                        setAgents((prev) => prev.map((a) => (a.id === selectedAgent.id ? { ...a, systemPrompt: val } : a)));
                      }}
                      className="w-full bg-[#F7F7F7] dark:bg-[#1A0530] border border-gray-300 dark:border-white/20 rounded-2xl p-4 text-xs font-mono text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none leading-relaxed"
                    />
                  </div>
                </div>
              )}

              {/* TAB 4: SCALING & REPLICAS */}
              {activeInspectTab === 'scaling' && (
                <div className="space-y-6 animate-fadeIn font-mono text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10 space-y-3">
                      <div className="flex justify-between items-center font-bold">
                        <span>Max Concurrency Parallel Subagents</span>
                        <span className="text-[#FF6B35]">{selectedAgent.concurrencyLimit} Worker Threads</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="64"
                        value={selectedAgent.concurrencyLimit}
                        onChange={(e) => {
                          const val = parseInt(e.target.value);
                          setAgents((prev) => prev.map((a) => (a.id === selectedAgent.id ? { ...a, concurrencyLimit: val } : a)));
                        }}
                        className="w-full accent-[#FF6B35]"
                      />
                    </div>

                    <div className="p-4 bg-[#F7F7F7] dark:bg-[#2B0063]/50 rounded-2xl border border-gray-200 dark:border-white/10 space-y-3">
                      <div className="flex justify-between items-center font-bold">
                        <span>Replicas &amp; Containers Count</span>
                        <span className="text-[#FF6B35]">{selectedAgent.replicas} Active Containers</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="16"
                        value={selectedAgent.replicas}
                        onChange={(e) => {
                          const val = parseInt(e.target.value);
                          setAgents((prev) => prev.map((a) => (a.id === selectedAgent.id ? { ...a, replicas: val } : a)));
                        }}
                        className="w-full accent-[#FF6B35]"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Interactive Prompt Test Sandbox Section */}
              <div className="p-5 bg-[#1A0530] text-white rounded-2xl border border-[#FF6B35]/40 space-y-3 font-mono">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#FF6B35] text-sm">terminal</span>
                    <span>Test Prompt Sandbox (Live Agent API Test)</span>
                  </h4>
                  <span className="text-[10px] text-[#FF6B35] font-bold">Route: {selectedAgent.endpoint}</span>
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={sandboxPrompt}
                    onChange={(e) => setSandboxPrompt(e.target.value)}
                    placeholder="Enter test prompt to send to agent..."
                    className="flex-1 bg-white/10 border border-white/20 rounded-xl px-3 py-2 text-xs text-white placeholder-white/40 focus:ring-2 focus:ring-[#FF6B35] outline-none"
                  />
                  <button
                    onClick={handleRunSandboxTest}
                    disabled={isSandboxRunning}
                    className="px-4 py-2 bg-[#FF6B35] hover:bg-[#E85520] text-white font-bold text-xs rounded-xl transition-all shadow-md flex items-center gap-1.5 cursor-pointer"
                  >
                    <span className={`material-symbols-outlined text-sm ${isSandboxRunning ? 'animate-spin' : ''}`}>
                      {isSandboxRunning ? 'sync' : 'send'}
                    </span>
                    <span>{isSandboxRunning ? 'Running...' : 'Execute'}</span>
                  </button>
                </div>

                {sandboxResponse && (
                  <div className="p-3 bg-white/5 border border-[#FF6B35]/30 rounded-xl text-xs text-[#FF6B35] whitespace-pre-wrap leading-relaxed animate-fadeIn">
                    {sandboxResponse}
                  </div>
                )}
              </div>

            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-gray-100 dark:bg-[#1A0530] rounded-b-3xl flex justify-between items-center border-t border-gray-200 dark:border-white/10">
              <span className="text-xs font-mono text-muted">API Security Key: {selectedAgent.apiKeyMasked}</span>
              <button
                onClick={() => setIsInspectModalOpen(false)}
                className="px-5 py-2 bg-[#FF6B35] text-white font-mono text-xs font-bold rounded-xl hover:bg-[#E85520] transition-colors"
              >
                Done / Close Studio
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Register New Agent */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#3C1053] border border-gray-200 dark:border-white/20 rounded-3xl max-w-md w-full p-6 space-y-5 shadow-2xl animate-scaleIn text-[#333333] dark:text-white">
            <div className="flex justify-between items-center border-b border-gray-200 dark:border-white/10 pb-3">
              <h3 className="font-headline font-bold text-lg text-[#2B0063] dark:text-white flex items-center gap-2">
                <span className="material-symbols-outlined text-[#FF6B35]">add_circle</span>
                <span>Deploy Custom AI Agent</span>
              </h3>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateAgent} className="space-y-4 font-mono text-xs">
              <div>
                <label className="font-bold text-secondary block mb-1">
                  Agent Profile Name (e.g. JANE, VICTOR)
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. SOPHIA"
                  value={newAgentName}
                  onChange={(e) => setNewAgentName(e.target.value)}
                  className="w-full bg-[#F7F7F7] dark:bg-[#2B0063] border border-gray-300 dark:border-white/20 rounded-xl px-3 py-2 text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none"
                />
              </div>

              <div>
                <label className="font-bold text-secondary block mb-1">
                  Agent Title &amp; Specialty
                </label>
                <input
                  type="text"
                  placeholder="e.g. Real-Time Vibration Anomaly Classifier"
                  value={newAgentTitle}
                  onChange={(e) => setNewAgentTitle(e.target.value)}
                  className="w-full bg-[#F7F7F7] dark:bg-[#2B0063] border border-gray-300 dark:border-white/20 rounded-xl px-3 py-2 text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none"
                />
              </div>

              <div>
                <label className="font-bold text-secondary block mb-1">
                  Profile Photo URL (Human Avatar)
                </label>
                <input
                  type="text"
                  value={newAgentAvatar}
                  onChange={(e) => setNewAgentAvatar(e.target.value)}
                  className="w-full bg-[#F7F7F7] dark:bg-[#2B0063] border border-gray-300 dark:border-white/20 rounded-xl px-3 py-2 text-primary focus:ring-2 focus:ring-[#FF6B35] outline-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 bg-gray-200 dark:bg-slate-700 text-[#333333] dark:text-white font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-[#FF6B35] hover:bg-[#E85520] text-white font-bold rounded-xl shadow-md"
                >
                  Deploy Agent Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentManagerView;
