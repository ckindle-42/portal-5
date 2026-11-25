"""CLI entry: `python3 -m tests.qat` (or `uv run python -m tests.qat`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from .config import Settings
from .models import Status
from .runner import RunnerOptions, run_selected

ALL_STAGES = {0, 1, 2, 3, 4, 5}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m tests.qat",
        description="Portal 5 live end-to-end QAT and human-grade UAT suite",
    )
    parser.add_argument(
        "--stage", help="stages to run: 0,1,2,3,4,5/uat (comma list) or 'all'", default="all"
    )
    parser.add_argument("--phase", action="append", help="restrict to phase (repeatable)")
    parser.add_argument("--scenario", action="append", help="restrict to scenario id (repeatable)")
    parser.add_argument("--browser-only", action="store_true", help="only browser scenarios")
    parser.add_argument("--api-only", action="store_true", help="skip browser scenarios")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan from live discovery; zero network/GPU",
    )
    parser.add_argument(
        "--append", metavar="RUN_DIR", help="add missing scenarios to an existing run"
    )
    parser.add_argument(
        "--rerun-failed", metavar="RUN_DIR", help="resubmit FAIL/BLOCKED rows of an existing run"
    )
    parser.add_argument(
        "--cleanup-chats",
        action="store_true",
        help="delete test chats instead of archiving to QAT/{date}",
    )
    parser.add_argument(
        "--output-dir", metavar="PATH", help="run directory (default results/qat/…)"
    )
    parser.add_argument(
        "--emit-worksheets", action="store_true", help="write Stage 4 operator rubric worksheets"
    )
    parser.add_argument(
        "--ingest-worksheets",
        action="store_true",
        help="validate + freeze filled Stage 4 worksheets before running",
    )
    return parser


def parse_stages(raw: str) -> set[int]:
    if raw.strip().lower() == "all":
        return ALL_STAGES
    stages = {
        5 if part.strip().lower() == "uat" else int(part) for part in raw.split(",") if part.strip()
    }
    unknown = stages - ALL_STAGES
    if unknown:
        raise SystemExit(f"unknown stage(s): {sorted(unknown)}; valid: 0,1,2,3,4,5,uat")
    return stages


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load()
    if (
        not args.dry_run
        and not args.emit_worksheets
        and not args.ingest_worksheets
        and not settings.owui_pass
    ):
        print(
            "OPENWEBUI_ADMIN_PASSWORD not set (named key in .env) — live stages need it",
            file=sys.stderr,
        )
    opts = RunnerOptions(
        stages=parse_stages(args.stage),
        phases=set(args.phase or ()),
        only_scenarios=set(args.scenario or ()),
        browser_only=args.browser_only,
        api_only=args.api_only,
        dry_run=args.dry_run,
        cleanup_chats=args.cleanup_chats,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        resume_dir=Path(args.append or args.rerun_failed)
        if (args.append or args.rerun_failed)
        else None,
        resume_mode="append" if args.append else ("rerun-failed" if args.rerun_failed else ""),
        emit_worksheets=args.emit_worksheets,
        ingest_worksheets=args.ingest_worksheets,
    )
    state = run_selected(settings, opts)
    if opts.dry_run:
        return 0
    paths = report.write_reports(
        state.run_dir,
        state.discovery,
        state.scenarios,
        state.results,
        shots_dir=state.run_dir / "screenshots",
        provenance=state.provenance,
    )
    counts = {status.value: 0 for status in Status}
    for row in state.results:
        counts[row.status.value] += 1
    print(f"results   : {paths['jsonl']}")
    print(f"report    : {paths['markdown']}")
    print(f"sign-off  : {paths['html']}")
    print(
        f"verdict   : {counts['PASS']}P / {counts['WARN']}W / {counts['FAIL']}F"
        f" / {counts['SKIP']}S / {counts['BLOCKED']}B"
    )
    return 1 if counts["FAIL"] or counts["BLOCKED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
