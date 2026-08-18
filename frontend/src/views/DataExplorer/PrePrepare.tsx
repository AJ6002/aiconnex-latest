import React, { useState, useEffect } from 'react';
import { 
  Workflow, 
  GitCommit, 
  ArrowRight, 
  Info, 
  AlertCircle,
  FileText,
  Sliders,
  Cpu,
  Search,
  CheckCircle,
  AlertTriangle,
  TrendingUp
} from 'lucide-react';

interface PrePrepareProps {
  onProceed?: () => void;
  compiledCsvPath?: string;
  runId?: string;
  dagId?: string;
  algorithmFamily?: string;
  backendProfile?: Record<string, any> | null;
  onApproveDeliverables?: () => void;
}

// Reusable SVG Chart Renderer for Pre-Prepare visualizations (140px uniform height)
function ChartRenderer({ type, id, flagged }: { type: string; id: string | number; flagged?: boolean }) {
  const primaryColor = flagged ? '#C8102E' : '#1E47C8';
  const secondaryColor = flagged ? '#fca5a5' : '#93c5fd';
  const accentColor = '#8b5cf6';
  
  switch (type) {
    case 'line':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <defs>
            <linearGradient id={`grad-line-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={primaryColor} stopOpacity="0.2"/>
              <stop offset="100%" stopColor={primaryColor} stopOpacity="0.0"/>
            </linearGradient>
          </defs>
          <line x1="20" y1="20" x2="280" y2="20" stroke="var(--border-light)" strokeWidth="0.5" strokeDasharray="3" />
          <line x1="20" y1="60" x2="280" y2="60" stroke="var(--border-light)" strokeWidth="0.5" strokeDasharray="3" />
          <line x1="20" y1="100" x2="280" y2="100" stroke="var(--border-light)" strokeWidth="0.5" strokeDasharray="3" />
          <path d={`M 20 100 Q 80 ${flagged ? 10 : 40} 140 ${flagged ? 90 : 70} T 280 ${flagged ? 10 : 50} L 280 100 L 20 100 Z`} fill={`url(#grad-line-${id})`} />
          <path d={`M 20 100 Q 80 ${flagged ? 10 : 40} 140 ${flagged ? 90 : 70} T 280 ${flagged ? 10 : 50}`} fill="none" stroke={primaryColor} strokeWidth="2.5" />
          <circle cx="140" cy={flagged ? 90 : 70} r="4" fill={primaryColor} />
          {flagged && <circle cx="280" cy="10" r="5" fill="#C8102E" className="animate-pulse" />}
        </svg>
      );

    case 'heatmap':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          {Array.from({ length: 4 }).map((_, r) => 
            Array.from({ length: 8 }).map((_, c) => {
              const val = Math.sin(r * c + 1) * 0.5 + 0.5;
              const isCellFlagged = flagged && r === 2 && c === 4;
              return (
                <rect 
                  key={`${r}-${c}`}
                  x={20 + c * 32}
                  y={12 + r * 24}
                  width="28"
                  height="20"
                  rx="3"
                  fill={isCellFlagged ? '#C8102E' : primaryColor}
                  opacity={isCellFlagged ? 0.95 : Math.max(0.1, val)}
                  stroke={isCellFlagged ? '#fee2e2' : 'none'}
                  strokeWidth="1.5"
                />
              );
            })
          )}
        </svg>
      );

    case 'donut':
      const percentage = flagged ? 18 : 84;
      const radius = 35;
      const circumference = 2 * Math.PI * radius;
      const strokeDashoffset = circumference - (percentage / 100) * circumference;
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <circle cx="150" cy="60" r={radius} fill="none" stroke="var(--border-medium)" strokeWidth="8" />
          <circle 
            cx="150" 
            cy="60" 
            r={radius} 
            fill="none" 
            stroke={primaryColor} 
            strokeWidth="8" 
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform="rotate(-90 150 60)"
          />
          <text x="150" y="66" textAnchor="middle" fill="var(--text-main)" fontSize="16" fontWeight="bold" fontFamily="var(--font-heading)">
            {percentage}%
          </text>
        </svg>
      );

    case 'bar':
      const bars = flagged ? [85, 92, 12, 74, 98, 110] : [70, 75, 82, 79, 88, 85];
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <line x1="20" y1="40" x2="280" y2="40" stroke="#f59e0b" strokeWidth="1" strokeDasharray="4" />
          {bars.map((h, i) => {
            const isBarFlagged = flagged && i === 2;
            return (
              <rect 
                key={i}
                x={25 + i * 42}
                y={110 - (h * 0.8)}
                width="24"
                height={h * 0.8}
                rx="3"
                fill={isBarFlagged ? '#C8102E' : primaryColor}
              />
            );
          })}
        </svg>
      );

    case 'scatter':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <line x1="20" y1="100" x2="280" y2="100" stroke="var(--border-light)" strokeWidth="0.5" />
          <line x1="20" y1="20" x2="20" y2="100" stroke="var(--border-light)" strokeWidth="0.5" />
          {Array.from({ length: 20 }).map((_, i) => {
            const x = 50 + (Math.cos(i) * 30) + (i * 8);
            const y = 60 + (Math.sin(i * 1.5) * 20);
            return <circle key={i} cx={x} cy={y} r="3.5" fill={primaryColor} opacity="0.6" />;
          })}
          {flagged && (
            <>
              <circle cx="260" cy="25" r="5" fill="#C8102E" />
              <line x1="260" y1="25" x2="210" y2="55" stroke="#C8102E" strokeWidth="1" strokeDasharray="2" />
              <text x="250" y="16" fill="#C8102E" fontSize="8" fontWeight="bold">Outlier</text>
            </>
          )}
        </svg>
      );

    case 'barcode':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          {Array.from({ length: 48 }).map((_, i) => {
            const isMissing = flagged && (i > 18 && i < 24);
            return (
              <line 
                key={i}
                x1={20 + i * 5.5}
                y1="25"
                x2={20 + i * 5.5}
                y2="95"
                stroke={isMissing ? 'var(--border-light)' : primaryColor}
                strokeWidth={isMissing ? 0.5 : 2}
                opacity={isMissing ? 0.2 : 0.85}
              />
            );
          })}
          {flagged && (
            <rect x="120" y="20" width="36" height="80" fill="none" stroke="#C8102E" strokeWidth="1.5" strokeDasharray="3" rx="4" />
          )}
        </svg>
      );

    case 'gauge':
      const angle = flagged ? 140 : 45;
      const rad = (angle - 180) * Math.PI / 180;
      const pointerX = 150 + 45 * Math.cos(rad);
      const pointerY = 90 + 45 * Math.sin(rad);
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <path d="M 90 90 A 60 60 0 0 1 210 90" fill="none" stroke="var(--border-medium)" strokeWidth="12" strokeLinecap="round" />
          <path d={`M 90 90 A 60 60 0 0 1 ${150 + 60 * Math.cos(rad)} ${90 + 60 * Math.sin(rad)}`} fill="none" stroke={primaryColor} strokeWidth="12" strokeLinecap="round" />
          <line x1="150" y1="90" x2={pointerX} y2={pointerY} stroke="var(--text-main)" strokeWidth="3" strokeLinecap="round" />
          <circle cx="150" cy="90" r="6" fill="var(--text-main)" />
        </svg>
      );

    case 'matrix':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          {Array.from({ length: 3 }).map((_, r) => 
            Array.from({ length: 6 }).map((_, c) => {
              const isConflict = flagged && r === 1 && c === 3;
              return (
                <g key={`${r}-${c}`} transform={`translate(${30 + c * 40}, ${20 + r * 30})`}>
                  <rect width="32" height="22" rx="4" fill="var(--bg-card)" stroke="var(--border-medium)" strokeWidth="1" />
                  {isConflict ? (
                    <text x="16" y="16" textAnchor="middle" fill="#C8102E" fontSize="12" fontWeight="bold">⚠️</text>
                  ) : (
                    <circle cx="16" cy="11" r="3.5" fill="#FF6B35" />
                  )}
                </g>
              );
            })
          )}
        </svg>
      );

    case 'treemap':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <rect x="20" y="15" width="160" height="90" rx="4" fill={primaryColor} opacity="0.85" stroke="var(--bg-card)" strokeWidth="1.5" />
          <text x="30" y="35" fill="white" fontSize="11" fontWeight="bold">Feature_Set_A</text>
          <text x="30" y="55" fill="white" fontSize="10" opacity="0.8">{flagged ? '58% MB' : '65% MB'}</text>
          <rect x="185" y="15" width="95" height="42" rx="4" fill={secondaryColor} stroke="var(--bg-card)" strokeWidth="1.5" />
          <text x="192" y="32" fill="var(--text-main)" fontSize="9" fontWeight="bold">Feature_B</text>
          <rect x="185" y="60" width="50" height="45" rx="4" fill={accentColor} opacity="0.6" stroke="var(--bg-card)" strokeWidth="1.5" />
          <rect x="238" y="60" width="42" height="45" rx="4" fill={flagged ? '#f87171' : secondaryColor} opacity="0.8" stroke="var(--bg-card)" strokeWidth="1.5" />
        </svg>
      );

    case 'waterfall':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <rect x="20" y="20" width="30" height="80" fill="#1E47C8" rx="2" />
          <rect x="60" y="20" width="30" height="20" fill="#FF6B35" rx="2" />
          <line x1="50" y1="20" x2="60" y2="20" stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2" />
          <rect x="100" y="40" width="30" height="30" fill="#FF6B35" rx="2" />
          <line x1="90" y1="40" x2="100" y2="40" stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2" />
          <rect x="140" y="70" width="30" height="25" fill="#C8102E" rx="2" />
          <line x1="130" y1="70" x2="140" y2="70" stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2" />
          <rect x="180" y="95" width="30" height="15" fill={flagged ? '#C8102E' : '#1E47C8'} rx="2" />
          <line x1="170" y1="95" x2="180" y2="95" stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="2" />
        </svg>
      );

    case 'kde':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <path d="M 20 100 C 60 100, 100 15, 140 15 C 180 15, 220 100, 280 100" fill="none" stroke="var(--border-medium)" strokeWidth="2" />
          <path 
            d={`M 20 100 C 70 100, 120 ${flagged ? 45 : 20}, 160 ${flagged ? 45 : 20} C 200 ${flagged ? 45 : 20}, 240 100, 280 100`} 
            fill="none" 
            stroke={primaryColor} 
            strokeWidth="2.5" 
          />
        </svg>
      );

    case 'box':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <line x1="40" y1="60" x2="250" y2="60" stroke="var(--text-main)" strokeWidth="1.5" />
          <line x1="40" y1="45" x2="40" y2="75" stroke="var(--text-main)" strokeWidth="1.5" />
          <line x1="250" y1="45" x2="250" y2="75" stroke="var(--text-main)" strokeWidth="1.5" />
          <rect x="90" y="35" width="100" height="50" fill={secondaryColor} stroke="var(--text-main)" strokeWidth="1.5" rx="3" />
          <line x1="140" y1="35" x2="140" y2="85" stroke={primaryColor} strokeWidth="3" />
          <circle cx="20" cy="60" r="3" fill="#C8102E" />
          <circle cx="270" cy="60" r="3" fill="#C8102E" />
        </svg>
      );

    case 'radar':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <g transform="translate(150, 60)">
            <polygon points="0,-45 39,-22.5 39,22.5 0,45 -39,22.5 -39,-22.5" fill="none" stroke="var(--border-medium)" strokeWidth="1" />
            <polygon points="0,-25 21,-12.5 21,12.5 0,25 -21,12.5 -21,-12.5" fill="none" stroke="var(--border-light)" strokeWidth="0.5" />
            <polygon 
              points={flagged 
                ? "0,-42 35,-15 15,10 0,40 -35,5 -10,-20"
                : "0,-30 30,-18 25,18 0,32 -25,18 -20,-18"
              } 
              fill={primaryColor} 
              fillOpacity="0.4" 
              stroke={primaryColor} 
              strokeWidth="2" 
            />
          </g>
        </svg>
      );

    case 'sankey':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <rect x="20" y="20" width="15" height="30" fill={primaryColor} rx="2" />
          <rect x="20" y="65" width="15" height="35" fill={accentColor} rx="2" />
          <path d={`M 35 35 C 100 35, 120 ${flagged ? 85 : 55}, 180 ${flagged ? 85 : 55}`} fill="none" stroke={primaryColor} strokeWidth="8" opacity="0.35" />
          <path d="M 35 80 C 100 80, 120 45, 180 45" fill="none" stroke={accentColor} strokeWidth="12" opacity="0.35" />
          <rect x="180" y="30" width="15" height="25" fill={accentColor} rx="2" />
          <rect x="180" y="65" width="15" height="30" fill={primaryColor} rx="2" />
        </svg>
      );

    case 'tree':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <rect x="135" y="15" width="30" height="15" rx="3" fill="var(--text-main)" />
          <line x1="150" y1="30" x2="90" y2="55" stroke="var(--border-medium)" strokeWidth="1.5" />
          <line x1="150" y1="30" x2="210" y2="55" stroke="var(--border-medium)" strokeWidth="1.5" />
          <rect x="75" y="55" width="30" height="15" rx="3" fill={primaryColor} />
          <rect x="195" y="55" width="30" height="15" rx="3" fill={secondaryColor} />
          <line x1="90" y1="70" x2="60" y2="95" stroke="var(--border-medium)" strokeWidth="1" />
          <line x1="90" y1="70" x2="120" y2="95" stroke="var(--border-medium)" strokeWidth="1" />
          <rect x="45" y="95" width="30" height="15" rx="3" fill={flagged ? '#C8102E' : secondaryColor} />
          <rect x="105" y="95" width="30" height="15" rx="3" fill="#FF6B35" />
        </svg>
      );

    case 'gantt':
      return (
        <svg viewBox="0 0 300 120" className="w-full h-full">
          <line x1="60" y1="20" x2="60" y2="100" stroke="var(--border-light)" strokeWidth="0.5" />
          <line x1="130" y1="20" x2="130" y2="100" stroke="var(--border-light)" strokeWidth="0.5" />
          <line x1="200" y1="20" x2="200" y2="100" stroke="var(--border-light)" strokeWidth="0.5" />
          <rect x="40" y="25" width="70" height="12" rx="3" fill="#FF6B35" />
          <rect x="100" y="45" width="50" height="12" rx="3" fill="#FF6B35" />
          <rect x="140" y="65" width="80" height="12" rx="3" fill={flagged ? '#f59e0b' : '#FF6B35'} />
          <rect x="210" y="85" width="60" height="12" rx="3" fill={primaryColor} />
        </svg>
      );

    default:
      return (
        <div className="w-full h-full flex items-center justify-center text-xs text-slate-400 font-mono">
          Custom Plot Canvas ({type})
        </div>
      );
  }
}

