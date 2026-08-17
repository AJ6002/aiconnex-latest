"""
runner.py — AIConnex ML Pipeline Main Orchestrator
===================================================
Executes the complete 10-node DAG from manifest to deployed model:

  SCOPE → ACQUIRE → PREPARE → SPLIT → ENGINEER → TRAIN → VG_1 → VG_2 → DEPLOY → REPORT

Usage:
    python runner.py --manifest manifest.json

Or in code:
    from services.aiconnex_ml.runner import PipelineRunner
    runner = PipelineRunner("manifest.json")
    final_manifest = runner.run()
"""

from __future__ import annotations
import argparse
import sys
from typing import Dict, Any

from services.aiconnex_ml.shared.utils.manifest import load_manifest, save_manifest, mark_step_complete
from services.aiconnex_ml.shared.data.loader import load_dataset
from services.aiconnex_ml.shared.splitter.policy import enforce_split
from services.aiconnex_ml.shared.data.validation_gate_1 import check_vg1
from services.aiconnex_ml.engineer_node import run_engineer_node
from services.aiconnex_ml.monitoring.validation_gate_2 import run_vg2
from services.aiconnex_ml.monitoring.reporter import generate_json_report, generate_markdown_report


MAX_VG1_RETRIES = 3
MAX_VG2_RETRIES = 2


