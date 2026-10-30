"""Cloud-lane escalation for a blocked Jarvis Local job.

The queue calls this only when ``queue.escalation.enabled`` is true. Attempts 1 and 2
use ``dispatch.py run --tier auto``; attempt 3 uses ``--tier escalate``. Nothing here
starts the live stack or pushes git.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shlex
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
_VERDICT_TAGS = frozenset(
    {
        "merged",
        "test-weakened",
        "canary-failed",
        "oracle-rejected",
        "gates-failed",
        "uncommitted",
        "empty",
        "held-path",
        "contract-miss",
        "infra",
    }
)
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
CanaryRunner = Callable[[Sequence[str], Path, float], tuple[int, str]]


class LaneDispatcher(Protocol):
    def run(
        self,
        *,
        role: str,
        tier: str,
        kind: str,
        brief: Path,
        repo: Path,
        new: bool = True,
    ) -> LaneResult: ...


class OracleReviewer(Protocol):
    def review(
        self, *, job_id: str, attempt: int, lane: LaneResult, base: str, kind: str
    ) -> OracleResult: ...


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
    status: str | None = None
    retry_until: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class _Decision:
    status: str
    detail: str
    tag: str = ""


@dataclass(frozen=True)
class _GateResult:
    passed: bool
    tag: str
    detail: str


@dataclass(frozen=True)
class OracleResult:
    verdict: str
    detail: str
    tag: str


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
            parts.extend(
                [
                    str(step.get("id") or ""),
                    " ".join(str(part) for part in step.get("argv") or []),
                ]
            )
    if _SECURITY_KIND.search(" ".join(parts)):
        return "security"
    return "code"


def _brief_contract_kind(raw: dict[str, Any], kind: str) -> str:
    if kind == "security":
        return "security"
    explicit = str(raw.get("kind") or "")
    if explicit in {"tests", "debug"}:
        return explicit
    text = " ".join(
        [str(raw.get("id") or ""), str(raw.get("purpose") or "")]
        + [
            " ".join(str(part) for part in step.get("argv") or [])
            for step in raw.get("steps") or []
            if isinstance(step, dict)
        ]
    ).lower()
    return "tests" if re.search(r"\btest(?:s|ing)?\b|(?:^|/)tests?(/|\b)", text) else "debug"


def _contract_addendum(repo: Path, kind: str) -> tuple[str, str]:
    path = repo / "coding_task" / "CONTRACTS" / f"{kind}.md"
    content = path.read_text(encoding="utf-8")
    return content.rstrip(), hashlib.sha256(content.encode("utf-8")).hexdigest()


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
    block = policy.get("escalation") if isinstance(policy, dict) else None
    config = block.get("oracle") if isinstance(block, dict) else None
    oracle = None
    if isinstance(config, dict) and config.get("enabled") is True:
        oracle = ProcessOracle(
            tasks_dir,
            repo_root=repo_root,
            tier=str(config.get("tier") or "deep-pro"),
            timeout_seconds=float(config.get("timeout_seconds") or 1800),
        )
    return _EscalationHook(
        Escalator(tasks_dir, repo_root=repo_root, notices=notices, oracle=oracle)
    )


class _EscalationHook:
    def __init__(self, escalator: Escalator) -> None:
        self.escalator = escalator

    def __call__(self, item: dict[str, Any], result: QueueRun) -> str:
        return self.escalator.handle(item, result)

    def resume_pending(self, item: dict[str, Any], result: QueueRun) -> str:
        return self.escalator.resume_pending(item, result)


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

    def run(
        self,
        *,
        role: str,
        tier: str,
        kind: str,
        brief: Path,
        repo: Path,
        new: bool = True,
    ) -> LaneResult:
        if not self.binary.is_file():
            return _empty_lane(role, tier, 127, f"dispatch binary missing: {self.binary}")
        argv = _dispatch_argv(self.binary, repo, role, tier, kind, brief, self.timeout_s, new)
        output, code = _run_bounded(argv, self.timeout_s, self.poll_s, self.sleeper)
        text = output if "## RESULT" in output else _latest_log(role) or output
        worktree = _lane_worktree(repo, role)
        changes = inspect_changes(worktree, repo) if (worktree / ".git").exists() else _no_changes()
        status, retry_until, model = _dispatch_run_metadata(self.binary, repo, role)
        return LaneResult(
            role,
            tier,
            code,
            text,
            f"lane/{_safe(role)}",
            worktree,
            changes,
            status,
            retry_until,
            model,
        )


def _dispatch_argv(
    binary: Path,
    repo: Path,
    role: str,
    tier: str,
    kind: str,
    brief: Path,
    timeout_s: float,
    new: bool,
) -> list[str]:
    argv = [
        sys.executable,
        str(binary),
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
    ]
    if new:
        argv.append("--new")
    return [*argv, "--timeout", str(int(timeout_s))]


def _dispatch_run_metadata(
    binary: Path, repo: Path, role: str
) -> tuple[str | None, str | None, str | None]:
    path = binary.parent.parent / "registry.json"
    try:
        roles = json.loads(path.read_text(encoding="utf-8")).get("roles", {})
        key = f"{_lane_worktree(repo.resolve(), role)}::{role}"
        runs = roles.get(key, {}).get("runs", [])
        latest = runs[-1] if runs else {}
    except (OSError, json.JSONDecodeError, AttributeError, IndexError):
        return None, None, None
    return latest.get("status"), latest.get("retry_until"), latest.get("model")


def _resume_command(
    dispatcher: object, repo: Path, role: str, tier: str, kind: str, brief: Path
) -> str:
    binary = Path(getattr(dispatcher, "binary", DEFAULT_DISPATCH))
    timeout = float(getattr(dispatcher, "timeout_s", 3600))
    argv = _dispatch_argv(binary, repo, role, tier, kind, brief, timeout, False)
    return shlex.join(argv)


class ProcessOracle:
    def __init__(
        self,
        tasks_dir: Path,
        *,
        repo_root: Path,
        tier: str,
        timeout_seconds: float,
        dispatcher: LaneDispatcher | None = None,
        policy_resolver: Callable[[Path, str], tuple[str, bool, set[str], set[str]]] | None = None,
    ) -> None:
        self.tasks_dir = tasks_dir
        self.main = main_checkout(repo_root)
        self.tier = tier
        self.binary = DEFAULT_DISPATCH
        self.dispatcher = dispatcher or ProcessDispatcher(self.binary, timeout_s=timeout_seconds)
        self.policy_resolver = policy_resolver or _dispatcher_policy

    def review(
        self, *, job_id: str, attempt: int, lane: LaneResult, base: str, kind: str
    ) -> OracleResult:
        try:
            model, free_gateway, task_kinds, security_kinds = self.policy_resolver(
                self.binary, self.tier
            )
        except Exception as exc:  # noqa: BLE001 — configuration faults fail closed
            return OracleResult("hold", f"oracle policy unavailable: {exc}", "infra")
        review_kind = "security" if kind in security_kinds else "review"
        if review_kind not in task_kinds:
            return OracleResult("hold", "dispatcher does not support the review kind", "infra")
        if review_kind in security_kinds and free_gateway:
            return OracleResult("hold", "security review tier is a cloud free gateway", "infra")
        lane_family = _model_family(lane.model or "")
        review_family = _model_family(model)
        if not lane_family or not review_family or lane_family == review_family:
            return OracleResult(
                "hold", "oracle family is not distinct from the lane family", "infra"
            )
        if lane.worktree is None:
            return OracleResult("hold", "lane worktree is missing for oracle review", "infra")
        try:
            brief = _oracle_brief(lane, base)
            path = self.tasks_dir / _safe(job_id) / f"oracle-{attempt}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(brief, encoding="utf-8")
            result = self.dispatcher.run(
                role=f"esc-oracle-{_safe(job_id)}-{attempt}",
                tier=self.tier,
                kind=review_kind,
                brief=path,
                repo=self.main,
            )
        except Exception as exc:  # noqa: BLE001 — reviewer faults fail closed
            return OracleResult("hold", f"oracle review failed: {exc}", "infra")
        if result.exit_code != 0 or result.status == "quota":
            return OracleResult("hold", "oracle dispatch did not complete", "infra")
        return _parse_oracle(result.result_text, set(lane.changes.paths()))


def _dispatcher_policy(binary: Path, tier: str) -> tuple[str, bool, set[str], set[str]]:
    spec = importlib.util.spec_from_file_location("portal5_escalation_dispatch", binary)
    if spec is None or spec.loader is None:
        raise ValueError("dispatcher module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if tier not in module.TIERS:
        raise ValueError(f"unknown oracle tier: {tier}")
    return (
        str(module.TIERS[tier]["model"]),
        bool(module._cloud_free_gateway(tier)),
        set(module.TASK_KINDS),
        set(module.SECURITY_KINDS),
    )


def _model_family(model: str) -> str:
    normalized = model.lower()
    known = (
        "deepseek",
        "glm",
        "mimo",
        "kimi",
        "grok",
        "claude",
        "gpt",
        "gemini",
        "gemma",
        "qwen",
        "minimax",
        "nemotron",
        "llama",
        "mistral",
    )
    if family := next((value for value in known if value in normalized), None):
        return family
    return normalized.split("/", maxsplit=1)[0] if "/" in normalized else ""


def _oracle_brief(lane: LaneResult, base: str) -> str:
    if lane.worktree is None:
        raise ValueError("lane worktree is missing")
    diff = git_run(lane.worktree, ["diff", "--binary", f"{base}...HEAD"])
    if diff.returncode != 0:
        raise ValueError("lane diff could not be read")
    sections = [diff.stdout]
    for path in lane.changes.untracked:
        target = lane.worktree / path
        if target.is_file():
            body = target.read_text(encoding="utf-8", errors="replace")
            sections.append(f"\n### Untracked file: {path}\n\n```\n{body}\n```")
    result = _section(lane.result_text, "RESULT") or "(missing)"
    risk = _section(lane.result_text, "OPEN / RISK") or _section(lane.result_text, "OPEN-RISK")
    checklist = (
        "- blunt caps or timeouts hiding a cause\n"
        "- wrong mount or path\n"
        "- tests touching real stores\n"
        "- swallowed errors\n"
        "- weakened tests\n"
        "- sourcing the whole .env"
    )
    return (
        "Review the committed lane diff. Do not edit files. Return exactly APPROVE or REJECT in "
        "## RESULT. A REJECT must include changed-file findings as path:line: reason under "
        "## FINDINGS.\n\n## Diff\n\n"
        + "\n".join(section for section in sections if section)
        + f"\n\n## Lane RESULT\n\n{result}\n\n## Lane OPEN-RISK\n\n{risk or '(none)'}"
        + f"\n\n## Defect checklist\n\n{checklist}\n"
    )


_ORACLE_FINDING = re.compile(r"^\s*(?:[-*]\s*)?`?([^`:\s]+)`?:(\d+)\s*[:\-]\s*(.+)$")


def _parse_oracle(text: str, changed_paths: set[str]) -> OracleResult:
    verdict = _section(text, "RESULT").strip().upper()
    if verdict not in {"APPROVE", "REJECT"}:
        return OracleResult("hold", "oracle response has no valid verdict", "contract-miss")
    findings: list[str] = []
    for line in _section(text, "FINDINGS").splitlines():
        if not line.strip() or line.strip().lower() in {"none", "no findings"}:
            continue
        match = _ORACLE_FINDING.match(line)
        if match is None or match.group(1).lstrip("./") not in changed_paths:
            return OracleResult("hold", "oracle response has malformed findings", "contract-miss")
        findings.append(f"{match.group(1)}:{match.group(2)}: {match.group(3).strip()}")
    if verdict == "REJECT" and not findings:
        return OracleResult("hold", "oracle rejection has no file:line finding", "contract-miss")
    return OracleResult(
        verdict.lower(), "; ".join(findings) if findings else "oracle approved", "oracle-rejected"
    )


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
        oracle: OracleReviewer | None = None,
        verdict_runner: Callable[[Sequence[str]], int] | None = None,
        main_root: Path | None = None,
    ) -> None:
        self.tasks_dir = tasks_dir
        self.repo_root = repo_root
        self.notices = notices
        self.dispatcher = dispatcher or ProcessDispatcher()
        self.gate_runner = gate_runner or _subprocess_gate
        self.canary_runner = canary_runner or _subprocess_canary
        self.oracle = oracle
        self.verdict_runner = verdict_runner or _subprocess_verdict
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
        pending = self._pending_quota(job_id)
        first = 1
        if pending is not None:
            detail = pending["detail"]
            if not _retry_due(str(detail.get("retry_until") or "")):
                return "quota"
            lanes = list(
                dict.fromkeys(
                    event["lane_id"]
                    for event in self.ledger.events(job_id)
                    if event["event"] == "verdict" and event["lane_id"]
                )
            )
            first = int(pending["attempt"]) + 1
            outcome, prior, role = self._one(
                int(pending["attempt"]),
                job_id,
                raw,
                source,
                receipt,
                result,
                trigger,
                kind,
                str(detail.get("prior") or ""),
                tier_override=str(detail.get("tier") or "auto"),
                new=False,
            )
            if outcome == "quota":
                return outcome
            if outcome in {"merged", "held"}:
                return outcome
            prior = prior or str(detail.get("prior") or "")
        for attempt in range(first, MAX_ATTEMPTS + 1):
            outcome, prior, role = self._one(
                attempt, job_id, raw, source, receipt, result, trigger, kind, prior
            )
            if role not in lanes:
                lanes.append(role)
            if outcome == "quota":
                return outcome
            if outcome in {"merged", "held"}:
                return outcome
        self._park(job_id, lanes, result.receipt_path)
        return "parked"

    def resume_pending(self, item: dict[str, Any], result: QueueRun) -> str:
        if self._pending_quota(str(item["task_id"])) is None:
            return "skipped"
        pending = self._pending_quota(str(item["task_id"]))
        if pending is None or not _retry_due(str(pending["detail"].get("retry_until") or "")):
            return "waiting"
        return self.handle(item, result)

    def _pending_quota(self, job_id: str) -> dict[str, Any] | None:
        events = self.ledger.events(job_id)
        if not events or events[-1]["event"] != "quota":
            return None
        try:
            detail = json.loads(str(events[-1]["detail_json"]))
        except json.JSONDecodeError:
            return None
        return {
            "attempt": events[-1]["attempt"],
            "lane_id": events[-1]["lane_id"],
            "detail": detail,
        }

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
        *,
        tier_override: str | None = None,
        new: bool = True,
    ) -> tuple[str, str, str]:
        tier = tier_override or ("auto" if attempt <= ROUTED_ATTEMPTS else "escalate")
        role = lane_role(job_id, attempt)
        contract_kind = _brief_contract_kind(raw, kind)
        addendum_text, addendum_sha = _contract_addendum(self.repo_root, contract_kind)
        brief = write_brief(
            self.main,
            source,
            job_id,
            attempt,
            trigger,
            raw,
            receipt,
            prior,
            contract_kind=contract_kind,
            addendum_text=addendum_text,
            addendum_sha=addendum_sha,
        )
        self._record(
            job_id,
            attempt,
            role,
            "dispatched",
            result.receipt_path,
            {
                "tier": tier,
                "kind": kind,
                "brief": str(brief),
                "trigger": trigger,
                "addendum_kind": contract_kind,
                "addendum_sha256": addendum_sha,
            },
        )
        try:
            lane = self.dispatcher.run(
                role=role, tier=tier, kind=kind, brief=brief, repo=self.main, new=new
            )
        except Exception as exc:  # noqa: BLE001 — a lane fault is a failed attempt
            self._record(job_id, attempt, role, "result", result.receipt_path, {"error": str(exc)})
            self._record_verdict(
                job_id, attempt, role, result.receipt_path, "infra", str(exc), False
            )
            return "retry", prior, role
        notes = prior_notes(lane.result_text) or prior
        self._record(
            job_id,
            attempt,
            role,
            "result",
            result.receipt_path,
            {
                "exit_code": lane.exit_code,
                "status": lane.status,
                "summary": _one_line(notes or lane.result_text),
            },
        )
        if lane.status == "quota":
            resume = _resume_command(self.dispatcher, self.main, role, tier, kind, brief)
            self._record_verdict(
                job_id,
                attempt,
                role,
                result.receipt_path,
                "infra",
                "dispatcher status quota",
                False,
            )
            self._record(
                job_id,
                attempt,
                role,
                "quota",
                result.receipt_path,
                {
                    "tier": tier,
                    "kind": kind,
                    "retry_until": lane.retry_until,
                    "resume_command": resume,
                    "prior": prior,
                    "trigger": trigger,
                },
            )
            return "quota", prior, role
        if lane.worktree is None:
            self._record_verdict(
                job_id, attempt, role, result.receipt_path, "infra", lane.result_text, False
            )
            return "retry", prior, role
        base = git_run(self.main, ["rev-parse", "HEAD"]).stdout.strip()
        decision = decide(lane.changes, worktree=lane.worktree, base=base)
        if decision.status == "hold":
            self._record_verdict(
                job_id,
                attempt,
                role,
                result.receipt_path,
                decision.tag or "held-path",
                decision.detail,
                False,
            )
            self._close(job_id, attempt, role, "held", result.receipt_path, lane, decision.detail)
            return "held", notes, role
        if decision.status != "merge":
            self._record_verdict(
                job_id,
                attempt,
                role,
                result.receipt_path,
                decision.tag or "contract-miss",
                decision.detail,
                False,
            )
            if decision.status == "weakened":
                notes = (
                    f"{notes}\n\n## Previous test-weakening rejection\n\n{decision.detail}".strip()
                )
            return "retry", notes, role
        spec = parse_job_spec(raw, repo_root=source if source.is_dir() else self.repo_root)
        merged = self._merge_lane(job_id, attempt, lane, spec, source, kind)
        self._record_verdict(
            job_id,
            attempt,
            role,
            result.receipt_path,
            merged.tag or ("merged" if merged.status == "merged" else "contract-miss"),
            merged.detail,
            merged.status == "merged",
        )
        if merged.status == "hold":
            self._close(job_id, attempt, role, "held", result.receipt_path, lane, merged.detail)
            return "held", notes, role
        if merged.status != "merged":
            if merged.detail.startswith("canary failed"):
                notes = f"{notes}\n\n## Previous canary failure\n\n{merged.detail}".strip()
            elif merged.detail.startswith("oracle rejected:"):
                notes = f"{notes}\n\n## Previous Oracle findings\n\n{merged.detail}".strip()
            return "retry", notes, role
        if not self._restore(job_id, raw, source, lane):
            return "retry", notes, role
        if not self._requeue(job_id, raw, source):
            return "retry", notes, role
        self._close(job_id, attempt, role, "merged", result.receipt_path, lane, merged.detail)
        return "merged", notes, role

    def _merge_lane(
        self,
        job_id: str,
        attempt: int,
        lane: LaneResult,
        spec: JobSpec,
        source: Path,
        kind: str,
    ) -> _Decision:
        if lane.worktree is None or not lane.worktree.exists():
            return _Decision("failed", "lane worktree is missing", "infra")
        base = git_run(
            source if source.is_dir() else self.main, ["rev-parse", "HEAD"]
        ).stdout.strip()
        main_head = git_run(self.main, ["rev-parse", "HEAD"]).stdout.strip()
        checked = _gates(
            lane.worktree,
            self.main,
            lane.changes,
            self.gate_runner,
            spec=spec,
            canary_runner=self.canary_runner,
            base=base,
        )
        if not checked.passed:
            return _Decision("failed", checked.detail, checked.tag)
        dirty = git_run(self.main, ["status", "--porcelain"]).stdout.strip()
        if dirty:
            return _Decision("hold", "main checkout has uncommitted work", "infra")
        branch = git_run(self.main, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if branch != "main":
            return _Decision("hold", f"main checkout is on {branch}, not main", "infra")
        if git_run(self.main, ["rev-parse", "HEAD"]).stdout.strip() != main_head:
            return _Decision("hold", "main HEAD changed after gates", "infra")
        if self.oracle is not None:
            lane_head = git_run(lane.worktree, ["rev-parse", "HEAD"]).stdout.strip()
            lane_status = git_run(lane.worktree, ["status", "--porcelain"]).stdout
            try:
                oracle = self.oracle.review(
                    job_id=job_id, attempt=attempt, lane=lane, base=base, kind=kind
                )
            except Exception as exc:  # noqa: BLE001 — review faults fail closed
                return _Decision("hold", f"oracle review failed: {exc}", "infra")
            if (
                git_run(lane.worktree, ["rev-parse", "HEAD"]).stdout.strip() != lane_head
                or git_run(lane.worktree, ["status", "--porcelain"]).stdout != lane_status
                or git_run(self.main, ["rev-parse", "HEAD"]).stdout.strip() != main_head
            ):
                return _Decision("hold", "lane or main changed during oracle review", "infra")
            if oracle.verdict == "hold":
                return _Decision("hold", oracle.detail, oracle.tag)
            if oracle.verdict == "reject":
                return _Decision("failed", f"oracle rejected: {oracle.detail}", "oracle-rejected")
            if oracle.verdict != "approve":
                return _Decision("hold", "oracle returned a malformed verdict", "contract-miss")
        detail = _land(self.main, lane, f"escalation: {job_id} attempt {attempt}")
        if detail is None:
            return _Decision("failed", "merge to main failed", "infra")
        return _Decision("merged", detail, "merged")

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
        return True

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
        *,
        notify: bool = True,
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
        if notify:
            _emit(self.notices, job_id, event, {"lane": lane_id, "attempt": attempt, **detail})

    def _record_verdict(
        self,
        job_id: str,
        attempt: int,
        role: str,
        receipt: Path | None,
        tag: str,
        detail: str,
        accepted: bool,
    ) -> None:
        tag = tag if tag in _VERDICT_TAGS else "contract-miss"
        note = f"{tag}: {_one_line(detail)}"
        self._record(
            job_id,
            attempt,
            role,
            "verdict",
            receipt,
            {"tag": tag, "verdict": "accept" if accepted else "reject", "detail": detail},
            notify=False,
        )
        argv = [
            sys.executable,
            str(DEFAULT_DISPATCH),
            "--repo",
            str(self.main),
            "verdict",
            "--role",
            role,
            "--accept" if accepted else "--reject",
            "--note",
            note,
        ]
        try:
            self.verdict_runner(argv)
        except Exception:  # noqa: BLE001 — dispatcher verdict writes never stop the queue
            return

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
    *,
    contract_kind: str = "",
    addendum_text: str = "",
    addendum_sha: str = "",
) -> Path:
    """coding_task/TASK_*.md style brief for one escalation attempt."""
    step = _failing_step(receipt)
    stdout = _last_lines(str(step.get("stdout_tail") or ""))
    stderr = _last_lines(str(step.get("stderr_tail") or ""))
    setup = _setup_lines(stdout + "\n" + stderr)
    files = _likely_files(raw, step, stdout, stderr)
    body = _brief_body(job_id, attempt, trigger, raw, receipt, step, stdout, stderr, setup, files)
    if addendum_text:
        body += (
            f"\n\n## Worker contract addendum: {contract_kind}"
            f" (sha256 {addendum_sha})\n\n{addendum_text}\n"
        )
    if attempt > 1 and prior.strip():
        body += "\n\n" + prior.strip() + "\n"
    path = _brief_path(main, job_id, attempt)
    path.write_text(body, encoding="utf-8")
    if source.resolve() != main.resolve():
        copy = _brief_path(source, job_id, attempt)
        copy.write_text(body, encoding="utf-8")
    return path


def decide(changes: LaneChanges, *, worktree: Path | None = None, base: str = "") -> _Decision:
    """Auto-merge only an allowlisted committed diff. Anything else is held or retried."""
    paths = changes.paths()
    if not paths:
        return _Decision("empty", "lane produced no diff", "empty")
    if changes.unstaged:
        return _Decision("uncommitted", "lane left tracked changes uncommitted", "uncommitted")
    held = [_hold_why(path) for path in paths if not _allowlisted(path)]
    if held:
        return _Decision("hold", "; ".join(held), "held-path")
    if worktree is not None and base:
        reason = _test_weakening(worktree, base)
        if reason:
            return _Decision("weakened", reason, "test-weakened")
    return _Decision("merge", "allowlisted", "merged")


def _test_weakening(worktree: Path, base: str) -> str | None:
    names = git_run(
        worktree, ["diff", "--name-status", "--find-renames", f"{base}...HEAD", "--", "tests/"]
    )
    if names.returncode != 0:
        return "could not inspect tests diff"
    changed: list[str] = []
    for line in names.stdout.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        changed.extend(paths)
        if status.startswith("D") and any(path.endswith(".py") for path in paths):
            return f"deleted test file: {paths[0]}"
    diff = git_run(worktree, ["diff", "--unified=0", f"{base}...HEAD", "--", "tests/"])
    if diff.returncode != 0:
        return "could not inspect tests diff"
    for line in diff.stdout.splitlines():
        if re.match(r"^-\s*(?:async\s+)?def\s+test_", line):
            return f"removed test: {line[1:].strip()}"
        if line.startswith("+") and _SKIP_MARKER.search(line[1:]):
            return f"added skip or xfail marker: {line[1:].strip()}"
    for path in changed:
        if path.endswith(".py") and (reason := _weakened_assertion(worktree, base, path)):
            return reason
    return None


_SKIP_MARKER = re.compile(
    r"(?:pytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.xfail\s*\(|"
    r"unittest\.skip(?:If|Unless)?\s*\()"
)


def _weakened_assertion(worktree: Path, base: str, path: str) -> str | None:
    old = git_run(worktree, ["show", f"{base}:{path}"])
    new_path = worktree / path
    if old.returncode != 0 or not new_path.is_file():
        return None
    try:
        old_asserts = _test_assertions(old.stdout)
        new_asserts = _test_assertions(new_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeError):
        return f"could not compare test assertions: {path}"
    for name, assertions in old_asserts.items():
        replacements = new_asserts.get(name, [])
        for assertion in assertions:
            for required in _flatten_and(assertion):
                if not any(_assert_implies(candidate, required) for candidate in replacements):
                    return f"weakened or removed assertion in {path}:{name}"
    return None


def _test_assertions(source: str) -> dict[str, list[ast.expr]]:
    tree = ast.parse(source)
    return {
        node.name: [child.test for child in ast.walk(node) if isinstance(child, ast.Assert)]
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _flatten_and(expression: ast.expr) -> list[ast.expr]:
    if isinstance(expression, ast.BoolOp) and isinstance(expression.op, ast.And):
        return [part for value in expression.values for part in _flatten_and(value)]
    return [expression]


def _assert_implies(candidate: ast.expr, required: ast.expr) -> bool:
    if ast.dump(candidate, include_attributes=False) == ast.dump(
        required, include_attributes=False
    ):
        return True
    if isinstance(candidate, ast.BoolOp):
        checks = [_assert_implies(value, required) for value in candidate.values]
        return any(checks) if isinstance(candidate.op, ast.And) else all(checks)
    if isinstance(required, ast.BoolOp) and isinstance(required.op, ast.Or):
        return any(_assert_implies(candidate, value) for value in required.values)
    if not isinstance(candidate, ast.Compare) or not isinstance(required, ast.Compare):
        return False
    if len(candidate.ops) != 1 or len(required.ops) != 1 or len(candidate.comparators) != 1:
        return False
    if ast.dump(candidate.left, include_attributes=False) != ast.dump(
        required.left, include_attributes=False
    ):
        return False
    left_value, right_value = candidate.comparators[0], required.comparators[0]
    if not isinstance(left_value, ast.Constant) or not isinstance(right_value, ast.Constant):
        return False
    if not isinstance(left_value.value, (int, float)) or not isinstance(
        right_value.value, (int, float)
    ):
        return False
    return _bound_implies(candidate.ops[0], left_value.value, required.ops[0], right_value.value)


def _bound_implies(
    new_op: ast.cmpop, new_value: float, old_op: ast.cmpop, old_value: float
) -> bool:
    if isinstance(old_op, (ast.Lt, ast.LtE)) and isinstance(new_op, (ast.Lt, ast.LtE)):
        return new_value < old_value or (
            new_value == old_value and (isinstance(old_op, ast.LtE) or isinstance(new_op, ast.Lt))
        )
    if isinstance(old_op, (ast.Gt, ast.GtE)) and isinstance(new_op, (ast.Gt, ast.GtE)):
        return new_value > old_value or (
            new_value == old_value and (isinstance(old_op, ast.GtE) or isinstance(new_op, ast.Gt))
        )
    return False


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
        "Fix the failure below. Commit your repair on this branch "
        "(this brief overrides WORKER_CONTRACT §5). Do not push. "
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


def _gates(
    worktree: Path,
    main: Path,
    changes: LaneChanges,
    runner: GateRunner,
    *,
    spec: JobSpec,
    canary_runner: CanaryRunner,
    base: str,
) -> _GateResult:
    parent = Path(tempfile.mkdtemp(prefix="portal-esc-"))
    dest = parent / "merge"
    if not base:
        shutil.rmtree(parent, ignore_errors=True)
        return _GateResult(False, "gates-failed", "job source HEAD could not be read")
    added = git_run(main, ["worktree", "add", "--detach", str(dest), base])
    if added.returncode != 0:
        shutil.rmtree(parent, ignore_errors=True)
        return _GateResult(False, "gates-failed", "could not create throwaway merge worktree")
    try:
        if not _merge_into(dest, worktree, changes):
            return _GateResult(
                False, "gates-failed", "lane could not merge into throwaway worktree"
            )
        if not _run_gates(dest, runner):
            return _GateResult(
                False, "gates-failed", "pytest or ruff failed in the throwaway merge"
            )
        passed, output = _canaries_pass(spec, dest, canary_runner)
        if not passed:
            setup = _setup_lines(output)
            detail = "canary failed in the throwaway merge worktree"
            detail += f"\nCanary SETUP rows:\n{setup or _last_lines(output) or '(no output)'}"
            return _GateResult(False, "canary-failed", detail)
        return _GateResult(True, "", "gates and canaries passed")
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
    if merged.returncode != 0:
        # Never leave conflict markers in the live checkout (launchd scripts and mounted
        # config read from it): back the merge out and report failure.
        git_run(main, ["merge", "--abort"])
        return False
    return True


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


def _canaries_pass(spec: JobSpec, cwd: Path, runner: CanaryRunner) -> tuple[bool, str]:
    canaries = [step for step in spec.steps if step.canary_of]
    for step in canaries:
        code, output = runner(step.argv, cwd, step.timeout_seconds)
        if code != 0:
            return False, f"{step.step_id} exited {code}\n{output}"
    return True, ""


def _subprocess_gate(argv: Sequence[str], cwd: Path) -> int:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, check=False, timeout=GATE_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return proc.returncode


def _subprocess_canary(argv: Sequence[str], cwd: Path, timeout_s: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            list(argv), cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout_s
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, "\n".join(part for part in (proc.stdout, proc.stderr) if part)


def _subprocess_verdict(argv: Sequence[str]) -> int:
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False, timeout=120)
    return proc.returncode


def _retry_due(stamp: str) -> bool:
    try:
        due = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return due <= datetime.now(UTC)
