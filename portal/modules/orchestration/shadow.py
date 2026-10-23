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
from typing import Any

from .contracts import _parse_bite
from .service import _review_worker
from .tools import TASK_DATA_DIRECTORY
from .worker import Engine, check_output, run_bite


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
        "errors": len(rows) - total,
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


def run_shadow(job: dict[str, Any], engine: Engine, deep_engine: Engine) -> dict[str, Any]:
    """Run one isolated copy and return its verdict without touching the live bite."""
    base = job["comparison"]
    shadow_dir = (
        Path(job["task_dir"]) / "bites" / base["bite_id"] / "attempts" / base["attempt"] / "shadow"
    )
    bite = _parse_bite(job["bite"])
    bite = replace(
        bite,
        budget=replace(bite.budget, minutes=min(bite.budget.minutes, job["timeout_seconds"] / 60)),
    )
    started = time.monotonic()
    record = {
        **base,
        "shadow_verdict": None,
        "shadow_latency_seconds": None,
        "agree": None,
        "error": None,
    }
    try:
        shutil.copytree(job["source_data"], shadow_dir / TASK_DATA_DIRECTORY)
        worker = run_bite(
            shadow_dir,
            bite,
            engine,
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
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["shadow_latency_seconds"] = time.monotonic() - started
    return record


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
    signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, float(job["timeout_seconds"]))
    try:
        record = run_shadow(job, engine, deep_engine)
    except Exception as exc:
        record = {
            **job["comparison"],
            "shadow_verdict": None,
            "shadow_latency_seconds": None,
            "agree": None,
            "error": f"{type(exc).__name__}: {exc}",
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
