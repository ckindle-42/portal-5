"""One personal task per poll: plan, confirm when risky, then one tool loop.

Risky steps wait for a Telegram confirm and still do not run shell, writes, or
memory changes. Hard-denied fleets are rejected before any Pipeline call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from portal.modules.orchestration.personal_policy import (
    FAST_WORKSPACE,
    HELD_TEXT,
    HOP_CAP,
    PersonalPlan,
    hidden_fleet_ids,
    parse_planner_json,
    planner_body,
    text_gate,
    validate_personal_plan,
    workspace_for,
)
from portal.modules.orchestration.personal_store import PersonalStore, PersonalTask
from portal.modules.orchestration.personal_tools import LOCAL_TOOLS, run_read_tool, tool_schema
from portal.modules.orchestration.worker import Engine, _call_arguments, _response_parts


@dataclass(frozen=True)
class Completion:
    content: str
    tool_calls: tuple[dict[str, Any], ...] = ()
    pipeline_hops: int = 0


class PipelineCaller(Protocol):
    def complete(self, body: dict[str, Any]) -> Completion: ...


@dataclass(frozen=True)
class PersonalRun:
    task_id: str
    status: str


class EngineCaller:
    """Stream one Pipeline chat and count the tool hops it actually dispatched."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.engine = Engine("personal", "", base_url, api_key)

    def complete(self, body: dict[str, Any]) -> Completion:
        audits: list[dict[str, Any]] = []

        def on_event(event: dict[str, Any]) -> None:
            if event.get("type") == "exec_audit" and isinstance(event.get("tool_calls"), list):
                audits.append(event)

        response = self.engine.chat({**body, "stream": True}, 300, on_event)
        content, calls = _response_parts(response)
        hops = sum(len(event["tool_calls"]) for event in audits)
        return Completion(content, tuple(calls), hops)


def poll_personal_tasks(
    root: Path,
    notices: Any,
    caller: PipelineCaller | None = None,
) -> PersonalRun | None:
    """Run the oldest queued personal task. A Pipeline fault is stored, not raised."""
    store = PersonalStore(root)
    task = store.oldest_runnable()
    if task is None:
        return None
    if task.status == "confirmed":
        return _hold_confirmed(root, store, task, notices)
    if task.status != "queued":
        return None
    claimed = store.update(task.id, status="running", expect=frozenset({"queued"}))
    if claimed is None:
        return None
    try:
        return _run_planned(root, store, claimed, _caller(caller), notices)
    except (PermissionError, ValueError) as exc:
        _finish(
            root, store, claimed, "rejected", "", FAST_WORKSPACE, 0, [], notices, error=str(exc)
        )
        return PersonalRun(claimed.id, "rejected")
    except Exception as exc:  # noqa: BLE001 — one personal task must not kill queue-run
        _finish(root, store, claimed, "blocked", "", FAST_WORKSPACE, 0, [], notices, error=str(exc))
        return PersonalRun(claimed.id, "blocked")


def _caller(caller: PipelineCaller | None) -> PipelineCaller:
    if caller is not None:
        return caller
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    if not api_key:
        raise RuntimeError("PIPELINE_API_KEY is not set")
    url = os.environ.get("PORTAL_ARM_PIPELINE_URL", "http://127.0.0.1:9099")
    return EngineCaller(url, api_key)


def apply_personal_decision(root: Path, task_id: str, action: str) -> str | None:
    """Confirm lets the runner proceed. Abort cancels. Other states stay put."""
    store = PersonalStore(root)
    task = store.get(task_id)
    if task is None or task.status != "pending":
        return None
    status = "confirmed" if action == "confirm" else "cancelled"
    if action not in {"confirm", "abort"}:
        return None
    updated = store.update(task_id, status=status, expect=frozenset({"pending"}))
    return None if updated is None else updated.status


def _hold_confirmed(
    root: Path, store: PersonalStore, task: PersonalTask, notices: Any
) -> PersonalRun | None:
    claimed = store.update(task.id, status="running", expect=frozenset({"confirmed"}))
    if claimed is None:
        return None
    plan, tools = _stored_plan(claimed.plan_json)
    _finish(
        root,
        store,
        claimed,
        "held",
        HELD_TEXT,
        workspace_for(tools),
        0,
        [],
        notices,
        plan=plan,
    )
    return PersonalRun(claimed.id, "held")


def _stored_plan(plan_json: str | None) -> tuple[dict[str, Any] | None, set[str]]:
    if not plan_json:
        return None, set()
    try:
        payload = json.loads(plan_json)
    except ValueError:
        return None, set()
    if not isinstance(payload, dict):
        return None, set()
    tools: set[str] = set()
    steps = payload.get("steps", payload.get("bites"))
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and isinstance(step.get("tools"), list):
                tools.update(str(name) for name in step["tools"])
    return payload, tools


