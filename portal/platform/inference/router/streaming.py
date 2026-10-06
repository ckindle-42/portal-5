"""Streaming transport — pure bytes-in / SSE-bytes-out, no routing policy.

This module owns the streaming machinery extracted from ``router_pipe.py``:

* :func:`_json_completion_to_sse` — convert a non-streaming completion JSON to
  SSE frames for the fallback path.
* :func:`_stream_with_tool_loop` — semaphore-owning wrapper for multi-hop
  tool dispatch; delegates to :func:`_stream_with_tool_loop_impl`.
* :func:`_stream_with_tool_loop_impl` — the ~300-line tool-loop core (no
  semaphore ownership, no policy).
* :func:`_stream_with_preamble` — semaphore-owning wrapper for the no-tools
  path; emits the role preamble before opening the backend connection.
* :func:`_stream_from_backend_guarded` — lowest-level: HTTP stream → SSE
  bytes, with channel separation and error envelope.

**Transport-only contract**: a prepared request goes in; OWUI-shaped SSE
bytes come out. No routing decisions, no persona resolution, no tool policy.
Imports from ``router.workspaces``, ``router.tools``, ``router.metrics``,
``router.state``, ``router.power``, and ``router.concurrency`` (for
:class:`~portal.platform.inference.router.concurrency.RequestSlot` type). None of
those modules import ``streaming`` — the dependency graph is acyclic.

The shared ``httpx.AsyncClient`` is injected by ``lifespan`` as
``_http_client``; ``_SHOW_ROUTING_STATUS`` is parsed from env at import time.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException

from portal.platform.inference.config import PersonaSpec
from portal.platform.inference.router.backend_introspect import (
    free_ollama_for_omlx,
    make_room_for_omlx,
)
from portal.platform.inference.router.correlation import (
    get_correlation_id as _corr_id,
)
from portal.platform.inference.router.metrics import (
    _hint_fallback_total,
    _record_response_time,
    _tool_calls_recovered,
    _tool_loop_hops,
)
from portal.platform.inference.router.non_streaming import (
    _REQUEST_ERROR_STATUSES,
    BackendRequestError,
    _is_capacity_error,
    _try_non_streaming,
    backend_error_detail,
    resolve_hop_target,
)
from portal.platform.inference.router.state import _record_error
from portal.platform.inference.router.text_tool_calls import (
    TextToolCallHoldback,
    salvage_text_tool_calls,
)
from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE, ThinkTagFilter
from portal.platform.inference.router.tools import (
    _dispatch_tool_call,
    _select_explicit_required_tool,
)
from portal.platform.inference.router.trace import (
    capture as trace_capture,
)
from portal.platform.inference.router.trace import (
    finalize_trace,
)
from portal.platform.inference.router.trace import (
    note as trace_note,
)
from portal.platform.inference.router.trace import (
    span as trace_span,
)
from portal.platform.inference.router.validation import (
    _inject_ollama_options,
    _inject_omlx_options,
    _model_supports_tools,
)
from portal.platform.inference.router.workspaces import (
    _PERSONA_MAP,
    MAX_TOOL_HOPS,
    WORKSPACES,
    _resolve_persona_tool_choice,
    _resolve_persona_tools,
)

if TYPE_CHECKING:
    from portal.platform.inference.router.concurrency import RequestSlot

logger = logging.getLogger(__name__)

# ── Module-level singletons (injected by lifespan) ───────────────────────────

_http_client: httpx.AsyncClient | None = None

# ── Routing visibility ────────────────────────────────────────────────────────
# When true, the first line of every streaming response shows which workspace
# and model was selected. Set SHOW_ROUTING_STATUS=true in .env to enable.
_SHOW_ROUTING_STATUS: bool = os.environ.get("SHOW_ROUTING_STATUS", "false").lower() in (
    "1",
    "true",
    "yes",
)


# ── SSE helpers ───────────────────────────────────────────────────────────────


def _as_bytes(body: bytes | memoryview[int]) -> bytes:
    """Normalise a response body that may be bytes or memoryview for json.loads."""
    return body.tobytes() if isinstance(body, memoryview) else body


def _content_chunk(request_id: str, workspace_id: str, text: str) -> bytes:
    """One OpenAI chunk carrying ``text`` as assistant content."""
    payload = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": workspace_id,
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _backend_error_chunk(status: int, raw: bytes) -> bytes:
    """Error envelope for a non-200 backend reply: the engine's own message plus
    the status, so the fallback wrapper can tell a malformed request (surface it)
    from an unavailable backend (fall back)."""
    msg = f"Backend returned HTTP {status}: {backend_error_detail(raw)}"
    return f"data: {json.dumps({'error': msg, 'status': status})}\n\n".encode()


def _stream_error(chunk: bytes) -> int | None:
    """``None`` unless ``chunk`` is an error envelope; else its HTTP status (0 if
    unknown). Parsed, not substring-matched: a delta whose text contained the
    JSON key ``"error"`` used to be taken for a failure."""
    if b'"error"' not in chunk or not chunk.startswith(b"data:"):
        return None
    try:
        obj = json.loads(chunk[5:].strip())
    except Exception:
        return None
    if not isinstance(obj, dict) or "error" not in obj or obj.get("choices"):
        return None
    status = obj.get("status")
    return status if isinstance(status, int) else 0


def _stream_error_detail(chunk: bytes) -> str:
    """The message text from a ``_backend_error_chunk`` envelope, else ''."""
    if not chunk.startswith(b"data:"):
        return ""
    try:
        obj = json.loads(chunk[5:].strip())
    except Exception:
        return ""
    return str(obj.get("error", "")) if isinstance(obj, dict) else ""


def _is_noncascadable_stream_error(status: int | None, buffer: bytes | None) -> bool:
    """Whether a streamed backend error should surface to the client instead of
    falling back to the next candidate — mirrors non_streaming.py's
    ``_raise_for_backend_status`` rule (see there for why a 400 needs a
    capacity exception: oMLX's prefill_memory_guard also returns 400, and that
    one should cascade to Ollama, not surface)."""
    if status not in _REQUEST_ERROR_STATUSES:
        return False
    return not (status == 400 and buffer and _is_capacity_error(_stream_error_detail(buffer)))


def _chunk_has_output(chunk: bytes) -> bool:
    """Whether an SSE chunk puts model output in front of the client (content,
    reasoning or a tool call — not the role preamble or routing status line)."""
    if not chunk.startswith(b"data:"):
        return False
    try:
        obj = json.loads(chunk[5:].strip())
    except Exception:
        return False
    for choice in (obj.get("choices") or []) if isinstance(obj, dict) else []:
        d = choice.get("delta") or {}
        content = d.get("content")
        if content and not (isinstance(content, str) and content.startswith("`⚡ ")):
            return True
        if d.get("reasoning") or d.get("reasoning_content") or d.get("thinking"):
            return True
        if d.get("tool_calls"):
            return True
    return False


def _thinking_enabled(body: dict[str, Any]) -> bool:
    """Read the effective thinking policy across Ollama and oMLX request shapes."""
    direct = body.get("enable_thinking")
    if isinstance(direct, bool):
        return direct
    ctk = body.get("chat_template_kwargs")
    if isinstance(ctk, dict) and isinstance(ctk.get("enable_thinking"), bool):
        return ctk["enable_thinking"]
    if body.get("reasoning_effort") == "none":
        return False
    if body.get("think") is False:
        return False
    options = body.get("options")
    return not (isinstance(options, dict) and options.get("think") is False)


def _indexed_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Streamed tool_call deltas must carry ``index``: an OpenAI-style client
    defaults a missing one to 0 and merges every call in the turn into one."""
    return [{**tc, "index": tc.get("index", i)} for i, tc in enumerate(tool_calls)]


def _completion_finish_chunk(reason: str) -> bytes:
    return f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': reason}]})}\n\n".encode()


