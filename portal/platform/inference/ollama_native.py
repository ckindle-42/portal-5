"""Serve OpenAI-shaped chat requests to Ollama from its NATIVE /api/chat.

Why: Ollama's /v1/chat/completions silently drops most sampling. Measured
2026-09-25 on Ollama 0.34.2 (gemma4 + qwen3-vl, extreme values so an honoured
key is unmistakable): the whole ``options`` object is ignored, and top_k,
min_p and repeat_penalty are ignored at the top level too — /v1 honours only
temperature, top_p, seed, frequency_penalty and max_tokens, and a top-level
``think: true`` is dropped. /api/chat honours every one of them. Every
workspace served by Ollama was therefore running at its tag's baked sampling,
not the sampling ``config/portal.yaml`` declares for it.

The pipeline speaks OpenAI end to end (streaming, tool loop, council,
non-streaming fallback), so the fix sits at the HTTP boundary: an httpx
transport on the shared client that answers POST ``<ollama>/v1/chat/completions``
from ``/api/chat`` and translates the response back to the exact shape /v1
emits (``reasoning`` for thinking, ``tool_calls`` with string arguments and
``finish_reason: tool_calls``, a trailing usage chunk, ``[DONE]``). Nothing
upstream changes; every other URL passes through untouched.

Deliberately NOT forwarded — model-lifecycle fields, because /v1 never
delivered them and turning them on is a memory-behaviour change, not a fix:
  * load-time options (num_ctx, num_batch, ...): honouring them would reload a
    resident model whenever a caller's value differed from the loaded instance.
    The context window stays a property of the ``-ctxNk`` tag, as before.
  * ``keep_alive``: /v1 has no such field, so the pipeline's -1 default and the
    per-workspace 5m/10m overrides have never applied — every model has been
    released on Ollama's server default. Delivering -1 would pin models that
    oMLX (a separate process) cannot reclaim. An operator decision, recorded in
    KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Per-request sampling options /api/chat honours. Load-time options are left
#: out on purpose (module docstring).
_SAMPLING_OPTIONS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "stop",
        "num_predict",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
    }
)

#: OpenAI top-level fields that map onto an Ollama option of the same name.
#: top_k/min_p/repeat_penalty are not OpenAI fields, but callers that know they
#: are talking to Ollama (the WFE harness) send them top-level.
_TOP_LEVEL_OPTIONS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "stop",
)

_CHAT_PATH = "/v1/chat/completions"


# ── request: OpenAI -> native ───────────────────────────────────────────────


def _tool_call_to_native(tc: dict[str, Any]) -> dict[str, Any]:
    fn = dict(tc.get("function") or {})
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    out: dict[str, Any] = {"function": {"name": fn.get("name", ""), "arguments": args or {}}}
    if tc.get("id"):
        out["id"] = tc["id"]
    return out


def _content_parts(role: str, content: Any) -> list[dict[str, Any]]:
    """OpenAI string-or-parts content -> native messages. A parts list becomes
    ONE MESSAGE PER PART, in order, which is what /v1 itself does (measured:
    text+image in one native message renders 1040 prompt tokens, as /v1's
    split form 1045 — the split is the parity target)."""
    if not isinstance(content, list):
        return [{"role": role, "content": content if isinstance(content, str) else ""}]
    out: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            out.append({"role": role, "content": str(part.get("text", ""))})
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if isinstance(url, str) and url.startswith("data:") and "," in url:
                out.append({"role": role, "content": "", "images": [url.split(",", 1)[1]]})
    return out or [{"role": role, "content": ""}]


def messages_to_native(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate OpenAI chat messages to /api/chat messages. Tool results carry
    both ``tool_call_id`` and the ``tool_name`` it resolves to, so a template
    that renders either form gets it."""
    names: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        parts = _content_parts(role, m.get("content"))
        nm = parts[-1]
        thinking = m.get("reasoning") or m.get("reasoning_content") or m.get("thinking")
        if thinking:
            nm["thinking"] = thinking
        if m.get("tool_calls"):
            nm["tool_calls"] = [_tool_call_to_native(tc) for tc in m["tool_calls"]]
            for tc in m["tool_calls"]:
                if tc.get("id"):
                    names[tc["id"]] = (tc.get("function") or {}).get("name", "")
        if role == "tool":
            call_id = m.get("tool_call_id")
            if call_id:
                nm["tool_call_id"] = call_id
            name = m.get("name") or names.get(call_id or "", "")
            if name:
                nm["tool_name"] = name
        out.extend(parts)
    return out


def _think_value(body: dict[str, Any]) -> bool | str | None:
    """The think control implied by the OpenAI body: an explicit ``think``, else
    ``reasoning_effort`` (``none`` suppresses; a tier is gpt-oss's level)."""
    think = body.get("think")
    if isinstance(think, bool | str):
        return think
    effort = body.get("reasoning_effort")
    if effort == "none":
        return False
    if effort in ("low", "medium", "high"):
        return str(effort)
    return None


