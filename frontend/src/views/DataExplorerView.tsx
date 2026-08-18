import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  MessageSquare, 
  UploadCloud, 
  BarChart2, 
  Eraser, 
  CheckSquare, 
  Beaker, 
  Workflow, 
  FileText, 
  Rocket, 
  TrendingUp, 
  Network, 
  Shield, 
  Database,
  Bell,
  Sun,
  Moon,
  ChevronDown,
  Folder
} from 'lucide-react';

import PrePrepare from './DataExplorer/PrePrepare';
import PostPrepare from './DataExplorer/PostPrepare';
import PostFE from './DataExplorer/PostFE';
import PostTrain from './DataExplorer/PostTrain';
import AdHocExplorer from './DataExplorer/AdHocExplorer';

interface DataExplorerViewProps {
  compiledCsvPath?: string;
  runId?: string;
  dagId?: string;
  algorithmFamily?: string;
  onProceedToPrepare: () => void;
  onApproveDeliverables?: () => void;
}

// ── Resilient Stage Error Boundary ───────────────────────────────────────────
interface StageErrorBoundaryProps {
  children: React.ReactNode;
  stageName: string;
  onReset?: () => void;
}

interface StageErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class DataExplorerErrorBoundary extends React.Component<StageErrorBoundaryProps, StageErrorBoundaryState> {
  public state: StageErrorBoundaryState = { hasError: false };

  public static getDerivedStateFromError(error: Error): StageErrorBoundaryState {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.warn('[DataExplorer] Stage renderer caught error:', error, errorInfo);
  }

  public handleRetry = (): void => {
    (this as unknown as React.Component<StageErrorBoundaryProps, StageErrorBoundaryState>).setState({ hasError: false, error: undefined });
    if (this.props.onReset) this.props.onReset();
  };