export const PrePrepare: React.FC<PrePrepareProps> = ({
  onProceed,
  runId = 'run_20250115_143022',
  dagId = 'DAG_201',
  algorithmFamily = 'Anomaly Detection',
  backendProfile = null,
  onApproveDeliverables,
}) => {
  const [activeStep, setActiveStep] = useState<number | null>(null);

  // Pre-Prepare 4 Steps Dataset Analysis Catalog
  const prePrepareSteps = [
    {
      id: 1,
      title: "1. ⚙️ COMPILER INSIGHTS",
      badge: "Compiled ✓",
      badgeClass: "badge-green",
      description: "Shows how sub-CSV raw files were merged together, recording compilation duration, file counts, and checking for data duplication or corruption.",
      plots: [
        { id: '1.1', title: 'File Merge Trace', type: 'line', check: 'Row count per merged sub-file vs expected baseline', threshold: '<100 rows or >3x avg', flagged: false, exp: 'Line plot showing row counts per merged sub-file. Spikes show large sub-files; sharp drops indicate missing records.' },
        { id: '1.2', title: 'Schema Consistency Matrix', type: 'heatmap', check: 'Column presence & type match across sub-files', threshold: '>2 missing columns', flagged: true, exp: 'Color grid mapping columns per file. Red cells mark missing attributes or data type mismatches.' },
        { id: '1.3', title: 'Column Type Distribution', type: 'donut', check: '% of numeric vs categorical vs date fields', threshold: '>15% string increase', flagged: false, exp: 'Donut chart of field types. Sudden increase in text types highlights unparsed numeric fields.' },
        { id: '1.4', title: 'Row Count per File Timeline', type: 'bar', check: 'Row count stability across batch files', threshold: 'CV > 0.5 ratio', flagged: true, exp: 'Bar chart comparing row counts across sub-files. Red bar alerts to abnormal file truncation.' },
        { id: '1.5', title: 'File Size vs. Row Count Scatter', type: 'scatter', check: 'Data density (MB per row count)', threshold: '>2 std deviations', flagged: false, exp: 'Scatter plot mapping size against row count. Outliers reveal bloated binary data or corrupted rows.' },
        { id: '1.6', title: 'Column Co-occurrence Matrix', type: 'barcode', check: 'Which columns co-exist in each file', threshold: 'Empty vertical stripe', flagged: true, exp: 'Barcode plot of column presence. White vertical gaps highlight columns omitted during merging.' },
        { id: '1.7', title: 'Compilation Duration Gauge', type: 'gauge', check: 'Time taken to assemble ZIP dataset', threshold: '>2x historical avg', flagged: false, exp: 'Speedometer dial measuring compilation runtime. High reading points to I/O bottlenecks.' },
        { id: '1.8', title: 'Column Type Conflict Matrix', type: 'matrix', check: 'Same column with mismatched types across files', threshold: 'Any type conflict', flagged: true, exp: 'Conflict grid flagging schema type clashes across files (e.g. integer vs string).' }
      ]
    },
    {
      id: 2,
      title: "2. 📊 DATA-PROFILER INSIGHTS",
      badge: "Profiled ✓",
      badgeClass: "badge-green",
      description: "Analyzes missing value rates, data types, and feature shapes to auto-recommend the optimal AI workflow model (DAG ID).",
      plots: [
        { id: '2.1', title: 'Feature Distribution Overlay', type: 'kde', check: 'Distribution shift per feature', threshold: 'KS p-value < 0.05', flagged: true, exp: 'Overlaid curve comparing old vs new feature shape. Rightward shift signals environmental drift.' },
        { id: '2.2', title: 'Null Value Waterfall', type: 'waterfall', check: 'Missing value % change per feature', threshold: '>10% null increase', flagged: false, exp: 'Waterfall chart tracking missing value counts. Growing red bars highlight missing data degradation.' },
        { id: '2.3', title: 'Feature Correlation Shift Matrix', type: 'heatmap', check: 'Correlation change between numerical pairs', threshold: 'Delta > 0.3', flagged: false, exp: 'Heatmap matrix of feature relationship shifts. Color changes highlight altering dependencies.' },
        { id: '2.4', title: 'Outlier Density Pinpointer', type: 'box', check: 'Outlier percentage beyond 1.5x IQR', threshold: '>1% of dataset', flagged: true, exp: 'Box plot pinpointer highlighting extreme outlier readings beyond typical interquartile bounds.' },
        { id: '2.5', title: 'Sparsity Detection Matrix', type: 'barcode', check: '% of zero / empty values per feature', threshold: '>60% zero ratio', flagged: true, exp: 'Sparse matrix highlighting features with high zero-value density (>60%).' },
        { id: '2.6', title: 'Memory Footprint Treemap', type: 'treemap', check: 'Memory usage per feature column', threshold: 'Object cols >40% MB', flagged: false, exp: 'Treemap breakdown of memory consumption per column to target data type downcasting.' },
        { id: '2.7', title: 'DAG Recommendation Tree', type: 'tree', check: 'Decision tree path leading to recommended DAG', threshold: 'Sparse + Skewed + Drift', flagged: false, exp: 'Decision path chart explaining why DAG_201 was auto-recommended based on dataset traits.' }
      ]
    },
    {
      id: 3,
      title: "3. 🕸️ DAG ORCHESTRATOR INSIGHTS",
      badge: "Training ⏳",
      badgeClass: "badge-yellow",
      description: "Details the active pipeline execution configuration, validating data topology and enforcing quality safety gates.",
      plots: [
        { id: '3.1', title: 'Pipeline Step Execution Timeline', type: 'gantt', check: 'Step completion times (Compile ➔ Train)', threshold: '>3x avg step duration', flagged: false, exp: 'Gantt timeline bar chart tracking execution time per pipeline node to isolate bottlenecks.' },
        { id: '3.2', title: 'Hyperparameter Change Radar', type: 'radar', check: 'Hyperparameter shifts (Old vs Current)', threshold: 'Value change >20%', flagged: true, exp: 'Spider radar plot contrasting configured hyperparameter values against historical defaults.' },
        { id: '3.3', title: 'Recipe Override Heatmap', type: 'heatmap', check: 'Default vs Overridden recipe settings', threshold: '>3 overrides per recipe', flagged: false, exp: 'Grid heatmap highlighting custom user overrides applied to default stage recipes.' },
        { id: '3.4', title: 'Quality Gate Boundary Scatter', type: 'scatter', check: 'Metric vs Quality Gate limits (RMSE, R²)', threshold: 'Metric outside gates', flagged: false, exp: 'Scatter plot comparing pipeline evaluation metrics against configured Quality Gate bounds.' }
      ]
    },
    {
      id: 4,
      title: "4. 🧪 RECIPE ORCHESTRATOR INSIGHTS",
      badge: "Resolved ✓",
      badgeClass: "badge-green",
      description: "Details the exact algorithm choices, scaling rules, data split ratios, and hyperparameter tuning values configured for training.",
      plots: [
        { id: '4.1', title: 'Parameter Delta Matrix', type: 'matrix', check: 'Old ➔ New resolved parameter values', threshold: 'Parameter delta >20%', flagged: false, exp: 'Parameter matrix displaying exact value changes between default and resolved training settings.' },
        { id: '4.2', title: 'Preprocessing Pipeline Flow', type: 'sankey', check: 'Raw ➔ Impute ➔ Scale ➔ Encode ➔ Output', threshold: 'Step skipped / overridden', flagged: false, exp: 'Flow diagram tracing data transformations through cleaning, scaling, and encoding stages.' },
        { id: '4.3', title: 'Hyperparameter Tuning Trace', type: 'line', check: 'Metric improvement over tuning iterations', threshold: 'Flatline >20 iterations', flagged: false, exp: 'Convergence line chart showing validation score gains across hyperparameter tuning iterations.' }
      ]
    }
  ];

  return (
    <div className="page-container font-sans text-xs">
      
      {/* 🚀 Status & Action Header Banner */}
      <section className="status-action-bar">
        <div className="status-bar-info">
          <div className="status-bar-icon-block">
            <Workflow size={20} />
          </div>
          <div className="status-bar-details">
            <div className="status-bar-title-row">
              <span>Pipeline Stage 1 Transit: Pre-Prepare [Brain]</span>
              <span className="status-run-badge">
                <GitCommit size={10} /> {runId}
              </span>
            </div>
            <div className="status-bar-parameters">
              <div className="param-item">
                <span>Recommended DAG:</span>
                <span className="highlight-orange font-bold font-mono">🏆 {dagId}</span>
              </div>
              <span>•</span>
              <div className="param-item">
                <span>Family:</span>
                <span className="highlight-green font-bold">{algorithmFamily}</span>
              </div>
              <span>•</span>
              <div className="param-item">
                <span>Target:</span>
                <span className="highlight-blue font-bold font-mono">failure_label</span>
              </div>
            </div>
          </div>
        </div>

        {onProceed && (
          <button className="proceed-cta-btn" onClick={onProceed}>
            Proceed to Preparation
            <ArrowRight size={16} />
          </button>
        )}
      </section>

      {/* 💡 Informational Banner */}
      <section className="info-callout-banner">
        <Info size={18} className="info-banner-icon" />
        <div className="info-banner-text">
          <strong>Pre-Prepare Stage Overview:</strong> Every visualization plot below includes a 1-line plain English explanation so you can easily understand what happened to your dataset during compilation, statistical profiling, and DAG resolution.
        </div>
      </section>

      {/* ⚡ Automated Quality Recommendation Cards ───────────────────────── */}
      {/* These cards are powered by the backend profiler (/api/v1/profile)   */}
      {/* and fall back to representative static values when backend is offline*/}
      <section className="dashboard-card border-amber-200 bg-gradient-to-r from-amber-50/60 via-white to-orange-50/40">
        <div className="card-header-row">
          <div className="card-title-group">
            <AlertTriangle className="card-title-icon-wrapper text-amber-600" size={18} />
            <h2 className="card-title">⚡ Automated Data Quality Recommendations</h2>
          </div>
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
            Auto-Generated
          </span>
        </div>
        <div className="card-subtitle-row">
          <Info className="card-subtitle-icon" size={16} />
          <span>
            These cards are automatically generated from statistical profiling of your dataset.
            Each card identifies a data quality signal and recommends the optimal transformation for your ML pipeline.
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px]">

          {/* Card 1: Extreme Skewness */}
          <div className={`p-4 rounded-xl border shadow-sm flex flex-col gap-2.5 ${
            (backendProfile?.max_skewness ?? 3.2) > 2.0
              ? 'border-rose-300 bg-rose-50/30'
              : 'border-[#FF6B35]/30 bg-[#FF6B35]/08/20'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-bold text-slate-800">
                <TrendingUp size={14} className={(backendProfile?.max_skewness ?? 3.2) > 2.0 ? 'text-rose-600' : 'text-[#FF6B35]'} />
                Extreme Skewness Detected
              </div>
              {(backendProfile?.max_skewness ?? 3.2) > 2.0 ? (
                <span className="flex items-center gap-0.5 bg-rose-100 text-rose-700 text-[9px] font-bold px-1.5 py-0.5 rounded border border-rose-200">
                  <AlertTriangle size={9} /> ALERT
                </span>
              ) : (
                <span className="flex items-center gap-0.5 bg-[#FF6B35]/12 text-[#FF6B35] text-[9px] font-bold px-1.5 py-0.5 rounded border border-[#FF6B35]/20">
                  <CheckCircle size={9} /> OK
                </span>
              )}
            </div>
            <div className="text-slate-600 leading-snug">
              <span className="font-mono text-[10px] text-rose-700 font-bold">
                Skewness: {(backendProfile?.max_skewness ?? 3.2).toFixed(2)} (column: {backendProfile?.most_skewed_col ?? 'temp_celsius'})
              </span>
              <br />
              Threshold: skewness &gt; 2.0 indicates a heavily right/left-tailed distribution.
            </div>
            <div className="p-2 bg-white/80 rounded-lg border border-amber-200 text-[10px] text-amber-900 leading-snug">
              <strong>Recommendation:</strong> Apply <span className="font-mono font-bold">Log Transform</span> or{' '}
              <span className="font-mono font-bold">Yeo-Johnson Power Transformation</span> to normalise this feature
              before training. The DAG Recipe Orchestrator will auto-configure this if your DAG supports it.
            </div>
          </div>

          {/* Card 2: Outlier Spike */}
          <div className={`p-4 rounded-xl border shadow-sm flex flex-col gap-2.5 ${
            (backendProfile?.outlier_pct ?? 2.1) > 1.5
              ? 'border-rose-300 bg-rose-50/30'
              : 'border-[#FF6B35]/30 bg-[#FF6B35]/08/20'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-bold text-slate-800">
                <Search size={14} className={(backendProfile?.outlier_pct ?? 2.1) > 1.5 ? 'text-rose-600' : 'text-[#FF6B35]'} />
                High Outlier Density
              </div>
              {(backendProfile?.outlier_pct ?? 2.1) > 1.5 ? (
                <span className="flex items-center gap-0.5 bg-rose-100 text-rose-700 text-[9px] font-bold px-1.5 py-0.5 rounded border border-rose-200">
                  <AlertTriangle size={9} /> ALERT
                </span>
              ) : (
                <span className="flex items-center gap-0.5 bg-[#FF6B35]/12 text-[#FF6B35] text-[9px] font-bold px-1.5 py-0.5 rounded border border-[#FF6B35]/20">
                  <CheckCircle size={9} /> OK
                </span>
              )}
            </div>
            <div className="text-slate-600 leading-snug">
              <span className="font-mono text-[10px] text-rose-700 font-bold">
                Outliers: {(backendProfile?.outlier_pct ?? 2.1).toFixed(1)}% of rows (IQR method)
              </span>
              <br />
              Threshold: &gt;1.5% outlier density can destabilise regression and anomaly models.
            </div>
            <div className="p-2 bg-white/80 rounded-lg border border-amber-200 text-[10px] text-amber-900 leading-snug">
              <strong>Recommendation:</strong> Use <span className="font-mono font-bold">Robust Scaler</span> (median + IQR)
              instead of StandardScaler. For anomaly detection, consider{' '}
              <span className="font-mono font-bold">One-Class SVM</span> or{' '}
              <span className="font-mono font-bold">Isolation Forest</span> as base learners.
            </div>
          </div>

          {/* Card 3: High Missingness */}
          <div className={`p-4 rounded-xl border shadow-sm flex flex-col gap-2.5 ${
            (backendProfile?.max_missing_pct ?? 7.3) > 5.0
              ? 'border-rose-300 bg-rose-50/30'
              : 'border-[#FF6B35]/30 bg-[#FF6B35]/08/20'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-bold text-slate-800">
                <AlertCircle size={14} className={(backendProfile?.max_missing_pct ?? 7.3) > 5.0 ? 'text-rose-600' : 'text-[#FF6B35]'} />
                High Missingness Detected
              </div>
              {(backendProfile?.max_missing_pct ?? 7.3) > 5.0 ? (
                <span className="flex items-center gap-0.5 bg-rose-100 text-rose-700 text-[9px] font-bold px-1.5 py-0.5 rounded border border-rose-200">
                  <AlertTriangle size={9} /> ALERT
                </span>
              ) : (
                <span className="flex items-center gap-0.5 bg-[#FF6B35]/12 text-[#FF6B35] text-[9px] font-bold px-1.5 py-0.5 rounded border border-[#FF6B35]/20">
                  <CheckCircle size={9} /> OK
                </span>
              )}
            </div>
            <div className="text-slate-600 leading-snug">
              <span className="font-mono text-[10px] text-rose-700 font-bold">
                Missing: {(backendProfile?.max_missing_pct ?? 7.3).toFixed(1)}% (column: {backendProfile?.most_missing_col ?? 'pressure_bar'})
              </span>
              <br />
              Threshold: &gt;5% missingness in a sensor column indicates sensor dropout or data loss events.
            </div>
            <div className="p-2 bg-white/80 rounded-lg border border-amber-200 text-[10px] text-amber-900 leading-snug">
              <strong>Recommendation:</strong> Apply <span className="font-mono font-bold">KNN Imputation</span> for
              non-temporal features or <span className="font-mono font-bold">Forward Fill</span> for time-indexed
              sensor streams. Flag the sensor for maintenance review.
            </div>
          </div>
        </div>
      </section>

      {/* 🧩 CROSS-COMPONENT MASTER CAUSAL CHAIN CARD */}
      <section className="dashboard-card border-indigo-200 bg-gradient-to-r from-indigo-50/70 via-slate-50 to-blue-50/70">
        <div className="card-header-row">
          <div className="card-title-group">
            <Workflow className="card-title-icon-wrapper text-indigo-600" size={18} />
            <h2 className="card-title">🧩 Cross-Component Unified Cause-and-Effect Analysis ("Why {dagId} Was Selected")</h2>
          </div>
          <span className="card-header-badge-blue bg-indigo-600">Cross-Component Flow</span>
        </div>

        <div className="p-3 bg-white/80 rounded-xl border border-indigo-100 text-slate-700 flex items-start gap-2">
          <Info size={16} className="text-indigo-600 flex-shrink-0 mt-0.5" />
          <span>
            <strong>What it shows:</strong> Connects the dots from raw file compilation to statistical profiling, explaining step-by-step why {dagId} was auto-recommended and how recipes auto-adjusted.
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
          <div className="p-3 bg-white rounded-xl border border-blue-200 shadow-sm space-y-1">
            <span className="font-bold text-blue-800 flex items-center gap-1">
              <Cpu size={12} />
              1. ⚙️ Compiler Step
            </span>
            <p className="text-slate-600 text-[10.5px]">Merged 5 sub-CSVs (+23% size growth). Detected 3.2% duplicate rows.</p>
          </div>

          <div className="p-3 bg-white rounded-xl border border-teal-200 shadow-sm space-y-1">
            <span className="font-bold text-teal-800 flex items-center gap-1">
              <Sliders size={12} />
              2. 📊 Profiler Step
            </span>
            <p className="text-slate-600 text-[10.5px]">Drift detected (KS=0.03). Imbalance: 35% ➔ 15%. Sparsity: 45% ➔ 68% zeros.</p>
          </div>

          <div className="p-3 bg-white rounded-xl border border-amber-200 shadow-sm space-y-1">
            <span className="font-bold text-amber-800 flex items-center gap-1">
              <Workflow size={12} />
              3. 🕸️ Orchestrator Step
            </span>
            <p className="text-slate-600 text-[10.5px]">Triggered DAG shift: DAG_001 ➔ {dagId} (Sparse? Yes ➔ Imbalanced? Yes).</p>
          </div>

          <div className="p-3 bg-white rounded-xl border border-purple-200 shadow-sm space-y-1">
            <span className="font-bold text-purple-800 flex items-center gap-1">
              <CheckCircle size={12} />
              4. 🧪 Recipe Step
            </span>
            <p className="text-slate-600 text-[10.5px]">Auto-adjusted imputation: Mean ➔ Median. Added SMOTE for class balance.</p>
          </div>
        </div>
      </section>

      {/* 📚 4 Core Steps Catalog Section */}
      {prePrepareSteps.map((step) => (
        <section key={step.id} className="dashboard-card">
          <div className="card-header-row">
            <div className="card-title-group">
              <FileText className="card-title-icon-wrapper" size={18} />
              <h2 className="card-title">{step.title}</h2>
            </div>
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
              step.badgeClass === 'badge-green' ? 'bg-[#FF6B35]/12 text-[#FF6B35]' : 'bg-[#FF6B35]/08 text-[#FF8F5A]'
            }`}>
              {step.badge}
            </span>
          </div>

          <div className="card-subtitle-row">
            <Info className="card-subtitle-icon" size={16} />
            <span>{step.description}</span>
          </div>

          {/* Grid of Visualization Plots for this Step */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {step.plots.map((plot) => (
              <div 
                key={plot.id}
                className={`p-3.5 bg-white rounded-xl border transition-all flex flex-col justify-between gap-2.5 shadow-sm ${
                  plot.flagged ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200 hover:border-blue-300'
                }`}
              >
                <div className="flex justify-between items-start gap-2 border-b border-slate-100 pb-2">
                  <div>
                    <div className="font-bold text-slate-800 text-[11.5px] truncate">
                      {plot.title}
                    </div>
                    <div className="text-[9.5px] text-slate-500 mt-0.5 font-normal">
                      <strong>Visualizes:</strong> Statistical distribution &amp; quality check for dataset telemetry.
                    </div>
                  </div>
                  {plot.flagged && (
                    <span className="bg-rose-100 text-rose-700 text-[9px] font-bold px-1.5 py-0.2 rounded border border-rose-200 flex-shrink-0 flex items-center gap-0.5">
                      <AlertTriangle size={9} /> Alert
                    </span>
                  )}
                </div>

                {/* SVG Visualization Canvas */}
                <div className="w-full h-[120px] bg-slate-50 rounded-lg p-1 overflow-hidden border border-slate-100">
                  <ChartRenderer type={plot.type} id={plot.id} flagged={plot.flagged} />
                </div>

                {/* Live Values Badge */}
                <div className="px-2 py-1 bg-slate-50 rounded-md border border-slate-100 flex flex-wrap gap-2 text-[9.5px] font-mono">
                  <span className="text-slate-700"><span>Check:</span> <strong>{plot.threshold}</strong></span>
                </div>

                {/* 1-Line Universal Explanation Banner */}
                <div className="p-2 bg-slate-50 rounded-lg border border-slate-100 text-[10px] text-slate-600 leading-snug flex items-start gap-1">
                  <Info size={12} className="text-blue-600 flex-shrink-0 mt-0.5" />
                  <span>{plot.exp}</span>
                </div>

                <div className="text-[9.5px] font-mono text-slate-400 border-t border-slate-100 pt-1.5 flex justify-between items-center">
                  <span>Threshold: {plot.threshold}</span>
                  <span className="text-slate-500 font-bold">#{plot.id}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {/* Jane Deliverables Handoff Approval Banner */}
      <div className="p-6 bg-gradient-to-r from-[#2B0063] to-[#461285] rounded-3xl text-white shadow-xl flex flex-col md:flex-row items-center justify-between gap-4 my-8 border border-white/10">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-[#E86326] flex items-center justify-center text-white text-2xl font-bold shadow-md">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
          </div>
          <div>
            <h3 className="font-headline font-bold text-base text-white flex items-center gap-2">
              Jane AI Handoff Approval
              <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-mono px-2 py-0.5 rounded-full border border-emerald-500/30">
                Prepared & Cleaned
              </span>
            </h3>
            <p className="text-xs text-white/70 font-mono mt-0.5">
              Dataset deliverables prepared with 27 features, 0 missing values, and validated SCADA temporal channels. Ready for ML Studio model training?
            </p>
          </div>
        </div>

        {onApproveDeliverables && (
          <button
            onClick={onApproveDeliverables}
            className="w-full md:w-auto px-6 py-3 bg-[#E86326] hover:bg-[#d4541c] text-white font-mono text-xs font-bold rounded-2xl shadow-lg transition-all active:scale-95 flex items-center justify-center gap-2 cursor-pointer shrink-0"
          >
            <span className="material-symbols-outlined text-base">verified</span>
            <span>Approve & Dispatch Deliverables to ML Studio</span>
          </button>
        )}
      </div>
    </div>
  );
};

export default PrePrepare;