def _run_planned(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    caller: PipelineCaller,
    notices: Any,
) -> PersonalRun:
    hidden = _hidden_fleets()
    if text_gate(task.text, hidden) == "deny":
        raise ValueError("denied before any call")
    plan = _validated_plan(task, caller, root, hidden)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Execute only this validated plan. Use only the tools it names. "
                "Do not invent jobs or paths."
            ),
        },
        {"role": "user", "content": json.dumps(plan.payload, sort_keys=True)},
    ]
    content, hops, called = _hop_loop(caller, messages, root, plan.workspace, sorted(plan.tools))
    _finish(
        root, store, task, "done", content, plan.workspace, hops, called, notices, plan=plan.payload
    )
    return PersonalRun(task.id, "done")


def _request_confirm(
    store: PersonalStore, task: PersonalTask, plan: PersonalPlan, notices: Any
) -> None:
    store.update(
        task.id,
        status="pending",
        plan_json=json.dumps(plan.payload, sort_keys=True),
        tool_log="[]",
        expect=frozenset({"running"}),
    )
    control = getattr(notices, "store", None)
    if control is not None:
        control.add_control_request(0, "personal", task.id, status="pending")
    if notices is not None:
        notices.notify(task.id, "personal", f"Confirm {task.id} before any tool call?")


def _validated_plan(
    task: PersonalTask, caller: PipelineCaller, root: Path, hidden: frozenset[str]
) -> PersonalPlan:
    result = caller.complete(planner_body(task.text))
    if result.tool_calls:
        raise ValueError("planner returned a tool call")
    return validate_personal_plan(parse_planner_json(result.content), root, hidden)


def _hidden_fleets() -> frozenset[str]:
    import yaml

    path = Path(__file__).resolve().parents[3] / "config" / "portal.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return hidden_fleet_ids(loaded if isinstance(loaded, dict) else {})


def _hop_loop(
    caller: PipelineCaller,
    messages: list[dict[str, Any]],
    root: Path,
    workspace: str,
    tool_names: list[str],
) -> tuple[str, int, list[str]]:
    hops = 0
    called: list[str] = []
    content = ""
    while hops < HOP_CAP:
        body = _tool_body(workspace, messages, tool_names, HOP_CAP - hops)
        result = caller.complete(body)
        spent = (
            result.pipeline_hops if result.pipeline_hops > 0 else (1 if result.tool_calls else 0)
        )
        hops += spent
        content = result.content
        if not result.tool_calls or hops >= HOP_CAP:
            break
        messages.append(
            {"role": "assistant", "content": content, "tool_calls": list(result.tool_calls)}
        )
        for call in result.tool_calls:
            if hops >= HOP_CAP:
                break
            name = str((call.get("function") or {}).get("name") or "")
            if name not in tool_names or name not in LOCAL_TOOLS:
                raise PermissionError(f"tool outside the personal allowlist: {name}")
            output = run_read_tool(name, _call_arguments(call), root)
            called.append(name)
            hops += 1
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": output})
        if hops >= HOP_CAP:
            break
    return content, min(hops, HOP_CAP), called


def _tool_body(
    workspace: str, messages: list[dict[str, Any]], tool_names: list[str], hops_left: int
) -> dict[str, Any]:
    local = [name for name in tool_names if name in LOCAL_TOOLS]
    return {
        "model": workspace,
        "messages": messages,
        "portal_bite_tools": list(tool_names),
        "portal_bite_max_hops": max(1, min(HOP_CAP, hops_left)),
        "tools": [tool_schema(name) for name in local],
        "exec_audit": True,
        "temperature": 0.1,
    }


def _finish(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    status: str,
    content: str,
    workspace: str,
    hops: int,
    called: list[str],
    notices: Any,
    *,
    error: str = "",
    plan: dict[str, Any] | None = None,
) -> None:
    receipt = {
        "workspace": workspace,
        "hops": hops,
        "final_text": content,
        "tool_calls": called,
        "plan": plan,
        "error": error,
    }
    task_dir = root / task.id
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "receipt.json"
    path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    store.update(
        task.id,
        status=status,
        plan_json=None if plan is None else json.dumps(plan, sort_keys=True),
        receipt_path=str(path),
        tool_log=json.dumps(called),
        expect=frozenset({"running", "queued", "confirmed", "pending"}),
    )
    if notices is not None and content:
        notices.notify(task.id, "personal", content)