class PipelineRunner:
    """
    Main pipeline orchestrator.
    Reads a manifest.json, runs all nodes, and writes the final manifest back.
    """

    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.manifest = load_manifest(manifest_path)
        self.manifest.setdefault("paths", {})
        self.manifest["paths"]["manifest_self"] = manifest_path

    def run(self) -> Dict[str, Any]:
        """Execute the full pipeline DAG."""
        manifest = self.manifest
        ml_task = manifest.get("ml_task", "regression")

        print(f"""
+----------------------------------------------------------+
|       AIConnex ML Pipeline v{manifest.get('pipeline_version', '2.0.0')}                       |
|  Run ID: {manifest.get('pipeline_run_id', 'N/A')[:40]:40s}  |
|  Task:   {ml_task:51s} |
+----------------------------------------------------------+
""")

        # ── Node 1: SCOPE ─────────────────────────────────────────────────────
        self._log_node("SCOPE")
        # Manifest is already loaded and validated via Pydantic on entry
        # If deep validation is needed, import config.Manifest and validate here
        manifest = mark_step_complete(manifest, "scope")

        # ── Node 2: ACQUIRE ───────────────────────────────────────────────────
        self._log_node("ACQUIRE")
        df, manifest = load_dataset(manifest)
        manifest = mark_step_complete(manifest, "acquire")

        # ── Node 3: SPLIT (topology-enforced, before feature engineering) ─────
        self._log_node("SPLIT")
        df_train, df_val, df_test, manifest = enforce_split(df, manifest)
        manifest = mark_step_complete(manifest, "split")

        # ── Node 4: ENGINEER ──────────────────────────────────────────────────
        self._log_node("ENGINEER")
        X_train, y_train, X_val, y_val, X_test, y_test, feature_cols, manifest, df_train, df_val, df_test = \
            run_engineer_node(df_train, df_val, df_test, manifest)

        # ── VG_1: Data Validation Gate ────────────────────────────────────────
        self._log_node("VG_1")
        import pandas as pd
        vg1_passes, report = check_vg1(manifest, pd.DataFrame(X_train, columns=feature_cols))

        retries = 0
        while not vg1_passes and retries < MAX_VG1_RETRIES:
            retries += 1
            print(f"[Runner] VG_1 failed. Retry {retries}/{MAX_VG1_RETRIES}: Applying G-02 Repair Logic...")
            # G-02 Repair Logic: mutate manifest config before re-running engineer node
            feat_cfg = manifest.setdefault("features_config", {})
            if retries == 1:
                # Repair 1: Fill NaNs aggressively and relax null threshold
                print("[Runner G-02 Repair] Relaxing null thresholds and enabling forward-fill.")
                feat_cfg["impute_missing_strategy"] = "median"
                feat_cfg["allow_stuck_sensors"] = True
            elif retries == 2:
                # Repair 2: Reduce rolling window sizes to preserve rows
                print("[Runner G-02 Repair] Reducing time window sizes to preserve training rows.")
                feat_cfg["time_window_sizes"] = [5, 10]

            X_train, y_train, X_val, y_val, X_test, y_test, feature_cols, manifest, df_train, df_val, df_test = \
                run_engineer_node(df_train, df_val, df_test, manifest)
            vg1_passes, report = check_vg1(manifest, pd.DataFrame(X_train, columns=feature_cols))

        if not vg1_passes:
            print(f"[Runner] ❌ VG_1 failed after {MAX_VG1_RETRIES} retries. Aborting.")
            manifest["status"] = "failed_vg1"
            self._finalize(manifest)
            return manifest

        # ── Node 5: TRAIN ─────────────────────────────────────────────────────
        self._log_node("TRAIN")

        if ml_task == "regression":
            from services.aiconnex_ml.regression.trainer import RegressionTrainer
            trainer = RegressionTrainer(manifest)
            manifest = trainer.run(
                X_train, y_train, X_val, y_val, X_test, y_test,
                feature_cols=feature_cols, df_test=df_test
            )

        elif ml_task == "anomaly":
            from services.aiconnex_ml.anomaly.trainer import AnomalyTrainer
            import numpy as np
            fault_col = manifest.get("label_contract", {}).get("fault_label_column")
            y_val_true = df_val[fault_col].values if fault_col and fault_col in df_val.columns else None
            y_test_true = df_test[fault_col].values if fault_col and fault_col in df_test.columns else None

            trainer = AnomalyTrainer(manifest)
            manifest = trainer.run(
                df_train, df_val, df_test, feature_cols,
                y_val_true=y_val_true, y_test_true=y_test_true
            )

        else:
            print(f"[Runner] ⚠️  ml_task='{ml_task}' training not yet implemented. Skipping TRAIN node.")

        # ── VG_2: Model Quality Gate ──────────────────────────────────────────
        self._log_node("VG_2")
        vg2_passes, _ = run_vg2(manifest)

        retries = 0
        while not vg2_passes and retries < MAX_VG2_RETRIES:
            retries += 1
            print(f"[Runner] VG_2 failed. Retry {retries}/{MAX_VG2_RETRIES}: Applying G-03 Config Mutation...")
            # G-03 Config Mutation Logic: alter model search space / hyperparameters
            hpo_cfg = manifest.setdefault("hpo_config", {})
            candidates = manifest.get("candidate_algorithms", [])
            if retries == 1:
                # Mutation 1: Double HPO search iterations and enable secondary candidate algorithm
                print("[Runner G-03 Mutation] Doubling HPO iterations and broadening algorithm search.")
                hpo_cfg["n_iter"] = int(hpo_cfg.get("n_iter", 30)) * 2
                if len(candidates) > 1:
                    manifest["candidate_algorithms"] = candidates[1:] + [candidates[0]]
            elif retries == 2:
                # Mutation 2: Enable polynomial interaction features
                print("[Runner G-03 Mutation] Enabling polynomial interaction features for high capacity.")
                manifest.setdefault("features_config", {})["interaction_features"] = True

            if ml_task == "regression":
                trainer = RegressionTrainer(manifest)
                manifest = trainer.run(
                    X_train, y_train, X_val, y_val, X_test, y_test,
                    feature_cols=feature_cols, df_test=df_test
                )
            elif ml_task == "anomaly":
                trainer = AnomalyTrainer(manifest)
                manifest = trainer.run(df_train, df_val, df_test, feature_cols)
            vg2_passes, _ = run_vg2(manifest)

        if not vg2_passes:
            print(f"[Runner] ❌ VG_2 failed after {MAX_VG2_RETRIES} retries. Model not deployed.")
            manifest["status"] = "failed_vg2"
            self._finalize(manifest)
            return manifest

        # ── Node 6: DEPLOY + REPORT ───────────────────────────────────────────
        self._log_node("DEPLOY")
        manifest["status"] = "deployed"
        manifest = mark_step_complete(manifest, "deploy")

        self._log_node("REPORT")
        reports_dir = manifest.get("paths", {}).get("reports", "outputs/reports")
        run_id = manifest.get("pipeline_run_id", "run")
        generate_json_report(manifest, f"{reports_dir}/{run_id}_report.json")
        generate_markdown_report(manifest, f"{reports_dir}/{run_id}_report.md")
        manifest = mark_step_complete(manifest, "report")

        print(f"""
+----------------------------------------------------------+
|  ✅ PIPELINE COMPLETE — Status: DEPLOYED                 |
+----------------------------------------------------------+
""")
        self._finalize(manifest)
        return manifest

    def _log_node(self, node_name: str) -> None:
        print(f"\n{'-'*60}")
        print(f"  > NODE: {node_name}")
        print(f"{'-'*60}")

    def _finalize(self, manifest: Dict[str, Any]) -> None:
        """Save final manifest to disk."""
        path = manifest.get("paths", {}).get("manifest_self", self.manifest_path)
        save_manifest(manifest, path)
        print(f"[Runner] Final manifest saved: {path}")
        self.manifest = manifest


def main():
    parser = argparse.ArgumentParser(description="AIConnex ML Pipeline Runner")
    parser.add_argument("--manifest", required=True, help="Path to manifest.json")
    args = parser.parse_args()

    runner = PipelineRunner(args.manifest)
    final_manifest = runner.run()
    status = final_manifest.get("status", "unknown")
    sys.exit(0 if status == "deployed" else 1)


if __name__ == "__main__":
    main()
