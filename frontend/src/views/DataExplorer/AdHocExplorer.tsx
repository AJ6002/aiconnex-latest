import React, { Suspense, lazy, useState, useEffect, ErrorInfo, ReactNode } from 'react';
import { BarChart2, Loader2, AlertCircle, Info, Sliders, TableIcon, TrendingUp, RefreshCw, Layers } from 'lucide-react';

// Lazy-load Graphic Walker with fallback handling
const GraphicWalkerComponent = lazy(() =>
  import('@kanaries/graphic-walker').then((mod) => ({
    default: mod.GraphicWalker || mod.default,
  }))
);

interface AdHocExplorerProps {
  compiledCsvPath?: string;
  runId?: string;
  dagId?: string;
  algorithmFamily?: string;
}

// ── Error Boundary for Graphic Walker ─────────────────────────────────────────
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class GraphicWalkerErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = { hasError: false };

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.warn('[AdHocExplorer] GraphicWalker renderer caught error:', error, errorInfo);
  }

  public handleRetry = (): void => {
    (this as unknown as React.Component<ErrorBoundaryProps, ErrorBoundaryState>).setState({ hasError: false, error: undefined });
  };

  public render(): ReactNode {
    const currentProps = (this as unknown as React.Component<ErrorBoundaryProps, ErrorBoundaryState>).props;
    const currentState = (this as unknown as React.Component<ErrorBoundaryProps, ErrorBoundaryState>).state;

    if (currentState && currentState.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-8 bg-slate-50 rounded-2xl border border-slate-200 min-h-[500px] text-center">
          <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center mb-3 text-amber-600">
            <AlertCircle size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-800 mb-1">Visual Explorer Engine Initializing</h3>
          <p className="text-xs text-slate-500 max-w-md mb-4">
            The multi-dimensional Graphic Walker canvas requires an active client connection or Web Worker.
          </p>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-2 px-4 py-2 bg-[#FF6B35] hover:bg-[#e05624] text-white text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer"
          >
            <RefreshCw size={14} /> Retry Loading Canvas
          </button>
        </div>
      );
    }
    return currentProps ? currentProps.children : null;
  }
}

