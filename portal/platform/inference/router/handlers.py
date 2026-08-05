"""Route handler function bodies — no decorators.

Extracted from router_pipe.py during M6-A finish. Each function
is a route handler body; the ``@app.<method>`` decorators live in
``router/app.py``.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import generate_latest

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import ollama_url
from portal.platform.inference.router.anthropic_compat import (
    anthropic_to_openai_body,
    openai_response_to_anthropic,
    openai_stream_to_anthropic_sse,
)
from portal.platform.inference.router.auth import _verify_admin_key, _verify_key
from portal.platform.inference.router.concurrency import (
    RequestSlot,
)
from portal.platform.inference.router.context_inject import (
    inject_recalled_memory,
    inject_retrieved_context,
)
from portal.platform.inference.router.correlation import get_correlation_id
from portal.platform.inference.router.council import (
    run_council_review,
    stream_council_review,
)
from portal.platform.inference.router.lifespan import (
    _startup_time,
)
from portal.platform.inference.router.metrics import (
    _REGISTRY,
    _record_response_time,
    _requests_total,
)
from portal.platform.inference.router.non_streaming import (
    _run_non_streaming_chain,
    _try_non_streaming,
)
from portal.platform.inference.router.preinject import (
    _inject_attached_files,
    _inject_system_prompt_append,
    _inject_temporal_context,
    _resolve_auto_routing,
    _resolve_model_override,
    _resolve_persona_workspace,
    _resolve_vision_fallback,
    _resolve_workspace_variant,
    _unpack_synthetic_workspace,
)
from portal.platform.inference.router.state import (
    _record_error,
    _record_persona,
    _req_count_by_model,
    _request_count,
)
from portal.platform.inference.router.streaming import (
    _build_streaming_request,
    _prioritize_hinted_backend,  # noqa: F401  (re-exported: tests import it from handlers)
    _select_stream_fn,
    _select_streaming_backend,
    _stream_with_fallback,
)
from portal.platform.inference.router.workspaces import (
    _PERSONA_MAP,
    WORKSPACES,
)

logger = logging.getLogger(__name__)

# Set by lifespan — pushed in at startup, not captured at import time.
registry: BackendRegistry | None = None
_notification_dispatcher: Any = None


# ── Module constants ──────────────────────────────────────────────────────────
try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"

_startup_time_val: float = time.time()
_mp_registry_cache: Any = None
_mp_registry_dir_cache: str | None = None


async def health() -> dict:
    """GET /health — fast unauthenticated liveness probe.

    Used by Open WebUI's "test connection" button, Docker healthchecks, and
    Kubernetes readiness probes. ``status`` is ``"ok"`` if at least one backend
    is healthy, else ``"degraded"`` — deliberately not 503, since the problem
    is upstream (Ollama down), not the pipeline.

    Raises:
        HTTPException: 503 only when the backend registry isn't initialised
            yet (lifespan startup race).
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = registry.list_healthy_backends()
    return {
        "status": "ok" if healthy else "degraded",
        "version": _PKG_VERSION,
        "backends_healthy": len(healthy),
        "backends_total": len(registry.list_backends()),
        "workspaces": len(WORKSPACES),
    }


async def health_all():
    """GET /health/all — aggregate diagnostic check across the full stack.

    Probes the pipeline, Ollama, and every MCP in ``tool_registry.MCP_SERVERS``
    in parallel with a per-probe 3s timeout via one shared
    ``httpx.AsyncClient``. Each value is the component's ``/health`` (or
    ``/api/tags`` for Ollama) JSON if 200, else a status dict.

    Returns:
        Dict keyed by component name.
    """
    from portal.platform.inference.tool_registry import MCP_SERVERS

    async def _probe(url: str, path: str) -> dict:
        try:
            r = await _health_client.get(f"{url}{path}")
            return (
                r.json() if r.status_code == 200 else {"status": "degraded", "code": r.status_code}
            )
        except Exception as e:
            return {"status": "down", "error": str(e)[:100]}

    async with httpx.AsyncClient(timeout=3) as _health_client:
        pipeline_result = {"pipeline": {"status": "ok"}}
        ollama_result = await _probe(
            ollama_url(),
            "/api/tags",
        )
        mcp_probes = {
            f"mcp_{server_id}": _probe(url, "/health") for server_id, url in MCP_SERVERS.items()
        }
        mcp_results_list = await asyncio.gather(*mcp_probes.values(), return_exceptions=True)
        mcp_results = dict(zip(mcp_probes.keys(), mcp_results_list, strict=True))

    return {**pipeline_result, "ollama": ollama_result, **mcp_results}


