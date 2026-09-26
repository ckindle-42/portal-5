"""One streamed chat turn with an idle timeout — the shared wire client.

Why this exists: a single blocking ``stream=False`` read applies its timeout to
the ENTIRE call. A cold model swap (a resident model being evicted and a
different one loaded for the next request) routinely needs minutes of
load+prefill before the first token, so a total-duration budget discards real
in-flight work as a timeout. httpx's ``read`` timeout, used with a *streamed*
response, is inactivity-based — it applies between successive chunk reads, not
to the whole call — so the transport streams and raises
:class:`StreamTurnStalledError` only when NO bytes arrive for
``idle_timeout_s``, no matter how long the turn legitimately takes. P5-EMERGENT-003
measured the failure live (a 120s budget killing turns that were loading, not
hung); the non-streaming pipeline branch still has a whole-request timeout
(``non_streaming.py``, ``httpx.Timeout(request_timeout, connect=...)``), which
is why long calls — the compliance reading loop's turns run past 300s — must
travel on this client and never on a blocking read.

Two wire protocols, selected by ``is_pipeline_mode``:

* pipeline (OpenAI-shaped SSE): ``data: {...}`` chunks with incremental
  ``delta`` tool_calls, terminated by ``data: [DONE]``;
* native Ollama (``/api/chat``): JSON lines with a FULL ``tool_calls`` array
  per chunk (replace, not accumulate) and a ``done`` terminator.

Attribution: the pipeline sets ``x-portal-route`` —
``{requested_workspace};{backend_id};{target_model}`` — once per HTTP response
(handlers.py). Unlike per-chunk ``model`` fields, which echo the *requested*
value on the pipeline's synthetic preamble chunks and are unreliable on
tool-calling turns that never emit content, this is the router's own decision.
``expected_model_hint`` turns that header into the P5-SILENT-SUBSTITUTION-001
guard: a workspace whose served model differs from its declared model_hint is
an error, never a silent swap.

Callers keep their own post-processing. The security chain-test wraps this with
its tool-call wrapper recovery; the compliance pipeline dialect uses it bare
because the pipeline applies tool-call recovery server-side (C6) and the
reading loop's tools travel as ``portal_client_tools_only`` client schemas.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

__all__ = ["StreamTurnStalledError", "stream_chat_turn"]


class StreamTurnStalledError(RuntimeError):
    """The backend accepted the request but produced no bytes for the idle
    timeout. Attributed to the engine, never used as a control-flow signal for
    "model is still working" — that is precisely what this client exists to not
    do."""


def _accumulate_tool_call_deltas(
    tc_deltas: list[dict[str, Any]], tool_calls_buf: list[dict[str, Any]]
) -> None:
    """Accumulate streamed tool_call deltas by index — mirrors
    portal.platform.inference.router.streaming._accumulate_tool_calls so every
    client of this module parses the OpenAI-style incremental tool_calls shape
    identically to the pipeline's own hop logic."""
    for tc_delta in tc_deltas:
        idx = tc_delta.get("index", 0)
        while len(tool_calls_buf) <= idx:
            tool_calls_buf.append(
                {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
        buf = tool_calls_buf[idx]
        if "id" in tc_delta:
            buf["id"] = tc_delta["id"]
        if "function" in tc_delta:
            fn = tc_delta["function"]
            if "name" in fn:
                buf["function"]["name"] += fn["name"]
            if "arguments" in fn:
                buf["function"]["arguments"] += fn["arguments"]


class _Turn:
    """Mutable accumulator for one streamed turn."""

    def __init__(self) -> None:
        self.content_parts: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.role = "assistant"
        self.usage: dict[str, Any] = {}


def _take_pipeline_line(line: str, turn: _Turn) -> bool:
    """Parse one pipeline SSE line into ``turn``. True when [DONE] ended the turn."""
    if not line.startswith("data: "):
        return False
    data = line[len("data: ") :]
    if data == "[DONE]":
        return True
    chunk = json.loads(data)
    choice = (chunk.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    if delta.get("role"):
        turn.role = delta["role"]
    if delta.get("content"):
        turn.content_parts.append(delta["content"])
    if delta.get("tool_calls"):
        _accumulate_tool_call_deltas(delta["tool_calls"], turn.tool_calls)
    # The pipeline sends a trailing usage chunk after [DONE]-able content;
    # captured so callers get token counts without a second, non-streamed
    # request.
    if chunk.get("usage"):
        turn.usage = chunk["usage"]
    return False


def _take_native_line(line: str, turn: _Turn) -> bool:
    """Parse one Ollama /api/chat JSON line into ``turn``. True when done."""
    chunk = json.loads(line)
    msg = chunk.get("message") or {}
    if msg.get("role"):
        turn.role = msg["role"]
    if msg.get("content"):
        turn.content_parts.append(msg["content"])
    if msg.get("tool_calls"):
        # Ollama sends the full tool_calls array per chunk, not incremental
        # deltas — replace rather than accumulate.
        turn.tool_calls = msg["tool_calls"]
    return bool(chunk.get("done"))


def stream_chat_turn(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    is_pipeline_mode: bool,
    idle_timeout_s: float,
    connect_timeout_s: float = 10.0,
    expected_model_hint: str | set[str] | None = None,
    recover_tool_calls: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One turn, streamed, aggregated to a plain message dict.

    Returns ``{"role", "content", "tool_calls", "served_model", "usage"}``.
    ``served_model`` carries the router's ``x-portal-route`` decision (empty on
    a direct-Ollama call, where the tag on the wire is the literal model).
    ``usage`` carries the pipeline's trailing usage chunk when it sent one.

    ``expected_model_hint``: when set (pipeline mode only), a served model that
    is NEITHER the hint nor one of its alias targets is a RuntimeError naming
    both — silent substitution is the failure mode this guard exists for. The
    alias targets belong in the acceptable set because a priority-10 shadow
    alias legitimately serves the engine-native conversion id, not the GGUF
    tag the workspace names (P5-FANOUT-001 W4).

    ``recover_tool_calls``: optional last-step wrapper for a message that ended
    with no tool_calls (model drift from its own chat template). Receives and
    returns the message dict; never called when tool_calls are present.
    """
    payload = dict(payload, stream=True)
    timeout = httpx.Timeout(idle_timeout_s, connect=connect_timeout_s, write=connect_timeout_s)
    turn = _Turn()
    got_any_chunk = False
    served_model = ""
    take_line = _take_pipeline_line if is_pipeline_mode else _take_native_line

    with (
        httpx.Client(timeout=timeout) as client,
        client.stream("POST", url, headers=headers, json=payload) as resp,
    ):
        if resp.is_error:
            # A streamed response's body is not buffered, and raise_for_status
            # builds its message from response.content — on recent httpx that
            # itself raises ResponseNotRead, masking the real status. Buffer
            # the error body FIRST so the status error carries it (the
            # compliance pipeline dialect's 400 classification reads it).
            resp.read()
            resp.raise_for_status()
        route_header = resp.headers.get("x-portal-route", "")
        if route_header.count(";") == 2:
            served_model = route_header.rsplit(";", 1)[1]
        for line in resp.iter_lines():
            if not line:
                continue
            got_any_chunk = True
            if take_line(line, turn):
                break

    if not got_any_chunk:
        raise StreamTurnStalledError(f"no data received within {idle_timeout_s}s")

    # P5-SILENT-SUBSTITUTION-001: the pipeline treats `model` as a workspace id
    # and silently falls back to the routing group's first model when nothing
    # matches. A declared hint that the served model contradicts is a mapping
    # bug — fix the mapping, never continue.
    if is_pipeline_mode and served_model and expected_model_hint:
        acceptable = (
            {expected_model_hint}
            if isinstance(expected_model_hint, str)
            else set(expected_model_hint)
        )
        if served_model not in acceptable:
            raise RuntimeError(
                f"Silent model substitution: requested workspace {payload.get('model', '')!r} "
                f"(expected model(s) {sorted(acceptable)}) but the pipeline served "
                f"{served_model!r} instead. This means the workspace's model_hint is "
                "missing/wrong in config/portal.yaml, or its workspace_routing group in "
                "config/backends.yaml doesn't actually carry that model — fix the mapping, "
                "don't silently continue."
            )

    message: dict[str, Any] = {
        "role": turn.role,
        "content": "".join(turn.content_parts),
        "tool_calls": turn.tool_calls,
    }
    if recover_tool_calls is not None and not message["tool_calls"]:
        message = recover_tool_calls(message)
    message["served_model"] = served_model
    message["usage"] = turn.usage
    return message
