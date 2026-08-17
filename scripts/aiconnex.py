"""
aiconnex.py - Single Command Entry Point
=========================================
One command runs the full AIConnex pipeline:

    python aiconnex.py --input data.zip --output workspace_data/run_01

What it does:
  1. Asks the user whether to start (can skip with --yes or --batch)
  2. Runs the compiler in interactive TUI mode (user picks their model goal)
  3. On success, hands the compiled CSV straight to the 9-node ML pipeline

Modes:
  --interactive  (default when tty) - halts at TUI for user model selection
  --batch                           - auto-selects default, no prompts
  --yes          -y                 - skip the start confirmation, still show TUI
  --no-intelligence                 - skip LLM analysis, deterministic only
  --dry-run                         - compile only, skip ML pipeline execution
  --target       -t                 - override the auto-detected ML target column
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _header() -> None:
    print()
    _line("=")
    print("  AIConnex  |  Compiler + ML Pipeline Runner")
    _line("=")
    print()


def _ask_start(input_path: Path, output_dir: Path, batch: bool) -> bool:
    """
    Print a summary of what is about to run and ask the user to confirm.
    Returns True if the user wants to proceed, False to abort.
    In --batch mode skips the question and returns True immediately.
    """
    if batch:
        return True

    print("  Input  :", input_path)
    print("  Output :", output_dir)
    print()
    print("This will:")
    print("  Step 1  Compile the archive -> clean CSV(s)")
    print("  Step 2  Run the 9-node ML pipeline on the compiled data")
    print()

    while True:
        try:
            raw = input("Start? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if raw in ("", "y", "yes"):
            print()
            return True
        if raw in ("n", "no"):
            print("Aborted.")
            return False
        print("  Please enter Y or N.")


def _print_compile_result(res, output_dir: Path) -> None:
    print()
    _line()
    print(f"  Compiler finished in {res.duration_seconds}s")
    _line()

    if res.merged_files:
        print("  Group CSVs:")
        for f in res.merged_files:
            print(f"    {f}")

    if res.combined_file:
        print(f"  Combined CSV:\n    {res.combined_file}")

    artifacts = res.artifacts
    if artifacts:
        print("  Artifacts:")
        for attr in ("join_audit_json", "schema_map_json", "compiler_report_json", "dataset_card_json"):
            p = getattr(artifacts, attr, None)
            if p:
                print(f"    {p}")

    lock = output_dir / "compiler_lock.json"
    if lock.exists():
        print(f"    {lock}")
    print()


def _pick_csv_for_pipeline(res, output_dir: Path) -> Path | None:
    """
    Pick the best CSV to hand to the ML pipeline.
    Prefers all_groups_combined.csv when it exists (unified model path).
    Falls back to the first per-group CSV.
    """
    combined = output_dir / "all_groups_combined.csv"
    if combined.exists():
        return combined

    if res.combined_file and Path(res.combined_file).exists():
        return Path(res.combined_file)

    if res.merged_files:
        first = Path(res.merged_files[0])
        if first.exists():
            return first

    # Last resort: scan for any CSV
    for csv_path in output_dir.rglob("*.csv"):
        if csv_path.stat().st_size > 0:
            return csv_path

    return None


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    input_path: Path,
    output_dir: Path,
    interactive: bool,
    batch: bool,
    strategy: str | None,
    no_intelligence: bool,
    target_column: str | None,
    dry_run: bool,
    verbose: bool,
    confirm_batch: bool = False,
) -> int:

    _header()

    # --- Step 0: Ask to start -----------------------------------------------
    if not _ask_start(input_path, output_dir, confirm_batch):
        return 0

    # --- Step 1: Compiler ---------------------------------------------------
    _line("=")
    print("  STEP 1 / 2   Compiling archive")
    _line("=")
    print()

    sys.path.insert(0, str(Path(__file__).parent))

    from services.aiconnex_zip_compiler.compiler import UnifiedCompiler
    from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry

    PluginRegistry.reset_instance()

    compiler = UnifiedCompiler(
        zip_path=input_path,
        output_dir=output_dir,
        interactive=interactive,
        strategy_override=strategy,
        batch=batch,
        enable_intelligence=not no_intelligence,
    )

    res = compiler.compile()

    if not res.success:
        print(f"[FAIL] Compilation failed: {res.error}", file=sys.stderr)
        return 1

    _print_compile_result(res, output_dir)

    if dry_run:
        print("[dry-run] Skipping ML pipeline execution.")
        return 0

    # --- Step 2: Hand off to ML pipeline ------------------------------------
    _line("=")
    print("  STEP 2 / 2   Running ML pipeline")
    _line("=")
    print()

    csv_path = _pick_csv_for_pipeline(res, output_dir)

    if csv_path is None:
        print("[WARN] No compiled CSV found. Cannot run ML pipeline.")
        return 1

    print(f"  Dataset   : {csv_path}")
    print(f"  Target    : {target_column or '(auto-detected)'}")
    print(f"  Output    : {output_dir / 'pipeline_run'}")
    print()

    try:
        # Add aic/ to path so run_pipeline imports work
        aic_dir = Path(__file__).parent / "aic"
        sys.path.insert(0, str(aic_dir))
        from run_pipeline import PipelineRunner

        runner = PipelineRunner(
            dataset_path=str(csv_path),
            target_column=target_column,
            output_dir=str(output_dir / "pipeline_run"),
            verbose=verbose,
        )
        pipeline_result = runner.run()

        print()
        _line("=")
        print("  DONE")
        _line("=")
        if hasattr(pipeline_result, "success") and not pipeline_result.success:
            print(f"[WARN] Pipeline finished with issues: {getattr(pipeline_result, 'error', '')}")
            return 1

        print("  Compiler + ML pipeline completed successfully.")
        print(f"  Output directory: {output_dir}")
        print()
        return 0

    except Exception as exc:
        print(f"[FAIL] ML pipeline error: {exc}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python aiconnex.py",
        description=(
            "AIConnex - Single command that compiles any dataset archive "
            "and runs the full 9-node ML pipeline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python aiconnex.py -i data/raw/NASA_CMAPSS.zip -o workspace_data/cmapss_run
  python aiconnex.py -i data/raw/Dataset-TAS.zip -o workspace_data/tas_run --batch
  python aiconnex.py -i data/raw/Solar.zip -o workspace_data/solar_run --strategy per_partition_batch
  python aiconnex.py -i data/raw/Battery.zip -o workspace_data/battery_run --dry-run
""",
    )

    p.add_argument(
        "--input", "-i", required=True, metavar="PATH",
        help="Path to the input ZIP archive or dataset directory.",
    )
    p.add_argument(
        "--output", "-o", required=False, default=None, metavar="OUTPUT_DIR",
        help="Root output directory. Defaults to data/compiled/<dataset_name> if omitted.",
    )

    # Interaction mode (mutually exclusive)
    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--batch", action="store_true", default=False,
        help="Skip all prompts. Auto-selects defaults for both the start "
             "confirmation and the TUI model selection.",
    )
    mode_group.add_argument(
        "--strategy", metavar="SELECTOR", type=str, default=None,
        help=(
            "Bypass the TUI and use this strategy directly. "
            "Accepts: output_mode (single_merged, per_partition_batch, "
            "keep_separate), a 1-based index (1, 2...), or an exact option_id."
        ),
    )

    p.add_argument(
        "--yes", "-y", action="store_true", default=False,
        help="Skip the start confirmation but still show the interactive TUI.",
    )
    p.add_argument(
        "--target", "-t", metavar="COLUMN", default=None,
        help="Override the auto-detected target column for the ML pipeline.",
    )
    p.add_argument(
        "--no-intelligence", action="store_true", default=False,
        help="Disable the LLM intelligence layer. Faster, offline-safe, "
             "no LLM calls. Uses deterministic heuristics only.",
    )
    p.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Compile only. Skip the ML pipeline execution.",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Print detailed logs from both the compiler and ML pipeline.",
    )

    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else Path("data/compiled") / input_path.stem

    if not input_path.exists():
        print(f"Error: Input not found at {input_path}", file=sys.stderr)
        return 1

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(message)s")

    batch = args.batch
    strategy = args.strategy
    yes = args.yes

    # interactive = show the TUI for model selection
    # True when: neither --batch nor --strategy suppresses it
    interactive = not batch and strategy is None

    # confirm_batch = skip the "Start? [Y/n]" question
    # True when: --batch (skip everything) or --yes (just skip the start question)
    confirm_batch = batch or yes

    return run(
        input_path=input_path,
        output_dir=output_dir,
        interactive=interactive,
        batch=batch,
        strategy=strategy,
        no_intelligence=getattr(args, "no_intelligence", False),
        target_column=args.target,
        dry_run=getattr(args, "dry_run", False),
        verbose=args.verbose,
        confirm_batch=confirm_batch,
    )


if __name__ == "__main__":
    sys.exit(main())
