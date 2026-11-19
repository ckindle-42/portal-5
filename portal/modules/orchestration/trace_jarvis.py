"""``portal trace`` jarvis section: one live personal request, end to end.

Submitted through the pipeline MCP's ``jarvis_submit`` (the tool Open WebUI calls),
confirmed exactly as the operator confirms, executed by the live arm queue runner, and
judged by its receipt; a confirm-required write task must stay ``pending`` until
confirmed. Contributed through the plugin seam like the lab section; the platform CLI
never imports module code. Rows it creates are deleted; receipt dirs stay for inspection.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from portal.modules.orchestration.personal_policy import READ_TOOLS
from portal.modules.orchestration.personal_runner import (
    _PERSONAL_LIVE_STATUSES as LIVE,
)
from portal.modules.orchestration.personal_runner import (
    _PERSONAL_TERMINAL_STATUSES as TERMINAL,
)
from portal.modules.orchestration.personal_runner import (
    apply_personal_decision,
    cancel_personal_task,
)
from portal.modules.orchestration.personal_store import PersonalStore
from portal.platform.inference.cli.trace import mcps
from portal.platform.inference.cli.trace.context import env_value

REQUEST = "List the three largest files in /workspace/generated and report their sizes."
WRITE_REQUEST = (
    "Remember that the portal trace jarvis section held a write task for confirmation today."
)
POLL_S = 2.0
DEFAULT_WAIT_S = 420.0
HOLD_POLLS = 2
_FILE = re.compile(r"[\w.\-/\\]+\.[A-Za-z0-9]{2,6}")


def _hop(
    name: str, status: str, observed: object = "", expected: str = "", detail: object = ""
) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "observed": str(observed),
        "expected": expected,
        "detail": str(detail),
    }


def _tasks_root() -> Path:
    from portal.platform.mcp_host.workspace import get_generated_dir

    return get_generated_dir("tasks")


def _generated_root() -> Path:
    from portal.platform.mcp_host.workspace import get_workspace_root

    return get_workspace_root() / "generated"


def _wait_s() -> float:
    try:
        return max(30.0, float(env_value("PORTAL_TRACE_JARVIS_WAIT_S", str(DEFAULT_WAIT_S))))
    except ValueError:
        return DEFAULT_WAIT_S


def _submit_hop(user_id: str, text: str) -> tuple[dict[str, str], str]:
    """One submission through the same MCP client the personal runner uses."""
    url = mcps.servers()["pipeline"]
    payload = mcps.mcp_call(url, "jarvis_submit", {"text": text, "user_id": user_id}, 30.0)
    task_id = str(payload.get("id") or "")
    if payload.get("error") or not task_id.startswith("pt-"):
        return _hop("mcp submit", "FAIL", str(payload)[:96], "queued <pt-id>"), ""
    return _hop(
        "mcp submit", "PASS", str(payload.get("reply") or task_id), "queued <pt-id>"
    ), task_id


def _wait_terminal(root: Path, task_id: str, wait_s: float) -> tuple[str, bool]:
    """Poll one row to a terminal status, applying the operator confirm once."""
    get = PersonalStore(root).get
    deadline = time.monotonic() + wait_s
    confirmed = False
    status = ""
    while time.monotonic() < deadline:
        task = get(task_id)
        if task is None:
            return "missing", confirmed
        status = task.status
        if status == "pending" and not confirmed:
            confirmed = apply_personal_decision(root, task_id, "confirm") == "confirmed"
            continue
        if status in TERMINAL:
            return status, confirmed
        time.sleep(POLL_S)
    return status or "timeout", confirmed


def _terminal_hop(status: str, confirmed: bool, wait_s: float, error: str = "") -> dict[str, str]:
    state = f"status={status} confirm={'applied' if confirmed else 'not-required'}"
    if status not in TERMINAL:
        return _hop(
            "confirm + terminal",
            "FAIL",
            state,
            "terminal within the wait budget",
            f"timed out after {wait_s:.0f}s; last status {status}",
        )
    ok = status == "done"
    return _hop(
        "confirm + terminal",
        "PASS" if ok else "FAIL",
        state,
        "status done",
        error if not ok else "",
    )


def _receipt(root: Path, task_id: str) -> dict[str, Any]:
    path = root / task_id / "receipt.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}
    return payload if isinstance(payload, dict) else {"_error": "not an object", "_path": str(path)}


def _size_forms(size: int) -> list[str]:
    forms = [str(size), f"{size:,}"]
    for unit, div in (("KB", 1024), ("MB", 1024**2), ("GB", 1024**3)):
        value = size / div
        if value >= 1:
            forms += [
                f"{value:.1f} {unit}",
                f"{value:.0f} {unit}",
                f"{value:.1f} {unit[0]}i{unit[1]}",
            ]
    return forms


def _named_file_with_size(text: str, root: Path) -> tuple[str, int] | None:
    """A real file under generated/ whose name and size the answer names."""
    seen: list[str] = []
    for token in _FILE.findall(text):
        name = token.replace("\\", "/").rsplit("/", 1)[-1].strip(".,;:")
        if not name or name in seen:
            continue
        seen.append(name)
        for path in root.rglob(name):
            if not path.is_file():
                continue
            size = path.stat().st_size
            if any(form in text for form in _size_forms(size)):
                return name, size
    return None


def _receipt_hop(payload: dict[str, Any]) -> dict[str, str]:
    """The receipt must show done, a read tool, a real named file, and no cloud handoff."""
    if "_error" in payload:
        return _hop(
            "receipt proof",
            "FAIL",
            payload["_error"],
            "a readable receipt",
            str(payload.get("_path")),
        )
    status = str(payload.get("status") or "")
    tools = [str(tool) for tool in payload.get("tool_calls") or [] if isinstance(tool, str)]
    read = "workspace_files" in tools or any(tool in READ_TOOLS for tool in tools)
    named = _named_file_with_size(str(payload.get("final_text") or ""), _generated_root())
    ok = status == "done" and read and named is not None and "cloud" not in payload
    observed = (
        f"status={status} tools={','.join(tools) or '-'}"
        f" file={named[0] if named else '-'} size={named[1] if named else '-'}"
    )
    missed: list[str] = []
    if status != "done":
        missed.append(f"status is {status}, not done")
    if not read:
        missed.append("no read tool in tool_calls")
    if named is None:
        missed.append("final_text names no generated file with its size")
    if "cloud" in payload:
        missed.append("receipt records a cloud handoff")
    return _hop(
        "receipt proof",
        "PASS" if ok else "FAIL",
        observed[:120],
        "done + read tool + real file",
        "" if ok else "; ".join(missed),
    )


def _wait_pending_hold(root: Path, task_id: str, wait_s: float) -> str:
    """Wait for ``pending``, then require it to hold across HOLD_POLLS polls."""
    get = PersonalStore(root).get
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        task = get(task_id)
        if task is None:
            return "missing"
        if task.status == "pending":
            for _ in range(HOLD_POLLS):
                time.sleep(POLL_S)
                held = get(task_id)
                if held is None or held.status != "pending" or held.tool_log != "[]":
                    return f"left pending: {held.status if held else 'missing'}"
            return "pending"
        if task.status in TERMINAL:
            return task.status
        time.sleep(POLL_S)
    return "timeout"


def _negative_hops(
    root: Path, user_id: str, wait_s: float, created: list[str]
) -> list[dict[str, str]]:
    submit, task_id = _submit_hop(user_id, WRITE_REQUEST)
    if not task_id:
        return [submit]
    created.append(task_id)
    outcome = _wait_pending_hold(root, task_id, wait_s)
    reason = "" if outcome == "pending" else f"outcome={outcome} after {wait_s:.0f}s"
    pending = _hop(
        "write stays pending",
        "PASS" if outcome == "pending" else "FAIL",
        outcome,
        "pending until confirm",
        reason,
    )
    if outcome != "pending":
        return [submit, pending]
    decided = apply_personal_decision(root, task_id, "abort")
    return [
        submit,
        pending,
        _hop(
            "write abort",
            "PASS" if decided == "cancelled" else "FAIL",
            f"abort -> {decided}",
            "cancelled",
        ),
    ]


def _cleanup_hop(root: Path, created: list[str]) -> dict[str, str]:
    for task_id in created:
        task = PersonalStore(root).get(task_id)
        if task is not None and task.status in LIVE:
            cancel_personal_task(root, task_id)
    deleted = "nothing to delete"
    if created:
        db = sqlite3.connect(root / "personal_tasks.sqlite3", timeout=5)
        try:
            db.execute("PRAGMA busy_timeout = 5000")
            marks = ",".join("?" for _ in created)
            db.execute(f"DELETE FROM personal_tasks WHERE id IN ({marks})", created)
            db.commit()
            deleted = f"deleted {len(created)}"
        finally:
            db.close()
    remaining = [t for t in created if PersonalStore(root).get(t) is not None]
    return _hop(
        "rows cleanup",
        "PASS" if not remaining else "FAIL",
        f"{deleted}; receipts kept for inspection",
        "rows deleted",
        f"remaining rows: {remaining}" if remaining else "",
    )


def _positive_hops(
    root: Path, user_id: str, wait_s: float, created: list[str]
) -> list[dict[str, str]]:
    submit, task_id = _submit_hop(user_id, REQUEST)
    if not task_id:
        return [submit]
    created.append(task_id)
    status, confirmed = _wait_terminal(root, task_id, wait_s)
    payload = _receipt(root, task_id)
    terminal = _terminal_hop(status, confirmed, wait_s, str(payload.get("error") or ""))
    return [submit, terminal] if status != "done" else [submit, terminal, _receipt_hop(payload)]


def run() -> list[dict[str, str]]:
    """Submit, confirm as the operator would, judge the receipt, hold the negative, clean up."""
    user_id = next(
        (t.strip() for t in env_value("TELEGRAM_USER_IDS").split(",") if t.strip().isdigit()), ""
    )
    if not user_id:
        return [
            _hop(
                "jarvis prereqs",
                "WARN",
                "no allowlisted TELEGRAM_USER_IDS id",
                "operator id",
                "set TELEGRAM_USER_IDS to run this section",
            )
        ]
    root, wait_s = _tasks_root(), _wait_s()
    created: list[str] = []
    hops: list[dict[str, str]] = []
    try:
        hops += _positive_hops(root, user_id, wait_s, created)
        hops += _negative_hops(root, user_id, wait_s, created)
    finally:
        # Its own rows are deleted even when a phase faults; the fault itself is the
        # section hop the trace command renders.
        hops.append(_cleanup_hop(root, created))
    return hops