  public render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="p-8 max-w-[1200px] mx-auto my-8 bg-white rounded-2xl border border-slate-200 shadow-sm text-center">
          <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
            <span className="material-symbols-outlined text-2xl">analytics</span>
          </div>
          <h2 className="text-base font-bold text-slate-800 mb-1">
            {this.props.stageName} Initializing
          </h2>
          <p className="text-xs text-slate-500 max-w-lg mx-auto mb-5">
            Synchronizing live statistical profiling metrics for this stage. Click below to refresh the view.
          </p>
          <button
            onClick={this.handleRetry}
            className="px-5 py-2.5 bg-[#FF6B35] hover:bg-[#e05624] text-white text-xs font-bold rounded-xl shadow-md transition-all cursor-pointer inline-flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-sm">refresh</span> Refresh {this.props.stageName}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export const DataExplorerView: React.FC<DataExplorerViewProps> = ({
  compiledCsvPath,
  runId = 'run_20250115_143022',
  dagId = 'DAG_201',
  algorithmFamily = 'Anomaly Detection',
  onProceedToPrepare,
  onApproveDeliverables,
}) => {
  const [activeTab, setActiveTab] = useState<'pre-prepare' | 'exhaustive-eda' | 'post-prepare' | 'post-fe' | 'post-train' | 'ad-hoc'>('pre-prepare');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [actionsOpen, setActionsOpen] = useState(false);
  const [backendProfile, setBackendProfile] = useState<any>(null);

  // Sync theme with document attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  // Fetch backend profiling payload if backend is online
  useEffect(() => {
    if (compiledCsvPath) {
      const profilerForm = new FormData();
      profilerForm.append('file_path', compiledCsvPath);
      fetch('http://localhost:8000/api/v1/profile', {
        method: 'POST',
        body: profilerForm
      })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && data.profile) {
          setBackendProfile(data.profile);
        }
      })
      .catch(() => {});
    }
  }, [compiledCsvPath]);

  // Sidebar Icons definitions (MainPages Rail)
  const sidebarTopIcons = [
    { id: 'magic', icon: <Sparkles size={18} />, classes: "sidebar-icon-magic" },
    { id: 'chat', icon: <MessageSquare size={18} /> },
    { id: 'upload', icon: <UploadCloud size={18} /> },
    { id: 'analytics', icon: <BarChart2 size={18} />, classes: "sidebar-icon-active" },
    { id: 'cleanup', icon: <Eraser size={18} /> },
    { id: 'tasks', icon: <CheckSquare size={18} /> },
    { id: 'lab', icon: <Beaker size={18} /> },
    { id: 'flow', icon: <Workflow size={18} /> },
    { id: 'docs', icon: <FileText size={18} /> },
    { id: 'deploy', icon: <Rocket size={18} /> },
    { id: 'growth', icon: <TrendingUp size={18} /> },
  ];

  const sidebarBottomIcons = [
    { id: 'network', icon: <Network size={18} />, classes: "sidebar-icon-blue-active", badge: 9 },
    { id: 'security', icon: <Shield size={18} /> },
    { id: 'storage', icon: <Database size={18} /> }
  ];

  // Pipeline stage tabs
  const tabs = [
    { id: 'pre-prepare', label: 'Pre-Prepare', badge: 'Brain', number: 1 },
    { id: 'exhaustive-eda', label: 'Exhaustive EDA', badge: 'fg-Profiler', number: 2 },
    { id: 'post-prepare', label: 'Post-Prepare', badge: 'Prepare', number: 3 },
    { id: 'post-fe', label: 'Post-F.E', badge: 'Feature Engineered', number: 4 },
    { id: 'post-train', label: 'Post-Train', badge: 'Training', number: 5 },
    { id: 'ad-hoc', label: 'Ad-Hoc Explorer', badge: 'Visual Query', number: 6 }
  ];

  // Render correct subpage
  const renderSubpage = () => {
    switch (activeTab) {
      case 'pre-prepare':
        return (
          <PrePrepare 
            onProceed={() => setActiveTab('post-prepare')}
            compiledCsvPath={compiledCsvPath}
            runId={runId}
            dagId={dagId}
            algorithmFamily={algorithmFamily}
            backendProfile={backendProfile}
            onApproveDeliverables={onApproveDeliverables}
          />
        );
      case 'exhaustive-eda':
        const effectiveRunId = (runId && runId !== 'undefined' && runId !== 'null') ? runId : 'run_20250115_143022';
        const activeCsvName = compiledCsvPath ? compiledCsvPath.replace(/\\/g, '/').split('/').pop() : 'all_groups_combined.csv';
        return (
          <div className="p-6 max-w-[1700px] mx-auto animate-fadeIn space-y-4">
            <div className="flex items-center justify-between bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-3.5">
                <div className="w-10 h-10 flex items-center justify-center bg-[#FF6B35]/10 border border-[#FF6B35]/30 rounded-xl text-[#FF6B35]">
                  <span className="material-symbols-outlined text-xl">insights</span>
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2.5">
                    Exhaustive Statistical EDA Report
                    <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold">
                      Live fg-data-profiling
                    </span>
                  </h2>
                  <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                    <span>Source: <strong className="text-slate-700 font-mono bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">{activeCsvName}</strong></span>
                    <span className="text-slate-300">•</span>
                    <span>Real histograms, time-series PACF &amp; missingness heatmaps (&lt; 2 MB fast load)</span>
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setActiveTab('pre-prepare')}
                className="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-xl transition-all border border-slate-200 hover:border-slate-300 shadow-2xs cursor-pointer flex items-center gap-1.5"
              >
                <span>← Back to Pre-Prepare</span>
              </button>
            </div>
            
            <iframe 
              src={`http://localhost:8000/api/v1/reports/${effectiveRunId}/eda_report.html?theme=${theme}&file_path=${encodeURIComponent(compiledCsvPath || '')}`}
              className="w-full h-[82vh] rounded-2xl border border-slate-200 shadow-sm bg-white transition-all"
              title="Exhaustive Data Profiling Report"
            />
          </div>
        );

      case 'post-prepare':
        return (
          <PostPrepare 
            onProceed={() => setActiveTab('post-fe')}
            compiledCsvPath={compiledCsvPath}
            runId={runId}
            dagId={dagId}
          />
        );
      case 'post-fe':
        return (
          <PostFE 
            onProceed={() => setActiveTab('post-train')}
            compiledCsvPath={compiledCsvPath}
            runId={runId}
            dagId={dagId}
          />
        );
      case 'post-train':
        return (
          <PostTrain 
            compiledCsvPath={compiledCsvPath}
            runId={runId}
            dagId={dagId}
          />
        );
      case 'ad-hoc':
        return (
          <AdHocExplorer
            compiledCsvPath={compiledCsvPath}
            runId={runId}
            dagId={dagId}
            algorithmFamily={algorithmFamily}
          />
        );
      default:
        return <PrePrepare onProceed={() => setActiveTab('post-prepare')} />;
    }
  };


  return (
    <div className="flex flex-col min-h-screen bg-canvas font-sans animate-slideInRight">
      
      {/* Sub-Header / Control Hub */}
      <section className="sub-header-container">
        <div className="sub-header-top">
          <div className="window-dots-title">
            <div className="window-dots">
              <span className="dot dot-red" style={{ backgroundColor: '#C8102E' }}></span>
              <span className="dot dot-yellow"></span>
              <span className="dot dot-green"></span>
            </div>
            <div className="window-title">
              <Folder size={14} />
              Dataset Explorer Stage Transit Hub
            </div>
          </div>
        </div>

        {/* Navigation Pipeline Tabs */}
        <nav className="stages-tabs-container">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`stage-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id as any)}
            >
              <span className="stage-tab-text-title">{tab.label}</span>
              <span className={`stage-badge stage-badge-${tab.id === 'pre-prepare' ? 'brain' : tab.id === 'post-prepare' ? 'prepare' : tab.id === 'post-fe' ? 'fe' : tab.id === 'post-train' ? 'training' : 'adhoc'}`}>
                {tab.badge}
              </span>
              <span className="stage-tab-number">{tab.number}</span>
            </button>
          ))}
        </nav>
      </section>

      {/* Content Render Workspace */}
      <div style={{ flex: 1 }}>
        <DataExplorerErrorBoundary stageName={tabs.find(t => t.id === activeTab)?.label || 'Data Explorer'}>
          {renderSubpage()}
        </DataExplorerErrorBoundary>
      </div>

      {/* Operational Footer */}
      <footer className="app-footer">
        <div className="footer-status">
          <span className="status-dot"></span>
          SYSTEM STATUS: OPERATIONAL
        </div>
        <div>
          © 2026 TAS AI-Suite. All Rights Reserved.
        </div>
        <div className="footer-links">
          <a href="#privacy">Privacy Policy</a>
          <a href="#terms">Terms of Service</a>
          <a href="#security">Security Standards</a>
        </div>
      </footer>

    </div>
  );
};

export default DataExplorerView;
