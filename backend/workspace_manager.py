import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("aiconnex.workspace")

WORKSPACE_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "workspace_data"))


def get_workspace_root() -> str:
    os.makedirs(WORKSPACE_BASE_DIR, exist_ok=True)
    return WORKSPACE_BASE_DIR


def get_tenant_dir(tenant_id: str = "global") -> str:
    tid = (tenant_id or "global").strip() or "global"
    tdir = os.path.join(get_workspace_root(), tid)
    os.makedirs(tdir, exist_ok=True)
    return os.path.abspath(tdir)


def get_tenant_subfolder(sub: str, tenant_id: str = "global") -> str:
    tdir = get_tenant_dir(tenant_id)
    path = os.path.join(tdir, sub)
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def resolve_safe_path(path_str: str, tenant_id: str = "global") -> Optional[str]:
    """Validate that path_str resolves to a path inside the tenant workspace (prevent directory traversal)."""
    if not path_str:
        return None
    tdir = get_tenant_dir(tenant_id)
    
    # If absolute path, check if it's within WORKSPACE_BASE_DIR
    if os.path.isabs(path_str):
        clean = os.path.abspath(path_str)
        if clean.startswith(WORKSPACE_BASE_DIR) and os.path.exists(clean):
            return clean
        return None

    # Treat as relative to tenant root
    target = os.path.abspath(os.path.join(tdir, path_str.lstrip("/\\")))
    if target.startswith(tdir) and os.path.exists(target):
        return target
    
    # Also try relative to WORKSPACE_BASE_DIR if tenant_id was already included in path
    target_base = os.path.abspath(os.path.join(WORKSPACE_BASE_DIR, path_str.lstrip("/\\")))
    if target_base.startswith(WORKSPACE_BASE_DIR) and os.path.exists(target_base):
        return target_base

    return None


