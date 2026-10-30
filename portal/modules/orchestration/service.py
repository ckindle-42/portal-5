"""Offline-first orchestration arm for hand-written bite plans."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import warnings
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx
import yaml

from .calibration import calibration_status
from .contracts import Bite, TaskPlan
from .ledger import ArmLedger
from .planner import plan_goal, validate_execution_plan
from .review import is_high_risk, review_output
from .tools import READ_TOOLS, TASK_BYTES_LIMIT, TASK_DATA_DIRECTORY, TASK_FILE_LIMIT
from .worker import Engine, QueueYieldError, check_output, run_bite


class NoticeSink(Protocol):
    """Receives an exhausted bite notification."""

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None: ...

    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None: ...

    def job_finished(self, job_id: str, status: str, detail: dict[str, Any]) -> None: ...


class StubNoticeSink:
    """Test and offline notice sink; it never sends a message."""

    def __init__(self) -> None:
        self.notices: list[dict[str, Any]] = []
        self.job_notices: list[dict[str, Any]] = []
        self.escalations: list[dict[str, Any]] = []

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        self.notices.append({"task_id": task_id, "bite_id": bite_id, "failure": failure})

    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        return None

    def job_finished(self, job_id: str, status: str, detail: dict[str, Any]) -> None:
        self.job_notices.append({"job_id": job_id, "status": status, "detail": detail})

    def escalation(self, job_id: str, event: str, detail: dict[str, Any]) -> None:
        self.escalations.append({"job_id": job_id, "event": event, "detail": detail})


class ArmService:
    """Submit or resume one task under explicit build and model identities."""

    def __init__(
        self,
        task_root: Path,
        engines: dict[str, Engine],
        *,
        build_sha: str | None = None,
        residency_config: Path | None = None,
        notices: NoticeSink | None = None,
        bite_gate: Callable[[Bite], bool] | None = None,
    ) -> None:
        self.task_root = task_root
        self.engines = engines
        self.build_sha = build_sha or _head_sha()
        self.config_path = residency_config or _default_config_path()
        self.arm_config = load_arm_config(self.config_path)
        for seat, tag in seated_model_tags(self.arm_config).items():
            if engines[seat].model_tag != tag:
                raise ValueError(f"{seat} seat must use {tag}")
        self.residency_mode = load_residency_mode(self.config_path)
        self.notices = notices or StubNoticeSink()
        self.bite_gate = bite_gate
        self.queue_yield_reason: str | None = None
        self._shadow_jobs: list[Path] = []

    def submit(
        self, raw_plan: dict[str, Any], source_dir: Path, *, unattended: bool = True
    ) -> Path:
        plan = validate_execution_plan(raw_plan, self.arm_config, source_dir)
        _require_calibration(self.arm_config, unattended, {bite.discipline for bite in plan.bites})
        task_dir = self.task_root / plan.task_id
        if task_dir.exists():
            raise FileExistsError(f"task already exists: {task_dir}")
        task_dir.mkdir(parents=True)
        try:
            input_map = self._input_map(plan, source_dir, task_dir)
        except Exception:
            shutil.rmtree(task_dir, ignore_errors=True)
            raise
        (task_dir / "inputs.json").write_text(
            json.dumps(input_map, indent=2) + "\n", encoding="utf-8"
        )
        identities = self._identities()
        ledger = ArmLedger(task_dir)
        try:
            ledger.initialize(
                plan,
                build_sha=self.build_sha,
                model_digest=_combined_digest(identities),
                engines=identities,
                residency_mode=self.residency_mode,
            )
            self._run(plan, task_dir, ledger, input_map)
        finally:
            ledger.close()
        return task_dir

    def submit_goal(
        self,
        *,
        task_id: str,
        goal: str,
        discipline: str,
        source_dir: Path,
        unattended: bool = True,
    ) -> Path:
        """Plan a goal on Deep, validate it, then run its bites."""
        _require_calibration(self.arm_config, unattended, {discipline})
        raw = plan_goal(
            self.engines["deep"],
            task_id=task_id,
            goal=goal,
            discipline=discipline,
            arm_config=self.arm_config,
            source_dir=source_dir,
        )
        return self.submit(raw, source_dir, unattended=unattended)

    def resume(self, task_id: str, *, override: bool = False, unattended: bool = True) -> Path:
        task_dir = self.task_root / task_id
        if not task_dir.is_dir():
            raise FileNotFoundError(f"no task directory: {task_dir}")
        raw_plan = json.loads((task_dir / "plan.json").read_text(encoding="utf-8"))
        plan = validate_execution_plan(raw_plan, self.arm_config)
        _require_calibration(self.arm_config, unattended, {bite.discipline for bite in plan.bites})
        if plan.task_id != task_id:
            raise ValueError("task directory and plan task_id differ")
        input_map = json.loads((task_dir / "inputs.json").read_text(encoding="utf-8"))
        identities = self._identities()
        ledger = ArmLedger(task_dir)
        try:
            if ledger.task()["status"] == "PAUSED_FOR_REPLAN":
                raise ValueError("calibration pause requires a replacement plan before resume")
            ledger.resume(
                plan,
                build_sha=self.build_sha,
                model_digest=_combined_digest(identities),
                engines=identities,
                override=override,
            )
            self._run(plan, task_dir, ledger, input_map)
        finally:
            ledger.close()
        return task_dir

    def _input_map(
        self, plan: TaskPlan, source_dir: Path, task_dir: Path
    ) -> dict[str, dict[str, str]]:
        by_id = {bite.bite_id: bite for bite in plan.bites}
        source_root = source_dir.expanduser().resolve()
        data_dir = task_dir / TASK_DATA_DIRECTORY
        data_dir.mkdir()
        staged: dict[Path, str] = {}
        staged_bytes = 0
        out: dict[str, dict[str, str]] = {}
        for bite in plan.bites:
            inputs: dict[str, str] = {}
            for ref in bite.inputs:
                if ref in by_id:
                    if ref not in bite.depends_on:
                        raise ValueError(
                            f"bite {bite.bite_id}: input bite {ref} must be a dependency"
                        )
                    inputs[ref] = by_id[ref].output_path
                    continue
                relative_ref = Path(ref)
                path = (source_root / relative_ref).resolve()
                if (
                    relative_ref.is_absolute()
                    or ".." in relative_ref.parts
                    or not path.is_relative_to(source_root)
                ):
                    raise ValueError(f"bite {bite.bite_id}: input path escapes source directory")
                if not path.is_file():
                    raise ValueError(f"bite {bite.bite_id}: input file does not exist: {ref}")
                if path in staged:
                    inputs[ref] = staged[path]
                    continue
                if len(staged) >= TASK_FILE_LIMIT:
                    raise ValueError(f"task inputs exceed the {TASK_FILE_LIMIT}-file limit")
                # Keep the source layout so staged files can still import their siblings.
                relative = Path("inputs") / path.relative_to(source_root)
                target = data_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                staged_bytes += _copy_input(path, target, TASK_BYTES_LIMIT - staged_bytes)
                staged[path] = relative.as_posix()
                inputs[ref] = staged[path]
            out[bite.bite_id] = inputs
        return out

    def _identities(self) -> dict[str, dict[str, str]]:
        return {seat: self.engines[seat].identity() for seat in ("fast", "deep")}

    def _run(
        self,
        plan: TaskPlan,
        task_dir: Path,
        ledger: ArmLedger,
        input_map: dict[str, dict[str, str]],
    ) -> None:
        self.queue_yield_reason = None
        self._shadow_jobs = []
        self._refresh_ready(plan, ledger)
        completed = {
            bite.bite_id
            for bite in plan.bites
            if ledger.bite(bite.bite_id)["state"] in {"passed", "blocked"}
        }
        waiting, paused, calibration_records, waiting_for_capacity = self._execute_ready(
            plan, task_dir, ledger, input_map, completed
        )
        results = self._receipt_results(plan, ledger)
        status = self._task_status(results, waiting, paused, waiting_for_capacity)
        ledger.set_task_status(status, build_sha=self.build_sha, model=self._identities()["fast"])
        self._write_receipt(task_dir, plan, status, results, calibration_records)
        self._start_shadow_jobs(task_dir)

    def _execute_ready(
        self,
        plan: TaskPlan,
        task_dir: Path,
        ledger: ArmLedger,
        input_map: dict[str, dict[str, str]],
        completed: set[str],
    ) -> tuple[bool, bool, list[dict[str, Any]], bool]:
        calibration_records: list[dict[str, Any]] = []
        waiting_for_approval = paused_for_replan = waiting_for_capacity = False
        while True:
            self._block_unreachable(plan, ledger)
            ready = [bite for bite in plan.bites if ledger.bite(bite.bite_id)["state"] == "ready"]
            if not ready:
                break
            bite = self._choose(ready, plan, ledger)
            if self.bite_gate is not None and not self.bite_gate(bite):
                waiting_for_capacity = True
                break
            decision = self._approval_decision(plan, bite, ledger)
            if decision == "wait":
                waiting_for_approval = True
                break
            if decision == "denied":
                completed.add(bite.bite_id)
                self._refresh_ready(plan, ledger)
                continue
            try:
                self._run_bite(plan, bite, task_dir, ledger, input_map[bite.bite_id])
            except QueueYieldError:
                waiting_for_capacity = True
                break
            if ledger.bite(bite.bite_id)["state"] in {"passed", "blocked"}:
                completed.add(bite.bite_id)
            if self._calibration_checkpoint(plan, completed, calibration_records):
                paused_for_replan = True
                break
            self._refresh_ready(plan, ledger)
        return waiting_for_approval, paused_for_replan, calibration_records, waiting_for_capacity

    def _approval_decision(self, plan: TaskPlan, bite: Bite, ledger: ArmLedger) -> str:
        if not self._approval_required(bite):
            return "run"
        decision = self.notices.approval(
            plan.task_id,
            bite.bite_id,
            bite.as_dict(),
            f"high-risk write tools: {', '.join(bite.tools)}",
            str(ledger.task()["created_at"]),
        )
        if decision is None:
            return "wait"
        if decision:
            return "run"
        failure = {"reason": "operator denied the Telegram approval gate"}
        ledger.transition(
            bite,
            "blocked",
            build_sha=self.build_sha,
            engine=self.engines[bite.model].identity(),
            failure=failure,
        )
        self.notices.blocked(plan.task_id, bite.bite_id, failure)
        return "denied"

    def _calibration_checkpoint(
        self,
        plan: TaskPlan,
        completed: set[str],
        records: list[dict[str, Any]],
    ) -> bool:
        calibration = self.arm_config.get("calibration", {})
        if not isinstance(calibration, dict):
            return False
        interval = calibration.get("after_bites", 0)
        if (
            not isinstance(interval, int)
            or interval <= 0
            or len(completed) < interval
            or len(completed) % interval
        ):
            return False
        if calibration.get("minimum_pass_probability") is None:
            return False
        projection, pause = calibration_status(calibration, plan, completed)
        if projection is not None:
            records.append(
                {
                    "after_bites": len(completed),
                    "remaining_bites": projection.remaining_bites,
                    "projected_pass_probability": projection.pass_probability,
                    "projected_cost_seconds": projection.expected_seconds,
                    "threshold": calibration["minimum_pass_probability"],
                }
            )
        return pause

    def _task_status(
        self, results: list[dict[str, Any]], waiting: bool, paused: bool, waiting_for_capacity: bool
    ) -> str:
        if waiting or waiting_for_capacity:
            return "WAITING"
        if paused:
            return "PAUSED_FOR_REPLAN"
        return (
            "BLOCKED" if any(item["state"] in {"blocked", "failed"} for item in results) else "PASS"
        )

    def _write_receipt(
        self,
        task_dir: Path,
        plan: TaskPlan,
        status: str,
        results: list[dict[str, Any]],
        calibration_records: list[dict[str, Any]],
    ) -> None:
        receipt = {
            "head": self.build_sha,
            "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workdir": str(task_dir.resolve()),
            "task_id": plan.task_id,
            "status": status,
            "residency_mode": self.residency_mode,
            "model_digests": {
                seat: data["model_digest"] for seat, data in self._identities().items()
            },
            "calibration": calibration_records,
            "results": results,
        }
        (task_dir / "receipt.json").write_text(
            json.dumps(receipt, indent=1) + "\n", encoding="utf-8"
        )

    def _approval_required(self, bite: Bite) -> bool:
        approval = self.arm_config.get("approval", {})
        disciplines = self.arm_config.get("disciplines", {})
        discipline = disciplines.get(bite.discipline, {}) if isinstance(disciplines, dict) else {}
        if not isinstance(approval, dict) or not approval.get("high_risk_writes"):
            return False
        if not isinstance(discipline, dict):
            return False
        review = self.arm_config.get("review", {})
        if not isinstance(review, dict) or not is_high_risk(bite, discipline, review):
            return False
        action_tools = discipline.get("action_tools", [])
        scope = discipline.get("write_scope")
        return bool(set(bite.tools) & set(action_tools)) or (
            scope is not None and scope != "task_directory"
        )

    def _refresh_ready(self, plan: TaskPlan, ledger: ArmLedger) -> None:
        for bite in plan.bites:
            row = ledger.bite(bite.bite_id)
            if row["state"] == "pending" and all(
                ledger.bite(dep)["state"] == "passed" for dep in bite.depends_on
            ):
                ledger.ready(
                    bite, build_sha=self.build_sha, engine=self.engines[bite.model].identity()
                )

    def _block_unreachable(self, plan: TaskPlan, ledger: ArmLedger) -> None:
        changed = True
        while changed:
            changed = False
            for bite in plan.bites:
                row = ledger.bite(bite.bite_id)
                if row["state"] != "pending":
                    continue
                bad = [
                    dep
                    for dep in bite.depends_on
                    if ledger.bite(dep)["state"] in {"blocked", "superseded"}
                ]
                if bad:
                    failure = {"reason": "dependency blocked", "dependencies": bad}
                    ledger.transition(
                        bite,
                        "blocked",
                        build_sha=self.build_sha,
                        engine=self.engines[bite.model].identity(),
                        failure=failure,
                    )
                    self.notices.blocked(plan.task_id, bite.bite_id, failure)
                    changed = True

    def _choose(self, ready: list[Bite], plan: TaskPlan, ledger: ArmLedger) -> Bite:
        if self.residency_mode != "swap":
            return ready[0]
        fast = [bite for bite in ready if bite.model == "fast"]
        deep = [bite for bite in ready if bite.model == "deep"]
        if not fast:
            return deep[0]
        for bite in deep:
            if _downstream_count(bite, plan) > len(fast):
                return bite
        return fast[0]

    def _run_bite(
        self,
        plan: TaskPlan,
        bite: Bite,
        task_dir: Path,
        ledger: ArmLedger,
        input_paths: dict[str, str],
    ) -> None:
        seats = ["fast", "fast", "fast", "deep"] if bite.model == "fast" else ["deep"]
        final_failure: dict[str, Any] = {"reason": "failure ladder exhausted"}
        for attempt_index, seat in enumerate(seats, start=1):
            failure = self._run_attempt(
                bite, task_dir, ledger, input_paths, seat, attempt_index, len(seats)
            )
            if failure is None:
                return
            final_failure = failure
        ledger.transition(
            bite,
            "blocked",
            build_sha=self.build_sha,
            engine=self.engines[seats[-1]].identity(),
            failure=final_failure,
        )
        self.notices.blocked(plan.task_id, bite.bite_id, final_failure)

    def _run_attempt(
        self,
        bite: Bite,
        task_dir: Path,
        ledger: ArmLedger,
        input_paths: dict[str, str],
        seat: str,
        attempt_index: int,
        attempt_count: int,
    ) -> dict[str, Any] | None:
        engine = self.engines[seat]
        ledger.transition(bite, "running", build_sha=self.build_sha, engine=engine.identity())
        attempt_number = int(ledger.bite(bite.bite_id)["attempts"])
        attempt_dir = task_dir / "bites" / bite.bite_id / "attempts" / f"{attempt_number:02d}"
        resolved_inputs = {key: Path(value) for key, value in input_paths.items()}
        disciplines = self.arm_config.get("disciplines", {})
        discipline = disciplines.get(bite.discipline, {}) if isinstance(disciplines, dict) else {}
        persona = discipline.get("persona") if isinstance(discipline, dict) else None
        started = time.monotonic()
        try:
            worker = run_bite(
                task_dir,
                bite,
                engine,
                input_paths=resolved_inputs,
                attempt_dir=attempt_dir,
                require_idle=self.bite_gate is not None,
                persona=persona,
            )
        except QueueYieldError as exc:
            self.queue_yield_reason = str(exc)
            ledger.yield_attempt(
                bite, build_sha=self.build_sha, engine=engine.identity(), reason=str(exc)
            )
            shutil.rmtree(attempt_dir, ignore_errors=True)
            raise
        failure = self._judge_attempt(
            bite,
            task_dir,
            ledger,
            engine,
            worker,
            attempt_dir,
            attempt_number,
            seat,
            attempt_index,
            attempt_count,
        )
        # Shadow only the attempt that decided the bite; retry noise would
        # inflate the false-accept/false-fail counts with duplicate inputs.
        if failure is None or attempt_index == attempt_count:
            self._launch_shadow(
                bite, task_dir, attempt_dir, input_paths, seat, time.monotonic() - started
            )
        return failure

    def _launch_shadow(
        self,
        bite: Bite,
        task_dir: Path,
        attempt_dir: Path,
        input_paths: dict[str, str],
        seat_name: str,
        incumbent_seconds: float,
    ) -> None:
        comparison: dict[str, Any] = {
            "task_id": task_dir.name,
            "bite_id": bite.bite_id,
            "attempt": attempt_dir.name,
            "incumbent_latency_seconds": incumbent_seconds,
        }
        try:
            discipline = self.arm_config["disciplines"].get(bite.discipline, {})
            if not isinstance(discipline, dict):
                return
            kind = self._shadow_kind(bite, discipline)
            seats = discipline.get("shadow_seats", {})
            seat = seats.get(kind) if isinstance(seats, dict) and kind else None
            if not isinstance(seat, dict):
                return
            comparison.update(
                {
                    "kind": kind,
                    "incumbent_model": self.engines[seat_name].model_tag,
                    "shadow_model": seat["model"],
                    "incumbent_verdict": json.loads(
                        (attempt_dir / "checks.json").read_text(encoding="utf-8")
                    )["passed"],
                }
            )
            shadow_dir = attempt_dir / "shadow"
            job = {
                "bite": bite.as_dict(),
                "inputs": input_paths,
                "comparison": comparison,
                "timeout_seconds": seat["timeout_seconds"],
                "pipeline_url": self.engines[seat_name].base_url,
                "incumbent_model": self.engines[seat_name].model_tag,
                "deep_model": self.engines["deep"].model_tag,
                "config": self.arm_config,
                "task_dir": str(task_dir),
                "source_data": str(task_dir / TASK_DATA_DIRECTORY),
            }
            job_path = shadow_dir / "job.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job) + "\n", encoding="utf-8")
            self._shadow_jobs.append(job_path)
        except Exception as exc:
            _append_shadow_error(task_dir, comparison, f"launch: {type(exc).__name__}: {exc}")

    @staticmethod
    def _shadow_kind(bite: Bite, discipline: dict[str, Any]) -> str | None:
        if not bite.tools:
            return "check"
        declared = discipline.get("read_tools")
        read_tools = frozenset(declared) if isinstance(declared, list) else READ_TOOLS
        return "read" if set(bite.tools) <= read_tools else None

    def _start_shadow_jobs(self, task_dir: Path) -> None:
        if not self._shadow_jobs:
            return
        try:
            manifest = task_dir / f"shadow_jobs_{uuid4().hex}.json"
            manifest.write_text(
                json.dumps([str(path) for path in self._shadow_jobs]) + "\n", encoding="utf-8"
            )
            with (task_dir / "shadow_worker.log").open("a", encoding="utf-8") as log:
                subprocess.Popen(
                    [sys.executable, "-m", "portal.modules.orchestration.shadow", str(manifest)],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except Exception as exc:
            for job_path in self._shadow_jobs:
                with suppress(OSError, KeyError, TypeError, ValueError):
                    comparison = json.loads(job_path.read_text(encoding="utf-8"))["comparison"]
                    _append_shadow_error(
                        task_dir, comparison, f"launch: {type(exc).__name__}: {exc}"
                    )

    def _judge_attempt(
        self,
        bite: Bite,
        task_dir: Path,
        ledger: ArmLedger,
        engine: Engine,
        worker: Any,
        attempt_dir: Path,
        attempt_number: int,
        seat: str,
        attempt_index: int,
        attempt_count: int,
    ) -> dict[str, Any] | None:
        ledger.transition(
            bite,
            "checking",
            build_sha=self.build_sha,
            engine=engine.identity(),
            wall_seconds=worker.elapsed_seconds,
            detail={"loop_outcome": worker.loop_outcome, "red_flags": list(worker.red_flags)},
        )
        checks = (
            check_output(bite, worker.output, task_dir / TASK_DATA_DIRECTORY)
            if worker.finished
            else None
        )
        failures = list(worker.red_flags)
        if worker.failure:
            failures.append(worker.failure)
        if checks is not None and not checks.passed:
            failures.extend(checks.failures)
        try:
            review = self._review_attempt(bite, worker, failures)
        except QueueYieldError as exc:
            self.queue_yield_reason = str(exc)
            ledger.transition(
                bite,
                "ready",
                build_sha=self.build_sha,
                engine=engine.identity(),
                detail={"queue_yield": str(exc)},
            )
            _inside_task(task_dir / TASK_DATA_DIRECTORY, bite.output_path).unlink(missing_ok=True)
            raise
        if review is not None and not review["passed"]:
            failures.append(review["failure"])
        check_record = self._check_record(worker, checks, review, failures)
        (attempt_dir / "checks.json").write_text(
            json.dumps(check_record, indent=2, default=str) + "\n", encoding="utf-8"
        )
        if not failures:
            ledger.transition(
                bite,
                "passed",
                build_sha=self.build_sha,
                engine=engine.identity(),
                wall_seconds=worker.elapsed_seconds,
                detail={"checks": check_record},
            )
            return None
        failure = {"attempt": attempt_number, "model": seat, "failures": failures}
        self._record_failed_attempt(
            bite,
            task_dir,
            ledger,
            engine,
            worker,
            check_record,
            failure,
            attempt_index,
            attempt_count,
        )
        return failure

    def _review_attempt(
        self, bite: Bite, worker: Any, failures: list[Any]
    ) -> dict[str, Any] | None:
        if not worker.finished or failures:
            return None
        gate = self.bite_gate
        return _review_worker(
            bite,
            worker.output,
            self.arm_config,
            self.engines["deep"],
            None if gate is None else lambda: bool(gate(bite)),
        )

    @staticmethod
    def _check_record(worker: Any, checks: Any, review: Any, failures: list[Any]) -> dict[str, Any]:
        return {
            "passed": not failures,
            "red_flags": list(worker.red_flags),
            "deterministic": list(checks.values) if checks else [],
            "deep_review": review,
            "failures": failures,
            "output_tokens": worker.output_tokens,
            "elapsed_seconds": worker.elapsed_seconds,
        }

    def _record_failed_attempt(
        self,
        bite: Bite,
        task_dir: Path,
        ledger: ArmLedger,
        engine: Engine,
        worker: Any,
        check_record: dict[str, Any],
        failure: dict[str, Any],
        attempt_index: int,
        attempt_count: int,
    ) -> None:
        retry_available = attempt_index < attempt_count
        ledger.transition(
            bite,
            "failed",
            build_sha=self.build_sha,
            engine=engine.identity(),
            wall_seconds=worker.elapsed_seconds,
            detail={"checks": check_record, "retry_available": retry_available},
            failure=failure,
        )
        _inside_task(task_dir / TASK_DATA_DIRECTORY, bite.output_path).unlink(missing_ok=True)
        if retry_available:
            ledger.transition(
                bite,
                "ready",
                build_sha=self.build_sha,
                engine=engine.identity(),
                detail={"retry": attempt_index + 1},
            )

    def _receipt_results(self, plan: TaskPlan, ledger: ArmLedger) -> list[dict[str, Any]]:
        out = []
        for bite in plan.bites:
            row = ledger.bite(bite.bite_id)
            out.append(
                {
                    "scenario": bite.bite_id,
                    "task_id": plan.task_id,
                    "bite_id": bite.bite_id,
                    "status": _receipt_bite_status(str(row["state"])),
                    "state": row["state"],
                    "attempts": row["attempts"],
                    "failure": json.loads(row["failure_json"]) if row["failure_json"] else None,
                    "evidence": {
                        "state": row["state"],
                        "attempts": row["attempts"],
                        "failure": json.loads(row["failure_json"]) if row["failure_json"] else None,
                    },
                }
            )
        return out


def load_residency_mode(path: Path) -> str:
    """Load the scheduler mode, defaulting safely to swap."""
    if not path.is_file():
        return "swap"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mode = raw.get("residency_mode", "swap") if isinstance(raw, dict) else "swap"
    if mode not in {"swap", "co-resident"}:
        raise ValueError("residency_mode must be swap or co-resident")
    return str(mode)


def load_arm_config(path: Path) -> dict[str, Any]:
    """Load generated arm policy and fail closed when required sections are absent."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = {"planner", "review", "approval", "calibration", "disciplines"}
    if not isinstance(raw, dict) or not required <= set(raw):
        raise ValueError(f"orchestration config must define {sorted(required)}")
    if not all(isinstance(raw[key], dict) for key in required):
        raise ValueError("orchestration policy sections must be mappings")
    for name, discipline in raw["disciplines"].items():
        shadows = discipline.get("shadow_seats", {}) if isinstance(discipline, dict) else {}
        if not isinstance(shadows, dict):
            raise ValueError(f"{name}: shadow_seats must be a mapping")
        for kind, seat in shadows.items():
            if (
                kind not in {"read", "check"}
                or not isinstance(seat, dict)
                or not isinstance(seat.get("model"), str)
                or not seat["model"].startswith("portal5/")
                or not isinstance(seat.get("timeout_seconds"), (int, float))
                or isinstance(seat["timeout_seconds"], bool)
                or seat["timeout_seconds"] <= 0
            ):
                raise ValueError(f"{name}: invalid shadow_seats.{kind}")
    _validate_shadow_wait(raw.get("shadow_slot_wait_seconds"))
    return raw


