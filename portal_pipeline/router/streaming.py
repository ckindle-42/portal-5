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
  bytes, with reasoning promotion and error envelope.

**Transport-only contract**: a prepared request goes in; OWUI-shaped SSE
bytes come out. No routing decisions, no persona resolution, no tool policy.
Imports from ``router.workspaces``, ``router.tools``, ``router.metrics``,
``router.state``, ``router.power``, and ``router.concurrency`` (for
:class:`~portal_pipeline.router.concurrency.RequestSlot` type). None of
those modules import ``streaming`` — the dependency graph is acyclic.

The shared ``httpx.AsyncClient`` is injected by ``lifespan`` as
``_http_client``; ``_SHOW_ROUTING_STATUS`` is parsed from env at import time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import httpx

from portal_pipeline.router.metrics import _record_response_time, _tool_loop_hops
from portal_pipeline.router.state import _record_error
from portal_pipeline.router.thinking import extract_think_inner, strip_think
from portal_pipeline.router.tools import _dispatch_tool_call
from portal_pipeline.router.workspaces import MAX_TOOL_HOPS, WORKSPACES

if TYPE_CHECKING:
    from portal_pipeline.router.concurrency import RequestSlot

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


def _json_completion_to_sse(data: dict, workspace_id: str) -> Iterator[bytes]:
    """Yield OpenAI completion JSON as SSE frames: role, content (with
    reasoning->content promotion when content empty), tool_calls, done,
    and [DONE] marker.
    """
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    role = message.get("role", "assistant")
    if role:
        yield f"data: {json.dumps({'choices': [{'delta': {'role': role}}]})}\n\n".encode()
    content = message.get("content")
    if not content:
        reasoning = message.get("reasoning_content")
        if reasoning:
            content = reasoning
    if content:
        yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n".encode()
    tool_calls = message.get("tool_calls")
    if tool_calls:
        yield f"data: {json.dumps({'choices': [{'delta': {'tool_calls': tool_calls}}]})}\n\n".encode()
    yield f"data: {json.dumps({'choices': [{'finish_reason': choice.get('finish_reason', 'stop')}]})}\n\n".encode()
    yield b"data: [DONE]\n\n"


# ── Streaming wrappers (own the RequestSlot lifecycle) ────────────────────────


