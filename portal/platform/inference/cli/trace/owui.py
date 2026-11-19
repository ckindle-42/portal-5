"""Section — an Open WebUI turn reaches the Pipeline tool path and renders a closed receipt."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from .context import TraceContext, env_value
from .model import Hop, Status, short
from .workspaces import StreamedTurn, TurnStats

WORKSPACE = "auto-coding"
VALUE = "488895"
MARKER = "<details><summary>Tool results</summary>"
PROMPT = (
    "Use the execute_python tool exactly once with this code:\n"
    "print(sum(len(str(i)) for i in range(1, 100001)))\n"
    "Then reply with only the number it printed. Do not compute the number yourself."
)


def receipt_hop(turn: StreamedTurn) -> Hop:
    """The answer carries the value only the sandbox can produce.

    In Open WebUI's native tool flow OWUI renders the tool call itself, so the Pipeline's text
    receipt is optional here; that the tool ran is proved by the trace hop's tool_calls (live
    2026-11-19: value present, tool_calls=1, no text receipt)."""
    body, _, receipt = turn.stats.text.partition(MARKER)
    named, closed = "execute_python" in receipt, receipt.rstrip().endswith("</details>")
    ok = VALUE in body
    observed = f"{VALUE}={VALUE in body} tool={named} closed={closed}"
    detail = "" if ok else short(turn.error or turn.body or turn.stats.text, 70)
    return Hop("owui tool receipt", Status.PASS if ok else Status.FAIL, observed, VALUE, detail)


def completion_body(
    preset: dict[str, Any], prompt: str, chat_id: str, message_id: str, session_id: str
) -> dict[str, Any]:
    """Build the native Open WebUI request from the selected workspace preset."""
    return {
        "model": preset["id"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "chat_id": chat_id,
        "id": message_id,
        "session_id": session_id,
        "features": {
            "web_search": False,
            "code_interpreter": False,
            "image_generation": False,
            "memory": False,
        },
        "tool_ids": preset["meta"]["toolIds"],
        "params": {"function_calling": preset["params"]["function_calling"]},
    }


def _new_chat(model: str, prompt: str, user_id: str, message_id: str) -> dict[str, Any]:
    """Create the message tree the Open WebUI chat tool loop requires."""
    now = int(time.time())
    return {
        "chat": {
            "title": "Portal trace tool check",
            "models": [model],
            "history": {
                "currentId": message_id,
                "messages": {
                    user_id: {
                        "id": user_id,
                        "role": "user",
                        "content": prompt,
                        "timestamp": now,
                        "models": [model],
                        "childrenIds": [message_id],
                    },
                    message_id: {
                        "id": message_id,
                        "role": "assistant",
                        "content": "",
                        "parentId": user_id,
                        "childrenIds": [],
                        "model": model,
                        "modelName": model,
                        "modelIdx": 0,
                        "done": False,
                        "timestamp": now + 1,
                    },
                },
            },
        }
    }


def _chat_turn(ctx: TraceContext, key: str) -> StreamedTurn:
    """Run one native chat turn and read its completed assistant message."""
    preset = json.loads(
        (ctx.repo_root / "imports/openwebui/workspaces/workspace_auto_coding.json").read_text()
    )
    user_id, message_id = str(uuid.uuid4()), str(uuid.uuid4())
    session_id = f"portal-trace-{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=ctx.timeout_s) as client:
        created = client.post(
            f"{ctx.owui_url}/api/v1/chats/new",
            headers=headers,
            json=_new_chat(WORKSPACE, PROMPT, user_id, message_id),
        )
        created.raise_for_status()
        chat_id = str(created.json()["id"])
        try:
            response = client.post(
                f"{ctx.owui_url}/api/chat/completions",
                headers=headers,
                json=completion_body(preset, PROMPT, chat_id, message_id, session_id),
            )
            response.raise_for_status()
            deadline = time.monotonic() + ctx.timeout_s
            while (
                client.get(f"{ctx.owui_url}/api/tasks/chat/{chat_id}", headers=headers)
                .json()
                .get("task_ids")
            ):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"Open WebUI chat {chat_id} timed out")
                time.sleep(min(1.0, left))
            final = client.get(f"{ctx.owui_url}/api/v1/chats/{chat_id}", headers=headers)
            final.raise_for_status()
            message = final.json()["chat"]["history"]["messages"][message_id]
            return StreamedTurn(200, stats=TurnStats(text=str(message.get("content") or "")))
        finally:
            client.delete(f"{ctx.owui_url}/api/v1/chats/{chat_id}", headers=headers)


def trace_hop(ctx: TraceContext, since: float) -> Hop:
    """The Pipeline's record of that turn: the seat it resolved, its backend and its tool call."""
    headers = {"Authorization": f"Bearer {ctx.api_key}"} if ctx.api_key else {}
    try:
        listing = httpx.get(f"{ctx.pipeline_url}/v1/trace", headers=headers, params={"limit": 10})
        records = listing.json()["data"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return Hop("owui route trace", Status.WARN, "unread", "GET /v1/trace", str(exc)[:70])
    if not records:
        return Hop("owui route trace", Status.WARN, "empty trace store", "a trace record")
    recent = [
        row
        for row in records
        if row.get("workspace") == WORKSPACE and float(row.get("started_at") or 0) >= since - 5
    ]
    row = max(recent, key=lambda item: float(item.get("started_at") or 0)) if recent else {}
    calls = int(row.get("tool_calls") or 0)
    ok = bool(row.get("backend")) and row.get("outcome") == "complete" and calls >= 1
    observed = f"{row.get('backend')}/{row.get('model')} tool_calls={calls}"
    return Hop(
        "owui route trace", Status.PASS if ok else Status.FAIL, observed, f"{WORKSPACE} turn"
    )


def run(ctx: TraceContext, portal: dict[str, object]) -> list[Hop]:
    """One OWUI turn: user ingress must reach the Pipeline's tool loop, not just an engine."""
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("owui turn", Status.WARN, "not run: no OWUI_API_KEY", "an OWUI turn", "set it")]
    started = time.time()
    try:
        turn = _chat_turn(ctx, key)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        turn = StreamedTurn(0, error=f"{type(exc).__name__}: {exc}")
    return [receipt_hop(turn), trace_hop(ctx, started)]