def _validate_shadow_wait(raw: Any) -> None:
    if raw is None:
        return
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        raise ValueError("shadow_slot_wait_seconds must be a positive number")


def seated_model_tags(config: dict[str, Any]) -> dict[str, str]:
    """Pipeline variant per seat: one discipline-wide choice, defaulting to auto-daily::<seat>."""
    tags = {seat: f"auto-daily::{seat}" for seat in ("fast", "deep")}
    chosen: dict[str, str] = {}
    for name, discipline in config["disciplines"].items():
        seated = discipline.get("seated_models") if isinstance(discipline, dict) else None
        for seat, tag in (seated or {}).items():
            if seat not in tags or not isinstance(tag, str) or not tag.startswith("auto-daily::"):
                raise ValueError(f"{name}: seated_models.{seat} must be an auto-daily:: variant")
            if chosen.setdefault(seat, tag) != tag:
                raise ValueError(
                    f"disciplines disagree on the {seat} seat: {chosen[seat]} vs {tag}"
                )
    return tags | chosen


# Host seat digests. `portal arm digests refresh` rewrites this file.
ARM_DIGESTS_ENV = Path.home() / ".portal5" / "arm_digests.env"
_ARM_SEATS = ("fast", "deep")


def resolve_seat_digest(
    seat: str,
    identity: Any,
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
    fetch_tags: Callable[[], Mapping[str, Any]] | None = None,
    config_path: Path | None = None,
) -> str:
    """Seat digest from the env var, then Ollama /api/tags, then the host arm_digests.env file."""
    source = os.environ if environ is None else environ
    key = f"PORTAL_ARM_{seat.upper()}_DIGEST"
    configured = str(source.get(key, "")).strip()
    if configured:
        return configured
    model = str(identity.get("model") or "").strip() if isinstance(identity, dict) else ""
    if model:
        found = _digest_from_tags(model, (fetch_tags or _fetch_ollama_tags)())
        if found:
            return found
    path = env_file or ARM_DIGESTS_ENV
    found = _digest_from_env_file(path, key)
    if found:
        _warn_stale_arm_digests(path, config_path or _default_config_path())
    return found


