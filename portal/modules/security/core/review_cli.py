"""Command-line adapter for the public security review runtime.

All review behavior remains in ``review.service``; this module only parses arguments,
calls the runtime surface, and renders JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .review.contracts import Verdict, to_plain
from .review.service import ReviewRequest, ReviewRuntime, build_default_runtime
from .review.window import SourceSpec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m portal.modules.security.core review")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="start a review and wait for its durable result")
    run.add_argument("--source", action="append", required=True, metavar="INDEX:SOURCETYPE")
    run.add_argument("--start", type=float, required=True, help="inclusive epoch time")
    run.add_argument("--end", type=float, required=True, help="exclusive epoch time")
    run.add_argument("--environment", default=None)

    for command in ("status", "result"):
        sub = commands.add_parser(command)
        sub.add_argument("run_id")

    verdict = commands.add_parser("verdict")
    verdict.add_argument("concern_id")
    verdict.add_argument("verdict", choices=[item.value for item in Verdict])
    verdict.add_argument("--actor", required=True)
    verdict.add_argument("--note", default="")

    queue = commands.add_parser("queue")
    queue.add_argument("--limit", type=int, default=None)

    explain = commands.add_parser("explain")
    explain.add_argument("concern_id")

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--fix", action="store_true")

    build = commands.add_parser(
        "build-calibration-slice",
        help="build a benign calibration slice from the live portal5_lab index and write it to disk",
    )
    build.add_argument("--start", type=float, required=True, help="inclusive epoch time")
    build.add_argument("--end", type=float, required=True, help="exclusive epoch time")
    build.add_argument("--rule", required=True, help="operator-stated rule for this benign window")
    build.add_argument("--sources", nargs="+", default=None, metavar="INDEX:SOURCETYPE")
    build.add_argument(
        "--target-units",
        type=int,
        default=600,
        help="minimum calibration-half units; 600 gives p_step=1/601 and 120 steps at alpha=0.2",
    )
    build.add_argument("--output-dir", default=None)

    return parser


def _source_spec(value: str) -> SourceSpec:
    index, separator, sourcetype = value.partition(":")
    if not separator or not index or not sourcetype:
        raise ValueError(f"source must be INDEX:SOURCETYPE, got {value!r}")
    return SourceSpec(index=index, sourcetype=sourcetype)


def _plain_dict(value: Any) -> dict[str, Any]:
    plain = to_plain(value)
    if not isinstance(plain, dict):
        raise TypeError("review response did not serialize to an object")
    return plain


def _run(runtime: ReviewRuntime | None, args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "build-calibration-slice":
        from .review.build_calibration_slice import build

        return build(
            start=args.start,
            end=args.end,
            rule=args.rule,
            sources=[_source_spec(value) for value in args.sources] if args.sources else None,
            target_units=args.target_units,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    if runtime is None:
        raise RuntimeError("review runtime was not initialized")
    if args.command == "run":
        request = ReviewRequest(
            sources=[_source_spec(value) for value in args.source],
            start=args.start,
            end=args.end,
            environment_id=args.environment or runtime.environment_id,
            config=runtime.config,
        )
        run_id = runtime.start(request)
        runtime.worker.join(run_id)
        record = runtime.status(run_id)
        return {
            "run_id": run_id,
            "status": record.status.value if record is not None else "UNKNOWN",
        }
    if args.command == "status":
        record = runtime.status(args.run_id)
        return {"error": f"unknown run {args.run_id!r}"} if record is None else to_plain(record)
    if args.command == "result":
        record = runtime.status(args.run_id)
        if record is None:
            return {"error": f"unknown run {args.run_id!r}"}
        return (
            record.result
            if record.result is not None
            else {"run_id": args.run_id, "status": record.status.value, "progress": record.progress}
        )
    if args.command == "verdict":
        return _plain_dict(
            runtime.verdict(
                args.concern_id,
                Verdict(args.verdict),
                actor=args.actor,
                note=args.note,
            )
        )
    if args.command == "queue":
        items = runtime.queue() if args.limit is None else runtime.queue(limit=args.limit)
        return {"count": len(items), "concerns": to_plain(items)}
    if args.command == "explain":
        return runtime.explain(args.concern_id)
    if args.command == "doctor":
        return runtime.doctor(fix=args.fix)
    raise ValueError(f"unsupported review command {args.command!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    runtime = None
    try:
        if args.command != "build-calibration-slice":
            runtime = build_default_runtime()
        output = _run(runtime, args)
        print(json.dumps(output, sort_keys=True, indent=2, default=str))
        return 1 if "error" in output else 0
    except Exception as exc:  # noqa: BLE001 -- CLI renders adapter/runtime errors as JSON
        message = str(exc)
        if args.command == "build-calibration-slice":
            from .review.build_calibration_slice import _redact_credentials

            message = _redact_credentials(message)
        print(
            json.dumps({"error": f"{type(exc).__name__}: {message}"}, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    finally:
        if runtime is not None:
            runtime.close()