def export_cuc_manifest(tenant_id: str, session_id: str, cuc_dict: Dict[str, Any]) -> str:
    """Save Conversation Understanding Contract (CUC) manifest into workspace."""
    try:
        manifest_dir = get_tenant_subfolder("manifests", tenant_id)
        file_path = os.path.join(manifest_dir, f"cuc_{session_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cuc_dict, f, indent=2, default=str)
        logger.info(f"[Workspace] Exported CUC manifest to {file_path}")
        return file_path
    except Exception as e:
        logger.warning(f"[Workspace] Error exporting CUC manifest: {e}")
        return ""


def export_dic_manifest(tenant_id: str, run_id: str, dic_dict: Dict[str, Any]) -> str:
    """Save Dataset Intelligence Contract (DIC) manifest into workspace."""
    try:
        manifest_dir = get_tenant_subfolder("manifests", tenant_id)
        file_path = os.path.join(manifest_dir, f"dic_{run_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(dic_dict, f, indent=2, default=str)
        logger.info(f"[Workspace] Exported DIC manifest to {file_path}")
        return file_path
    except Exception as e:
        logger.warning(f"[Workspace] Error exporting DIC manifest: {e}")
        return ""


def export_profile_report(tenant_id: str, run_id: str, profile_dict: Dict[str, Any]) -> str:
    """Save Dataset Profiler health report into workspace."""
    try:
        rep_dir = get_tenant_subfolder("reports", tenant_id)
        file_path = os.path.join(rep_dir, f"profile_{run_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile_dict, f, indent=2, default=str)
        logger.info(f"[Workspace] Exported Profile report to {file_path}")
        return file_path
    except Exception as e:
        logger.warning(f"[Workspace] Error exporting Profile report: {e}")
        return ""


def _categorize_folder(name: str) -> str:
    n = name.lower()
    if n in ("runs", "compiled_datasets"):
        return "runs"
    if n in ("uploads", "raw_data"):
        return "uploads"
    if n in ("manifests", "contracts"):
        return "manifests"
    if n in ("models", "checkpoints"):
        return "models"
    if n in ("reports", "evaluations", "profiles"):
        return "reports"
    if n in ("sessions", "chat_history"):
        return "sessions"
    return "directory"


def _categorize_file(filename: str, ext: str) -> str:
    e = ext.lower()
    fn = filename.lower()
    if e in ("csv", "tsv", "parquet"):
        return "dataset"
    if e == "json":
        if "cuc" in fn or "manifest" in fn:
            return "contract"
        if "dic" in fn or "lock" in fn or "card" in fn:
            return "metadata"
        if "report" in fn or "audit" in fn or "lineage" in fn:
            return "report"
        return "json"
    if e in ("zip", "tar", "gz", "7z"):
        return "archive"
    if e in ("pkl", "joblib", "pt", "onnx", "h5"):
        return "model"
    return "file"


def build_workspace_tree(tenant_id: str = "global", include_sessions: bool = False) -> Dict[str, Any]:
    """Recursively build hierarchical directory tree of tenant workspace."""
    tdir = get_tenant_dir(tenant_id)
    
    total_files = 0
    total_bytes = 0

    def _walk_tree(current_path: str, rel_prefix: str = "") -> Dict[str, Any]:
        nonlocal total_files, total_bytes
        name = os.path.basename(current_path)
        stat = os.stat(current_path)
        
        node = {
            "name": name,
            "path": rel_prefix or name,
            "abs_path": current_path.replace("\\", "/"),
            "type": "directory",
            "category": _categorize_folder(name),
            "size_bytes": 0,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "children": []
        }

        try:
            entries = sorted(os.scandir(current_path), key=lambda e: (not e.is_dir(), e.name.lower()))
            dir_size = 0
            for entry in entries:
                # Per Q1: hide sessions folder from frontend workspace unless explicitly requested
                if not include_sessions and entry.is_dir() and entry.name.lower() == "sessions":
                    continue
                if entry.name.startswith("."):
                    continue

                child_rel = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
                if entry.is_dir():
                    child_node = _walk_tree(entry.path, child_rel)
                    node["children"].append(child_node)
                    dir_size += child_node["size_bytes"]
                else:
                    total_files += 1
                    fstat = entry.stat()
                    fsize = fstat.st_size
                    total_bytes += fsize
                    dir_size += fsize
                    ext = os.path.splitext(entry.name)[1].lstrip(".").lower()
                    
                    node["children"].append({
                        "name": entry.name,
                        "path": child_rel,
                        "abs_path": entry.path.replace("\\", "/"),
                        "type": "file",
                        "extension": ext,
                        "category": _categorize_file(entry.name, ext),
                        "size_bytes": fsize,
                        "modified_at": datetime.fromtimestamp(fstat.st_mtime).isoformat()
                    })
            node["size_bytes"] = dir_size
        except Exception as exc:
            logger.warning(f"[Workspace] Error scanning {current_path}: {exc}")

        return node

    tree = _walk_tree(tdir, "")
    tree["name"] = tenant_id

    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "workspace_root": tdir.replace("\\", "/"),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "tree": tree
    }


def list_workspace_flat(tenant_id: str = "global", include_sessions: bool = False) -> List[Dict[str, Any]]:
    """Return flat list of all items for backwards compatibility."""
    tdir = get_tenant_dir(tenant_id)
    items = []
    
    for root, dirs, files in os.walk(tdir):
        rel_root = os.path.relpath(root, tdir).replace("\\", "/")
        if not include_sessions and "sessions" in rel_root.split("/"):
            continue

        for d in dirs:
            if not include_sessions and d == "sessions":
                continue
            full = os.path.join(root, d)
            rel = os.path.relpath(full, tdir).replace("\\", "/")
            items.append({
                "name": d,
                "path": rel,
                "size_bytes": 0,
                "is_dir": True,
                "category": _categorize_folder(d),
                "extension": ""
            })

        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, tdir).replace("\\", "/")
            ext = os.path.splitext(f)[1].lstrip(".").lower()
            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            items.append({
                "name": f,
                "path": rel,
                "size_bytes": size,
                "is_dir": False,
                "category": _categorize_file(f, ext),
                "extension": ext
            })

    return items


def get_file_preview(path_str: str, tenant_id: str = "global", max_rows: int = 50) -> Dict[str, Any]:
    """Return preview content (JSON parsed, CSV rows, or text metadata) for a given file."""
    safe_path = resolve_safe_path(path_str, tenant_id)
    if not safe_path or not os.path.isfile(safe_path):
        return {"error": "File not found or access denied.", "status": 404}

    filename = os.path.basename(safe_path)
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    size_bytes = os.path.getsize(safe_path)

    response_data = {
        "filename": filename,
        "path": os.path.relpath(safe_path, get_tenant_dir(tenant_id)).replace("\\", "/"),
        "abs_path": safe_path.replace("\\", "/"),
        "extension": ext,
        "size_bytes": size_bytes,
        "type": ext,
    }

    # CSV / TSV preview
    if ext in ("csv", "tsv"):
        try:
            import pandas as pd
            sep = "\t" if ext == "tsv" else ","
            df = pd.read_csv(safe_path, sep=sep, nrows=max_rows, low_memory=False)
            total_estimated_rows = -1
            try:
                with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                    total_estimated_rows = sum(1 for _ in f) - 1
            except Exception:
                pass
            
            response_data["preview_type"] = "tabular"
            response_data["columns"] = list(df.columns)
            response_data["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
            response_data["rows"] = df.fillna("").to_dict(orient="records")
            response_data["sample_row_count"] = len(df)
            response_data["total_row_count"] = total_estimated_rows if total_estimated_rows >= 0 else len(df)
            return response_data
        except Exception as exc:
            response_data["preview_type"] = "error"
            response_data["error_message"] = f"Could not parse CSV: {exc}"
            return response_data

    # JSON preview
    if ext == "json":
        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                content = json.load(f)
            response_data["preview_type"] = "json"
            response_data["json_content"] = content
            return response_data
        except Exception as exc:
            try:
                with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read(50000)
                response_data["preview_type"] = "text"
                response_data["text_content"] = text_content
                return response_data
            except Exception:
                response_data["preview_type"] = "error"
                response_data["error_message"] = f"Could not read JSON file: {exc}"
                return response_data

    # General Text preview
    if ext in ("txt", "log", "md", "yaml", "yml", "xml", "html"):
        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                text_content = f.read(50000)
            response_data["preview_type"] = "text"
            response_data["text_content"] = text_content
            return response_data
        except Exception as exc:
            response_data["preview_type"] = "error"
            response_data["error_message"] = f"Could not read text file: {exc}"
            return response_data

    # Binary / Archive / Model
    response_data["preview_type"] = "binary"
    response_data["message"] = f"Binary file ({ext.upper()}) cannot be previewed as text. Use download."
    return response_data
