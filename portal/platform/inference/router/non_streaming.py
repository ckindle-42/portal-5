"""Non-streaming request dispatch.

Mirror of router/streaming.py for non-streaming completion requests.
Both modules are called from the chat_completions handler; the
streaming/non-streaming branch is decided by the request body's
``stream`` flag.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Collection
from typing import Any

import httpx
from fastapi.responses import JSONResponse

from portal.platform.inference.config import PersonaSpec
from portal.platform.inference.router.backend_introspect import _approx_prompt_tokens
from portal.platform.inference.router.correlation import get_correlation_id
from portal.platform.inference.router.download_links import (
    offers_file_creation,
    strip_unbacked_download_lines,
    successful_file_creation,
)
from portal.platform.inference.router.eval_gate import apply_bite_tool_scope, apply_eval_scope
from portal.platform.inference.router.metrics import (
    _answer_without_tool_retried,
    _hint_fallback_total,
    _tool_calls_recovered,
    _tool_repeat_suppressed,
)
from portal.platform.inference.router.power import _record_usage
from portal.platform.inference.router.state import _record_error
from portal.platform.inference.router.text_tool_calls import (
    drop_unparsed_markup,
    salvage_text_tool_calls,
)
from portal.platform.inference.router.thinking import (
    NO_ANSWER_MESSAGE,
    _reasoning_text,
    _thinking_enabled,
    strip_think,
)
from portal.platform.inference.router.tool_repeat import (
    FINAL_ANSWER_REQUEST,
    GROUNDING_REQUEST,
    UNGROUNDED_NOTICE,
    ToolRepeatGuard,
)
from portal.platform.inference.router.tools import (
    _dispatch_tool_call,
    _select_explicit_required_tool,
)
from portal.platform.inference.router.trace import (
    add_model_turn,
    current_portal_timings,
    usage_metric_kwargs,
)
from portal.platform.inference.router.trace import capture as trace_capture
from portal.platform.inference.router.trace import note as trace_note
from portal.platform.inference.router.truncation import take_notice as take_truncation_notice
from portal.platform.inference.router.validation import (
    _inject_ollama_options,
    _inject_omlx_options,
    _model_supports_tools,
)
from portal.platform.inference.router.workspaces import (
    _PERSONA_MAP,
    WORKSPACES,
    _resolve_persona_tool_choice,
    _resolve_persona_tools,
)

# Set by lifespan — same push pattern as streaming.py
_http_client: Any = None
registry: Any = None

logger = logging.getLogger(__name__)


class BackendRequestError(Exception):
    """The backend rejected the request itself (HTTP 4xx).

    Every other candidate would reject it the same way, so the caller surfaces
    it to the client instead of cascading — a cascade turned a bad parameter
    into an opaque 502 after sending the request to unrelated models.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


#: Statuses meaning the request itself is malformed. 404 (model not on this
#: engine), 408 and 429 stay cascadable — another candidate can serve those.
_REQUEST_ERROR_STATUSES = frozenset({400, 413, 422})

#: Substrings identifying oMLX's own capacity rejections (prefill_memory_guard
#: at 400, "cannot load" at 507) rather than a genuinely malformed request.
#: Matched case-insensitively. A false negative just means a capacity error
#: surfaces to the client instead of cascading (the behavior before this
#: distinction existed); a false positive would let a truly bad request loop
#: across every candidate before failing — the narrower match is the safer
#: side to err on.
_CAPACITY_ERROR_MARKERS = (
    "memory guard",
    "prefill memory",
    "would exceed",
    "projected memory",
    "cannot load",
    "does not fit",
    "dynamic memory ceiling",
    "metal_cap",
    "wired_limit",
)


def is_omlx_capacity_refusal(status: int, detail: bytes | str) -> bool:
    """An oMLX capacity refusal that freeing idle Ollama residents can cure: the 400 prefill
    guard or the 507 load ceiling ("does not fit under the dynamic memory ceiling"). Used by
    every path (streamed, tool-loop, non-streamed), so all three free and retry the same way."""
    return status in (400, 507) and _is_capacity_error(backend_error_detail(detail))


def is_omlx_prefill_refusal(status: int, detail: bytes | str) -> bool:
    """Identify oMLX's prompt-specific prefill guard response."""
    low = backend_error_detail(detail).lower().replace("_", " ")
    return status == 400 and "prefill" in low and "memory" in low


def format_omlx_prefill_error(detail: str, body: dict[str, Any]) -> str:
    """Add the shared prompt-size estimate to the engine's capacity detail."""
    prefix = "oMLX prefill memory guard refused"
    if prefix in detail:
        return detail
    return f"{prefix} estimated prompt size ~{_approx_prompt_tokens(body):,} tokens: {detail}"


def _omlx_prefill_refusal_detail(backend: Any, exc: Exception) -> str | None:
    if getattr(backend, "type", "") != "omlx" or not isinstance(exc, httpx.HTTPStatusError):
        return None
    if not is_omlx_prefill_refusal(exc.response.status_code, exc.response.content):
        return None
    return backend_error_detail(exc.response.content)


def _raise_prefill_capacity_error(detail: str | None, body: dict[str, Any]) -> None:
    """Raise the guard refusal, with the estimate, once the caller has no candidate left."""
    if detail is not None:
        raise BackendRequestError(400, format_omlx_prefill_error(detail, body))


