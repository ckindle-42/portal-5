"""Cloud-lane escalation for a blocked Jarvis Local job.

The queue calls this only when ``queue.escalation.enabled`` is true. Attempts 1 and 2
use ``dispatch.py run --tier auto``; attempt 3 uses ``--tier escalate``. Nothing here
starts the live stack or pushes git.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from portal.modules.orchestration.jobs import JobSpec, job_json, parse_job_spec
from portal.modules.orchestration.queue import QueueLedger, QueueRun

_CANARY_SETUP = re.compile(r"^CANARY\s+\S+:\s+SETUP\b", re.MULTILINE)
_SECURITY_KIND = re.compile(r"\b(security|compliance|detection)\b", re.IGNORECASE)
_PATH_RE = re.compile(r"(?:[\w.+-]+/)+[\w.+-]+\.[\w.+-]+")
_AUTO_PREFIXES = ("tests/wfe/", "tests/wfe/plans/", "config/arm_jobs/", "coding_task/")
_GATE_COMMANDS = (
    ["uv", "run", "pytest", "tests/unit", "tests/wfe/tests", "-q"],
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
)
_GIT_ENV_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
)
ROUTED_ATTEMPTS = 2
MAX_ATTEMPTS = 3
TAIL_LINES = 60
GATE_TIMEOUT_S = 7200
DEFAULT_DISPATCH = Path.home() / ".claude" / "orchestrate" / "bin" / "dispatch.py"

GateRunner = Callable[[Sequence[str], Path], int]
CanaryRunner = Callable[[Sequence[str], Path, float], int]


class LaneDispatcher(Protocol):
    def run(self, *, role: str, tier: str, kind: str, brief: Path, repo: Path) -> LaneResult: ...


@dataclass(frozen=True)
class LaneChanges:
    committed: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]

    def paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.committed, *self.unstaged, *self.untracked]))


@dataclass(frozen=True)
class LaneResult:
    lane_id: str
    tier: str
    exit_code: int
    result_text: str
    branch: str
    worktree: Path | None
    changes: LaneChanges


@dataclass(frozen=True)
class _Decision:
    status: str
    detail: str


def escalation_enabled(policy: object) -> bool:
    """True only for the explicit boolean the operator sets under queue.escalation."""
    if not isinstance(policy, dict):
        return False
    block = policy.get("escalation")
    if not isinstance(block, dict):
        return False
    return block.get("enabled") is True


def classify_block(receipt: dict[str, Any], queue_reason: str | None = None) -> str | None:
    """Why a finished job should ask a cloud lane, or None when it should not."""
    status = str(receipt.get("status") or "")
    reason = str(receipt.get("reason") or receipt.get("error") or queue_reason or "")
    if _cancelled(status, reason):
        return None
    if _memory_trip(receipt, reason):
        return "memory_trip"
    text = _output_text(receipt)
    if _CANARY_SETUP.search(text):
        return "canary_setup"
    if "HARNESS_ERROR" in text or "HARNESS_ERROR" in reason:
        return "harness_error"
    if _failed_step(receipt):
        return "step_failure"
    if receipt.get("error") and not receipt.get("steps"):
        return "harness_error"
    lower = reason.lower()
    if "step exited" in lower or "step timed out" in lower or "timed out after" in lower:
        return "step_failure"
    return None


def dispatch_kind(raw: dict[str, Any]) -> str:
    """Security, compliance and detection jobs stay off cloud free gateways."""
    parts = [str(raw.get("id") or ""), str(raw.get("purpose") or "")]
    for step in raw.get("steps") or []:
        if isinstance(step, dict):
            parts.append(str(step.get("id") or ""))
    if _SECURITY_KIND.search(" ".join(parts)):
        return "security"
    return "code"


def lane_role(job_id: str, attempt: int) -> str:
    return f"esc-{_safe(job_id)}-{attempt}"


def build_escalator(
    tasks_dir: Path,
    repo_root: Path,
    notices: object,
    policy: object,
) -> Callable[[dict[str, Any], QueueRun], str] | None:
    """The queue hook, or None while the operator has left the flag off."""
    if not escalation_enabled(policy):
        return None
    return Escalator(tasks_dir, repo_root=repo_root, notices=notices).handle


class EscalationLedger:
    """One sqlite row per escalation step, beside the queue ledger."""

    def __init__(self, tasks_dir: Path) -> None:
        tasks_dir.mkdir(parents=True, exist_ok=True)
        self.path = tasks_dir / "escalation.sqlite3"

    def add(
        self,
        job_id: str,
        attempt: int,
        lane_id: str,
        event: str,
        detail: dict[str, Any],
    ) -> None:
        import sqlite3

        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS escalation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    lane_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "INSERT INTO escalation "
                "(job_id, attempt, lane_id, event, detail_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, attempt, lane_id, event, json.dumps(detail, sort_keys=True), _utc()),
            )

    def events(self, job_id: str) -> list[dict[str, Any]]:
        import sqlite3

        if not self.path.is_file():
            return []
        with sqlite3.connect(self.path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT attempt, lane_id, event, detail_json, created_at "
                "FROM escalation WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class ProcessDispatcher:
    """Run dispatch.py and poll its process until it exits or the bound hits."""

    def __init__(
        self,
        binary: Path | None = None,
        timeout_s: float = 3600,
        poll_s: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.binary = binary or DEFAULT_DISPATCH
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.sleeper = sleeper

    def run(self, *, role: str, tier: str, kind: str, brief: Path, repo: Path) -> LaneResult:
        if not self.binary.is_file():
            return _empty_lane(role, tier, 127, f"dispatch binary missing: {self.binary}")
        argv = [
            sys.executable,
            str(self.binary),
            "--repo",
            str(repo),
            "run",
            "--role",
            role,
            "--tier",
            tier,
            "--kind",
            kind,
            "--brief",
            str(brief.relative_to(repo) if brief.is_relative_to(repo) else brief),
            "--new",
            "--timeout",
            str(int(self.timeout_s)),
        ]
        output, code = _run_bounded(argv, self.timeout_s, self.poll_s, self.sleeper)
        text = output if "## RESULT" in output else _latest_log(role) or output
        worktree = _lane_worktree(repo, role)
        changes = inspect_changes(worktree, repo) if (worktree / ".git").exists() else _no_changes()
        return LaneResult(role, tier, code, text, f"lane/{_safe(role)}", worktree, changes)


class Escalator:
    """One blocked job: up to two routed attempts, then one escalated attempt."""

    def __init__(
        self,
        tasks_dir: Path,
        *,
        repo_root: Path,
        notices: object = None,
        dispatcher: LaneDispatcher | None = None,
        gate_runner: GateRunner | None = None,
        canary_runner: CanaryRunner | None = None,
        main_root: Path | None = None,
    ) -> None:
        self.tasks_dir = tasks_dir
        self.repo_root = repo_root
        self.notices = notices
        self.dispatcher = dispatcher or ProcessDispatcher()
        self.gate_runner = gate_runner or _subprocess_gate
        self.canary_runner = canary_runner or _subprocess_canary
        self.main = main_root or main_checkout(repo_root)
        self.ledger = EscalationLedger(tasks_dir)

    def handle(self, item: dict[str, Any], result: QueueRun) -> str:
        receipt = _load_receipt(result.receipt_path)
        if not receipt:
            receipt = {"status": "BLOCKED", "reason": result.reason or ""}
        trigger = classify_block(receipt, result.reason)
        if trigger is None or item.get("kind", "job") != "job":
            return "skipped"
        raw = json.loads(str(item["plan_json"]))
        if not isinstance(raw, dict):
            return "skipped"
        source = Path(str(item.get("source_dir") or self.repo_root))
        return self._attempts(str(item["task_id"]), raw, source, receipt, result, trigger)

    def _attempts(
        self,
        job_id: str,
        raw: dict[str, Any],
        source: Path,
        receipt: dict[str, Any],
        result: QueueRun,
        trigger: str,
    ) -> str:
        prior = ""
        lanes: list[str] = []
        kind = dispatch_kind(raw)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            outcome, prior, role = self._one(
                attempt, job_id, raw, source, receipt, result, trigger, kind, prior
            )
            lanes.append(role)
            if outcome in {"merged", "held"}:
                return outcome
        self._park(job_id, lanes, result.receipt_path)
        return "parked"

    def _one(
        self,
        attempt: int,
        job_id: str,
        raw: dict[str, Any],
        source: Path,
        receipt: dict[str, Any],
        result: QueueRun,
        trigger: str,
        kind: str,
        prior: str,
    ) -> tuple[str, str, str]:
        tier = "auto" if attempt <= ROUTED_ATTEMPTS else "escalate"
        role = lane_role(job_id, attempt)
        brief = write_brief(self.main, source, job_id, attempt, trigger, raw, receipt, prior)
        self._record(
            job_id,
            attempt,
            role,
            "dispatched",
            result.receipt_path,
            {"tier": tier, "kind": kind, "brief": str(brief), "trigger": trigger},
        )
        try:
            lane = self.dispatcher.run(role=role, tier=tier, kind=kind, brief=brief, repo=self.main)
        except Exception as exc:  # noqa: BLE001 — a lane fault is a failed attempt
            self._record(job_id, attempt, role, "result", result.receipt_path, {"error": str(exc)})
            return "retry", prior, role
        notes = prior_notes(lane.result_text)
        self._record(
            job_id,
            attempt,
            role,
            "result",
            result.receipt_path,
            {"exit_code": lane.exit_code, "summary": _one_line(notes or lane.result_text)},
        )
        decision = decide(lane.changes)
        if decision.status == "hold":
            self._close(job_id, attempt, role, "held", result.receipt_path, lane, decision.detail)
            return "held", notes, role
        if decision.status != "merge":
            return "retry", notes, role
        merged = self._merge_lane(job_id, attempt, lane)
        if merged.status == "hold":
            self._close(job_id, attempt, role, "held", result.receipt_path, lane, merged.detail)
            return "held", notes, role
        if merged.status != "merged":
            return "retry", notes, role
        if not self._restore(job_id, raw, source, lane):
            return "retry", notes, role
        if not self._requeue(job_id, raw, source):
            return "retry", notes, role
        self._close(job_id, attempt, role, "merged", result.receipt_path, lane, merged.detail)
        return "merged", notes, role

    def _merge_lane(self, job_id: str, attempt: int, lane: LaneResult) -> _Decision:
        if lane.worktree is None or not lane.worktree.exists():
            return _Decision("failed", "lane worktree is missing")
        if not _gates(lane.worktree, self.main, lane.changes, self.gate_runner):
            return _Decision("failed", "pytest or ruff failed in the throwaway merge")
        dirty = git_run(self.main, ["status", "--porcelain"]).stdout.strip()
        if dirty:
            return _Decision("hold", "main checkout has uncommitted work")
        branch = git_run(self.main, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if branch != "main":
            return _Decision("hold", f"main checkout is on {branch}, not main")
        detail = _land(self.main, lane, f"escalation: {job_id} attempt {attempt}")
        if detail is None:
            return _Decision("failed", "merge to main failed")
        return _Decision("merged", detail)

    def _restore(self, job_id: str, raw: dict[str, Any], source: Path, lane: LaneResult) -> bool:
        try:
            return self._restore_checked(job_id, raw, source, lane)
        except (OSError, ValueError) as exc:
            self._note(job_id, "result", {"reason": str(exc)})
            return False

    def _restore_checked(
        self, job_id: str, raw: dict[str, Any], source: Path, lane: LaneResult
    ) -> bool:
        if not _repin(self.main, source):
            self._note(job_id, "result", {"reason": "snapshot worktree did not re-pin"})
            return False
        if lane.worktree is not None:
            _copy_paths(lane.worktree, source, lane.changes.untracked)
        root = source if source.is_dir() else self.repo_root
        spec = parse_job_spec(raw, repo_root=root)
        if _canaries_pass(spec, source, self.canary_runner):
            return True
        self._note(job_id, "result", {"reason": "canary did not pass after merge"})
        return False

    def _requeue(self, job_id: str, raw: dict[str, Any], source: Path) -> bool:
        root = source if source.is_dir() else self.repo_root
        try:
            spec = parse_job_spec(raw, repo_root=root)
            with QueueLedger(self.tasks_dir) as ledger:
                if ledger.task(job_id) is not None:
                    ledger.requeue_job(job_id, job_json(spec))
        except (OSError, ValueError) as exc:
            self._note(job_id, "result", {"reason": str(exc)})
            return False
        return True

    def _park(self, job_id: str, lanes: list[str], receipt: Path | None) -> None:
        reason = "escalation exhausted: " + ", ".join(lanes)
        with QueueLedger(self.tasks_dir) as ledger:
            if ledger.task(job_id) is not None:
                ledger.finish(job_id, "blocked", "BLOCKED", reason)
        self._record(
            job_id,
            MAX_ATTEMPTS,
            lanes[-1] if lanes else "",
            "parked",
            receipt,
            {
                "reason": reason,
                "lanes": lanes,
            },
        )

    def _close(
        self,
        job_id: str,
        attempt: int,
        role: str,
        event: str,
        receipt: Path | None,
        lane: LaneResult,
        detail: str,
    ) -> None:
        self._record(
            job_id,
            attempt,
            role,
            event,
            receipt,
            {
                "branch": lane.branch,
                "detail": detail,
                "summary": _one_line(prior_notes(lane.result_text)),
            },
        )

    def _record(
        self,
        job_id: str,
        attempt: int,
        lane_id: str,
        event: str,
        receipt: Path | None,
        detail: dict[str, Any],
    ) -> None:
        self.ledger.add(job_id, attempt, lane_id, event, detail)
        _append_receipt(
            receipt,
            {
                "at": _utc(),
                "attempt": attempt,
                "lane_id": lane_id,
                "event": event,
                "detail": detail,
            },
        )
        _emit(self.notices, job_id, event, {"lane": lane_id, "attempt": attempt, **detail})

    def _note(self, job_id: str, event: str, detail: dict[str, Any]) -> None:
        _emit(self.notices, job_id, event, detail)


def write_brief(
    main: Path,
    source: Path,
    job_id: str,
    attempt: int,
    trigger: str,
    raw: dict[str, Any],
    receipt: dict[str, Any],
    prior: str,
) -> Path:
    """coding_task/TASK_*.md style brief for one escalation attempt."""
    step = _failing_step(receipt)
    stdout = _last_lines(str(step.get("stdout_tail") or ""))
    stderr = _last_lines(str(step.get("stderr_tail") or ""))
    setup = _setup_lines(stdout + "\n" + stderr)
    files = _likely_files(raw, step, stdout, stderr)
    body = _brief_body(job_id, attempt, trigger, raw, receipt, step, stdout, stderr, setup, files)
    if attempt > 1 and prior.strip():
        body += "\n\n" + prior.strip() + "\n"
    path = _brief_path(main, job_id, attempt)
    path.write_text(body, encoding="utf-8")
    if source.resolve() != main.resolve():
        copy = _brief_path(source, job_id, attempt)
        copy.write_text(body, encoding="utf-8")
    return path


def decide(changes: LaneChanges) -> _Decision:
    """Auto-merge only an allowlisted committed diff. Anything else is held or retried."""
    paths = changes.paths()
    if not paths:
        return _Decision("empty", "lane produced no diff")
    if changes.unstaged:
        return _Decision("uncommitted", "lane left tracked changes uncommitted")
    held = [_hold_why(path) for path in paths if not _allowlisted(path)]
    if held:
        return _Decision("hold", "; ".join(held))
    return _Decision("merge", "allowlisted")


def inspect_changes(worktree: Path, main: Path) -> LaneChanges:
    base = git_run(main, ["rev-parse", "HEAD"]).stdout.strip()
    committed = _diff_names(worktree, ["diff", "--name-only", f"{base}...HEAD"])
    unstaged = _diff_names(worktree, ["diff", "--name-only", "HEAD"])
    untracked = _diff_names(worktree, ["ls-files", "--others", "--exclude-standard"])
    return LaneChanges(committed, unstaged, untracked)


def main_checkout(repo: Path) -> Path:
    proc = git_run(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return repo
    common = Path(proc.stdout.strip())
    return common.parent if common.name == ".git" else common.parent


def git_run(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in _GIT_ENV_KEYS:
        env.pop(key, None)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def prior_notes(text: str) -> str:
    """The previous lane's RESULT and OPEN-RISK sections, for the next brief."""
    result = _section(text, "RESULT")
    risk = _section(text, "OPEN / RISK") or _section(text, "OPEN-RISK")
    parts = []
    if result:
        parts.append("## Previous RESULT\n\n" + result)
    if risk:
        parts.append("## Previous OPEN-RISK\n\n" + risk)
    return "\n\n".join(parts)


