"""CLI entry — argparse, main async coroutine, sync wrapper."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ._common import RESULTS_DIR, WORKSPACE_REGISTRY
from .ollama_client import run_audit_tools
from .sweep import run_sweep
from .render import render_matrix_table


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--workspace",
        default="auto-compliance",
        choices=tuple(WORKSPACE_REGISTRY.keys()),
        help=(
            "Which workspace's chain to sweep. Default: auto-compliance. "
            "Each workspace has its own fixture + assertion library + "
            "threshold doc registered in WORKSPACE_REGISTRY."
        ),
    )
    p.add_argument("--persona", help="filter persona slugs by substring")
    p.add_argument("--model", help="filter model ids by substring")
    p.add_argument(
        "--backend",
        choices=("ollama",),
        help="restrict to one backend type",
    )
    p.add_argument(
        "--include-big-models",
        action="store_true",
        help="include models flagged big_model: true (default: skip)",
    )
    p.add_argument(
        "--require",
        default="",
        help=(
            "comma-separated list of model substrings that MUST appear in "
            "the resolved chain (after filters). Driver exits non-zero "
            "before running if any required model is absent. Example: "
            "--require granite4.1:8b,granite4.1:30b"
        ),
    )
    p.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="cap scenarios per persona (0 = no cap, default)",
    )
    p.add_argument("--dry-run", action="store_true", help="print plan and exit")
    p.add_argument(
        "--audit-tools",
        action="store_true",
        help="Per-model tool-call verification mode. Skips persona/scenario "
        "fixtures; sends AUDIT_PROMPT with AUDIT_TOOL_DEFINITION attached "
        "and classifies the response. See TASK_TOOL_SUPPORT_AUDIT_V1 §A14.",
    )
    p.add_argument(
        "--output",
        help="JSON output path (default: results dir UTC-stamped)",
    )
    p.add_argument(
        "--baseline-compare",
        default="",
        help=(
            "Path to an existing matrix-result JSON to diff this run against. "
            "After the sweep completes, the driver runs the diff equivalent "
            "of `tests/persona_matrix_diff.py baseline.json this_run.json` "
            "and prints regressions to stderr. Exits non-zero if any "
            "regression exceeds --regression-threshold."
        ),
    )
    p.add_argument(
        "--regression-threshold",
        type=float,
        default=10.0,
        help=(
            "Per-(persona, model) PASS-rate drop in percentage points that "
            "counts as a regression. Default: 10.0. Used only with "
            "--baseline-compare."
        ),
    )
    return p.parse_args(argv)


async def amain(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.audit_tools:
        await run_audit_tools(args)
        return 0
    report = await run_sweep(args)

    if args.dry_run:
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"persona_matrix_{args.workspace}_{ts}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out_path}")
    print("\n--- MATRIX (PASS/WARN/FAIL per cell) ---")
    print(render_matrix_table(report))

    # Inline diff-vs-baseline (TASK 007 §2.4).
    regressions: list[str] = []
    if args.baseline_compare:
        try:
            from tests.persona_matrix_diff import compute_regressions  # noqa: E402

            regressions = compute_regressions(
                Path(args.baseline_compare),
                report,
                threshold_pp=args.regression_threshold,
            )
        except Exception as e:
            print(f"baseline-compare failed: {e}", file=sys.stderr)

    if regressions:
        print(
            f"\n--- REGRESSIONS vs baseline (threshold {args.regression_threshold:.1f}pp) ---",
            file=sys.stderr,
        )
        for line in regressions:
            print(f"  {line}", file=sys.stderr)

    any_fail = any(c["summary"].get("FAIL", 0) > 0 for c in report["cells"])
    if regressions:
        return 2 if any_fail else 1
    return 1 if any_fail else 0





def main() -> int:
    """Synchronous entry point."""
    return asyncio.run(amain())