def _is_capacity_error(detail: str) -> bool:
    """Whether a 400 is an engine capacity rejection, not a malformed request.

    oMLX's prefill_memory_guard returns HTTP 400 when it predicts a request
    would blow its own memory ceiling right now — a fact about current engine
    state, not the request's shape. Another engine (Ollama has an entirely
    different memory profile) would very likely serve it fine, so unlike a
    genuinely malformed request (bad JSON, an invalid parameter — the same
    failure on every candidate), this one is cascadable.

    The 2026-09-25 hardening pass that introduced ``_REQUEST_ERROR_STATUSES``
    (commit ddd4726c) didn't carry this distinction, which silently broke the
    "automatic Ollama fallback on unhealthy/rejects" pattern the oMLX
    shadow-shift design (P5-FANOUT-001, docs/TASK_FANOUT_CONCURRENCY_V1.md)
    depends on for every priority-10 alias. Found in the P5-FANOUT-001 audit
    follow-up, not yet reproduced as a live incident — the one lane that
    reliably trips the guard (granite-30b ctx98k) was already Ollama-only for
    an unrelated reason, and SWEEP_CONCURRENCY defaults to 1 (opt-in).
    """
    low = detail.lower()
    return any(marker in low for marker in _CAPACITY_ERROR_MARKERS)


def _raise_for_backend_status(resp: httpx.Response) -> None:
    if resp.status_code in _REQUEST_ERROR_STATUSES:
        detail = backend_error_detail(resp.content)
        if resp.status_code == 400 and _is_capacity_error(detail):
            resp.raise_for_status()  # a capacity rejection, not a bad request — cascade
            return
        raise BackendRequestError(resp.status_code, detail)
    resp.raise_for_status()


def backend_error_detail(raw: bytes | str) -> str:
    """The message from an OpenAI-style ``{"error": ...}`` body, else the raw text."""
    text = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
    try:
        err = json.loads(text).get("error")
    except Exception:
        return text[:500]
    if isinstance(err, dict):
        err = err.get("message")
    return str(err or text)[:500]


def _completion_body(resp: httpx.Response, workspace_id: str) -> dict[str, Any]:
    """``resp.json()`` for a completion, refusing an error object a backend wrote in its
    place (Ollama's qwen3coder parser abort, ollama#18563, also answers HTTP 200)."""
    data: dict[str, Any] = resp.json()
    if isinstance(data, dict) and "error" in data and not data.get("choices"):
        detail = backend_error_detail(json.dumps(data))
        logger.error(
            "Backend wrote an error inside an HTTP 200 body instead of a completion "
            "(workspace=%s correlation_id=%s): %s",
            workspace_id,
            get_correlation_id() or "-",
            detail,
        )
        _record_error(workspace_id, "backend_in_band_error")
        raise ValueError(f"backend error instead of a completion: {detail}")
    return data


#: Keys the primary request carries for its own engine (Ollama native options,
#: oMLX template kwargs, the think control). A hop served elsewhere must not
#: inherit them.
_ENGINE_SPECIFIC_KEYS = (
    "options",
    "keep_alive",
    "think",
    "reasoning_effort",
    "chat_template_kwargs",
    "repetition_penalty",
)