PORTAL5_ADMIN_KEY = os.environ.get("PORTAL5_ADMIN_KEY", os.environ.get("PIPELINE_API_KEY", ""))


async def admin_refresh_tools(authorization: str | None = Header(None)):
    """POST /admin/refresh-tools — force a tool-registry refresh.

    Operator escape hatch to pick up MCP changes without waiting for the next
    scheduled refresh (bypasses the 1h TTL via ``refresh(force=True)``).
    Requires the admin key (``PORTAL5_ADMIN_KEY``), not the regular API key.

    Returns:
        ``{"refreshed": True, "tools_registered": int, "names": [str, ...]}``.
    """
    _verify_admin_key(authorization)
    from portal.platform.inference.tool_registry import tool_registry

    n = await tool_registry.refresh(force=True)
    return {"refreshed": True, "tools_registered": n, "names": tool_registry.list_tool_names()}


async def test_notifications(authorization: str | None = Header(None)) -> dict:
    """POST /notifications/test — fire a test alert and summary; report status.

    Sanity-check for notification configuration: dispatches one AlertEvent
    (labeled as test) and one SummaryEvent with live data. Requires
    ``NOTIFICATIONS_ENABLED=true`` at process start, else 503. ``channels``
    reports env-var config status; the ``results`` field is authoritative for
    actual deliverability.

    Returns:
        ``{"status": "ok", "results": {...}}``.

    Raises:
        HTTPException: 401 on bad auth, 503 when notifications are disabled.
    """
    _verify_key(authorization)

    if _notification_dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="Notification dispatcher not initialized (NOTIFICATIONS_ENABLED=false?)",
        )

    from portal.platform.inference.notifications.events import AlertEvent, EventType, SummaryEvent

    results: dict[str, str] = {}

    # Fire a test alert
    alert = AlertEvent(
        type=EventType.BACKEND_DOWN,
        message="This is a test alert — Portal 5 notification test successful!",
        backend_id="test-backend",
    )
    try:
        await _notification_dispatcher.dispatch(alert)
        results["alert"] = "dispatched"
    except Exception as e:
        results["alert"] = f"error: {e}"

    # Fire a test summary (stats will be zeros/minimal for a test)
    summary = SummaryEvent(
        timestamp=datetime.now(UTC),
        report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
        total_requests=sum(_request_count.values()),
        requests_by_workspace=dict(_request_count),
        healthy_backends=len(registry.list_healthy_backends()) if registry else 0,
        total_backends=len(registry.list_backends()) if registry else 0,
        uptime_seconds=time.time() - _startup_time if _startup_time else 0.0,
        requests_by_model=dict(_req_count_by_model),
        avg_tokens_per_second=0.0,
        total_input_tokens=0,
        total_output_tokens=0,
        avg_response_time_ms=0.0,
    )
    try:
        await _notification_dispatcher.dispatch(summary)
        results["summary"] = "dispatched"
    except Exception as e:
        results["summary"] = f"error: {e}"

    # Report per-channel configuration status
    results["channels"] = {
        "slack": "configured" if os.environ.get("SLACK_ALERT_WEBHOOK_URL") else "not configured",
        "telegram": "configured"
        if os.environ.get("TELEGRAM_ALERT_BOT_TOKEN")
        else "not configured",
        "email": "configured" if os.environ.get("SMTP_HOST") else "not configured",
        "pushover": "configured"
        if (os.environ.get("PUSHOVER_API_TOKEN") and os.environ.get("PUSHOVER_USER_KEY"))
        else "not configured",
        "webhook": "configured" if os.environ.get("WEBHOOK_URL") else "not configured",
    }

    # Report scheduler settings
    results["scheduler"] = {
        "enabled": os.environ.get("ALERT_SUMMARY_ENABLED", "true").lower() in ("true", "1", "yes"),
        "hour": int(os.environ.get("ALERT_SUMMARY_HOUR", "9")),
        "timezone": os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC"),
    }

    return {"status": "ok", "results": results}


