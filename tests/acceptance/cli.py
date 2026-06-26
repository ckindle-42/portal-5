"""CLI entry point for Portal 5 acceptance tests."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.resolve()


async def _send_notification(event_type: str, message: str, metadata: dict | None = None) -> None:
    """Fire a notification via the Portal 5 notification dispatcher.

    Gracefully handles missing dependencies or disabled notifications — never
    crashes the test suite.
    """
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        from portal_pipeline.notifications.channels.email import EmailChannel
        from portal_pipeline.notifications.channels.pushover import PushoverChannel
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.channels.telegram import TelegramChannel
        from portal_pipeline.notifications.channels.webhook import WebhookChannel
        from portal_pipeline.notifications.dispatcher import NotificationDispatcher
        from portal_pipeline.notifications.events import AlertEvent, EventType

        dispatcher = NotificationDispatcher()
        for ch in [SlackChannel, TelegramChannel, EmailChannel, PushoverChannel, WebhookChannel]:
            dispatcher.add_channel(ch())

        event = AlertEvent(
            type=EventType(event_type.lower()),
            message=message,
            workspace="acceptance-test",
            metadata=metadata or {},
        )
        await dispatcher.dispatch(event)
    except Exception as e:
        print(f"  ⚠️  Notification failed: {e}")


async def _notify_test_start(section: str, total_sections: int) -> None:
    """Send a notification that acceptance testing has started."""
    from .results import _git_sha

    await _send_notification(
        "test_start",
        f"Acceptance test suite started — section {section} ({total_sections} total)\n"
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        metadata={"section": section, "total_sections": total_sections},
    )


async def _notify_test_end(
    section: str, elapsed: int, counts: dict[str, int], total_sections: int
) -> None:
    """Send a notification that acceptance testing has completed."""
    from .results import _git_sha

    summary_parts = [
        f"PASS={counts.get('PASS', 0)}",
        f"FAIL={counts.get('FAIL', 0)}",
        f"WARN={counts.get('WARN', 0)}",
        f"INFO={counts.get('INFO', 0)}",
    ]
    await _send_notification(
        "test_end",
        f"Acceptance test suite completed — section {section} in {elapsed}s\n"
        f"Results: {', '.join(summary_parts)}\n"
        f"Git: {_git_sha()}",
        metadata={"elapsed_s": elapsed, "counts": counts},
    )


async def _notify_test_summary(
    counts: dict[str, int], elapsed: int, section: str, total_sections: int
) -> None:
    """Send the narrative summary + formatted table via all enabled notification channels."""
    from .results import _ICON, _git_sha, _log

    total = sum(counts.values())
    failed = counts.get("FAIL", 0)
    blocked = counts.get("BLOCKED", 0)
    warned = counts.get("WARN", 0)

    if failed:
        narrative = f"{failed} test{'s' if failed > 1 else ''} failed"
    elif blocked:
        narrative = f"{blocked} test{'s' if blocked > 1 else ''} blocked (require code changes)"
    elif warned:
        narrative = f"All {total} tests passed with {warned} warning{'s' if warned > 1 else ''}"
    else:
        narrative = f"All {total} tests passed"

    lines = [
        narrative,
        "",
        f"Portal 5 Acceptance Test v6 — {section}",
        f"Duration: {elapsed}s  |  Sections: {total_sections}",
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        "",
    ]
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if s in counts:
            icon = _ICON.get(s, "  ")
            lines.append(f"  {icon} {s}: {counts[s]}")
    lines.append(f"  Total: {total}")

    if failed or blocked:
        lines.append("")
        label = "Failed" if failed else "Blocked"
        lines.append(f"{label} checks:")
        for r in _log:
            if r.status in ("FAIL", "BLOCKED"):
                lines.append(f"  [{r.status}] {r.section}/{r.name}: {r.detail[:120]}")

    await _send_notification(
        "test_summary",
        "\n".join(lines),
        metadata={"counts": counts, "elapsed_s": elapsed, "section": section},
    )


async def main() -> int:
    """Run acceptance tests — CLI entry point."""
    from . import _common
    from . import results as _results_mod
    from .results import (
        _ICON,
        _git_sha,
        _load_prior_results,
        _log,
        _print_routing_summary,
        _write_results,
    )
    from .runner import _parse_sections, run_sections

    parser = argparse.ArgumentParser(description="Portal 5 Acceptance Tests v6")
    parser.add_argument("--section", "-s", default="ALL", help="Section(s) to run")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild before tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--skip-passing", action="store_true", help="Skip sections that passed in prior run"
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge targeted re-run results into prior ACCEPTANCE_RESULTS.md baseline",
    )
    args = parser.parse_args()

    _common._FORCE_REBUILD = args.rebuild
    _results_mod._verbose = args.verbose

    sections = _parse_sections(args.section)

    if args.append:
        _load_prior_results(sections_to_skip=set(sections))

    print("=" * 70)
    print("Portal 5 Acceptance Tests v6")
    print(f"Git: {_git_sha()}")
    print(f"Sections: {', '.join(sections)}")
    print("=" * 70)
    _common._check_image_freshness()

    Path(_results_mod._PROGRESS_LOG).write_text(
        f"[{time.strftime('%H:%M:%S')}] Starting acceptance tests\n"
    )

    await _notify_test_start(args.section, len(sections))

    sections_run, elapsed = await run_sections(sections, verbose=args.verbose)

    _write_results(elapsed, sections_run)

    counts: dict[str, int] = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for status in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if status in counts:
            print(f"  {_ICON.get(status, '')} {status}: {counts[status]}")
    print(f"  Total: {sum(counts.values())}")
    print(f"  Runtime: {elapsed}s ({elapsed // 60}m {elapsed % 60}s)")
    print("=" * 70)

    _print_routing_summary()

    await _notify_test_end(args.section, elapsed, counts, len(sections))
    await _notify_test_summary(counts, elapsed, args.section, len(sections))

    if counts.get("FAIL", 0) > 0 or counts.get("BLOCKED", 0) > 0:
        return 1
    return 0