def resolve_hop_target(
    workspace_id: str, hop_model: str, primary_url: str, hop_body: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """``(chat_url, body)`` for one chain hop.

    Chain hops used to be posted to the primary backend's URL with the hop's
    raw model id. With the primary on oMLX (priority seats) every hop naming an
    Ollama tag 404'd — the purple-team chains silently lost their blue-team,
    detection and IR hops. The hop now goes to the first healthy backend that
    serves its model (workspace groups first, then any), under that backend's
    native id.
    """
    if registry is None:
        return primary_url, hop_body
    seen: set[str] = set()
    for b in [*registry.get_backend_candidates(workspace_id), *registry.list_healthy_backends()]:
        if b.id in seen:
            continue
        seen.add(b.id)
        native = b.resolve_model(hop_model)
        if native is None:
            continue
        body = {**hop_body, "model": native}
        if b.chat_url != primary_url:
            for key in _ENGINE_SPECIFIC_KEYS:
                body.pop(key, None)
        return b.chat_url, body
    logger.warning(
        "Chain hop model %s is not served by any healthy backend (workspace=%s)",
        hop_model,
        workspace_id,
    )
    return primary_url, hop_body


async def _run_non_streaming_chain(
    primary_text: str,
    chain: list[dict[str, Any]],
    backend: Any,
    body: dict[str, Any],
    workspace_id: str,
    start_time: float,
    primary_data: dict[str, Any],
    primary_model: str,
) -> JSONResponse:
    """Run the N additional hops for a non-streaming chain request.

    Each hop uses SSE streaming internally so completion is event-driven
    (we finish when [DONE] arrives, not when a fixed timer fires). Results
    are concatenated with separator headers and returned as a single
    non-streaming JSONResponse.
    """
    import json as _json

    collected: list[str] = [primary_text]
    combined_parts: list[str] = [primary_text]

    for hop_cfg in chain:
        hop_model = hop_cfg["model"]
        label = hop_cfg.get("label", "")
        system_prompt = hop_cfg.get("system", "")
        user_tmpl = hop_cfg.get("user_template", "{hop_0}")
        context_vars = {f"hop_{i}": collected[i] for i in range(len(collected))}
        try:
            user_content = user_tmpl.format(**context_vars)
        except (KeyError, IndexError):
            user_content = collected[-1]  # same fallback as the streaming chain

        hop_body = {
            **body,
            "model": hop_model,
            "stream": True,  # stream internally — event-driven, no read timeout
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "tools": None,
            "tool_choice": None,
        }
        hop_body = {k: v for k, v in hop_body.items() if v is not None}
        hop_url, hop_body = resolve_hop_target(workspace_id, hop_model, backend.chat_url, hop_body)

        hop_parts: list[str] = []
        try:
            async with _http_client.stream("POST", hop_url, json=hop_body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    try:
                        d = _json.loads(line[6:])
                        c = d["choices"][0]["delta"].get("content") or ""
                        if c:
                            hop_parts.append(c)
                    except Exception:
                        pass
            hop_text = "".join(hop_parts)
        except Exception as exc:
            logger.warning(
                "Non-streaming chain hop failed for workspace=%s model=%s: %s(%s)",
                workspace_id,
                hop_model,
                type(exc).__name__,
                exc,
            )
            hop_text = ""

        collected.append(hop_text)
        if hop_text:
            sep = f"\n\n---\n\n{label}\n\n" if label else "\n\n---\n\n"
            combined_parts.append(sep + hop_text)

    full_content = "".join(combined_parts)
    primary_data["choices"][0]["message"]["content"] = full_content
    _record_usage(
        model=primary_model,
        workspace=workspace_id,
        data=primary_data,
        elapsed_seconds=time.monotonic() - start_time,
        **usage_metric_kwargs(primary_data),
    )
    return JSONResponse(
        content=primary_data,
        headers={"x-portal-route": f"{workspace_id};{backend.id};{primary_model}"},
    )


def _apply_non_stream_response(
    data: dict[str, Any],
    backend: Any,
    workspace_id: str,
    target_model: str,
    start_time: float,
    *,
    successful_creation: bool = False,
    model_elapsed_s: float | None = None,
) -> JSONResponse:
    """Normalise + record + wrap a completed non-streaming response dict.

    Called from both the normal path and the timeout-retry path in
    ``_try_non_streaming`` to avoid duplicating ~60 lines of post-processing.
    Pure sync — no awaits.
    """
    if not successful_creation:
        for choice in data.get("choices") or []:
            msg = choice.get("message") or {}
            if isinstance(msg.get("content"), str):
                msg["content"] = strip_unbacked_download_lines(msg["content"])

    try:
        from portal.platform.inference.router.thinking import (
            NO_ANSWER_MESSAGE,
            normalize_think_message,
        )

        for choice in data.get("choices") or []:
            msg = choice.get("message") or {}
            reasoning_only = normalize_think_message(
                msg, workspace_id=workspace_id, backend_id=backend.id
            )
            empty_answer = not str(msg.get("content") or "").strip()
            if (reasoning_only or empty_answer) and not msg.get("tool_calls"):
                # Keep a concise, non-verdict failure visible to ordinary
                # clients. The finish reason gives machine callers a stable
                # way to reject this response without parsing the warning.
                msg["content"] = NO_ANSWER_MESSAGE
                choice["finish_reason"] = (
                    "length"
                    if reasoning_only or choice.get("finish_reason") == "length"
                    else "stop"
                )

    except Exception:
        pass  # Never let normalisation break a valid response

    _elapsed = time.monotonic() - start_time
    _model_total_s = (
        max(0.0, model_elapsed_s)
        if model_elapsed_s is not None
        else max(0.0, _elapsed - (current_portal_timings().get("tool_s") or 0.0))
    )
    _record_usage(
        model=target_model,
        workspace=workspace_id,
        data=data,
        elapsed_seconds=_elapsed,
        **usage_metric_kwargs(data, {"total_s": _model_total_s}),
    )
    data["portal_timings"] = add_model_turn(
        data,
        measured={"total_s": _model_total_s},
    )
    trace_note(portal_timings=data["portal_timings"])
    if "model" not in data or not data["model"]:
        data["model"] = target_model
    if notice := take_truncation_notice():
        for choice in data.get("choices") or []:
            msg = choice.get("message") or {}
            if msg.get("content") is not None and not msg.get("tool_calls"):
                msg["content"] = f"{notice}\n\n{msg['content']}"
    logger.info(
        "Backend %s succeeded for workspace=%s model=%s",
        backend.id,
        workspace_id,
        target_model,
    )
    return JSONResponse(
        content=data,
        headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
    )


def _recover_or_withhold_markup(
    data: dict[str, Any], tools: list[dict[str, Any]] | None, model: str, workspace_id: str
) -> None:
    """Turn a tool call the model wrote as text into a real ``tool_calls`` entry, or withhold it.

    A reply that carries call markup but no offered tool (a synthesis turn runs with none)
    is call syntax, never an answer: it is cut from the content, not delivered."""
    for choice in data.get("choices") or []:
        msg = choice.get("message") or {}
        if msg.get("tool_calls"):
            continue
        text, salvaged = salvage_text_tool_calls(msg.get("content") or "", tools)
        if salvaged:
            logger.info(
                "NON-STREAM: recovered %d tool call(s) written as text (model=%s)",
                len(salvaged),
                model,
            )
            _tool_calls_recovered.labels(workspace=workspace_id).inc(len(salvaged))
            msg.update(content=text, tool_calls=salvaged)
            choice["finish_reason"] = "tool_calls"
        elif (
            msg.get("content") and (clean := drop_unparsed_markup(msg["content"])) != msg["content"]
        ):
            logger.warning("NON-STREAM: unparseable tool-call markup withheld (model=%s)", model)
            _record_error(workspace_id, "unparsed_tool_call")
            msg["content"] = clean


def _collect_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tool call across a response's choices."""
    return [
        tc
        for c in data.get("choices") or []
        for tc in (c.get("message") or {}).get("tool_calls") or []
    ]


def _all_offered(tool_calls: list[dict[str, Any]], offered: Collection[str]) -> bool:
    """True when every call names a tool this request offered (else it is not dispatchable)."""
    return all((tc.get("function") or {}).get("name", "").strip() in offered for tc in tool_calls)


def _assistant_turn(
    data: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    thinking_allowed: bool,
    creation_succeeded: bool,
) -> dict[str, Any]:
    """The model's tool-calling turn as history for the next hop: visible prose and, when
    thinking is on, its reasoning, so an interleaved-thinking model keeps its plan.
    `reasoning_content` is canonical; OllamaNativeTransport maps it to /api/chat `thinking`."""
    content: list[str] = []
    reasoning: list[str] = []
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        text = message.get("content")
        if isinstance(text, str):
            visible = strip_think(text)
            if not creation_succeeded:
                visible = strip_unbacked_download_lines(visible)
            if visible:
                content.append(visible)
        if thinking_allowed and (r := _reasoning_text(message)):
            reasoning.append(r)
    turn: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content) or None,
        "tool_calls": tool_calls,
    }
    if reasoning:
        turn["reasoning_content"] = "".join(reasoning)
    return turn