async def metrics() -> PlainTextResponse:
    """GET /metrics — Prometheus-compatible exposition.

    Intentionally unauthenticated — metrics expose counts/categories, not
    credentials or message content, and auth would burden Prometheus config.

    Combines hand-rolled gauges (backends healthy/total, uptime, workspaces)
    with the ``prometheus_client`` registry — the in-process ``_REGISTRY``
    (single-worker) or a cached ``MultiProcessCollector`` over the multiproc
    dir (``PROMETHEUS_MULTIPROC_DIR``). The collector reads disk files on each
    call, so caching the registry never serves stale data. ``os.makedirs`` is
    idempotent (prometheus_client doesn't create the parent dir).

    Returns:
        ``PlainTextResponse`` with Prometheus exposition format.

    Raises:
        HTTPException: 503 when the registry isn't yet initialised.
    """
    uptime = time.time() - _startup_time
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = len(registry.list_healthy_backends())
    total = len(registry.list_backends())

    lines = [
        "# HELP portal_backends_healthy Number of healthy backends",
        "# TYPE portal_backends_healthy gauge",
        f"portal_backends_healthy {healthy}",
        "# HELP portal_backends_total Total registered backends",
        "# TYPE portal_backends_total gauge",
        f"portal_backends_total {total}",
        "# HELP portal_uptime_seconds Process uptime in seconds",
        "# TYPE portal_uptime_seconds gauge",
        f"portal_uptime_seconds {uptime:.1f}",
        "# HELP portal_workspaces_total Number of configured workspaces",
        "# TYPE portal_workspaces_total gauge",
        f"portal_workspaces_total {len(WORKSPACES)}",
    ]
    # Hand-rolled gauges + prometheus_client registry; use the multiprocess
    # collector when PROMETHEUS_MULTIPROC_DIR is set. The registry is cached —
    # MultiProcessCollector reads from disk files on each call.
    global _mp_registry_cache, _mp_registry_dir_cache
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        # prometheus_client writes per-pid files but doesn't create the parent
        # dir — without this the first scrape after worker fork 500s.
        os.makedirs(mp_dir, exist_ok=True)
        if _mp_registry_cache is None or _mp_registry_dir_cache != mp_dir:
            from prometheus_client import CollectorRegistry as _CollectorRegistry
            from prometheus_client import multiprocess

            _mp_registry_cache = _CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
        prometheus_output = generate_latest(_mp_registry_cache).decode("utf-8")
    else:
        prometheus_output = generate_latest(_REGISTRY).decode("utf-8")
    return PlainTextResponse("\n".join(lines) + "\n" + prometheus_output)


async def list_models(authorization: str | None = Header(None)) -> dict:
    """GET /v1/models — OpenAI-compatible model catalogue.

    One entry per ``WORKSPACES`` key, plus one entry per IDE-curated persona
    (``ide_expose: true``). Portal 5 is Open WebUI's sole model source — OWUI
    sees workspaces as models, and the user's pick becomes the ``model`` field
    that ``chat_completions`` routes on. Persona entries keep this endpoint
    consistent with ``opencode.jsonc``'s curated picker without exposing the
    full persona catalogue.

    Per-entry fields: ``id`` (workspace key or persona slug), ``name``,
    ``category`` (derived from the id, overridable via ``category:``), ``tags``
    (default ``[category]``), ``tools`` (workspace default whitelist),
    ``is_benchmark`` (``bench-*`` workspaces only), ``is_persona``
    (IDE-curated personas).

    Authenticated because the response reveals operational config.

    Returns:
        ``{"object": "list", "data": [...]}`` — OpenAI-spec shape.

    Raises:
        HTTPException: 401 on bad auth.
    """
    _verify_key(authorization)
    ts = int(time.time())
    models = []
    for ws_id, ws_cfg in WORKSPACES.items():
        is_benchmark = ws_id.startswith("bench-")
        # Derive category from workspace ID: auto-coding → coding, bench-* → benchmark
        if is_benchmark:
            category = "benchmark"
        elif ws_id.startswith("auto-"):
            category = ws_id[5:]  # strip "auto-"
        else:
            category = ws_id
        category = ws_cfg.get("category", category)
        models.append(
            {
                "id": ws_id,
                "object": "model",
                "created": ts,
                "owned_by": "portal-5",
                "name": ws_cfg["name"],
                "description": ws_cfg.get("description", ""),
                "category": category,
                "tags": ws_cfg.get("tags", [category]),
                "tools": ws_cfg.get("tools", []),
                "is_benchmark": is_benchmark,
            }
        )
    for slug, persona in _PERSONA_MAP.items():
        if not getattr(persona, "ide_expose", False):
            continue
        models.append(
            {
                "id": slug,
                "object": "model",
                "created": ts,
                "owned_by": "portal-5",
                "name": persona.name,
                "description": f"Portal persona: {persona.name}",
                "category": persona.category,
                "tags": persona.tags or [persona.category],
                "tools": [],
                "is_benchmark": False,
                "is_persona": True,
            }
        )
    return {"object": "list", "data": models}


