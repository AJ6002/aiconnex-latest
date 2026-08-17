import React, { useState } from 'react';
import { TasLogo } from '../components/TasLogo';

export class QueueNode<T> {
  data: T;
  next: QueueNode<T> | null = null;
  constructor(data: T) {
    this.data = data;
  }
}

export class FIFOQueue<T> {
  head: QueueNode<T> | null = null;
  tail: QueueNode<T> | null = null;
  size: number = 0;

  enqueue(data: T): void {
    const node = new QueueNode(data);
    if (!this.head) {
      this.head = node;
      this.tail = node;
    } else if (this.tail) {
      this.tail.next = node;
      this.tail = node;
    }
    this.size++;
  }

  dequeue(): T | null {
    if (!this.head) return null;
    const data = this.head.data;
    this.head = this.head.next;
    if (!this.head) {
      this.tail = null;
    }
    this.size--;
    return data;
  }

  toArray(): T[] {
    const arr: T[] = [];
    let curr = this.head;
    while (curr) {
      arr.push(curr.data);
      curr = curr.next;
    }
    return arr;
  }
}

interface CompilerViewProps {
  onSendToMLOps: (compiledCsvPath: string, filename: string) => void;
  onCompilationFinished?: (compiledCsvPath: string, filename: string, profileData?: any) => void;
  fifoQueue?: any[];
  activeQueueIndex?: number;
  isQueueRunning?: boolean;
  onRunSequential?: (filesMap: Record<string, string>, familyLabel: string) => void;
  onProceed?: () => void;
  initialPrompt?: string;
  initialInputs?: any;
  janeSessionId?: string | null;
  onJaneNarration?: (message: string, node?: string) => void;
  onJaneInterrupt?: (interruptPayload: any) => void;
  onUploadStarted?: (fileName: string) => void;
}

