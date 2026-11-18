"""Offline tests for arm job specs, preconditions, resume and receipts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from portal.modules.orchestration import queue as queue_module
from portal.modules.orchestration.jobs import JobRunner
from portal.modules.orchestration.service import StubNoticeSink


def test_build_queue_digest_counts_jobs_rows_and_long_waits() -> None:
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    items = [
        {
            "task_id": "done-job",
            "state": "done",
            "receipt_status": "PASS",
            "updated_at": (now - timedelta(hours=3)).isoformat(),
        },
        {
            "task_id": "blocked-job",
            "state": "blocked",
            "receipt_status": "STOPPED",
            "last_error": "job receipt status is STOPPED: step exited 1",
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "task_id": "old-blocked-job",
            "state": "blocked",
            "receipt_status": "BLOCKED",
            "last_error": "job receipt status is BLOCKED: step exited 4",
            "updated_at": (now - timedelta(days=3)).isoformat(),
        },
        {
            "task_id": "waiting-job",
            "state": "queued",
            "receipt_status": "WAITING",
            "last_error": "dispatch lane lock lane.lock is active (pid 9)",
            "waiting_since": (now - timedelta(hours=2)).isoformat(),
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        },
        {
            "task_id": "fresh-job",
            "state": "queued",
            "receipt_status": None,
            "last_error": None,
            "waiting_since": None,
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        },
    ]
    receipts = {
        "done-job": {
            "steps": [{"stdout_tail": "hello\nCAMPAIGN c1: complete (all rows judged) rows 3/5\n"}]
        },
        "blocked-job": {"steps": [{"stdout_tail": "CAMPAIGN c2: stopped (judge) rows 2/5"}]},
    }

    text = queue_module.build_queue_digest(items, receipts, now=now)

    assert "Queue digest 2026-10-30 12:00Z." in text
    assert "Jobs: 1 done, 2 blocked, 2 queued, 0 running." in text
    assert "old-blocked-job" not in text  # older than a day: counted, not listed
    assert "(+1 older blocked; `portal arm queue-status` lists them)" in text
    assert "blocked blocked-job: job receipt status is STOPPED: step exited 1" in text
    assert "Rows measured: 5/10." in text
    assert "done-job: CAMPAIGN c1: complete (all rows judged) rows 3/5" in text
    assert "blocked-job: CAMPAIGN c2: stopped (judge) rows 2/5" in text
    assert "waiting-job (2.0h) — dispatch lane lock lane.lock is active (pid 9)" in text
    assert "fresh-job" not in text


def _watcher(tmp_path: Path, *, trip_after: float | None = None) -> Path:
    path = tmp_path / "memory_watch.py"
    body = "#!/usr/bin/env python3\nimport sys, time\n"
    if trip_after is None:
        body += "time.sleep(0.05)\nsys.exit(0)\n"
    else:
        body += (
            f"time.sleep({trip_after})\n"
            "log = sys.argv[sys.argv.index('--log') + 1]\n"
            "open(log, 'a').write('MEMORY SAFETY TRIP: fixture\\n')\n"
            "sys.exit(2)\n"
        )
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


class _Gate:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason

    def external_reason(self) -> str | None:
        return self.reason


def _stub_page_cache_drop() -> dict[str, Any]:
    return {"ok": True, "swap_used_gib_before": 1.0, "swap_used_gib_after": 1.0, "error": None}


def _runner(
    tmp_path: Path,
    repo: Path,
    *,
    gate: Any = None,
    watcher: Path | None = None,
    stack: str = "down",
    memory: float | None = 64.0,
    disk: float | None = 64.0,
    notices: StubNoticeSink | None = None,
    page_cache_drop: Any = None,
) -> JobRunner:
    """Kept for tests/unit/test_arm_escalation.py, which is outside this lane."""
    return JobRunner(
        tmp_path / "tasks",
        repo_root=repo,
        gate=gate or _Gate(),
        notices=notices or StubNoticeSink(),
        dispatch_lock_dir=tmp_path / "dispatch-locks",
        memory_watch_script=watcher or _watcher(tmp_path),
        stack_probe=lambda: stack,
        memory_probe=lambda: memory,
        disk_probe=lambda _path: disk,
        page_cache_drop=page_cache_drop or _stub_page_cache_drop,
        poll_seconds=0.02,
    )