def refresh_arm_digests(
    config: Mapping[str, Any],
    *,
    env_file: Path | None = None,
    config_path: Path | None = None,
    client: httpx.Client | None = None,
    omlx_identity: Callable[[str], tuple[str, str]] | None = None,
    dry_run: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, str]:
    """Compute both seat digests and atomically rewrite the host arm_digests.env file."""
    load_plan = config.get("load_plan_models") if isinstance(config, Mapping) else None
    if not isinstance(load_plan, Mapping):
        raise ValueError("load_plan_models must map the fast and deep seats")
    tags: Mapping[str, Any] = {}
    if _plan_uses_ollama(load_plan):
        tags, why = _ollama_tags(client)
        if why:
            raise ValueError(why)
    identity = omlx_identity or _wfe_omlx_content
    digests: dict[str, str] = {}
    for seat in _ARM_SEATS:
        digest, why = _seat_digest(load_plan.get(seat), tags, identity)
        if not digest:
            raise ValueError(f"load_plan_models.{seat}: {why}")
        digests[seat] = digest
    if not dry_run:
        moment = (clock or (lambda: datetime.now(UTC)))()
        _write_arm_digests(
            env_file or ARM_DIGESTS_ENV,
            digests,
            config_path or _default_config_path(),
            moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    return digests


def _digest_from_env_file(path: Path, key: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip().strip("'\"")
    return ""


def _digest_from_tags(model: str, payload: Mapping[str, Any]) -> str:
    models = payload.get("models")
    if not isinstance(models, list):
        return ""
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "")
        if name == model:
            return str(item.get("digest") or "").strip()
    return ""


def _fetch_ollama_tags() -> dict[str, Any]:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as response:
            raw = response.read()
    except (OSError, ValueError):
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _warn_stale_arm_digests(env_file: Path, config_path: Path) -> None:
    """Warn when the digest file is older than the seat config it was written from."""
    try:
        stale = env_file.stat().st_mtime < config_path.stat().st_mtime
    except OSError:
        return
    if stale:
        warnings.warn(
            f"{env_file} is older than {config_path}; run `portal arm digests refresh`",
            UserWarning,
            stacklevel=3,
        )


def _plan_uses_ollama(load_plan: Mapping[str, Any]) -> bool:
    return any(_seat_model(load_plan.get(seat))[1] == "ollama" for seat in _ARM_SEATS)


def _seat_model(spec: Any) -> tuple[str, str]:
    if not isinstance(spec, Mapping):
        return "", ""
    model = str(spec.get("model") or "").strip()
    engine = str(spec.get("engine") or "").strip()
    return model, engine


def _seat_digest(
    spec: Any,
    tags: Mapping[str, Any],
    omlx_identity: Callable[[str], tuple[str, str]],
) -> tuple[str, str]:
    model, engine = _seat_model(spec)
    if not model or not engine:
        return "", "engine and model are required"
    if engine == "ollama":
        found = _digest_from_tags(model, tags)
        return (found, "") if found else ("", f"{model!r} is not in Ollama /api/tags")
    if engine == "omlx":
        content, why = omlx_identity(model)
        text = str(content).strip()
        return (text, "") if text else ("", why or "oMLX content is unobservable")
    return "", f"engine {engine!r} has no content identity"


def _wfe_omlx_content(model: str) -> tuple[str, str]:
    """The oMLX content id shared with the WFE identity guard."""
    from portal.platform.inference.identity import omlx_content_id

    return omlx_content_id(model)


def _ollama_tags(client: httpx.Client | None) -> tuple[dict[str, Any], str]:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    owns = client is None
    http = client or httpx.Client(trust_env=False, timeout=10.0)
    try:
        response = http.get(f"{host}/api/tags")
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {}, f"Ollama /api/tags unreachable ({type(exc).__name__})"
    finally:
        if owns:
            http.close()
    if not isinstance(payload, dict):
        return {}, "Ollama /api/tags returned no model list"
    return payload, ""


def _write_arm_digests(path: Path, digests: Mapping[str, str], source: Path, stamped: str) -> None:
    body = "\n".join(
        [
            f"# refreshed {stamped} from {source}",
            *(f"PORTAL_ARM_{seat.upper()}_DIGEST={digests[seat]}" for seat in _ARM_SEATS),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(body, encoding="utf-8")
    try:
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _positive_probability(value: Any) -> bool:
    """True only for a numeric probability in (0, 1]."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1


def _require_calibration(
    config: dict[str, Any], unattended: bool, disciplines: set[str] | None = None
) -> None:
    calibration = config["calibration"]
    if unattended and not _positive_probability(calibration.get("minimum_pass_probability")):
        raise ValueError(
            "unattended runs are disabled until Gate C rates set a positive calibration threshold"
        )
    if not unattended:
        return
    rates = calibration.get("rates_by_discipline", {})
    for discipline in disciplines or set():
        profile = rates.get(discipline) if isinstance(rates, dict) else None
        if not isinstance(profile, dict) or not {"fast", "deep"} <= set(profile):
            raise ValueError(f"unattended runs need Fast and Deep WFE rates for {discipline}")
        for seat in ("fast", "deep"):
            seat_rates = profile[seat]
            if (
                not isinstance(seat_rates, dict)
                or not isinstance(seat_rates.get("pass_probability"), (int, float))
                or not 0 <= seat_rates["pass_probability"] <= 1
                or not isinstance(seat_rates.get("mean_seconds"), (int, float))
                or seat_rates["mean_seconds"] < 0
            ):
                raise ValueError(f"unattended runs need valid WFE rates for {discipline}/{seat}")


def _review_worker(
    bite: Bite,
    output: Any,
    config: dict[str, Any],
    engine: Engine,
    gate: Callable[[], bool] | None = None,
) -> dict[str, Any] | None:
    review = config.get("review", {})
    disciplines = config.get("disciplines", {})
    discipline = disciplines.get(bite.discipline, {}) if isinstance(disciplines, dict) else {}
    if not isinstance(review, dict) or not isinstance(discipline, dict):
        return None
    high_risk = is_high_risk(bite, discipline, review)
    if not high_risk and bite.review != "deep":
        return None
    votes = review.get("vote_count", 0) if high_risk else 1
    required = review.get("minimum_approve_votes", 0) if high_risk else 1
    try:
        result = review_output(
            engine,
            bite,
            output,
            vote_count=int(votes),
            minimum_approve_votes=int(required),
            persona=discipline.get("persona"),
            require_idle=gate is not None,
            gate=gate,
        )
    except QueueYieldError:
        raise
    except Exception as exc:
        return {"passed": False, "failure": f"Deep review failed: {type(exc).__name__}: {exc}"}
    return {
        "passed": result.passed,
        "approvals": result.approvals,
        "required": result.required,
        "votes": list(result.votes),
        "failure": (
            None
            if result.passed
            else f"Deep review received {result.approvals}/{len(result.votes)} approvals; "
            f"{result.required} required"
        ),
    }


def _append_shadow_error(task_dir: Path, comparison: dict[str, Any], error: str) -> None:
    from .shadow import append_comparison

    with suppress(OSError, TypeError, ValueError):
        append_comparison(
            task_dir,
            {**comparison, "shadow_verdict": None, "agree": None, "error": error},
        )


def module_is_enabled(config_path: Path) -> bool:
    """Read the arm's persisted module switch without loading Portal runtime state."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    state = raw.get("modules", {}).get("orchestration", {})
    return bool(state.get("enabled", False)) if isinstance(state, dict) else False


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("could not determine build SHA from git HEAD")
    return result.stdout.strip()


def _combined_digest(identities: dict[str, dict[str, str]]) -> str:
    payload = json.dumps(
        {seat: identity["model_digest"] for seat, identity in identities.items()}, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _downstream_count(bite: Bite, plan: TaskPlan) -> int:
    found: set[str] = set()
    frontier = {bite.bite_id}
    while frontier:
        children = {
            candidate.bite_id
            for candidate in plan.bites
            if candidate.bite_id not in found and frontier.intersection(candidate.depends_on)
        }
        found.update(children)
        frontier = children
    return len(found)


def _copy_input(source: Path, target: Path, remaining_bytes: int) -> int:
    copied = 0
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        while chunk := input_stream.read(min(1024 * 1024, remaining_bytes - copied + 1)):
            copied += len(chunk)
            if copied > remaining_bytes:
                raise ValueError(f"task inputs exceed the {TASK_BYTES_LIMIT}-byte limit")
            output_stream.write(chunk)
    return copied


def _receipt_bite_status(state: str) -> str:
    if state == "passed":
        return "PASS"
    if state == "blocked":
        return "BLOCKED"
    return state.upper()


def _inside_task(task_dir: Path, relative: str) -> Path:
    target = (task_dir / relative).resolve()
    if not target.is_relative_to(task_dir.resolve()):
        raise ValueError("bite output path escapes the task directory")
    return target