def _cancelled(status: str, reason: str) -> bool:
    return status == "CANCELLED" or "cancelled by operator" in reason.lower()


def _memory_trip(receipt: dict[str, Any], reason: str) -> bool:
    if "memory safety trip" in reason.lower():
        return True
    memory = receipt.get("memory")
    if isinstance(memory, dict) and memory.get("trips"):
        return True
    return any(isinstance(step, dict) and step.get("memory_trip") for step in _steps(receipt))


def _failed_step(receipt: dict[str, Any]) -> bool:
    return any(isinstance(step, dict) and step.get("state") == "failed" for step in _steps(receipt))


def _steps(receipt: dict[str, Any]) -> list[Any]:
    steps = receipt.get("steps")
    return steps if isinstance(steps, list) else []


def _output_text(receipt: dict[str, Any]) -> str:
    chunks = []
    for step in _steps(receipt):
        if isinstance(step, dict):
            chunks.append(str(step.get("stdout_tail") or ""))
            chunks.append(str(step.get("stderr_tail") or ""))
    return "\n".join(chunks)


def _failing_step(receipt: dict[str, Any]) -> dict[str, Any]:
    steps = [step for step in _steps(receipt) if isinstance(step, dict)]
    for step in steps:
        if step.get("memory_trip") or step.get("state") in {"failed", "stopped"}:
            return step
    return steps[-1] if steps else {}


