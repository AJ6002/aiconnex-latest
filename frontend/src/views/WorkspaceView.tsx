import React, { useState, useEffect, useMemo } from 'react';

interface WorkspaceNode {
  name: string;
  path: string;
  abs_path?: string;
  type: 'directory' | 'file';
  category?: string;
  extension?: string;
  size_bytes: number;
  modified_at?: string;
  created_at?: string;
  permissions?: string;
  children?: WorkspaceNode[];
}

interface WorkspaceTreeResponse {
  status: string;
  tenant_id: string;
  workspace_root: string;
  total_files: number;
  total_bytes: number;
  tree: WorkspaceNode;
}

interface FilePreviewData {
  filename: string;
  path: string;
  abs_path: string;
  extension: string;
  size_bytes: number;
  modified_at?: string;
  created_at?: string;
  permissions?: string;
  preview_type: 'tabular' | 'json' | 'text' | 'binary' | 'error';
  columns?: string[];
  dtypes?: Record<string, string>;
  rows?: Record<string, any>[];
  sample_row_count?: number;
  total_row_count?: number;
  json_content?: any;
  text_content?: string;
  error_message?: string;
}

interface WorkspaceViewProps {
  onSelectCompiledCsv?: (csvPath: string, filename: string) => void;
  onNavigateTo?: (view: string) => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({
  onSelectCompiledCsv,
  onNavigateTo
}) => {
  const [tenantId, setTenantId] = useState<string>('global');
  const [treeData, setTreeData] = useState<WorkspaceTreeResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState<string>('all');
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    'global': true,
    'global/runs': true,
    'global/uploads': true,
    'global/manifests': true,
    'global/reports': true,
    'global/models': true,
  });

  const [selectedNode, setSelectedNode] = useState<WorkspaceNode | null>(null);
  const [previewData, setPreviewData] = useState<FilePreviewData | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree');
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  // Fetch workspace hierarchical tree
  const fetchWorkspaceTree = async () => {
    setIsLoading(true);
    try {
      let res = await fetch(`http://localhost:8000/api/v1/workspace/tree?tenant_id=${tenantId}`).catch(() => null);
      if (!res || !res.ok) {
        res = await fetch(`http://localhost:5000/api/v1/workspace/tree?tenant_id=${tenantId}`).catch(() => null);
      }
      if (res && res.ok) {
        const data: WorkspaceTreeResponse = await res.json();
        setTreeData(data);
        
        // Auto-expand top categories
        if (data.tree && data.tree.children) {
          const initialExpanded: Record<string, boolean> = { [data.tree.path]: true };
          data.tree.children.forEach(c => {
            initialExpanded[c.path] = true;
            if (c.children) {
              c.children.forEach(sub => {
                initialExpanded[sub.path] = true;
              });
            }
          });
          setExpandedFolders(prev => ({ ...prev, ...initialExpanded }));
        }
      }
    } catch (err) {
      console.error('[WorkspaceView] Error fetching tree:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspaceTree();
  }, [tenantId]);

  const toggleFolder = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setExpandedFolders(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const expandAll = () => {
    if (!treeData) return;
    const allExpanded: Record<string, boolean> = {};
    const traverse = (node: WorkspaceNode) => {
      if (node.type === 'directory') {
        allExpanded[node.path] = true;
        if (node.children) node.children.forEach(traverse);
      }
    };
    traverse(treeData.tree);
    setExpandedFolders(allExpanded);
  };

  const collapseAll = () => {
    setExpandedFolders({});
  };

  const handlePreviewFile = async (node: WorkspaceNode) => {
    setSelectedNode(node);
    if (node.type === 'directory') {
      setPreviewData(null);
      return;
    }

    setIsPreviewLoading(true);
    try {
      let res = await fetch(`http://localhost:8000/api/v1/workspace/file?path=${encodeURIComponent(node.path)}&tenant_id=${tenantId}`).catch(() => null);
      if (!res || !res.ok) {
        res = await fetch(`http://localhost:5000/api/v1/workspace/file?path=${encodeURIComponent(node.path)}&tenant_id=${tenantId}`).catch(() => null);
      }
      if (res && res.ok) {
        const data: FilePreviewData = await res.json();
        setPreviewData(data);
      } else {
        setPreviewData({
          filename: node.name,
          path: node.path,
          abs_path: node.abs_path || '',
          extension: node.extension || '',
          size_bytes: node.size_bytes,
          preview_type: 'error',
          error_message: 'Unable to retrieve file preview.'
        });
      }
    } catch (err: any) {
      setPreviewData({
        filename: node.name,
        path: node.path,
        abs_path: node.abs_path || '',
        extension: node.extension || '',
        size_bytes: node.size_bytes,
        preview_type: 'error',
        error_message: err.message || 'Error loading preview'
      });
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleDownloadFile = (node: WorkspaceNode, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const downloadUrl = `http://localhost:8000/api/v1/workspace/file?path=${encodeURIComponent(node.path)}&tenant_id=${tenantId}&download=true`;
    window.open(downloadUrl, '_blank');
  };

  const [sortBy, setSortBy] = useState<'name' | 'modified' | 'size' | 'category'>('modified');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const formatDate = (isoString?: string) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return d.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });
    } catch {
      return isoString;
    }
  };

  const handleCopyPath = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    navigator.clipboard.writeText(path);
    setCopiedPath(path);
    setTimeout(() => setCopiedPath(null), 2500);
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  };

  // High-clarity, crisp light theme badges & colors
  const getNodeMeta = (node: WorkspaceNode) => {
    if (node.type === 'directory') {
      const cat = node.category || node.name.toLowerCase();
      if (cat === 'runs') return { icon: 'rocket_launch', color: '#2563EB', badge: 'Compilation Runs', badgeBg: 'bg-blue-50 text-blue-700 border-blue-200' };
      if (cat === 'uploads') return { icon: 'upload_file', color: '#EA580C', badge: 'Raw Uploads', badgeBg: 'bg-orange-50 text-orange-700 border-orange-200' };
      if (cat === 'manifests') return { icon: 'contract', color: '#059669', badge: 'Contracts & Manifests', badgeBg: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
      if (cat === 'models') return { icon: 'memory', color: '#7C3AED', badge: 'Model Artifacts', badgeBg: 'bg-purple-50 text-purple-700 border-purple-200' };
      if (cat === 'reports') return { icon: 'insights', color: '#DB2777', badge: 'Quality Reports', badgeBg: 'bg-pink-50 text-pink-700 border-pink-200' };
      if (node.name.startsWith('run_')) return { icon: 'folder_special', color: '#0891B2', badge: 'Run Folder', badgeBg: 'bg-cyan-50 text-cyan-800 border-cyan-200' };
      return { icon: 'folder', color: '#FF6B35', badge: 'Directory', badgeBg: 'bg-slate-100 text-slate-700 border-slate-200' };
    }

    const ext = (node.extension || node.name.split('.').pop() || '').toLowerCase();
    if (ext === 'csv' || ext === 'tsv') return { icon: 'table_view', color: '#059669', badge: 'CSV Dataset', badgeBg: 'bg-emerald-50 text-emerald-800 border-emerald-200 font-bold' };
    if (ext === 'json') {
      if (node.name.includes('lock') || node.name.includes('cuc') || node.name.includes('dic')) {
        return { icon: 'verified', color: '#2563EB', badge: 'Contract JSON', badgeBg: 'bg-blue-50 text-blue-800 border-blue-200 font-bold' };
      }
      return { icon: 'data_object', color: '#D97706', badge: 'JSON Manifest', badgeBg: 'bg-amber-50 text-amber-800 border-amber-200' };
    }
    if (ext === 'zip' || ext === 'tar' || ext === 'gz') return { icon: 'folder_zip', color: '#EA580C', badge: 'Archive', badgeBg: 'bg-orange-50 text-orange-800 border-orange-200' };
    if (ext === 'pkl' || ext === 'joblib' || ext === 'pt' || ext === 'onnx') return { icon: 'model_training', color: '#7C3AED', badge: 'Model Weights', badgeBg: 'bg-purple-50 text-purple-800 border-purple-200' };
    if (ext === 'txt' || ext === 'md' || ext === 'log') return { icon: 'description', color: '#64748B', badge: 'Doc / Log', badgeBg: 'bg-slate-100 text-slate-700 border-slate-200' };
    return { icon: 'draft', color: '#475569', badge: ext.toUpperCase() || 'FILE', badgeBg: 'bg-slate-100 text-slate-700 border-slate-200' };
  };

  const workspaceStats = useMemo(() => {
    let csvCount = 0;
    let jsonCount = 0;
    let uploadCount = 0;
    let runCount = 0;

    const traverse = (node: WorkspaceNode) => {
      if (node.type === 'directory') {
        if (node.name.startsWith('run_')) runCount++;
        if (node.children) node.children.forEach(traverse);
      } else {
        const ext = (node.extension || '').toLowerCase();
        if (ext === 'csv') csvCount++;
        if (ext === 'json') jsonCount++;
        if (ext === 'zip' || ext === 'tar' || ext === 'gz') uploadCount++;
      }
    };

    if (treeData?.tree) traverse(treeData.tree);

    return { csvCount, jsonCount, uploadCount, runCount };
  }, [treeData]);

  const flatNodes = useMemo(() => {
    if (!treeData?.tree) return [];
    const result: WorkspaceNode[] = [];
    const traverse = (node: WorkspaceNode) => {
      if (node.name !== treeData.tree.name) {
        result.push(node);
      }
      if (node.children) node.children.forEach(traverse);
    };
    traverse(treeData.tree);
    return result;
  }, [treeData]);

  const filteredFlatNodes = useMemo(() => {
    const filtered = flatNodes.filter(n => {
      const q = searchQuery.toLowerCase();
      const matchesSearch = !searchQuery || n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q);
      if (!matchesSearch) return false;

      if (selectedCategoryFilter === 'csv') return n.type === 'file' && (n.extension === 'csv' || n.extension === 'tsv');
      if (selectedCategoryFilter === 'json') return n.type === 'file' && n.extension === 'json';
      if (selectedCategoryFilter === 'uploads') return n.path.includes('uploads') || (n.type === 'file' && ['zip', 'tar', 'gz'].includes(n.extension || ''));
      if (selectedCategoryFilter === 'runs') return n.path.includes('runs');
      return true;
    });

    return filtered.sort((a, b) => {
      let comp = 0;
      if (sortBy === 'name') {
        comp = a.name.localeCompare(b.name);
      } else if (sortBy === 'size') {
        comp = a.size_bytes - b.size_bytes;
      } else if (sortBy === 'modified') {
        const timeA = a.modified_at ? new Date(a.modified_at).getTime() : 0;
        const timeB = b.modified_at ? new Date(b.modified_at).getTime() : 0;
        comp = timeA - timeB;
      } else if (sortBy === 'category') {
        comp = (a.category || '').localeCompare(b.category || '');
      }
      return sortOrder === 'asc' ? comp : -comp;
    });
  }, [flatNodes, searchQuery, selectedCategoryFilter, sortBy, sortOrder]);

  // Recursive Tree Node Renderer with clear Light Theme typography and high-contrast lines
  const renderTreeNode = (node: WorkspaceNode, depth: number = 0) => {
    const isExpanded = !!expandedFolders[node.path];
    const isSelected = selectedNode?.path === node.path;
    const isFolder = node.type === 'directory';
    const meta = getNodeMeta(node);

    const nodeMatches = !searchQuery || node.name.toLowerCase().includes(searchQuery.toLowerCase()) || node.path.toLowerCase().includes(searchQuery.toLowerCase());
    const hasMatchingDescendant = (n: WorkspaceNode): boolean => {
      if (n.name.toLowerCase().includes(searchQuery.toLowerCase()) || n.path.toLowerCase().includes(searchQuery.toLowerCase())) return true;
      return !!(n.children && n.children.some(hasMatchingDescendant));
    };

    if (searchQuery && !nodeMatches && !hasMatchingDescendant(node)) {
      return null;
    }

    return (
      <div key={node.path} className="select-none">
        <div
          onClick={() => {
            if (isFolder) {
              toggleFolder(node.path);
            }
            handlePreviewFile(node);
          }}
          style={{ paddingLeft: `${Math.max(8, depth * 18)}px` }}
          className={`group flex items-center justify-between py-2 px-3 rounded-xl cursor-pointer transition-all duration-150 border ${
            isSelected
              ? 'bg-[#FF6B35]/12 border-[#FF6B35]/40 text-[#0F172A] font-bold shadow-xs'
              : 'border-transparent hover:bg-slate-100/80 text-slate-800'
          }`}
        >
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            {/* Expand/Collapse Chevron for Folders */}
            {isFolder ? (
              <button
                onClick={(e) => toggleFolder(node.path, e)}
                className="w-5 h-5 flex items-center justify-center rounded-md hover:bg-slate-200 text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
              >
                <span className={`material-symbols-outlined text-base transition-transform duration-200 ${isExpanded ? 'rotate-90 text-slate-800' : 'text-slate-400'}`}>
                  chevron_right
                </span>
              </button>
            ) : (
              <div className="w-5 h-5 flex items-center justify-center">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
              </div>
            )}

            {/* Item Icon */}
            <span className="material-symbols-outlined text-lg shrink-0" style={{ color: meta.color }}>
              {isFolder ? (isExpanded ? 'folder_open' : 'folder') : meta.icon}
            </span>

            {/* Name */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs truncate ${isSelected ? 'text-[#0F172A] font-bold' : 'text-slate-800'}`}>
                  {node.name}
                </span>
                {node.name.startsWith('run_') && (
                  <span className="px-1.5 py-0.2 text-[9px] font-mono font-bold rounded bg-cyan-100 text-cyan-800 border border-cyan-200">
                    RUN
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right info badges & actions */}
          <div className="flex items-center gap-2 shrink-0 ml-2">
            <span className={`hidden sm:inline-block px-2 py-0.5 text-[9px] font-mono font-bold uppercase rounded-md border ${meta.badgeBg}`}>
              {meta.badge}
            </span>

            {/* Date Time Badge */}
            {node.modified_at && (
              <span className="hidden md:inline-flex items-center gap-1 font-mono text-[10px] text-slate-500 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-md" title={`Last Modified: ${formatDate(node.modified_at)}`}>
                <span className="material-symbols-outlined text-[11px] text-slate-400">schedule</span>
                <span>{formatDate(node.modified_at)}</span>
              </span>
            )}

            <span className="font-mono text-[11px] text-slate-500 w-16 text-right font-medium">
              {isFolder ? `${node.children?.length || 0} items` : formatSize(node.size_bytes)}
            </span>

            {/* Quick Actions Menu */}
            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
              <button
                onClick={(e) => handleCopyPath(node.path, e)}
                title="Copy relative path"
                className="p-1 rounded hover:bg-slate-200 text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-sm">
                  {copiedPath === node.path ? 'check' : 'content_copy'}
                </span>
              </button>
              {!isFolder && (
                <button
                  onClick={(e) => handleDownloadFile(node, e)}
                  title="Download File"
                  className="p-1 rounded hover:bg-slate-200 text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-sm">download</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Child Nodes */}
        {isFolder && isExpanded && node.children && node.children.length > 0 && (
          <div className="border-l border-slate-200 ml-4 pl-1 mt-0.5 space-y-0.5">
            {node.children.map(child => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6 text-slate-900 animate-fadeIn pb-12">
      {/* ── 1. Top Header Banner ── */}
      <div className="p-6 sm:p-8 rounded-3xl relative overflow-hidden bg-white border border-slate-200 shadow-sm">
        <div className="absolute top-0 right-0 w-96 h-96 bg-[#FF6B35]/06 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20"></div>
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest mb-1.5">
              <span className="text-[#FF6B35] font-extrabold flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">domain</span>
                TENANT DOCK
              </span>
              <span className="text-slate-300">•</span>
              <span className="text-slate-500 font-bold">Workspace Repository</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="font-headline text-2xl sm:text-3xl font-extrabold text-[#0F172A] tracking-tight">
                My Workspace
              </h1>
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-slate-100 border border-slate-200 text-xs font-mono font-bold text-slate-800">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>Tenant: {tenantId}</span>
              </div>
            </div>
            <p className="text-xs text-slate-500 font-mono mt-1.5">
              Filesystem Directory: <code className="text-slate-700 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded font-mono">services/workspace_data/{tenantId}/</code>
            </p>
          </div>

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={expandAll}
              className="px-3.5 py-2 border border-slate-200 hover:bg-slate-100 hover:border-slate-300 text-slate-700 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <span className="material-symbols-outlined text-sm">unfold_more</span>
              <span>Expand All</span>
            </button>
            <button
              onClick={collapseAll}
              className="px-3.5 py-2 border border-slate-200 hover:bg-slate-100 hover:border-slate-300 text-slate-700 rounded-xl text-xs font-mono font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <span className="material-symbols-outlined text-sm">unfold_less</span>
              <span>Collapse All</span>
            </button>
            <button
              onClick={fetchWorkspaceTree}
              disabled={isLoading}
              className="px-4 py-2 bg-[#FF6B35] hover:bg-[#E85520] text-white rounded-xl text-xs font-mono font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-sm ${isLoading ? 'animate-spin' : ''}`}>sync</span>
              <span>Refresh Workspace</span>
            </button>
          </div>
        </div>

        {/* ── Stats Metric Cards (Clean Light Theme) ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3.5 mt-6 pt-6 border-t border-slate-200">
          <div className="p-3.5 rounded-2xl bg-slate-50/70 border border-slate-200 hover:border-blue-300 transition-colors">
            <div className="flex items-center justify-between text-slate-500 text-[10px] font-mono uppercase font-bold">
              <span>Runs & Datasets</span>
              <span className="material-symbols-outlined text-blue-600 text-base">rocket_launch</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-headline font-black text-xl text-[#0F172A]">
                {workspaceStats.runCount}
              </span>
              <span className="text-[10px] font-mono text-emerald-700 font-bold">
                {workspaceStats.csvCount} compiled CSVs
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-slate-50/70 border border-slate-200 hover:border-orange-300 transition-colors">
            <div className="flex items-center justify-between text-slate-500 text-[10px] font-mono uppercase font-bold">
              <span>Raw Uploads</span>
              <span className="material-symbols-outlined text-orange-600 text-base">upload_file</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-headline font-black text-xl text-[#0F172A]">
                {workspaceStats.uploadCount}
              </span>
              <span className="text-[10px] font-mono text-slate-500">archives</span>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-slate-50/70 border border-slate-200 hover:border-emerald-300 transition-colors">
            <div className="flex items-center justify-between text-slate-500 text-[10px] font-mono uppercase font-bold">
              <span>CUC / DIC Manifests</span>
              <span className="material-symbols-outlined text-emerald-600 text-base">contract</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-headline font-black text-xl text-[#0F172A]">
                {workspaceStats.jsonCount}
              </span>
              <span className="text-[10px] font-mono text-slate-500">contracts</span>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-slate-50/70 border border-slate-200 hover:border-purple-300 transition-colors">
            <div className="flex items-center justify-between text-slate-500 text-[10px] font-mono uppercase font-bold">
              <span>Total Artifacts</span>
              <span className="material-symbols-outlined text-purple-600 text-base">inventory_2</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-headline font-black text-xl text-[#0F172A]">
                {treeData?.total_files || 0}
              </span>
              <span className="text-[10px] font-mono text-slate-500">files</span>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-slate-50/70 border border-slate-200 hover:border-[#FF6B35]/40 transition-colors col-span-2 sm:col-span-4 lg:col-span-1">
            <div className="flex items-center justify-between text-slate-500 text-[10px] font-mono uppercase font-bold">
              <span>Storage Used</span>
              <span className="material-symbols-outlined text-[#FF6B35] text-base">hard_drive</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-headline font-black text-xl text-[#0F172A]">
                {formatSize(treeData?.total_bytes || 0)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── 2. Search, Filter Chips & View Mode Controls ── */}
      <div className="p-4 flex flex-col md:flex-row gap-4 items-center justify-between bg-white border border-slate-200 rounded-2xl shadow-sm">
        <div className="flex flex-1 items-center gap-3 w-full md:w-auto">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">search</span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search files, runs, manifests, extensions..."
              className="w-full rounded-xl pl-8 pr-8 py-2 text-xs font-mono bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[#FF6B35] focus:bg-white transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>

          {/* Filter Chips */}
          <div className="hidden lg:flex items-center gap-1.5 text-xs font-mono">
            {[
              { id: 'all', label: 'All Files' },
              { id: 'runs', label: 'Runs' },
              { id: 'csv', label: 'CSVs' },
              { id: 'json', label: 'Manifests' },
              { id: 'uploads', label: 'Uploads' }
            ].map(f => (
              <button
                key={f.id}
                onClick={() => setSelectedCategoryFilter(f.id)}
                className={`px-3 py-1.5 rounded-xl transition-all cursor-pointer font-bold ${
                  selectedCategoryFilter === f.id
                    ? 'bg-[#FF6B35] text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200/70'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center gap-2 self-end md:self-auto">
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setViewMode('tree')}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1 transition-all cursor-pointer ${
                viewMode === 'tree' ? 'bg-white text-[#0F172A] shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <span className="material-symbols-outlined text-sm">account_tree</span>
              <span>Tree</span>
            </button>
            <button
              onClick={() => setViewMode('flat')}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1 transition-all cursor-pointer ${
                viewMode === 'flat' ? 'bg-white text-[#0F172A] shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <span className="material-symbols-outlined text-sm">table_rows</span>
              <span>Flat</span>
            </button>
          </div>
        </div>
      </div>

      {/* ── 3. Main Workspace Explorer & Preview Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Explorer Tree / Table */}
        <div className={`${selectedNode && selectedNode.type === 'file' ? 'lg:col-span-5 xl:col-span-4' : 'lg:col-span-12'} transition-all duration-200`}>
          <div className="p-4 rounded-3xl bg-white border border-slate-200 shadow-sm min-h-[500px] flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-3 text-xs font-mono text-slate-500">
              <span className="font-bold uppercase tracking-wider flex items-center gap-1.5 text-slate-800">
                <span className="material-symbols-outlined text-base text-[#FF6B35]">folder_open</span>
                <span>Workspace File Tree</span>
              </span>
              <span className="text-slate-500 font-bold">{viewMode === 'tree' ? `${treeData?.total_files || 0} files` : `${filteredFlatNodes.length} items`}</span>
            </div>

            {isLoading ? (
              <div className="p-16 flex flex-col items-center justify-center space-y-3 my-auto">
                <div className="w-8 h-8 border-3 border-[#FF6B35] border-t-transparent rounded-full animate-spin"></div>
                <span className="text-xs font-mono text-slate-500">Loading workspace files...</span>
              </div>
            ) : !treeData?.tree || (treeData.total_files === 0 && (!treeData.tree.children || treeData.tree.children.length === 0)) ? (
              <div className="p-16 flex flex-col items-center justify-center text-center space-y-3 my-auto">
                <span className="material-symbols-outlined text-4xl text-slate-400">folder_open</span>
                <h3 className="font-headline font-bold text-sm text-[#0F172A]">Workspace is Empty</h3>
                <p className="text-xs text-slate-500 max-w-xs font-mono">
                  Compile a dataset or upload files to populate the tenant directory.
                </p>
              </div>
            ) : viewMode === 'tree' ? (
              <div className="space-y-1 overflow-y-auto max-h-[700px] pr-1 font-mono text-xs">
                {renderTreeNode(treeData.tree)}
              </div>
            ) : (
              /* Flat Table View */
              <div className="overflow-x-auto max-h-[700px]">
                <table className="w-full text-left border-collapse font-mono text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase font-bold text-slate-600">
                      <th
                        className="py-2.5 px-3 cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => {
                          if (sortBy === 'name') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                          else { setSortBy('name'); setSortOrder('asc'); }
                        }}
                      >
                        <div className="flex items-center gap-1">
                          <span>Name & Path</span>
                          {sortBy === 'name' && (
                            <span className="material-symbols-outlined text-xs">{sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}</span>
                          )}
                        </div>
                      </th>
                      <th
                        className="py-2.5 px-3 cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => {
                          if (sortBy === 'category') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                          else { setSortBy('category'); setSortOrder('asc'); }
                        }}
                      >
                        <div className="flex items-center gap-1">
                          <span>Category</span>
                          {sortBy === 'category' && (
                            <span className="material-symbols-outlined text-xs">{sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}</span>
                          )}
                        </div>
                      </th>
                      <th
                        className="py-2.5 px-3 cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => {
                          if (sortBy === 'size') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                          else { setSortBy('size'); setSortOrder('desc'); }
                        }}
                      >
                        <div className="flex items-center gap-1">
                          <span>Size</span>
                          {sortBy === 'size' && (
                            <span className="material-symbols-outlined text-xs">{sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}</span>
                          )}
                        </div>
                      </th>
                      <th
                        className="py-2.5 px-3 cursor-pointer hover:bg-slate-100 transition-colors"
                        onClick={() => {
                          if (sortBy === 'modified') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                          else { setSortBy('modified'); setSortOrder('desc'); }
                        }}
                      >
                        <div className="flex items-center gap-1">
                          <span>Date Modified</span>
                          {sortBy === 'modified' && (
                            <span className="material-symbols-outlined text-xs">{sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}</span>
                          )}
                        </div>
                      </th>
                      <th className="py-2.5 px-3">Date Created</th>
                      <th className="py-2.5 px-3">Perms</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredFlatNodes.map((n, idx) => {
                      const meta = getNodeMeta(n);
                      const isSelected = selectedNode?.path === n.path;
                      return (
                        <tr
                          key={idx}
                          onClick={() => handlePreviewFile(n)}
                          className={`hover:bg-slate-50 cursor-pointer transition-colors ${
                            isSelected ? 'bg-[#FF6B35]/12 font-bold' : ''
                          }`}
                        >
                          <td className="py-2.5 px-3 flex items-center gap-2">
                            <span className="material-symbols-outlined text-base shrink-0" style={{ color: meta.color }}>
                              {meta.icon}
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs text-slate-800 font-bold">{n.name}</p>
                              <p className="text-[10px] text-slate-500 truncate">{n.path}</p>
                            </div>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${meta.badgeBg}`}>
                              {meta.badge}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-600 text-[11px] whitespace-nowrap">
                            {n.type === 'directory' ? 'DIR' : formatSize(n.size_bytes)}
                          </td>
                          <td className="py-2.5 px-3 text-slate-600 text-[11px] whitespace-nowrap">
                            {formatDate(n.modified_at)}
                          </td>
                          <td className="py-2.5 px-3 text-slate-500 text-[11px] whitespace-nowrap">
                            {formatDate(n.created_at)}
                          </td>
                          <td className="py-2.5 px-3 text-slate-500 text-[10px] font-mono whitespace-nowrap">
                            {n.permissions || '644'}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={(e) => handleCopyPath(n.path, e)}
                                className="p-1 text-slate-500 hover:text-slate-900"
                                title="Copy Relative Path"
                              >
                                <span className="material-symbols-outlined text-xs">
                                  {copiedPath === n.path ? 'check' : 'content_copy'}
                                </span>
                              </button>
                              {n.type === 'file' && (
                                <button
                                  onClick={(e) => handleDownloadFile(n, e)}
                                  className="p-1 text-slate-500 hover:text-slate-900"
                                  title="Download File"
                                >
                                  <span className="material-symbols-outlined text-xs">download</span>
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: File Preview Panel (Pristine Light Theme) */}
        {selectedNode && selectedNode.type === 'file' && (
          <div className="lg:col-span-7 xl:col-span-8 animate-fadeIn">
            <div className="p-6 rounded-3xl bg-white border border-slate-200 shadow-sm min-h-[500px] flex flex-col">
              {/* Preview Header */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-2.5 rounded-2xl bg-slate-100 border border-slate-200 shrink-0">
                    <span className="material-symbols-outlined text-2xl" style={{ color: getNodeMeta(selectedNode).color }}>
                      {getNodeMeta(selectedNode).icon}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-headline font-bold text-base text-[#0F172A] truncate">
                        {selectedNode.name}
                      </h3>
                      <span className={`px-2 py-0.5 text-[9px] font-mono font-bold uppercase rounded-md border ${getNodeMeta(selectedNode).badgeBg}`}>
                        {getNodeMeta(selectedNode).badge}
                      </span>
                    </div>
                    <p className="text-[11px] font-mono text-slate-500 truncate mt-0.5">
                      {selectedNode.path} • {formatSize(selectedNode.size_bytes)}
                    </p>
                  </div>
                </div>

                {/* Preview Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleCopyPath(selectedNode.path)}
                    className="px-3 py-1.5 border border-slate-200 rounded-xl text-xs font-mono font-bold text-slate-700 hover:bg-slate-100 flex items-center gap-1 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-xs">
                      {copiedPath === selectedNode.path ? 'check' : 'content_copy'}
                    </span>
                    <span>{copiedPath === selectedNode.path ? 'Copied' : 'Copy Path'}</span>
                  </button>

                  <button
                    onClick={() => handleDownloadFile(selectedNode)}
                    className="px-3.5 py-1.5 bg-[#FF6B35] hover:bg-[#E85520] text-white rounded-xl text-xs font-mono font-bold flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-xs">download</span>
                    <span>Download</span>
                  </button>

                  <button
                    onClick={() => setSelectedNode(null)}
                    className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg cursor-pointer"
                    title="Close Preview"
                  >
                    <span className="material-symbols-outlined text-base">close</span>
                  </button>
                </div>
              </div>

              {/* Comprehensive File Metadata Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 my-4 p-3 bg-slate-50 border border-slate-200 rounded-2xl font-mono text-xs">
                <div>
                  <div className="text-[10px] text-slate-500 font-bold uppercase flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs text-blue-600">schedule</span>
                    <span>Date Modified</span>
                  </div>
                  <div className="text-slate-800 font-bold text-[11px] mt-0.5 truncate" title={selectedNode.modified_at}>
                    {formatDate(selectedNode.modified_at)}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-slate-500 font-bold uppercase flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs text-purple-600">history</span>
                    <span>Date Created</span>
                  </div>
                  <div className="text-slate-800 font-bold text-[11px] mt-0.5 truncate" title={selectedNode.created_at}>
                    {formatDate(selectedNode.created_at)}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-slate-500 font-bold uppercase flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs text-emerald-600">hard_drive</span>
                    <span>Size & Bytes</span>
                  </div>
                  <div className="text-slate-800 font-bold text-[11px] mt-0.5">
                    {formatSize(selectedNode.size_bytes)} ({selectedNode.size_bytes.toLocaleString()} B)
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-slate-500 font-bold uppercase flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs text-amber-600">lock</span>
                    <span>Permissions</span>
                  </div>
                  <div className="text-slate-800 font-bold text-[11px] mt-0.5">
                    Mode {selectedNode.permissions || '644'}
                  </div>
                </div>
              </div>

              {selectedNode.abs_path && (
                <div className="mb-2 px-3 py-1.5 bg-slate-100/70 border border-slate-200 rounded-xl flex items-center justify-between text-[11px] font-mono text-slate-600">
                  <div className="truncate flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-xs text-slate-400">folder_special</span>
                    <span className="font-bold text-slate-500 shrink-0">Disk Path:</span>
                    <span className="truncate text-slate-800 select-all">{selectedNode.abs_path}</span>
                  </div>
                  <button
                    onClick={() => handleCopyPath(selectedNode.abs_path!)}
                    className="text-slate-400 hover:text-slate-700 ml-2 shrink-0 cursor-pointer"
                    title="Copy Absolute Path"
                  >
                    <span className="material-symbols-outlined text-xs">
                      {copiedPath === selectedNode.abs_path ? 'check' : 'content_copy'}
                    </span>
                  </button>
                </div>
              )}

              {/* Preview Body */}
              <div className="mt-4 flex-1 flex flex-col">
                {isPreviewLoading ? (
                  <div className="p-16 flex flex-col items-center justify-center space-y-3 my-auto">
                    <div className="w-8 h-8 border-3 border-[#FF6B35] border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-xs font-mono text-slate-500">Parsing file preview...</span>
                  </div>
                ) : !previewData ? (
                  <div className="p-12 text-center text-slate-400 font-mono text-xs my-auto">
                    Select a file to inspect its data.
                  </div>
                ) : previewData.preview_type === 'tabular' ? (
                  /* Tabular CSV Preview */
                  <div className="space-y-3 flex-1 flex flex-col">
                    <div className="flex items-center justify-between text-xs font-mono text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                      <span>Showing first {previewData.sample_row_count} rows of {previewData.total_row_count ? `${previewData.total_row_count.toLocaleString()} total rows` : 'dataset'}</span>
                      <span className="font-bold text-emerald-700">{previewData.columns?.length || 0} Columns</span>
                    </div>

                    <div className="overflow-x-auto overflow-y-auto max-h-[500px] border border-slate-200 rounded-2xl shadow-2xs">
                      <table className="w-full text-left border-collapse font-mono text-[11px]">
                        <thead className="sticky top-0 bg-slate-100 z-10">
                          <tr className="border-b border-slate-200">
                            <th className="py-2 px-3 text-slate-500 w-10 text-center font-bold">#</th>
                            {previewData.columns?.map(col => (
                              <th key={col} className="py-2 px-3 font-bold text-slate-900 whitespace-nowrap">
                                <div>{col}</div>
                                {previewData.dtypes && previewData.dtypes[col] && (
                                  <div className="text-[9px] text-slate-500 font-normal">{previewData.dtypes[col]}</div>
                                )}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {previewData.rows?.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-slate-50">
                              <td className="py-1.5 px-3 text-center text-slate-500 bg-slate-50/70 text-[10px] font-medium border-r border-slate-100">
                                {rIdx + 1}
                              </td>
                              {previewData.columns?.map(col => (
                                <td key={col} className="py-1.5 px-3 text-slate-800 whitespace-nowrap">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Action to use in pipeline */}
                    {onSelectCompiledCsv && (
                      <div className="pt-2 flex justify-end">
                        <button
                          onClick={() => {
                            if (previewData.abs_path) {
                              onSelectCompiledCsv(previewData.abs_path, selectedNode.name);
                            }
                          }}
                          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-mono font-bold flex items-center gap-1.5 shadow-sm cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-sm">rocket_launch</span>
                          <span>Use in Data Explorer / ML Studio</span>
                        </button>
                      </div>
                    )}
                  </div>
                ) : previewData.preview_type === 'json' ? (
                  /* JSON Manifest Viewer */
                  <div className="space-y-2 flex-1 flex flex-col">
                    <div className="flex items-center justify-between text-xs font-mono text-slate-600">
                      <span>JSON Object Preview</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(previewData.json_content, null, 2));
                          alert('JSON copied to clipboard!');
                        }}
                        className="text-xs text-[#FF6B35] hover:underline font-bold cursor-pointer"
                      >
                        Copy JSON
                      </button>
                    </div>
                    <pre className="p-4 rounded-2xl bg-slate-900 text-emerald-300 font-mono text-xs overflow-auto max-h-[500px] leading-relaxed border border-slate-800 shadow-inner">
                      {JSON.stringify(previewData.json_content, null, 2)}
                    </pre>
                  </div>
                ) : previewData.preview_type === 'text' ? (
                  /* Text / Log Viewer */
                  <pre className="p-4 rounded-2xl bg-slate-50 text-slate-900 font-mono text-xs overflow-auto max-h-[500px] leading-relaxed border border-slate-200">
                    {previewData.text_content}
                  </pre>
                ) : previewData.preview_type === 'binary' ? (
                  /* Binary / Archive notice */
                  <div className="p-12 flex flex-col items-center justify-center text-center space-y-3 my-auto bg-slate-50/60 rounded-2xl border border-slate-200">
                    <span className="material-symbols-outlined text-4xl text-orange-500">folder_zip</span>
                    <h4 className="font-headline font-bold text-sm text-[#0F172A]">Binary File / Archive</h4>
                    <p className="text-xs text-slate-600 font-mono max-w-sm">
                      {previewData.message}
                    </p>
                    <button
                      onClick={() => handleDownloadFile(selectedNode)}
                      className="px-4 py-2 bg-[#FF6B35] hover:bg-[#E85520] text-white rounded-xl text-xs font-mono font-bold flex items-center gap-1.5 shadow-sm cursor-pointer mt-2"
                    >
                      <span className="material-symbols-outlined text-sm">download</span>
                      <span>Download Archive</span>
                    </button>
                  </div>
                ) : (
                  /* Error */
                  <div className="p-12 text-center text-red-600 font-mono text-xs my-auto">
                    {previewData.error_message || 'Could not preview file.'}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
