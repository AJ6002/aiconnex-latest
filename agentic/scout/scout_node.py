"""
aiconnex_agent/scout/scout_node.py
=====================================
Real Scout Agent Node (Phase 5b) - replaces stub_scout_agent_node's hardcoded
fake dataset info with a real UnifiedCompiler call against state.upload_path.

Fixes applied (see docs/superpowers/plans/2026-07-29-phased-arch-audit.md
and the Phase 5b gap-list discussion):

  Gap 1 - reads the REAL file path from state.upload_path (set by the caller
          before graph invocation), instead of a fixed "suyash2.zip" string.
  Gap 2 - delegates to compiler_adapter.py to translate the real CompileResult
          into ScoutEnrichedContract / DatasetIntelligenceContract fields.
  Gap 3 - on compile failure: retries the compile ONCE (transient errors -
          e.g. a locked temp dir - are worth one retry), then if it still
          fails, flags the error via a real LangGraph clarification instead
          of silently proceeding with an empty/fake DIC.
  Gap 4 - PreCompilerContract.compiler_request flags are now actually read
          and passed into UnifiedCompiler's real constructor parameters
          (previously decorative, never consumed).
  Gap 7 - peeks at the real IntentOptions before compiling. If the compiler's
          own IntentClassifier finds 2+ genuinely different strategies, Scout
          raises a real LangGraph interrupt with the actual option labels
          instead of letting UnifiedCompiler silently auto-pick options[0].
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from langgraph.types import interrupt

from agentic.state import MasterAgentState
from agentic.scout.strategy_peek import peek_dataset_card_and_options
from agentic.scout import compiler_adapter as adapter

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_ROOT = Path("scratch") / "scout_output"


def _resolve_output_dir(state: MasterAgentState, upload_path: Path) -> Path:
    """Bug #2 fix: use state.session_id (stable across all nodes in a conversation)
    instead of state.cuc.conversation['session_id'] (which was never populated).
    Also resolves Bug #5: two users uploading a file named data.zip no longer
    collide on the same output folder since session_id is unique per state."""
    return _DEFAULT_OUTPUT_ROOT / state.session_id


from agentic.schemas import InterruptPayload, InterruptOption


def _ask_user_to_choose_strategy(options) -> str:
    """Gap 7: a real LangGraph interrupt using typed InterruptPayload."""
    payload = InterruptPayload(
        interrupt_type="strategy_choice",
        questions=[
            f"Your dataset supports {len(options)} different processing strategies. "
            "Which would you like?"
        ],
        options=[
            InterruptOption(
                option_id=getattr(o, "option_id", f"opt_{i}"),
                label=getattr(o, "label", f"Strategy {i+1}"),
                description=getattr(o, "description", "")
            )
            for i, o in enumerate(options)
        ],
        reason="Scout detected multiple valid compilation strategies",
    )
    return interrupt(payload.model_dump() if hasattr(payload, "model_dump") else payload.dict())


def _flag_compile_failure(error_message: str) -> str:
    """Gap 3: after retry still fails, ask the user via a typed LangGraph interrupt."""
    payload = InterruptPayload(
        interrupt_type="compile_failure",
        questions=[
            f"I couldn't process this file: {error_message}. "
            "Could you check the file and re-upload it?"
        ],
        options=[],
        reason="Scout compile failure after retry",
    )
    return interrupt(payload.model_dump() if hasattr(payload, "model_dump") else payload.dict())



def real_scout_agent_node(state: MasterAgentState) -> Dict[str, Any]:
    """Real Scout Agent Node: real file -> real UnifiedCompiler -> real contracts."""
    logger.info("[ScoutAgent] Executing real scout node")

    from services.aiconnex_zip_compiler.compiler import UnifiedCompiler

    if not state.upload_path:
        # Gap 1 safety net: no real file was ever provided - this is a genuine
        # ambiguity, not something to paper over with fake data.
        # Capture the user's answer; store it in planning_hints so the next
        # turn can surface it. Route back to "scout" (not "evaluator") so the
        # graph waits for a real file before advancing the plan.
        user_answer = _flag_compile_failure("no dataset file was provided")
        cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else state.cuc.dict()
        cuc_dict["planning_hints"] = {"reupload_response": user_answer}
        return {
            "cuc": cuc_dict,
            "interrupt_reason": "missing_upload_path",
            "active_agent": "scout",
        }

    upload_path = Path(state.upload_path)
    output_dir = _resolve_output_dir(state, upload_path)

    # -- Gap 7: peek at real strategy options before committing to a compile --
    strategy_override = None
    try:
        _, options = peek_dataset_card_and_options(upload_path)
        if len(options) >= 2:
            chosen_id = _ask_user_to_choose_strategy(options)
            strategy_override = chosen_id
    except Exception as e:
        logger.warning(f"[ScoutAgent] Strategy peek failed, proceeding to compiler's own default: {e}")

    # -- Gap 4: translate CompilerRequest flags into real UnifiedCompiler params --
    compiler_request = state.pre_compiler.compiler_request
    enable_intelligence = compiler_request.infer_targets or compiler_request.infer_problem_candidates

    # -- Gap 3: compile with one retry on transient failure, then flag --
    result = None
    last_error = None
    for attempt in range(2):
        compiler = UnifiedCompiler(
            zip_path=upload_path,
            output_dir=output_dir,
            batch=True,
            strategy_override=strategy_override,
            enable_intelligence=enable_intelligence,
        )
        result = compiler.compile()
        if result.success:
            break
        last_error = result.error
        logger.warning(f"[ScoutAgent] Compile attempt {attempt + 1} failed: {last_error}")

    if result is None or not result.success:
        # Bug #1 fix: capture the interrupt() return value (the user's response
        # to the "please re-upload" prompt) and store it in planning_hints.
        # Route back to "scout" so the graph does not advance to the evaluator
        # with an empty/fake DIC — it will re-enter this node on resume.
        user_answer = _flag_compile_failure(last_error or "unknown compilation error")
        cuc_dict = state.cuc.model_dump() if hasattr(state.cuc, "model_dump") else state.cuc.dict()
        cuc_dict["planning_hints"] = {"reupload_response": user_answer}
        return {
            "cuc": cuc_dict,
            "interrupt_reason": "compile_failure",
            "active_agent": "scout",
            "compile_error": last_error or "Compilation failed",
        }

    # -- Gap 2: adapt the real CompileResult into the agent's contracts --
    scout_dict = state.scout_enriched.model_dump() if hasattr(state.scout_enriched, "model_dump") else state.scout_enriched.dict()
    scout_dict["upload"] = adapter.build_upload_metadata(upload_path).model_dump()
    scout_dict["archive_discovery"] = adapter.build_archive_discovery(result).model_dump()
    scout_dict["file_inventory"] = [item.model_dump() for item in adapter.build_file_inventory(result)]
    scout_dict["parser_selection"] = adapter.build_parser_selection(result).model_dump()

    dic_dict = state.dic.model_dump() if hasattr(state.dic, "model_dump") else state.dic.dict()
    dic_dict["dataset_identity"] = adapter.build_dataset_identity(result).model_dump()
    dic_dict["compiled_dataset"] = adapter.build_compiled_dataset_summary(result).model_dump()
    dic_dict["statistics"] = adapter.build_dataset_statistics(result).model_dump()
    dic_dict["quality_report"] = adapter.build_quality_report(result).model_dump()

    # -- Issue 6: DIC post-compile completeness validation --
    from agentic.scout.dic_validator import DICValidator
    validator = DICValidator()
    is_valid, validation_warnings = validator.validate(dic_dict)
    existing_warnings = dic_dict.get("compiler_warnings", [])
    dic_dict["compiler_warnings"] = list(set(existing_warnings + validation_warnings))

    # -- Recipe Catalog: analyze compiled CSV to populate intelligence fields --
    combined_csv = result.combined_file
    if not combined_csv and result.merged_files:
        combined_csv = result.merged_files[0]

    if combined_csv:
        try:
            from agentic.scout.recipe_catalog_builder import build_recipe_catalog
            catalog = build_recipe_catalog(str(combined_csv))
            dic_dict["dataset_card"] = catalog["dataset_card"]
            dic_dict["schema_map"] = catalog["schema_map"]
            dic_dict["target_candidates"] = catalog["target_candidates"]
            dic_dict["problem_candidates"] = catalog["problem_candidates"]
            dic_dict["feature_catalog"] = catalog["feature_catalog"]
            dic_dict["recipes"] = catalog["recipes"]
            dic_dict["branching_hints"] = catalog["branching_hints"]
            logger.info(
                f"[ScoutAgent] Recipe catalog built: {len(catalog['recipes'])} recipes, "
                f"{len(catalog['target_candidates'])} targets"
            )
        except Exception as exc:
            logger.warning(f"[ScoutAgent] Recipe catalog build failed (non-fatal): {exc}")





    # --- Telemetry: emit dataset compilation profile ---
    try:
        from agentic.telemetry.emitters import ScoutEmitter
        ScoutEmitter().emit(
            session_id=state.session_id,
            dic_dict=dic_dict,
            scout_dict=scout_dict,
        )
    except Exception as exc:
        logger.debug(f"[ScoutAgent] Telemetry emit skipped: {exc}")

    return {
        "scout_enriched": scout_dict,
        "dic": dic_dict,
        "active_agent": "evaluator",
    }

