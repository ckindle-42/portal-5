"""CLI entry point: argument parsing, image-freshness check, run orchestration.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py except the shared
httpx client teardown now goes through measure.close_bench_client().
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import (
    MAX_TOKENS,
    OLLAMA_URL,
    PIPELINE_URL,
    PROJECT_ROOT,
    RESULTS_DIR,
    RESULTS_FILE,
)
from .discovery import (
    _config_ollama_models_unique,
    _config_workspaces,
    _discover_personas,
)
from .lifecycle import _check_backend, _cleanup_all_backends, _get_hardware_info
from .measure import close_bench_client
from .notify import _send_bench_notification
from .prompts import (
    GROUP_PROMPT_MAP,
    PERSONA_CATEGORY_PROMPT_MAP,
    PROMPTS,
    WORKSPACE_PROMPT_MAP,
)
from .report import (
    _print_availability_report,
    _print_direct_table,
    _print_persona_table,
    _print_pipeline_table,
)
from .results_io import _init_output
from .runners import bench_direct, bench_personas, bench_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 TPS Benchmark")
    parser.add_argument(
        "--mode",
        choices=["direct", "pipeline", "personas", "all"],
        default="all",
        help="Test direct backends, pipeline workspaces, persona routing, or all (default: all)",
    )
    parser.add_argument("--runs", type=int, default=5, help="Runs per model/workspace (default: 5)")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="MODEL",
        help="Filter: substring match on model name (direct only, repeatable — OR logic)",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        dest="workspaces",
        metavar="WORKSPACE",
        help="Filter: exact workspace ID (pipeline only, repeatable — OR logic)",
    )
    parser.add_argument("--persona", help="Filter: substring match on persona slug/name")
    parser.add_argument("--prompt", help="Override all prompts with this single prompt string")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Resume from the most recent results file, skipping successful entries "
            "and re-testing only failed ones. Pair with --mode to target a specific tier "
            "(e.g. --mode pipeline --retry-failed retests only failed workspaces)."
        ),
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=10.0,
        help="Seconds to wait after memory reclaim before loading next model (default: 10)",
    )
    parser.add_argument(
        "--order",
        choices=["size", "config", "largest"],
        default="size",
        help="Model test order: 'size' = smallest first (default), 'largest' = biggest first, 'config' = backends.yaml order",
    )
    parser.add_argument(
        "--spec-decoding-tag",
        type=str,
        default="",
        help="Label this run as 'spec_decoding=on/off' for later comparison (M4 Track 1)",
    )
    parser.add_argument(
        "--kv-quant-tag",
        default="",
        help="Label appended to output JSON tagging the KV-quant configuration "
        "active during the run (e.g. 'off', 'lm-kv4.5', 'vlm-kv4.5'). "
        "Used for before/after comparison across TASK_KV_PROMOTE_V1 runs.",
    )
    args = parser.parse_args()

    # --retry-failed: find the most recent results file and use it as --output so
    # successful entries are skipped and failures are re-run automatically.
    if args.retry_failed and args.output == RESULTS_FILE:
        candidates = sorted(
            RESULTS_DIR.glob("bench_tps_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            args.output = str(candidates[0])
            print(f"--retry-failed: resuming from {candidates[0].name}")
        else:
            print("--retry-failed: no previous results file found in results/, starting fresh")

    original_prompts = dict(PROMPTS) if args.prompt else None
    if args.prompt:
        for key in PROMPTS:
            PROMPTS[key] = args.prompt

    try:
        _run_main(args)
    finally:
        if original_prompts is not None:
            PROMPTS.clear()
            PROMPTS.update(original_prompts)
        close_bench_client()


def _check_image_freshness() -> None:
    """Warn if any portal Docker image predates the latest relevant git commit."""

    def _ts(git_paths=None, image=None):
        try:
            if git_paths:
                r = subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%ct", "--", *git_paths],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                ts = r.stdout.strip()
                from datetime import datetime

                return datetime.fromtimestamp(int(ts), tz=UTC) if ts else None
            if image:
                r = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Created}}", image],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                raw = r.stdout.strip()
                if raw and raw != "[]":
                    from datetime import datetime

                    return datetime.fromisoformat(raw.rstrip("Z") + "+00:00")
        except Exception:
            return None

    checks = [
        (
            "portal-pipeline",
            "portal-5-portal-pipeline",
            ["portal_pipeline/", "config/backends.yaml", "Dockerfile.pipeline", "pyproject.toml"],
        ),
        (
            "mcp-services",
            "portal-5-mcp-documents",
            ["portal_mcp/", "Dockerfile.mcp", "pyproject.toml"],
        ),
    ]
    stale = []
    for label, image, paths in checks:
        built = _ts(image=image)
        committed = _ts(git_paths=paths)
        if built and committed:
            lag = (committed - built).total_seconds()
            if lag > 30:
                stale.append(f"{label} ({int(lag // 60)}m behind HEAD)")
    if stale:
        print("  WARNING: stale Docker images — run './launch.sh rebuild' before trusting results:")
        for s in stale:
            print(f"    {s}")


def _run_main(args) -> None:
    print("=" * 70)
    print("Portal 5 — Comprehensive TPS Benchmark")
    print("=" * 70)
    _check_image_freshness()

    hw = _get_hardware_info()
    print(f"Hardware: {json.dumps(hw)}")
    if args.prompt:
        print(f"Prompt override: {args.prompt[:60]}...")
    else:
        print(f"Prompts: {len(PROMPTS)} categories ({', '.join(PROMPTS.keys())})")
    print(f"Max tokens: {MAX_TOKENS}  |  Runs per model: {args.runs}")
    print(f"Mode: {args.mode}  |  Order: {args.order}  |  Cooldown: {args.cooldown:.0f}s")

    # Config summary
    ollama_cfg = _config_ollama_models_unique()
    workspaces_cfg = _config_workspaces()
    personas_cfg = _discover_personas()

    print("\nConfigured (from backends.yaml + persona YAMLs):")
    print(f"  Ollama models: {len(ollama_cfg)}")
    print(f"  Workspaces:    {len(workspaces_cfg)}")
    print(f"  Personas:      {len(personas_cfg)}")
    total_configured = len(ollama_cfg)
    if args.mode in ("pipeline", "all"):
        total_configured += len(workspaces_cfg)
    if args.mode in ("personas", "all"):
        total_configured += len(personas_cfg)
    print(f"  Total to test: ~{total_configured} (mode={args.mode})")

    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")
    pipeline_available = _check_backend(PIPELINE_URL, "/v1/models")

    print("\nBackends:")
    print(f"  Ollama     ({OLLAMA_URL}):    {'available' if ollama_available else 'not running'}")
    print(f"  Pipeline   ({PIPELINE_URL}):  {'available' if pipeline_available else 'not running'}")

    if not any([ollama_available, pipeline_available]):
        print("\nNo backends running. Start at least one and retry.")
        return

    do_direct = args.mode in ("direct", "all")
    do_pipeline = args.mode in ("pipeline", "all")
    do_personas = args.mode in ("personas", "all")

    _ws_filter = f" ws={','.join(args.workspaces)}" if getattr(args, "workspaces", None) else ""
    _model_filter = f" model={','.join(args.models)}" if getattr(args, "models", None) else ""
    _send_bench_notification(
        f"mode={args.mode}{_ws_filter}{_model_filter}  runs={args.runs}\n"
        f"HW: {hw.get('cpu', '?')}  {hw.get('unified_memory_gb', '?')}GB\n"
        f"Ollama={'✓' if ollama_available else '✗'}  Pipeline={'✓' if pipeline_available else '✗'}",
        title="Portal 5 Bench — Started",
    )

    t0 = time.time()

    # Initialize output file (or load existing for resume)
    output = _init_output(args.output, args, hw, ollama_cfg, workspaces_cfg, personas_cfg)
    all_results = list(output.get("results", []))
    if all_results:
        print(f"\n  Resuming: {len(all_results)} results already saved")

    if do_direct:
        print("\n── Ollama Direct Tests ──")
        all_results.extend(
            bench_direct(
                ollama_available,
                args.models,
                args.runs,
                args.dry_run,
                cooldown=args.cooldown,
                order=args.order,
                output_path=args.output,
            )
        )

    if do_pipeline:
        print("\n── Pipeline Workspace Tests ──")
        all_results.extend(
            bench_pipeline(
                pipeline_available,
                args.workspaces,
                args.runs,
                args.dry_run,
                output_path=args.output,
            )
        )

    if do_personas:
        print("\n── Persona Routing Tests ──")
        all_results.extend(
            bench_personas(
                pipeline_available, args.persona, args.runs, args.dry_run, output_path=args.output
            )
        )

    total_time = time.time() - t0

    if not args.dry_run:
        _print_availability_report(ollama_available, pipeline_available, all_results)
        _print_direct_table(all_results)
        _print_pipeline_table(all_results)
        _print_persona_table(all_results)

    # Finalize output with wall time and metadata
    output["timestamp"] = datetime.now(UTC).isoformat()
    output["total_wall_time_s"] = round(total_time, 1)
    output["backends"] = {
        "ollama": {"url": OLLAMA_URL, "available": ollama_available},
        "pipeline": {"url": PIPELINE_URL, "available": pipeline_available},
    }
    output["prompts"] = {
        "override": args.prompt if args.prompt else None,
        "library": {k: v[:80] + "..." if len(v) > 80 else v for k, v in PROMPTS.items()},
        "workspace_map": WORKSPACE_PROMPT_MAP,
        "group_map": GROUP_PROMPT_MAP,
        "persona_category_map": PERSONA_CATEGORY_PROMPT_MAP,
    }
    # Merge: keep all results from the file (including resumed ones)
    try:
        with open(args.output) as f:
            file_data = json.load(f)
        output["results"] = file_data.get("results", all_results)
    except Exception:
        output["results"] = all_results

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    tested = sum(1 for r in output["results"] if r.get("runs_success", 0) > 0)
    available_ct = sum(1 for r in output["results"] if r.get("available", True))
    failed_ct = available_ct - tested
    print(
        f"\nTotal: {tested}/{available_ct} passed ({len(output['results'])} total) in {total_time:.0f}s"
    )
    _top = sorted(
        [r for r in output["results"] if r.get("avg_tps", 0) > 0],
        key=lambda r: r.get("avg_tps", 0),
        reverse=True,
    )[:5]
    _top_lines = "\n".join(
        f"  {r.get('model', r.get('workspace', '?'))[:30]:30s} {r['avg_tps']:.1f} t/s" for r in _top
    )
    _send_bench_notification(
        f"{tested}/{available_ct} passed  {failed_ct} failed  {total_time:.0f}s\n"
        + (_top_lines + "\n" if _top_lines else "")
        + f"→ {Path(args.output).name}",
        title="Portal 5 Bench — Done",
    )
    # Final cleanup: unload all Ollama models to prevent OOM after testing
    if not args.dry_run and ollama_available:
        _cleanup_all_backends()

    print(f"Results: {args.output}")
