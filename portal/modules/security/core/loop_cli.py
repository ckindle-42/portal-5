"""``python3 -m portal.modules.security.core loop ...`` (TASK_SEC_LOOP_NOTIFY_V1
Phase 3) — run a playbook engagement and resume a checkpointed one.

The resume_cmd carried in every ENGAGEMENT_ESCALATED/ENGAGEMENT_STUCK
notification is exactly `loop resume <engagement_id>`, so an operator can act
straight from the alert.
"""

from __future__ import annotations

import json


def loop_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="portal security loop",
        description="Autonomous playbook engagement loop — run, resume",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_run = sub.add_parser("run", help="Run a playbook to a stop condition")
    p_run.add_argument("playbook_path", help="Path to a playbook YAML")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--lab-exec", action="store_true")
    p_run.add_argument("--workspace", default=None)
    p_run.add_argument("--auto-continue-safe", action="store_true")
    p_run.add_argument(
        "--notify-on-success",
        action="store_true",
        help="Also fire ENGAGEMENT_COMPLETE when the goal is met (default: off)",
    )
    p_run.add_argument("--json", action="store_true")

    p_resume = sub.add_parser("resume", help="Resume a checkpointed engagement")
    p_resume.add_argument("engagement_id")
    p_resume.add_argument("--dry-run", action="store_true")
    p_resume.add_argument("--lab-exec", action="store_true")
    p_resume.add_argument("--notify-on-success", action="store_true")
    p_resume.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    from .loop import resume_engagement, run_engagement

    if args.subcommand == "run":
        report = run_engagement(
            args.playbook_path,
            dry_run=args.dry_run,
            lab_exec=args.lab_exec,
            workspace=args.workspace,
            auto_continue_safe=args.auto_continue_safe,
            notify_on_success=args.notify_on_success,
        )
    else:
        report = resume_engagement(
            args.engagement_id,
            lab_exec=args.lab_exec,
            dry_run=args.dry_run,
            notify_on_success=args.notify_on_success,
        )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"status: {report.get('status')}")
        print(f"stop_reason: {report.get('stop_reason')}")
        if report.get("engagement_id"):
            print(f"engagement_id: {report['engagement_id']}")
        if report.get("escalations"):
            print(f"escalations: {report['escalations']}")

    return 0 if report.get("status") not in ("rejected", "error") else 1
