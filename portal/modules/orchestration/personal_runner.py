"""One personal task per poll: the Pipeline tool loop, capped at 8 hops.

The planner and the confirm gate are added by later steps. This module posts to
the Pipeline; it does not open a third tool framework.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from portal.modules.orchestration.personal_policy import FAST_WORKSPACE, HOP_CAP, READ_TOOLS
from portal.modules.orchestration.personal_store import PersonalStore, PersonalTask
from portal.modules.orchestration.personal_tools import run_read_tool, tool_schema
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
    if task is None or task.status != "queued":
        return None
    claimed = store.update(task.id, status="running", expect=frozenset({"queued"}))
    if claimed is None:
        return None
    try:
        return _run_tool_loop(root, store, claimed, _caller(caller), notices)
    except PermissionError as exc:
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


def _run_tool_loop(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    caller: PipelineCaller,
    notices: Any,
) -> PersonalRun:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Answer the personal task with the provided tools only. "
                "queue_status and read_receipt are local reads of the tasks directory. "
                "Do not invent jobs."
            ),
        },
        {"role": "user", "content": task.text},
    ]
    content, hops, called = _hop_loop(caller, messages, root, FAST_WORKSPACE, sorted(READ_TOOLS))
    _finish(root, store, task, "done", content, FAST_WORKSPACE, hops, called, notices)
    return PersonalRun(task.id, "done")


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
            if name not in READ_TOOLS or name == "recall":
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
    local = [name for name in tool_names if name != "recall"]
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
        receipt_path=str(path),
        tool_log=json.dumps(called),
        expect=frozenset({"running", "queued", "confirmed", "pending"}),
    )
    if notices is not None and content:
        notices.notify(task.id, "personal", content)
