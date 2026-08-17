import io
import os
import json
import hashlib
import pandas as pd
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any
import uvicorn

from profiler import generate_profile
from detector import detect_family

app = FastAPI(
    title="Dataset Profiler API",
    description="Processes tabular datasets and returns profiling statistics along with recommended ML algorithm families.",
    version="1.0.0"
)

# Enable CORS for frontend dashboard communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "service": "Dataset Profiler API"}

@app.post("/api/v1/compile")
async def compile_zip(file: UploadFile = File(...)):
    # Save to a temporary file, retaining the original extension
    import tempfile
    import shutil
    from pathlib import Path
    
    suffix = Path(file.filename).suffix
    fd, temp_zip_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    
    try:
        # Read uploaded zip file contents
        contents = await file.read()
        with open(temp_zip_path, "wb") as f:
            f.write(contents)
            
        # Run compiler
        import sys
        services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        aic_root = os.path.dirname(services_dir)
        if aic_root not in sys.path:
            sys.path.insert(0, aic_root)
        if services_dir not in sys.path:
            sys.path.insert(0, services_dir)
            
        from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
        
        # Output directory is inside workspace_data
        zip_stem = os.path.splitext(file.filename)[0]
        # Keep directory name short and safe
        if len(zip_stem) > 40:
            import hashlib
            zip_dir_name = "compiled_" + hashlib.md5(zip_stem.encode()).hexdigest()[:12]
        else:
            zip_dir_name = "compiled_" + zip_stem
            
        output_dir = os.path.join(services_dir, "workspace_data", zip_dir_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # If direct CSV or TSV upload, skip ZIP compiler and save directly
        if file.filename.lower().endswith(".csv") or file.filename.lower().endswith(".tsv"):
            dest_csv_path = os.path.join(output_dir, file.filename)
            shutil.copy(temp_zip_path, dest_csv_path)
            first_csv = dest_csv_path
            duration_sec = 0.01
            merged_files_list = [dest_csv_path]
            combined_file_path = dest_csv_path
        else:
            from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
            compiler = UnifiedCompiler(temp_zip_path, output_dir, enable_intelligence=False)
            res = compiler.compile()
            
            if not res.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Compilation failed: {res.error}"
                )
                
            first_csv = res.merged_files[0] if res.merged_files else (res.combined_file or "")
            duration_sec = res.duration_seconds
            merged_files_list = res.merged_files
            combined_file_path = res.combined_file

        
        # Create manifest.json inside output_dir
        manifest_path = os.path.join(output_dir, "manifest.json")
        manifest = {
            "dataset_name": zip_stem,
            "compiled_file_path": first_csv,
            "status": "compiled",
            "pipeline_step": "compile",
            "compiler_report": {
                "duration_seconds": duration_sec,
                "merged_files": merged_files_list,
                "combined_file": combined_file_path,
            }
        }
        try:
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, indent=2)
        except Exception as me:
            print(f"Error writing manifest.json: {me}")
            
        # Log to SQLite
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import sqlite_tracker
            sqlite_tracker.init_run(run_id=zip_dir_name, dataset_name=zip_stem, dag_id="", family="", suggested_task="")
            sqlite_tracker.log_step(run_id=zip_dir_name, step_name="Compile (Unified Compiler)", status="success", output_file=first_csv, metrics={"duration_seconds": duration_sec})

            sqlite_tracker.update_run_manifest(run_id=zip_dir_name, manifest_dict=manifest)
        except Exception as sqle:
            print(f"Error logging compile step to SQLite: {sqle}")

        # Let's read first few rows of the first_csv to provide preview columns and rows
        preview_cols = []
        preview_rows = []
        total_rows = 0
        total_cols = 0
        if first_csv and os.path.exists(first_csv):
            try:
                df = pd.read_csv(first_csv)
                total_rows = len(df)
                total_cols = len(df.columns)
                for col in df.columns[:10]:
                    preview_cols.append({
                        "name": col,
                        "type": str(df[col].dtype),
                        "badge": "bg-emerald-100 text-emerald-800" if "float" in str(df[col].dtype) else "bg-blue-100 text-blue-800"
                    })
                # First 8 rows
                for _, row in df.head(8).iterrows():
                    preview_row = {}
                    for col in df.columns[:10]:
                        val = row[col]
                        if isinstance(val, (int, float)) and not pd.isna(val):
                            preview_row[col] = f"{val:.4f}" if isinstance(val, float) else str(val)
                        else:
                            preview_row[col] = str(val) if not pd.isna(val) else ""
                    preview_rows.append(preview_row)
            except Exception as pe:
                print("Error reading preview data:", pe)
                
        # Load dataset card and join audit details
        dataset_card = {}
        card_file = os.path.join(output_dir, "dataset_card.json")
        if os.path.exists(card_file):
            try:
                with open(card_file, "r", encoding="utf-8") as card_f:
                    dataset_card = json.load(card_f)
            except Exception:
                pass
                
        join_audits = []
        audit_file = os.path.join(output_dir, "join_audit.json")
        if os.path.exists(audit_file):
            try:
                with open(audit_file, "r", encoding="utf-8") as audit_f:
                    join_audits = json.load(audit_f).get("audits", [])
            except Exception:
                pass
                
        schema_map = {}
        schema_file = os.path.join(output_dir, "schema_map.json")
        if os.path.exists(schema_file):
            try:
                with open(schema_file, "r", encoding="utf-8") as schema_f:
                    schema_map = json.load(schema_f)
            except Exception:
                pass
                
        return {
            "status": "success",
            "filename": file.filename,
            "duration_seconds": duration_sec,
            "output_dir": output_dir,
            "merged_files": merged_files_list,
            "combined_file": combined_file_path,
            "first_csv": first_csv,
            "total_rows": total_rows,
            "total_cols": total_cols,

            "preview_columns": preview_cols,
            "preview_rows": preview_rows,
            "dataset_card": dataset_card,
            "join_audits": join_audits,
            "schema_map": schema_map
        }
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while compiling the ZIP archive: {str(e)}"
        )
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)

