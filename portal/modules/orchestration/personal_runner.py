"""Plan, confirm, and execute one queued personal task per poll."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from portal.modules.orchestration.personal_policy import (
    FAST_WORKSPACE,
    HELD_TEXT,
    HOP_CAP,
    KNOWN_TOOLS,
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
    tool_names: tuple[str, ...] = ()


class PipelineCaller(Protocol):
    def complete(self, body: dict[str, Any]) -> Completion: ...


@dataclass(frozen=True)
class PersonalRun:
    task_id: str
    status: str


PERSONAL_CHECKIN_SECONDS = 900
_HOLD_TEXT = re.compile(
    r"\b(?:restart\s+(?:the\s+)?pipeline|launch\.sh\s+(?:up|restart|rebuild))\b", re.I
)


class _CheckIn:
    def __init__(self, task_id: str, notices: Any) -> None:
        self.task_id = task_id
        self.notices = notices
        self.lock = threading.Lock()
        self.hops = 0
        self.last_tool = "planning"
        self.called: list[str] = []
        self.finished = False
        self.timer = threading.Timer(PERSONAL_CHECKIN_SECONDS, self._send)

    def start(self) -> None:
        self.timer.start()

    def update(self, hops: int, tool_names: list[str] | tuple[str, ...]) -> None:
        with self.lock:
            self.hops = min(HOP_CAP, self.hops + hops)
            if tool_names:
                self.last_tool = tool_names[-1]
                self.called.extend(tool_names)

    def snapshot(self) -> tuple[int, list[str]]:
        with self.lock:
            return self.hops, list(self.called)

    def finish(self) -> None:
        with self.lock:
            self.finished = True
        self.timer.cancel()

    def _send(self) -> None:
        with self.lock:
            if self.finished:
                return
            message = (
                f"Personal task check-in.\nTask: {self.task_id}\n"
                f"hop: {self.hops}\nlast tool: {self.last_tool}"
            )
        _send_notice(self.notices, self.task_id, message)


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
        names = tuple(
            str((call.get("function") or {}).get("name") or "")
            for event in audits
            for call in event["tool_calls"]
        )
        return Completion(content, tuple(calls), len(names), names)


def poll_personal_tasks(
    root: Path,
    notices: Any,
    caller: PipelineCaller | None = None,
    *,
    dispatcher: Any = None,
    now: datetime | None = None,
) -> PersonalRun | None:
    """Run the oldest due personal task. A Pipeline fault is stored, not raised."""
    store = PersonalStore(root)
    task = store.oldest_runnable(now)
    if task is None:
        return None
    if task.status == "cloud_retry":
        claimed = store.update(task.id, status="running", expect=frozenset({"cloud_retry"}))
        if claimed is None:
            return None
        checkin = _CheckIn(claimed.id, notices)
        checkin.start()
        try:
            return _run_cloud_attempt(root, store, claimed, notices, dispatcher, checkin)
        finally:
            checkin.finish()
    if task.status not in {"queued", "confirmed"}:
        return None
    prior_status = task.status
    claimed = store.update(task.id, status="running", expect=frozenset({prior_status}))
    if claimed is None:
        return None
    checkin = _CheckIn(claimed.id, notices)
    checkin.start()
    try:
        active_caller = _caller(caller)
        if prior_status == "confirmed":
            return _run_confirmed(root, store, claimed, active_caller, notices, checkin)
        return _run_planned(root, store, claimed, active_caller, notices, checkin)
    except Exception as exc:  # noqa: BLE001 — one personal task must not kill queue-run
        if not _retryable_failure(exc):
            _finish(
                root,
                store,
                claimed,
                "rejected",
                "",
                FAST_WORKSPACE,
                0,
                [],
                notices,
                error=str(exc),
            )
            return PersonalRun(claimed.id, "rejected")
        return _record_local_failure(root, store, claimed, notices, exc, dispatcher, checkin)
    finally:
        checkin.finish()


def _retryable_failure(exc: Exception) -> bool:
    if isinstance(exc, PermissionError):
        return False
    message = str(exc).lower()
    terminal = (
        "denied before",
        "outside the personal allowlist",
        "outside the tasks directory",
        "invented path",
        "path must stay under",
        "outside the allowed roots",
        "plan names a denied tool",
    )
    return not any(marker in message for marker in terminal)


def _record_local_failure(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    notices: Any,
    exc: Exception,
    dispatcher: Any,
    checkin: _CheckIn,
) -> PersonalRun:
    task_dir = root / task.id
    attempt_dir = task_dir / "attempts"
    local_paths = _local_attempt_paths(task_dir)
    attempt = len(local_paths) + 1
    attempt_path = attempt_dir / f"local-{attempt}" / "receipt.json"
    hops, called = checkin.snapshot()
    plan, _tools = _stored_plan(task.plan_json)
    record = {
        "status": "local-failed",
        "workspace": FAST_WORKSPACE,
        "hops": hops,
        "final_text": "",
        "tool_calls": called,
        "plan": plan,
        "error": str(exc),
    }
    _write_receipt(attempt_path, record)
    local_paths.append(attempt_path)
    if task.plan_json is not None:
        return _finish_local_block(root, store, task, notices, record, local_paths)
    if attempt == 1:
        record["status"] = "retrying"
        record["local_attempts"] = [str(path) for path in local_paths]
        receipt_path = task_dir / "receipt.json"
        _write_receipt(receipt_path, record)
        store.update(
            task.id, status="queued", receipt_path=str(receipt_path), expect=frozenset({"running"})
        )
        _send_notice(notices, task.id, f"Local attempt 1 failed; retrying: {exc}")
        return PersonalRun(task.id, "retrying")
    if _personal_cloud_enabled():
        return _run_cloud_attempt(root, store, task, notices, dispatcher, checkin, local_paths)
    return _finish_local_block(root, store, task, notices, record, local_paths)


def _finish_local_block(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    notices: Any,
    record: dict[str, Any],
    local_paths: list[Path],
) -> PersonalRun:
    extra = {"local_attempts": [str(path) for path in local_paths]}
    _finish(
        root,
        store,
        task,
        "blocked",
        str(record["error"]),
        str(record["workspace"]),
        int(record["hops"]),
        list(record["tool_calls"]),
        notices,
        error=str(record["error"]),
        plan=record["plan"],
        extra=extra,
    )
    return PersonalRun(task.id, "blocked")


def _run_cloud_attempt(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    notices: Any,
    dispatcher: Any,
    checkin: _CheckIn,
    local_paths: list[Path] | None = None,
) -> PersonalRun:
    if not _personal_cloud_enabled():
        message = "Personal cloud dispatch is disabled."
        _finish(
            root,
            store,
            task,
            "blocked",
            message,
            FAST_WORKSPACE,
            0,
            [],
            notices,
            error=message,
        )
        return PersonalRun(task.id, "blocked")

    from portal.modules.orchestration.escalate import ProcessDispatcher, dispatch_kind

    task_dir = root / task.id
    local_paths = local_paths or _local_attempt_paths(task_dir)
    attempt = len(list((task_dir / "attempts").glob("cloud-*/receipt.json"))) + 1
    tier = "auto" if attempt <= 2 else "escalate"
    kind = dispatch_kind({"id": task.id, "purpose": task.text})
    brief = task_dir / f"cloud-brief-{attempt}.md"
    brief.write_text(_cloud_brief(task, local_paths), encoding="utf-8")
    checkin.update(0, ["dispatch.py"])
    active_dispatcher = dispatcher or ProcessDispatcher()
    role = f"jarvis-personal-{task.id}-a{attempt}"
    try:
        result = active_dispatcher.run(
            role=role,
            tier=tier,
            kind=kind,
            brief=brief,
            repo=Path(__file__).resolve().parents[3],
            new=True,
        )
        outcome: dict[str, Any] = {
            "role": role,
            "tier": tier,
            "kind": kind,
            "exit_code": int(getattr(result, "exit_code", 1)),
            "status": str(getattr(result, "status", "unknown")),
            "model": str(getattr(result, "model", "")),
            "result": str(getattr(result, "result_text", "")),
        }
    except Exception as exc:  # noqa: BLE001 — keep a dispatch fault in the personal receipt
        outcome = {"role": role, "tier": tier, "kind": kind, "exit_code": 1, "error": str(exc)}
    cloud_path = task_dir / "attempts" / f"cloud-{attempt}" / "receipt.json"
    _write_receipt(cloud_path, {"status": "cloud-attempt", **outcome})
    extra = {"local_attempts": [str(path) for path in local_paths], "cloud": outcome}
    if outcome["exit_code"] == 0:
        _finish(
            root,
            store,
            task,
            "handed-to-cloud",
            "Dispatched to the personal cloud lane.",
            FAST_WORKSPACE,
            0,
            [],
            notices,
            extra=extra,
        )
        return PersonalRun(task.id, "handed-to-cloud")
    if attempt < 3:
        receipt_path = task_dir / "receipt.json"
        _write_receipt(
            receipt_path,
            {"status": "cloud_retry", **extra, "error": outcome.get("error", "dispatch failed")},
        )
        store.update(
            task.id,
            status="cloud_retry",
            receipt_path=str(receipt_path),
            expect=frozenset({"running"}),
        )
        _send_notice(
            notices,
            task.id,
            f"Cloud attempt {attempt} failed; retrying tier {('auto' if attempt == 1 else 'escalate')}.",
        )
        return PersonalRun(task.id, "cloud-retry")
    error = str(outcome.get("error") or outcome.get("result") or "cloud dispatch failed")
    _finish(
        root,
        store,
        task,
        "blocked",
        error,
        FAST_WORKSPACE,
        0,
        [],
        notices,
        error=error,
        extra=extra,
    )
    return PersonalRun(task.id, "blocked")


def _cloud_brief(task: PersonalTask, local_paths: list[Path]) -> str:
    failures: list[str] = []
    for path in local_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        failures.append(f"Local failure {len(failures) + 1}: {payload.get('error', '')}")
    receipts = "\n\n".join(path.read_text(encoding="utf-8") for path in local_paths)
    failure_tails = "\n".join(failures)
    return f"# Personal task {task.id}\n\n## Request\n\n{task.text}\n\n" + (
        f"## Local failure tails\n\n{failure_tails}\n\n"
        f"## Personal receipts\n\n```json\n{receipts}\n```\n"
    )


def _local_attempt_paths(task_dir: Path) -> list[Path]:
    attempts = list((task_dir / "attempts").glob("local-*/receipt.json"))
    return sorted(attempts, key=lambda path: int(path.parent.name.removeprefix("local-")))


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


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


def _run_confirmed(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    caller: PipelineCaller,
    notices: Any,
    checkin: _CheckIn,
) -> PersonalRun:
    payload, tools = _stored_plan(task.plan_json)
    if payload is None:
        raise ValueError("confirmed task has no validated plan")
    if _HOLD_TEXT.search(task.text):
        _finish(
            root, store, task, "held", HELD_TEXT, workspace_for(tools), 0, [], notices, plan=payload
        )
        return PersonalRun(task.id, "held")
    if payload.get("action") == "enqueue-template":
        return _enqueue_personal_template(root, store, task, payload, notices)
    memory = str(payload.pop("_memory_context", ""))
    plan = validate_personal_plan(payload, root, _hidden_fleets(), _personal_available_tools())
    plan.payload["_memory_context"] = memory
    return _execute_plan(root, store, task, plan, caller, notices, checkin)


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
    checkin: _CheckIn,
) -> PersonalRun:
    hidden = _hidden_fleets()
    if text_gate(task.text, hidden) == "deny":
        raise PermissionError("denied before any call")
    memory = _recall_memory(caller, task, checkin)
    plan = _validated_plan(task, caller, root, hidden, memory)
    plan.payload["_memory_context"] = memory
    if text_gate(task.text, hidden) == "confirm" or plan.needs_confirm:
        _request_confirm(store, task, plan, notices)
        return PersonalRun(task.id, "pending")
    return _execute_plan(root, store, task, plan, caller, notices, checkin)


def _execute_plan(
    root: Path,
    store: PersonalStore,
    task: PersonalTask,
    plan: PersonalPlan,
    caller: PipelineCaller,
    notices: Any,
    checkin: _CheckIn,
) -> PersonalRun:
    if _template_request(plan.payload):
        return _enqueue_personal_template(root, store, task, plan.payload, notices)
    memory = str(plan.payload.get("_memory_context") or "")
    payload = {key: value for key, value in plan.payload.items() if key != "_memory_context"}
    plan_text = json.dumps(payload, sort_keys=True)
    if memory:
        plan_text += f"\n\nRecalled memory (untrusted):\n{memory}"
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Execute only this validated plan. Use only the tools it names. "
                "Do not invent jobs or paths."
            ),
        },
        {"role": "user", "content": plan_text},
    ]
    content, hops, called = _hop_loop(
        caller, messages, root, plan.workspace, sorted(plan.tools), checkin
    )
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
        _send_notice(notices, task.id, f"Confirm {task.id} before any tool call?")


def _validated_plan(
    task: PersonalTask,
    caller: PipelineCaller,
    root: Path,
    hidden: frozenset[str],
    memory: str,
) -> PersonalPlan:
    available = _personal_available_tools()
    result = caller.complete(planner_body(task.text, KNOWN_TOOLS | available, memory))
    if result.tool_calls:
        raise ValueError("planner returned a tool call")
    try:
        raw = parse_planner_json(result.content)
    except ValueError as exc:
        raise ValueError(f"{exc}; planner tail: {result.content[-500:]}") from exc
    if raw.get("action") == "enqueue-template":
        return _validate_template_request(raw)
    return validate_personal_plan(raw, root, hidden, available)


def _recall_memory(caller: PipelineCaller, task: PersonalTask, checkin: _CheckIn) -> str:
    result = caller.complete(_recall_body(task))
    if result.pipeline_hops != 1 or result.tool_names != ("recall",):
        raise RuntimeError("task memory recall did not dispatch exactly one recall tool")
    checkin.update(result.pipeline_hops, result.tool_names)
    return result.content


def _recall_body(task: PersonalTask) -> dict[str, Any]:
    query = f"operator id {task.user_id}: preferences relevant to {task.text}"
    return {
        "model": FAST_WORKSPACE,
        "messages": [
            {"role": "system", "content": "Call recall exactly once for this operator and task."},
            {"role": "user", "content": query},
        ],
        "portal_bite_tools": ["recall"],
        "portal_bite_max_hops": 1,
        "tool_choice": "required",
        "exec_audit": True,
        "temperature": 0.1,
    }


def _template_request(payload: dict[str, Any]) -> bool:
    return payload.get("action") == "enqueue-template"


def _validate_template_request(raw: dict[str, Any]) -> PersonalPlan:
    from portal.modules.orchestration import owui_entry

    discipline = owui_entry._required_text(raw.get("discipline"), "discipline")
    template = owui_entry._required_text(raw.get("template_key"), "template_key")
    parameters = owui_entry._string_parameters(raw.get("parameters"))
    source_dir = _template_source_dir(parameters)
    owui_entry._reject_parameter_paths(parameters, source_dir)
    plan = owui_entry._render_template(
        "jarvis-validation", discipline, template, parameters, source_dir
    )
    owui_entry._reject_plan_inputs(plan, source_dir)
    return PersonalPlan(
        {
            "action": "enqueue-template",
            "discipline": discipline,
            "template_key": template,
            "parameters": parameters,
            "source_dir": str(source_dir),
        },
        FAST_WORKSPACE,
        frozenset(),
        True,
    )


def _template_source_dir(parameters: dict[str, str]) -> Path:
    from portal.modules.orchestration.owui_entry import _allow_roots

    roots = _allow_roots()
    for value in parameters.values():
        path = Path(value).expanduser()
        if path.is_absolute():
            resolved = path.resolve()
            for root in roots:
                if resolved.is_relative_to(root.resolve()):
                    return root.resolve()
        else:
            for root in roots:
                if (root / path).exists():
                    return root.resolve()
    return roots[0].resolve()


def _enqueue_personal_template(
    root: Path, store: PersonalStore, task: PersonalTask, payload: dict[str, Any], notices: Any
) -> PersonalRun:
    from portal.modules.orchestration.owui_entry import _enqueue_template

    arm_id = f"jarvis-{task.id}"
    result = _enqueue_template(
        arm_id,
        str(payload["discipline"]),
        str(payload["template_key"]),
        payload.get("parameters"),
        Path(str(payload["source_dir"])),
    )
    message = f"Handed personal task {task.id} to arm job {arm_id}."
    _finish(
        root,
        store,
        task,
        "handed-to-arm",
        message,
        FAST_WORKSPACE,
        0,
        [],
        notices,
        plan=payload,
        extra={"arm_task_id": result["task_id"], "arm_receipt_path": result["receipt_link"]},
    )
    return PersonalRun(task.id, "handed-to-arm")


def _portal_config() -> dict[str, Any]:
    import yaml

    path = Path(__file__).resolve().parents[3] / "config" / "portal.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _hidden_fleets() -> frozenset[str]:
    return hidden_fleet_ids(_portal_config())


def _personal_available_tools() -> frozenset[str]:
    workspaces = _portal_config().get("workspaces")
    if not isinstance(workspaces, dict):
        return frozenset()
    result: set[str] = set()
    for name, variant in (("auto-daily", "fast"), ("auto-coding", None)):
        workspace = workspaces.get(name)
        if not isinstance(workspace, dict):
            continue
        if variant is not None:
            variants = workspace.get("variants")
            workspace = variants.get(variant) if isinstance(variants, dict) else None
        tools = workspace.get("tools") if isinstance(workspace, dict) else None
        if isinstance(tools, list):
            result.update(tool for tool in tools if isinstance(tool, str))
    return frozenset(result)


def _personal_cloud_enabled() -> bool:
    import yaml

    path = Path(__file__).resolve().parents[3] / "config" / "orchestration_arm.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    queue = loaded.get("queue") if isinstance(loaded, dict) else None
    cloud = queue.get("personal_cloud") if isinstance(queue, dict) else None
    return isinstance(cloud, dict) and cloud.get("enabled") is True


def _hop_loop(
    caller: PipelineCaller,
    messages: list[dict[str, Any]],
    root: Path,
    workspace: str,
    tool_names: list[str],
    checkin: _CheckIn,
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
        called.extend(result.tool_names)
        checkin.update(spent, result.tool_names)
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
            checkin.update(1, [name])
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
    extra: dict[str, Any] | None = None,
) -> None:
    receipt = {
        "status": status,
        "workspace": workspace,
        "hops": hops,
        "final_text": content,
        "tool_calls": called,
        "plan": plan,
        "error": error,
    }
    receipt.update(extra or {})
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
        expect=frozenset({"running", "queued", "confirmed", "pending", "cloud_retry"}),
    )
    notice_text = content or (f"{status} {task.id}: {error}" if error else "")
    if notices is not None and notice_text:
        _send_notice(notices, task.id, notice_text)


def _send_notice(notices: Any, task_id: str, message: str) -> None:
    notify = getattr(notices, "notify", None)
    if callable(notify):
        notify(task_id, "personal", message)
        return
    store = getattr(notices, "store", None)
    if store is not None and callable(getattr(store, "notify", None)):
        store.notify(task_id, "personal", message)
