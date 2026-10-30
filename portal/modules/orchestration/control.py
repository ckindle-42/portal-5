"""Telegram control plane — host-side executor for Jarvis control requests.

The bot (Docker) and the queue runner (host) share only the arm SQLite store:
the bot writes ``control_requests`` rows, this module executes them through the
same functions the ``portal arm`` CLI uses, and replies ride the outbox.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from portal_channels.telegram.arm_bridge import (
    ArmTelegramStore,
    ControlRequest,
    default_arm_telegram_path,
)

CANARY_SUMMARY = re.compile(
    r"^CANARY\s+(\S+):\s+(\w+)\s*\((\d+) setup row\(s\) of (\d+)\)", re.MULTILINE
)
DESTRUCTIVE_VERBS = frozenset({"cancel", "merge"})
NEEDS_JOB_VERBS = frozenset({"requeue", "cancel", "canary", "merge", "keep", "escalate", "diff"})
RESULT_MAX_CHARS = 3900
NOTICE_KIND = "control"
PAUSE_FLAG = "paused"


def telegram_control_enabled(policy: object) -> bool:
    """True only for the explicit boolean the operator sets under queue.telegram_control."""
    if not isinstance(policy, dict):
        return False
    block = policy.get("telegram_control")
    return isinstance(block, dict) and block.get("enabled") is True


def load_queue_policy() -> dict[str, Any]:
    """The queue block of config/orchestration_arm.yaml, as both bot and runner see it."""
    path = Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    queue = config.get("queue", {}) if isinstance(config, dict) else {}
    return queue if isinstance(queue, dict) else {}


@dataclass(frozen=True)
class ControlContext:
    root: Path
    repo_root: Path
    store: ArmTelegramStore
    notices: Any


def digest_inputs(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(root) as ledger:
        items = ledger.items()
        for item in items:
            item["waiting_since"] = ledger.waiting_since(str(item["task_id"]))
    receipts: dict[str, dict[str, Any]] = {}
    for item in items:
        payload = read_receipt(root, str(item["task_id"]))
        if payload is not None:
            receipts[str(item["task_id"])] = payload
    return items, receipts


def read_receipt(root: Path, task_id: str) -> dict[str, Any] | None:
    try:
        payload: Any = json.loads((root / task_id / "receipt.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def queue_items(root: Path) -> list[dict[str, Any]]:
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(root) as ledger:
        return ledger.items()


def cancel_job(root: Path, task_id: str, reason: str, *, force: bool = False) -> str:
    """Mark a queued task blocked/CANCELLED; refuse a live runner unless forced."""
    from portal.modules.orchestration.jobs import release_window_claim
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(root) as ledger:
        ledger.cancel_task(task_id, reason, force=force)
    released = release_window_claim(task_id)
    text = f"cancelled {task_id}"
    if released:
        text += "; released the quiet-host window claim"
    return text


def requeue_job(root: Path, task_id: str, repo_root: Path) -> str:
    """Requeue a blocked or done job from the spec in its job directory."""
    from portal.modules.orchestration.jobs import job_json, parse_job_spec
    from portal.modules.orchestration.queue import QueueLedger

    spec_path = root / task_id / "job.json"
    if not spec_path.is_file():
        raise ValueError(f"no job spec for {task_id}")
    spec = parse_job_spec(
        yaml.safe_load(spec_path.read_text(encoding="utf-8")), repo_root=repo_root
    )
    if spec.job_id != task_id:
        raise ValueError(f"job spec id {spec.job_id} does not match queue id {task_id}")
    with QueueLedger(root) as ledger:
        ledger.requeue_job(task_id, job_json(spec))
    spec_path.write_text(
        json.dumps(spec.as_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return f"requeued {task_id}"


def escalate_blocked_job(root: Path, job_id: str, repo_root: Path, policy: dict[str, Any]) -> str:
    """Ask a cloud lane to repair one blocked job (queue.escalation must be enabled)."""
    from portal.modules.orchestration.escalate import Escalator, escalation_enabled
    from portal.modules.orchestration.queue import QueueLedger, QueueRun
    from portal.modules.orchestration.telegram import TelegramNoticeSink

    if not escalation_enabled(policy):
        raise ValueError("queue.escalation.enabled is false")
    with QueueLedger(root) as ledger:
        item = ledger.task(job_id)
    if item is None:
        raise ValueError(f"no queue task: {job_id}")
    receipt = root / job_id / "receipt.json"
    return Escalator(root, repo_root=repo_root, notices=TelegramNoticeSink()).handle(
        item, QueueRun("BLOCKED", job_id, receipt if receipt.is_file() else None)
    )


def canary_summary(root: Path, job_id: str) -> str:
    """One-line SETUP/MODEL counts from the job's last canary step output."""
    receipt = read_receipt(root, job_id)
    if receipt is None:
        return f"no receipt for {job_id}"
    for step in reversed(receipt.get("steps", [])):
        if not isinstance(step, dict):
            continue
        argv = step.get("argv")
        if not (isinstance(argv, list) and argv and str(argv[-1]) == "--canary"):
            continue
        text = str(step.get("stdout_tail") or "")
        matches = list(CANARY_SUMMARY.finditer(text))
        if not matches:
            return f"canary {job_id}: no CANARY summary in its output"
        cid, verdict = matches[-1].group(1), matches[-1].group(2)
        setup, total = int(matches[-1].group(3)), int(matches[-1].group(4))
        return (
            f"canary {job_id} [{cid}]: {verdict} — "
            f"SETUP {setup}/{total}, MODEL {total - setup}/{total}"
        )
    return f"canary {job_id}: no canary step in its receipt"


