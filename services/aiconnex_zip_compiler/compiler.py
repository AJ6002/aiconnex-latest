"""
compiler.py - Extensible Plugin Pipeline Ingestion Compiler Engine
===================================================================
Orchestrates:
  0. HITL Intent Layer (optional interactive terminal prompt)
  1-5. Plugin Pipeline (Discovery -> Parser -> Assembler -> Harvester -> Normalizer)

Produces deterministic, lockfile-tracked ingestion outputs for ML Node 1.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

from .handoff import export_compiler_handoff, HandoffArtifacts
from .plugins import (
    PipelineContext,
    PluginRegistry,
    UnsupportedLayoutError,
    AmbiguousPluginMatchError,
)
from .models import SchemaMap, JoinAudit, CompilerState, CompilerWorkspace

logger = logging.getLogger(__name__)


@dataclass
class CompileResult:
    input_zip: str
    output_dir: str
    merged_files: List[str]
    combined_file: Optional[str]
    artifacts: HandoffArtifacts
    audits: List[JoinAudit]
    schema_map: SchemaMap
    duration_seconds: float
    success: bool = True
    error: Optional[str] = None
    state: CompilerState = CompilerState.COMPILED
    state_history: List[str] = field(default_factory=list)


class UnifiedCompiler:
    """
    Extensible Ingestion Compiler powered by HITL Intent Layer + 5-Stage Plugin Pipeline.

    Parameters
    ----------
    zip_path : str | Path
        Path to raw .zip or dataset directory.
    output_dir : str | Path
        Destination folder for compiled CSVs, audits, and compiler_lock.json.
    interactive : bool
        If True, forces the interactive terminal prompt (halts for user input)
        even if stdin is not a tty.
    strategy_override : str, optional
        If set, bypasses the prompt and uses this strategy directly.
    batch : bool
        If True, always auto-selects the default intent option without prompting,
        regardless of tty state. Takes precedence over `interactive`.
    enable_intelligence : bool
        If True (default), runs the LLM-driven intelligence layer (7 analysis
        stages) to generate the DatasetCard, HITL question, and options
        dynamically. Falls back to the legacy heuristic path when the LLM is
        unreachable or analysis fails.
    """

    def __init__(
        self,
        zip_path: str | Path,
        output_dir: str | Path,
        interactive: bool = False,
        strategy_override: Optional[str] = None,
        batch: bool = False,
        enable_intelligence: bool = True,
        scout: Optional[Any] = None,
    ) -> None:
        self.zip_path = Path(zip_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.interactive = interactive
        self.strategy_override = strategy_override
        self.batch = batch
        self.enable_intelligence = enable_intelligence
        self.scout = scout
        self._intelligence = None  # IntelligenceOrchestrator, set during compile()

    def compile(self) -> CompileResult:
        t0 = time.time()
        import uuid
        job_id = uuid.uuid4().hex[:8]
        workspace = CompilerWorkspace(job_id=job_id)
        workspace.setup()
        temp_dir = workspace.extracted
        self.output_dir.mkdir(parents=True, exist_ok=True)

        state_history: List[str] = [CompilerState.RECEIVED.value]
        current_state = CompilerState.RECEIVED

        # -- Scout Inspection (if ScoutAgent provided) ---------------------------
        if self.scout is not None:
            try:
                current_state = CompilerState.INSPECTING
                state_history.append(current_state.value)
                logger.info("[UnifiedCompiler] ScoutAgent present - running scout.inspect()")
                self.scout.inspect(inventory=self.zip_path)
            except Exception as e:
                logger.warning(f"[UnifiedCompiler] scout.inspect() call failed: {e}")

        # -- Pre-Check: Entry Schema Gate ----------------------------------------
        from .schema_gate import SchemaGate
        gate = SchemaGate(self.zip_path)
        decision = gate.evaluate()
        if not decision.is_valid:
            current_state = CompilerState.FAILED
            state_history.append(current_state.value)
            logger.error(f"[SchemaGate] Rejected: {decision.gate_message}")
            workspace.quarantine_file(self.zip_path, reason=f"SchemaGate rejected: {decision.gate_message}")
            if self.scout is not None:
                try:
                    self.scout.self_heal(
                        error_traceback=f"SchemaGate rejected input: {decision.gate_message}",
                        zip_path=self.zip_path,
                    )
                except Exception as ex:
                    logger.warning(f"[UnifiedCompiler] scout.self_heal() on SchemaGate rejection failed: {ex}")
            return CompileResult(
                input_zip=str(self.zip_path),
                output_dir=str(self.output_dir),
                merged_files=[],
                combined_file=None,
                artifacts=HandoffArtifacts({}, None, Path(""), Path(""), Path(""), Path("")),
                audits=[],
                schema_map=SchemaMap(),
                duration_seconds=0.0,
                success=False,
                error=f"SchemaGate rejected input: {decision.gate_message}",
                state=CompilerState.FAILED,
                state_history=state_history,
            )
        logger.info(f"[SchemaGate] Passed: {decision.gate_message} (Route: {decision.primary_route})")

        try:
            # -- Initialize Pipeline Context & Plugin Registry -----------------
            context = PipelineContext(
                target_path=self.zip_path,
                temp_dir=temp_dir,
                output_dir=self.output_dir,
            )

            registry = PluginRegistry.get_instance()
            registry.auto_discover()

            # -- Intelligence Stages 1-3 (archive, formats, parser advice) ----
            current_state = CompilerState.INSPECTING
            state_history.append(current_state.value)
            self._run_intelligence_pre_parse(temp_dir, registry)

            # -- Stage 1: Discovery Plugin ------------------------------------
            current_state = CompilerState.EXECUTING
            state_history.append(current_state.value)
            disc_plugin = registry.resolve("discovery", context)
            context = disc_plugin.execute(context)
            context.active_plugins["discovery"] = f"{disc_plugin.plugin_id}@{disc_plugin.version}"

            # -- Stage 2: Parser Plugin ---------------------------------------
            parser_plugin = registry.resolve("parser", context)
            context = parser_plugin.execute(context)
            context.active_plugins["parser"] = f"{parser_plugin.plugin_id}@{parser_plugin.version}"

            # -- Scout Strategy Advice (if ScoutAgent provided) ---------------
            if self.scout is not None and context.parsed_tables:
                try:
                    scout_strat = self.scout.advise_strategy(
                        tables=context.parsed_tables,
                        inventory=context.inventory,
                    )
                    if scout_strat and self.strategy_override is None:
                        logger.info(f"[UnifiedCompiler] Scout advised strategy: {scout_strat}")
                        self.strategy_override = scout_strat
                except Exception as e:
                    logger.warning(f"[UnifiedCompiler] scout.advise_strategy() failed: {e}")

            # -- Intelligence Stages 4-7 (stats, roles, semantics, problem) ---
            # Needs real DataFrames, so it runs after parsing but before the
            # HITL prompt, because it generates the question and the options.
            self._run_intelligence_post_parse(context)

            # -- HITL Intent Layer (after parsing, before assembly) -----------
            current_state = CompilerState.WAITING_FOR_AGENT
            state_history.append(current_state.value)
            self._run_intent_layer(context)

            current_state = CompilerState.PLAN_READY
            state_history.append(current_state.value)

            # -- Stage 3: Assembler Plugin ------------------------------------
            current_state = CompilerState.EXECUTING
            state_history.append(current_state.value)
            assembler_plugin = registry.resolve("assembler", context)
            context = assembler_plugin.execute(context)
            context.active_plugins["assembler"] = f"{assembler_plugin.plugin_id}@{assembler_plugin.version}"

            # -- Stage 4: Feature Harvester Plugin (Optional) -----------------
            try:
                harvester_plugin = registry.resolve("harvester", context)
                context = harvester_plugin.execute(context)
                context.active_plugins["harvester"] = f"{harvester_plugin.plugin_id}@{harvester_plugin.version}"
            except (UnsupportedLayoutError, AmbiguousPluginMatchError):
                logger.debug("[UnifiedCompiler] Stage 4 Harvester skipped (not required for layout)")

            # -- Stage 5: Schema Normalizer Plugin ---------------------------
            normalizer_plugin = registry.resolve("normalizer", context)
            context = normalizer_plugin.execute(context)
            context.active_plugins["normalizer"] = f"{normalizer_plugin.plugin_id}@{normalizer_plugin.version}"

            # -- Freeze Registry & Write Lockfile -----------------------------
            snapshot = registry.freeze()
            intent_dict = context.intent_decision.to_dict() if context.intent_decision else None
            snapshot.write_lockfile(self.output_dir, intent_decision=intent_dict)

            # Determine final target DataFrames for handoff
            final_dfs = context.normalized_tables or context.harvested_tables or context.assembled_tables or context.parsed_tables
            if not final_dfs:
                raise ValueError("Pipeline produced no final canonical DataFrames")

            schema_map = SchemaMap()
            if context.primary_timestamp_col:
                schema_map.canonical_timestamp_col = context.primary_timestamp_col
            if getattr(context, "schema_warnings", None):
                schema_map.warnings = list(context.schema_warnings)

            audits = [
                JoinAudit(
                    group_id=k,
                    fact_file=k,
                    dimension_files=[],
                    join_keys=context.join_keys,
                    join_type="plugin_pipeline",
                    fact_rows_before=len(v),
                    merged_rows_after=len(v),
                    null_column_percentages={},
                    cartesian_guard_passed=True,
                    warnings=[],
                    redundant_keys_excluded=[],
                )
                for k, v in final_dfs.items()
            ]

            current_state = CompilerState.VALIDATING_OUTPUT
            state_history.append(current_state.value)

            duration = round(time.time() - t0, 3)
            artifacts = export_compiler_handoff(
                output_dir=self.output_dir,
                merged_dfs=final_dfs,
                audits=audits,
                schema_map=schema_map,
                duration_seconds=duration,
                zip_filename=self.zip_path.name,
            )

            # Copy reports to persistent workspace.unified & workspace.reports
            try:
                for src_p in artifacts.per_group_csvs.values():
                    shutil.copy2(src_p, workspace.unified / src_p.name)
                for src_p in artifacts.per_group_parquets.values():
                    shutil.copy2(src_p, workspace.unified / src_p.name)
                if artifacts.combined_csv:
                    shutil.copy2(artifacts.combined_csv, workspace.unified / artifacts.combined_csv.name)
                if artifacts.combined_parquet:
                    shutil.copy2(artifacts.combined_parquet, workspace.unified / artifacts.combined_parquet.name)
                if artifacts.dataset_card_json and artifacts.dataset_card_json.exists():
                    shutil.copy2(artifacts.dataset_card_json, workspace.reports / artifacts.dataset_card_json.name)
                if artifacts.lineage_json and artifacts.lineage_json.exists():
                    shutil.copy2(artifacts.lineage_json, workspace.reports / artifacts.lineage_json.name)
                if artifacts.quality_report_json and artifacts.quality_report_json.exists():
                    shutil.copy2(artifacts.quality_report_json, workspace.reports / artifacts.quality_report_json.name)
            except Exception as w_err:
                logger.debug(f"[UnifiedCompiler] Workspace report copy warning: {w_err}")

            # -- Per-Partition Job Batch (individual model per fault mode) ----
            self._maybe_export_partition_batch(context, final_dfs)

            # -- Write the intelligence report artifact -----------------------
            if self._intelligence is not None:
                self._intelligence.write_report(self.output_dir)

            current_state = CompilerState.COMPILED
            state_history.append(current_state.value)

            return CompileResult(
                input_zip=str(self.zip_path),
                output_dir=str(self.output_dir),
                merged_files=[str(p) for p in artifacts.per_group_csvs.values()],
                combined_file=str(artifacts.combined_csv) if artifacts.combined_csv else None,
                artifacts=artifacts,
                audits=audits,
                schema_map=schema_map,
                duration_seconds=duration,
                success=True,
                state=CompilerState.COMPILED,
                state_history=state_history,
            )

        except Exception as e:
            duration = round(time.time() - t0, 3)
            logger.error(f"[UnifiedCompiler] Ingestion failure: {e}")
            current_state = CompilerState.FAILED
            state_history.append(current_state.value)
            
            workspace.quarantine_file(self.zip_path, reason=str(e))
            
            if self.scout is not None:
                import traceback
                tb_str = traceback.format_exc()
                try:
                    logger.warning("[UnifiedCompiler] Ingestion failed - triggering scout.self_heal()")
                    self.scout.self_heal(error_traceback=tb_str, zip_path=self.zip_path)
                except Exception as ex:
                    logger.warning(f"[UnifiedCompiler] scout.self_heal() call failed: {ex}")

            return CompileResult(
                input_zip=str(self.zip_path),
                output_dir=str(self.output_dir),
                merged_files=[],
                combined_file=None,
                artifacts=HandoffArtifacts({}, None, Path(""), Path(""), Path(""), Path("")),
                audits=[],
                schema_map=SchemaMap(),
                duration_seconds=duration,
                success=False,
                error=str(e),
                state=CompilerState.FAILED,
                state_history=state_history,
            )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # -- Intelligence Layer -------------------------------------------------

    def _run_intelligence_pre_parse(self, temp_dir: Path, registry) -> None:
        """
        Intelligence Stages 1-3: archive exploration, true format detection,
        LLM parser advice over the live plugin catalog.

        Never raises - intelligence failures must not abort compilation.
        """
        if not self.enable_intelligence:
            return

        try:
            from .intelligence import IntelligenceOrchestrator

            self._intelligence = IntelligenceOrchestrator()
            self._intelligence.run_pre_parse(
                target_path=self.zip_path,
                temp_dir=temp_dir,
                registry=registry,
            )
        except Exception as e:
            logger.warning(f"[Intelligence] Pre-parse stages failed: {e}")
            self._intelligence = None

    def _run_intelligence_post_parse(self, context: PipelineContext) -> None:
        """
        Intelligence Stages 4-7: column statistics, schema roles, semantic
        meaning, and problem framing with dynamically generated HITL options.

        Never raises - intelligence failures must not abort compilation.
        """
        if self._intelligence is None or not context.parsed_tables:
            return

        try:
            source_paths = {
                item.relative_path: str(item.filepath) for item in context.inventory
            }
            self._intelligence.run_post_parse(
                parsed_tables=context.parsed_tables,
                source_paths=source_paths,
            )
        except Exception as e:
            logger.warning(f"[Intelligence] Post-parse stages failed: {e}")

    # -- Output Shaping -----------------------------------------------------

    def _maybe_export_partition_batch(
        self, context: PipelineContext, final_dfs: Dict[str, pd.DataFrame]
    ) -> None:
        """
        Emit a per-partition job batch when the user chose individual models.

        Never raises - a batch export failure leaves the single-merged artifacts
        already written by export_compiler_handoff intact.
        """
        strategy = context.strategy
        if strategy is None or getattr(strategy, "output_mode", "") != "per_partition_batch":
            return

        partitions = getattr(strategy, "partitions", None) or []
        if not partitions:
            logger.warning(
                "[UnifiedCompiler] per_partition_batch requested but no partitions "
                "were identified - keeping single merged output only"
            )
            return

        try:
            from .batch_writer import export_partition_batch

            result = export_partition_batch(
                output_dir=self.output_dir,
                tables=final_dfs,
                partitions=partitions,
                partition_dimension=strategy.partition_by,
                target_column=strategy.target_column_hint,
                dataset_name=self.zip_path.name,
            )
            if result is not None:
                logger.info(
                    f"[UnifiedCompiler] Per-partition batch: {len(result.job_specs)} job(s)"
                )
        except Exception as e:
            logger.warning(f"[UnifiedCompiler] Partition batch export failed: {e}")

    # -- HITL Intent Layer --------------------------------------------------

    def _run_intent_layer(self, context: PipelineContext) -> None:
        """
        Execute the HITL Intent Layer.

        Preferred path: use the LLM-generated DatasetCard, question, and options
        from the intelligence layer. Falls back to the legacy heuristic
        CardGenerator/IntentClassifier when intelligence is unavailable.
        """
        from .intent import (
            CardGenerator,
            IntentClassifier,
            IntentResolver,
            IntentDecision,
        )

        inventory_dicts = [
            {
                "filepath": str(item.filepath),
                "relative_path": item.relative_path,
                "format_ext": item.format_ext,
                "size_bytes": item.size_bytes,
            }
            for item in context.inventory
        ]
        card = CardGenerator().generate(
            dataset_name=self.zip_path.stem,
            inventory=inventory_dicts,
        )
        options = IntentClassifier().classify(card)
        context.data_card = card

        if not options:
            logger.debug("[IntentLayer] No options generated - skipping intent layer")
            return

        chosen_id = self.strategy_override or options[0].option_id
        strategy = IntentResolver().resolve(chosen_id, card)
        context.strategy = strategy

        if strategy and strategy.assembler_policy_override:
            context.policy_overrides["assembler"] = strategy.assembler_policy_override

        context.intent_decision = IntentDecision(
            dataset_name=card.dataset_name,
            data_card=card.to_dict(),
            options_presented=[
                {"option_id": o.option_id, "label": o.label, "description": o.description}
                for o in options
            ],
            user_choice=chosen_id,
            resolved_strategy=strategy.to_dict() if strategy else {},
        )

        logger.info(
            f"[IntentLayer] Intent '{chosen_id}' -> output_mode={strategy.output_mode}, "
            f"merge_rule={strategy.merge_rule}, llm_generated={strategy.generated_by_llm}"
        )