def _json_completion_to_sse(
    data: dict[str, Any], workspace_id: str, *, thinking_enabled: bool = True
) -> Iterator[bytes]:
    """Convert a completion to SSE without treating reasoning as answer text."""
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    role = message.get("role", "assistant")
    if role:
        yield f"data: {json.dumps({'choices': [{'delta': {'role': role}}]})}\n\n".encode()
    content = message.get("content") or ""
    content_filter = ThinkTagFilter()
    visible = content_filter.feed(content, final=True) if isinstance(content, str) else ""
    delta: dict[str, Any] = {}
    if visible:
        delta["content"] = visible
    if thinking_enabled:
        for name in ("reasoning", "reasoning_content", "thinking"):
            if message.get(name):
                delta[name] = message[name]
    if delta:
        yield f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\n".encode()
    tool_calls = message.get("tool_calls")
    if tool_calls:
        yield f"data: {json.dumps({'choices': [{'delta': {'tool_calls': _indexed_tool_calls(tool_calls)}}]})}\n\n".encode()
    finish_reason = choice.get("finish_reason", "stop")
    if not visible.strip() and not tool_calls:
        yield _content_chunk(str(data.get("id", "chatcmpl")), workspace_id, NO_ANSWER_MESSAGE)
        finish_reason = (
            "length"
            if content_filter.removed
            or any(message.get(name) for name in ("reasoning", "reasoning_content", "thinking"))
            or finish_reason == "length"
            else "stop"
        )
    yield _completion_finish_chunk(str(finish_reason or "stop"))
    yield b"data: [DONE]\n\n"


# ── Streaming wrappers (own the RequestSlot lifecycle) ────────────────────────