async def list_backends_endpoint(authorization: str | None = Header(None)) -> dict:
    """GET /v1/backends — diagnostic view of every registered backend.

    Returns ``{id, type, group, url, models, healthy, last_check}`` per
    backend. Not part of the OpenAI API surface; used by the UAT driver and
    operator tooling. Authenticated via ``_verify_key``.

    Returns:
        ``{"object": "list", "data": [...]}``.

    Raises:
        HTTPException: 401 on bad auth, 503 when the registry isn't
            yet initialised.
    """
    _verify_key(authorization)
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    return {
        "object": "list",
        "data": [
            {
                "id": b.id,
                "type": b.type,
                "group": b.group,
                "url": b.url,
                "models": b.models,
                "healthy": b.healthy,
                "last_check": b.last_check,
            }
            for b in registry.list_backends()
        ],
    }


async def _resolve_request_route(
    request: Request,
    slot: RequestSlot,
) -> tuple[str, dict[str, Any], bool, str, list[Any]]:
    """Resolve the request's workspace + context and select backend candidates.

    Phases 2-7 of ``chat_completions``: parse the body, resolve a persona
    slug to its workspace, run auto-routing for ``auto``, apply the
    auto-vision text-only fallback, unpack synthetic ``base::variant`` ids,
    gate on module state, apply variant/model overrides, inject temporal /
    system-prompt / file-attachment / memory context, acquire the
    per-workspace semaphore, record counters, and select healthy backend
    candidates for the resolved workspace.

    Returns:
        ``(workspace_id, body, stream, persona, candidates)``.
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    workspace_id = body.get("model") or "auto"
    _original_model_id = workspace_id
    # Phase 2: Resolve persona slug → workspace_model (e.g. "dailydriver" → "auto-daily")
    workspace_id = _resolve_persona_workspace(workspace_id)
    stream = body.get("stream", False)

    # Phase 3: Content-aware routing for 'auto' — LLM intent classification,
    # falling back to weighted keyword scoring.
    workspace_id = await _resolve_auto_routing(workspace_id, body.get("messages", []))

    # Phase 4: auto-vision text-only fallback — reroute to auto-reasoning when
    # no image_url is present in the request.
    workspace_id, body = _resolve_vision_fallback(workspace_id, body)

    # Phase 4a: unpack the canonical "base::variant" synthetic form before
    # Gate 4 so the gate sees the real workspace's module state.
    workspace_id, _alias_variant = _unpack_synthetic_workspace(workspace_id)

    # Gate 4: reject requests to a workspace whose owning module is currently
    # disabled. Checked after all workspace_id-mutating phases so it sees the
    # final resolved id, not an intermediate alias.
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    if is_workspace_disabled(workspace_id):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' is disabled (module not enabled).",
        )

    # Phase 4b: apply a named variant override. Priority: explicit ?variant=
    # query param, else the legacy alias's implied variant, else the persona's
    # declared variant. A variant can only narrow behavior within an
    # already-permitted workspace, never grant access to a disabled one.
    workspace_id = _resolve_workspace_variant(
        _original_model_id,
        workspace_id,
        request.query_params.get("variant") or _alias_variant,
    )

    # Phase 4c: explicit ?model=<hint> query param overrides the resolved
    # model_hint, bounded to the known model catalog (unrecognized = silent
    # no-op). A persona's model_pin applies through the same mechanism; an
    # explicit ?model= always wins over the pin.
    _persona_for_pin = _PERSONA_MAP.get(_original_model_id)
    _model_pin = _persona_for_pin.model_pin if _persona_for_pin else None
    workspace_id = _resolve_model_override(
        workspace_id, request.query_params.get("model") or _model_pin
    )

    # Phase 5: Temporal context injection — today's date + a search-first nudge
    # for web-tool-enabled workspaces.
    body = _inject_temporal_context(workspace_id, body)

    # Phase 6: Workspace-level system_prompt_append — appended to existing system
    # message or injected as a new system message if none is present.
    body = _inject_system_prompt_append(workspace_id, body)

    # Phase 7: File attachment injection — OWUI uploads live in body["files"];
    # inject notes into the last user message so the model can reference file IDs.
    body = _inject_attached_files(body)

    # Phase 8: Auto-context injection — proactive memory recall + KB retrieval
    # for opted-in workspaces (no-op unless inject_memory / auto_rag).
    _cid = get_correlation_id()
    body = await inject_recalled_memory(workspace_id, body, _cid)
    body = await inject_retrieved_context(workspace_id, body, _cid)

    # Per-workspace semaphore + gauge
    await slot.acquire_workspace(workspace_id)

    _request_count[workspace_id] = _request_count.get(workspace_id, 0) + 1
    _requests_total.labels(workspace=workspace_id).inc()
    slot.mark_active()

    # Track persona usage — the "model" field in the request is the persona
    # (workspace ID) the user selected in Open WebUI.
    persona = body.get("model") or "auto"
    if persona in WORKSPACES:
        _record_persona(persona, "unknown")

    candidates = registry.get_backend_candidates(workspace_id)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail=(
                "No healthy backends available. "
                "Ensure Ollama is running and a model is pulled. "
                "Check config/backends.yaml."
            ),
        )

    return workspace_id, body, stream, persona, candidates


async def _dispatch_council(
    workspace_id: str,
    body: dict[str, Any],
    stream: bool,
    persona: str,
    slot: RequestSlot,
    start_time: float,
) -> Any | None:
    """Handle the council-routing path for workspaces that declare a council config.

    Returns a streaming or JSON response when the workspace declares a
    ``council`` block, else ``None`` so the caller proceeds to the normal
    non-streaming / streaming branches.
    """
    council_cfg = WORKSPACES.get(workspace_id, {}).get("council")
    if not council_cfg:
        return None
    logger.info(
        "Council routing: workspace=%s reviewers=%d stream=%s",
        workspace_id,
        len(council_cfg.get("members") or []),
        stream,
    )
    synth_model = str(council_cfg.get("synthesizer_model", "council"))
    _record_persona(persona, synth_model)
    if stream:
        return StreamingResponse(
            stream_council_review(
                body,
                council_cfg,
                slot.detach(),
                registry=registry,
                workspace_id=workspace_id,
            ),
            media_type="text/event-stream",
            headers={"x-portal-route": f"{workspace_id};council;{synth_model}"},
        )

    completion = await run_council_review(
        body,
        council_cfg,
        registry=registry,
        workspace_id=workspace_id,
    )
    _record_response_time(
        completion.model,
        workspace_id,
        time.monotonic() - start_time,
    )
    return JSONResponse(
        content=completion.data,
        headers={"x-portal-route": (f"{workspace_id};{completion.backend_id};{completion.model}")},
    )


async def _dispatch_non_streaming(
    candidates: list[Any],
    body: dict[str, Any],
    workspace_id: str,
    persona: str,
    stream: bool,
    start_time: float,
) -> JSONResponse:
    """Iterate healthy candidates and return the first successful non-streaming response.

    Tries each backend in priority order via ``_try_non_streaming``; the model
    hint is enforced (skip backends without the hinted model) for all but the
    last candidate, where any model is accepted. Applies the workspace's
    ``chain`` when configured. Raises HTTPException 502 when every candidate
    fails.

    Lives here (not non_streaming.py) so unit tests monkeypatch
    ``handlers._try_non_streaming`` to intercept the dispatch.

    Returns:
        ``JSONResponse`` from the first successful backend.
    """
    logger.info(
        "Routing workspace=%s → %d candidate(s) stream=%s",
        workspace_id,
        len(candidates),
        stream,
    )
    _ns_chain = WORKSPACES.get(workspace_id, {}).get("chain") or []
    for i, backend in enumerate(candidates):
        is_last = i == len(candidates) - 1
        result = await _try_non_streaming(
            backend,
            body,
            workspace_id,
            start_time,
            enforce_hint=(not is_last),
            persona=persona,
        )
        if result is not None:
            route_header = result.headers.get("x-portal-route", ";;")
            resolved_model = (
                route_header.split(";")[2] if len(route_header.split(";")) > 2 else "unknown"
            )
            _record_response_time(
                resolved_model,
                workspace_id,
                time.monotonic() - start_time,
            )
            _record_persona(persona, resolved_model)
            if _ns_chain:
                primary_data = result.body
                if isinstance(primary_data, bytes):
                    import json as _json

                    primary_data = _json.loads(primary_data)
                primary_text = str(
                    primary_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                return await _run_non_streaming_chain(
                    primary_text=primary_text,
                    chain=_ns_chain,
                    backend=backend,
                    body=body,
                    workspace_id=workspace_id,
                    start_time=start_time,
                    primary_data=primary_data,
                    primary_model=resolved_model,
                )
            return result
    # All backends failed
    _record_error(workspace_id, "all_backends_failed")
    raise HTTPException(
        status_code=502,
        detail="All backends failed — check server logs",
    )


async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
) -> Any:
    """POST /v1/chat/completions — primary OpenAI-compatible chat endpoint.

    Routes, applies policy, dispatches to a backend, and streams (or returns)
    the response. Phases, in order:
    1. Auth + size limit + three-tier semaphore acquisition (global, per-API-key,
       per-workspace; timeout → HTTP 429 with Retry-After).
    2. Persona-to-workspace resolution (``_PERSONA_MAP[slug].workspace_model``).
    3. Auto-routing for ``auto`` (LLM intent classifier → keyword fallback).
    4. auto-vision text-only fallback (no image → reroute to auto-reasoning).
    5. ``system_prompt_append`` injection.
    6. File attachment injection (OWUI uploads live in ``body["files"]``).
    7. Candidate selection (``registry.get_backend_candidates``).
    8. Non-streaming branch: iterate candidates, first success or 502.
    9. Streaming branch: single candidate → direct stream; multiple candidates →
       ``_stream_with_fallback`` (stream, falling back to non-streaming retries).

    Semaphore lifecycle — two release sites: ``chat_completions.finally`` →
    ``slot.release_if_attached()`` (no-op for detached streaming paths); the
    streaming helper's finally → ``slot.release()`` after the stream is consumed
    or the client disconnects. ``RequestSlot`` owns all three semaphores and
    the concurrent-requests gauge for the request's lifetime.

    Raises:
        HTTPException: 400 (invalid JSON), 401 (bad auth), 413 (body too
            large), 429 (semaphore timeout), 502 (all backends failed), 503
            (registry not initialised; no healthy backends).
    """
    _verify_key(authorization)

    slot = RequestSlot()
    await slot.acquire_global()

    # Per-API-key semaphore
    _api_key_raw = authorization.removeprefix("Bearer ").strip() if authorization else ""
    await slot.acquire_api_key(_api_key_raw)

    workspace_id: str = "unknown"
    start_time = time.monotonic()
    try:
        workspace_id, body, stream, persona, candidates = await _resolve_request_route(
            request, slot
        )

        council_resp = await _dispatch_council(
            workspace_id, body, stream, persona, slot, start_time
        )
        if council_resp is not None:
            return council_resp

        if not stream:
            # Non-streaming: try each backend until one succeeds; enforce the
            # model hint except on the last candidate.
            return await _dispatch_non_streaming(
                candidates, body, workspace_id, persona, stream, start_time
            )

        backend, target_model, _model_hint, _chain, _secondary_model, _tertiary_model = (
            _select_streaming_backend(workspace_id, candidates)
        )
        (
            backend_body,
            effective_tools,
            _has_tools,
            _portal_no_tools,
        ) = await _build_streaming_request(body, backend, target_model, workspace_id, persona)

        logger.info(
            "Routing workspace=%s → backend=%s model=%s stream=%s (1/%d candidates)",
            workspace_id,
            backend.id,
            target_model,
            stream,
            len(candidates),
        )

        if len(candidates) == 1:
            # Single candidate — no fallback possible, return streaming directly
            _record_persona(persona, target_model)
            _stream_fn = _select_stream_fn(
                backend,
                backend_body,
                slot,
                workspace_id,
                target_model,
                persona,
                effective_tools,
                start_time,
                _chain,
                _secondary_model,
                _tertiary_model,
                _portal_no_tools,
                _has_tools,
            )
            _streaming_response = StreamingResponse(
                _stream_fn,
                media_type="text/event-stream",
                headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
            )
            return _streaming_response

        # Multiple candidates — stream from the first; fall back to non-streaming
        # retries of the remaining.
        remaining = candidates[1:]

        slot.detach()
        _streaming_response = StreamingResponse(
            _stream_with_fallback(
                backend,
                body,
                workspace_id,
                target_model,
                persona,
                effective_tools,
                start_time,
                _has_tools,
                _chain,
                _portal_no_tools,
                _secondary_model,
                _tertiary_model,
                remaining,
                slot,
                backend_body,
            ),
            media_type="text/event-stream",
            headers={"x-portal-route": f"{workspace_id};{backend.id};{target_model}"},
        )
        _record_persona(persona, target_model)
        return _streaming_response
    except HTTPException:
        raise
    except Exception:
        _record_error(workspace_id, "unexpected_error")
        raise
    finally:
        slot.release_if_attached()


async def anthropic_messages(
    request: Request,
    authorization: str | None = Header(None),
) -> Any:
    """POST /v1/messages — Anthropic Messages API compatibility endpoint.

    Translates Anthropic SDK requests (Claude Code, ``anthropic`` Python SDK)
    into the pipeline's OpenAI-compatible format, routes them through the same
    workspace logic as ``/v1/chat/completions``, and returns responses in
    Anthropic wire format. Makes Claude Code usable as a local-model IDE (see
    ``scripts/cc-local.sh``).

    Implementation: translates the body then dispatches to
    ``/v1/chat/completions`` via ASGI-level loopback (zero network overhead,
    full routing stack, independent semaphore slot).
    """
    _verify_key(authorization)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None

    model_id = body.get("model", "auto")
    openai_body = anthropic_to_openai_body(body)
    stream = openai_body.get("stream", False)
    msg_id = f"msg_{__import__('uuid').uuid4().hex[:24]}"

    fwd_headers = {
        "Authorization": authorization or "",
        "Content-Type": "application/json",
    }

    # Deferred to avoid circular import (app.py imports handlers.py)
    from portal.platform.inference.router.app import app as _app  # noqa: PLC0415

    if stream:

        async def _generate() -> AsyncIterator[str]:
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=_app),  # type: ignore[arg-type]
                    base_url="http://portal-local",
                    timeout=httpx.Timeout(300.0),
                ) as client,
                client.stream(
                    "POST",
                    "/v1/chat/completions",
                    json=openai_body,
                    headers=fwd_headers,
                ) as resp,
            ):
                async for chunk in openai_stream_to_anthropic_sse(
                    resp.aiter_lines(), msg_id, model_id
                ):
                    yield chunk

        return StreamingResponse(_generate(), media_type="text/event-stream")

    # Non-streaming
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app),  # type: ignore[arg-type]
        base_url="http://portal-local",
        timeout=httpx.Timeout(300.0),
    ) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json=openai_body,
            headers=fwd_headers,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return openai_response_to_anthropic(resp.json(), model_id)
