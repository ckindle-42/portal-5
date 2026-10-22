"""The turn no candidate could serve: who is reading it, what it says, and one count.

A chat UI gets an answer where a program gets a retryable status, and no model is
substituted for the pinned one (it would answer as a model the user did not pick).
``is_chat_ui`` names the evidence it decides on.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from portal.platform.inference.router.metrics import _record_no_answer
from portal.platform.inference.router.non_streaming import _is_capacity_error
from portal.platform.inference.router.workspaces import WORKSPACES

logger = logging.getLogger(__name__)

#: Open WebUI's server posts through a bare ``aiohttp.ClientSession``
#: (``open_webui/utils/session_pool.py``), so its turns carry aiohttp's default UA;
#: forwarded-user mode adds ``X-OpenWebUI-*``. Repo clients speak httpx/curl/fetch.
_UA_MARKER = "aiohttp"
_FORWARDED_HEADERS = ("x-openwebui-user-id", "x-openwebui-user-email", "x-openwebui-user-jwt")
_CLIENT_HEADER = "x-portal-client"
_CHAT_CLIENTS = frozenset({"chat", "ui", "owui"})

#: How the head line names the failure, per reason class.
_FAILURE = {
    "memory_refused": "could not be loaded",
    "timeout": "did not answer in time",
    "engine_error": "could not be served",
    "no_candidate": "could not be served",
}

#: What the user can do about it, per reason class.
_RETRY = {
    "memory_refused": "retry in a minute — a running request may finish and give the memory back",
    "timeout": "retry in a moment — the model may still be finishing the previous turn",
    "engine_error": "retry in a moment",
    "no_candidate": "retry in a moment",
}

_chat_ui: ContextVar[bool] = ContextVar("portal_chat_ui", default=False)


def is_chat_ui(headers: Any) -> bool:
    """Whether the reply is read in a chat UI rather than by a program (see module docstring)."""
    override = str(headers.get(_CLIENT_HEADER) or "").strip().lower()
    if override:
        return override in _CHAT_CLIENTS
    if any(headers.get(name) for name in _FORWARDED_HEADERS):
        return True
    return _UA_MARKER in str(headers.get("user-agent") or "").lower()


def set_chat_ui(headers: Any) -> None:
    """Record the request's audience for the whole turn (set once in the handler)."""
    _chat_ui.set(is_chat_ui(headers))


def chat_ui() -> bool:
    """The current turn's audience, as recorded by :func:`set_chat_ui`."""
    return _chat_ui.get()


def workspace_model(workspace_id: str, body: dict[str, Any] | None = None) -> str:
    """The model the workspace pinned — what the user picked, else what the request named."""
    hint = WORKSPACES.get(workspace_id, {}).get("model_hint") or (body or {}).get("model")
    return str(hint or "")


def reason_class(reasons: Sequence[str]) -> str:
    """The metric's reason label: memory_refused | timeout | engine_error | no_candidate."""
    text = " ".join(reason for reason in reasons if reason).lower()
    if any(_is_capacity_error(reason or "") for reason in reasons):
        return "memory_refused"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    return "engine_error" if text else "no_candidate"


def message(model: str, reasons: Sequence[str], alternative: tuple[str, str] | None) -> str:
    """What a chat UI is told when the turn cannot be served, in plain words."""
    kind = reason_class(reasons)
    head = (
        f"⚠️ **`{model}` {_FAILURE[kind]}, so this turn has no answer.** "
        "No other model was substituted for it."
        if model
        else "⚠️ **This turn could not be answered.**"
    )
    return "\n\n".join([head, _why(reasons), _advice(kind, alternative)])


def _why(reasons: Sequence[str]) -> str:
    refusal = next((r for r in reasons if r and _is_capacity_error(r)), None)
    detail = refusal or next((r for r in reasons if r), "")
    if not detail:
        return "**Why:** no backend could serve it; this turn's trace in the pipeline log names every attempt."
    return f"**Why:** {detail[:300]}"


def _advice(kind: str, alternative: tuple[str, str] | None) -> str:
    retry = _RETRY[kind]
    if alternative is None:
        return f"**What to do:** {retry}."
    workspace, alt_model = alternative
    return (
        f"**What to do:** {retry}, or switch to the **{workspace}** workspace — "
        f"its model `{alt_model}` is loaded and ready now."
    )


async def alternative_workspace(workspace_id: str, model_hint: str) -> tuple[str, str] | None:
    """A workspace whose own model is resident right now, so it needs no cold load."""
    try:
        from portal.platform.inference.router import backend_introspect

        resident = await backend_introspect.loaded_models()
    except Exception as exc:
        logger.debug("could not list resident models: %s", exc)
        return None
    if not resident:
        return None
    for name in sorted(WORKSPACES):
        hint = str(WORKSPACES[name].get("model_hint") or "")
        if name == workspace_id or not hint or hint == model_hint or name.startswith("bench-"):
            continue
        if hint in resident:
            return name, hint
    return None


async def chat_reply(workspace_id: str, model: str, reasons: Sequence[str], *, path: str) -> str:
    """The text a chat UI gets in place of an error status; counts the turn."""
    reason = reason_class(reasons)
    _record_no_answer(workspace_id, reason, "chat", path)
    logger.warning(
        "workspace=%s: no candidate could serve %r (%s) — answering the chat UI "
        "instead of an error status",
        workspace_id,
        model,
        reason,
    )
    return message(model, reasons, await alternative_workspace(workspace_id, model))


def record_api(workspace_id: str, reasons: Sequence[str], *, path: str) -> None:
    """Count a turn that ended for an API client with its real error status."""
    _record_no_answer(workspace_id, reason_class(reasons), "api", path)


def completion(workspace_id: str, text: str) -> dict[str, Any]:
    """An OpenAI completion carrying the notice — what a chat UI stores as the answer."""
    return {
        "id": f"chatcmpl-p5-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": workspace_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
