import pytest
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from workspace_manager import (
    build_workspace_tree,
    list_workspace_flat,
    get_file_preview,
    resolve_safe_path,
    export_cuc_manifest,
    export_dic_manifest,
    get_tenant_dir,
)

def test_workspace_tree_structure():
    tree_res = build_workspace_tree("global", include_sessions=False)
    assert tree_res["status"] == "ok"
    assert tree_res["tenant_id"] == "global"
    assert "tree" in tree_res
    root = tree_res["tree"]
    assert root["name"] == "global"
    assert root["type"] == "directory"
    
    # Verify categories exist
    child_names = [c["name"] for c in root.get("children", [])]
    assert "runs" in child_names
    assert "uploads" in child_names
    assert "manifests" in child_names
    # By default, sessions should not be in children when include_sessions=False
    assert "sessions" not in child_names

def test_workspace_file_preview():
    # Test preview on a known CSV in global/runs/run_4d9a27ef/
    preview = get_file_preview("runs/run_4d9a27ef/all_groups_combined.csv", "global")
    if preview.get("status") != 404:
        assert preview["preview_type"] == "tabular"
        assert len(preview.get("columns", [])) > 0
        assert len(preview.get("rows", [])) > 0

def test_workspace_manifest_export_and_safe_path():
    test_cuc = {
        "primary_intent": "predict_rul",
        "task_family": "regression",
        "domain": "oil_and_gas",
        "target_hint": "RUL"
    }
    cuc_path = export_cuc_manifest("global", "test_sess_999", test_cuc)
    assert os.path.exists(cuc_path)
    
    safe = resolve_safe_path("manifests/cuc_test_sess_999.json", "global")
    assert safe is not None
    assert os.path.exists(safe)
    
    preview = get_file_preview("manifests/cuc_test_sess_999.json", "global")
    assert preview["preview_type"] == "json"
    assert preview["json_content"]["primary_intent"] == "predict_rul"
    
    # Cleanup test file
    if os.path.exists(cuc_path):
        os.remove(cuc_path)

def test_directory_traversal_protection():
    # Trying to break out of workspace should return None
    assert resolve_safe_path("../../backend/app.py", "global") is None
    assert resolve_safe_path("/etc/passwd", "global") is None
