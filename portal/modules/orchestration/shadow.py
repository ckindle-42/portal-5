"""Detached, non-gating comparison runner for orchestration read/check bites."""

from __future__ import annotations

import json
import os
import shutil
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from .contracts import _parse_bite
from .service import _review_worker
from .tools import TASK_DATA_DIRECTORY
from .worker import Engine, PipelineError, check_output, run_bite

DEFAULT_SLOT_WAIT_SECONDS = 300.0
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 5.0


class ShadowEngine(Engine):
    def chat(
        self,
        body: dict[str, Any],
        timeout: float,
        on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        return super().chat(
            {**body, "temperature": 1.0, "top_p": 0.95, "top_k": -1, "min_p": 0.0},
            timeout,
            on_event,
        )


class SlotUnavailableError(Exception):
    """The wait cap ended before load-plan reported an idle seat."""


class SlotWaitingEngine:
    """Retry a busy load-plan or HTTP 429 until the seat is idle."""

    def __init__(
        self,
        engine: Engine,
        *,
        wait_seconds: float,
        call_timeout: float,
        arm_timeout: Callable[[float], None] | None = None,
        disarm_timeout: Callable[[], None] | None = None,
    ) -> None:
        self._engine = engine
        self._wait_seconds = wait_seconds
        self._call_timeout = call_timeout
        self._arm_timeout = arm_timeout
        self._disarm_timeout = disarm_timeout
        self.waited = False
        self.waited_seconds = 0.0
        self.granted = False
        self._started = time.monotonic()
        self._attempt = 0
        self._model_deadline: float | None = None

    def load_plan(self, timeout: float) -> dict[str, Any]:
        while True:
            try:
                plan = self._engine.load_plan(timeout)
            except PipelineError as exc:
                hint = _admission_hint(exc)
                if hint is None:
                    raise
                self._pause(hint)
                continue
            if _slot_is_free(plan):
                self._grant()
                return plan
            self._pause(0.0)

    def chat(
        self,
        body: dict[str, Any],
        timeout: float,
        on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        while True:
            # Re-check immediately before the request so a stale grant cannot overlap the main bite.
            self.granted = False
            self.load_plan(timeout)
            try:
                return self._engine.chat(body, timeout, on_event)
            except PipelineError as exc:
                if exc.status_code != 429:
                    raise
                self._pause(exc.retry_after or 0.0)

    def _grant(self) -> None:
        now = time.monotonic()
        if self._model_deadline is None:
            self._model_deadline = now + self._call_timeout
        remaining = self._model_deadline - now
        if remaining <= 0:
            raise TimeoutError("shadow timeout")
        self.granted = True
        if self._arm_timeout is not None:
            self._arm_timeout(remaining)

    def _pause(self, retry_after: float) -> None:
        delay = _slot_delay(self._attempt, retry_after)
        self._attempt += 1
        remaining = self._wait_seconds - (time.monotonic() - self._started)
        if delay > remaining:
            raise SlotUnavailableError
        if self._disarm_timeout is not None:
            self._disarm_timeout()
        self.granted = False
        self.waited = True
        before = time.monotonic()
        time.sleep(delay)
        self.waited_seconds += time.monotonic() - before

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


def append_comparison(task_dir: Path, record: dict[str, Any]) -> None:
    path = task_dir / "shadow_comparisons.jsonl"
    line = (json.dumps(record, sort_keys=True, default=str) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def summarize_comparisons(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "shadow_comparisons.jsonl"
    return _summarize(_records(path.read_text(encoding="utf-8")))


def summarize_all(task_root: Path) -> dict[str, Any]:
    if not task_root.is_dir():
        raise FileNotFoundError(f"no tasks directory: {task_root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(task_root.glob("*/shadow_comparisons.jsonl")):
        rows.extend(_records(path.read_text(encoding="utf-8")))
    return _summarize(rows)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compared = [
        row
        for row in rows
        if isinstance(row.get("shadow_verdict"), bool)
        and isinstance(row.get("incumbent_verdict"), bool)
        and not row.get("error")
    ]
    total = len(compared)
    return {
        "total": len(rows),
        "compared": total,
        "agree_percent": 100 * sum(row["agree"] is True for row in compared) / total
        if total
        else None,
        "false_accept": sum(
            row["shadow_verdict"] and not row["incumbent_verdict"] for row in compared
        ),
        "false_fail": sum(
            not row["shadow_verdict"] and row["incumbent_verdict"] for row in compared
        ),
        "waited": sum(row.get("waited") is True for row in rows),
        "errors": sum(bool(row.get("error")) for row in rows),
    }


def _records(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def run_shadow(
    job: dict[str, Any],
    engine: Engine,
    deep_engine: Engine,
    *,
    arm_timeout: Callable[[float], None] | None = None,
    disarm_timeout: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Run one isolated copy and return its verdict without touching the live bite."""
    base = job["comparison"]
    shadow_dir = (
        Path(job["task_dir"]) / "bites" / base["bite_id"] / "attempts" / base["attempt"] / "shadow"
    )
    wait_seconds = _slot_wait_seconds(job)
    call_timeout = float(job["timeout_seconds"])
    bite = _parse_bite(job["bite"])
    # Extra minutes keep the admission wait from being stored as a wall-clock failure.
    bite = replace(
        bite,
        budget=replace(
            bite.budget,
            minutes=min(bite.budget.minutes, call_timeout / 60) + wait_seconds / 60,
        ),
    )
    gate = SlotWaitingEngine(
        engine,
        wait_seconds=wait_seconds,
        call_timeout=call_timeout,
        arm_timeout=arm_timeout,
        disarm_timeout=disarm_timeout,
    )
    started = time.monotonic()
    record: dict[str, Any] = {
        **base,
        "shadow_verdict": None,
        "shadow_latency_seconds": None,
        "agree": None,
        "error": None,
        "waited": False,
        "wait_seconds": 0.0,
    }
    try:
        _run_shadow_bite(job, bite, gate, deep_engine, shadow_dir, record)
    except SlotUnavailableError:
        record["error"] = None
        record["waited"] = True
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["waited"] = bool(record["waited"] or gate.waited)
    record["wait_seconds"] = gate.waited_seconds
    record["shadow_latency_seconds"] = time.monotonic() - started
    return record


def _run_shadow_bite(
    job: dict[str, Any],
    bite: Any,
    gate: SlotWaitingEngine,
    deep_engine: Engine,
    shadow_dir: Path,
    record: dict[str, Any],
) -> None:
    base = job["comparison"]
    shutil.copytree(job["source_data"], shadow_dir / TASK_DATA_DIRECTORY)
    worker = run_bite(
        shadow_dir,
        bite,
        cast(Engine, gate),
        input_paths={key: Path(value) for key, value in job["inputs"].items()},
        attempt_dir=shadow_dir,
        require_idle=True,
    )
    failures = list(worker.red_flags)
    if worker.failure:
        failures.append(worker.failure)
    if worker.finished:
        checks = check_output(bite, worker.output, shadow_dir / TASK_DATA_DIRECTORY)
        failures.extend(checks.failures)
        if not failures:
            review = _review_worker(bite, worker.output, job["config"], deep_engine)
            if review is not None and not review["passed"]:
                failures.append(review["failure"])
    if not worker.finished and not failures:
        failures.append(worker.loop_outcome)
    record["shadow_verdict"] = not failures
    record["agree"] = record["shadow_verdict"] == base["incumbent_verdict"]
    if worker.failure:
        record["error"] = worker.failure


def _slot_wait_seconds(job: dict[str, Any]) -> float:
    config = job.get("config")
    raw = config.get("shadow_slot_wait_seconds") if isinstance(config, dict) else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        return DEFAULT_SLOT_WAIT_SECONDS
    return float(raw)


def _slot_is_free(plan: Any) -> bool:
    if not isinstance(plan, dict):
        return False
    if plan.get("skipped") is True:
        return True
    return plan.get("busy") is False and plan.get("fits") is True


def _admission_hint(exc: PipelineError) -> float | None:
    """Seconds hinted by a slot delay, or None when the failure is genuine."""
    if exc.status_code == 429:
        return exc.retry_after or 0.0
    if str(exc).startswith("load guard refused the seat:"):
        return 0.0
    return None


def _slot_delay(attempt: int, retry_after: float) -> float:
    if retry_after > 0:
        return retry_after
    return float(min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2**attempt)))


def _timeout(_signum: int, _frame: Any) -> None:
    raise TimeoutError("shadow timeout")


def run_job(job_path: Path) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    key = os.environ.get("PIPELINE_API_KEY", "")
    model = job["comparison"]["shadow_model"]
    engine = ShadowEngine(
        job["incumbent_model"],
        "shadow",
        job["pipeline_url"],
        key,
        load_plan_engine="ollama",
        load_plan_model=model,
        model_override=model,
    )
    deep_engine = Engine(job["deep_model"], "shadow-review", job["pipeline_url"], key)

    def arm_timeout(remaining: float) -> None:
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, max(0.01, remaining))

    def disarm_timeout() -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)

    try:
        record = run_shadow(
            job,
            engine,
            deep_engine,
            arm_timeout=arm_timeout,
            disarm_timeout=disarm_timeout,
        )
    except Exception as exc:
        record = {
            **job["comparison"],
            "shadow_verdict": None,
            "shadow_latency_seconds": None,
            "agree": None,
            "error": f"{type(exc).__name__}: {exc}",
            "waited": False,
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    append_comparison(Path(job["task_dir"]), record)


def main(manifest_path: Path) -> None:
    for job_path in json.loads(manifest_path.read_text(encoding="utf-8")):
        path = Path(job_path)
        try:
            run_job(path)
        except Exception as exc:
            _log_job_error(path, f"{type(exc).__name__}: {exc}")


def _log_job_error(job_path: Path, error: str) -> None:
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        append_comparison(
            Path(job["task_dir"]),
            {**job["comparison"], "shadow_verdict": None, "agree": None, "error": error},
        )
    except (OSError, KeyError, TypeError, ValueError):
        print(f"shadow job {job_path} failed: {error}", file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
