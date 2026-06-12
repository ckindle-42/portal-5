"""Portal 5 UAT — run notifications (per-test + summary), git sha.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B). _git_sha lives here because the notify functions are its only
callers (A8).
"""

from __future__ import annotations

import os

from tests.uat.freshness import _REPO_ROOT


def _git_sha() -> str:
    """Get current git SHA."""
    try:
        import subprocess as _subprocess

        return _subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        return "unknown"


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
            workspace="uat-test",
            metadata=metadata or {},
        )
        await dispatcher.dispatch(event)
    except Exception as e:
        print(f"  WARNING: Notification failed: {e}")


async def _notify_test_start(sections: list[str] | None = None, test_count: int = 0) -> None:
    """Send a notification that UAT testing has started."""
    sections_str = ", ".join(sections) if sections else "all"
    await _send_notification(
        "test_start",
        f"UAT test suite started — section(s): {sections_str} ({test_count} tests)\n"
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        metadata={"sections": sections or [], "test_count": test_count},
    )


async def _notify_test_end(
    sections: list[str] | None,
    elapsed: int,
    counts: dict[str, int],
    test_count: int,
) -> None:
    """Send a notification that UAT testing has completed."""
    summary_parts = [
        f"PASS={counts.get('PASS', 0)}",
        f"FAIL={counts.get('FAIL', 0)}",
        f"WARN={counts.get('WARN', 0)}",
        f"SKIP={counts.get('SKIP', 0)}",
        f"MANUAL={counts.get('MANUAL', 0)}",
    ]
    sections_str = ", ".join(sections) if sections else "all"
    await _send_notification(
        "test_end",
        f"UAT test suite completed — section(s): {sections_str} in {elapsed}s\n"
        f"Results: {', '.join(summary_parts)}\n"
        f"Git: {_git_sha()}",
        metadata={"elapsed_s": elapsed, "counts": counts},
    )


async def _notify_test_summary(
    counts: dict[str, int], elapsed: int, sections: list[str] | None, test_count: int
) -> None:
    """Send the narrative summary via all enabled notification channels."""
    total = sum(counts.values())
    failed = counts.get("FAIL", 0)
    warned = counts.get("WARN", 0)

    if failed:
        narrative = f"{failed} test{'s' if failed > 1 else ''} failed"
    elif warned:
        narrative = f"All {total} tests passed with {warned} warning{'s' if warned > 1 else ''}"
    else:
        narrative = f"All {total} tests passed"

    sections_str = ", ".join(sections) if sections else "all"
    lines = [
        narrative,
        "",
        f"Portal 5 UAT Driver — section(s): {sections_str}",
        f"Duration: {elapsed}s  |  Tests: {test_count}",
        f"Git: {_git_sha()}  |  Host: {os.uname().nodename}",
        "",
    ]
    for s in ["PASS", "FAIL", "WARN", "SKIP", "BLOCKED", "MANUAL"]:
        if s in counts:
            lines.append(f"  {s}: {counts[s]}")
    lines.append(f"  Total: {total}")

    await _send_notification(
        "test_summary",
        "\n".join(lines),
        metadata={"counts": counts, "elapsed_s": elapsed, "test_count": test_count},
    )