def _record_intermediate_model(
    data: dict[str, Any], model: str, workspace_id: str, started: float
) -> None:
    """Count tool/grounding hops as model time, excluding discarded prose."""
    timing_data = dict(data)
    if isinstance(data.get("choices"), list):
        timing_data["choices"] = []
        for choice in data["choices"]:
            if isinstance(choice, dict):
                copied = dict(choice)
                copied["message"] = {**(choice.get("message") or {}), "content": ""}
                timing_data["choices"].append(copied)
    if isinstance(data.get("message"), dict):
        timing_data["message"] = {**data["message"], "content": ""}
    timing_data["portal_timings"] = {
        **(data.get("portal_timings") or {}),
        "answer_tokens": 0,
        "answer_s": 0,
    }
    _record_usage(
        model=data.get("model") or model,
        workspace=workspace_id,
        data=timing_data,
        **usage_metric_kwargs(timing_data),
    )
    add_model_turn(timing_data, measured={"total_s": max(0.0, time.monotonic() - started)})
    trace_note(portal_timings=current_portal_timings())


def _strip_tool_calls(data: dict[str, Any]) -> list[str]:
    dropped: list[str] = []
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        for call in message.pop("tool_calls", None) or []:
            dropped.append(str((call.get("function") or {}).get("name", "?")))
        if choice.get("finish_reason") == "tool_calls":
            choice["finish_reason"] = "stop"
    return dropped


async def _final_toolless_answer(
    client: Any,
    url: str,
    timeout: httpx.Timeout,
    req_body: dict[str, Any],
    messages: list[dict[str, Any]],
    data: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    hops: int,
    thinking_allowed: bool,
    creation_succeeded: bool,
    workspace_id: str,
    target_model: str,
    model_started: float,
) -> tuple[dict[str, Any], float]:
    _record_intermediate_model(data, target_model, workspace_id, model_started)
    dropped = _strip_tool_calls(data)
    logger.info(
        "Non-stream tool loop: workspace=%s model=%s dropping undispatchable tool call(s): %s",
        workspace_id,
        target_model,
        ", ".join(dropped),
    )
    visible = [
        str((c.get("message") or {}).get("content") or "") for c in data.get("choices") or []
    ]
    if any(text.strip() for text in visible):
        return data, time.monotonic()
    final_messages = list(messages)
    if hops == 0:
        final_messages.append(
            _assistant_turn(data, tool_calls, thinking_allowed, creation_succeeded)
        )
    final_messages.append(FINAL_ANSWER_REQUEST)
    final_body = {**req_body, "messages": final_messages, "tools": None, "tool_choice": None}
    started = time.monotonic()
    final_resp = await client.post(url, json=final_body, timeout=timeout)
    _raise_for_backend_status(final_resp)
    data = _completion_body(final_resp, workspace_id)
    _recover_or_withhold_markup(data, None, req_body.get("model", ""), workspace_id)
    late = _collect_tool_calls(data)
    if late:
        late_names = _strip_tool_calls(data)
        logger.info(
            "Non-stream tool loop: workspace=%s model=%s final toolless turn still called: %s — "
            "returning the no-answer notice",
            workspace_id,
            target_model,
            ", ".join(late_names),
        )
        for choice in data.get("choices") or []:
            message = choice.get("message") or {}
            if not str(message.get("content") or "").strip():
                message["content"] = NO_ANSWER_MESSAGE
    return data, started


