"""Durable run lifecycle: complete / fail / cancel / interrupted-on-restart."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from portal.modules.security.core.review.runs import (
    RunContext,
    RunStatus,
    RunStore,
    RunWorker,
)


def _wait(worker: RunWorker, run_id: str) -> None:
    worker.join(run_id, timeout=10)


def test_complete_run_persists_request_progress_and_result() -> None:
    store = RunStore()

    def runner(request: Mapping[str, Any], ctx: RunContext) -> Mapping[str, Any]:
        ctx.report("score", 1, 2)
        return {"echo": request["x"], "concerns": 3}

    worker = RunWorker(store, runner)
    run_id = worker.start({"x": 41})
    _wait(worker, run_id)
    record = store.get(run_id)
    assert record is not None and record.status == RunStatus.COMPLETE
    assert record.result == {"echo": 41, "concerns": 3}
    assert record.progress == {"stage": "score", "done": 1, "total": 2}


def test_failed_run_is_recorded_not_lost() -> None:
    store = RunStore()

    def runner(_r: Mapping[str, Any], _c: RunContext) -> Mapping[str, Any]:
        raise ValueError("boom")

    worker = RunWorker(store, runner)
    run_id = worker.start({})
    _wait(worker, run_id)
    record = store.get(run_id)
    assert record is not None and record.status == RunStatus.FAILED
    assert record.error == "ValueError: boom" and record.result is None


def test_running_run_cancels_at_its_next_checkpoint() -> None:
    store = RunStore()
    started = threading.Event()
    release = threading.Event()

    def runner(_r: Mapping[str, Any], ctx: RunContext) -> Mapping[str, Any]:
        started.set()
        release.wait(timeout=10)
        ctx.check_cancel()
        return {"finished": True}

    worker = RunWorker(store, runner)
    run_id = worker.start({})
    assert started.wait(timeout=10)
    assert store.request_cancel(run_id) is True
    release.set()
    _wait(worker, run_id)
    record = store.get(run_id)
    assert record is not None and record.status == RunStatus.CANCELLED


def test_queued_run_cancels_immediately_and_terminal_runs_refuse() -> None:
    store = RunStore()
    run_id = store.create({})
    assert store.request_cancel(run_id) is True
    assert store.get(run_id).status == RunStatus.CANCELLED  # type: ignore[union-attr]
    assert store.request_cancel(run_id) is False
    assert store.request_cancel("run-missing") is False


def test_a_restart_marks_unfinished_runs_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    first = RunStore(path)
    queued = first.create({"a": 1})
    running = first.create({"b": 2})
    first.mark_running(running)
    done = first.create({"c": 3})
    first.complete(done, {"ok": True})
    first.close()

    second = RunStore(path)
    assert second.mark_interrupted() == 2
    assert second.get(queued).status == RunStatus.INTERRUPTED  # type: ignore[union-attr]
    assert second.get(running).status == RunStatus.INTERRUPTED  # type: ignore[union-attr]
    assert second.get(done).status == RunStatus.COMPLETE  # type: ignore[union-attr]
    assert {r.run_id for r in second.list(status=RunStatus.INTERRUPTED)} == {queued, running}