def _tools_for_choice(tools: list[dict[str, Any]], choice: Any) -> list[dict[str, Any]]:
    """Apply ``tool_choice`` the one way /api/chat allows — by what is offered.

    It has no tool_choice field, so ``"none"`` (offer nothing) and a named
    function (offer only that one) are expressed through the tools list;
    dropping the field let the model call tools the caller had forbidden.
    ``"required"`` cannot be expressed and stays a no-op.
    """
    if choice == "none":
        return []
    if isinstance(choice, dict):
        name = (choice.get("function") or {}).get("name")
        named = [t for t in tools if (t.get("function") or {}).get("name") == name]
        return named or tools
    return tools


def to_native_request(body: dict[str, Any], can_think: bool) -> dict[str, Any]:
    """Build the /api/chat body for an OpenAI chat body."""
    options = {k: v for k, v in (body.get("options") or {}).items() if k in _SAMPLING_OPTIONS}
    for key in _TOP_LEVEL_OPTIONS:
        if body.get(key) is not None:
            options[key] = body[key]
    # OpenAI allows a bare string; /api/chat 500s on anything but an array.
    if isinstance(options.get("stop"), str):
        options["stop"] = [options["stop"]]
    max_tokens = body.get("max_completion_tokens") or body.get("max_tokens")
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    native: dict[str, Any] = {
        "model": body.get("model"),
        "messages": messages_to_native(body.get("messages") or []),
        "stream": bool(body.get("stream", False)),
        "options": options,
    }
    tools = _tools_for_choice(body.get("tools") or [], body.get("tool_choice"))
    if tools:
        native["tools"] = tools
    fmt = body.get("response_format") or {}
    if fmt.get("type") == "json_object":
        native["format"] = "json"
    elif fmt.get("type") == "json_schema":
        native["format"] = (fmt.get("json_schema") or {}).get("schema") or "json"
    think = _think_value(body)
    # A think field of either polarity is rejected (400 "does not support
    # thinking") by a model without the capability; /v1 dropped it silently.
    if think is not None and can_think:
        native["think"] = think
    return native


# ── response: native -> OpenAI ──────────────────────────────────────────────


def _openai_tool_calls(calls: list[dict[str, Any]], start: int) -> list[dict[str, Any]]:
    out = []
    for i, tc in enumerate(calls):
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        out.append(
            {
                "id": tc.get("id") or f"call_{start + i}",
                "index": start + i,
                "type": "function",
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": args
                    if isinstance(args, str)
                    else json.dumps(args or {}, separators=(",", ":")),
                },
            }
        )
    return out


def _usage(final: dict[str, Any]) -> dict[str, Any]:
    p, c = final.get("prompt_eval_count") or 0, final.get("eval_count") or 0
    return {
        "prompt_tokens": p,
        "prompt_tokens_details": {"cached_tokens": final.get("prompt_eval_cached_count") or 0},
        "completion_tokens": c,
        "total_tokens": p + c,
    }


def _finish(done_reason: str | None, saw_tools: bool) -> str:
    if saw_tools:
        return "tool_calls"
    return "length" if done_reason == "length" else "stop"


def _envelope(
    model: str, obj: str, choices: list[dict[str, Any]], created: int, cid: str
) -> dict[str, Any]:
    return {
        "id": cid,
        "object": obj,
        "created": created,
        "model": model,
        "system_fingerprint": "fp_ollama",
        "choices": choices,
    }


def to_openai_completion(native: dict[str, Any]) -> dict[str, Any]:
    """A non-streamed /api/chat response as a /v1 chat.completion."""
    msg = native.get("message") or {}
    out_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("thinking"):
        out_msg["reasoning"] = msg["thinking"]
    calls = msg.get("tool_calls") or []
    if calls:
        out_msg["tool_calls"] = _openai_tool_calls(calls, 0)
    body = _envelope(
        native.get("model", ""),
        "chat.completion",
        [
            {
                "index": 0,
                "message": out_msg,
                "finish_reason": _finish(native.get("done_reason"), bool(calls)),
            }
        ],
        int(time.time()),
        f"chatcmpl-{time.monotonic_ns() % 1000}",
    )
    body["usage"] = _usage(native)
    return body