async def _stream_with_tool_loop(
    backend_url: str,
    body: dict[str, Any],
    slot: RequestSlot,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Streaming wrapper with the multi-hop tool loop; owns the RequestSlot lifecycle.

    The **semaphore-ownership boundary** for the tool-loop path.
    Delegates the actual streaming work (and the loop) to
    ``_stream_with_tool_loop_impl``, which doesn't know about
    semaphores. This wrapper's only responsibility is the
    ``try/finally`` that calls ``slot.release()`` once the entire
    stream — across all tool hops — is done.

    The release happens **after** the inner generator is exhausted,
    not after the first hop. A multi-hop request holds all three
    semaphores for the entire conversation, not just the first
    backend POST. This is deliberate: the rate-limiting intent is
    "one in-flight conversation per slot," not "one HTTP request
    per slot."

    Args mirror ``_stream_with_tool_loop_impl`` plus:
        slot: :class:`~portal.platform.inference.router.concurrency.RequestSlot`
            (detached from the handler). ``slot.release()`` is called
            in ``finally:`` after the stream completes.

    Yields:
        SSE bytes for OWUI consumption.
    """
    outcome = "interrupted"
    try:
        async for chunk in _stream_with_tool_loop_impl(
            backend_url, body, workspace_id, model, persona, effective_tools, start_time
        ):
            yield chunk
        outcome = "complete"
    except Exception:
        outcome = "error"
        raise
    finally:
        trace_note(outcome=outcome)
        trace_span("stream.finished", outcome=outcome)
        slot.release()
        finalize_trace()


def _accumulate_tool_calls(
    tc_deltas: list[dict[str, Any]], tool_calls_buf: list[dict[str, Any]]
) -> None:
    """Accumulate streamed tool_call deltas into tool_calls_buf in place."""
    for tc_delta in tc_deltas:
        idx = tc_delta.get("index", 0)
        while len(tool_calls_buf) <= idx:
            tool_calls_buf.append(
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }
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


def _apply_reasoning_rewrite(
    line: str,
    delta: dict[str, Any],
    choice: dict[str, Any],
    obj: dict[str, Any],
    thinking_enabled: bool,
    think_filter: ThinkTagFilter,
) -> tuple[bytes | None, bool, bool]:
    """Separate reasoning channels and incrementally filter inline wrappers.

    Returns:
        (rewritten_chunk_or_None, content_emitted, skip_default_yield)

        - rewritten_chunk_or_None: SSE bytes to yield instead of the original line,
          or None if no rewrite is needed.
        - content_emitted: True if content should count as emitted to the client.
        - skip_default_yield: True if the caller should ``continue`` instead of yielding
          the original line.
    """
    new_delta = dict(delta)
    changed = False
    if not thinking_enabled:
        for name in ("reasoning", "reasoning_content", "thinking"):
            if name in new_delta:
                new_delta.pop(name)
                changed = True

    content = delta.get("content")
    visible = think_filter.feed(content) if isinstance(content, str) else content
    if isinstance(content, str) and visible != content:
        changed = True
        if visible:
            new_delta["content"] = visible
        else:
            new_delta.pop("content", None)

    emitted = bool(visible.strip()) if isinstance(visible, str) else False
    if not changed:
        return None, emitted, False
    new_obj = dict(obj)
    new_obj["choices"] = [dict(choice, delta=new_delta)]
    return f"data: {json.dumps(new_obj)}\n\n".encode(), emitted, True


async def _dispatch_hop_tool_calls(
    all_tool_calls: list[dict[str, Any]],
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
    hop: int,
    max_hops: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Dispatch all tool calls for one hop in parallel.

    Returns (assistant_msg, dispatch_results) where assistant_msg is ready to
    append to the message list and dispatch_results is the list of tool result
    messages (one per tool call).
    """
    dispatch_results: list[dict[str, Any]] = list(
        await asyncio.gather(
            *[
                _dispatch_tool_call(tc, effective_tools, workspace_id, persona, request_id)
                for tc in all_tool_calls
            ],
        )
    )
    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": all_tool_calls,
    }
    logger.info(
        "Tool loop hop=%d/%d workspace=%s tools_called=%s",
        hop,
        max_hops,
        workspace_id,
        [tc["function"]["name"] for tc in all_tool_calls],
    )
    # A tool result carrying "error" used to leave only a bare error COUNT in
    # portal5_tool_call_errors_total — the message itself (§P4.2: e.g. the
    # router-narrowing residue from an already-dispatched call) was never
    # logged, so a turn that died at hop 1 was knowable only by re-running it
    # and guessing. Log the body so the first run is enough.
    for result in dispatch_results:
        try:
            content = json.loads(result.get("content") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(content, dict) and content.get("error"):
            logger.warning(
                "Tool loop hop=%d workspace=%s tool=%s error=%s",
                hop,
                workspace_id,
                result.get("name"),
                content["error"],
            )
    return assistant_msg, dispatch_results


_DONE = b"data: [DONE]\n\n"


async def _stream_with_tool_loop_impl(
    backend_url: str,
    body: dict[str, Any],
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """The tool loop's frames, terminated by exactly one ``[DONE]``.

    The loop body forwards the backend's ``[DONE]`` and then, on several paths,
    appends frames after it (the reasoning fallback, the empty-response notice).
    OpenAI-SDK clients stop reading at the first ``[DONE]``, so those frames
    never reached them. Every ``[DONE]`` inside is dropped and one is emitted
    at the true end — error paths included.
    """
    # aclosing: a client disconnect closes the backend stream now, not at GC.
    async with contextlib.aclosing(
        _tool_loop_frames(
            backend_url, body, workspace_id, model, persona, effective_tools, start_time
        )
    ) as frames:
        async for chunk in frames:
            if chunk != _DONE:
                yield chunk
    yield _DONE


async def _tool_loop_frames(
    backend_url: str,
    body: dict[str, Any],
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream-and-tool-loop implementation (no semaphore ownership).

    The most complex function in the file. Wrapped by
    ``_stream_with_tool_loop`` which adds semaphore lifecycle.
    Spans ~300 lines covering multi-hop tool dispatch, OpenAI SSE,
    several backend quirks, and a per-chunk reasoning-content rewriter.

    Per-hop algorithm:

    1. **Emit preamble** on hop 1: OpenAI role chunk plus an
       optional ``⚡ workspace → model`` status when
       ``_SHOW_ROUTING_STATUS=true``.
    2. **POST + stream** from ``backend_url`` with ``current_body``.
    3. **Per-chunk processing** of OpenAI SSE — see "One protocol"
       below.
    4. **After stream completes**, if ``finish_reason ==
       "tool_calls"``:
       - Collect tool_calls from the OpenAI-format buffer.
       - Bail with "Tool-use limit reached" content if
         ``hop >= MAX_TOOL_HOPS``.
       - Dispatch all tool calls in parallel via
         ``asyncio.gather(_dispatch_tool_call, ...)``.
       - Append assistant turn + tool results to
         ``current_body.messages`` and loop.
    5. **Otherwise** (``"stop"`` or similar): record response time
       and return.

    **One protocol (OpenAI SSE):**

    All backends (Ollama ``/v1/``, vLLM, etc.) speak OpenAI-compatible
    SSE. ``data: {...}`` lines, OpenAI-spec shape.

    **Pipeline-owned tool dispatch — OWUI never sees ``tool_calls``
    deltas.** Every ``delta.get("tool_calls")`` chunk from the
    backend is *suppressed from the OWUI SSE stream*. If OWUI saw
    a ``tool_calls`` event it would trigger its own dispatch loop,
    creating duplicate turns with empty tool results that
    overwrite the pipeline's real answer. The pipeline collects
    ``tool_calls`` into ``tool_calls_buf``, then dispatches them
    itself after the stream completes.

    Reasoning fields stay separate from answer content on every hop. If the
    effective request disables thinking, unexpected reasoning fields are
    suppressed. Inline protocol think blocks are filtered incrementally.

    Args:
        backend_url: Full URL to POST to (chat_url on the
            chosen backend).
        body: Initial request body; copied via ``dict(body)``
            and mutated in place across hops (this is OK
            because the caller already gave us a copy).
        workspace_id, model, persona: For logging, metrics,
            and tool dispatch.
        effective_tools: Tool whitelist from
            ``_resolve_persona_tools``; passed to
            ``_dispatch_tool_call`` for per-call authorization.
        start_time: For elapsed-time metrics; ``None`` skips
            response-time recording.

    Yields:
        SSE bytes for OWUI. Tool-call deltas are suppressed;
        every other delta type is forwarded after applicable
        rewriting.
    """
    request_id = _corr_id() or f"chatcmpl-p5-{int(time.time())}"
    hop = 0
    current_body = dict(body)
    _exec_audit: bool = bool(body.get("exec_audit"))
    _exec_audit_calls: list[
        dict[str, Any]
    ] = []  # accumulates tool calls across all hops when exec_audit=true

    while hop < MAX_TOOL_HOPS:
        hop += 1

        # Accumulators for this iteration
        tool_calls_buf: list[dict[str, Any]] = []
        finish_reason: str | None = None
        _content_emitted: bool = False  # substantive answer bytes reached client
        _reasoning_seen = False
        _think_filter = ThinkTagFilter()
        _thinking_allowed = _thinking_enabled(current_body)
        # Text-written tool calls (P5-OMLX-QWEN3CODER-TOOLTEXT-001): with tools
        # offered, content from a call marker on is withheld until the stream
        # ends, then dispatched if it parses or released as text if it doesn't.
        _holdback = TextToolCallHoldback() if current_body.get("tools") else None

        # Emit preamble (role chunk) on first hop
        if hop == 1:
            ts = int(time.time())
            role_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": ts,
                "model": workspace_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(role_chunk)}\n\n".encode()
            if _SHOW_ROUTING_STATUS:
                ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
                status_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": workspace_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": f"`⚡ {ws_name} → {model}`\n\n"},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(status_chunk)}\n\n".encode()

        # Stream from backend
        try:
            trace_capture(backend_request=current_body)
            async with _http_client.stream("POST", backend_url, json=current_body) as resp:  # type: ignore[union-attr]
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(
                        "Tool-loop backend returned HTTP %d: %s", resp.status_code, err[:200]
                    )
                    _record_error(workspace_id, f"backend_http_{resp.status_code}")
                    yield _backend_error_chunk(resp.status_code, err)
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        yield (line + "\n\n").encode()
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        # The router decides whether this was a tool hop or a
                        # terminal answer before writing the finish/DONE pair.
                        continue
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        yield (line + "\n\n").encode()
                        continue
                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta", {})
                    _reasoning_seen = _reasoning_seen or any(
                        delta.get(name) for name in ("reasoning", "reasoning_content", "thinking")
                    )

                    if delta.get("tool_calls"):
                        _accumulate_tool_calls(delta["tool_calls"], tool_calls_buf)
                        # Some backends send tool_calls + finish_reason in
                        # the same final chunk — capture finish_reason here
                        # so the dispatch gate fires after the stream ends.
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        # Suppress tool_call delta — pipeline owns dispatch
                        continue

                    _frame_finish = choice.get("finish_reason")
                    if _frame_finish:
                        finish_reason = _frame_finish
                        if finish_reason == "tool_calls":
                            # Suppress finish_reason=tool_calls chunk too
                            continue
                        # Emit terminal finish only after final content/error.
                        choice = dict(choice, finish_reason=None)
                        obj = dict(obj, choices=[choice])
                        line = f"data: {json.dumps(obj)}"

                    _ct = delta.get("content")
                    if _holdback is not None and _ct and isinstance(_ct, str):
                        _ct = _ct if isinstance(_ct, str) else ""
                        _shown = _holdback.feed(_ct)
                        if _shown != _ct:
                            if not _shown:
                                continue
                            delta = dict(delta, content=_shown)
                            choice = dict(choice, delta=delta)
                            obj = dict(obj, choices=[choice])
                            line = f"data: {json.dumps(obj)}"

                    _rewrite_chunk, _emitted, _skip = _apply_reasoning_rewrite(
                        line,
                        delta,
                        choice,
                        obj,
                        _thinking_allowed,
                        _think_filter,
                    )
                    if _rewrite_chunk is not None:
                        yield _rewrite_chunk
                        _content_emitted = _content_emitted or _emitted
                    if _skip:
                        continue
                    if _emitted:
                        _content_emitted = True
                    if delta or not _frame_finish:
                        yield (line + "\n\n").encode()
        except httpx.TimeoutException:
            logger.warning(
                "Tool-loop backend %s timed out (workspace=%s, hop=%d) — probing engine state",
                backend_url,
                workspace_id,
                hop,
            )
            from portal.platform.inference.router.backend_introspect import (
                model_still_running as _msr,
            )

            _still_running = await _msr(backend_url, timeout_s=5.0)
            if _still_running:
                logger.warning(
                    "Backend %s: model still in /api/ps after stream timeout — "
                    "reasoning model mid-generation? (workspace=%s)",
                    backend_url,
                    workspace_id,
                )
                yield (
                    f"data: {json.dumps({'error': 'Response timed out — model may still be generating. Please retry.'})}\n\n"
                ).encode()
            else:
                logger.warning(
                    "Backend %s: no model in /api/ps after timeout — backend may be down (workspace=%s)",
                    backend_url,
                    workspace_id,
                )
                _record_error(workspace_id, "stream_timeout")
                yield (
                    f"data: {json.dumps({'error': 'Backend timed out and no model is loaded. Please retry.'})}\n\n"
                ).encode()
            return
        except Exception as e:
            logger.error("Tool-loop stream error from %s: %s", backend_url, e)
            _record_error(workspace_id, "stream_error")
            yield (f"data: {json.dumps({'error': 'Backend connection error'})}\n\n").encode()
            return

        if _holdback is not None and _holdback.holding:
            _held = _holdback.take()
            _, _salvaged = salvage_text_tool_calls(_held, current_body.get("tools"))
            if _salvaged:
                logger.info(
                    "Tool loop hop %d: recovered %d tool call(s) written as text "
                    "(workspace=%s model=%s)",
                    hop,
                    len(_salvaged),
                    workspace_id,
                    current_body.get("model", ""),
                )
                _tool_calls_recovered.labels(workspace=workspace_id).inc(len(_salvaged))
                tool_calls_buf.extend(_salvaged)
                finish_reason = "tool_calls"
            else:
                _visible_held = _think_filter.feed(_held)
                if _visible_held:
                    _held_chunk = {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": workspace_id,
                        "choices": [
                            {"index": 0, "delta": {"content": _visible_held}, "finish_reason": None}
                        ],
                    }
                    yield f"data: {json.dumps(_held_chunk)}\n\n".encode()
                    _content_emitted = _content_emitted or bool(_visible_held.strip())

        _tail = _think_filter.feed("", final=True)
        if _tail:
            _tail_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": workspace_id,
                "choices": [{"index": 0, "delta": {"content": _tail}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(_tail_chunk)}\n\n".encode()
            _content_emitted = _content_emitted or bool(_tail.strip())

        # Empty and reasoning-only terminals are explicit no-answer outcomes.
        # Diagnostics contain only the outcome class and route identity; raw
        # reasoning text is not copied into ordinary logs.
        if not _content_emitted and finish_reason != "tool_calls":
            _reasoning_only = _reasoning_seen or _think_filter.removed
            logger.warning(
                "Streaming hop %d/%d completed without answer content "
                "(workspace=%s, finish_reason=%s, backend=%s, model=%s, "
                "reasoning_only=%s).",
                hop,
                MAX_TOOL_HOPS,
                workspace_id,
                finish_reason,
                backend_url,
                current_body.get("model", ""),
                _reasoning_only,
            )
            _record_error(workspace_id, "reasoning_only" if _reasoning_only else "empty_completion")
            _empty_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": workspace_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": NO_ANSWER_MESSAGE},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(_empty_chunk)}\n\n".encode()
            finish_reason = "length" if _reasoning_only or finish_reason == "length" else "stop"

        # After stream completes, check if tool calls were emitted
        if finish_reason == "tool_calls":
            all_tool_calls = tool_calls_buf

            if not all_tool_calls:
                logger.warning(
                    "Tool loop hop %d: finish_reason=tool_calls but no tool_calls "
                    "extracted (backend=%s workspace=%s). "
                    "Check backend tool parser compatibility.",
                    hop,
                    backend_url,
                    workspace_id,
                )
                _record_error(workspace_id, "tool_parse_failure")
                yield (
                    f"data: {json.dumps({'error': 'Tool call could not be parsed from the model response — please retry.'})}\n\n"
                ).encode()
                yield _completion_finish_chunk("stop")
                yield b"data: [DONE]\n\n"
                return

            _tool_loop_hops.labels(workspace=workspace_id).observe(hop)

            # Hop limit guard
            if hop >= MAX_TOOL_HOPS:
                limit_msg = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": f"\n\n[Tool-use limit ({MAX_TOOL_HOPS} hops) reached. Returning partial result.]"
                            },
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(limit_msg)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return

            # Only auto-dispatch when every requested call belongs to the
            # workspace's own whitelist. A client-injected tool (not in
            # effective_tools) has no real MCP registry entry —
            # _dispatch_tool_call would reject it and the loop would burn
            # through hops on rejection errors instead of letting the caller
            # handle it. Mirrors the non_streaming.py fix (2026-07-05): if
            # any call isn't ours to dispatch, surface the tool_calls we'd
            # been suppressing (pipeline "owns dispatch" only for its own
            # tools) as the final response instead of auto-resolving them.
            if not all(
                (tc.get("function") or {}).get("name", "").strip() in effective_tools
                for tc in all_tool_calls
            ):
                passthrough_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"tool_calls": _indexed_tool_calls(all_tool_calls)},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(passthrough_chunk)}\n\n".encode()
                finish_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }
                yield f"data: {json.dumps(finish_chunk)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return

            # Dispatch all tool calls in parallel
            assistant_msg, dispatch_results = await _dispatch_hop_tool_calls(
                all_tool_calls,
                effective_tools,
                workspace_id,
                persona,
                request_id,
                hop,
                MAX_TOOL_HOPS,
            )
            current_body["messages"] = (
                current_body.get("messages", []) + [assistant_msg] + dispatch_results
            )
            if _exec_audit:
                _exec_audit_calls.extend(
                    [
                        {**tc, "_output": dr.get("content", "")}
                        for tc, dr in zip(all_tool_calls, dispatch_results)
                    ]
                )
            # Continue loop for next iteration
        else:
            # Model finished without tool calls — done
            if _exec_audit and _exec_audit_calls:
                audit_event = {
                    "type": "exec_audit",
                    "tool_calls": [
                        {
                            "tool": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", ""),
                            "output": tc.get("_output", ""),
                        }
                        for tc in _exec_audit_calls
                    ],
                }
                yield f"data: {json.dumps(audit_event)}\n\n".encode()
            yield _completion_finish_chunk(finish_reason or "stop")
            yield b"data: [DONE]\n\n"
            if start_time is not None:
                _record_response_time(model, workspace_id, time.monotonic() - start_time)
            return


async def _stream_with_preamble(
    url: str,
    body: dict[str, Any],
    slot: RequestSlot,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Streaming path without tools; emits preamble + owns the RequestSlot lifecycle.

    **The preamble is a UX fix.** Without it, OWUI shows a frozen
    input box for 10–30s while a cold model loads — entirely silent
    from the user's perspective. The preamble is a zero-content
    OpenAI role chunk that FastAPI flushes to the client before the
    backend connection is even opened. OWUI sees "stream started,
    role=assistant", shows the typing indicator, and the user knows
    something is happening. Actual content streams in normally once
    the model produces tokens.

    If ``_SHOW_ROUTING_STATUS=true`` (operator debug toggle), a
    second chunk shows ``⚡ workspace → model`` at the top of the
    response.

    **Slot ownership boundary.** ``slot.release()`` is called in
    ``finally:``, which catches client disconnects after the preamble
    yield but before the backend connection starts.

    Args:
        url: Backend chat URL.
        body: Already-injected request body (Ollama options
            applied at the call site).
        slot: :class:`~portal.platform.inference.router.concurrency.RequestSlot`
            (detached from the handler). ``slot.release()`` called here.
        workspace_id, model: For logging and the
            ``x-portal-route`` header set by the caller.
        start_time: For elapsed-time metrics.

    Yields:
        SSE bytes — preamble role chunk, optional status chunk,
        then whatever ``_stream_from_backend_guarded`` produces.
    """
    ts = int(time.time())
    request_id = f"chatcmpl-p5-{ts}"

    def _make_chunk(delta: dict[str, Any]) -> bytes:
        """Serialise a single OpenAI-compatible SSE chunk."""
        payload = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": workspace_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode()

    # Empty role chunk — starts Open WebUI typing indicator with zero latency.
    yield _make_chunk({"role": "assistant", "content": ""})

    # Optional routing annotation — shows workspace + model at top of response.
    if _SHOW_ROUTING_STATUS:
        ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
        yield _make_chunk({"content": f"`⚡ {ws_name} → {model}`\n\n"})

    # Stream from backend.
    outcome = "interrupted"
    try:
        async for chunk in _stream_from_backend_guarded(
            url, body, workspace_id=workspace_id, model=model, start_time=start_time
        ):
            yield chunk
        outcome = "complete"
    except Exception:
        outcome = "error"
        raise
    finally:
        trace_note(outcome=outcome)
        trace_span("stream.finished", outcome=outcome)
        slot.release()
        finalize_trace()


async def _stream_from_backend_guarded(
    url: str,
    body: dict[str, Any],
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Stream from backend; pass-through OpenAI SSE; record metrics.

    The lowest-level streaming function. Connects to ``url``,
    streams the response, yields bytes for OWUI. Handles two
    cases:

    * **OpenAI SSE** (Ollama ``/v1/``, vLLM, etc.):
      ``data: {...}`` lines, mostly pass-through.
    * **Failure** (connect error, HTTP non-200): emit explicit
      ``data: {"error": "..."}\\n\\n`` envelope and return. This
      is what ``_stream_or_fallback`` matches on with its
      ``b'"error"' in chunk`` check.

    **Line-based fast-path checks** replace the old byte-chunk
    scanning. Each line from ``aiter_lines()`` (which yields ``str``
    per the httpx contract) is checked with fast substring ops
    (``'"done"'``, ``'"reasoning"'``). Only successful matches pay
    the decode-parse cost. Steady-state cost per line is a couple
    of substring checks.

    Args:
        url: Backend chat URL.
        body: Request body; pass-through to the backend.
        workspace_id, model: For logging and metrics.
        start_time: For elapsed-time metrics; ``None`` skips
            response-time recording.

    Yields:
        SSE bytes for OWUI consumption.
    """
    from portal.platform.inference.router.power import _record_usage

    if _http_client is None:
        logger.error("HTTP client not initialised — yielding error chunk")
        yield ("data: " + json.dumps({"error": "Pipeline not ready"}) + "\n\n").encode()
        return
    _answer_emitted = False
    _tool_calls_emitted = False
    _reasoning_seen = False
    _completion_tokens_seen = 0
    _finish_reason: str | None = None
    _think_filter = ThinkTagFilter()
    _thinking_allowed = _thinking_enabled(body)
    try:
        _usage_recorded = False  # guard: only record TPS once per request
        trace_capture(backend_request=body)
        async with _http_client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                err = await resp.aread()
                logger.error(
                    "Backend %s returned HTTP %d: %s",
                    url,
                    resp.status_code,
                    err[:200].decode(errors="replace"),
                )
                _record_error(
                    workspace_id,
                    f"backend_http_{resp.status_code}",
                )
                yield _backend_error_chunk(resp.status_code, err)
                return
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:") and line[5:].strip() == "[DONE]":
                    # The router owns the terminal sequence so it can classify
                    # an empty/reasoning-only turn before finish and [DONE].
                    break
                # Fast-path: detect Ollama native "done" chunk (has eval_count/eval_duration)
                if '"done"' in line and line.startswith("data:") and line != "data: [DONE]":
                    payload = line[5:].strip()
                    if payload and not _usage_recorded:
                        try:
                            usage_data = json.loads(payload)
                            elapsed = (
                                (time.monotonic() - start_time) if start_time is not None else None
                            )
                            _record_usage(
                                model=usage_data.get("model", model),
                                workspace=workspace_id,
                                data=usage_data,
                                elapsed_seconds=elapsed,
                            )
                            _usage_recorded = True
                        except Exception:
                            logger.debug("Could not parse usage payload from stream")
                # OpenAI usage chunk from Ollama stream_options.include_usage=true:
                # Ollama sends a final data:{...,"usage":{"prompt_tokens":X,"completion_tokens":Y}}
                # chunk before [DONE]. Detect by "completion_tokens" in the line so we parse
                # it once and record TPS for every streaming request (not just the 13% that
                # happen to return Ollama native format with eval_count/eval_duration).
                elif (
                    '"completion_tokens"' in line
                    and line.startswith("data:")
                    and not _usage_recorded
                ):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            usage_data = json.loads(payload)
                            elapsed = (
                                (time.monotonic() - start_time) if start_time is not None else None
                            )
                            _record_usage(
                                model=model,
                                workspace=workspace_id,
                                data=usage_data,
                                elapsed_seconds=elapsed,
                            )
                            _usage_recorded = True
                            _completion_tokens_seen = usage_data.get("completion_tokens", 0) or 0
                        except Exception:
                            logger.debug("Could not parse OpenAI usage chunk from stream")
                if line.startswith("data:"):
                    try:
                        frame = json.loads(line[5:].strip())
                    except (json.JSONDecodeError, TypeError):
                        yield (line + "\n\n").encode()
                        continue
                    choices = frame.get("choices") or []
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta") or {}
                        _reasoning_seen = _reasoning_seen or any(
                            delta.get(name)
                            for name in ("reasoning", "reasoning_content", "thinking")
                        )
                        _tool_calls_emitted = _tool_calls_emitted or bool(delta.get("tool_calls"))
                        finish = choice.get("finish_reason")
                        if finish:
                            _finish_reason = str(finish)
                        clean_choice = dict(choice)
                        clean_choice["finish_reason"] = None
                        clean_frame = dict(frame, choices=[clean_choice])
                        rewritten, emitted, _skip = _apply_reasoning_rewrite(
                            line,
                            delta,
                            clean_choice,
                            clean_frame,
                            _thinking_allowed,
                            _think_filter,
                        )
                        _answer_emitted = _answer_emitted or emitted
                        if rewritten is not None:
                            yield rewritten
                        elif finish:
                            # Finish is emitted once after terminal answer
                            # classification, never before a recovered error.
                            if delta:
                                yield f"data: {json.dumps(clean_frame)}\n\n".encode()
                        else:
                            yield (line + "\n\n").encode()
                        continue
                    yield (line + "\n\n").encode()
                    continue
                yield (line + "\n\n").encode()

            tail = _think_filter.feed("", final=True)
            if tail:
                yield _content_chunk(f"chatcmpl-{workspace_id}", workspace_id, tail)
                _answer_emitted = _answer_emitted or bool(tail.strip())
            if not _answer_emitted and not _tool_calls_emitted:
                reasoning_only = _reasoning_seen or _think_filter.removed
                _record_error(
                    workspace_id, "reasoning_only" if reasoning_only else "empty_completion"
                )
                logger.warning(
                    "Backend %s completed without answer content (workspace=%s, model=%s, "
                    "reasoning_only=%s, completion_tokens=%d, finish_reason=%s).",
                    url,
                    workspace_id,
                    model,
                    reasoning_only,
                    _completion_tokens_seen,
                    _finish_reason,
                )
                yield _content_chunk(f"chatcmpl-{workspace_id}", workspace_id, NO_ANSWER_MESSAGE)
                _finish_reason = (
                    "length" if reasoning_only or _finish_reason == "length" else "stop"
                )
            yield _completion_finish_chunk(
                _finish_reason or ("tool_calls" if _tool_calls_emitted else "stop")
            )
            yield b"data: [DONE]\n\n"
    except httpx.TimeoutException:
        logger.warning(
            "Backend %s timed out during stream (workspace=%s) — probing engine state",
            url,
            workspace_id,
        )
        from portal.platform.inference.router.backend_introspect import (
            model_still_running as _msr,
        )

        _still_running = await _msr(url, timeout_s=5.0)
        if _still_running:
            logger.warning(
                "Backend %s: model still in /api/ps after stream timeout — "
                "reasoning model mid-generation? (workspace=%s)",
                url,
                workspace_id,
            )
            yield (
                "data: "
                + json.dumps(
                    {"error": "Response timed out — model may still be generating. Please retry."}
                )
                + "\n\n"
            ).encode()
        else:
            logger.warning(
                "Backend %s: no model in /api/ps after timeout — backend may be down (workspace=%s)",
                url,
                workspace_id,
            )
            _record_error(workspace_id, "stream_timeout")
            yield (
                "data: "
                + json.dumps({"error": "Backend timed out and no model is loaded. Please retry."})
                + "\n\n"
            ).encode()
    except Exception as e:
        logger.error("Stream error from %s: %s", url, e)
        _record_error(workspace_id, "stream_error")
        yield (
            "data: "
            + json.dumps({"error": "Backend connection error — check server logs"})
            + "\n\n"
        ).encode()
    finally:
        if start_time is not None:
            _record_response_time(model, workspace_id, time.monotonic() - start_time)


def _collect_text(chunk: bytes, parts: list[str]) -> None:
    """Extract content delta from an SSE chunk and append to parts list."""
    if chunk.startswith(b"data:"):
        try:
            obj = json.loads(chunk[5:].strip())
            for choice in obj.get("choices", []):
                text = choice.get("delta", {}).get("content") or ""
                if text:
                    parts.append(text)
        except Exception:
            logger.debug("Skipping malformed SSE chunk in _collect_text", exc_info=True)


async def _stream_with_chain(
    url: str,
    body: dict[str, Any],
    slot: RequestSlot,
    workspace_id: str = "unknown",
    primary_model: str = "unknown",
    chain: list[dict[str, Any]] | None = None,
    start_time: float | None = None,
    persona: str = "unknown",
    primary_tools: set[str] | None = None,
) -> AsyncIterator[bytes]:
    """Multi-hop purple-team chain: primary model followed by any number of follow-on hops.

    ``primary_tools`` runs hop 0 through the tool loop — a tool-using chain
    workspace (auto-security::purpleteam-exec) used to take the plain tool-loop
    branch in streaming and silently skip every follow-on hop, while the
    non-streaming path ran them.

    Hop 0 is the primary model using ``body`` as-is (system_prompt_append already
    applied by the router). Each subsequent hop is driven by an entry in ``chain``:

        model         — Ollama model ID for this hop
        label         — Markdown string emitted as the visual separator before this hop
        system        — Full system prompt for this hop
        user_template — User message with {hop_0}, {hop_1}, … placeholders referencing
                        prior hops' collected text. Defaults to "{hop_0}".

    All hops' [DONE] tokens are suppressed until the final hop, which closes the SSE
    connection naturally. The slot is held across all hops and released in finally.

    Example chain for auto-purpleteam-deep (4 hops):
        [
          {model: blue_model,   label: "🔵 BLUE TEAM ...",    system: "...", user_template: "{hop_0}"},
          {model: coder_model,  label: "🛡️ DETECTION ...",    system: "...", user_template: "RED:\n{hop_0}\nBLUE:\n{hop_1}"},
          {model: reason_model, label: "📋 IR PLAYBOOK ...",  system: "...", user_template: "RED:\n{hop_0}\nBLUE:\n{hop_1}\nDETECT:\n{hop_2}"},
        ]
    """
    _chain = chain or []
    ts = int(time.time())
    request_id = f"chatcmpl-p5-{ts}"

    def _make_chunk(delta: dict[str, Any]) -> bytes:
        payload = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": workspace_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode()

    yield _make_chunk({"role": "assistant", "content": ""})

    if _SHOW_ROUTING_STATUS:
        ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
        hop_models = [primary_model] + [h["model"] for h in _chain]
        chain_label = " ⟶ ".join(hop_models)
        yield _make_chunk({"content": f"`⚡ {ws_name} → {chain_label}`\n\n"})

    # collected[i] holds the joined text output of hop i
    collected: list[str] = []
    outcome = "interrupted"
    try:
        # ── Hop 0: primary model (uses body as-is) ───────────────────────────
        hop0_parts: list[str] = []
        has_more = bool(_chain)
        hop0 = (
            _stream_with_tool_loop_impl(
                url, body, workspace_id, primary_model, persona, primary_tools, start_time
            )
            if primary_tools
            else _stream_from_backend_guarded(
                url, body, workspace_id=workspace_id, model=primary_model, start_time=start_time
            )
        )
        async for chunk in hop0:
            if has_more and chunk == b"data: [DONE]\n\n":
                continue
            _collect_text(chunk, hop0_parts)
            yield chunk
        collected.append("".join(hop0_parts))

        # ── Hops 1..N ────────────────────────────────────────────────────────
        for hop_idx, hop_cfg in enumerate(_chain):
            prior_text = collected[-1]
            if not prior_text:
                # previous hop produced nothing — abort chain, emit [DONE]
                yield b"data: [DONE]\n\n"
                outcome = "complete"
                return

            hop_model = hop_cfg["model"]
            label = hop_cfg.get("label", "")
            system_prompt = hop_cfg.get("system", "")
            user_tmpl = hop_cfg.get("user_template", "{hop_0}")

            # Format user message using all collected outputs so far
            context_vars = {f"hop_{i}": collected[i] for i in range(len(collected))}
            try:
                user_content = user_tmpl.format(**context_vars)
            except KeyError:
                user_content = prior_text  # safe fallback

            if label:
                yield _make_chunk({"content": f"\n\n---\n\n{label}\n\n"})

            hop_tools: list[str] = hop_cfg.get("tools") or []
            is_last_hop = hop_idx == len(_chain) - 1
            hop_parts: list[str] = []

            if hop_tools:
                # Tool-enabled hop — build body without stripping tools, then
                # inject the hop's own tool schema and route through the tool loop.
                from portal.platform.inference.tool_registry import tool_registry  # noqa: PLC0415

                await tool_registry.refresh()
                tools_array = tool_registry.get_openai_tools(hop_tools)
                hop_body = {
                    **{k: v for k, v in body.items() if k not in ("tools", "tool_choice")},
                    "model": hop_model,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                }
                if tools_array:
                    hop_body["tools"] = tools_array
                    hop_body["tool_choice"] = "auto"
                    logger.info(
                        "Chain hop %d tool-loop: workspace=%s model=%s tools=%d",
                        hop_idx + 1,
                        workspace_id,
                        hop_model,
                        len(tools_array),
                    )
                    hop_url, hop_body = resolve_hop_target(workspace_id, hop_model, url, hop_body)
                    async for chunk in _stream_with_tool_loop_impl(
                        backend_url=hop_url,
                        body=hop_body,
                        workspace_id=workspace_id,
                        model=hop_model,
                        persona=persona,
                        effective_tools=set(hop_tools),
                        start_time=None,
                    ):
                        if not is_last_hop and chunk == b"data: [DONE]\n\n":
                            continue
                        _collect_text(chunk, hop_parts)
                        yield chunk
                else:
                    # Tool registry returned nothing — fall through to no-tools path
                    logger.warning(
                        "Chain hop %d: tools=%s resolved to empty list, falling back to no-tools",
                        hop_idx + 1,
                        hop_tools,
                    )
                    hop_tools = []

            if not hop_tools:
                # No-tools path (original behaviour)
                hop_body = {
                    k: v
                    for k, v in {
                        **body,
                        "model": hop_model,
                        "stream": True,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "tools": None,
                        "tool_choice": None,
                    }.items()
                    if v is not None
                }
                hop_url, hop_body = resolve_hop_target(workspace_id, hop_model, url, hop_body)
                async for chunk in _stream_from_backend_guarded(
                    hop_url,
                    hop_body,
                    workspace_id=workspace_id,
                    model=hop_model,
                    start_time=None,
                ):
                    if not is_last_hop and chunk == b"data: [DONE]\n\n":
                        continue
                    _collect_text(chunk, hop_parts)
                    yield chunk

            collected.append("".join(hop_parts))

        outcome = "complete"
    except Exception:
        outcome = "error"
        raise
    finally:
        trace_note(outcome=outcome)
        trace_span("stream.finished", outcome=outcome)
        slot.release()
        finalize_trace()


# ── Legacy two/three-hop shim (kept for any callers outside this module) ──────


async def _stream_with_secondary_chain(
    url: str,
    body: dict[str, Any],
    slot: RequestSlot,
    workspace_id: str = "unknown",
    model: str = "unknown",
    secondary_model: str = "",
    tertiary_model: str = "",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Legacy shim — delegates to _stream_with_chain. Do not add new callers."""
    _BLUE = (
        "You are a defensive security analyst. A red team operator has described an attack "
        "technique or scenario. Provide blue team analysis covering:\n"
        "- Detection opportunities and log sources to monitor\n"
        "- IOC signatures and behavioral indicators\n"
        "- MITRE ATT&CK mitigations and D3FEND countermeasures\n"
        "- Prioritized hardening recommendations\n"
        "Be specific and actionable."
    )
    _DETECT = (
        "You are a detection engineer. A purple team exercise has completed. "
        "Generate ready-to-deploy detection artifacts. Output ONLY the detection content.\n\n"
        "1. Sigma rule(s) (YAML) — one per primary technique.\n"
        "2. Wazuh custom rule(s) (XML) with <description>, <group>, <mitre> tags.\n"
        "3. Hunting query (SPL or KQL — label which platform).\n"
        "4. Atomic test command (optional) to validate the detection fires in a lab."
    )
    chain: list[dict[str, Any]] = []
    if secondary_model:
        chain.append(
            {
                "model": secondary_model,
                "label": "🔵 **BLUE TEAM ANALYSIS** *(Foundation-Sec-8B-Reasoning)*",
                "system": _BLUE,
                "user_template": "Analyze the following attack scenario for defensive detection and response:\n\n{hop_0}",
            }
        )
    if tertiary_model:
        chain.append(
            {
                "model": tertiary_model,
                "label": "🛡️ **DETECTION ENGINEERING** *(Qwen3-Coder)*",
                "system": _DETECT,
                "user_template": "## RED TEAM OUTPUT\n\n{hop_0}\n\n## BLUE TEAM ANALYSIS\n\n{hop_1}\n\nGenerate detection artifacts for the above.",
            }
        )
    async for chunk in _stream_with_chain(
        url,
        body,
        slot,
        workspace_id=workspace_id,
        primary_model=model,
        chain=chain,
        start_time=start_time,
    ):
        yield chunk


# ── Streaming dispatch helpers (decomposed from handlers.chat_completions) ────


def _prioritize_hinted_backend(candidates: list[Any], model_hint: str) -> list[Any]:
    """Move the first backend able to serve ``model_hint`` to the front.

    Workspace group priority remains the default. A concrete model hint is
    more specific, though, and streaming previously substituted the first
    backend's default model even when a later eligible backend contained the
    requested one. Non-streaming already skips candidates that cannot satisfy
    the hint; this gives streaming the same served-model behavior.

    Uses ``resolve_model`` rather than a plain ``in candidate.models`` check
    so a backend that serves the hint under an aliased native id (e.g. the
    oMLX entry translating a GGUF hint to its own model directory name)
    still matches — a bare membership check would always skip it in favor
    of the Ollama backend that carries the literal hint string.
    """
    if not model_hint:
        return candidates
    for index, candidate in enumerate(candidates):
        if candidate.resolve_model(model_hint) is not None:
            if index == 0:
                return candidates
            return [candidate, *candidates[:index], *candidates[index + 1 :]]
    return candidates


def _select_streaming_backend(
    workspace_id: str,
    candidates: list[Any],
) -> tuple[Any, str, str, list[dict[str, Any]], str, str]:
    """Pick the streaming backend + target model for a workspace.

    Reads the workspace's ``model_hint`` / ``chain`` / ``secondary_model`` /
    ``tertiary_model`` config, reorders candidates so the first can serve the
    hint, resolves the target model (translating aliases), and returns
    ``(backend, target_model, model_hint, chain, secondary_model,
    tertiary_model)``.
    """
    ws_cfg = WORKSPACES.get(workspace_id, {})
    model_hint = ws_cfg.get("model_hint", "")
    _chain = ws_cfg.get("chain") or []
    _secondary_model = ws_cfg.get("secondary_model", "")
    _tertiary_model = ws_cfg.get("tertiary_model", "")

    # Streaming: prefer the eligible backend that can actually serve the
    # requested model hint. If the stream yields an error chunk early, fall
    # back to non-streaming with the reordered remaining candidates.
    candidates = _prioritize_hinted_backend(candidates, model_hint)
    backend = candidates[0]

    # Pick target model from the workspace's model_hint, translating
    # through the backend's aliases (e.g. GGUF hint -> oMLX native id)
    # when the hint isn't served under its literal name.
    if model_hint:
        resolved_hint = backend.resolve_model(model_hint)
        if resolved_hint is not None:
            target_model = resolved_hint
        else:
            if not backend.models:
                logger.warning(
                    "Backend %s has empty models list — cannot fall back. Skipping.",
                    backend.id,
                )
                raise HTTPException(
                    502,
                    f"Backend {backend.id} has an empty models list — fix config/backends.yaml",
                )
            target_model = backend.models[0]
            logger.warning(
                "model_hint %r not in backend %s models — falling back to %r. "
                "Add it to config/backends.yaml or correct the hint in WORKSPACES.",
                model_hint,
                backend.id,
                target_model,
            )
            _hint_fallback_total.labels(
                workspace=workspace_id,
                hinted=model_hint,
                served=target_model,
                path="streaming",
            ).inc()
    else:
        if not backend.models:
            logger.warning(
                "Backend %s has empty models list — cannot resolve. Skipping.",
                backend.id,
            )
            raise HTTPException(
                502, f"Backend {backend.id} has an empty models list — fix config/backends.yaml"
            )
        _literal_model = backend.resolve_model(workspace_id)
        target_model = _literal_model if _literal_model is not None else backend.models[0]

    logger.info(
        "Stream routing: workspace=%s backend=%s model=%s (1/%d candidates)",
        workspace_id,
        backend.id,
        target_model,
        len(candidates),
    )

    return backend, target_model, model_hint, _chain, _secondary_model, _tertiary_model


async def _build_streaming_request(
    body: dict[str, Any],
    backend: Any,
    target_model: str,
    workspace_id: str,
    persona: str,
) -> tuple[dict[str, Any], list[str], bool, bool]:
    """Assemble the backend request body for the streaming path.

    Injects per-engine options, resolves the effective tool list, strips
    tools for non-tool models / ``portal_no_tools`` theory mode, and
    attaches the merged tool schemas. Returns
    ``(backend_body, effective_tools, _has_tools, _portal_no_tools)``.
    """
    backend_body = {**body, "model": target_model}

    # Per-engine option injection: keep_alive/num_batch/options for
    # Ollama; plain-OpenAI max_tokens/stream_options for oMLX.
    if backend.type == "ollama":
        backend_body = _inject_ollama_options(backend_body, workspace_id)
    elif backend.type == "omlx":
        backend_body = _inject_omlx_options(backend_body, workspace_id)

    # Resolve effective tool list for this request (M2)
    persona_data: PersonaSpec | dict[str, Any] = _PERSONA_MAP.get(persona, {})
    effective_tools = _resolve_persona_tools(persona_data, workspace_id)
    # portal_client_tools_only: a client that brings its own toolset (an
    # external agent, the WFE harness) is offered exactly those tools. The tool
    # loop still runs, so a call written as text is recovered and passed back
    # to the client; the workspace's MCP tools are neither offered nor dispatched.
    _client_tools_only = bool(backend_body.pop("portal_client_tools_only", False))
    if _client_tools_only:
        effective_tools = []
    # Per-model supports_tools lookup for both backend types — see
    # TASK_TOOL_SUPPORT_AUDIT_V1 §A4. The previous Ollama-default-true
    # logic caused tool-using workspaces to error when their fallback
    # chain landed on a non-tool-tagged Ollama model.
    backend_supports_tools = _model_supports_tools(target_model or "")
    # Strip any client-injected tools from the request body when the backend
    # model doesn't support tool calls — without this strip, Ollama returns
    # HTTP 400 "does not support tools" even for non-tool workspaces.
    if not backend_supports_tools:
        backend_body.pop("tools", None)
        backend_body.pop("tool_choice", None)
    # portal_no_tools: bench theory-pass flag — skip tool attachment entirely
    # so the model cannot call tools and must return prose (tool_choice=none
    # alone leaves tool definitions in the request, causing skeletal responses).
    _portal_no_tools = backend_body.pop("portal_no_tools", False)
    if _portal_no_tools:
        backend_body.pop("tools", None)
        backend_body.pop("tool_choice", None)
        _has_tools = False
    else:
        _has_tools = backend_supports_tools and (
            bool(effective_tools) or (_client_tools_only and bool(backend_body.get("tools")))
        )
    if effective_tools and not backend_supports_tools:
        logger.info(
            "Tool-call: workspace=%s persona=%s model=%s does not declare "
            "supports_tools — falling back to text-only response (no tools "
            "attached). Set supports_tools=true in config/backends.yaml after "
            "verification via tests/portal5_persona_matrix.py --audit-tools.",
            workspace_id,
            persona,
            target_model,
        )

    if _has_tools and _client_tools_only:
        backend_body["tool_choice"] = backend_body.get("tool_choice") or "auto"
    elif _has_tools:
        from portal.platform.inference.tool_registry import tool_registry

        _required_tool = None
        if backend_body.get("tool_choice") in (None, "auto"):
            _required_tool = _select_explicit_required_tool(
                backend_body.get("messages", []), set(effective_tools)
            )
        # _offer_tools narrows the SCHEMA the model sees; effective_tools
        # (returned below, used for _dispatch_tool_call authorization) stays
        # the workspace's full whitelist. A model under tool_choice=required
        # that names a different tool the workspace actually allows used to
        # have that call dropped by the whitelist gate — the narrowing was
        # a hint about what to offer, not a shrink of what's authorized.
        _offer_tools = [_required_tool] if _required_tool else effective_tools
        if _required_tool:
            backend_body["tool_choice"] = "required"
            logger.info(
                "Tool-call: workspace=%s explicit side-effect intent selected required tool=%s",
                workspace_id,
                _required_tool,
            )
        await tool_registry.refresh()
        tools_array = tool_registry.get_openai_tools(_offer_tools)
        # Merge client-injected tools with workspace tools — clients
        # (e.g. bench blue/purple) may inject domain-specific tools
        # that complement the workspace tools, not replace them.
        client_tools = [] if _required_tool else backend_body.get("tools", [])
        if tools_array:
            if client_tools:
                seen_names = {t.get("function", {}).get("name") for t in tools_array}
                for ct in client_tools:
                    ct_name = ct.get("function", {}).get("name", "")
                    if ct_name and ct_name not in seen_names:
                        tools_array.append(ct)
                        seen_names.add(ct_name)
            backend_body["tools"] = tools_array
            backend_body["tool_choice"] = (
                backend_body.get("tool_choice")
                or _resolve_persona_tool_choice(persona_data)
                or WORKSPACES.get(workspace_id, {}).get("tool_choice")
                or "auto"
            )
            logger.info(
                "Tool-call: workspace=%s persona=%s exposed %d tools (merged)",
                workspace_id,
                persona,
                len(tools_array),
            )
        else:
            _has_tools = False

    return backend_body, effective_tools, _has_tools, _portal_no_tools


def _select_stream_fn(
    backend: Any,
    backend_body: dict[str, Any],
    slot: RequestSlot,
    workspace_id: str,
    target_model: str,
    persona: str,
    effective_tools: list[str],
    start_time: float,
    chain: list[dict[str, Any]],
    secondary_model: str,
    tertiary_model: str,
    portal_no_tools: bool,
    has_tools: bool,
) -> AsyncIterator[bytes]:
    """Pick the streaming generator for the resolved backend/body.

    Chooses ``_stream_with_chain`` (multi-hop chain, unless theory mode; its
    first hop uses the tool loop when tools apply), ``_stream_with_tool_loop``
    (tools), ``_stream_with_secondary_chain``
    (legacy secondary/tertiary chain), else ``_stream_with_preamble``.
    Detaches the slot for the generator's lifetime.
    """
    if chain and not portal_no_tools:
        # Chain requires tool execution to be meaningful — skip in theory
        # mode (portal_no_tools) so exec models get a plain prose prompt
        # instead of hallucinating the entire multi-hop chain themselves.
        # Checked before has_tools: a tool-using chain runs its first hop
        # through the tool loop rather than dropping the chain.
        return _stream_with_chain(
            backend.chat_url,
            backend_body,
            slot.detach(),
            workspace_id=workspace_id,
            primary_model=target_model,
            chain=chain,
            start_time=start_time,
            persona=persona,
            primary_tools=set(effective_tools) if has_tools else None,
        )
    elif has_tools:
        return _stream_with_tool_loop(
            backend.chat_url,
            backend_body,
            slot.detach(),
            workspace_id,
            target_model,
            persona,
            set(effective_tools),
            start_time,
        )
    elif secondary_model:
        return _stream_with_secondary_chain(
            backend.chat_url,
            backend_body,
            slot.detach(),
            workspace_id=workspace_id,
            model=target_model,
            secondary_model=secondary_model,
            tertiary_model=tertiary_model,
            start_time=start_time,
        )
    else:
        return _stream_with_preamble(
            backend.chat_url,
            backend_body,
            slot.detach(),
            workspace_id=workspace_id,
            model=target_model,
            start_time=start_time,
        )


async def _stream_with_fallback(
    backend: Any,
    body: dict[str, Any],
    workspace_id: str,
    target_model: str,
    persona: str,
    effective_tools: list[str],
    start_time: float,
    has_tools: bool,
    chain: list[dict[str, Any]],
    portal_no_tools: bool,
    secondary_model: str,
    tertiary_model: str,
    remaining: list[Any],
    slot: RequestSlot,
    backend_body: dict[str, Any],
) -> AsyncIterator[bytes]:
    """Streaming wrapper for the multi-candidate path; falls back to non-streaming.

    Formerly a nested closure inside ``chat_completions``; lifted to module
    scope with the ~15 captured locals (backend, body, semaphores,
    target_model, etc.) promoted to explicit parameters.

    Behaviour:

    1. Stream from ``backend`` (first candidate) via either
       ``_stream_with_tool_loop`` or ``_stream_with_preamble``
       depending on ``has_tools``.
    2. Detect failure by either a parsed error envelope
       (``_stream_error``) or an exception from the inner generator.
    3. No fallback when output already reached the client (a second
       answer would be appended to the partial one) or when the backend
       rejected the request as malformed (HTTP 400/413/422 — every
       candidate would reject it alike): the error is reported instead.
    4. Otherwise try the **remaining** candidates non-streaming, skipping
       any ``(engine URL, model)`` pair already attempted — several backend
       groups front one engine, so the same request would just be resent.
       A success is wrapped as SSE (OWUI cannot tolerate a Content-Type
       switch mid-stream — once SSE has started it must stay SSE).

    Semaphore release is delegated to the streaming function
    (``_stream_with_tool_loop`` or ``_stream_with_preamble``) via
    their own ``try/finally``. This generator does not own
    semaphores.
    """
    stream_failed = False
    _error_buffer = None

    def _record_fallback_route(result: Any, candidate: Any) -> None:
        route_parts = result.headers.get("x-portal-route", "").split(";")
        resolved_backend = (
            route_parts[1] if len(route_parts) > 1 and route_parts[1] else candidate.id
        )
        resolved_model = route_parts[2] if len(route_parts) > 2 and route_parts[2] else target_model
        trace_note(backend=resolved_backend, model=resolved_model, outcome="ok")
        trace_span(
            "backend.selected",
            backend=resolved_backend,
            model=resolved_model,
            fallback=True,
        )

    _output_sent = False  # any content/reasoning/tool call reached the client
    _error_status: int | None = None
    _freed_ollama = False
    await make_room_for_omlx(backend, backend_body)
    while True:
        try:
            _inner_stream = _select_stream_fn(
                backend,
                backend_body,
                slot,
                workspace_id,
                target_model,
                persona,
                effective_tools,
                start_time,
                chain,
                secondary_model,
                tertiary_model,
                portal_no_tools,
                has_tools,
            )
            async for chunk in _inner_stream:
                if stream_failed:
                    # Drain after an error: a trailing [DONE] forwarded here would
                    # end the client's read before any fallback answer arrives.
                    continue
                _err = _stream_error(chunk)
                if _err is not None:
                    stream_failed = True
                    _error_buffer = chunk
                    _error_status = _err
                    continue
                if not _output_sent and _chunk_has_output(chunk):
                    _output_sent = True
                yield chunk
        except Exception:
            stream_failed = True
        # oMLX rejected the prompt for memory it cannot reclaim from Ollama:
        # free Ollama's idle models and retry oMLX once before cascading to the
        # slower engine. The first attempt has already released the slot, and
        # release is idempotent, so the retry runs unslotted for those moments.
        if (
            stream_failed
            and not _output_sent
            and not _freed_ollama
            and getattr(backend, "type", "") == "omlx"
            and _error_status == 400
            and _error_buffer
            and _is_capacity_error(_stream_error_detail(_error_buffer))
        ):
            _freed_ollama = True
            _freed = await free_ollama_for_omlx()
            if _freed:
                logger.info(
                    "oMLX capacity rejection for workspace=%s; freed Ollama %s, retrying oMLX",
                    workspace_id,
                    _freed,
                )
                stream_failed = False
                _error_buffer = None
                _error_status = None
                continue
        break

    if stream_failed and (
        _output_sent or _is_noncascadable_stream_error(_error_status, _error_buffer)
    ):
        # Part of an answer is already on screen — a fallback would append a
        # second, different answer to it. A malformed request (4xx, minus an
        # oMLX capacity rejection wearing a 400) fails the same on every
        # candidate. Either way, report the error and stop.
        yield _error_buffer or b'data: {"error": "Backend stream failed"}\n\n'
        yield _DONE
        _record_error(workspace_id, "stream_failed_after_output" if _output_sent else "bad_request")
        trace_note(outcome="error")
        finalize_trace()
        return

    if stream_failed:
        fallback_body = {**body, "stream": False}
        # The streamed (engine, model) pair already failed; several backend
        # groups front the same engine, so resending there is a repeat.
        tried: dict[tuple[str, str], str] = {(backend.chat_url, target_model): ""}
        if remaining:
            logger.info(
                "Stream from %s failed, falling back to remaining backends for workspace=%s",
                backend.id,
                workspace_id,
            )
            for j, fb in enumerate(remaining):
                fb_last = j == len(remaining) - 1
                try:
                    result = await _try_non_streaming(
                        fb,
                        fallback_body,
                        workspace_id,
                        start_time,
                        enforce_hint=not fb_last,
                        persona=persona,
                        tried=tried,
                    )
                except BackendRequestError as exc:
                    _error_buffer = (
                        f"data: {json.dumps({'error': exc.detail, 'status': exc.status_code})}\n\n"
                    ).encode()
                    break
                if result is not None:
                    _record_fallback_route(result, fb)
                    data = json.loads(_as_bytes(result.body))
                    for frame in _json_completion_to_sse(
                        data, workspace_id, thinking_enabled=_thinking_enabled(body)
                    ):
                        yield frame
                    finalize_trace()
                    return

        if _error_buffer:
            yield _error_buffer
        else:
            yield b'data: {"error": "All backends failed"}\n\n'
        yield _DONE
        _record_error(workspace_id, "all_backends_failed")
        trace_note(outcome="error")
        trace_span("backend.failed", backend=backend.id)
        finalize_trace()