def _allowlisted(path: str) -> bool:
    normal = path.replace("\\", "/").lstrip("./")
    return any(
        normal.startswith(prefix) or normal == prefix.rstrip("/") for prefix in _AUTO_PREFIXES
    )


def _hold_why(path: str) -> str:
    name = Path(path).name
    normal = path.replace("\\", "/").lstrip("./")
    if name == "Dockerfile" or name.startswith("Dockerfile"):
        return f"{path} is a Dockerfile"
    if normal.startswith("portal/"):
        return f"{path} is under portal/"
    if normal.startswith("scripts/"):
        return f"{path} is under scripts/"
    if normal.startswith("config/") and not normal.startswith("config/arm_jobs/"):
        return f"{path} is under config/ outside config/arm_jobs/"
    return f"{path} is outside the auto-merge allowlist"


def _brief_body(
    job_id: str,
    attempt: int,
    trigger: str,
    raw: dict[str, Any],
    receipt: dict[str, Any],
    step: dict[str, Any],
    stdout: str,
    stderr: str,
    setup: str,
    files: list[str],
) -> str:
    purpose = str(raw.get("purpose") or receipt.get("purpose") or "")
    argv = " ".join(str(part) for part in step.get("argv") or [])
    file_lines = "\n".join(f"- `{path}`" for path in files) or "- (none named by the receipt)"
    spec = json.dumps(raw, indent=2, sort_keys=True)
    return (
        f"# Lane {lane_role(job_id, attempt)} — repair blocked job {job_id}\n\n"
        f"Job `{job_id}` finished {receipt.get('status')} ({trigger}). "
        f"Purpose: {purpose}\n\n"
        "Jarvis Local asked for this repair. The orchestrator is not in the loop. "
        "Fix the failure below. Commit the repair on this branch. Do not push. "
        "Do not rebuild or restart the live stack.\n\n"
        f"## Failure\n\n- Trigger: {trigger}\n- Step: `{step.get('id', '')}`\n"
        f"- Argv: `{argv}`\n- Reason: {step.get('reason') or receipt.get('reason') or ''}\n\n"
        f"## Last stdout\n\n```\n{stdout}\n```\n\n## Last stderr\n\n```\n{stderr}\n```\n\n"
        f"## Canary SETUP rows\n\n```\n{setup or '(none)'}\n```\n\n"
        f"## Files most likely involved\n\n{file_lines}\n\n"
        f"## Job spec\n\n```json\n{spec}\n```\n"
    )