// ── Lightweight CSV → IDataSet converter ──────────────────────────────────────
function parseCSVtoGWDataset(csvText: string): {
  fields: { fid: string; name: string; semanticType: 'quantitative' | 'nominal'; analyticType: 'measure' | 'dimension' }[];
  dataSource: Record<string, any>[];
} {
  const lines = csvText.trim().split('\n');
  const headers = lines[0].split(',').map((h) => h.trim().replace(/"/g, ''));

  const sampleLines = lines.slice(1, 5001); // cap at 5000 rows for smooth UI
  const dataSource = sampleLines.map((line) => {
    const vals = line.split(',');
    const row: Record<string, any> = {};
    headers.forEach((h, i) => {
      const raw = (vals[i] ?? '').trim().replace(/"/g, '');
      const num = parseFloat(raw);
      row[h] = isNaN(num) ? raw : num;
    });
    return row;
  });

  const fields = headers.map((h) => {
    const firstVal = dataSource[0]?.[h];
    const isNumeric = typeof firstVal === 'number';
    return {
      fid: h,
      name: h,
      semanticType: (isNumeric ? 'quantitative' : 'nominal') as 'quantitative' | 'nominal',
      analyticType: (isNumeric ? 'measure' : 'dimension') as 'measure' | 'dimension',
    };
  });

  return { fields, dataSource };
}

// ── Demo dataset (industrial telemetry) used when no real CSV is loaded ────────
const DEMO_FIELDS = [
  { fid: 'cycle', name: 'Cycle', semanticType: 'quantitative' as const, analyticType: 'dimension' as const },
  { fid: 'temp_celsius', name: 'Temp (°C)', semanticType: 'quantitative' as const, analyticType: 'measure' as const },
  { fid: 'vibration_index', name: 'Vibration', semanticType: 'quantitative' as const, analyticType: 'measure' as const },
  { fid: 'pressure_bar', name: 'Pressure (bar)', semanticType: 'quantitative' as const, analyticType: 'measure' as const },
  { fid: 'rpm', name: 'RPM', semanticType: 'quantitative' as const, analyticType: 'measure' as const },
  { fid: 'sensor_id', name: 'Sensor ID', semanticType: 'nominal' as const, analyticType: 'dimension' as const },
  { fid: 'anomaly_flag', name: 'Anomaly Flag', semanticType: 'nominal' as const, analyticType: 'dimension' as const },
];

const DEMO_DATA = Array.from({ length: 200 }, (_, i) => ({
  cycle: i + 1,
  temp_celsius: parseFloat((85 + Math.sin(i / 10) * 12 + Math.random() * 4).toFixed(2)),
  vibration_index: parseFloat((0.03 + Math.cos(i / 15) * 0.025 + Math.random() * 0.01).toFixed(4)),
  pressure_bar: parseFloat((14.5 + Math.sin(i / 8) * 2 + Math.random() * 0.5).toFixed(2)),
  rpm: Math.round(3000 + Math.cos(i / 12) * 400 + Math.random() * 100),
  sensor_id: `S-${(i % 5) + 1}`,
  anomaly_flag: i % 30 === 0 ? 'ANOMALY' : 'NOMINAL',
}));

export const AdHocExplorer: React.FC<AdHocExplorerProps> = ({
  compiledCsvPath,
  runId = 'run_20250115_143022',
  dagId = 'DAG_201',
  algorithmFamily = 'Anomaly Detection',
}) => {
  const [gwData, setGwData] = useState<{ fields: any[]; dataSource: any[] }>({
    fields: DEMO_FIELDS,
    dataSource: DEMO_DATA,
  });
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ready'>('ready');
  const [rowCount, setRowCount] = useState(DEMO_DATA.length);

  // Attempt to fetch real CSV from backend if supplied
  useEffect(() => {
    if (!compiledCsvPath) {
      setGwData({ fields: DEMO_FIELDS, dataSource: DEMO_DATA });
      setRowCount(DEMO_DATA.length);
      setLoadState('ready');
      return;
    }

    setLoadState('loading');
    fetch(`http://localhost:8000/api/v1/dataset?path=${encodeURIComponent(compiledCsvPath)}&rows=5000`)
      .then((res) => (res.ok ? res.text() : Promise.reject('backend unavailable')))
      .then((csvText) => {
        const parsed = parseCSVtoGWDataset(csvText);
        setGwData(parsed);
        setRowCount(parsed.dataSource.length);
        setLoadState('ready');
      })
      .catch(() => {
        // Fallback gracefully to demo telemetry data
        setGwData({ fields: DEMO_FIELDS, dataSource: DEMO_DATA });
        setRowCount(DEMO_DATA.length);
        setLoadState('ready');
      });
  }, [compiledCsvPath]);

  return (
    <div className="page-container font-sans text-xs">
      {/* ── Header Status Bar ────────────────────────────────────────────────── */}
      <section className="status-action-bar mb-4">
        <div className="status-bar-info">
          <div className="status-bar-icon-block">
            <Sliders size={20} />
          </div>
          <div className="status-bar-details">
            <div className="status-bar-title-row">
              <span className="font-semibold text-slate-800">Ad-Hoc Visual Explorer — Drag & Drop Pivot & Chart Builder</span>
              <span className="status-run-badge">
                <BarChart2 size={10} /> {runId}
              </span>
            </div>
            <div className="status-bar-parameters">
              <div className="param-item">
                <span>DAG:</span>
                <span className="highlight-orange font-bold font-mono">{dagId}</span>
              </div>
              <span>•</span>
              <div className="param-item">
                <span>Family:</span>
                <span className="highlight-green font-bold">{algorithmFamily}</span>
              </div>
              <span>•</span>
              <div className="param-item">
                <span>Rows Loaded:</span>
                <span className="highlight-blue font-bold font-mono">
                  {rowCount.toLocaleString()}
                  {!compiledCsvPath && <span className="text-amber-600 ml-1 font-normal">(demo)</span>}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Info Callout ─────────────────────────────────────────────────────── */}
      <section className="info-callout-banner mb-4">
        <Info size={18} className="info-banner-icon" />
        <div className="info-banner-text">
          <strong>Ad-Hoc Visual Query:</strong> Drag fields from the left panel onto X/Y channels to build dynamic scatter
          plots, bar charts, line trends, and pivot tables without writing SQL or Python.
          {!compiledCsvPath && (
            <span className="text-amber-700 ml-1 font-medium">
              — Displaying industrial sensor telemetry stream (200 records). Upload a custom dataset in Data Studio to explore your fleet.
            </span>
          )}
        </div>
      </section>

      {/* ── Quick Tips Bar ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="p-3 bg-white rounded-xl border border-blue-200 shadow-sm flex items-start gap-2">
          <TableIcon size={14} className="text-blue-600 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-bold text-slate-700 text-[11px]">1. Drag Dimensions & Measures</div>
            <div className="text-slate-500 text-[10px]">Drag variables onto Rows, Columns, Color, and Size encodings.</div>
          </div>
        </div>
        <div className="p-3 bg-white rounded-xl border border-[#FF6B35]/20 shadow-sm flex items-start gap-2">
          <TrendingUp size={14} className="text-[#FF6B35] mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-bold text-slate-700 text-[11px]">2. Switch Visual Marks</div>
            <div className="text-slate-500 text-[10px]">Toggle between Bar, Line, Scatter, Heatmap, and Correlation views.</div>
          </div>
        </div>
        <div className="p-3 bg-white rounded-xl border border-purple-200 shadow-sm flex items-start gap-2">
          <Layers size={14} className="text-purple-600 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-bold text-slate-700 text-[11px]">3. Pivot Grid Aggregations</div>
            <div className="text-slate-500 text-[10px]">Switch to Table mode to compute real-time sums, averages, and counts.</div>
          </div>
        </div>
      </div>

      {/* ── Graphic Walker Canvas with Suspense and ErrorBoundary ──────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden p-2" style={{ minHeight: '620px' }}>
        <GraphicWalkerErrorBoundary>
          <Suspense
            fallback={
              <div className="flex flex-col items-center justify-center min-h-[500px] gap-3">
                <Loader2 className="animate-spin text-[#FF6B35]" size={32} />
                <span className="text-slate-600 text-xs font-medium">Initializing Drag-and-Drop Visual Engine...</span>
              </div>
            }
          >
            {gwData && gwData.dataSource.length > 0 && (
              <GraphicWalkerComponent
                dataSource={gwData.dataSource}
                fields={gwData.fields}
                appearance="light"
              />
            )}
          </Suspense>
        </GraphicWalkerErrorBoundary>
      </div>
    </div>
  );
};

export default AdHocExplorer;
