"""Offline-first orchestration arm for hand-written bite plans."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from .contracts import Bite, TaskPlan, parse_plan
from .ledger import ArmLedger
from .worker import Engine, check_output, run_bite


class NoticeSink(Protocol):
    """Receives an exhausted bite notification."""

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None: ...


class StubNoticeSink:
    """Test and offline notice sink; it never sends a message."""

    def __init__(self) -> None:
        self.notices: list[dict[str, Any]] = []

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        self.notices.append({"task_id": task_id, "bite_id": bite_id, "failure": failure})


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
        self.residency_mode = load_residency_mode(residency_config or _default_config_path())
        self.notices = notices or StubNoticeSink()

    def submit(self, raw_plan: dict[str, Any], source_dir: Path) -> Path:
        plan = parse_plan(raw_plan)
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

    def resume(self, task_id: str, *, override: bool = False) -> Path:
        task_dir = self.task_root / task_id
        if not task_dir.is_dir():
            raise FileNotFoundError(f"no task directory: {task_dir}")
        plan = parse_plan(json.loads((task_dir / "plan.json").read_text(encoding="utf-8")))
        if plan.task_id != task_id:
            raise ValueError("task directory and plan task_id differ")
        input_map = json.loads((task_dir / "inputs.json").read_text(encoding="utf-8"))
        identities = self._identities()
        ledger = ArmLedger(task_dir)
        try:
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
        while True:
            self._block_unreachable(plan, ledger)
            ready = [bite for bite in plan.bites if ledger.bite(bite.bite_id)["state"] == "ready"]
            if not ready:
                break
            bite = self._choose(ready, plan, ledger)
            self._run_bite(plan, bite, task_dir, ledger, input_map[bite.bite_id])
            self._refresh_ready(plan, ledger)
        results = self._receipt_results(plan, ledger)
        status = "BLOCKED" if any(item["status"] == "BLOCKED" for item in results) else "PASS"
        model = self._identities()["fast"]
        ledger.set_task_status(status, build_sha=self.build_sha, model=model)
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
            "results": results,
        }
        (task_dir / "receipt.json").write_text(
            json.dumps(receipt, indent=1) + "\n", encoding="utf-8"
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
            engine = self.engines[seat]
            ledger.transition(bite, "running", build_sha=self.build_sha, engine=engine.identity())
            attempt_number = int(ledger.bite(bite.bite_id)["attempts"])
            attempt_dir = task_dir / "bites" / bite.bite_id / "attempts" / f"{attempt_number:02d}"
            resolved_inputs = {key: Path(value) for key, value in input_paths.items()}
            worker = run_bite(
                task_dir,
                bite,
                engine,
                input_paths=resolved_inputs,
                attempt_dir=attempt_dir,
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
            check_record = {
                "passed": not failures,
                "red_flags": list(worker.red_flags),
                "deterministic": list(checks.values) if checks else [],
                "failures": failures,
                "output_tokens": worker.output_tokens,
                "elapsed_seconds": worker.elapsed_seconds,
            }
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
                return
            final_failure = {"attempt": attempt_number, "model": seat, "failures": failures}
            ledger.transition(
                bite,
                "failed",
                build_sha=self.build_sha,
                engine=engine.identity(),
                wall_seconds=worker.elapsed_seconds,
                detail={
                    "checks": check_record,
                    "retry_available": attempt_index < len(seats),
                },
                failure=final_failure,
            )
            _inside_task(task_dir, bite.output_path).unlink(missing_ok=True)
            if attempt_index < len(seats):
                ledger.transition(
                    bite,
                    "ready",
                    build_sha=self.build_sha,
                    engine=engine.identity(),
                    detail={"retry": attempt_index + 1},
                )
        ledger.transition(
            bite,
            "blocked",
            build_sha=self.build_sha,
            engine=self.engines[seats[-1]].identity(),
            failure=final_failure,
        )
        self.notices.blocked(plan.task_id, bite.bite_id, final_failure)

    def _receipt_results(self, plan: TaskPlan, ledger: ArmLedger) -> list[dict[str, Any]]:
        out = []
        for bite in plan.bites:
            row = ledger.bite(bite.bite_id)
            out.append(
                {
                    "scenario": bite.bite_id,
                    "task_id": plan.task_id,
                    "bite_id": bite.bite_id,
                    "status": "PASS" if row["state"] == "passed" else "BLOCKED",
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


def _inside_task(task_dir: Path, relative: str) -> Path:
    target = (task_dir / relative).resolve()
    if not target.is_relative_to(task_dir.resolve()):
        raise ValueError("bite output path escapes the task directory")
    return target