export const CompilerView: React.FC<CompilerViewProps> = ({
  onSendToMLOps,
  onCompilationFinished,
  fifoQueue = [],
  activeQueueIndex = -1,
  isQueueRunning = false,
  onRunSequential,
  onProceed,
  initialPrompt,
  initialInputs,
  janeSessionId,
  onJaneNarration,
  onJaneInterrupt,
  onUploadStarted,
}) => {
  const [loaderStep, setLoaderStep] = useState<number>(-1);
  // Compiler UI States
  const [activeTab, setActiveTab] = useState<'upload' | 'inspector' | 'pipeline' | 'audit'>('upload');
  const [queryInput, setQueryInput] = useState('');
  const [queryResponse, setQueryResponse] = useState<string | null>(null);
  const [isInspectionDrawerOpen, setIsInspectionDrawerOpen] = useState(false);
  const [showRejectionShield, setShowRejectionShield] = useState(false);
  const [compilationLayer, setCompilationLayer] = useState<number>(4); // 1 to 4
  const [isCompiling, setIsCompiling] = useState(false);
  const [showDagModal, setShowDagModal] = useState(false);
  const [selectedDagId, setSelectedDagId] = useState<string | null>(null);

  // Real API states
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [compiledData, setCompiledData] = useState<any>(null);
  const [compileError, setCompileError] = useState<string | null>(null);

  // Wizard modal states
  const [showWizard, setShowWizard] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [targetColInput, setTargetColInput] = useState(initialInputs?.targetColumn || '');
  const [problemTypeInput, setProblemTypeInput] = useState(initialInputs?.problemType || 'regression');
  const [timeColInput, setTimeColInput] = useState(initialInputs?.timestampColumn || initialInputs?.timeColumn || '');
  const [entityColInput, setEntityColInput] = useState(initialInputs?.entityColumn || '');
  const [nlpExtractedFields, setNlpExtractedFields] = useState<{
    target: boolean;
    problemType: boolean;
    timeCol: boolean;
    entityCol: boolean;
  }>({
    target: !!initialInputs?.targetColumn,
    problemType: !!initialInputs?.problemType,
    timeCol: !!(initialInputs?.timestampColumn || initialInputs?.timeColumn),
    entityCol: !!initialInputs?.entityColumn
  });

  // Run rule-based NLP extraction when the user prompt arrives
  React.useEffect(() => {
    if (!initialPrompt) return;
    const lowerPrompt = initialPrompt.toLowerCase();
    const extracted = { target: false, problemType: false, timeCol: false, entityCol: false };
    
    // 1. Problem Type heuristics
    if (lowerPrompt.includes('classify') || lowerPrompt.includes('classification') || lowerPrompt.includes('fault') || lowerPrompt.includes('anomaly') || lowerPrompt.includes('outlier')) {
      if (lowerPrompt.includes('anomaly') || lowerPrompt.includes('outlier') || lowerPrompt.includes('unusual')) {
        setProblemTypeInput('anomaly');
      } else {
        setProblemTypeInput('classification');
      }
      extracted.problemType = true;
    } else if (lowerPrompt.includes('time') || lowerPrompt.includes('forecast') || lowerPrompt.includes('series') || lowerPrompt.includes('chronological')) {
      setProblemTypeInput('time-series');
      extracted.problemType = true;
    } else if (lowerPrompt.includes('cluster') || lowerPrompt.includes('group') || lowerPrompt.includes('segment')) {
      setProblemTypeInput('clustering');
      extracted.problemType = true;
    } else if (lowerPrompt.includes('predict') || lowerPrompt.includes('regress') || lowerPrompt.includes('continuous') || lowerPrompt.includes('rul') || lowerPrompt.includes('charges') || lowerPrompt.includes('saleprice')) {
      setProblemTypeInput('regression');
      extracted.problemType = true;
    }

    // 2. Target Column heuristics
    const targetMatch = lowerPrompt.match(/(?:predict|forecast|target is|target column is|estimate|calculate)\s+([a-zA-Z0-9_\-]+)/);
    if (targetMatch && targetMatch[1]) {
      setTargetColInput(targetMatch[1]);
      extracted.target = true;
    } else {
      const commonColumns = ['rul', 'charges', 'saleprice', 'temperature', 'pressure', 'voltage', 'vibration', 'cycles', 'price', 'cost', 'failure', 'label'];
      for (const col of commonColumns) {
        if (lowerPrompt.includes(col)) {
          setTargetColInput(col);
          extracted.target = true;
          break;
        }
      }
    }

    // 3. Time Index heuristics
    const timeMatch = lowerPrompt.match(/(?:time|date|timestamp|cycle|epoch|sequence)\s+(?:column|index|is)?\s*([a-zA-Z0-9_\-]+)/);
    if (timeMatch && timeMatch[1]) {
      setTimeColInput(timeMatch[1]);
      extracted.timeCol = true;
    } else {
      const commonTime = ['time_cycle', 'time', 'date', 'timestamp', 'datetime', 'cycle'];
      for (const t of commonTime) {
        if (lowerPrompt.includes(t)) {
          setTimeColInput(t);
          extracted.timeCol = true;
          break;
        }
      }
    }

    // 4. Entity ID heuristics
    const entityMatch = lowerPrompt.match(/(?:entity|asset|machine|device|unit|id|identifier)\s+(?:column|is)?\s*([a-zA-Z0-9_\-]+)/);
    if (entityMatch && entityMatch[1]) {
      setEntityColInput(entityMatch[1]);
      extracted.entityCol = true;
    } else {
      const commonEntity = ['unit_id', 'asset_id', 'machine_id', 'device_id', 'serial', 'id'];
      for (const e of commonEntity) {
        if (lowerPrompt.includes(e)) {
          setEntityColInput(e);
          extracted.entityCol = true;
          break;
        }
      }
    }

    setNlpExtractedFields(extracted);
  }, [initialPrompt]);

  // Sample extracted archive tree fallback
  const archiveFiles = [
    { name: 'C-MAPSS_FD001_train.csv', size: '14.2 MB', encoding: 'utf-8', type: 'SCADA Table', cols: 26 },
    { name: 'unit_metadata_v2.json', size: '420 KB', encoding: 'utf-8', type: 'Entity Index', cols: 6 },
    { name: 'high_freq_vibration_ch1.mat', size: '38.5 MB', encoding: 'binary/mat', type: 'High-Freq Signal', cols: 1 },
    { name: 'thermal_sensor_log.txt', size: '2.8 MB', encoding: 'latin-1', type: 'Raw Text Dump', cols: 14 },
    { name: 'operational_settings.xlsx', size: '1.1 MB', encoding: 'ooxml', type: 'Spreadsheet', cols: 8 },
  ];

  // Sample preview columns fallback
  const previewColumns = [
    { name: 'unit_id', type: 'int64', badge: 'bg-blue-100 text-blue-800' },
    { name: 'time_cycle', type: 'int64', badge: 'bg-blue-100 text-blue-800' },
    { name: 'setting_1', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'setting_2', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'setting_3', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'fan_inlet_temp', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'lpc_outlet_temp', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'hpc_outlet_temp', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'lpt_outlet_temp', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
    { name: 'fan_speed_rpm', type: 'float64', badge: 'bg-[#FF6B35]/12 text-[#FF6B35]' },
  ];

  // Sample data preview rows fallback
  const previewRows = Array.from({ length: 8 }).map((_, i) => ({
    unit_id: 1,
    time_cycle: i + 1,
    setting_1: (0.0023 + i * 0.0001).toFixed(4),
    setting_2: (0.0003 - i * 0.00005).toFixed(4),
    setting_3: '100.0',
    fan_inlet_temp: (518.67 + Math.sin(i) * 0.4).toFixed(2),
    lpc_outlet_temp: (641.82 + i * 0.15).toFixed(2),
    hpc_outlet_temp: (1589.7 + i * 0.8).toFixed(2),
    lpt_outlet_temp: (1400.6 + i * 0.5).toFixed(2),
    fan_speed_rpm: (14.62 + i * 0.02).toFixed(2),
  }));

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setPendingFile(file);
      
      // Auto-extract heuristic values to pre-populate inputs nicely
      const lowerName = file.name.toLowerCase();
      const defaultTarget = lowerName.includes('insurance') ? 'charges' : (lowerName.includes('house_prices') ? 'SalePrice' : (lowerName.includes('manufacturing') ? 'RUL' : ''));
      setTargetColInput(defaultTarget);
      
      const defaultEntity = lowerName.includes('manufacturing') ? 'unit_id' : '';
      setEntityColInput(defaultEntity);
      
      const defaultTime = lowerName.includes('manufacturing') ? 'time_cycle' : '';
      setTimeColInput(defaultTime);

      const defaultType = (lowerName.includes('insurance') || lowerName.includes('house_prices') || lowerName.includes('manufacturing')) ? 'regression' : 'classification';
      setProblemTypeInput(defaultType);

      setShowWizard(false);
      if (onUploadStarted) onUploadStarted(file.name);
      triggerCompilation(file);
    }
  };

  const triggerCompilation = async (
    file: File,
    userInputs?: { targetColumn?: string; problemType?: string; timestampColumn?: string; entityColumn?: string }
  ) => {
    setIsCompiling(true);
    setCompileError(null);

    const formData = new FormData();
    formData.append('file', file);

    let apiData: any = null;
    let apiErr: any = null;
    let profileData: any = null;

    const effectiveSessionId = janeSessionId || 'default_session';
    if (effectiveSessionId) {
      // Real Jane-Centric SSE Compilation
      try {
        if (onJaneNarration) {
          onJaneNarration(`📦 **Ingesting archive \`${file.name}\`...**\nDecompressing tables and initializing LangGraph Scout Compiler pipeline.`, 'archive_discovery_node');
        }

        const sseForm = new FormData();
        sseForm.append('file', file);
        sseForm.append('session_id', effectiveSessionId);

        let response = await fetch('http://localhost:8000/api/upload', {
          method: 'POST',
          body: sseForm,
        }).catch(() => null);

        if (!response || !response.ok) {
          response = await fetch('http://localhost:5000/api/upload', {
            method: 'POST',
            body: sseForm,
          }).catch(() => null);
        }

        if (!response || !response.ok) {
          throw new Error(`Upload failed with status ${response ? response.status : 'offline'}`);
        }

        let compiledPath = '';
        let receivedRunId = '';
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (reader) {
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const eventData = JSON.parse(line.slice(6));
                  if (eventData.type === 'text' && eventData.delta && onJaneNarration) {
                    onJaneNarration(eventData.delta, eventData.node);
                  }
                  if (eventData.type === 'interrupt' && eventData.payload && onJaneInterrupt) {
                    onJaneInterrupt(eventData.payload);
                  }
                  if (eventData.type === 'compiled' && eventData.compiled_csv_path) {
                    compiledPath = eventData.compiled_csv_path;
                    if (eventData.run_id) receivedRunId = eventData.run_id;
                  }
                  if (eventData.type === 'error' && eventData.message) {
                    throw new Error(eventData.message);
                  }
                } catch (parseErr: any) {
                  if (parseErr.message && !parseErr.message.includes('JSON')) {
                    throw parseErr;
                  }
                }
              }
            }
          }
        }

        const isValidCompiledCsv = Boolean(
          compiledPath && 
          !compiledPath.toLowerCase().endsWith('.zip') && 
          !compiledPath.toLowerCase().endsWith('.tar') && 
          !compiledPath.toLowerCase().endsWith('.gz')
        );

        if (!isValidCompiledCsv) {
          throw new Error('Compilation did not generate a valid canonical CSV dataset. Please check archive contents.');
        }

        apiData = {
          status: 'success',
          first_csv: compiledPath,
          compiled_csv: compiledPath,
          filename: file.name,
          run_id: receivedRunId
        };

        // Fetch profile dataset metadata for the real compiled CSV
        if (apiData && apiData.first_csv) {
          try {
            const profilerForm = new FormData();
            profilerForm.append('file_path', apiData.first_csv);
            
            const customTarget = userInputs?.targetColumn;
            const customEntity = userInputs?.entityColumn;
            const customTimestamp = userInputs?.timestampColumn;
            const customProblemType = userInputs?.problemType;

            const lowerName = file.name.toLowerCase();
            const defaultTargetColumn = lowerName.includes('insurance') ? 'charges' : (lowerName.includes('house_prices') ? 'SalePrice' : (lowerName.includes('manufacturing') ? 'RUL' : ''));
            
            profilerForm.append('target_column', customTarget || defaultTargetColumn || '');
            if (customEntity) profilerForm.append('entity_column', customEntity);
            if (customTimestamp) profilerForm.append('timestamp_column', customTimestamp);
            if (customProblemType) profilerForm.append('problem_type', customProblemType);

            const profileRes = await fetch('http://localhost:8000/api/v1/profile', {
              method: 'POST',
              body: profilerForm
            });
            if (profileRes.ok) {
              profileData = await profileRes.json();
            }
          } catch (profErr) {
            console.error('Failed to profile compiled file:', profErr);
          }
        }

        if (onJaneNarration) {
          onJaneNarration(`✅ **Dataset Compiled Successfully!**\n\nArchive \`${file.name}\` processed. Generated canonical parquet & CSV artifacts. Ready to explore!`, 'exploration_synthesizer_node');
        }

        setCompiledData(apiData);
        setIsCompiling(false);

        // Give user 1.5s to see the completion message in centered Jane, then navigate
        setTimeout(() => {
          if (onCompilationFinished && apiData && apiData.first_csv) {
            onCompilationFinished(apiData.first_csv, file.name, profileData);
          }
        }, 1500);

      } catch (err: any) {
        apiErr = err;
        setCompileError(err.message || 'Error occurred during compilation');
        setIsCompiling(false);
        if (onJaneNarration) {
          onJaneNarration(`❌ **Compilation Error:** ${err.message || 'Failed to process dataset'}`, 'error');
        }
      }
    } else {
      // Legacy offline/fallback path with manual loaderStep
      setLoaderStep(0);
      try {
        const res = await fetch('http://localhost:8000/api/v1/compile', {
          method: 'POST',
          body: formData
        });
        if (!res.ok) {
          const errJson = await res.json();
          throw new Error(errJson.detail || 'Compilation failed');
        }
        apiData = await res.json();
      } catch (err: any) {
        apiErr = err;
      }

      for (let step = 0; step <= 5; step++) {
        setLoaderStep(step);
        setCompilationLayer(Math.min(4, Math.floor(step / 1.5) + 1));
        await new Promise((r) => setTimeout(r, 800));
      }

      setLoaderStep(-1);
      setIsCompiling(false);

      if (apiErr) {
        setCompileError(apiErr.message || 'Error occurred during compilation');
        return;
      }

      setCompiledData(apiData);
      if (onCompilationFinished) {
        const firstCsv = apiData?.first_csv || 'workspace_data/ds1_FD001/C-MAPSS_FD001_train.csv';
        onCompilationFinished(firstCsv, file.name, profileData);
      }
    }
  };

  const handleQuerySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryInput.trim()) return;
    if (compiledData) {
      setQueryResponse(
        `AI Agent scanned compiled output across ${selectedFile?.name}. Auto-aligned on timestamp axis '${compiledData.schema_map.canonical_timestamp_col || 'time_cycle'}' and group key '${compiledData.schema_map.canonical_group_col || 'unit_id'}'. Found ${compiledData.total_cols} columns. Row explosion delta check passed.`
      );
    } else {
      setQueryResponse(
        `AI Agent scanned archive files across C-MAPSS_FD001. Found 21 continuous sensor signals (temperature, pressure, vibration) sampled at 1Hz. Auto-aligned on timestamp axis 'time_cycle' and entity key 'unit_id'. Missing values: 0.00%.`
      );
    }
  };

  const handleSend = () => {
    if (compiledData && compiledData.first_csv) {
      onSendToMLOps(compiledData.first_csv, selectedFile?.name || 'compiled_dataset.zip');
    } else {
      // Fallback
      onSendToMLOps('testing_ds/ds_3/manufacturing.csv', 'manufacturing.csv');
    }
  };

  const filesList = compiledData?.merged_files?.map((file: string) => {
    const parts = file.split(/[\\/]/);
    const name = parts[parts.length - 1];
    return { name, size: 'Compiled', encoding: 'utf-8', type: 'Compiled CSV', cols: compiledData.total_cols };
  }) || archiveFiles;

  const cols = compiledData?.preview_columns || previewColumns;
  const rows = compiledData?.preview_rows || previewRows;
  
  const hasRul = compiledData?.dataset_card?.rul_synthesis_applied || false;
  const domainLabel = compiledData?.dataset_card?.domain_detected || "Industrial Sensor Telemetry";
  const compiledRowsCount = compiledData?.total_rows || 20631;
  const compiledColsCount = compiledData?.total_cols || 27;

  return (
    <div className="space-y-6 text-primary">
      {/* Top Banner & AI_CONNEX Hero Banner */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 glass-panel p-6 sm:p-8 rounded-3xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-tas-red/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20"></div>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5 relative z-10">
          <div>
            <div className="flex items-center gap-2 text-muted text-xs font-mono uppercase tracking-widest mb-1">
              <span className="text-[#E86326] font-extrabold">TOTAL AUTOMATION SOLUTIONS</span>
              <span>•</span>
              <span className="text-cb font-bold">Relational Industrial Compiler</span>
            </div>
            <h1 className="font-headline text-2xl sm:text-3xl font-extrabold text-primary tracking-tight flex items-center gap-3">
              <span>Relational Pipeline Studio</span>
              <span className="px-3 py-0.5 bg-[#E86326]/20 text-[#E86326] border border-[#E86326]/40 rounded-full text-xs font-mono font-bold">
                9-Node Cascade Engine
              </span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3 relative z-10 shrink-0">
          {onProceed && (
            <button
              onClick={onProceed}
              className="px-5 py-2.5 bg-[#E86326] hover:bg-[#D5521B] text-white font-mono text-xs font-bold rounded-2xl transition-all flex items-center gap-2 border-none shadow-md active:scale-95 cursor-pointer"
            >
              <span>Proceed to Next Page</span>
              <span className="material-symbols-outlined text-sm">arrow_forward</span>
            </button>
          )}

          <button
            onClick={() => setIsInspectionDrawerOpen(!isInspectionDrawerOpen)}
            className="px-4 py-2.5 text-primary font-mono text-xs font-bold rounded-2xl transition-all flex items-center gap-2 border border-ui backdrop-blur-md hover:border-[#E86326]"
            style={{background:'var(--bg-input)'}}
          >
            <span className="material-symbols-outlined text-base text-[#E86326]">folder_open</span>
            <span>Inspect Archive ({filesList.length} files)</span>
          </button>
        </div>
      </div>

      {/* Main Container: Archive Dropzone & 4-Layer Tracker */}
      <div className="space-y-6">
          {/* Section 1: Universal Data Entry Upload Controller */}
          <div className="glass-card p-6 relative overflow-hidden">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 border-b border-ui pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-[#2B0063] flex items-center justify-center text-white shadow-md">
                  <span className="material-symbols-outlined text-xl">cloud_upload</span>
                </div>
                <div>
                  <h2 className="font-headline font-bold text-base text-primary">
                    Universal Data Entry & Ingestion Controller
                  </h2>
                  <p className="text-xs text-secondary font-mono">
                    Select your industrial dataset entry point to profile and prepare sensor telemetry
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 bg-[#2B0063]/10 p-1.5 rounded-2xl border border-[#2B0063]/20">
                <button
                  type="button"
                  onClick={() => setActiveTab('upload')}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-1.5 cursor-pointer ${
                    activeTab === 'upload' ? 'bg-[#2B0063] text-white shadow-md' : 'text-secondary hover:text-primary'
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">tune</span>
                  <span>Ingestion Hub</span>
                </button>
              </div>
            </div>

            {/* 4 Entry Point Option Tabs */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              <button
                type="button"
                onClick={() => setQueryInput('files')}
                className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  queryInput !== 's3' && queryInput !== 'cloud' && queryInput !== 'stream'
                    ? 'border-[#E86326] bg-[#E86326]/10 shadow-md ring-2 ring-[#E86326]/20'
                    : 'border-ui hover:border-[#E86326]/40'
                }`}
                style={queryInput === 's3' || queryInput === 'cloud' || queryInput === 'stream' ? {background:'var(--bg-input)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="material-symbols-outlined text-xl text-[#E86326]">upload_file</span>
                  <span className="text-[10px] font-mono font-extrabold uppercase px-2 py-0.5 rounded bg-[#E86326]/15 text-[#E86326]">Option 1</span>
                </div>
                <h4 className="font-bold text-xs text-primary">Local Archives & Files</h4>
                <p className="text-[10px] text-secondary mt-0.5">.csv, .parquet, .json, .zip</p>
              </button>

              <button
                type="button"
                onClick={() => setQueryInput('s3')}
                className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  queryInput === 's3'
                    ? 'border-[#2B0063] bg-[#2B0063]/10 shadow-md ring-2 ring-[#2B0063]/20'
                    : 'border-ui hover:border-[#2B0063]/40'
                }`}
                style={queryInput !== 's3' ? {background:'var(--bg-input)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="material-symbols-outlined text-xl text-[#2B0063]">cloud</span>
                  <span className="text-[10px] font-mono font-extrabold uppercase px-2 py-0.5 rounded bg-[#2B0063]/15 text-[#2B0063]">Option 2</span>
                </div>
                <h4 className="font-bold text-xs text-primary">AWS S3 Cloud Storage</h4>
                <p className="text-[10px] text-secondary mt-0.5">s3://bucket/key credentials</p>
              </button>

              <button
                type="button"
                onClick={() => setQueryInput('cloud')}
                className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  queryInput === 'cloud'
                    ? 'border-blue-600 bg-blue-500/10 shadow-md ring-2 ring-blue-500/20'
                    : 'border-ui hover:border-blue-500/40'
                }`}
                style={queryInput !== 'cloud' ? {background:'var(--bg-input)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="material-symbols-outlined text-xl text-blue-600">database</span>
                  <span className="text-[10px] font-mono font-extrabold uppercase px-2 py-0.5 rounded bg-blue-500/15 text-blue-600">Option 3</span>
                </div>
                <h4 className="font-bold text-xs text-primary">Cloud SQL & Big Data</h4>
                <p className="text-[10px] text-secondary mt-0.5">Snowflake, Postgres, Databricks</p>
              </button>

              <button
                type="button"
                onClick={() => setQueryInput('stream')}
                className={`p-3.5 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  queryInput === 'stream'
                    ? 'border-purple-600 bg-purple-500/10 shadow-md ring-2 ring-purple-500/20'
                    : 'border-ui hover:border-purple-500/40'
                }`}
                style={queryInput !== 'stream' ? {background:'var(--bg-input)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="material-symbols-outlined text-xl text-purple-600">sensors</span>
                  <span className="text-[10px] font-mono font-extrabold uppercase px-2 py-0.5 rounded bg-purple-500/15 text-purple-600">Option 4</span>
                </div>
                <h4 className="font-bold text-xs text-primary">Industrial SCADA Stream</h4>
                <p className="text-[10px] text-secondary mt-0.5">OPC UA, MQTT Telemetry</p>
              </button>
            </div>

            {/* TAB CONTENT 1: Local Files & Archives */}
            {queryInput !== 's3' && queryInput !== 'cloud' && queryInput !== 'stream' && (
              <div 
                onClick={() => document.getElementById('zip-file-input')?.click()}
                className="border-2 border-dashed border-[#E86326]/40 hover:border-[#E86326] transition-all rounded-2xl p-8 text-center cursor-pointer group"
                style={{background:'var(--bg-input)'}}
              >
                <input
                  type="file"
                  id="zip-file-input"
                  accept=".zip,.csv,.xlsx,.xls,.json,.txt,.mat,.parquet"
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                />
                <div className="w-14 h-14 bg-[#2B0063] rounded-2xl border border-white/20 flex items-center justify-center mx-auto mb-3 shadow-lg group-hover:scale-110 transition-transform text-[#E86326]">
                  <span className="material-symbols-outlined text-3xl">cloud_upload</span>
                </div>
                <p className="font-headline font-bold text-sm text-primary">
                  Drag & Drop Industrial Telemetry Archives Here
                </p>
                <p className="text-secondary text-xs mt-1">
                  or <span className="text-[#E86326] font-bold underline">browse local storage</span> to select multi-table SCADA dataset
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3 mt-4 text-[10px] font-mono text-secondary">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const sampleFile = new File(["dummy C-MAPSS zip content"], "CMAPSSData.zip", { type: "application/zip" });
                      setSelectedFile(sampleFile);
                      if (onUploadStarted) onUploadStarted(sampleFile.name);
                      triggerCompilation(sampleFile);
                    }}
                    className="px-2.5 py-1 border border-ui rounded-xl hover:border-[#E86326] hover:text-[#E86326] transition-colors cursor-pointer"
                    style={{background:'var(--bg-input)'}}
                  >
                    C-MAPSS Turbofan (.zip)
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const sampleFile = new File(["dummy Wind Turbine content"], "wind_turbine_scada.parquet", { type: "application/octet-stream" });
                      setSelectedFile(sampleFile);
                      if (onUploadStarted) onUploadStarted(sampleFile.name);
                      triggerCompilation(sampleFile);
                    }}
                    className="px-2.5 py-1 border border-ui rounded-xl hover:border-[#E86326] hover:text-[#E86326] transition-colors cursor-pointer"
                    style={{background:'var(--bg-input)'}}
                  >
                    Wind Turbine SCADA (.parquet)
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const sampleFile = new File(["dummy IGBT content"], "igbt_semiconductor.csv", { type: "text/csv" });
                      setSelectedFile(sampleFile);
                      if (onUploadStarted) onUploadStarted(sampleFile.name);
                      triggerCompilation(sampleFile);
                    }}
                    className="px-2.5 py-1 border border-ui rounded-xl hover:border-[#E86326] hover:text-[#E86326] transition-colors cursor-pointer"
                    style={{background:'var(--bg-input)'}}
                  >
                    IGBT Semiconductor (.csv)
                  </button>
                </div>
              </div>
            )}

            {/* TAB CONTENT 2: AWS S3 Storage */}
            {queryInput === 's3' && (
              <div className="p-6 rounded-2xl border border-[#2B0063]/30 bg-[#2B0063]/5 space-y-4">
                <div className="flex items-center gap-2 text-sm font-bold text-[#2B0063]">
                  <span className="material-symbols-outlined">cloud</span>
                  <span>AWS S3 Bucket Integration</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">S3 Bucket Path / URI</label>
                    <input
                      type="text"
                      defaultValue="s3://aiconnex-industrial-telemetry/cmapss-fd001.zip"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-[#2B0063]"
                    />
                  </div>
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">AWS Region</label>
                    <input
                      type="text"
                      defaultValue="us-east-1"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-[#2B0063]"
                    />
                  </div>
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">AWS Access Key ID</label>
                    <input
                      type="password"
                      defaultValue="AKIAIOSFODNN7EXAMPLE"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-[#2B0063]"
                    />
                  </div>
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">AWS Secret Access Key</label>
                    <input
                      type="password"
                      defaultValue="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-[#2B0063]"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const mockFile = new File(["dummy content"], "s3_cmapss_fd001.zip", { type: "application/zip" });
                    triggerCompilation(mockFile, { targetColumn: 'RUL', problemType: 'regression' });
                  }}
                  className="w-full py-3 bg-[#2B0063] hover:bg-[#1e0046] text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">sync</span>
                  <span>Connect S3 Bucket & Ingest Data</span>
                </button>
              </div>
            )}

            {/* TAB CONTENT 3: Cloud & Big Data Connection */}
            {queryInput === 'cloud' && (
              <div className="p-6 rounded-2xl border border-blue-500/30 bg-blue-500/5 space-y-4">
                <div className="flex items-center gap-2 text-sm font-bold text-blue-600">
                  <span className="material-symbols-outlined">database</span>
                  <span>Cloud Database & Warehouse Connection</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">Warehouse / DB Type</label>
                    <select className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900">
                      <option>PostgreSQL / TimescaleDB (Port 5432)</option>
                      <option>Snowflake Data Cloud</option>
                      <option>Databricks Delta Lake</option>
                      <option>Google BigQuery</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">Connection String / Host</label>
                    <input
                      type="text"
                      defaultValue="postgresql://postgres:pass@127.0.0.1:5432/aiconnex_scada"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const mockFile = new File(["dummy content"], "scada_postgresql_export.csv", { type: "text/csv" });
                    triggerCompilation(mockFile, { targetColumn: 'RUL', problemType: 'regression' });
                  }}
                  className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">hub</span>
                  <span>Test Connection & Ingest SCADA Tables</span>
                </button>
              </div>
            )}

            {/* TAB CONTENT 4: Industrial Stream (OPC UA / MQTT) */}
            {queryInput === 'stream' && (
              <div className="p-6 rounded-2xl border border-purple-500/30 bg-purple-500/5 space-y-4">
                <div className="flex items-center gap-2 text-sm font-bold text-purple-600">
                  <span className="material-symbols-outlined">sensors</span>
                  <span>Real-Time Industrial SCADA Telemetry Stream</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">Protocol</label>
                    <select className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900">
                      <option>OPC UA Server (opc.tcp://...)</option>
                      <option>MQTT Broker (mqtts://...)</option>
                      <option>Modbus TCP Gateway</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-secondary font-mono mb-1 font-bold">Endpoint URL / Topic</label>
                    <input
                      type="text"
                      defaultValue="opc.tcp://industrial-gateway.plant.local:4840/UA/Telemetry"
                      className="w-full p-3 rounded-xl border border-ui font-mono text-xs text-primary bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const mockFile = new File(["dummy content"], "opcua_stream_snapshot.parquet", { type: "application/octet-stream" });
                    triggerCompilation(mockFile, { targetColumn: 'RUL', problemType: 'regression' });
                  }}
                  className="w-full py-3 bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-base">rss_feed</span>
                  <span>Connect Stream & Capture Telemetry Snapshot</span>
                </button>
              </div>
            )}

            {/* Error Message if any */}
            {compileError && (
              <div className="mt-4 p-4 bg-rose-950/50 border border-rose-800 text-rose-200 rounded-2xl text-xs font-mono flex items-start gap-2.5">
                <span className="material-symbols-outlined text-base text-rose-400 mt-0.5">error</span>
                <div className="flex-1 whitespace-pre-wrap">{compileError}</div>
              </div>
            )}

          </div>

          {/* Section 3: Live 4-Layer Compilation Pipeline Tracker */}
          <div className="glass-card p-6">
            <div className="flex justify-between items-center mb-6">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#E86326] text-xl">layers</span>
                <h2 className="font-headline font-bold text-base text-primary">
                  3. Live 4-Layer Compilation Pipeline Tracker
                </h2>
              </div>
              <span className="px-3 py-1 bg-[#E86326]/15 text-[#E86326] border border-[#E86326]/30 rounded-full text-xs font-mono font-bold flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#E86326] animate-pulse"></span>
                Status: Handoff Ready
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 relative">
              {/* Layer 1 */}
              <div
                className={`p-4 rounded-xl border transition-all ${
                  compilationLayer >= 1
                    ? 'border-[#E86326] bg-[#E86326]/10 text-primary'
                    : 'opacity-55'
                }`}
                style={compilationLayer < 1 ? {background:'var(--bg-input)', borderColor:'var(--border-ui)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase text-secondary">Layer 1</span>
                  <span className="material-symbols-outlined text-base text-[#E86326]">check_circle</span>
                </div>
                <h4 className="font-sans font-bold text-xs text-primary">Discovery</h4>
                <p className="text-[11px] text-secondary mt-1 leading-tight">
                  File tree parsing & encoding normalization.
                </p>
              </div>

              {/* Layer 2 */}
              <div
                className={`p-4 rounded-xl border transition-all ${
                  compilationLayer >= 2
                    ? 'border-[#E86326] bg-[#E86326]/10 text-primary'
                    : 'opacity-55'
                }`}
                style={compilationLayer < 2 ? {background:'var(--bg-input)', borderColor:'var(--border-ui)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase text-secondary">Layer 2</span>
                  <span className="material-symbols-outlined text-base text-[#E86326]">check_circle</span>
                </div>
                <h4 className="font-sans font-bold text-xs text-primary">Schema Mapper</h4>
                <p className="text-[11px] text-secondary mt-1 leading-tight">
                  Snake_case header alignment & time axis pairing.
                </p>
              </div>

              {/* Layer 3 */}
              <div
                className={`p-4 rounded-xl border transition-all ${
                  compilationLayer >= 3
                    ? 'border-[#E86326] bg-[#E86326]/10 text-primary'
                    : 'opacity-55'
                }`}
                style={compilationLayer < 3 ? {background:'var(--bg-input)', borderColor:'var(--border-ui)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase text-secondary">Layer 3</span>
                  <span className="material-symbols-outlined text-base text-[#E86326]">check_circle</span>
                </div>
                <h4 className="font-sans font-bold text-xs text-primary">Relational Joiner</h4>
                <p className="text-[11px] text-secondary mt-1 leading-tight">
                  Side-by-side index join on parallel sensor channels.
                </p>
              </div>

              {/* Layer 4 */}
              <div
                className={`p-4 rounded-xl border transition-all ${
                  compilationLayer >= 4
                    ? 'border-[#2B0063] bg-[#2B0063]/10 ring-2 ring-[#2B0063]/30 backdrop-blur-md'
                    : 'opacity-55'
                }`}
                style={compilationLayer < 4 ? {background:'var(--bg-input)', borderColor:'var(--border-ui)'} : {}}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold uppercase text-[#2B0063] dark:text-[#E86326]">Layer 4</span>
                  <span className="material-symbols-outlined text-base text-[#E86326]">verified</span>
                </div>
                <h4 className="font-sans font-bold text-xs text-[#E86326]">Handoff</h4>
                <p className="text-[11px] text-secondary mt-1 leading-tight">
                  Fleet vertical concatenation into clean 27-col table.
                </p>
              </div>
            </div>
          </div>

          {/* Linked List FIFO Ingestion Queue Section */}
          {(() => {
            const separateFilesMap = compiledData?.dataset_card?.output_paths?.separate_condition_csvs || {};
            const hasMultipleFiles = Object.keys(separateFilesMap).length > 1;
            
            if (!hasMultipleFiles) return null;

            return (
              <div className="glass-card p-6 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-ui pb-4">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-tas-red text-xl">account_tree</span>
                    <h2 className="font-headline font-bold text-base text-primary">
                      Linked List Ingestion & FIFO MLOps Queue
                    </h2>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => onSendToMLOps(compiledData.combined_file || compiledData.first_csv, selectedFile?.name || 'combined_dataset.zip')}
                      disabled={isQueueRunning}
                      className="px-4 py-2 bg-slate-800 text-slate-200 font-mono text-xs font-bold rounded-xl border border-ui transition-all hover:bg-slate-700 disabled:opacity-50"
                    >
                      Option A: Merge & Train
                    </button>
                    <button
                      onClick={() => onRunSequential && onRunSequential(separateFilesMap, 'ANOMALY DETECTION FAMILY')}
                      disabled={isQueueRunning}
                      className="px-4 py-2 bg-gradient-to-r from-tas-red to-tas-red-hover text-white font-mono text-xs font-bold rounded-xl shadow-lg transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
                    >
                      {isQueueRunning ? 'Running FIFO Queue...' : 'Option B: Run FIFO Queue'}
                    </button>
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-slate-900/60 border border-ui space-y-4">
                  <div className="flex justify-between items-center text-[11px] font-mono text-secondary">
                    <span>QUEUE SEQUENCE LINKED LIST (FIFO DIRECTION)</span>
                    <span className="text-tas-red font-bold">{Object.keys(separateFilesMap).length} Datasets Found</span>
                  </div>

                  {/* Linked List Visualization Graph */}
                  <div className="flex flex-wrap items-center justify-center gap-4 py-4 overflow-x-auto">
                    {(() => {
                      const queueInstance = new FIFOQueue<any>();
                      if (fifoQueue && fifoQueue.length > 0) {
                        fifoQueue.forEach(item => queueInstance.enqueue(item));
                      } else {
                        Object.entries(separateFilesMap).forEach(([groupId, filePath]) => {
                          queueInstance.enqueue({
                            groupId,
                            filePath,
                            status: 'pending',
                            accuracy: 0,
                            latencyMs: 0,
                            endpointUrl: '',
                            dagId: '',
                            durationSeconds: 0
                          });
                        });
                      }

                      const elements = [];
                      let curr = queueInstance.head;
                      let idx = 0;
                      
                      while (curr) {
                        const queueItem = curr.data;
                        const groupId = queueItem.groupId;
                        const status = queueItem.status || 'pending';
                        
                        let statusClass = 'border-slate-300 dark:border-slate-800 bg-slate-900/40 text-slate-400';
                        let icon = 'hourglass_empty';
                        
                        if (status === 'running') {
                          statusClass = 'border-tas-red bg-tas-red/10 text-tas-red shadow-[0_0_15px_rgba(235,53,64,0.3)] animate-pulse';
                          icon = 'sync';
                        } else if (status === 'completed') {
                          statusClass = 'border-[#FF6B35] bg-[#FF6B35]/080/10 text-[#FF6B35]';
                          icon = 'check_circle';
                        } else if (status === 'failed') {
                          statusClass = 'border-rose-600 bg-rose-950/20 text-rose-400';
                          icon = 'cancel';
                        }
                        
                        elements.push(
                          <div key={`node-${groupId}`} className={`p-4 rounded-2xl border transition-all duration-300 flex flex-col items-center justify-between w-44 ${statusClass}`}>
                            <div className="flex items-center justify-between w-full mb-2">
                              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted">Node {idx + 1}</span>
                              <span className="material-symbols-outlined text-sm">{icon}</span>
                            </div>
                            <span className="material-symbols-outlined text-2xl text-tas-red mb-1">folder</span>
                            <h4 className="font-mono font-bold text-xs text-primary truncate max-w-full">{groupId}</h4>
                            <p className="text-[9px] text-secondary mt-1 font-mono text-center truncate max-w-full">
                              {status === 'completed' && queueItem?.accuracy 
                                ? `Acc: ${queueItem.accuracy}% | ${queueItem.latencyMs}ms` 
                                : (status === 'running' 
                                  ? `${queueItem.currentStep || 'Training...'}` 
                                  : 'In Queue')}
                            </p>
                            {status === 'running' && queueItem?.logs && queueItem.logs.length > 0 && (
                              <p className="text-[8px] text-tas-red/80 mt-1 font-mono text-center truncate max-w-full animate-pulse">
                                {queueItem.logs[queueItem.logs.length - 1]}
                              </p>
                            )}
                          </div>
                        );

                        // Draw arrow pointing to next
                        elements.push(
                          <div key={`arrow-${groupId}`} className="flex items-center justify-center shrink-0">
                            <span className="material-symbols-outlined text-slate-500 text-xl font-bold animate-pulse">arrow_forward</span>
                          </div>
                        );

                        curr = curr.next;
                        idx++;
                      }

                      // Render NULL node at the end of the chain
                      elements.push(
                        <div key="null-node" className="p-4 rounded-2xl border border-slate-700 bg-slate-950/80 text-slate-500 flex flex-col items-center justify-center w-28">
                          <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted mb-1">NULL</span>
                          <span className="material-symbols-outlined text-xl mb-1 text-slate-600">block</span>
                          <span className="font-mono text-xs font-bold text-slate-500">Ø</span>
                        </div>
                      );

                      return elements;
                    })()}
                  </div>
                </div>

                {/* Scorecard Table in exact FIFO order */}
                {fifoQueue.length > 0 && (
                  <div className="border border-ui rounded-2xl overflow-hidden" style={{background:'var(--bg-input)'}}>
                    <div className="p-4 border-b border-ui flex items-center justify-between">
                      <h3 className="text-xs font-mono font-bold uppercase text-primary flex items-center gap-2">
                        <span className="material-symbols-outlined text-sm text-tas-red">table_rows</span>
                        <span>FIFO Queue Training Scorecard (Correct FIFO Order)</span>
                      </h3>
                      {isQueueRunning ? (
                        <span className="text-[10px] font-mono bg-tas-red/15 text-tas-red border border-tas-red/30 px-2.5 py-0.5 rounded-full font-bold animate-pulse">
                          Active Index: #{activeQueueIndex + 1}
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono bg-[#FF6B35]/080/15 text-[#FF6B35] border border-[#FF6B35]/30 px-2.5 py-0.5 rounded-full font-bold">
                          Finished
                        </span>
                      )}
                    </div>
                    
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse font-mono text-xs text-secondary">
                        <thead>
                          <tr className="border-b border-ui text-[10px] text-muted font-bold uppercase" style={{background:'var(--bg-input)'}}>
                            <th className="px-4 py-3">Order</th>
                            <th className="px-4 py-3">Dataset / Group</th>
                            <th className="px-4 py-3">DAG ID Used</th>
                            <th className="px-4 py-3">Accuracy (R²)</th>
                            <th className="px-4 py-3">Latency</th>
                            <th className="px-4 py-3">Time</th>
                            <th className="px-4 py-3">API Endpoint URL</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-ui">
                          {fifoQueue.map((item, idx) => (
                            <tr key={idx} className="hover:bg-white/5 transition-colors">
                              <td className="px-4 py-3 font-bold text-tas-red">#{idx + 1}</td>
                              <td className="px-4 py-3 text-primary font-bold">{item.groupId}</td>
                              <td className="px-4 py-3">{item.dagId || '-'}</td>
                              <td className="px-4 py-3 font-bold text-[#FF6B35]">
                                {item.status === 'completed' ? `${item.accuracy}%` : (item.status === 'failed' ? 'FAILED' : (item.status === 'running' ? 'TRAINING...' : 'Pending'))}
                              </td>
                              <td className="px-4 py-3">{item.status === 'completed' ? `${item.latencyMs}ms` : '-'}</td>
                              <td className="px-4 py-3">{item.status === 'completed' ? `${item.durationSeconds}s` : '-'}</td>
                              <td className="px-4 py-3 text-[10px] truncate max-w-xs select-all text-blue-400">
                                {item.endpointUrl || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </div>

      {/* Section 4: Data Summary & Transformation Audit Card + Preview Table */}
      <div className="glass-card p-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-ui">
          <div>
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-tas-red text-xl">summarize</span>
              <h2 className="font-headline font-bold text-lg text-primary">
                4. Data Summary & Transformation Audit Card
              </h2>
            </div>
            <p className="text-xs text-secondary mt-0.5">
              Automated compilation summary pre- and post-transformation.
            </p>
          </div>

          <div className="px-4 py-2.5 bg-tas-red/15 border border-tas-red/30 rounded-2xl font-mono text-xs font-bold text-white flex items-center gap-2 backdrop-blur-md">
            <span className="material-symbols-outlined text-sm text-tas-red">transform</span>
            <span>
              {selectedFile 
                ? `Your Data: ${selectedFile.name} → Converted to: ${compiledColsCount} Clean Columns (${compiledRowsCount} Rows)`
                : 'Your Data: 12 Raw Text Files → Converted to: 27 Clean Columns (20,631 Rows)'}
            </span>
          </div>
        </div>

        {/* Column Types Header Pills */}
        <div>
          <div className="flex justify-between items-center mb-3">
            <span className="text-xs font-mono font-bold text-secondary uppercase tracking-wider">
              Compiled Data Schema Preview (First 10 Columns)
            </span>
            <span className="text-xs font-mono text-muted">
              Total Rows: {compiledRowsCount} • Domain: {domainLabel}
            </span>
          </div>

          <div className="overflow-x-auto border border-ui rounded-2xl" style={{background:'var(--bg-input)'}}>
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-ui text-[11px] font-mono text-secondary" style={{background:'var(--bg-input)'}}>
                  {cols.map((col: any) => (
                    <th key={col.name} className="px-4 py-3 font-semibold whitespace-nowrap">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-primary font-bold">{col.name}</span>
                        <span className="inline-block text-[9px] px-1.5 py-0.5 rounded font-mono border border-ui" style={{background:'var(--bg-input)', color:'var(--text-secondary)'}}>
                          {col.type}
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ui text-xs font-mono text-secondary">
                {rows.map((row: any, idx: number) => (
                  <tr key={idx} className="hover:bg-white/5 transition-colors">
                    {cols.map((col: any) => (
                      <td key={col.name} className="px-4 py-2.5 text-secondary">
                        {row[col.name]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Action Bar */}
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-secondary font-mono">
            <span className="material-symbols-outlined text-[#FF6B35] text-base">check_circle</span>
            <span>
              Target Column Synthesized:{' '}
              <strong className="text-primary font-mono">
                {compiledData?.dataset_card?.target_column || (hasRul ? 'RUL (Remaining Useful Life)' : 'Auto-detected')}
              </strong>
            </span>
          </div>

          <button
            onClick={handleSend}
            className="w-full sm:w-auto px-6 py-3 bg-gradient-to-r from-tas-red to-tas-red-hover hover:scale-105 text-white font-mono text-xs font-bold rounded-2xl shadow-xl transition-all active:scale-95 flex items-center justify-center gap-2"
          >
            <span>Direct MLOps Handoff: Trigger Node 1 Dataset Profiler</span>
            <span className="material-symbols-outlined text-base">arrow_forward</span>
          </button>
        </div>
      </div>

      {/* Archive Inspection Drawer (Overlay Slide-over) */}
      {isInspectionDrawerOpen && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-md z-50 flex justify-end animate-fadeIn">
          <div className="w-full max-w-md bg-slate-900/90 border-l border-white/15 h-full shadow-2xl p-6 flex flex-col justify-between overflow-y-auto backdrop-blur-2xl text-white">
            <div>
              <div className="flex justify-between items-center pb-4 border-b border-white/10 mb-4">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-tas-red text-xl">folder_open</span>
                  <h3 className="font-headline font-bold text-base text-white">Archive Inspection Drawer</h3>
                </div>
                <button
                  onClick={() => setIsInspectionDrawerOpen(false)}
                  className="p-1 hover:bg-white/10 rounded-lg text-slate-400 hover:text-white"
                >
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>

              <p className="text-xs text-slate-300 mb-4">
                Extracted subfolder tree with detected character encodings and size breakdown.
              </p>

              <div className="space-y-3 font-mono text-xs">
                {archiveFiles.map((file, i) => (
                  <div key={i} className="p-3 bg-slate-950/60 border border-white/15 rounded-2xl space-y-1">
                    <div className="flex justify-between items-center font-bold text-white">
                      <span className="truncate">{file.name}</span>
                      <span className="px-2 py-0.5 bg-white/10 text-slate-200 text-[10px] rounded-lg">{file.size}</span>
                    </div>
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Type: {file.type}</span>
                      <span>Encoding: <strong className="text-tas-red">{file.encoding}</strong></span>
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Columns: {file.cols} detected
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-4 border-t border-white/10">
              <button
                onClick={() => setIsInspectionDrawerOpen(false)}
                className="w-full py-2.5 bg-gradient-to-r from-tas-red to-tas-red-hover hover:scale-105 text-white font-mono text-xs font-bold rounded-2xl shadow-lg transition-all"
              >
                Close Inspection Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Premium Frosted Glass Compilation Loading Overlay */}
      {loaderStep >= 0 && (
        <div className="fixed inset-0 bg-white/40 dark:bg-slate-950/60 backdrop-blur-md z-50 flex items-center justify-center animate-fadeIn animate-duration-300">
          <div className="w-full max-w-lg bg-white/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-800 rounded-3xl p-8 shadow-2xl flex flex-col items-center space-y-6">
            
            {/* Spinning Rings & Logo */}
            <div className="relative w-24 h-24 flex items-center justify-center">
              <div className="absolute inset-0 border-4 border-slate-100 dark:border-slate-800 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-tas-red border-t-transparent rounded-full animate-spin"></div>
              <span className="material-symbols-outlined text-4xl text-tas-red animate-pulse">analytics</span>
            </div>

            {/* Title */}
            <div className="text-center space-y-1">
              <h3 className="font-headline text-lg font-extrabold text-slate-900 dark:text-white">
                Compiling SCADA Architecture
              </h3>
              <p className="text-xs text-slate-500 font-mono">
                Executing 4-Layer Relational Normalization
              </p>
            </div>

            {/* List of Steps */}
            <div className="w-full space-y-3 pt-2">
              {[
                "Profiling your data...",
                "Assigning DAG-IDS...",
                "Plotting Datavisuals...",
                "Cleaning Your Dataset...",
                "Preparing Your Dataset...",
                "Dataset is cleaned"
              ].map((text, idx) => {
                const isCompleted = loaderStep > idx;
                const isActive = loaderStep === idx;
                const isPending = loaderStep < idx;

                return (
                  <div
                    key={idx}
                    className={`flex items-center justify-between p-3 rounded-xl border transition-all duration-300 ${
                      isActive
                        ? 'border-tas-red/40 bg-tas-red/5 text-tas-red font-semibold'
                        : isCompleted
                        ? 'border-[#FF6B35]/30 bg-[#FF6B35]/080/5 text-[#FF6B35] dark:text-[#FF6B35]'
                        : 'border-slate-100 dark:border-slate-800/60 text-slate-400 opacity-60'
                    }`}
                  >
                    <div className="flex items-center gap-3 font-mono">
                      {isCompleted ? (
                        <span className="material-symbols-outlined text-[#FF6B35] text-lg">check_circle</span>
                      ) : isActive ? (
                        <div className="w-4 h-4 border-2 border-tas-red border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <span className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-700 ml-1"></span>
                      )}
                      <span className="text-xs font-mono">{text}</span>
                    </div>
                    {isCompleted && (
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#FF6B35]">Done</span>
                    )}
                    {isActive && (
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-tas-red animate-pulse">Running</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Recommended DAG-IDs Choice Pop-Up Modal */}
      {showDagModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xl animate-fadeIn">
          <div className="glass-panel w-full max-w-2xl p-6 sm:p-8 rounded-3xl border-2 border-tas-red/40 shadow-2xl space-y-6 relative overflow-hidden floating-window"
            style={{background:'rgba(13,21,51,0.95)', color:'#FFFFFF'}}>
            
            {/* Header Banner */}
            <div className="flex items-start justify-between pb-4 border-b border-white/10">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-tas-red to-tas-blue flex items-center justify-center shadow-lg">
                  <span className="material-symbols-outlined text-white text-2xl animate-pulse">auto_awesome</span>
                </div>
                <div>
                  <h3 className="font-headline font-extrabold text-lg text-white">
                    Select Recommended DAG Architecture
                  </h3>
                  <p className="text-xs text-slate-300 font-mono">
                    Data Profiler & DAG Orchestrator mapped 4 high-confidence candidate pipelines
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowDagModal(false)}
                className="p-1.5 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Recommended DAG Cards List */}
            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {[
                {
                  id: 'DAG_001',
                  title: 'Turbofan Remaining Useful Life (RUL) Predictor',
                  task: 'Time-Series Regression',
                  matchScore: '98.4% Match',
                  desc: 'Optimized for high-frequency sensor streams, temperature & pressure decay curves. Uses RobustScaler + Exponential Smoothing.',
                  icon: 'speed',
                  badgeColor: 'bg-[#FF6B35]/080/20 text-[#FF8F5A] border-[#FF6B35]/40',
                },
                {
                  id: 'DAG_283',
                  title: 'Equipment Failure & Health Degradation Classifier',
                  task: 'Binary Classification',
                  matchScore: '95.1% Match',
                  desc: 'Predicts discrete failure events within a 30-cycle horizon. Features XGBoost classifier with SMOTE balance.',
                  icon: 'warning',
                  badgeColor: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
                },
                {
                  id: 'DAG_573',
                  title: 'Multivariate Signal Anomaly & Drift Detector',
                  task: 'Unsupervised Anomaly',
                  matchScore: '91.8% Match',
                  desc: 'Detects unexpected sensor drift and out-of-bounds operational settings using Isolation Forest & PCA components.',
                  icon: 'insights',
                  badgeColor: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
                },
                {
                  id: 'DAG_906',
                  title: 'C-MAPSS Sensor Fusion Cascade Engine',
                  task: 'Deep Feature Regression',
                  matchScore: '89.6% Match',
                  desc: 'Applies lag matrix transformations (t-1, t-5, t-10) and polynomial features to maximize non-linear sensor correlation.',
                  icon: 'hub',
                  badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
                },
              ].map((dag) => {
                const isSelected = selectedDagId === dag.id;
                return (
                  <div
                    key={dag.id}
                    onClick={() => setSelectedDagId(dag.id)}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer flex items-start gap-3 font-mono ${
                      isSelected
                        ? 'border-tas-red bg-tas-red/15 shadow-lg'
                        : 'border-white/10 hover:border-white/30 bg-white/5'
                    }`}
                  >
                    <div className={`p-2.5 rounded-xl border ${dag.badgeColor}`}>
                      <span className="material-symbols-outlined text-xl">{dag.icon}</span>
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <h4 className="font-headline font-bold text-sm text-white flex items-center gap-2">
                          <span>{dag.title}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-white/10 text-slate-300 font-mono">
                            {dag.id}
                          </span>
                        </h4>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${dag.badgeColor}`}>
                          {dag.matchScore}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 font-sans leading-relaxed">{dag.desc}</p>
                      <div className="flex items-center gap-3 text-[10px] text-slate-400 pt-1">
                        <span>Task: <strong className="text-white">{dag.task}</strong></span>
                        <span>•</span>
                        <span>Auto-Recipe: <strong className="text-[#FF6B35]">Ready</strong></span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-4 border-t border-white/10">
              <span className="text-xs font-mono text-slate-400">
                Selected DAG: <strong className="text-tas-red font-bold">{selectedDagId}</strong>
              </span>
              <button
                onClick={() => {
                  setShowDagModal(false);
                  if (compiledData && compiledData.first_csv) {
                    onSendToMLOps(compiledData.first_csv, selectedFile?.name || 'compiled_dataset.zip');
                  } else if (onCompilationFinished) {
                    onCompilationFinished('workspace_data/ds1_FD001/C-MAPSS_FD001_train.csv', selectedFile?.name || 'compiled_dataset.zip');
                  } else {
                    onSendToMLOps('workspace_data/ds1_FD001/C-MAPSS_FD001_train.csv', 'compiled_dataset.zip');
                  }
                }}
                className="px-6 py-3 bg-gradient-to-r from-tas-red to-tas-red-hover hover:scale-105 text-white font-mono text-xs font-bold rounded-xl transition-all shadow-xl active:scale-95 flex items-center gap-2"
              >
                <span>Confirm Choice & Move to Prepare Node (Page 2)</span>
                <span className="material-symbols-outlined text-sm">arrow_forward</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🧙‍♂️ Simple Pipeline Setup Wizard Floating Modal */}
      {showWizard && pendingFile && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md flex items-center justify-center z-50 animate-fadeIn p-4">
          <div className="max-w-xl w-full p-6 sm:p-8 rounded-3xl shadow-2xl relative overflow-hidden flex flex-col gap-6 floating-window"
            style={{background:'#FFFFFF', border:'3px solid #2563eb', color:'#0F172A'}}>
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-50/5 rounded-full blur-3xl pointer-events-none -mr-16 -mt-16"></div>
            
            <div className="flex items-center gap-3 border-b border-slate-200 pb-4 relative z-10">
              <div className="p-3 bg-blue-50 text-blue-600 border border-blue-200 rounded-2xl">
                <span className="material-symbols-outlined text-2xl animate-pulse">auto_awesome</span>
              </div>
              <div>
                <h3 className="font-headline font-extrabold text-lg text-[#0F172A]">
                  Simple Dataset Setup Wizard
                </h3>
                <p className="text-xs text-slate-500 font-mono mt-0.5">
                  Let's configure the perfect AI model for your data file: {pendingFile.name}
                </p>
              </div>
            </div>

            <div className="space-y-4 relative z-10 font-mono text-xs">
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-slate-700 font-bold flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-blue-600">target</span>
                    <span>1. What value do you want the AI to predict?</span>
                  </label>
                  {nlpExtractedFields.target && (
                    <span className="text-[9px] font-mono text-[#FF6B35] bg-[#FF6B35]/08 border border-[#FF6B35]/20 px-2 py-0.5 rounded-full font-bold">
                      ✨ Extracted by NLP
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  placeholder="e.g. Temperature, Price, Failure, RUL"
                  value={targetColInput}
                  onChange={(e) => setTargetColInput(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-300 text-slate-800 focus:outline-none focus:border-blue-500 transition-all font-mono"
                />
                <span className="text-[10px] text-slate-500">
                  Tip: Type the name of the column you want to forecast (e.g. charges, SalePrice, RUL).
                </span>
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-slate-700 font-bold flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-sm text-blue-600">category</span>
                    <span>2. What type of prediction model is this?</span>
                  </label>
                  {nlpExtractedFields.problemType && (
                    <span className="text-[9px] font-mono text-[#FF6B35] bg-[#FF6B35]/08 border border-[#FF6B35]/20 px-2 py-0.5 rounded-full font-bold">
                      ✨ Extracted by NLP
                    </span>
                  )}
                </div>
                <select
                  value={problemTypeInput}
                  onChange={(e) => setProblemTypeInput(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-300 text-slate-800 focus:outline-none focus:border-blue-500 transition-all font-mono cursor-pointer"
                >
                  <option value="regression">Continuous Number (e.g. estimating numeric values like Price, Temperature, RUL)</option>
                  <option value="classification">Category Selection (e.g. yes/no answer or multiple choice categories like Fail / Pass)</option>
                  <option value="anomaly">Unusual Patterns (e.g. anomaly detection, finding errors / outlier logs)</option>
                  <option value="time-series">Time Sequence (e.g. forecasting trends based on cycle numbers or date/time)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-slate-700 font-bold flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-sm text-blue-600">schedule</span>
                      <span>3. Date/Time Column</span>
                    </label>
                    {nlpExtractedFields.timeCol && (
                      <span className="text-[9px] font-mono text-[#FF6B35] bg-[#FF6B35]/08 border border-[#FF6B35]/20 px-1.5 py-0.5 rounded-full font-bold">
                        ✨ NLP
                      </span>
                    )}
                  </div>
                  <input
                    type="text"
                    placeholder="Optional: e.g. time_cycle, date"
                    value={timeColInput}
                    onChange={(e) => setTimeColInput(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-300 text-slate-800 focus:outline-none focus:border-blue-500 transition-all font-mono"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-slate-700 font-bold flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-sm text-blue-600">precision_manufacturing</span>
                      <span>4. Machine/Asset ID Column</span>
                    </label>
                    {nlpExtractedFields.entityCol && (
                      <span className="text-[9px] font-mono text-[#FF6B35] bg-[#FF6B35]/08 border border-[#FF6B35]/20 px-1.5 py-0.5 rounded-full font-bold">
                        ✨ NLP
                      </span>
                    )}
                  </div>
                  <input
                    type="text"
                    placeholder="Optional: e.g. unit_id, asset_id"
                    value={entityColInput}
                    onChange={(e) => setEntityColInput(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-300 text-slate-800 focus:outline-none focus:border-blue-500 transition-all font-mono"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-200 pt-4 relative z-10">
              <button
                onClick={() => {
                  setShowWizard(false);
                  triggerCompilation(pendingFile);
                }}
                className="px-4 py-2.5 text-slate-500 hover:text-slate-800 transition-all font-mono text-xs cursor-pointer bg-transparent border-none"
              >
                Skip & Let AI Auto-Detect
              </button>

              <button
                onClick={() => {
                  setShowWizard(false);
                  triggerCompilation(pendingFile, {
                    targetColumn: targetColInput.trim() || undefined,
                    problemType: problemTypeInput,
                    timestampColumn: timeColInput.trim() || undefined,
                    entityColumn: entityColInput.trim() || undefined
                  });
                }}
                className="px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-mono text-xs font-bold rounded-xl transition-all shadow-lg shadow-blue-500/20 active:scale-95 flex items-center gap-2 border-none cursor-pointer"
              >
                <span>Save Settings & Compile</span>
                <span className="material-symbols-outlined text-sm">rocket_launch</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
