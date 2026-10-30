"""Offline job specs for long live campaigns run by the arm's durable queue; relative paths resolve under the repo root."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

_JOB_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_STEP_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_WFE_MODULE = re.compile(r"^tests\.wfe(\.[A-Za-z_][A-Za-z0-9_]*)+$")
_PYTHON = "python"
REPORT_FIELDS = frozenset(
    {
        "status",
        "purpose",
        "steps",
        "outputs",
        "checkpoints",
        "failures",
        "memory",
        "duration",
        "resume",
    }
)
DEFAULT_DISPATCH_LOCK_DIR = Path.home() / ".claude" / "orchestrate" / "locks"
# A due job that is waiting only on cloud lanes claims the window here; the dispatcher
# (Jarvis Cloud) starts no new lane while the claimant pid is alive, so running lanes
# drain and the job gets its quiet host instead of waiting forever.
WINDOW_CLAIM_NAME = "jarvis_local_window.json"
_TAIL_BYTES = 8192
_PEAK_SAMPLE_SECONDS = 5.0
_ENV_ALLOWLIST = Path("config/arm_job_env_allowlist.yaml")
_ENV_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_REDACTED = "[REDACTED]"
# Short alnum values are receipt-tail only; a byte replace would hit them inside other words.
_FILE_REDACT_MIN = 8
_LOG_REDACT_LIMIT = 32 * 1024 * 1024

_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "timeout_seconds"],
    # A canary step derives its argv from the step it gates, so only plain
    # steps must carry argv.
    "if": {"not": {"required": ["canary"]}},
    "then": {"required": ["argv"]},
    "properties": {
        "id": {"type": "string", "pattern": _STEP_ID.pattern},
        "argv": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "canary": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
        "quiet_host": {"type": "boolean"},
        "idempotent": {"type": "boolean"},
        "outputs": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "checkpoints": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "env_from_dotenv": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        },
    },
}
_JOB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "purpose", "preconditions", "steps", "report"],
    "properties": {
        "id": {"type": "string", "pattern": _JOB_ID.pattern},
        "purpose": {"type": "string", "minLength": 1},
        "preconditions": {
            "type": "object",
            "additionalProperties": False,
            "required": ["stack", "free_memory_gib", "disk_free_gib"],
            "properties": {
                "stack": {"enum": ["up", "down"]},
                "free_memory_gib": {"type": "number", "minimum": 0},
                "disk_free_gib": {"type": "number", "minimum": 0},
                "disk_path": {"type": "string", "minLength": 1},
            },
        },
        "steps": {"type": "array", "minItems": 1, "items": _STEP_SCHEMA},
        "outputs": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "checkpoints": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "stop_conditions": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "on_failure": {"enum": ["stop", "continue"]},
                "output_markers": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "max_job_minutes": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "report": {
            "oneOf": [
                {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"enum": sorted(REPORT_FIELDS)},
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["fields"],
                    "properties": {
                        "fields": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"enum": sorted(REPORT_FIELDS)},
                        }
                    },
                },
            ]
        },
    },
}
_VALIDATOR = Draft202012Validator(_JOB_SCHEMA)


@dataclass(frozen=True)
class JobPreconditionSpec:
    stack: str
    free_memory_gib: float
    disk_free_gib: float
    disk_path: str | None = None


@dataclass(frozen=True)
class JobStep:
    step_id: str
    argv: tuple[str, ...]
    timeout_seconds: float
    outputs: tuple[str, ...] = ()
    checkpoints: tuple[str, ...] = ()
    quiet_host: bool = True
    env_from_dotenv: tuple[str, ...] = ()
    idempotent: bool = True
    #: The step this canary gates: argv is that step's argv with --canary appended.
    canary_of: str | None = None


@dataclass(frozen=True)
class JobStopConditions:
    on_failure: str = "stop"
    output_markers: tuple[str, ...] = ()
    max_job_minutes: float | None = None


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    purpose: str
    preconditions: JobPreconditionSpec
    steps: tuple[JobStep, ...]
    stop_conditions: JobStopConditions
    report_fields: tuple[str, ...]
    outputs: tuple[str, ...] = ()
    checkpoints: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.job_id,
            "purpose": self.purpose,
            "preconditions": {
                "stack": self.preconditions.stack,
                "free_memory_gib": self.preconditions.free_memory_gib,
                "disk_free_gib": self.preconditions.disk_free_gib,
                **(
                    {"disk_path": self.preconditions.disk_path}
                    if self.preconditions.disk_path
                    else {}
                ),
            },
            "steps": [
                {
                    "id": step.step_id,
                    # A canary step omits argv so the round-trip re-derives it
                    # from its reference instead of double-applying --canary.
                    **({} if step.canary_of else {"argv": list(step.argv)}),
                    "timeout_seconds": step.timeout_seconds,
                    "outputs": list(step.outputs),
                    "checkpoints": list(step.checkpoints),
                    # Omitted when true so specs written before the flag stay byte-stable.
                    **({"quiet_host": False} if not step.quiet_host else {}),
                    **({"idempotent": False} if not step.idempotent else {}),
                    **(
                        {"env_from_dotenv": list(step.env_from_dotenv)}
                        if step.env_from_dotenv
                        else {}
                    ),
                    **({"canary": step.canary_of} if step.canary_of else {}),
                }
                for step in self.steps
            ],
            "outputs": list(self.outputs),
            "checkpoints": list(self.checkpoints),
            "stop_conditions": {
                "on_failure": self.stop_conditions.on_failure,
                "output_markers": list(self.stop_conditions.output_markers),
                **(
                    {"max_job_minutes": self.stop_conditions.max_job_minutes}
                    if self.stop_conditions.max_job_minutes is not None
                    else {}
                ),
            },
            "report": {"fields": list(self.report_fields)},
        }


@dataclass(frozen=True)
class PreconditionResult:
    ok: bool
    reasons: tuple[str, ...]
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class JobRun:
    status: str
    job_id: str
    receipt_path: Path | None = None
    reason: str | None = None


@dataclass
class _StepSignal:
    peak: int = 0
    memory_trip: dict[str, Any] | None = None
    timed_out: bool = False
    marker: str | None = None
    job_limit: bool = False


class ExternalGate(Protocol):
    def external_reason(self) -> str | None: ...


class JobNoticeSink(Protocol):
    def job_finished(self, job_id: str, status: str, detail: dict[str, Any]) -> None: ...


def parse_job_spec(raw: Any, *, repo_root: Path) -> JobSpec:
    """Validate a YAML job spec and its argv allowlist."""
    if not isinstance(raw, dict):
        raise ValueError("job spec must be an object")
    errors = sorted(_VALIDATOR.iter_errors(raw), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        where = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValueError(f"job spec is invalid at {where}: {error.message}")
    steps = tuple(_parse_step(item, repo_root) for item in raw["steps"])
    ids = [step.step_id for step in steps]
    if len(set(ids)) != len(ids):
        raise ValueError("step ids must be unique")
    steps = _resolve_canaries(list(steps), repo_root)
    preconditions = raw["preconditions"]
    if preconditions.get("disk_path"):
        _validate_job_path(str(preconditions["disk_path"]))
    stop = raw.get("stop_conditions", {})
    job_outputs = tuple(str(item) for item in raw.get("outputs", []))
    job_checkpoints = tuple(str(item) for item in raw.get("checkpoints", []))
    for value in job_outputs + job_checkpoints:
        _validate_job_path(value)
    report = raw["report"]
    report_fields = report if isinstance(report, list) else report["fields"]
    purpose = str(raw["purpose"]).strip()
    if not purpose:
        raise ValueError("purpose must be a non-empty string")
    return JobSpec(
        job_id=str(raw["id"]),
        purpose=purpose,
        preconditions=JobPreconditionSpec(
            stack=str(preconditions["stack"]),
            free_memory_gib=float(preconditions["free_memory_gib"]),
            disk_free_gib=float(preconditions["disk_free_gib"]),
            disk_path=(str(preconditions["disk_path"]) if preconditions.get("disk_path") else None),
        ),
        steps=steps,
        stop_conditions=JobStopConditions(
            on_failure=str(stop.get("on_failure", "stop")),
            output_markers=tuple(str(item) for item in stop.get("output_markers", [])),
            max_job_minutes=(
                float(stop["max_job_minutes"]) if stop.get("max_job_minutes") else None
            ),
        ),
        report_fields=tuple(str(item) for item in report_fields),
        outputs=job_outputs,
        checkpoints=job_checkpoints,
    )


def job_json(spec: JobSpec) -> str:
    return json.dumps(spec.as_dict(), sort_keys=True)


def _parse_step(raw: dict[str, Any], repo_root: Path) -> JobStep:
    canary_of = str(raw["canary"]) if raw.get("canary") else None
    if canary_of and "argv" in raw:
        raise ValueError(
            f"step {raw['id']}: a canary step derives its argv from {canary_of!r}; drop argv"
        )
    if canary_of:
        argv: tuple[str, ...] = ()
    else:
        argv = tuple(str(token) for token in raw["argv"])
        _validate_argv(argv, repo_root)
    outputs = tuple(str(item) for item in raw.get("outputs", []))
    checkpoints = tuple(str(item) for item in raw.get("checkpoints", []))
    for value in outputs + checkpoints:
        _validate_job_path(value)
    env_from_dotenv = tuple(str(item) for item in raw.get("env_from_dotenv", []))
    if env_from_dotenv:
        _validate_env_keys(env_from_dotenv, repo_root)
    return JobStep(
        step_id=str(raw["id"]),
        argv=argv,
        timeout_seconds=float(raw["timeout_seconds"]),
        outputs=outputs,
        checkpoints=checkpoints,
        quiet_host=bool(raw.get("quiet_host", True)),
        env_from_dotenv=env_from_dotenv,
        idempotent=bool(raw.get("idempotent", True)),
        canary_of=canary_of,
    )


def _resolve_canaries(steps: list[JobStep], repo_root: Path) -> tuple[JobStep, ...]:
    """A `canary: <step>` step runs the named step's argv with --canary appended.
    It must precede the step it gates, and that step must have its own argv."""
    index = {step.step_id: i for i, step in enumerate(steps)}
    out: list[JobStep] = []
    for i, step in enumerate(steps):
        if step.canary_of is None:
            out.append(step)
            continue
        j = index.get(step.canary_of)
        if j is None:
            raise ValueError(f"step {step.step_id}: canary names unknown step {step.canary_of!r}")
        ref = steps[j]
        if ref.canary_of is not None:
            raise ValueError(f"step {step.step_id}: canary must name a step with its own argv")
        if j <= i:
            raise ValueError(f"step {step.step_id}: canary must precede step {step.canary_of!r}")
        argv = (*ref.argv, "--canary")
        _validate_argv(argv, repo_root)
        out.append(replace(step, argv=argv))
    return tuple(out)


def _validate_argv(argv: tuple[str, ...], repo_root: Path) -> None:
    for token in argv:
        if any(unicodedata.category(char) == "Cc" for char in token):
            raise ValueError("step argv must not contain control characters")
    first = argv[0]
    if first == "uv":
        if len(argv) < 4 or argv[1:3] != ("run", _PYTHON):
            raise ValueError("step argv outside the allowlist: use `uv run python -m tests.wfe...`")
        target = argv[3]
        if target == "-m":
            if len(argv) < 5 or not _valid_wfe_module(argv[4]):
                raise ValueError("step argv outside the allowlist: -m must name a tests.wfe module")
            return
        _script_file(target, repo_root, executable=False)
        return
    _script_file(first, repo_root, executable=True)


def _valid_wfe_module(module: str) -> bool:
    return bool(_WFE_MODULE.fullmatch(module)) and not any(
        part.startswith("__") for part in module.split(".")
    )


def _script_file(token: str, repo_root: Path, *, executable: bool) -> Path:
    relative = Path(token.removeprefix("./"))
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != "scripts"
        or ".." in relative.parts
    ):
        raise ValueError(f"step argv {token!r} is outside the repo scripts/ allowlist")
    scripts_root = (repo_root / "scripts").resolve()
    path = (repo_root / relative).resolve()
    if not path.is_relative_to(scripts_root) or not path.is_file():
        raise ValueError(f"step argv {token!r} is outside the repo scripts/ allowlist")
    if executable and not os.access(path, os.X_OK):
        raise ValueError(
            f"step argv {token!r} is not executable; use `uv run python {token}` instead"
        )
    return path


def _validate_env_keys(keys: tuple[str, ...], repo_root: Path) -> None:
    patterns = _load_env_allowlist(repo_root)
    rejected = [key for key in keys if not _env_key_allowed(key, patterns)]
    if rejected:
        raise ValueError("env_from_dotenv keys outside the allowlist: " + ", ".join(rejected))


def _load_env_allowlist(repo_root: Path) -> tuple[str, ...]:
    path = repo_root / _ENV_ALLOWLIST
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read env allowlist {path.name}") from exc
    except yaml.YAMLError as exc:
        raise ValueError("env allowlist is not valid YAML") from exc
    if not isinstance(loaded, dict):
        raise ValueError("env allowlist must be a mapping")
    raw_patterns = loaded.get("patterns")
    if not isinstance(raw_patterns, list) or not raw_patterns:
        raise ValueError("env allowlist patterns must be a non-empty list")
    patterns: list[str] = []
    for item in raw_patterns:
        pattern = _env_pattern(item)
        patterns.append(pattern)
    return tuple(patterns)


def _env_pattern(item: Any) -> str:
    if not isinstance(item, str) or not item or item == "*":
        raise ValueError("env allowlist pattern must be a non-empty string")
    if item.count("*") > 1 or ("*" in item and not item.endswith("*")):
        raise ValueError(f"env allowlist pattern {item!r} must be exact or a trailing *")
    body = item[:-1] if item.endswith("*") else item
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", body):
        raise ValueError(f"env allowlist pattern {item!r} is not a key prefix")
    return item


def _env_key_allowed(key: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            if key.startswith(prefix) and len(key) > len(prefix):
                return True
        elif key == pattern:
            return True
    return False


def _step_dotenv(repo_root: Path, keys: tuple[str, ...]) -> dict[str, str]:
    if not keys:
        return {}
    return _read_dotenv_keys(repo_root / ".env", keys)


def _read_dotenv_keys(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    """Read named KEY=VALUE lines. Values are literal: no shell expansion or command substitution."""
    if not path.is_file():
        raise ValueError("repo .env is missing; env_from_dotenv cannot be loaded")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeError as exc:
        raise ValueError("repo .env is not utf-8") from exc
    wanted = set(keys)
    found: dict[str, str] = {}
    for raw_line in lines:
        name, value = _env_assignment(raw_line)
        if name is None or name not in wanted:
            continue
        if "\x00" in value:
            raise ValueError(f"env value for {name} contains a NUL")
        found[name] = value
    missing = [key for key in keys if not found.get(key)]
    if missing:
        raise ValueError("repo .env is missing keys: " + ", ".join(missing))
    return {key: found[key] for key in keys}


def _env_assignment(raw_line: str) -> tuple[str | None, str]:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None, ""
    match = _ENV_ASSIGNMENT.match(line)
    if match is None:
        return None, ""
    return match.group(1), _literal_env_value(match.group(2))


def _literal_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _child_env(extra: Mapping[str, str]) -> dict[str, str] | None:
    if not extra:
        return None
    merged = os.environ.copy()
    merged.update(extra)
    return merged


def _validate_job_path(value: str) -> None:
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("job paths must not contain control characters")
    path = Path(value).expanduser()
    if not path.is_absolute() and ".." in path.parts:
        raise ValueError(f"relative job path escapes the repository: {value}")


def resolve_job_path(value: str, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (repo_root / path)


class JobPreconditions:
    """Fail-closed host checks evaluated before every step."""

    def __init__(
        self,
        repo_root: Path,
        *,
        gate: ExternalGate | None = None,
        dispatch_lock_dir: Path = DEFAULT_DISPATCH_LOCK_DIR,
        stack_probe: Callable[[], str] | None = None,
        memory_probe: Callable[[], float | None] | None = None,
        disk_probe: Callable[[Path], float | None] | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.gate = gate
        self.dispatch_lock_dir = dispatch_lock_dir
        self.window_claim = dispatch_lock_dir.parent / "state" / WINDOW_CLAIM_NAME
        self.stack_probe = stack_probe or _stack_state
        self.memory_probe = memory_probe or _free_memory_gib
        self.disk_probe = disk_probe or _disk_free_gib

    def check(self, spec: JobSpec, *, quiet_host: bool = True) -> PreconditionResult:
        reasons: list[str] = []
        snapshot: dict[str, Any] = {}
        gate_reason = self.gate.external_reason() if self.gate is not None else None
        snapshot["queue_gate"] = gate_reason or "idle"
        if gate_reason:
            reasons.append(f"queue yield gate: {gate_reason}")
        dispatch_reason = _dispatch_lock_reason(self.dispatch_lock_dir)
        snapshot["dispatch_locks"] = dispatch_reason or "idle"
        if dispatch_reason and quiet_host:
            reasons.append(dispatch_reason)
            self.claim_window(spec.job_id)
        stack = self.stack_probe()
        snapshot["stack"] = stack
        if stack != spec.preconditions.stack:
            reasons.append(f"stack is {stack}; the job requires {spec.preconditions.stack}")
        memory = self.memory_probe()
        snapshot["free_memory_gib"] = memory
        if memory is None:
            reasons.append("free memory is unavailable")
        elif memory < spec.preconditions.free_memory_gib:
            reasons.append(
                f"free memory {memory:.1f} GiB is below the "
                f"{spec.preconditions.free_memory_gib:.1f} GiB floor"
            )
        disk_path = resolve_job_path(
            spec.preconditions.disk_path or str(self.repo_root), self.repo_root
        )
        disk = self.disk_probe(disk_path)
        snapshot["disk_path"] = str(disk_path)
        snapshot["disk_free_gib"] = disk
        if disk is None:
            reasons.append("disk free space is unavailable")
        elif disk < spec.preconditions.disk_free_gib:
            reasons.append(
                f"disk free {disk:.1f} GiB is below the "
                f"{spec.preconditions.disk_free_gib:.1f} GiB floor"
            )
        return PreconditionResult(not reasons, tuple(reasons), snapshot)

    def claim_window(self, job_id: str) -> None:
        """Ask Jarvis Cloud to start no new lanes until this job is done."""
        payload: dict[str, Any] = {"pid": os.getpid(), "job": job_id, "since": _utc_now()}
        started = _ps_field(os.getpid(), "lstart")
        if started:
            payload["started"] = started
        try:
            self.window_claim.parent.mkdir(parents=True, exist_ok=True)
            _write_json(self.window_claim, payload)
        except OSError:
            pass  # best effort: the job still waits fail-closed on the lane locks

    def release_window(self) -> None:
        try:
            claim = json.loads(self.window_claim.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(claim, dict) and _window_claim_is_ours(claim):
            self.window_claim.unlink(missing_ok=True)


class JobRunner:
    """Run one job's steps serially with receipt, resume and memory-trip stops.

    Seat models stay operator-owned, so after a load_plan_models change run
    `portal arm digests refresh` to rewrite ~/.portal5/arm_digests.env.
    """

    def __init__(
        self,
        task_root: Path,
        *,
        repo_root: Path,
        gate: ExternalGate | None = None,
        notices: JobNoticeSink | None = None,
        dispatch_lock_dir: Path = DEFAULT_DISPATCH_LOCK_DIR,
        memory_watch_script: Path | None = None,
        stack_probe: Callable[[], str] | None = None,
        memory_probe: Callable[[], float | None] | None = None,
        disk_probe: Callable[[Path], float | None] | None = None,
        poll_seconds: float = 0.5,
    ) -> None:
        self.task_root = task_root
        self.repo_root = repo_root
        self.notices = notices
        self.poll_seconds = poll_seconds
        self._interrupt_during_adoption = False
        self.memory_watch_script = memory_watch_script or repo_root / "scripts" / (
            "memory_safety_watch.py"
        )
        self.preconditions = JobPreconditions(
            repo_root,
            gate=gate,
            dispatch_lock_dir=dispatch_lock_dir,
            stack_probe=stack_probe,
            memory_probe=memory_probe,
            disk_probe=disk_probe,
        )

    def run(self, spec: JobSpec, *, rerun: str | None = None, force: bool = False) -> JobRun:
        self._interrupt_during_adoption = False
        if rerun is not None and rerun not in {step.step_id for step in spec.steps}:
            raise ValueError(f"unknown step for --rerun: {rerun}")
        if rerun is not None:
            selected = next(step for step in spec.steps if step.step_id == rerun)
            if not selected.idempotent and not force:
                raise ValueError(f"step {rerun} is non-idempotent; pass --force to rerun it")
        if not self.memory_watch_script.is_file():
            raise ValueError(f"memory safety watcher is missing: {self.memory_watch_script}")
        job_dir = self.task_root / spec.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        self._write_spec(job_dir, spec)
        lock = self._acquire_lock(job_dir, spec.job_id)
        try:
            state = self._load_state(job_dir, spec)
            if rerun is not None:
                entry = state["steps"][rerun]
                entry["state"] = "pending"
                entry["reason"] = "operator requested rerun"
            self._save_state(job_dir, state)
            # Hold the window while a remaining step needs a quiet host: a lane started
            # mid-run would load the host under a live campaign. Report-only resumes skip it.
            if any(
                step.quiet_host
                for step in spec.steps
                if state["steps"][step.step_id]["state"] != "done"
            ):
                self.preconditions.claim_window(spec.job_id)
            status, reason = self._run_steps(spec, job_dir, state)
            if status != "WAITING" or "dispatch lane lock" not in str(reason):
                self.preconditions.release_window()
            receipt = self._write_receipt(spec, job_dir, state, status, reason)
            self._notify(spec, status, reason, receipt)
            return JobRun(status, spec.job_id, receipt, reason)
        except KeyboardInterrupt:
            state = self._load_state(job_dir, spec)
            if not self._interrupt_during_adoption:
                for entry in state["steps"].values():
                    if entry["state"] == "running":
                        entry["state"] = "pending"
                        entry["reason"] = "interrupted"
            self._save_state(job_dir, state)
            receipt = self._write_receipt(spec, job_dir, state, "WAITING", "interrupted")
            self._notify(spec, "WAITING", "interrupted", receipt)
            raise
        finally:
            lock.unlink(missing_ok=True)

    def _run_steps(
        self, spec: JobSpec, job_dir: Path, state: dict[str, Any]
    ) -> tuple[str, str | None]:
        started_at = state.get("first_started_at")
        deadline = (
            _utc_timestamp(started_at) + spec.stop_conditions.max_job_minutes * 60
            if started_at and spec.stop_conditions.max_job_minutes
            else None
        )
        for step in spec.steps:
            entry = state["steps"][step.step_id]
            if entry["state"] == "done":
                continue
            if entry["state"] == "interrupted":
                return "BLOCKED", str(entry.get("reason") or f"step {step.step_id} was interrupted")
            if entry["state"] == "running":
                status, reason = self._recover_running_step(spec, step, job_dir, state, entry)
                if status is not None:
                    return status, reason
                continue
            preconditions = self.preconditions.check(spec, quiet_host=step.quiet_host)
            state["last_preconditions"] = preconditions.snapshot
            if not preconditions.ok:
                return "WAITING", preconditions.reasons[0]
            if deadline is not None and time.time() >= deadline:
                return (
                    "STOPPED",
                    f"job exceeded max_job_minutes={spec.stop_conditions.max_job_minutes}",
                )
            if started_at is None:
                started_at = _utc_now()
                state["first_started_at"] = started_at
                if spec.stop_conditions.max_job_minutes:
                    deadline = time.time() + spec.stop_conditions.max_job_minutes * 60
            backups, backup_error = self._backup_checkpoints(spec, step, job_dir, state)
            if backup_error:
                return "BLOCKED", f"checkpoint backup failed for {step.step_id}: {backup_error}"
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            entry["state"] = "running"
            entry["started_at"] = _utc_now()
            self._save_state(job_dir, state)
            result = self._execute_step(spec, step, job_dir, entry, backups, deadline)
            status, reason = self._complete_step(spec, job_dir, state, entry, result)
            if status is not None:
                return status, reason
        if any(entry["state"] == "failed" for entry in state["steps"].values()):
            return "BLOCKED", "one or more steps failed"
        return "PASS", None

    def _recover_running_step(
        self,
        spec: JobSpec,
        step: JobStep,
        job_dir: Path,
        state: dict[str, Any],
        entry: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        result = self._adopt_step(spec, step, job_dir, state, entry)
        return self._complete_step(spec, job_dir, state, entry, result)

    def _complete_step(
        self,
        spec: JobSpec,
        job_dir: Path,
        state: dict[str, Any],
        entry: dict[str, Any],
        result: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        entry["history"] = [*entry.get("history", []), result][-5:]
        entry["state"] = result["state"]
        entry["exit_code"] = result["exit_code"]
        entry["finished_at"] = result["finished_at"]
        entry["reason"] = result["reason"]
        self._save_state(job_dir, state)
        if result["state"] == "interrupted":
            return "BLOCKED", str(result["reason"])
        if result["state"] == "failed" and spec.stop_conditions.on_failure == "continue":
            return None, None
        if result["state"] in {"failed", "stopped"}:
            status = "STOPPED" if result["state"] == "stopped" else "BLOCKED"
            return status, str(result["reason"])
        return None, None

    def _adopt_step(
        self,
        spec: JobSpec,
        step: JobStep,
        job_dir: Path,
        state: dict[str, Any],
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        logs = job_dir / "logs"
        attempt = int(entry.get("attempts", 0))
        pid_file = logs / f"{step.step_id}.{attempt:02d}.pid"
        started_wall = str(entry.get("started_at") or _utc_now())
        pid, started_identity = _read_step_identity(pid_file)
        if started_identity is None:
            started_identity = _legacy_step_identity(pid, step, started_wall)
        backups = self._adopted_checkpoints(spec, step, state)
        if not isinstance(started_identity, str) or not _process_matches(pid, started_identity):
            started = _utc_timestamp(started_wall)
            return self._step_result(
                step,
                started_wall,
                time.monotonic() - max(0.0, time.time() - started),
                backups,
                "interrupted",
                None,
                0,
                logs / f"{step.step_id}.{attempt:02d}.stdout.log",
                logs / f"{step.step_id}.{attempt:02d}.stderr.log",
                "step child is not alive with its recorded PID and start time",
                None,
                False,
            )
        stdout_path = logs / f"{step.step_id}.{attempt:02d}.stdout.log"
        stderr_path = logs / f"{step.step_id}.{attempt:02d}.stderr.log"
        watch_log = logs / f"{step.step_id}.{attempt:02d}.watch.log"
        exit_code, timed_out, peak = self._wait_for_adopted_step(
            pid, started_identity, step, started_wall
        )
        memory_trip = _memory_trip_after_exit(None, watch_log, 0)
        marker = _marker_hit(spec.stop_conditions.output_markers, stdout_path, stderr_path)
        signal = _StepSignal(memory_trip=memory_trip, marker=marker, peak=peak, timed_out=timed_out)
        result_state, reason = _step_outcome(spec, step, signal, exit_code)
        if exit_code is None and result_state == "failed" and not timed_out:
            result_state, reason = "done", "exit unknown"
        started = _utc_timestamp(started_wall)
        result = self._step_result(
            step,
            started_wall,
            time.monotonic() - max(0.0, time.time() - started),
            backups,
            result_state,
            exit_code,
            peak,
            stdout_path,
            stderr_path,
            reason,
            memory_trip,
            timed_out,
        )
        return self._redact_adopted_result(result, step)

    def _adopted_checkpoints(
        self, spec: JobSpec, step: JobStep, state: dict[str, Any]
    ) -> list[dict[str, Any]]:
        checkpoints = state.get("checkpoint_index", {})
        paths = _dedupe_strings((*spec.checkpoints, *step.checkpoints))
        return [
            dict(checkpoints[str(resolve_job_path(path, self.repo_root))])
            for path in paths
            if str(resolve_job_path(path, self.repo_root)) in checkpoints
        ]

    def _wait_for_adopted_step(
        self, pid: int, started_identity: str, step: JobStep, started_wall: str
    ) -> tuple[int | None, bool, int]:
        deadline = _utc_timestamp(started_wall) + step.timeout_seconds + 1
        peak = 0
        timed_out = False
        try:
            while _process_matches(pid, started_identity):
                if time.time() >= deadline:
                    timed_out = True
                    self._terminate_adopted_step(pid, started_identity)
                    break
                peak = max(peak, _group_rss(pid) or 0)
                time.sleep(max(self.poll_seconds, 0.5))
        except KeyboardInterrupt:
            self._interrupt_during_adoption = True
            raise
        details = _ps_process_details(pid)
        exit_code = (
            _adopted_exit_code(pid)
            if details is not None and details[0] == started_identity and details[1].startswith("Z")
            else None
        )
        return exit_code, timed_out, peak

    def _terminate_adopted_step(self, pid: int, started_identity: str) -> None:
        if not _process_matches(pid, started_identity):
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _process_matches(pid, started_identity):
            time.sleep(0.1)
        if _process_matches(pid, started_identity):
            with suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)

    def _redact_adopted_result(self, result: dict[str, Any], step: JobStep) -> dict[str, Any]:
        try:
            extra_env = _step_dotenv(self.repo_root, step.env_from_dotenv)
        except ValueError:
            if step.env_from_dotenv:
                result["stdout_tail"] = ""
                result["stderr_tail"] = ""
            return result
        result["stdout_tail"] = _redact_text(str(result["stdout_tail"]), extra_env.values())
        result["stderr_tail"] = _redact_text(str(result["stderr_tail"]), extra_env.values())
        return result

    def _execute_step(
        self,
        spec: JobSpec,
        step: JobStep,
        job_dir: Path,
        entry: dict[str, Any],
        backups: list[dict[str, Any]],
        deadline: float | None,
    ) -> dict[str, Any]:
        logs = job_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        attempt = int(entry["attempts"])
        stdout_path = logs / f"{step.step_id}.{attempt:02d}.stdout.log"
        stderr_path = logs / f"{step.step_id}.{attempt:02d}.stderr.log"
        watch_log = logs / f"{step.step_id}.{attempt:02d}.watch.log"
        started_wall = _utc_now()
        started = time.monotonic()
        try:
            extra_env = _step_dotenv(self.repo_root, step.env_from_dotenv)
        except ValueError as exc:
            return self._step_result(
                step,
                started_wall,
                started,
                backups,
                "failed",
                None,
                0,
                stdout_path,
                stderr_path,
                str(exc),
                None,
                False,
            )
        signal, exit_code, error = self._run_process(
            spec,
            step,
            logs,
            attempt,
            stdout_path,
            stderr_path,
            watch_log,
            started,
            deadline,
            extra_env,
        )
        _redact_file(stdout_path, extra_env.values())
        _redact_file(stderr_path, extra_env.values())
        state, reason = _step_outcome(spec, step, signal, exit_code)
        if error:
            state, reason = "failed", _redact_text(error, extra_env.values())
        elif reason:
            reason = _redact_text(reason, extra_env.values())
        result = self._step_result(
            step,
            started_wall,
            started,
            backups,
            state,
            exit_code,
            signal.peak,
            stdout_path,
            stderr_path,
            reason,
            signal.memory_trip,
            signal.timed_out,
        )
        result["stdout_tail"] = _redact_text(str(result["stdout_tail"]), extra_env.values())
        result["stderr_tail"] = _redact_text(str(result["stderr_tail"]), extra_env.values())
        return result

    def _run_process(
        self,
        spec: JobSpec,
        step: JobStep,
        logs: Path,
        attempt: int,
        stdout_path: Path,
        stderr_path: Path,
        watch_log: Path,
        started: float,
        deadline: float | None,
        extra_env: Mapping[str, str],
    ) -> tuple[_StepSignal, int | None, str | None]:
        process: subprocess.Popen[bytes] | None = None
        watcher: subprocess.Popen[bytes] | None = None
        signal = _StepSignal()
        watch_offset = _file_size(watch_log)
        try:
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                process = subprocess.Popen(
                    list(step.argv),
                    cwd=self.repo_root,
                    env=_child_env(extra_env),
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                pid_file = logs / f"{step.step_id}.{attempt:02d}.pid"
                pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
                started_identity = _ps_field(process.pid, "lstart")
                if started_identity:
                    pid_file.with_name(pid_file.name + ".meta").write_text(
                        json.dumps({"pid": process.pid, "started": started_identity}) + "\n",
                        encoding="utf-8",
                    )
                watcher = self._start_watch(pid_file, watch_log)
                signal = self._poll_process(
                    spec,
                    step,
                    process,
                    watcher,
                    stdout_path,
                    stderr_path,
                    watch_log,
                    started,
                    deadline,
                )
                exit_code = process.wait()
                if signal.memory_trip is None:
                    signal.memory_trip = _memory_trip_after_exit(watcher, watch_log, watch_offset)
                return signal, exit_code, None
        except OSError as exc:
            return signal, None, f"could not start step: {type(exc).__name__}: {exc}"
        finally:
            if process is not None and process.poll() is None:
                self._terminate(process)
            self._stop_watch(watcher)

    def _poll_process(
        self,
        spec: JobSpec,
        step: JobStep,
        process: subprocess.Popen[bytes],
        watcher: subprocess.Popen[bytes] | None,
        stdout_path: Path,
        stderr_path: Path,
        watch_log: Path,
        started: float,
        deadline: float | None,
    ) -> _StepSignal:
        signal = _StepSignal()
        next_sample = 0.0
        while process.poll() is None:
            now = time.monotonic()
            if watcher is not None and watcher.poll() == 2:
                signal.memory_trip = {"reason": _trip_reason(watch_log)}
                self._terminate(process)
                break
            if now - started >= step.timeout_seconds:
                signal.timed_out = True
                self._terminate(process)
                break
            if deadline is not None and time.time() >= deadline:
                signal.job_limit = True
                self._terminate(process)
                break
            signal.marker = _marker_hit(
                spec.stop_conditions.output_markers, stdout_path, stderr_path
            )
            if signal.marker is not None:
                self._terminate(process)
                break
            if now >= next_sample:
                rss = _group_rss(process.pid)
                signal.peak = max(signal.peak, rss or 0)
                next_sample = now + _PEAK_SAMPLE_SECONDS
            time.sleep(self.poll_seconds)
        return signal

    def _step_result(
        self,
        step: JobStep,
        started_wall: str,
        started: float,
        backups: list[dict[str, Any]],
        state: str,
        exit_code: int | None,
        peak: int,
        stdout_path: Path,
        stderr_path: Path,
        reason: str | None,
        memory_trip: dict[str, Any] | None,
        timed_out: bool,
    ) -> dict[str, Any]:
        return {
            "argv": list(step.argv),
            "state": state,
            "exit_code": exit_code,
            "started_at": started_wall,
            "finished_at": _utc_now(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "peak_footprint_bytes": peak or None,
            "stdout_tail": _tail(stdout_path),
            "stderr_tail": _tail(stderr_path),
            "timed_out": timed_out,
            "reason": reason,
            "memory_trip": memory_trip,
            "checkpoint_backups": backups,
            "outputs": [
                _describe_path(resolve_job_path(item, self.repo_root)) for item in step.outputs
            ],
        }

    def _backup_checkpoints(
        self, spec: JobSpec, step: JobStep, job_dir: Path, state: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str | None]:
        backups: list[dict[str, Any]] = []
        index = state.setdefault("checkpoint_index", {})
        for raw in _dedupe_strings((*spec.checkpoints, *step.checkpoints)):
            source = resolve_job_path(raw, self.repo_root)
            record: dict[str, Any] = {"path": str(source), "backed_up": False}
            if not source.exists():
                record["reason"] = "checkpoint does not exist yet"
                backups.append(record)
                continue
            if not source.is_file():
                record["reason"] = "checkpoint is not a regular file"
                backups.append(record)
                return backups, f"{source} is not a regular file"
            try:
                stat = source.stat()
            except OSError as exc:
                record["reason"] = f"{type(exc).__name__}: {exc}"
                backups.append(record)
                return backups, str(exc)
            signature = f"{stat.st_mtime_ns}:{stat.st_size}"
            previous = index.get(str(source))
            if (
                previous
                and previous.get("signature") == signature
                and Path(str(previous.get("backup"))).is_file()
            ):
                record.update({**previous, "backed_up": True, "reused": True})
                backups.append(record)
                continue
            target_dir = job_dir / "checkpoints" / step.step_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            if target.exists():
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                target = target_dir / f"{source.name}.{stamp}"
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                record["reason"] = f"{type(exc).__name__}: {exc}"
                backups.append(record)
                return backups, str(exc)
            record.update(
                {
                    "backed_up": True,
                    "backup": str(target),
                    "bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                    "signature": signature,
                }
            )
            index[str(source)] = record
            backups.append(record)
        return backups, None

    def _start_watch(self, pid_file: Path, log: Path) -> subprocess.Popen[bytes] | None:
        return subprocess.Popen(
            [
                sys.executable,
                str(self.memory_watch_script),
                "--pid-file",
                str(pid_file),
                "--log",
                str(log),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def _stop_watch(watcher: subprocess.Popen[bytes] | None) -> None:
        if watcher is None or watcher.poll() is not None:
            return
        watcher.terminate()
        try:
            watcher.wait(timeout=2)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait()

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()

    def _write_receipt(
        self,
        spec: JobSpec,
        job_dir: Path,
        state: dict[str, Any],
        status: str,
        reason: str | None,
    ) -> Path:
        steps = _receipt_steps(spec, state)
        job_outputs = [
            _describe_path(resolve_job_path(item, self.repo_root)) for item in spec.outputs
        ]
        outputs = _dedupe_by_path(
            [*job_outputs, *(item for step in steps for item in step["outputs"])]
        )
        checkpoints = _dedupe_by_path(item for step in steps for item in step["checkpoint_backups"])
        failures = [
            {"step": step["id"], "reason": step["reason"]}
            for step in steps
            if step["state"] in {"failed", "stopped", "interrupted"}
        ]
        memory_trips = [
            {"step": step["id"], **step["memory_trip"]} for step in steps if step["memory_trip"]
        ]
        receipt = {
            "head": _head_sha(self.repo_root),
            "utc": _utc_now(),
            "workdir": str(job_dir.resolve()),
            "job_id": spec.job_id,
            "purpose": spec.purpose,
            "status": status,
            "reason": reason,
            "report": _report(
                spec,
                status,
                steps,
                outputs,
                checkpoints,
                failures,
                memory_trips,
            ),
            "preconditions": state.get("last_preconditions"),
            "steps": steps,
            "outputs": outputs,
            "checkpoints": checkpoints,
            "totals": {
                "duration_seconds": round(sum(step["duration_seconds"] or 0 for step in steps), 3),
                "peak_footprint_bytes": max(
                    (step["peak_footprint_bytes"] or 0 for step in steps), default=0
                )
                or None,
            },
        }
        path = job_dir / "receipt.json"
        _write_json(path, receipt)
        return path

    def _notify(self, spec: JobSpec, status: str, reason: str | None, receipt: Path) -> None:
        if self.notices is None or status == "WAITING":
            return
        completed = 0
        with suppress(OSError, ValueError, TypeError):
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            completed = sum(step["state"] == "done" for step in payload.get("steps", []))
        detail = {
            "purpose": spec.purpose,
            "reason": reason,
            "steps": f"{completed}/{len(spec.steps)} done",
            "duration_seconds": _receipt_duration(receipt),
            "receipt": str(receipt),
        }
        try:
            self.notices.job_finished(spec.job_id, status, detail)
        except Exception:  # noqa: BLE001 - a notice must never hide the receipt
            return

    def _write_spec(self, job_dir: Path, spec: JobSpec) -> None:
        path = job_dir / "job.json"
        payload = json.dumps(spec.as_dict(), sort_keys=True, indent=2) + "\n"
        if path.is_file() and path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"job directory {spec.job_id} already holds a different spec")
        if not path.is_file():
            path.write_text(payload, encoding="utf-8")

    @staticmethod
    def _acquire_lock(job_dir: Path, job_id: str) -> Path:
        lock = job_dir / "run.lock"
        pid, started = _read_run_lock(lock)
        if _foreign_lock_held(pid, started):
            raise RuntimeError(f"job {job_id} is already running (pid {pid})")
        _write_run_lock(lock)
        return lock

    @staticmethod
    def _load_state(job_dir: Path, spec: JobSpec) -> dict[str, Any]:
        path = job_dir / "job_state.json"
        if path.is_file():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"job state is unreadable: {exc}") from exc
            if not isinstance(state, dict) or state.get("job_id") != spec.job_id:
                raise ValueError("job state does not belong to this job id")
            state["run_count"] = int(state.get("run_count", 0)) + 1
        else:
            state = {
                "job_id": spec.job_id,
                "created_at": _utc_now(),
                "run_count": 1,
                "first_started_at": None,
                "steps": {},
            }
        steps = state.setdefault("steps", {})
        for step in spec.steps:
            steps.setdefault(
                step.step_id,
                {"state": "pending", "attempts": 0, "history": []},
            )
        state["updated_at"] = _utc_now()
        return state

    @staticmethod
    def _save_state(job_dir: Path, state: dict[str, Any]) -> None:
        state["updated_at"] = _utc_now()
        _write_json(job_dir / "job_state.json", state)


def _step_outcome(
    spec: JobSpec, step: JobStep, signal: _StepSignal, exit_code: int | None
) -> tuple[str, str | None]:
    if signal.memory_trip is not None:
        return "stopped", f"memory safety trip: {signal.memory_trip['reason']}"
    if signal.job_limit:
        return "stopped", f"job exceeded max_job_minutes={spec.stop_conditions.max_job_minutes}"
    if signal.timed_out:
        return "failed", f"step timed out after {step.timeout_seconds}s"
    if signal.marker is not None:
        return "stopped", f"output matched stop marker {signal.marker!r}"
    if exit_code != 0:
        return "failed", f"step exited {exit_code}"
    return "done", None


def _receipt_steps(spec: JobSpec, state: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for step in spec.steps:
        entry = state["steps"][step.step_id]
        last = entry["history"][-1] if entry.get("history") else {}
        out.append(
            {
                "id": step.step_id,
                "argv": list(step.argv),
                "state": entry["state"],
                "attempts": entry.get("attempts", 0),
                "exit_code": last.get("exit_code"),
                "duration_seconds": last.get("duration_seconds"),
                "peak_footprint_bytes": last.get("peak_footprint_bytes"),
                "stdout_tail": last.get("stdout_tail", ""),
                "stderr_tail": last.get("stderr_tail", ""),
                "timed_out": bool(last.get("timed_out")),
                "reason": last.get("reason") or entry.get("reason"),
                "memory_trip": last.get("memory_trip"),
                "checkpoint_backups": last.get("checkpoint_backups", []),
                "outputs": last.get("outputs", []),
            }
        )
    return out


def _report(
    spec: JobSpec,
    status: str,
    steps: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    checkpoints: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    memory_trips: list[dict[str, Any]],
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "status": status,
        "purpose": spec.purpose,
        "steps": [
            {
                "id": step["id"],
                "state": step["state"],
                "exit_code": step["exit_code"],
                "duration_seconds": step["duration_seconds"],
            }
            for step in steps
        ],
        "outputs": outputs,
        "checkpoints": checkpoints,
        "failures": failures,
        "memory": {
            "trips": memory_trips,
            "peak_footprint_bytes": max(
                (step["peak_footprint_bytes"] or 0 for step in steps), default=0
            )
            or None,
        },
        "duration": {"seconds": round(sum(step["duration_seconds"] or 0 for step in steps), 3)},
        "resume": {
            "completed": [step["id"] for step in steps if step["state"] == "done"],
            "incomplete": [step["id"] for step in steps if step["state"] != "done"],
        },
    }
    return {field: fields[field] for field in spec.report_fields}


def _dispatch_lock_reason(lock_dir: Path) -> str | None:
    try:
        locks = sorted(path for path in lock_dir.glob("*.lock") if path.is_file())
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"cannot inspect dispatch lane locks: {exc}"
    for lock in locks:
        try:
            value = lock.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return f"cannot read dispatch lane lock {lock.name}: {exc}"
        try:
            pid = int(value)
        except ValueError:
            return f"dispatch lane lock {lock.name} is unverifiable"
        if pid > 1 and _pid_alive(pid):
            return f"dispatch lane lock {lock.name} is active (pid {pid})"
    return None


def _stack_state() -> str:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode:
        return "unknown"
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return "up" if "portal5-pipeline" in names else "down"


def _free_memory_gib() -> float | None:
    if sys.platform == "darwin":
        return _darwin_free_memory_gib()
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^MemAvailable:\s*(\d+)\s*kB", text, re.MULTILINE)
    return round(int(match.group(1)) / 1024**2, 2) if match else None


def _darwin_free_memory_gib() -> float | None:
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    page_size = re.search(r"page size of (\d+) bytes", result.stdout, re.I)
    pages = {}
    for label in ("Pages free", "Pages inactive"):
        match = re.search(rf"{re.escape(label)}:\s*(\d+)", result.stdout)
        if match:
            pages[label] = int(match.group(1))
    if len(pages) != 2:
        return None
    size = int(page_size.group(1)) if page_size else 16384
    return round(sum(pages.values()) * size / 1024**3, 2)


def _disk_free_gib(path: Path) -> float | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return round(shutil.disk_usage(probe).free / 1024**3, 2)
    except OSError:
        return None


def _group_rss(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-g", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    total = sum(int(value) for value in result.stdout.split() if value.isdigit())
    return total * 1024 if total else None


def _marker_hit(markers: tuple[str, ...], *paths: Path) -> str | None:
    if not markers:
        return None
    text = "\n".join(_tail(path, _TAIL_BYTES) for path in paths)
    return next((marker for marker in markers if marker in text), None)


def _trip_reason(log: Path) -> str:
    for line in reversed(_tail(log, _TAIL_BYTES).splitlines()):
        if "MEMORY SAFETY TRIP" in line:
            return line.strip()
    return "memory safety watcher tripped"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _memory_trip_after_exit(
    watcher: subprocess.Popen[bytes] | None, watch_log: Path, offset: int
) -> dict[str, Any] | None:
    """Exit 2 still counts; a TRIP line written this attempt counts even if the watcher lags."""
    if _watcher_reported_trip(watcher):
        return {"reason": _trip_reason(watch_log)}
    line = _trip_line_since(watch_log, offset)
    if line:
        return {"reason": line}
    return None


def _watcher_reported_trip(watcher: subprocess.Popen[bytes] | None) -> bool:
    if watcher is None:
        return False
    if watcher.poll() is None:
        with suppress(subprocess.TimeoutExpired):
            watcher.wait(timeout=0.3)
    return watcher.poll() == 2


def _trip_line_since(log: Path, offset: int) -> str | None:
    try:
        size = log.stat().st_size
        with log.open("rb") as handle:
            start = max(0, offset, size - (_TAIL_BYTES * 8))
            handle.seek(start)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        if "MEMORY SAFETY TRIP" in line and line.strip():
            return line.strip()
    return None


def _redact_text(text: str, secrets: Iterable[str]) -> str:
    if not text:
        return text
    for secret in _file_secrets(secrets):
        text = text.replace(secret, _REDACTED)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        text = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(secret)}(?![A-Za-z0-9])",
            _REDACTED,
            text,
        )
    return text


def _file_secrets(secrets: Iterable[str]) -> list[str]:
    chosen = [
        item
        for item in dict.fromkeys(secrets)
        if item and (len(item) >= _FILE_REDACT_MIN or any(not char.isalnum() for char in item))
    ]
    return sorted(chosen, key=len, reverse=True)


def _redact_file(path: Path, secrets: Iterable[str], *, chunk_size: int = 1024 * 1024) -> None:
    needles = [item.encode("utf-8") for item in _file_secrets(secrets)]
    if not needles or not path.is_file():
        return
    tmp = path.with_name(path.name + ".redacting")
    changed = False
    try:
        with path.open("rb") as src, tmp.open("wb") as dst:
            buf = b""
            while True:
                chunk = src.read(chunk_size)
                buf += chunk
                width = max(len(needle) for needle in needles)
                if chunk and len(buf) < width:
                    continue
                head, buf = _emit_cut(buf, needles, at_eof=not chunk)
                rewritten = _replace_needles(head, needles)
                changed = changed or rewritten != head
                dst.write(rewritten)
                if not chunk:
                    break
        if changed:
            tmp.replace(path)
        else:
            tmp.unlink()
    except OSError:
        tmp.unlink(missing_ok=True)


def _emit_cut(buf: bytes, needles: list[bytes], *, at_eof: bool) -> tuple[bytes, bytes]:
    if at_eof or not needles:
        return buf, b""
    width = max(len(needle) for needle in needles)
    if width == 1:
        return buf, b""
    cut = max(0, len(buf) - (width - 1))
    while cut > 0:
        pull = max(_prefix_suffix_len(buf[:cut], needle) for needle in needles)
        if pull == 0:
            break
        cut -= pull
    if cut == 0 and len(buf) > _LOG_REDACT_LIMIT:
        cut = len(buf) - (width - 1)
    return buf[:cut], buf[cut:]


def _prefix_suffix_len(data: bytes, needle: bytes) -> int:
    limit = min(len(data), len(needle) - 1)
    for size in range(limit, 0, -1):
        if needle.startswith(data[-size:]):
            return size
    return 0


def _replace_needles(data: bytes, needles: list[bytes]) -> bytes:
    for needle in needles:
        data = data.replace(needle, _REDACTED.encode("utf-8"))
    return data


def _tail(path: Path, limit: int = _TAIL_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _describe_path(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "exists": False}
    try:
        if path.is_file():
            record.update(
                {
                    "exists": True,
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        elif path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
            manifest = "\n".join(
                f"{item.relative_to(path).as_posix()}:{_sha256(item)}" for item in files
            )
            record.update(
                {
                    "exists": True,
                    "kind": "directory",
                    "files": len(files),
                    "bytes": sum(item.stat().st_size for item in files),
                    "sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
                }
            )
    except OSError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _dedupe_strings(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_by_path(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        seen.setdefault(str(item["path"]), item)
    return list(seen.values())


def _receipt_duration(receipt: Path) -> float:
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        return float(payload.get("totals", {}).get("duration_seconds", 0))
    except (OSError, ValueError, TypeError):
        return 0.0


def _head_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _process_matches(pid: int, started: str) -> bool:
    if pid <= 1 or not _pid_alive(pid):
        return False
    details = _ps_process_details(pid)
    return details is not None and details[0] == started and not details[1].startswith("Z")


def _read_step_identity(pid_file: Path) -> tuple[int, str | None]:
    meta_file = pid_file.with_name(pid_file.name + ".meta")
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0, None
    try:
        identity = json.loads(meta_file.read_text(encoding="utf-8"))
        started = identity["started"]
        if int(identity["pid"]) != pid or not isinstance(started, str):
            return pid, None
    except (OSError, ValueError, KeyError, TypeError):
        return pid, None
    return pid, started


def _legacy_step_identity(pid: int, step: JobStep, started_wall: str) -> str | None:
    details = _ps_process_details(pid)
    if pid <= 1 or details is None or details[1].startswith("Z"):
        return None
    try:
        process_started = datetime.strptime(details[0], "%a %b %d %H:%M:%S %Y").timestamp()
    except ValueError:
        return None
    if not 0 <= process_started - _utc_timestamp(started_wall) <= 5:
        return None
    target = (
        step.argv[4]
        if step.argv[0] == "uv" and step.argv[3] == "-m"
        else (step.argv[3] if step.argv[0] == "uv" else step.argv[0])
    )
    command = _ps_field(pid, "command")
    return details[0] if command and target in command else None


def _ps_process_details(pid: int) -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "lstart=,stat="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().rsplit(None, 1)
    if len(fields) != 2:
        return None
    return fields[0], fields[1]


def _adopted_exit_code(pid: int) -> int | None:
    try:
        waited, status = os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return None
    return os.waitstatus_to_exitcode(status) if waited == pid else None


def _read_run_lock(lock: Path) -> tuple[int, str | None]:
    """Return ``(pid, started)``. ``started is None`` is a legacy bare-pid lock."""
    try:
        text = lock.read_text(encoding="utf-8").strip()
    except OSError:
        return 0, None
    if text.isdigit():
        return int(text), None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return 0, None
    if not isinstance(payload, dict):
        return 0, None
    try:
        pid = int(payload["pid"])
    except (KeyError, TypeError, ValueError):
        return 0, None
    started = payload.get("started")
    if not isinstance(started, str) or not started.strip():
        return pid, None
    return pid, started.strip()


def _write_run_lock(lock: Path) -> None:
    started = _ps_field(os.getpid(), "lstart")
    if started:
        text = json.dumps({"pid": os.getpid(), "started": started}) + "\n"
    else:
        text = f"{os.getpid()}\n"
    lock.write_text(text, encoding="utf-8")


def _foreign_lock_held(pid: int, started: str | None) -> bool:
    """True when this lock still belongs to another live process, not a reused PID."""
    if pid <= 1 or pid == os.getpid() or not _pid_alive(pid):
        return False
    if started is None:
        command = _ps_field(pid, "command")
        # Unreadable command is not proof the pid was reused.
        return command is None or "portal arm" in command
    live = _ps_field(pid, "lstart")
    return live is None or live == started


def _window_claim_is_ours(claim: dict[str, Any]) -> bool:
    if claim.get("pid") != os.getpid():
        return False
    started = claim.get("started")
    if not isinstance(started, str) or not started.strip():
        return True
    live = _ps_field(os.getpid(), "lstart")
    return live is None or live == started.strip()


def _ps_field(pid: int, field: str) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", f"{field}="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_timestamp(value: str) -> float:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return time.time()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)
