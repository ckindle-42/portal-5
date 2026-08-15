"""`hunt` CLI shell -- thin transport over bully/orchestrator.py (I-3).

No hunt logic lives here (MASTER "no hunt logic in the CLI"). This module
parses argv and delegates to the application contracts in
``bully.orchestrator``; it owns no state of its own (I-3 "thin CLI/config").
"""

from __future__ import annotations

import argparse
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hunt", description="Defensive Bully hunt loop")
    sub = parser.add_subparsers(dest="mode", required=True)

    run_p = sub.add_parser("run", help="authorize and run a new hunt")
    run_p.add_argument("--neighborhood", default="auto")
    run_p.add_argument("--budget-class", default="default")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--actor", required=True, help='authorized actor, e.g. "operator:alice"')
    run_p.add_argument("--json", action="store_true")

    resume_p = sub.add_parser("resume", help="resume a blocked/interrupted hunt")
    resume_p.add_argument("hunt_id")
    resume_p.add_argument("--actor", required=True)
    resume_p.add_argument("--json", action="store_true")

    status_p = sub.add_parser("status", help="report a hunt's current status")
    status_p.add_argument("hunt_id")
    status_p.add_argument("--json", action="store_true")

    cancel_p = sub.add_parser("cancel", help="cancel a hunt (preserves evidence)")
    cancel_p.add_argument("hunt_id")
    cancel_p.add_argument("--actor", required=True)
    cancel_p.add_argument("--reason", default="")
    cancel_p.add_argument("--json", action="store_true")

    doctor_p = sub.add_parser("doctor", help="SUB integrity check")
    doctor_p.add_argument("--json", action="store_true")

    queue_p = sub.add_parser("queue", help="operator promotion-queue resolution")
    queue_p.add_argument("--confirm", metavar="ITEM_ID")
    queue_p.add_argument("--actor", required=True)
    queue_p.add_argument("--rationale", default="")
    queue_p.add_argument("--json", action="store_true")

    return parser


def hunt_main(argv: list[str]) -> int:
    """Entry point registered by `__main__.py`'s dispatch pattern."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    from ..bully import orchestrator

    try:
        if args.mode == "run":
            report = orchestrator.run_hunt(
                neighborhood=args.neighborhood,
                budget_class=args.budget_class,
                dry_run=args.dry_run,
                actor=args.actor,
            )
        elif args.mode == "resume":
            report = orchestrator.resume_hunt(args.hunt_id, actor=args.actor)
        elif args.mode == "status":
            report = orchestrator.hunt_status(args.hunt_id)
        elif args.mode == "cancel":
            report = orchestrator.cancel_hunt(args.hunt_id, actor=args.actor, reason=args.reason)
        elif args.mode == "doctor":
            report = orchestrator.hunt_doctor()
        elif args.mode == "queue":
            report = orchestrator.queue_resolve(
                item_id=args.confirm, actor=args.actor, rationale=args.rationale
            )
        else:  # pragma: no cover -- argparse enforces `required=True`
            parser.error(f"unknown mode {args.mode!r}")
            return 2
    except orchestrator.HonestBlockedError as exc:
        payload = {"status": "blocked", "reason": str(exc)}
        print(json.dumps(payload) if args.json else f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except orchestrator.OperatorRequiredError as exc:
        payload = {"status": "denied", "reason": str(exc)}
        print(json.dumps(payload) if args.json else f"DENIED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, default=str))
    else:
        print(report)
    return 0