async def _stream_with_tool_loop(
    backend_url: str,
    body: dict,
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
        slot: :class:`~portal_pipeline.router.concurrency.RequestSlot`
            (detached from the handler). ``slot.release()`` is called
            in ``finally:`` after the stream completes.

    Yields:
        SSE bytes for OWUI consumption.
    """
    try:
        async for chunk in _stream_with_tool_loop_impl(
            backend_url, body, workspace_id, model, persona, effective_tools, start_time
        ):
            yield chunk
    finally:
        slot.release()


async def _stream_with_tool_loop_impl(
    backend_url: str,
    body: dict,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
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

    **Reasoning-content rewriting**: when thinking is disabled but the
    model still emits content in ``delta.reasoning_content`` (Gemma 4
    quirk), OR when this is hop 2+ (synthesis after a tool call, where
    recalled content must be visible not buried in OWUI's
    ``<details type="reasoning">`` accordion), the delta is rewritten
    to surface ``reasoning_content`` as ``content``. Also strips
    ``<think>...</think>`` wrapper when content is the wrapped form.

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
    request_id = f"chatcmpl-p5-{int(time.time())}"
    hop = 0
    current_body = dict(body)
    _exec_audit: bool = bool(body.get("exec_audit"))
    _exec_audit_calls: list[dict] = []  # accumulates tool calls across all hops when exec_audit=true

    while hop < MAX_TOOL_HOPS:
        hop += 1

        # Accumulators for this iteration
        tool_calls_buf: list[dict] = []
        finish_reason: str | None = None
        _content_emitted: bool = False  # any non-think content reached client
        _think_content_buf: list[str] = []  # reasoning fallback if content is empty

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
            async with _http_client.stream("POST", backend_url, json=current_body) as resp:  # type: ignore[union-attr]
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(
                        "Tool-loop backend returned HTTP %d: %s", resp.status_code, err[:200]
                    )
                    yield (
                        f"data: {json.dumps({'error': f'Backend HTTP {resp.status_code}'})}\n\n"
                    ).encode()
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        yield (line + "\n\n").encode()
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        # Suppress hop-N [DONE] when more hops follow.
                        # Hop 2+ will emit their own [DONE] after the
                        # final answer is streamed.
                        if finish_reason != "tool_calls" or not tool_calls_buf:
                            yield b"data: [DONE]\n\n"
                        continue
                    try:
                        obj = json.loads(data_str)
                    except Exception:
                        yield (line + "\n\n").encode()
                        continue

                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta", {})

                    if delta.get("tool_calls"):
                        for tc_delta in delta["tool_calls"]:
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
                        # Some backends send tool_calls + finish_reason in
                        # the same final chunk — capture finish_reason here
                        # so the dispatch gate fires after the stream ends.
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        # Suppress tool_call delta — pipeline owns dispatch
                        continue

                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                        if finish_reason == "tool_calls":
                            # Suppress finish_reason=tool_calls chunk too
                            continue

                    # ── Think-content handling ──────────────────────────────
                    # Centralised logic for both reasoning_content (Qwen3/Ollama
                    # thinking mode) and <think>...</think> inline tags.
                    # Mirrors the non-stream promotion in router_pipe.py so the
                    # same fallback behaviour applies regardless of stream mode.
                    _thinking_off = not current_body.get("enable_thinking", True)
                    _rc = delta.get("reasoning_content")
                    _ct = delta.get("content") or ""

                    # Buffer reasoning_content for end-of-stream fallback.
                    if _rc:
                        _think_content_buf.append(_rc)

                    if _rc and not _ct and (_thinking_off or hop > 1):
                        # reasoning_content with no content — surface as content.
                        # hop > 1: synthesis hops always surface reasoning as content
                        # so recalled keywords are visible, not buried in <details>.
                        _new_delta = {k: v for k, v in delta.items() if k != "reasoning_content"}
                        _new_delta["content"] = _rc
                        _new_obj = dict(obj)
                        _new_obj["choices"] = [dict(choice, delta=_new_delta)]
                        yield f"data: {json.dumps(_new_obj)}\n\n".encode()
                        _content_emitted = True
                        continue

                    if _ct and "<think>" in _ct:
                        _stripped = strip_think(_ct)
                        _inner_think = extract_think_inner(_ct)
                        # Buffer inline think content for end-of-stream fallback.
                        if _inner_think and _inner_think != _stripped:
                            _think_content_buf.append(_inner_think)

                        if _thinking_off and not _stripped:
                            # Thinking disabled + content is pure think block —
                            # surface inner text as content.
                            if _inner_think:
                                _new_delta = dict(delta)
                                _new_delta["content"] = _inner_think
                                _new_obj = dict(obj)
                                _new_obj["choices"] = [dict(choice, delta=_new_delta)]
                                yield f"data: {json.dumps(_new_obj)}\n\n".encode()
                                _content_emitted = True
                                continue
                    elif _ct:
                        _content_emitted = True

                    yield (line + "\n\n").encode()
        except httpx.TimeoutException:
            _ollama_base = backend_url.split("/v1/")[0]
            logger.warning(
                "Tool-loop backend %s timed out (workspace=%s, hop=%d) — checking /api/ps",
                backend_url,
                workspace_id,
                hop,
            )
            try:
                from portal_pipeline.router.monitor import wait_for_model_loaded as _wfml

                _still_running = await _wfml(timeout_s=5.0, poll_s=5.0, ollama_url=_ollama_base)
            except Exception:
                _still_running = False
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

        # End-of-stream think fallback: if the model exhausted its token budget
        # inside a <think> block and emitted no actual content, surface the
        # accumulated reasoning as the response rather than returning empty.
        # Mirrors the non-stream promotion in router_pipe.py:1308-1335.
        if not _content_emitted and _think_content_buf:
            _fallback = " ".join(_think_content_buf).strip()
            if _fallback:
                logger.warning(
                    "Streaming hop %d/%d: model produced only thinking content "
                    "(workspace=%s) — promoting reasoning as response.",
                    hop,
                    MAX_TOOL_HOPS,
                    workspace_id,
                )
                _fb_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": workspace_id,
                    "choices": [
                        {"index": 0, "delta": {"content": _fallback}, "finish_reason": None}
                    ],
                }
                yield f"data: {json.dumps(_fb_chunk)}\n\n".encode()

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

            # Dispatch all tool calls in parallel
            dispatch_results = await asyncio.gather(
                *[
                    _dispatch_tool_call(tc, effective_tools, workspace_id, persona, request_id)
                    for tc in all_tool_calls
                ],
            )

            # Append assistant turn and tool results to message list
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": all_tool_calls,
            }
            current_body["messages"] = (
                current_body.get("messages", []) + [assistant_msg] + dispatch_results
            )

            logger.info(
                "Tool loop hop=%d/%d workspace=%s tools_called=%s",
                hop,
                MAX_TOOL_HOPS,
                workspace_id,
                [tc["function"]["name"] for tc in all_tool_calls],
            )
            if _exec_audit:
                _exec_audit_calls.extend(all_tool_calls)
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
                        }
                        for tc in _exec_audit_calls
                    ],
                }
                yield f"data: {json.dumps(audit_event)}\n\n".encode()
            if start_time is not None:
                _record_response_time(model, workspace_id, time.monotonic() - start_time)
            return


async def _stream_with_preamble(
    url: str,
    body: dict,
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
        slot: :class:`~portal_pipeline.router.concurrency.RequestSlot`
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

    def _make_chunk(delta: dict) -> bytes:
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
    try:
        async for chunk in _stream_from_backend_guarded(
            url, body, workspace_id=workspace_id, model=model, start_time=start_time
        ):
            yield chunk
    finally:
        slot.release()


async def _stream_from_backend_guarded(
    url: str,
    body: dict,
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
    from portal_pipeline.router.power import _record_usage

    if _http_client is None:
        logger.error("HTTP client not initialised — yielding error chunk")
        yield ("data: " + json.dumps({"error": "Pipeline not ready"}) + "\n\n").encode()
        return
    try:
        _usage_recorded = False  # guard: only record TPS once per request
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
                yield (
                    "data: "
                    + json.dumps({"error": f"Backend returned HTTP {resp.status_code}"})
                    + "\n\n"
                ).encode()
                return
            async for line in resp.aiter_lines():
                if not line:
                    continue
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
                elif '"completion_tokens"' in line and line.startswith("data:") and not _usage_recorded:
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
                        except Exception:
                            logger.debug("Could not parse OpenAI usage chunk from stream")
                # OpenAI SSE: "data: [DONE]" — TPS already recorded from usage chunk above
                if line.startswith("data: [DONE]"):
                    pass

                # Reasoning-model deltas under Ollama /v1: keep the behaviour,
                # fix the attribution — promote reasoning → content.
                # Gate on '"reasoning"' only — not '"content"' not in line, because
                # qwen3.6 HauhauCS emits {"content":"","reasoning":"..."} (empty
                # string content) which makes that substring check false. The inner
                # `not delta.get("content")` correctly handles both absent and empty.
                if '"reasoning"' in line:
                    try:
                        if not line.startswith("data:") or line == "data: [DONE]":
                            yield (line + "\n\n").encode()
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            yield (line + "\n\n").encode()
                            continue
                        obj = json.loads(payload)
                        for choice in obj.get("choices", []):
                            delta = choice.get("delta", {})
                            reasoning_val = (
                                delta.get("reasoning")
                                or delta.get("reasoning_content")
                                or delta.get("thinking")
                            )
                            if reasoning_val and not delta.get("content"):
                                delta["content"] = reasoning_val
                                delta.pop("reasoning", None)
                                delta.pop("reasoning_content", None)
                                delta.pop("thinking", None)
                        line = f"data: {json.dumps(obj)}"
                    except Exception:
                        pass  # Fall through to raw yield on parse failure

                yield (line + "\n\n").encode()
    except httpx.TimeoutException:
        _ollama_base = url.split("/v1/")[0]
        logger.warning(
            "Backend %s timed out during stream (workspace=%s) — checking /api/ps",
            url,
            workspace_id,
        )
        try:
            from portal_pipeline.router.monitor import wait_for_model_loaded as _wfml

            _still_running = await _wfml(timeout_s=5.0, poll_s=5.0, ollama_url=_ollama_base)
        except Exception:
            _still_running = False
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
            pass


async def _stream_with_chain(
    url: str,
    body: dict,
    slot: RequestSlot,
    workspace_id: str = "unknown",
    primary_model: str = "unknown",
    chain: list[dict] | None = None,
    start_time: float | None = None,
    persona: str = "unknown",
) -> AsyncIterator[bytes]:
    """Multi-hop purple-team chain: primary model followed by any number of follow-on hops.

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

    def _make_chunk(delta: dict) -> bytes:
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
    try:
        # ── Hop 0: primary model (uses body as-is) ───────────────────────────
        hop0_parts: list[str] = []
        has_more = bool(_chain)
        async for chunk in _stream_from_backend_guarded(
            url, body, workspace_id=workspace_id, model=primary_model, start_time=start_time
        ):
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
                from portal_pipeline.tool_registry import tool_registry  # noqa: PLC0415

                await tool_registry.refresh()
                tools_array = tool_registry.get_openai_tools(set(hop_tools))
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
                        hop_idx + 1, workspace_id, hop_model, len(tools_array),
                    )
                    async for chunk in _stream_with_tool_loop_impl(
                        backend_url=url,
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
                        hop_idx + 1, hop_tools,
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
                async for chunk in _stream_from_backend_guarded(
                    url,
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

    finally:
        slot.release()


# ── Legacy two/three-hop shim (kept for any callers outside this module) ──────


async def _stream_with_secondary_chain(
    url: str,
    body: dict,
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
    chain: list[dict] = []
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
