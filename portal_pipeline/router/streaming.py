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

    while hop < MAX_TOOL_HOPS:
        hop += 1

        # Accumulators for this iteration
        tool_calls_buf: list[dict] = []
        finish_reason: str | None = None

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

                    # When thinking is disabled, Gemma 4 puts its answer in
                    # reasoning_content with empty content, or inside <think>
                    # tags in content. Both render as <details type="reasoning">
                    # in OWUI and get stripped by the test driver. Convert to
                    # regular content so the answer is visible.
                    _thinking_off = not current_body.get("enable_thinking", True)
                    _rc = delta.get("reasoning_content")
                    _ct = delta.get("content") or ""

                    if _rc and not _ct and (_thinking_off or hop > 1):
                        # reasoning_content with no content — surface as content.
                        # hop > 1: synthesis hops always surface reasoning as content
                        # so recalled keywords are visible, not buried in <details>.
                        _new_delta = {k: v for k, v in delta.items() if k != "reasoning_content"}
                        _new_delta["content"] = _rc
                        _new_obj = dict(obj)
                        _new_obj["choices"] = [dict(choice, delta=_new_delta)]
                        yield f"data: {json.dumps(_new_obj)}\n\n".encode()
                        continue

                    if _ct and "<think>" in _ct and _thinking_off:
                        # <think>answer</think> in content with empty actual
                        # response — strip wrapper and surface inner text.
                        import re as _re_s

                        _stripped = _re_s.sub(
                            r"<think>.*?</think>", "", _ct, flags=_re_s.DOTALL | _re_s.IGNORECASE
                        ).strip()
                        if not _stripped:
                            _inner = _re_s.sub(
                                r"<think>(.*?)</think>",
                                r"\1",
                                _ct,
                                flags=_re_s.DOTALL | _re_s.IGNORECASE,
                            ).strip()
                            if _inner:
                                _new_delta = dict(delta)
                                _new_delta["content"] = _inner
                                _new_obj = dict(obj)
                                _new_obj["choices"] = [dict(choice, delta=_new_delta)]
                                yield f"data: {json.dumps(_new_obj)}\n\n".encode()
                                continue

                    yield (line + "\n\n").encode()
        except Exception as e:
            logger.error("Tool-loop stream error from %s: %s", backend_url, e)
            _record_error(workspace_id, "stream_error")
            yield (f"data: {json.dumps({'error': 'Backend connection error'})}\n\n").encode()
            return

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
            # Continue loop for next iteration
        else:
            # Model finished without tool calls — done
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
                # Fast-path: detect "done" (usage payload or [DONE] marker)
                if '"done"' in line and line.startswith("data:") and line != "data: [DONE]":
                    payload = line[5:].strip()
                    if payload:
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
                        except Exception:
                            logger.debug("Could not parse usage payload from stream")
                # OpenAI SSE: "data: [DONE]" terminator
                if line.startswith("data: [DONE]"):
                    elapsed = (time.monotonic() - start_time) if start_time is not None else None
                    _record_usage(
                        model=model,
                        workspace=workspace_id,
                        data={},
                        elapsed_seconds=elapsed,
                    )

                # Reasoning-model deltas under Ollama /v1: keep the behaviour,
                # fix the attribution — promote reasoning → content
                if '"reasoning"' in line and '"content"' not in line:
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