async def _try_non_streaming(
    backend: Any,
    body: dict[str, Any],
    workspace_id: str,
    start_time: float,
    *,
    enforce_hint: bool = True,
    persona: str = "",
    tried: dict[tuple[str, str], str] | None = None,
    max_hops: int = 1,
) -> JSONResponse | None:
    """Attempt one non-streaming completion against ``backend``; ``None`` on failure.

    This is the **fallback engine**. It runs in two distinct
    callers:

    1. ``handlers._dispatch_non_streaming`` — iterates candidates until
       one succeeds.
    2. ``streaming._stream_with_fallback`` — when a stream fails before
       any output reached the client, the remaining candidates are tried.

    Every failure path returns ``None`` so the caller's loop can try the
    next candidate — except a request the backend rejects as malformed
    (``BackendRequestError``, HTTP 400/413/422), which every candidate would
    reject alike and which the caller surfaces instead of cascading, and an
    oMLX prefill refusal that survives the free/retry, which the caller may
    still cascade past to a candidate with a different memory profile.
    ``tried`` (shared across one request's attempts) maps each
    ``(chat_url, model)`` pair already attempted to its failure reason:
    several backend groups front the same engine, and resending an identical
    request to it is a repeat, not a fallback. The reasons let the caller
    tell the client why every attempt failed.

    Major steps in order:

    1. **Pick target model** from ``model_hint``.
       Return ``None`` if ``enforce_hint=True`` and the hint isn't
       satisfied.
    2. **Inject Ollama options** via ``_inject_ollama_options``.
    3. **Inject tool schemas** when the persona has effective tools
       AND ``_model_supports_tools(target_model)``.
    4. **POST**, parse JSON.
    5. **Non-streaming tool loop** (single hop): if the model
       returned ``tool_calls``, dispatch them via
       ``_dispatch_tool_call``, append assistant turn + tool
       results, call the model once more for synthesis with
       ``tools: None``, ``tool_choice: None``.
        **Single hop, not unbounded** — see "asymmetry" below.
     6. **Reasoning normalisation**: keep reasoning in its separate field,
       filter inline protocol wrappers, and classify a reasoning-only result
       as an incomplete answer.
     7. **Record metrics** + **emit ``x-portal-route`` header** so
       callers and operators can see which workspace × backend ×
       model served.

    Asymmetry with the streaming tool loop: the streaming variant
    in ``_stream_with_tool_loop_impl`` loops up to ``MAX_TOOL_HOPS``
    times; by default this does exactly one synthesis turn (``max_hops=1``;
    a stream's failover passes ``MAX_TOOL_HOPS``; undispatched end-of-turn
    calls are stripped and answered by one final toolless turn). Reason: Open WebUI
    sends **two** requests per user message when tools are enabled
    — one streaming (for the user-visible response) and one
    non-streaming (for its DB-of-record commit). The streaming
    side handles multi-hop conversations; the non-streaming commit
    just needs to capture the final answer.

    Args:
        backend: A ``Backend`` instance from the registry.
        body: The user's full request body. Not mutated.
        workspace_id: For metric labels and config lookup.
        start_time: ``time.monotonic()`` of the original request;
            used for elapsed-time metrics.
        enforce_hint: When ``True``, return ``None`` if the
            backend doesn't carry the hinted model. The caller
            sets this to ``False`` on the last candidate so the
            last shot accepts any model as fallback.
        persona: Persona slug; resolves to ``_PERSONA_MAP`` entry
            for tool authorization. Empty string falls back to
            the workspace-level tool list.

    Returns:
        ``JSONResponse`` on success (200 from the backend, well-formed
        JSON, normalisations applied), ``None`` on any failure mode
        the caller should treat as "try next candidate".
    """
    if _http_client is None:
        return None
    ws_cfg = WORKSPACES.get(workspace_id, {})
    model_hint = ws_cfg.get("model_hint", "")

    # Pick target model from the workspace's model_hint, translating through
    # the backend's aliases (e.g. GGUF hint -> oMLX native id) when the hint
    # isn't served under its literal name.
    _resolved_hint = backend.resolve_model(model_hint) if model_hint else None
    if model_hint and _resolved_hint is not None:
        target_model = _resolved_hint
    elif model_hint and enforce_hint:
        logger.debug(
            "Backend %s lacks hinted model %s for workspace=%s — skipping",
            backend.id,
            model_hint,
            workspace_id,
        )
        return None
    else:
        if not backend.models:
            logger.warning(
                "Backend %s has empty models list — cannot resolve fallback. Skipping.",
                backend.id,
            )
            return None
        if model_hint and tried:
            # The hinted model was reached and failed (error or timeout).
            # Substituting an unrelated model loads it under the same memory
            # pressure and answers with a model the user didn't pick; the
            # any-model last resort is for a hint no healthy backend serves.
            logger.warning(
                "workspace=%s: hinted model %s failed on every backend that serves it — "
                "not substituting a different model",
                workspace_id,
                model_hint,
            )
            return None
        _literal_model = backend.resolve_model(workspace_id)
        target_model = _literal_model if _literal_model is not None else backend.models[0]
        if model_hint and target_model != model_hint:
            logger.warning(
                "workspace=%s: model_hint mismatch — wanted %s, serving %s via %s "
                "(all preferred backends exhausted; response may be from wrong model)",
                workspace_id,
                model_hint,
                target_model,
                backend.id,
            )
            _hint_fallback_total.labels(
                workspace=workspace_id,
                hinted=model_hint,
                served=target_model,
                path="non_streaming",
            ).inc()

    if tried is not None:
        _attempt = (backend.chat_url, target_model)
        if _attempt in tried:
            logger.debug(
                "Backend %s: %s on %s already attempted for this request — skipping",
                backend.id,
                target_model,
                backend.chat_url,
            )
            return None
        tried[_attempt] = ""

    if enforce_hint:
        logger.info(
            "Non-stream routing: workspace=%s backend=%s model=%s",
            workspace_id,
            backend.id,
            target_model,
        )

    # Per-request timeout: reasoning workspaces get extra runway since their
    # chain-of-thought generation routinely exceeds the default window.
    # registry.request_timeout is loaded from backends.yaml defaults.request_timeout.
    _req_timeout = getattr(registry, "request_timeout", 300.0)
    if ws_cfg.get("emits_reasoning"):
        _req_timeout = max(_req_timeout, 600.0)
    _timeout_obj = httpx.Timeout(_req_timeout, connect=5.0)

    req_body = {**body, "model": target_model, "stream": False}
    req_body.pop("portal_bite_max_hops", None)
    if backend.type == "ollama":
        req_body = _inject_ollama_options(req_body, workspace_id)
    elif backend.type == "omlx":
        req_body = _inject_omlx_options(req_body, workspace_id)
    _ns_thinking_allowed = _thinking_enabled(req_body)

    # Inject tool schemas — same logic as the streaming path. Required when
    # _try_non_streaming is used as a fallback after a streaming attempt fails
    # (empty streaming chunks indicate a streaming/non-streaming shape
    # mismatch), so the tool schemas aren't silently dropped in the fallback.
    _persona_data: PersonaSpec | dict[str, Any] = _PERSONA_MAP.get(persona, {}) if persona else {}
    _ns_tools = _resolve_persona_tools(_persona_data, workspace_id)
    # portal_client_tools_only / portal_no_tools / the non-tool-model strip:
    # same contract as streaming._build_streaming_request, so a request (or a
    # stream's non-streaming fallback) behaves the same in either mode.
    _ns_tools = apply_eval_scope(req_body, _ns_tools)
    _ns_tools, _ = apply_bite_tool_scope(req_body, _ns_tools)
    if req_body.pop("portal_client_tools_only", False):
        _ns_tools = []
    _supports_tools = _model_supports_tools(target_model)
    if req_body.pop("portal_no_tools", False) or not _supports_tools:
        req_body.pop("tools", None)
        req_body.pop("tool_choice", None)
        _ns_tools = []
    if _ns_tools and _supports_tools:
        from portal.platform.inference.tool_registry import tool_registry  # noqa: PLC0415

        _required_tool = None
        if req_body.get("tool_choice") in (None, "auto"):
            _required_tool = _select_explicit_required_tool(
                req_body.get("messages", []), set(_ns_tools)
            )
        # _ns_offer_tools narrows the SCHEMA the model sees; _ns_tools stays
        # the workspace's full whitelist for dispatch authorization below —
        # see the matching comment in streaming.py's _build_stream_request.
        _ns_offer_tools = [_required_tool] if _required_tool else _ns_tools
        if _required_tool:
            req_body["tool_choice"] = "required"
            logger.info(
                "Tool-call (non-stream): workspace=%s explicit side-effect intent "
                "selected required tool=%s",
                workspace_id,
                _required_tool,
            )
        await tool_registry.refresh()
        _tools_arr = tool_registry.get_openai_tools(_ns_offer_tools)
        # Merge client-injected tools with workspace tools — same logic as the
        # streaming path (handlers.py). Without this, clients (e.g. bench
        # blue/purple) that inject domain-specific tools via body["tools"]
        # had them silently discarded and replaced with only the workspace's
        # own registered tools (found 2026-07-05).
        _client_tools = [] if _required_tool else req_body.get("tools", [])
        if _tools_arr:
            if _client_tools:
                _seen_names = {t.get("function", {}).get("name") for t in _tools_arr}
                for _ct in _client_tools:
                    _ct_name = _ct.get("function", {}).get("name", "")
                    if _ct_name and _ct_name not in _seen_names:
                        _tools_arr.append(_ct)
                        _seen_names.add(_ct_name)
            req_body["tools"] = _tools_arr
            req_body["tool_choice"] = (
                req_body.get("tool_choice")
                or _resolve_persona_tool_choice(_persona_data)
                or WORKSPACES.get(workspace_id, {}).get("tool_choice")
                or "auto"
            )
            logger.info(
                "Tool-call (non-stream): workspace=%s persona=%s model=%s exposed %d tools (merged)",
                workspace_id,
                persona or "(none)",
                target_model,
                len(_tools_arr),
            )

    _prefill_refusal: str | None = None
    _last_request_body: dict[str, Any] = req_body

    async def _run_request() -> JSONResponse | None:
        """POST → tool loop → normalise → return. None on any failure."""

        nonlocal _prefill_refusal, _last_request_body
        _prefill_refusal = None
        _last_request_body = req_body
        try:
            _req_tools = len(req_body.get("tools", []))
            _req_msgs = len(req_body.get("messages", []))
            _req_model = req_body.get("model", "?")
            logger.info(
                "NON-STREAM POST → %s | model=%s %d msgs, %d tools | timeout=%s",
                backend.chat_url,
                _req_model,
                _req_msgs,
                _req_tools,
                _timeout_obj,
            )
            # Log tool names so we can see what's exposed
            _tool_names = [
                t.get("function", {}).get("name", "?") for t in req_body.get("tools", [])
            ]
            logger.info("NON-STREAM tools: %s", _tool_names)
            trace_capture(backend_request=req_body)
            _model_started = time.monotonic()
            resp = await _http_client.post(backend.chat_url, json=req_body, timeout=_timeout_obj)
            _raise_for_backend_status(resp)
            data = _completion_body(resp, workspace_id)
            # P5-OMLX-QWEN3CODER-TOOLTEXT-001: a call the engine's parser
            # missed arrives as content; recover it before the tool loop.
            _recover_or_withhold_markup(
                data, req_body.get("tools"), req_body.get("model", ""), workspace_id
            )
            _resp_tc: list[dict[str, Any]] = []
            for _c in data.get("choices") or []:
                _resp_tc.extend((_c.get("message") or {}).get("tool_calls") or [])
            _resp_content = ""
            for _c in data.get("choices") or []:
                # content is null on a tool-call reply from OpenAI-shaped
                # engines; slicing None failed every such response.
                _resp_content = ((_c.get("message") or {}).get("content") or "")[:200]
            logger.info(
                "NON-STREAM ← %s | %d tool_calls, content=%r",
                backend.chat_url,
                len(_resp_tc),
                _resp_content[:100],
            )

            # Non-streaming tool loop: if the model returned tool_calls, dispatch them
            # and call the model once more for synthesis. This handles OWUI's second
            # non-streaming request (which it always sends when workspace tools are enabled)
            # so that the committed DB response contains the recalled content, not a stub.
            _ns_tool_calls: list[dict[str, Any]] = []
            for _c in data.get("choices") or []:
                _ns_tool_calls.extend((_c.get("message") or {}).get("tool_calls") or [])

            # Only auto-dispatch when every requested call belongs to the
            # workspace's own whitelist. A client-injected tool (e.g. bench
            # blue/purple's synthetic query_windows_events) has no real MCP
            # registry entry — _dispatch_tool_call correctly rejects it, but
            # that consumes the tool_calls and forces a synthesis reply
            # instead of returning them to the caller to handle itself
            # (found 2026-07-05: auto-blueteam's own tools mixed with
            # client-injected ones caused every client tool call to be
            # silently rejected and turned into a prose "unavailable" answer).
            _ns_dispatchable = bool(_ns_tools) and all(
                (tc.get("function") or {}).get("name", "").strip() in _ns_tools
                for tc in _ns_tool_calls
            )
            _ns_messages = list(req_body.get("messages") or [])
            _ns_hops = 0
            _ns_guard = ToolRepeatGuard()
            # no file tools offered: nothing to filter
            _ns_creation_succeeded = not offers_file_creation(req_body.get("tools"))
            if (
                WORKSPACES.get(workspace_id.split("::")[0], {}).get("require_tool_before_answer")
                and req_body.get("tools")
                and not _ns_tool_calls
                and any(
                    (_c.get("message") or {}).get("content") for _c in data.get("choices") or []
                )
            ):
                # Answered with no tool call on a workspace that requires one: ask once for a
                # grounded answer (tools still offered); an answer that is still ungrounded is
                # delivered with a notice.
                _answer_without_tool_retried.labels(workspace=workspace_id).inc()
                logger.warning(
                    "Non-stream: workspace=%s answered without a tool call; asking once for a "
                    "grounded answer",
                    workspace_id,
                )
                _ns_messages = [*_ns_messages, GROUNDING_REQUEST]
                _ns_guard.grounding_retried = True
                _record_intermediate_model(data, target_model, workspace_id, _model_started)
                _model_started = time.monotonic()
                _last_request_body = {**req_body, "messages": _ns_messages}
                _ns_retry = await _http_client.post(
                    backend.chat_url,
                    json=_last_request_body,
                    timeout=_timeout_obj,
                )
                _raise_for_backend_status(_ns_retry)
                data = _completion_body(_ns_retry, workspace_id)
                _recover_or_withhold_markup(
                    data, req_body.get("tools"), req_body.get("model", ""), workspace_id
                )
                _ns_tool_calls = _collect_tool_calls(data)
                _ns_dispatchable = bool(_ns_tools) and _all_offered(_ns_tool_calls, _ns_tools)
            while _ns_tool_calls and _ns_dispatchable:
                _record_intermediate_model(data, target_model, workspace_id, _model_started)
                _ns_hops += 1
                _ns_repeats = [_ns_guard.seen(tc) for tc in _ns_tool_calls]
                # In emitted order, one at a time: dependent calls must see each other land.
                _ns_fresh = iter(
                    [
                        await _dispatch_tool_call(
                            tc, set(_ns_tools), workspace_id, persona, f"ns-{int(time.time())}"
                        )
                        for tc, rep in zip(_ns_tool_calls, _ns_repeats, strict=True)
                        if not rep
                    ]
                )
                _ns_dispatch = []
                for tc, rep in zip(_ns_tool_calls, _ns_repeats, strict=True):
                    if rep:
                        _ns_dispatch.append(_ns_guard.repeat_result(tc))
                        _tool_repeat_suppressed.labels(workspace=workspace_id).inc()
                        logger.warning(
                            "Non-stream tool loop: workspace=%s tool=%s repeated with the same "
                            "arguments; answered from the earlier result",
                            workspace_id,
                            tc["function"]["name"],
                        )
                    else:
                        _ns_result = next(_ns_fresh)
                        _ns_guard.remember(tc, _ns_result)
                        _ns_dispatch.append(_ns_result)
                _ns_creation_succeeded = _ns_creation_succeeded or any(
                    successful_file_creation(result) for result in _ns_dispatch
                )
                _ns_assistant_msg = _assistant_turn(
                    data, _ns_tool_calls, _ns_thinking_allowed, _ns_creation_succeeded
                )
                _ns_messages = _ns_messages + [_ns_assistant_msg] + list(_ns_dispatch)
                # Every turn but the last keeps the tools, so a turn that needs a second
                # lookup gets it; the last is the synthesis, run with none.
                _ns_last = _ns_hops >= max_hops or _ns_guard.force_synthesis
                if _ns_guard.force_synthesis:
                    _ns_messages = [*_ns_messages, FINAL_ANSWER_REQUEST]
                _synth_body = {
                    **req_body,
                    "messages": _ns_messages,
                    "tools": None if _ns_last else req_body.get("tools"),
                    "tool_choice": None if _ns_last else req_body.get("tool_choice"),
                }
                _last_request_body = _synth_body
                _model_started = time.monotonic()
                _synth_resp = await _http_client.post(
                    backend.chat_url, json=_synth_body, timeout=_timeout_obj
                )
                _raise_for_backend_status(_synth_resp)
                data = _completion_body(_synth_resp, workspace_id)
                _recover_or_withhold_markup(
                    data, _synth_body.get("tools"), req_body.get("model", ""), workspace_id
                )
                logger.info(
                    "Non-stream tool loop: workspace=%s hop %d dispatched %d tool(s)",
                    workspace_id,
                    _ns_hops,
                    len(_ns_tool_calls),
                )
                _ns_tool_calls = _collect_tool_calls(data)
                _ns_dispatchable = (
                    not _ns_last
                    and bool(_ns_tool_calls)
                    and _all_offered(_ns_tool_calls, _ns_tools)
                )

            # A call to a tool the CLIENT offered (in the request but not pipeline-owned) is
            # the caller's to run: pass it through, as before (harness direct modes, API clients).
            _client_owned = {
                (t.get("function") or {}).get("name") for t in body.get("tools") or []
            } - set(_ns_tools or ())
            if _ns_tool_calls and not any(
                (tc.get("function") or {}).get("name") in _client_owned for tc in _ns_tool_calls
            ):
                data, _model_started = await _final_toolless_answer(
                    _http_client,
                    backend.chat_url,
                    _timeout_obj,
                    req_body,
                    _ns_messages,
                    data,
                    _ns_tool_calls,
                    _ns_hops,
                    _ns_thinking_allowed,
                    _ns_creation_succeeded,
                    workspace_id,
                    target_model,
                    _model_started,
                )

            if _ns_guard.grounding_retried and _ns_guard.executed == 0:
                for _c in data.get("choices") or []:
                    _m = _c.get("message") or {}
                    _m["content"] = (_m.get("content") or "") + UNGROUNDED_NOTICE

            # Salient memory write-back (fire-and-forget; once per OWUI turn).
            # Persists only salient USER statements; no-op unless the workspace
            # sets memory_writeback. Never blocks or fails the response.
            from portal.platform.inference.router.context_inject import schedule_writeback

            schedule_writeback(workspace_id, body.get("messages", []), get_correlation_id())

            return _apply_non_stream_response(
                data,
                backend,
                workspace_id,
                target_model,
                start_time,
                successful_creation=_ns_creation_succeeded,
                model_elapsed_s=max(0.0, time.monotonic() - _model_started),
            )
        except (httpx.TimeoutException, BackendRequestError):
            raise  # timeout: outer handler checks /api/ps; 4xx: caller surfaces it
        except Exception as exc:
            # The cause used to be swallowed: a cascade to the next candidate
            # left only "Backend X failed" in the log.
            detail = (
                backend_error_detail(exc.response.content)
                if isinstance(exc, httpx.HTTPStatusError)
                else str(exc)
            )
            _prefill_refusal = _omlx_prefill_refusal_detail(backend, exc)
            if tried is not None:
                tried[(backend.chat_url, target_model)] = f"{target_model}: {detail[:300]}"
            logger.warning(
                "Backend %s request failed for workspace=%s model=%s: %s: %s",
                backend.id,
                workspace_id,
                target_model,
                type(exc).__name__,
                detail[:300],
            )
            return None

    try:
        from portal.platform.inference.router.backend_introspect import make_room_for_omlx

        await make_room_for_omlx(backend, body)
        result = await _run_request()
        if (
            result is None
            and getattr(backend, "type", "") == "omlx"
            and _is_capacity_error((tried or {}).get((backend.chat_url, target_model), ""))
        ):
            # oMLX rejected the prompt for memory held by idle Ollama models it
            # cannot reclaim: free them and retry oMLX once before cascading.
            from portal.platform.inference.router.backend_introspect import free_ollama_for_omlx

            freed = await free_ollama_for_omlx()
            if freed:
                logger.info(
                    "oMLX capacity rejection for workspace=%s; freed Ollama %s, retrying oMLX",
                    workspace_id,
                    freed,
                )
                result = await _run_request()
        if result is not None:
            return result
        _raise_prefill_capacity_error(_prefill_refusal, _last_request_body)
        # Non-timeout failure (HTTP error, JSON parse, etc.) — cascade immediately.
        logger.warning(
            "Backend %s failed for workspace=%s — trying next candidate",
            backend.id,
            workspace_id,
        )
        return None
    except httpx.TimeoutException:
        # Before cascading, check whether the engine is still running the model.
        # A timeout on a reasoning model mid-generation is not a backend failure.
        logger.warning(
            "Backend %s timed out for workspace=%s (%.0fs) — probing engine state",
            backend.id,
            workspace_id,
            _req_timeout,
        )
        from portal.platform.inference.router.backend_introspect import (
            model_still_running as _msr,
        )

        _model_still_running = await _msr(backend.chat_url, timeout_s=60.0)

        if _model_still_running:
            logger.warning(
                "Backend %s: engine reports model still running — retrying once with %.0fs timeout",
                backend.id,
                _req_timeout,
            )
            try:
                result = await _run_request()
            except httpx.TimeoutException:
                result = None  # a second timeout must cascade, not escape
            if result is not None:
                return result
        if tried is not None:
            tried[(backend.chat_url, target_model)] = (
                f"{target_model}: timed out after {_req_timeout:.0f}s"
            )
        if _model_still_running:
            logger.warning(
                "Backend %s retry also failed for workspace=%s — cascading",
                backend.id,
                workspace_id,
            )
        else:
            logger.warning(
                "Backend %s: engine unreachable or no model running — cascading to next candidate",
                backend.id,
            )
        return None
