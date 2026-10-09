"""Command-line adapter for the public security review runtime.

All review behavior remains in ``review.service``; this module only parses arguments,
calls the runtime surface, and renders JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
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


def _run(runtime: ReviewRuntime, args: argparse.Namespace) -> dict[str, Any]:
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
        runtime = build_default_runtime()
        output = _run(runtime, args)
        print(json.dumps(output, sort_keys=True, indent=2, default=str))
        return 1 if "error" in output else 0
    except Exception as exc:  # noqa: BLE001 -- CLI renders adapter/runtime errors as JSON
        print(
            json.dumps({"error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr
        )
        return 1
    finally:
        if runtime is not None:
            runtime.close()