def _brief_path(repo: Path, job_id: str, attempt: int) -> Path:
    path = repo / "coding_task" / "escalations" / f"{_safe(job_id)}-{attempt}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _last_lines(text: str, limit: int = TAIL_LINES) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def _setup_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if "SETUP" in line)


def _likely_files(raw: dict[str, Any], step: dict[str, Any], stdout: str, stderr: str) -> list[str]:
    blob = "\n".join(
        [
            str(raw.get("purpose") or ""),
            " ".join(str(part) for part in step.get("argv") or []),
            stdout,
            stderr,
        ]
    )
    found = list(_PATH_RE.findall(blob))
    for part in step.get("argv") or []:
        text = str(part)
        if "/" in text or text.startswith("tests") or text.startswith("config"):
            found.append(text)
    return list(dict.fromkeys(found))


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            start = index + 1
            break
    if start is None:
        return ""
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out).strip()


def _safe(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-")
    return cleaned or "job"


def _utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(value: object) -> str:
    return " ".join(str(value).split())[:300]


def _load_receipt(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_receipt(path: Path | None, event: dict[str, Any]) -> None:
    payload = _load_receipt(path)
    if not payload or path is None:
        return
    events = payload.get("escalations")
    if not isinstance(events, list):
        events = []
    events.append(event)
    payload["escalations"] = events
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def _emit(notices: object, job_id: str, event: str, detail: dict[str, Any]) -> None:
    method = getattr(notices, "escalation", None)
    if method is None:
        return
    try:
        method(job_id, event, detail)
    except Exception:  # noqa: BLE001 — a notice must not stop the queue
        return


def _no_changes() -> LaneChanges:
    return LaneChanges((), (), ())


def _empty_lane(role: str, tier: str, code: int, text: str) -> LaneResult:
    return LaneResult(role, tier, code, text, f"lane/{_safe(role)}", None, _no_changes())


def _lane_worktree(repo: Path, role: str) -> Path:
    return repo.parent / f"{repo.name}-{_safe(role)}"


def _latest_log(role: str) -> str:
    directory = (
        Path.home() / ".claude" / "orchestrate" / "logs" / re.sub(r"[^A-Za-z0-9]", "_", role)
    )
    if not directory.is_dir():
        return ""
    logs = sorted(directory.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
    if not logs:
        return ""
    try:
        return logs[-1].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _run_bounded(
    argv: list[str], timeout_s: float, poll_s: float, sleeper: Callable[[float], None]
) -> tuple[str, int]:
    fd, name = tempfile.mkstemp(prefix="portal-esc-", suffix=".log")
    os.close(fd)
    path = Path(name)
    sink = path.open("w", encoding="utf-8")
    proc = subprocess.Popen(argv, stdout=sink, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        code = _wait_process(proc, timeout_s, poll_s, sleeper)
    finally:
        sink.close()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    path.unlink(missing_ok=True)
    return text, code


def _wait_process(
    proc: subprocess.Popen[Any],
    timeout_s: float,
    poll_s: float,
    sleeper: Callable[[float], None],
) -> int:
    deadline = time.monotonic() + timeout_s
    while proc.poll() is None:
        if time.monotonic() >= deadline:
            _stop_process(proc)
            break
        sleeper(poll_s)
    return proc.returncode if proc.returncode is not None else 124


def _stop_process(proc: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
        proc.wait(timeout=5)


def _diff_names(repo: Path, args: list[str]) -> tuple[str, ...]:
    proc = git_run(repo, args)
    if proc.returncode != 0:
        return ()
    return tuple(line.strip() for line in proc.stdout.splitlines() if line.strip())


def _gates(worktree: Path, main: Path, changes: LaneChanges, runner: GateRunner) -> bool:
    parent = Path(tempfile.mkdtemp(prefix="portal-esc-"))
    dest = parent / "merge"
    added = git_run(main, ["worktree", "add", "--detach", str(dest), "HEAD"])
    if added.returncode != 0:
        shutil.rmtree(parent, ignore_errors=True)
        return False
    try:
        if not _merge_into(dest, worktree, changes):
            return False
        return _run_gates(dest, runner)
    finally:
        git_run(main, ["worktree", "remove", "--force", str(dest)])
        shutil.rmtree(parent, ignore_errors=True)


def _merge_into(dest: Path, worktree: Path, changes: LaneChanges) -> bool:
    head = git_run(worktree, ["rev-parse", "HEAD"]).stdout.strip()
    base = git_run(dest, ["rev-parse", "HEAD"]).stdout.strip()
    if head and head != base:
        merged = git_run(dest, ["merge", "--no-edit", head])
        if merged.returncode != 0:
            return False
    _copy_paths(worktree, dest, changes.untracked)
    return True


def _run_gates(dest: Path, runner: GateRunner) -> bool:
    return all(runner(argv, dest) == 0 for argv in _GATE_COMMANDS)


def _land(main: Path, lane: LaneResult, message: str) -> str | None:
    if lane.worktree is None:
        return None
    if not _merge_head(main, lane.worktree, message):
        return None
    if not _commit_untracked(main, lane.changes.untracked, message):
        return None
    return git_run(main, ["rev-parse", "--short", "HEAD"]).stdout.strip()


def _merge_head(main: Path, worktree: Path, message: str) -> bool:
    head = git_run(worktree, ["rev-parse", "HEAD"]).stdout.strip()
    base = git_run(main, ["rev-parse", "HEAD"]).stdout.strip()
    if not head or head == base:
        return True
    merged = git_run(main, ["merge", "--no-ff", "--no-edit", "-m", message, head])
    return merged.returncode == 0


def _commit_untracked(main: Path, paths: Sequence[str], message: str) -> bool:
    if not paths:
        return True
    if git_run(main, ["add", "-f", "--", *paths]).returncode != 0:
        return False
    if git_run(main, ["diff", "--cached", "--quiet"]).returncode == 0:
        return True
    return git_run(main, ["commit", "-m", message]).returncode == 0


def _repin(main: Path, source: Path) -> bool:
    if source.resolve() == main.resolve() or not (source / ".git").exists():
        return True
    if git_run(source, ["status", "--porcelain"]).stdout.strip():
        return False
    sha = git_run(main, ["rev-parse", "HEAD"]).stdout.strip()
    return git_run(source, ["checkout", "--detach", sha]).returncode == 0


def _copy_paths(src: Path, dest: Path, paths: Sequence[str]) -> None:
    if src.resolve() == dest.resolve():
        return
    for rel in paths:
        origin = src / rel
        if not origin.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)


def _canaries_pass(spec: JobSpec, cwd: Path, runner: CanaryRunner) -> bool:
    canaries = [step for step in spec.steps if step.canary_of]
    return all(runner(step.argv, cwd, step.timeout_seconds) == 0 for step in canaries)


def _subprocess_gate(argv: Sequence[str], cwd: Path) -> int:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, check=False, timeout=GATE_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return proc.returncode


def _subprocess_canary(argv: Sequence[str], cwd: Path, timeout_s: float) -> int:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, check=False, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return proc.returncode