@app.post("/api/v1/profile")
async def profile_dataset(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    target_column: Optional[str] = Form(None),
    entity_column: Optional[str] = Form(None),
    timestamp_column: Optional[str] = Form(None),
    problem_type: Optional[str] = Form(None)
):
    # Validate input parameters
    if file_path:
        # Resolve path relative to parent directory if it's relative
        resolved_path = os.path.abspath(file_path)
        if not os.path.exists(resolved_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            resolved_path = os.path.join(base_dir, file_path)
        if not os.path.exists(resolved_path):
            raise HTTPException(
                status_code=400,
                detail=f"Local file path not found: {file_path}"
            )
        filename = os.path.basename(resolved_path)
        try:
            with open(resolved_path, "rb") as f:
                contents = f.read()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read local file: {str(e)}"
            )
    elif file:
        filename = file.filename
        contents = await file.read()
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'file' or 'file_path' must be provided."
        )

    # Validate file extension
    filename_lower = filename.lower()
    if not (filename_lower.endswith('.csv') or filename_lower.endswith('.json') or filename_lower.endswith('.txt') or filename_lower.endswith(('.xlsx', '.xls')) or filename_lower.endswith('.mat') or filename_lower.endswith('.zip')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a CSV (.csv), JSON (.json), TXT (.txt), Excel (.xlsx/.xls), MATLAB (.mat), or ZIP (.zip) file."
        )

    try:
        # Derive a safe short directory name to avoid Windows MAX_PATH (260 chars) crashes
        if "manufacturing" in filename_lower:
            ds_number = "ds3"
        elif "equipment_anomaly" in filename_lower:
            ds_number = "ds4"
        else:
            raw_stem = os.path.splitext(filename)[0]
            if len(raw_stem) > 40:
                # Hash the long stem to a safe 12-char identifier
                ds_number = "ds_" + hashlib.md5(raw_stem.encode()).hexdigest()[:12]
            else:
                ds_number = raw_stem
            
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_data_dir = os.path.join(base_dir, "workspace_data", ds_number)
        os.makedirs(workspace_data_dir, exist_ok=True)
        
        stem, ext = os.path.splitext(filename)
        if ext.lower() in ('.xlsx', '.xls', '.json', '.mat', '.txt'):
            saved_filename = stem[:76] + ".csv"
        else:
            saved_filename = filename[:80]
            
        saved_file_path = os.path.join(workspace_data_dir, saved_filename)
        
        if not filename_lower.endswith(('.xlsx', '.xls', '.json', '.mat', '.txt', '.zip')):
            try:
                with open(saved_file_path, "wb") as fout:
                    fout.write(contents)
            except OSError:
                # Disk persistence failed (e.g., path too long on Windows) — continue with in-memory path
                saved_file_path = os.path.join(workspace_data_dir, ds_number + ".csv")
                try:
                    with open(saved_file_path, "wb") as fout:
                        fout.write(contents)
                except OSError:
                    saved_file_path = "<in-memory-only>"

            
        # Read dataset into pandas DataFrame
        if filename_lower.endswith('.csv'):
            import re
            decoded = contents.decode('utf-8', errors='ignore')
            lines = decoded.strip().split('\n')
            
            # Find the header row index
            header_idx = 0
            header_keywords = {"date", "time", "timestamp", "s/n", "serial", "unit_id", "cycle", "lcv", "flow", "discharge", "suction", "press", "temp"}
            for idx, line in enumerate(lines[:30]):
                tokens = [t.strip().lower() for t in re.split(r"[,;\t]", line) if t.strip()]
                if any(any(kw in tok for kw in header_keywords) for tok in tokens):
                    header_idx = idx
                    break
            
            # Check if headerless numeric CSV
            if lines:
                check_line = lines[header_idx].split(',')
                is_numeric = True
                for val in check_line[:5]:
                    try:
                        float(val.strip())
                    except ValueError:
                        is_numeric = False
                        break
                if is_numeric:
                    df = pd.read_csv(io.StringIO(decoded), header=None)
                    if df.shape[1] == 26:
                        df.columns = ["unit_id", "cycle", "op_setting_1", "op_setting_2", "op_setting_3"] + [f"sensor_{i}" for i in range(1, 22)]
                    else:
                        df.columns = [f"col_{i}" for i in range(df.shape[1])]
                else:
                    df = pd.read_csv(io.StringIO(decoded), header=header_idx)
            else:
                df = pd.DataFrame()
        elif filename_lower.endswith('.txt') or filename.endswith('.txt'):
            import re
            decoded = contents.decode('utf-8', errors='ignore')
            lines = decoded.strip().split('\n')
            
            # Find the header row index
            header_idx = 0
            header_keywords = {"date", "time", "timestamp", "s/n", "serial", "unit_id", "cycle", "lcv", "flow", "discharge", "suction", "press", "temp"}
            for idx, line in enumerate(lines[:30]):
                tokens = [t.strip().lower() for t in re.split(r"[\s,;\t]+", line) if t.strip()]
                if any(any(kw in tok for kw in header_keywords) for tok in tokens):
                    header_idx = idx
                    break
            
            # Check if headerless numeric space-separated
            if lines:
                check_line = lines[header_idx].split()
                is_numeric = True
                for val in check_line[:5]:
                    try:
                        float(val.strip())
                    except ValueError:
                        is_numeric = False
                        break
                if is_numeric:
                    df = pd.read_csv(io.StringIO(decoded), sep=r'\s+', header=None)
                    if df.shape[1] == 26:
                        df.columns = ["unit_id", "cycle", "op_setting_1", "op_setting_2", "op_setting_3"] + [f"sensor_{i}" for i in range(1, 22)]
                    else:
                        df.columns = [f"col_{i}" for i in range(df.shape[1])]
                else:
                    df = pd.read_csv(io.StringIO(decoded), sep=r'\s+', header=header_idx)
            else:
                df = pd.DataFrame()
        elif filename_lower.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(io.BytesIO(contents))
            skip_idx = None
            for idx in range(min(15, len(df_raw))):
                row_vals = [str(x).lower() for x in df_raw.iloc[idx].values]
                if any("date" in v or "time" in v or "timestamp" in v for v in row_vals):
                    skip_idx = idx
                    break
            if skip_idx is not None:
                df = pd.read_excel(io.BytesIO(contents), header=skip_idx + 1)
            else:
                df = df_raw
        elif filename_lower.endswith('.mat'):
            import scipy.io as sio
            mat = sio.loadmat(io.BytesIO(contents))
            data_key = None
            for k in mat.keys():
                if not k.startswith("__"):
                    data_key = k
                    break
            if data_key is not None:
                df = pd.DataFrame(mat[data_key])
            else:
                raise ValueError("No valid key found in MAT file.")
        elif filename_lower.endswith('.zip'):
            import tempfile
            import shutil
            import zipfile
            from pathlib import Path
            from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
            
            suffix = ".zip"
            fd, temp_zip_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                with open(temp_zip_path, "wb") as f:
                    f.write(contents)
                
                services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                zip_stem = os.path.splitext(filename)[0]
                zip_dir_name = "compiled_profile_" + hashlib.md5(zip_stem.encode()).hexdigest()[:12]
                output_dir = os.path.join(services_dir, "workspace_data", zip_dir_name)
                os.makedirs(output_dir, exist_ok=True)
                
                try:
                    compiler = UnifiedCompiler(temp_zip_path, output_dir)
                    res = compiler.compile()
                    if res.success and res.merged_files:
                        first_csv = res.merged_files[0]
                        if first_csv and os.path.exists(first_csv):
                            df = pd.read_csv(first_csv)
                        else:
                            raise ValueError("No compiled csv path found.")
                    else:
                        raise ValueError(res.error or "No files compiled")
                except Exception as compile_err:
                    # Fallback extraction: extract raw files and find the first data file (.csv, .xlsx, .xls, .json, .mat, .txt)
                    fallback_dir = os.path.join(output_dir, "fallback_extracted")
                    os.makedirs(fallback_dir, exist_ok=True)
                    with zipfile.ZipFile(temp_zip_path, 'r') as z:
                        z.extractall(fallback_dir)
                    
                    found_file = None
                    for root_dir_walk, dirs, files in os.walk(fallback_dir):
                        for f in files:
                            fl = f.lower()
                            if fl.endswith(('.csv', '.xlsx', '.xls', '.json', '.mat', '.txt')):
                                found_file = os.path.join(root_dir_walk, f)
                                break
                        if found_file:
                            break
                    
                    if not found_file:
                        raise ValueError(f"Zip compilation failed: {compile_err}. Fallback extraction also found no tabular data files.")
                    
                    # Read the found file and convert if necessary
                    ff_lower = found_file.lower()
                    is_convertible = ff_lower.endswith(('.xlsx', '.xls', '.json', '.mat'))
                    
                    if ff_lower.endswith('.csv'):
                        df = pd.read_csv(found_file)
                    elif ff_lower.endswith('.txt'):
                        df = pd.read_csv(found_file, sep=r'\s+')
                    elif ff_lower.endswith(('.xlsx', '.xls')):
                        df_raw = pd.read_excel(found_file)
                        skip_idx = None
                        for idx in range(min(15, len(df_raw))):
                            row_vals = [str(x).lower() for x in df_raw.iloc[idx].values]
                            if any("date" in v or "time" in v or "timestamp" in v for v in row_vals):
                                skip_idx = idx
                                break
                        if skip_idx is not None:
                            df = pd.read_excel(found_file, header=skip_idx + 1)
                        else:
                            df = df_raw
                    elif ff_lower.endswith('.mat'):
                        import scipy.io as sio
                        mat = sio.loadmat(found_file)
                        data_key = None
                        for k in mat.keys():
                            if not k.startswith("__"):
                                data_key = k
                                break
                        if data_key is not None:
                            df = pd.DataFrame(mat[data_key])
                        else:
                            raise ValueError("No valid key found in MAT file.")
                    else:
                        with open(found_file, 'rb') as f_in:
                            decoded = f_in.read().decode('utf-8', errors='ignore')
                        df = pd.read_json(io.StringIO(decoded))

                        
                    if is_convertible:
                        converted_csv_path = os.path.splitext(found_file)[0] + ".csv"
                        df.to_csv(converted_csv_path, index=False)
                        saved_file_path = converted_csv_path
                    else:
                        saved_file_path = found_file

            finally:
                if os.path.exists(temp_zip_path):
                    try:
                        os.remove(temp_zip_path)
                    except Exception:
                        pass
        else:
            decoded = contents.decode('utf-8', errors='ignore')
            df = pd.read_json(io.StringIO(decoded))

            
        if filename_lower.endswith(('.xlsx', '.xls', '.json', '.mat', '.txt')):
            try:
                df.to_csv(saved_file_path, index=False)
            except OSError:
                saved_file_path = os.path.join(workspace_data_dir, ds_number + ".csv")
                try:
                    df.to_csv(saved_file_path, index=False)
                except OSError:
                    saved_file_path = "<in-memory-only>"

            
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse the file: {str(e)}"
        )

    if len(df) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded dataset is empty."
        )

    try:
        # 1. Generate column and dataset statistics
        profile = generate_profile(df)
        
        # 2. Detect the algorithm family
        family_result = detect_family(df, profile, target_hint=target_column)
        
        # 3. Resolve exact DAG ID from the 1690 mapping
        from detector import decide_dag_and_details
        dag_details = decide_dag_and_details(df, profile, family_result)
        
        # 4. Combine result
        profile['algorithm_family'] = family_result['algorithm_family']
        profile['family_confidence'] = family_result['family_confidence']
        profile['family_reason'] = family_result['reason']
        profile['detected_target'] = family_result['target_column']
        profile['suggested_task'] = family_result['suggested_task']
        
        # Add dynamic DAG recommendation fields
        profile['recommended_dag_id'] = dag_details['recommended_dag_id']
        profile['recommended_algorithm'] = dag_details['recommended_algorithm']
        profile['recommended_variant'] = dag_details['recommended_variant']
        profile['recommended_special_handling'] = dag_details['recommended_special_handling']
        profile['raw_file_path'] = saved_file_path

        # ── Correction: Mirror top-level dimension keys so clients don't need to dig into dataset_info
        profile['num_rows'] = profile['dataset_info']['num_rows']
        profile['num_cols'] = profile['dataset_info']['num_columns']
        
        # Save meta1.json inside 1_dataset_profiler/meta/
        meta_payload = {
            "status": "success",
            "filename": filename,
            "profile": profile
        }
        
        meta_dir = os.path.join(os.path.dirname(__file__), "meta")
        os.makedirs(meta_dir, exist_ok=True)
        meta_path = os.path.join(meta_dir, "meta1.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_payload, f, indent=2)

        # Copy dataset to profiled_<dataset_name>.csv and update manifest
        dataset_name = os.path.splitext(filename)[0]
        if dataset_name.startswith("compiled_"):
            dataset_name = dataset_name[9:]
        profiled_filename = f"profiled_{dataset_name}.csv"
        
        if workspace_data_dir and workspace_data_dir != "<in-memory-only>" and os.path.exists(workspace_data_dir):
            profiled_file_path = os.path.join(workspace_data_dir, profiled_filename)
            try:
                df.to_csv(profiled_file_path, index=False)
            except Exception as e:
                print(f"Error saving profiled dataset: {e}")
                profiled_file_path = saved_file_path
        else:
            profiled_file_path = saved_file_path
            
        # Override with user inputs if specified (e.g. for non-technical/illiterate interface)
        if target_column:
            profile['detected_target'] = target_column
        if problem_type:
            fam_mapping = {
                "regression": "Regression",
                "classification": "Classification",
                "anomaly": "Anomaly Detection",
                "time-series": "Time-Series"
            }
            family = fam_mapping.get(problem_type.lower(), problem_type)
            profile['algorithm_family'] = family
            profile['suggested_task'] = family
            fallback_ids = {
                "Classification": "DAG_001",
                "Regression": "DAG_283",
                "Anomaly Detection": "DAG_573",
                "Clustering": "DAG_820",
                "Time-Series": "DAG_1059",
                "Digital Twin": "DAG_1316",
                "Reinforcement Learning": "DAG_1451",
                "Recommendation": "DAG_1572",
                "NLP/Text-Classification": "DAG_1705",
                "Computer Vision": "DAG_1837"
            }
            profile['recommended_dag_id'] = fallback_ids.get(family, "DAG_001")

        profile['profiled_file_path'] = profiled_file_path
        
        if workspace_data_dir and workspace_data_dir != "<in-memory-only>" and os.path.exists(workspace_data_dir):
            manifest_path = os.path.join(workspace_data_dir, "manifest.json")
            manifest = {}
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as mf:
                        manifest = json.load(mf)
                except Exception:
                    pass
            
            manifest.update({
                "dataset_name": dataset_name,
                "raw_file_path": saved_file_path,
                "profiled_file_path": profiled_file_path,
                "profile": profile,
                "target_column": profile.get("detected_target"),
                "entity_column": entity_column or manifest.get("entity_column"),
                "timestamp_column": timestamp_column or manifest.get("timestamp_column"),
                "schema_config": {
                    "entity_column": entity_column or manifest.get("entity_column"),
                    "timestamp_column": timestamp_column or manifest.get("timestamp_column")
                },
                "dag_id": profile.get("recommended_dag_id"),
                "algorithm_family": profile.get("algorithm_family"),
                "suggested_task": profile.get("suggested_task"),
                "status": "profiled",
                "pipeline_step": "profile"
            })
            try:
                with open(manifest_path, "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, indent=2)
            except Exception as me:
                print(f"Error writing manifest.json in profile: {me}")
                
            # Log to SQLite
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                import sqlite_tracker
                sqlite_tracker.init_run(run_id=ds_number, dataset_name=dataset_name, 
                                        dag_id=profile.get("recommended_dag_id", ""), 
                                        family=profile.get("algorithm_family", ""), 
                                        suggested_task=profile.get("suggested_task", ""))
                sqlite_tracker.log_step(run_id=ds_number, step_name="Dataset Profiler (Node 1)", 
                                        status="success", output_file=profiled_file_path, 
                                        metrics={"suggested_task": profile.get("suggested_task"), "num_rows": profile.get("num_rows"), "num_cols": profile.get("num_cols")})
                sqlite_tracker.update_run_manifest(run_id=ds_number, manifest_dict=manifest)
            except Exception as sqle:
                print(f"Error logging profile step to SQLite: {sqle}")

        return meta_payload
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error during profiling: {error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the dataset: {str(e)}"
        )

@app.get("/api/v1/masterdata/dag_mapping")
def get_dag_mapping():
    path = os.path.join(os.path.dirname(__file__), "dag_mapping.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="dag_mapping.json not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/v1/masterdata/dag_conditions_mapping")
def get_dag_conditions_mapping():
    path = os.path.join(os.path.dirname(__file__), "dag_conditions_mapping.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="dag_conditions_mapping.json not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/v1/masterdata/algorithm_families")
def get_algorithm_families():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "algorithm_families_complete.xlsx")
    if not os.path.exists(path):
        path = os.path.join(base_dir, "algorithm_families.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Algorithm families excel not found")
    df = pd.read_excel(path)
    # Replace NaN with None so it translates cleanly to JSON null
    df = df.replace({np.nan: None})
    return {"headers": df.columns.tolist(), "records": df.to_dict(orient="records")}

@app.get("/api/v1/masterdata/boilerplate_metadata")
def get_boilerplate_metadata():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "boilerplate_metadata.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="boilerplate_metadata.xlsx not found")
    df = pd.read_excel(path)
    # Replace NaN with None
    df = df.replace({np.nan: None})
    return {"headers": df.columns.tolist(), "records": df.to_dict(orient="records")}

@app.get("/api/v1/masterdata/boilerplate_profiler_readme")
def get_boilerplate_profiler_readme():
    path = os.path.join(os.path.dirname(__file__), "README.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="README.md not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"content": f.read()}

@app.get("/api/v1/masterdata/boilerplate_dag_readme")
def get_boilerplate_dag_readme():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "2_dag", "README.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="README.md not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"content": f.read()}

@app.get("/api/v1/masterdata/boilerplate_recipe_readme")
def get_boilerplate_recipe_readme():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "3_recipe_orchestrator", "README.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="README.md not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"content": f.read()}

@app.get("/api/v1/masterdata/recipe/{dag_id}")
def get_recipe(dag_id: str):
    import json
    base_dir = os.path.dirname(os.path.dirname(__file__))
    recipe_dir = os.path.join(base_dir, "3_recipe_orchestrator", "recipe")
    
    # Query central transit mapping JSON database directly for any arbitrary DAG ID
    db_path = os.path.join(base_dir, "Documentation", "transit_mappings", "algorithm_dags_transit_mapping.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            if dag_id in db:
                recipes = db[dag_id]["recipes"]
                return {
                    "preparing": recipes["prepare_recipe"],
                    "feature_engineering": recipes["feature_engineering_recipe"],
                    "splitting": recipes["splitting_recipe"],
                    "training": recipes["training_recipe"]
                }
        except Exception as db_err:
            print("Error loading from transit mapping database in profiler:", db_err)
            
    prep_path = os.path.join(recipe_dir, "preparing", f"{dag_id}.json")
    feat_path = os.path.join(recipe_dir, "feature_engineering", f"{dag_id}.json")
    split_path = os.path.join(recipe_dir, "splitting", f"{dag_id}.json")
    train_path = os.path.join(recipe_dir, "training", f"{dag_id}.json")
    
    fallback_id = "DAG_001"
    try:
        dag_num = int(dag_id.split("_")[1])
    except Exception:
        dag_num = 1
        
    if dag_num >= 1 and dag_num <= 282: fallback_id = "DAG_001"
    elif dag_num >= 283 and dag_num <= 572: fallback_id = "DAG_283"
    elif dag_num >= 573 and dag_num <= 819: fallback_id = "DAG_573"
    elif dag_num >= 820 and dag_num <= 1058: fallback_id = "DAG_820"
    elif dag_num >= 1059 and dag_num <= 1315: fallback_id = "DAG_1059"
    elif dag_num >= 1316 and dag_num <= 1450: fallback_id = "DAG_1316"
    elif dag_num >= 1451 and dag_num <= 1571: fallback_id = "DAG_1451"
    elif dag_num >= 1572 and dag_num <= 1704: fallback_id = "DAG_1572"
    elif dag_num >= 1705 and dag_num <= 1836: fallback_id = "DAG_1705"
    elif dag_num >= 1837 and dag_num <= 1993: fallback_id = "DAG_1837"

    if not os.path.exists(prep_path): prep_path = os.path.join(recipe_dir, "preparing", f"{fallback_id}.json")
    if not os.path.exists(feat_path): feat_path = os.path.join(recipe_dir, "feature_engineering", f"{fallback_id}.json")
    if not os.path.exists(split_path): split_path = os.path.join(recipe_dir, "splitting", f"{fallback_id}.json")
    if not os.path.exists(train_path): train_path = os.path.join(recipe_dir, "training", f"{fallback_id}.json")
        
    try:
        with open(prep_path, "r", encoding="utf-8") as f: prep_data = json.load(f)
        with open(feat_path, "r", encoding="utf-8") as f: feat_data = json.load(f)
        with open(split_path, "r", encoding="utf-8") as f: split_data = json.load(f)
        with open(train_path, "r", encoding="utf-8") as f: train_data = json.load(f)
        return {
            "preparing": prep_data,
            "feature_engineering": feat_data,
            "splitting": split_data,
            "training": train_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read recipe files: {str(e)}")

@app.post("/api/v1/masterdata/recipe/{dag_id}")
def save_recipe(dag_id: str, payload: dict):
    import json
    base_dir = os.path.dirname(os.path.dirname(__file__))
    recipe_dir = os.path.join(base_dir, "3_recipe_orchestrator", "recipe")
    
    prep_path = os.path.join(recipe_dir, "preparing", f"{dag_id}.json")
    feat_path = os.path.join(recipe_dir, "feature_engineering", f"{dag_id}.json")
    split_path = os.path.join(recipe_dir, "splitting", f"{dag_id}.json")
    train_path = os.path.join(recipe_dir, "training", f"{dag_id}.json")
    
    try:
        if "preparing" in payload:
            os.makedirs(os.path.dirname(prep_path), exist_ok=True)
            with open(prep_path, "w", encoding="utf-8") as f: json.dump(payload["preparing"], f, indent=4)
        if "feature_engineering" in payload:
            os.makedirs(os.path.dirname(feat_path), exist_ok=True)
            with open(feat_path, "w", encoding="utf-8") as f: json.dump(payload["feature_engineering"], f, indent=4)
        if "splitting" in payload:
            os.makedirs(os.path.dirname(split_path), exist_ok=True)
            with open(split_path, "w", encoding="utf-8") as f: json.dump(payload["splitting"], f, indent=4)
        if "training" in payload:
            os.makedirs(os.path.dirname(train_path), exist_ok=True)
            with open(train_path, "w", encoding="utf-8") as f: json.dump(payload["training"], f, indent=4)
        return {"status": "success", "message": f"Recipes for {dag_id} saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save recipe: {str(e)}")

class ProfilePlotPayload(BaseModel):
    file_path: str
    column: Optional[str] = None

@app.post("/api/v1/plots/correlation")
def get_correlation_plot(payload: ProfilePlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="Dataset file not found")
        df = pd.read_csv(payload.file_path)
        numeric_df = df.select_dtypes(include=[np.number])
        if numeric_df.empty:
            return {"columns": [], "matrix": []}
        cols = list(numeric_df.columns[:12])
        corr_matrix = numeric_df[cols].corr().fillna(0).round(3).values.tolist()
        return {"columns": cols, "matrix": corr_matrix}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/plots/distribution")
def get_distribution_plot(payload: ProfilePlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="Dataset file not found")
        df = pd.read_csv(payload.file_path)
        col = payload.column or (df.columns[0] if len(df.columns) > 0 else None)
        if not col or col not in df.columns:
            return {"column": col, "bins": [], "counts": []}
        series = df[col].dropna()
        if pd.api.types.is_numeric_dtype(series):
            counts, bin_edges = np.histogram(series, bins=15)
            bins = [f"{round(bin_edges[i],2)}-{round(bin_edges[i+1],2)}" for i in range(len(counts))]
            return {"column": col, "type": "numeric", "bins": bins, "counts": counts.tolist()}
        else:
            val_counts = series.value_counts().head(10)
            return {"column": col, "type": "categorical", "bins": val_counts.index.tolist(), "counts": val_counts.values.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/plots/missing_matrix")
def get_missing_matrix_plot(payload: ProfilePlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="Dataset file not found")
        df = pd.read_csv(payload.file_path)
        missing_counts = df.isna().sum()
        missing_pcts = (missing_counts / len(df) * 100).round(2)
        return {
            "columns": list(df.columns),
            "missing_counts": missing_counts.tolist(),
            "missing_percentages": missing_pcts.tolist(),
            "total_rows": len(df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/plots/outliers")
def get_outliers_plot(payload: ProfilePlotPayload):
    try:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="Dataset file not found")
        df = pd.read_csv(payload.file_path)
        col = payload.column or ([c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])][:1] or [df.columns[0]])[0]
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            return {"column": col, "outliers_count": 0}
        series = df[col].dropna()
        q25, q75 = series.quantile(0.25), series.quantile(0.75)
        iqr = q75 - q25
        lower, upper = q25 - 1.5 * iqr, q75 + 1.5 * iqr
        outliers = series[(series < lower) | (series > upper)]
        return {
            "column": col,
            "min": round(float(series.min()), 2),
            "q25": round(float(q25), 2),
            "median": round(float(series.median()), 2),
            "q75": round(float(q75), 2),
            "max": round(float(series.max()), 2),
            "iqr_lower": round(float(lower), 2),
            "iqr_upper": round(float(upper), 2),
            "outliers_count": len(outliers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/masterdata/dag_mapping")
def save_dag_mapping(payload: dict):
    import json
    path1 = os.path.join(os.path.dirname(__file__), "dag_mapping.json")
    path2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "2_dag", "dag_mapping.json")
    try:
        with open(path1, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        with open(path2, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {"status": "success", "message": "dag_mapping.json updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/masterdata/dag_conditions_mapping")
def save_dag_conditions_mapping(payload: dict):
    import json
    path1 = os.path.join(os.path.dirname(__file__), "dag_conditions_mapping.json")
    path2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "2_dag", "dag_conditions_mapping.json")
    try:
        with open(path1, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        with open(path2, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {"status": "success", "message": "dag_conditions_mapping.json updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/masterdata/algorithm_families")
def save_algorithm_families(payload: dict):
    import json
    records = payload.get("records")
    if not records:
        raise HTTPException(status_code=400, detail="No records provided")
    try:
        df = pd.DataFrame(records)
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path_complete = os.path.join(base_dir, "algorithm_families_complete.xlsx")
        path_families = os.path.join(base_dir, "algorithm_families.xlsx")
        
        # Save to both Excel spreadsheets
        df.to_excel(path_complete, index=False)
        df.to_excel(path_families, index=False)
        
        # Synchronize back to dag_mapping.json
        mapping = {}
        for r in records:
            fam_name = str(r.get("FAMILY_NAME", "")).upper()
            if not fam_name:
                continue
            if fam_name not in mapping:
                mapping[fam_name] = []
            mapping[fam_name].append({
                "dag_id": r.get("DAG ID"),
                "algorithm": r.get("Algorithm"),
                "variant": r.get("Variant"),
                "special_handling": r.get("Special Handling") or ""
            })
            
        path1 = os.path.join(os.path.dirname(__file__), "dag_mapping.json")
        path2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "2_dag", "dag_mapping.json")
        with open(path1, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        with open(path2, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
            
        return {"status": "success", "message": "Algorithm families and dag_mapping.json updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/masterdata/boilerplate_metadata")
def save_boilerplate_metadata(payload: dict):
    records = payload.get("records")
    if not records:
        raise HTTPException(status_code=400, detail="No records provided")
    try:
        df = pd.DataFrame(records)
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "boilerplate_metadata.xlsx")
        df.to_excel(path, index=False)
        return {"status": "success", "message": "boilerplate_metadata.xlsx updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/masterdata/dag_mapping")
def get_dag_mapping():
    path = os.path.join(os.path.dirname(__file__), "dag_mapping.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/v1/masterdata/dag_conditions_mapping")
def get_dag_conditions_mapping():
    path = os.path.join(os.path.dirname(__file__), "dag_conditions_mapping.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/v1/masterdata/algorithm_families")
def get_algorithm_families():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "algorithm_families_complete.xlsx")
    if not os.path.exists(path):
        return {"records": []}
    try:
        df = pd.read_excel(path)
        df = df.where(pd.notnull(df), None)
        return {"records": df.to_dict(orient="records")}
    except Exception as e:
        return {"records": []}

@app.get("/api/v1/masterdata/boilerplate_metadata")
def get_boilerplate_metadata():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "boilerplate_metadata.xlsx")
    if not os.path.exists(path):
        return {"records": []}
    try:
        df = pd.read_excel(path)
        df = df.where(pd.notnull(df), None)
        return {"records": df.to_dict(orient="records")}
    except Exception as e:
        return {"records": []}

@app.get("/api/v1/workspace/files")
def list_workspace_files():
    services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workspace_dir = os.path.join(os.path.dirname(services_dir), "workspace_data")
    if not os.path.exists(workspace_dir):
        return {"items": []}
    
    items = []
    for root, dirs, files in os.walk(workspace_dir):
        for name in files:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, workspace_dir)
            size = os.path.getsize(full_path)
            items.append({
                "name": name,
                "path": rel_path.replace("\\", "/"),
                "size_bytes": size,
                "is_dir": False
            })
        for name in dirs:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, workspace_dir)
            items.append({
                "name": name,
                "path": rel_path.replace("\\", "/"),
                "size_bytes": 0,
                "is_dir": True
            })
    return {"items": items}

MASTER_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "master_data.json")

DEFAULT_MASTER_DATA = {
    "recipes": {
        "imputation": "median",
        "scaling": "RobustScaler",
        "test_size": "0.2",
        "features": "lag_1, lag_5, lag_10, rolling_mean_5, rolling_std_5"
    },
    "jsons": {
        "pipeline_config": "{\n  \"version\": \"1.4.2\",\n  \"stages\": [\"profile\", \"match\", \"recipe\", \"prepare\", \"feature\", \"split\", \"train\", \"eval\", \"deploy\"],\n  \"max_runtime_sec\": 3600\n}"
    },
    "boilerplates": {
        "html_report": "<!DOCTYPE html>\n<html>\n<head>\n<title>Evaluation Report</title>\n</head>\n<body>\n<h1>{{ title }}</h1>\n<p>Accuracy: {{ accuracy }}</p>\n</body>\n</html>"
    },
    "templates": {
        "json_blueprint": "{\n  \"dag_id\": \"DAG_CUSTOM\",\n  \"steps\": []\n}",
        "recipe_blueprint": "{\n  \"scaling\": \"StandardScaler\",\n  \"impute_strategy\": \"mean\"\n}",
        "training_notebook": "# Custom Training Notebook Boilerplate\nimport pandas as pd\nimport pickle\n...",
        "dag_template": "DAG: Custom_Waterfall\nNode 1 -> Node 2 -> Node 3"
    }
}

@app.get("/api/v1/master/config")
def get_master_config():
    if not os.path.exists(MASTER_DATA_FILE):
        with open(MASTER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_MASTER_DATA, f, indent=2)
        return DEFAULT_MASTER_DATA
    try:
        with open(MASTER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_MASTER_DATA

class UpdateMasterPayload(BaseModel):
    category: str
    key: str
    value: Any

@app.post("/api/v1/master/config")
def update_master_config(payload: UpdateMasterPayload):
    config = get_master_config()
    category = payload.category
    key = payload.key
    value = payload.value

    if category not in config:
        config[category] = {}
    config[category][key] = value

    with open(MASTER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return {"status": "success", "config": config}

if __name__ == "__main__":
    should_reload = os.environ.get("AIC_RELOAD", "0").lower() in ("true", "1", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=should_reload)