def _status_text(ctx: ControlContext, args: str) -> str:
    """Running and queued jobs, then the last day's finished ones; older history is counted.
    `status all` lists everything (queue-status has the full ledger)."""
    from portal.modules.orchestration.queue import _parsed

    items = queue_items(ctx.root)
    if not items:
        return "queue empty"
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    active = [i for i in items if str(i["state"]) in {"running", "queued", "waiting"}]
    recent = [
        i
        for i in items
        if i not in active
        and (
            args.strip() == "all"
            # cancelled jobs were retired on purpose; only `status all` shows them
            or (_parsed(i.get("updated_at")) >= cutoff and i.get("receipt_status") != "CANCELLED")
        )
    ]
    lines = []
    for item in active + recent:
        line = f"{item['task_id']} {item['state']}"
        if item.get("receipt_status"):
            line += f" {item['receipt_status']}"
        if item.get("last_error"):
            line += f" — {item['last_error']}"
        lines.append(line)
    older = len(items) - len(active) - len(recent)
    if older:
        lines.append(f"(+{older} older jobs; `status all` lists them)")
    return "\n".join(lines)[-RESULT_MAX_CHARS:]


def _digest_text(ctx: ControlContext, args: str) -> str:
    from portal.modules.orchestration.queue import build_queue_digest

    return str(build_queue_digest(*digest_inputs(ctx.root)))


def _pause(ctx: ControlContext, args: str) -> str:
    ctx.store.set_control_flag(PAUSE_FLAG, "1")
    return "queue paused: no new jobs picked; a running job is unaffected"


def _resume(ctx: ControlContext, args: str) -> str:
    ctx.store.set_control_flag(PAUSE_FLAG, "0")
    return "queue resumed"


def _requeue(ctx: ControlContext, args: str) -> str:
    return str(requeue_job(ctx.root, args, ctx.repo_root))


def _cancel(ctx: ControlContext, args: str) -> str:
    return str(cancel_job(ctx.root, args, "cancelled from Telegram"))


def _canary(ctx: ControlContext, args: str) -> str:
    return str(canary_summary(ctx.root, args))


def _held(ctx: ControlContext, args: str) -> str:
    from portal.modules.orchestration.escalate import held_escalations

    held = held_escalations(ctx.root)
    if not held:
        return "no held escalations"
    lines = [
        f"{h['job_id']} lane {h['lane_id']} attempt {h['attempt']} held since {h['created_at']}"
        for h in held
    ]
    return "\n".join(lines)[-RESULT_MAX_CHARS:]