async def native_stream_to_sse(
    lines: AsyncIterator[str], include_usage: bool
) -> AsyncIterator[bytes]:
    """Translate /api/chat NDJSON lines into /v1 SSE bytes."""
    created, cid = int(time.time()), f"chatcmpl-{time.monotonic_ns() % 1000}"
    first, n_calls, model = True, 0, ""

    def sse(obj: dict[str, Any]) -> bytes:
        return f"data: {json.dumps(obj, separators=(',', ':'))}\n\n".encode()

    async for line in lines:
        line = line.strip()
        if not line:
            continue
        chunk = json.loads(line)
        if chunk.get("error"):
            yield sse({"error": {"message": chunk["error"], "type": "api_error"}})
            break
        model = chunk.get("model", model)
        msg = chunk.get("message") or {}
        if chunk.get("done"):
            # The final chunk can still carry message fields; dropping its
            # tool_calls would also misreport finish_reason as "stop".
            final_delta: dict[str, Any] = {}
            if msg.get("content"):
                final_delta["content"] = msg["content"]
            if msg.get("thinking"):
                final_delta["reasoning"] = msg["thinking"]
            if msg.get("tool_calls"):
                final_delta["tool_calls"] = _openai_tool_calls(msg["tool_calls"], n_calls)
                n_calls += len(msg["tool_calls"])
            if final_delta:
                yield sse(
                    _envelope(
                        model,
                        "chat.completion.chunk",
                        [{"index": 0, "delta": final_delta, "finish_reason": None}],
                        created,
                        cid,
                    )
                )
            yield sse(
                _envelope(
                    model,
                    "chat.completion.chunk",
                    [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": _finish(chunk.get("done_reason"), n_calls > 0),
                        }
                    ],
                    created,
                    cid,
                )
            )
            if include_usage:
                usage_chunk = _envelope(model, "chat.completion.chunk", [], created, cid)
                usage_chunk["usage"] = _usage(chunk)
                yield sse(usage_chunk)
            break
        delta: dict[str, Any] = {"role": "assistant"} if first else {}
        first = False
        delta["content"] = msg.get("content") or ""
        if msg.get("thinking"):
            delta["reasoning"] = msg["thinking"]
        if msg.get("tool_calls"):
            delta["tool_calls"] = _openai_tool_calls(msg["tool_calls"], n_calls)
            n_calls += len(msg["tool_calls"])
        yield sse(
            _envelope(
                model,
                "chat.completion.chunk",
                [{"index": 0, "delta": delta, "finish_reason": None}],
                created,
                cid,
            )
        )
    yield b"data: [DONE]\n\n"


_ERROR_TYPES = {400: "invalid_request_error", 404: "not_found_error"}


def _error_body(status: int, raw: bytes) -> bytes:
    """/api/chat errors are {"error": "..."}; /v1's are {"error": {...}}."""
    try:
        msg = json.loads(raw).get("error") or raw.decode(errors="ignore")
    except Exception:
        msg = raw.decode(errors="ignore")
    err = {
        "message": msg,
        "type": _ERROR_TYPES.get(status, "api_error"),
        "param": None,
        "code": None,
    }
    return json.dumps({"error": err}).encode()


# ── transport ───────────────────────────────────────────────────────────────


class _TranslatedStream(httpx.AsyncByteStream):
    def __init__(self, inner: httpx.Response, include_usage: bool) -> None:
        self._inner = inner
        self._include_usage = include_usage

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for out in native_stream_to_sse(self._inner.aiter_lines(), self._include_usage):
            yield out

    async def aclose(self) -> None:
        await self._inner.aclose()


class OllamaNativeTransport(httpx.AsyncBaseTransport):
    """Answers /v1/chat/completions for Ollama backends from /api/chat.

    ``is_ollama(base_url)`` decides which bases are Ollama; it must return
    False for anything it does not positively know to be Ollama, so vLLM/oMLX
    and unknown URLs pass through unchanged.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, is_ollama: Callable[[str], bool]) -> None:
        self._inner = inner
        self._is_ollama = is_ollama
        self._thinking: dict[tuple[str, str], bool] = {}

    async def _can_think(self, base: str, model: str, extensions: dict[str, Any]) -> bool:
        key = (base, model)
        if key not in self._thinking:
            can = False
            try:
                req = httpx.Request(
                    "POST", f"{base}/api/show", json={"model": model}, extensions=extensions
                )
                resp = await self._inner.handle_async_request(req)
                raw = await resp.aread()
                await resp.aclose()
                if resp.status_code == 200:
                    can = "thinking" in (json.loads(raw).get("capabilities") or [])
                    self._thinking[key] = can
            except Exception as e:  # capability unknown: do not send think
                logger.warning("ollama_native: /api/show %s failed: %s", model, e)
            return can
        return self._thinking[key]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method != "POST" or not request.url.path.endswith(_CHAT_PATH):
            return await self._inner.handle_async_request(request)
        base = url.split(_CHAT_PATH)[0].rstrip("/")
        if not self._is_ollama(base):
            return await self._inner.handle_async_request(request)

        body = json.loads(await request.aread() or b"{}")
        can_think = await self._can_think(base, str(body.get("model", "")), request.extensions)
        native = to_native_request(body, can_think)
        native_req = httpx.Request(
            "POST", f"{base}/api/chat", json=native, extensions=request.extensions
        )
        resp = await self._inner.handle_async_request(native_req)

        if resp.status_code != 200:
            raw = await resp.aread()
            await resp.aclose()
            return httpx.Response(
                resp.status_code,
                headers={"content-type": "application/json"},
                content=_error_body(resp.status_code, raw),
                request=request,
            )
        if native["stream"]:
            include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
            inner = httpx.Response(resp.status_code, stream=resp.stream, request=native_req)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_TranslatedStream(inner, include_usage),
                request=request,
            )
        raw = await resp.aread()
        await resp.aclose()
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(to_openai_completion(json.loads(raw))).encode(),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
