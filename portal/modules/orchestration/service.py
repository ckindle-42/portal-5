"""Offline-first orchestration arm for hand-written bite plans."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from .calibration import calibration_status
from .contracts import Bite, TaskPlan, parse_plan
from .ledger import ArmLedger
from .planner import plan_goal
from .review import is_high_risk, review_output
from .worker import Engine, check_output, run_bite


class NoticeSink(Protocol):
    """Receives an exhausted bite notification."""

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None: ...

    def approval(self, task_id: str, bite_id: str, reason: str) -> bool | None: ...


class StubNoticeSink:
    """Test and offline notice sink; it never sends a message."""

    def __init__(self) -> None:
        self.notices: list[dict[str, Any]] = []

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        self.notices.append({"task_id": task_id, "bite_id": bite_id, "failure": failure})

    def approval(self, task_id: str, bite_id: str, reason: str) -> bool | None:
        return None


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
    ) -> None:
        self.task_root = task_root
        self.engines = engines
        if engines["fast"].model_tag != "auto-daily::fast":
            raise ValueError("fast seat must use auto-daily::fast")
        if engines["deep"].model_tag != "auto-daily::deep":
            raise ValueError("deep seat must use auto-daily::deep")
        self.build_sha = build_sha or _head_sha()
        self.config_path = residency_config or _default_config_path()
        self.arm_config = load_arm_config(self.config_path)
        self.residency_mode = load_residency_mode(self.config_path)
        self.notices = notices or StubNoticeSink()

    def submit(
        self, raw_plan: dict[str, Any], source_dir: Path, *, unattended: bool = True
    ) -> Path:
        plan = parse_plan(raw_plan)
        _require_calibration(self.arm_config, unattended, {bite.discipline for bite in plan.bites})
        task_dir = self.task_root / plan.task_id
        if task_dir.exists():
            raise FileExistsError(f"task already exists: {task_dir}")
        input_map = self._input_map(plan, source_dir, task_dir)
        task_dir.mkdir(parents=True)
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
        plan = parse_plan(json.loads((task_dir / "plan.json").read_text(encoding="utf-8")))
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
        out: dict[str, dict[str, str]] = {}
        for bite in plan.bites:
            inputs: dict[str, str] = {}
            for ref in bite.inputs:
                if ref in by_id:
                    if ref not in bite.depends_on:
                        raise ValueError(
                            f"bite {bite.bite_id}: input bite {ref} must be a dependency"
                        )
                    inputs[ref] = str(task_dir / by_id[ref].output_path)
                    continue
                path = Path(ref).expanduser()
                path = (path if path.is_absolute() else source_dir / path).resolve()
                if not path.is_file():
                    raise ValueError(f"bite {bite.bite_id}: input file does not exist: {ref}")
                inputs[ref] = str(path)
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
        self._refresh_ready(plan, ledger)
        completed = {
            bite.bite_id
            for bite in plan.bites
            if ledger.bite(bite.bite_id)["state"] in {"passed", "blocked"}
        }
        waiting, paused, calibration_records = self._execute_ready(
            plan, task_dir, ledger, input_map, completed
        )
        results = self._receipt_results(plan, ledger)
        status = self._task_status(results, waiting, paused)
        ledger.set_task_status(status, build_sha=self.build_sha, model=self._identities()["fast"])
        self._write_receipt(task_dir, plan, status, results, calibration_records)

    def _execute_ready(
        self,
        plan: TaskPlan,
        task_dir: Path,
        ledger: ArmLedger,
        input_map: dict[str, dict[str, str]],
        completed: set[str],
    ) -> tuple[bool, bool, list[dict[str, Any]]]:
        calibration_records: list[dict[str, Any]] = []
        waiting_for_approval = paused_for_replan = False
        while True:
            self._block_unreachable(plan, ledger)
            ready = [bite for bite in plan.bites if ledger.bite(bite.bite_id)["state"] == "ready"]
            if not ready:
                break
            bite = self._choose(ready, plan, ledger)
            decision = self._approval_decision(plan, bite, ledger)
            if decision == "wait":
                waiting_for_approval = True
                break
            if decision == "denied":
                completed.add(bite.bite_id)
                self._refresh_ready(plan, ledger)
                continue
            self._run_bite(plan, bite, task_dir, ledger, input_map[bite.bite_id])
            if ledger.bite(bite.bite_id)["state"] in {"passed", "blocked"}:
                completed.add(bite.bite_id)
            if self._calibration_checkpoint(plan, completed, calibration_records):
                paused_for_replan = True
                break
            self._refresh_ready(plan, ledger)
        return waiting_for_approval, paused_for_replan, calibration_records

    def _approval_decision(self, plan: TaskPlan, bite: Bite, ledger: ArmLedger) -> str:
        if not self._approval_required(bite):
            return "run"
        decision = self.notices.approval(
            plan.task_id,
            bite.bite_id,
            f"high-risk write tools: {', '.join(bite.tools)}",
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

    def _task_status(self, results: list[dict[str, Any]], waiting: bool, paused: bool) -> str:
        if waiting:
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
        worker = run_bite(
            task_dir, bite, engine, input_paths=resolved_inputs, attempt_dir=attempt_dir
        )
        ledger.transition(
            bite,
            "checking",
            build_sha=self.build_sha,
            engine=engine.identity(),
            wall_seconds=worker.elapsed_seconds,
            detail={"loop_outcome": worker.loop_outcome, "red_flags": list(worker.red_flags)},
        )
        checks = check_output(bite, worker.output, task_dir) if worker.finished else None
        failures = list(worker.red_flags)
        if worker.failure:
            failures.append(worker.failure)
        if checks is not None and not checks.passed:
            failures.extend(checks.failures)
        review = self._review_attempt(bite, worker, failures)
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
        return _review_worker(bite, worker.output, self.arm_config, self.engines["deep"])

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
        _inside_task(task_dir, bite.output_path).unlink(missing_ok=True)
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
    return raw


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
    bite: Bite, output: Any, config: dict[str, Any], engine: Engine
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
        )
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