def _escalator(ctx: ControlContext) -> Any:
    from portal.modules.orchestration.escalate import Escalator

    return Escalator(ctx.root, repo_root=ctx.repo_root, notices=ctx.notices)


def _merge(ctx: ControlContext, args: str) -> str:
    return str(_escalator(ctx).merge_held(args))


def _keep(ctx: ControlContext, args: str) -> str:
    return str(_escalator(ctx).keep_held(args))


def _diff(ctx: ControlContext, args: str) -> str:
    return str(_escalator(ctx).held_diffstat(args))


def _escalate(ctx: ControlContext, args: str) -> str:
    from portal.modules.orchestration.service import load_arm_config

    policy = load_arm_config(
        Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"
    ).get("queue", {})
    return escalate_blocked_job(
        ctx.root, args, ctx.repo_root, policy if isinstance(policy, dict) else {}
    )


_VERBS: dict[str, Callable[[ControlContext, str], str]] = {
    "status": _status_text,
    "digest": _digest_text,
    "pause": _pause,
    "resume": _resume,
    "requeue": _requeue,
    "cancel": _cancel,
    "canary": _canary,
    "held": _held,
    "merge": _merge,
    "keep": _keep,
    "diff": _diff,
    "escalate": _escalate,
}
VERB_NAMES = frozenset(_VERBS)


# Read-only verbs the bot answers itself from the shared tasks dir, so a reply never waits
# for the runner to finish its current job (10-30: `status` sat "Queued" behind a long run).
DIRECT_VERBS = frozenset({"status", "digest", "canary"})


def answer_direct(verb: str, args: str, root: Path, store: ArmTelegramStore) -> str:
    ctx = ControlContext(root=root, repo_root=root, store=store, notices=None)
    return _VERBS[verb](ctx, args)


def execute_control(request: ControlRequest, ctx: ControlContext) -> str:
    handler = _VERBS.get(request.verb)
    if handler is None:
        return f"refused: unknown verb {request.verb}"
    try:
        return str(handler(ctx, request.args))
    except Exception as exc:  # noqa: BLE001 — a fault becomes the row's result, not a crash
        return f"failed: {type(exc).__name__}: {exc}"[:RESULT_MAX_CHARS]


def _reply_text(request: ControlRequest, result: str) -> str:
    head = f"Jarvis {request.verb}" + (f" {request.args}" if request.args else "")
    return f"{head}\n{result}"[:RESULT_MAX_CHARS]


def process_control_requests(
    store: ArmTelegramStore, root: Path, repo_root: Path, notices: Any = None
) -> bool:
    """Execute due control requests; returns the runner pause state."""
    store.expire_stale_controls()
    ctx = ControlContext(root=root, repo_root=repo_root, store=store, notices=notices)
    for request in store.claim_control_requests():
        result = execute_control(request, ctx)
        status = "refused" if result.startswith("refused:") else "done"
        store.finish_control(request.id, status, result)
        store.notify(request.id, NOTICE_KIND, _reply_text(request, result))
    return store.control_flag(PAUSE_FLAG) == "1"


def build_control_poller(
    root: Path, repo_root: Path, notices: Any, policy: object
) -> Callable[[], bool] | None:
    """The runner's per-loop poll hook, or None while the flag is off."""
    if not telegram_control_enabled(policy):
        return None
    store = ArmTelegramStore(default_arm_telegram_path())
    log = logging.getLogger(__name__)

    def poll() -> bool:
        try:
            return process_control_requests(store, root, repo_root, notices)
        except Exception as exc:  # noqa: BLE001 — control faults must not kill the runner
            log.warning("control poll failed: %s", exc)
            return False

    return poll


def control_requests_text(limit: int = 10) -> str:
    """The last control requests for `portal arm queue-status`; empty when none."""
    path = default_arm_telegram_path()
    if not path.is_file():
        return ""
    rows = ArmTelegramStore(path).latest_control_requests(limit)
    lines = []
    for row in rows:
        line = f"{row.created_at} {row.status} user {row.user_id} {row.verb}"
        if row.args:
            line += f" {row.args}"
        if row.result:
            line += f" — {' '.join(row.result.split())[:120]}"
        lines.append(line)
    return "\n".join(lines)
