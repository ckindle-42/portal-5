"""Non-streaming request dispatch.

Mirror of router/streaming.py for non-streaming completion requests.
Both modules are called from the chat_completions handler; the
streaming/non-streaming branch is decided by the request body's
``stream`` flag.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi.responses import JSONResponse

from portal_pipeline.router.power import _record_usage
from portal_pipeline.router.tools import _dispatch_tool_call
from portal_pipeline.router.validation import _inject_ollama_options, _model_supports_tools
from portal_pipeline.router.workspaces import _PERSONA_MAP, WORKSPACES, _resolve_persona_tools

# Set by lifespan — same push pattern as streaming.py
_http_client: Any = None
registry: Any = None

logger = logging.getLogger(__name__)


async def _run_non_streaming_chain(
    primary_text: str,
    chain: list[dict],
    backend: Any,
    body: dict,
    workspace_id: str,
    start_time: float,
    primary_data: dict,
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
        user_content = user_tmpl.format(**context_vars)

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

        hop_parts: list[str] = []
        try:
            async with _http_client.stream(  # type: ignore[union-attr]
                "POST", backend.chat_url, json=hop_body
            ) as resp:
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
    )
    return JSONResponse(
        content=primary_data,
        headers={"x-portal-route": f"{workspace_id};{backend.id};{primary_model}"},
    )


def _apply_non_stream_response(
    data: dict,
    backend: Any,
    workspace_id: str,
    target_model: str,
    start_time: float,
) -> JSONResponse:
    """Normalise + record + wrap a completed non-streaming response dict.

    Called from both the normal path and the timeout-retry path in
    ``_try_non_streaming`` to avoid duplicating ~60 lines of post-processing.
    Pure sync — no awaits.
    """
    try:
        from portal_pipeline.router.thinking import normalize_think_message

        for choice in data.get("choices") or []:
            msg = choice.get("message") or {}
            normalize_think_message(msg, workspace_id=workspace_id, backend_id=backend.id)

    except Exception:
        pass  # Never let normalisation break a valid response

    _record_usage(
        model=target_model,
        workspace=workspace_id,
        data=data,
        elapsed_seconds=time.monotonic() - start_time,
    )
    if "model" not in data or not data["model"]:
        data["model"] = target_model
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


async def _try_non_streaming(
    backend: Any,
    body: dict,
    workspace_id: str,
    start_time: float,
    *,
    enforce_hint: bool = True,
    persona: str = "",
) -> JSONResponse | None:
    """Attempt one non-streaming completion against ``backend``; ``None`` on failure.

    This is the **fallback engine**. It runs in two distinct
    callers:

    1. The non-streaming branch of ``chat_completions`` (line 2572)
       — iterates candidates until one succeeds.
    2. ``_stream_or_fallback`` (line 2834) — when a streaming
       attempt yields an error chunk, the same backend is retried
       non-streaming, then remaining candidates are tried.

    **Never raises.** Every failure path returns ``None`` so the
    caller's loop can try the next candidate. Raising would
    short-circuit the fallback chain.

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
     6. **Reasoning normalisation**: promote
       ``message.reasoning`` → ``message.content`` when content is
       empty (DeepSeek-R1 CoT exhaustion).
    8. **Record metrics** + **emit ``x-portal-route`` header** so
       callers and operators can see which workspace × backend ×
       model served.

    Asymmetry with the streaming tool loop: the streaming variant
    in ``_stream_with_tool_loop_impl`` loops up to ``MAX_TOOL_HOPS``
    times; this does exactly one synthesis turn. Reason: Open WebUI
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

    # Pick target model from Ollama hint
    if model_hint and model_hint in backend.models:
        target_model = model_hint
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
        target_model = backend.models[0]
        if model_hint and target_model != model_hint:
            logger.warning(
                "workspace=%s: model_hint mismatch — wanted %s, serving %s via %s "
                "(all preferred backends exhausted; response may be from wrong model)",
                workspace_id,
                model_hint,
                target_model,
                backend.id,
            )

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
    if backend.type == "ollama":
        req_body = _inject_ollama_options(req_body, workspace_id)

    # Inject tool schemas — same logic as the streaming path. Required when
    # _try_non_streaming is used as a fallback after a streaming attempt fails
    # (empty streaming chunks indicate a streaming/non-streaming shape
    # mismatch), so the tool schemas aren't silently dropped in the fallback.
    _persona_data = _PERSONA_MAP.get(persona, {}) if persona else {}
    _ns_tools = _resolve_persona_tools(_persona_data, workspace_id)
    if _ns_tools and _model_supports_tools(target_model):
        from portal_pipeline.tool_registry import tool_registry  # noqa: PLC0415

        await tool_registry.refresh()
        _tools_arr = tool_registry.get_openai_tools(_ns_tools)
        # Merge client-injected tools with workspace tools — same logic as the
        # streaming path (handlers.py). Without this, clients (e.g. bench
        # blue/purple) that inject domain-specific tools via body["tools"]
        # had them silently discarded and replaced with only the workspace's
        # own registered tools (found 2026-07-05).
        _client_tools = body.get("tools", [])
        if _tools_arr:
            if _client_tools:
                _seen_names = {t.get("function", {}).get("name") for t in _tools_arr}
                for _ct in _client_tools:
                    _ct_name = _ct.get("function", {}).get("name", "")
                    if _ct_name and _ct_name not in _seen_names:
                        _tools_arr.append(_ct)
                        _seen_names.add(_ct_name)
            req_body["tools"] = _tools_arr
            req_body.setdefault("tool_choice", "auto")
            logger.info(
                "Tool-call (non-stream): workspace=%s persona=%s model=%s exposed %d tools (merged)",
                workspace_id,
                persona or "(none)",
                target_model,
                len(_tools_arr),
            )

    async def _run_request() -> JSONResponse | None:
        """POST → tool loop → normalise → return. None on any failure."""
        try:
            resp = await _http_client.post(  # type: ignore[union-attr]
                backend.chat_url, json=req_body, timeout=_timeout_obj
            )
            resp.raise_for_status()
            data = resp.json()

            # Non-streaming tool loop: if the model returned tool_calls, dispatch them
            # and call the model once more for synthesis. This handles OWUI's second
            # non-streaming request (which it always sends when workspace tools are enabled)
            # so that the committed DB response contains the recalled content, not a stub.
            _ns_tool_calls: list[dict] = []
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
            if _ns_tool_calls and _ns_dispatchable:
                _ns_dispatch = await asyncio.gather(
                    *[
                        _dispatch_tool_call(
                            tc, set(_ns_tools), workspace_id, persona, f"ns-{int(time.time())}"
                        )
                        for tc in _ns_tool_calls
                    ]
                )
                _synth_messages = (
                    (req_body.get("messages") or [])
                    + [{"role": "assistant", "content": None, "tool_calls": _ns_tool_calls}]
                    + list(_ns_dispatch)
                )
                _synth_body = {
                    **req_body,
                    "messages": _synth_messages,
                    "tools": None,
                    "tool_choice": None,
                }
                _synth_resp = await _http_client.post(  # type: ignore[union-attr]
                    backend.chat_url, json=_synth_body, timeout=_timeout_obj
                )
                _synth_resp.raise_for_status()
                data = _synth_resp.json()
                logger.info(
                    "Non-stream tool loop: workspace=%s dispatched %d tool(s), synthesis complete",
                    workspace_id,
                    len(_ns_tool_calls),
                )

            return _apply_non_stream_response(data, backend, workspace_id, target_model, start_time)
        except httpx.TimeoutException:
            raise  # propagate so outer handler can check /api/ps
        except Exception:
            return None

    try:
        result = await _run_request()
        if result is not None:
            return result
        # Non-timeout failure (HTTP error, JSON parse, etc.) — cascade immediately.
        logger.warning(
            "Backend %s failed for workspace=%s — trying next candidate",
            backend.id,
            workspace_id,
        )
        return None
    except httpx.TimeoutException:
        # Before cascading, check whether the model is still running in Ollama.
        # A timeout on a reasoning model mid-generation is not a backend failure.
        _ollama_base = backend.chat_url.split("/v1/")[0]
        logger.warning(
            "Backend %s timed out for workspace=%s (%.0fs) — checking /api/ps",
            backend.id,
            workspace_id,
            _req_timeout,
        )
        _model_still_running = False
        try:
            from portal_pipeline.router.monitor import wait_for_model_loaded as _wfml

            _model_still_running = await _wfml(timeout_s=60.0, ollama_url=_ollama_base)
        except Exception:
            pass

        if _model_still_running:
            logger.warning(
                "Backend %s: model present in /api/ps — retrying once with %.0fs timeout",
                backend.id,
                _req_timeout,
            )
            result = await _run_request()
            if result is not None:
                return result
            logger.warning(
                "Backend %s retry also failed for workspace=%s — cascading",
                backend.id,
                workspace_id,
            )
        else:
            logger.warning(
                "Backend %s: model absent from /api/ps — cascading to next candidate",
                backend.id,
            )
        return None
