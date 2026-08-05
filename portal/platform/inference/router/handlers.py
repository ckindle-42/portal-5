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

# Set by lifespan — NOT captured at import time.
# Importing registry/dispatcher by name from lifespan would capture the module-level
# None before lifespan runs; lifespan pushes the live objects in, same pattern
# as _routing_mod._http_client and _streaming_mod._http_client.
registry: BackendRegistry | None = None
_notification_dispatcher: Any = None


# ── Constants from original router_pipe.py ────────────────────────────────────
try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"

_startup_time_val: float = time.time()
_mp_registry_cache: Any = None
_mp_registry_dir_cache: str | None = None


async def health() -> dict:
    """GET /health — fast unauthenticated liveness probe.

    Used by Open WebUI's "test connection" button, Docker healthchecks,
    and Kubernetes readiness probes. Information disclosure is
    minimal (counts and version).

    ``status`` is ``"ok"`` if at least one backend is healthy, else
    ``"degraded"``. Returning 503 when zero backends are healthy
    would cause orchestrators to kill and restart the pipeline,
    which doesn't help because the problem is upstream (Ollama
    down, not pipeline broken).

    Raises:
        HTTPException: 503 only when the backend registry hasn't
            been initialised yet (lifespan startup race).
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

    Probes the pipeline itself, Ollama, and every MCP server in
    ``tool_registry.MCP_SERVERS`` in parallel with a per-probe 3s
    timeout. Returns a dict keyed by component name; each value is
    the component's own ``/health`` (or ``/api/tags`` for Ollama)
    JSON if 200, else a status dict with ``"degraded"`` (HTTP error)
    or ``"down"`` (connection error).

    One shared ``httpx.AsyncClient(timeout=3)`` handles all probes
    via ``asyncio.gather`` — no fresh client per probe.

    Returns:
        Dict keyed by component name, values are component-specific
        health JSON or status dicts.
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

    Operator escape hatch for "I just added or changed an MCP and
    want the pipeline to pick it up without waiting for the next
    scheduled refresh." Bypasses the 1h TTL via
    ``tool_registry.refresh(force=True)``.

    Requires the admin key (``PORTAL5_ADMIN_KEY``), not the regular
    API key — state-mutating endpoint.

    Returns:
        ``{"refreshed": True, "tools_registered": int, "names":
        [str, ...]}``. ``names`` is the sorted list of every tool
        currently in the registry, useful for verifying which
        servers' tools came through.
    """
    _verify_admin_key(authorization)
    from portal.platform.inference.tool_registry import tool_registry

    n = await tool_registry.refresh(force=True)
    return {"refreshed": True, "tools_registered": n, "names": tool_registry.list_tool_names()}


async def test_notifications(authorization: str | None = Header(None)) -> dict:
    """POST /notifications/test — fire a test alert and summary; report status.

    Sanity-check for notification configuration. Dispatches one
    ``AlertEvent`` (type BACKEND_DOWN, message labeled as test) and
    one ``SummaryEvent`` with live data — real ``_request_count``
    and backend counts, not zeros — so an operator can see what a
    real daily summary would look like with current data.

    Requires ``NOTIFICATIONS_ENABLED=true`` at process start (the
    dispatcher is lazily initialised in ``_init_notifications``);
    otherwise returns 503.

    Reports per-channel configuration status by checking the
    canonical env var for each (``SLACK_ALERT_WEBHOOK_URL``,
    ``TELEGRAM_ALERT_BOT_TOKEN``, ``SMTP_HOST``,
    ``PUSHOVER_API_TOKEN`` + ``PUSHOVER_USER_KEY``, ``WEBHOOK_URL``).
    A channel that says ``"configured"`` here may still fail at
    send time (bad token, network issue) — the ``results`` field
    of the response is authoritative for actual deliverability.

    Returns:
        ``{"status": "ok", "results": {...}}`` where ``results``
        contains ``alert``, ``summary``, ``channels``, and
        ``scheduler`` keys.

    Raises:
        HTTPException: 401 on bad auth, 503 when notifications are
            disabled.
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

    **Intentionally unauthenticated.** Prometheus scrapes without
    credentials; requiring auth would force Prometheus to be
    configured with a bearer token (operational burden) for
    minimal gain — the metrics expose request counts per workspace,
    error categories, persona usage, but nothing approaching
    credentials or message content.

    Combines two metric sources:

    1. Hand-rolled gauges (backends healthy/total, uptime,
       workspaces) written as plain Prometheus text.
    2. The full ``prometheus_client`` registry — either the
       in-process ``_REGISTRY`` (single-worker) or the multiprocess
       collector aggregating ``/tmp/<dir>/*.db`` files across all
       uvicorn workers.

    **Multi-worker caching**: when ``PROMETHEUS_MULTIPROC_DIR`` is
    set, the ``MultiProcessCollector`` is cached in
    ``_mp_registry_cache``. Construction scans the dir; caching
    avoids that work on every scrape. The collector reads from
    disk files on each call regardless, so caching the registry
    object never serves stale data.

    **P5-FIX defence-in-depth**: ``os.makedirs(mp_dir,
    exist_ok=True)`` is called both here and in ``lifespan``.
    ``prometheus_client`` writes per-pid files but doesn't create
    the parent dir; first scrape after a worker fork without the
    dir present would 500 (ACCEPTANCE_RESULTS S70-07, 2026-04-25).

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
    # Combine hand-rolled metrics with prometheus_client metrics.
    # Use multiprocess collector when PROMETHEUS_MULTIPROC_DIR is set
    # (aggregates metrics across all uvicorn workers).
    # Cache the registry object — MultiProcessCollector reads from disk files,
    # so there's no need to reconstruct it on every scrape.
    global _mp_registry_cache, _mp_registry_dir_cache
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        # P5-FIX: prometheus_client writes per-pid files but does not create the
        # parent dir. Without this, the first /metrics scrape after worker fork
        # fails with errno-2 (see ACCEPTANCE_RESULTS S70-07, 2026-04-25).
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

    Returns one entry per ``WORKSPACES`` key, plus one entry per
    IDE-curated persona (``ide_expose: true`` — DESIGN_OPENCODE_
    ADDRESSING_V1.md §3.2). Per CLAUDE.md, Portal 5 is Open WebUI's
    sole model source — OWUI sees workspaces as models, never the
    underlying Ollama models. The user picks a workspace (or, for
    opencode/Claude Code, a persona) in the model picker; that
    selection becomes the ``model`` field on the chat-completions
    request and is what ``chat_completions`` routes on.

    The persona entries exist so this endpoint agrees with
    ``opencode.jsonc``'s curated picker (previously they diverged —
    opencode's variant-carrying picker entries existed only in the
    hand-maintained jsonc, invisible to ``/v1/models`` discovery).
    Only ``ide_expose: true`` personas are included — this does NOT
    expose the full ~138-persona catalogue, only the same curated
    subset opencode's picker already shows.

    Per-entry fields:

    * ``id`` — workspace key (e.g. ``"auto-coding"``) or persona slug
      (e.g. ``"codingagentic"``).
    * ``name`` — human display name.
    * ``category`` — OWUI grouping. Derived from the workspace id
      (``bench-*`` → ``"benchmark"``; ``auto-X`` → ``"X"``; else
      the id itself), or explicitly overridden by ``category:`` in
      the workspace's ``WORKSPACES`` entry (or the persona's).
    * ``tags`` — non-standard OWUI extension; defaults to
      ``[category]`` if not set.
    * ``tools`` — the workspace's default tool whitelist (the
      pipeline applies persona-level overrides at request time).
    * ``is_benchmark`` — convenience flag for OWUI UI; ``True``
      for ``bench-*`` workspaces (always ``False`` for personas).
    * ``is_persona`` — ``True`` for IDE-curated persona entries,
      absent/``False`` for base workspace entries.

    Authenticated via ``_verify_key`` because the response leaks
    the full workspace catalogue, which reveals operational config.

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

    Returns ``{id, type, group, url, models, healthy, last_check}``
    per backend. Not part of the OpenAI API surface; used by
    ``tests/portal5_uat_driver.py`` and operator tooling that
    needs to know what's actually live (the registry is loaded
    from ``backends.yaml`` at startup; this is its current state).

    The ``_endpoint`` suffix on the function name is to avoid
    colliding with a previously-named ``_list_backends`` symbol;
    rename tracked in ``DOCSTRINGS_V1_NOTES.md`` as out-of-scope
    cleanup.

    Authenticated via ``_verify_key``.

    Returns:
        ``{"object": "list", "data": [...]}``.

    Raises:
        HTTPException: 401 on bad auth, 503 when the registry
            isn't yet initialised.
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

    # Phase 3: Content-aware routing for 'auto' workspace.
    # Primary path: LLM-based intent classification (P5-FUT-006).
    # Fallback: weighted keyword scoring (_detect_workspace).
    workspace_id = await _resolve_auto_routing(workspace_id, body.get("messages", []))

    # Phase 4: auto-vision text-only fallback — reroute to auto-reasoning when
    # no image_url is present in the request.
    workspace_id, body = _resolve_vision_fallback(workspace_id, body)

    # Phase 4a: unpack the canonical "base::variant" synthetic form (both
    # routing layers emit it directly — Phase 7 canonicalization) before
    # Gate 4, so the gate checks the real workspace's module state.
    workspace_id, _alias_variant = _unpack_synthetic_workspace(workspace_id)

    # Gate 4 (M7 toggle layer): reject requests to a workspace whose owning
    # module is currently disabled. Checked after all workspace_id-mutating
    # phases (persona resolution, auto-routing, vision fallback, legacy
    # alias) so this sees the final resolved workspace, not an intermediate
    # alias.
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    if is_workspace_disabled(workspace_id):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace '{workspace_id}' is disabled (module not enabled).",
        )

    # Phase 4b (BUILD_PROGRAM_COLLAPSE_V1.md Phase 5/6): apply a named
    # variant override onto a factored workspace. Priority: explicit
    # ?variant= query param, else the legacy alias's implied variant
    # (e.g. "auto-agentic" implies variant=heavy), else the persona's own
    # declared variant. Checked against the already-disabled-gated base
    # workspace_id — a variant can only narrow behavior within an
    # already-permitted workspace, never grant access to a disabled one.
    workspace_id = _resolve_workspace_variant(
        _original_model_id,
        workspace_id,
        request.query_params.get("variant") or _alias_variant,
    )

    # Phase 4c (BUILD_PROGRAM_COLLAPSE_V1.md Phase 8, DESIGN §D5): explicit
    # ?model=<hint> query param overrides the resolved workspace/variant's
    # model_hint. Bounded to config/backends.yaml's known model catalog
    # (see _resolve_model_override) -- an unrecognized model param is a
    # silent no-op, not an error.
    #
    # DESIGN_PERSONA_INTENT_REMEDIATION_V1.md §4.2: a persona's own
    # model_pin applies through this exact same mechanism, so a persona
    # claiming a specific model lineage (e.g. magistralstrategist ->
    # Magistral) is actually served that model, not just its
    # workspace's pool-primary. An explicit ?model= query param always
    # wins over the persona's pin (more specific caller intent).
    _persona_for_pin = _PERSONA_MAP.get(_original_model_id)
    _model_pin = _persona_for_pin.model_pin if _persona_for_pin else None
    workspace_id = _resolve_model_override(
        workspace_id, request.query_params.get("model") or _model_pin
    )

    # Phase 5: Temporal context injection — give web-tool-enabled workspaces today's
    # date plus a search-first nudge so local models don't answer time-sensitive
    # questions from a frozen training cutoff.
    body = _inject_temporal_context(workspace_id, body)

    # Phase 6: Workspace-level system_prompt_append — appended to existing system
    # message or injected as a new system message if none is present.
    body = _inject_system_prompt_append(workspace_id, body)

    # Phase 7: File attachment injection — OWUI sends uploaded files in body["files"]
    # but does not include them in the messages array. Inject a note into the last
    # user message so the model can reference audio/document file IDs in tool calls.
    body = _inject_attached_files(body)

    # Phase 8: Auto-context injection — proactively recall cross-session
    # memory and knowledge-base hits for opted-in workspaces, so grounding
    # does not depend on the model volunteering a recall/kb_search call.
    # Both no-op unless the workspace sets inject_memory / auto_rag.
    _cid = get_correlation_id()
    body = await inject_recalled_memory(workspace_id, body, _cid)
    body = await inject_retrieved_context(workspace_id, body, _cid)

    # Per-workspace semaphore + gauge (M6-T05)
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

    Non-streaming branch of ``chat_completions`` (extracted C4.3). Tries each
    backend in priority order via ``_try_non_streaming``; the model hint is
    enforced (skip backends without the hinted model) for all but the last
    candidate, where any model is accepted as fallback. Applies the
    workspace's ``chain`` when configured. Raises HTTPException 502 when
    every candidate fails.

    Lives in handlers.py (not non_streaming.py) so ``_try_non_streaming``
    resolves through this module's namespace — unit tests monkeypatch
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

    This is the function. Open WebUI calls it on every user message;
    it routes, applies policy, dispatches to a backend, and streams
    (or returns) the response. ~650 lines split across the
    following phases, in order:

    1. **Auth + size limit + three-tier semaphore acquisition**:
       global ``_request_semaphore``, per-API-key ``_api_sem``,
       per-workspace ``_ws_sem``. Each acquisition is wrapped in
       ``asyncio.wait_for`` with ``_SEMAPHORE_TIMEOUT`` (50ms
       default); timeout → HTTP 429 with Retry-After.
    2. **Persona-to-workspace resolution**: if the request's
       ``model`` field is a persona slug rather than a workspace
       id, look up ``_PERSONA_MAP[slug].workspace_model`` and use
       that.
    3. **Auto-routing** (only when ``workspace_id == "auto"``):
       Layer 1 ``_route_with_llm`` → Layer 2 ``_detect_workspace``.
       See chunk 2 for those functions.
    4. **auto-vision text-only fallback**: a vision-language model
       called without an image returns empty content. If the
       request has no ``image_url`` parts, reroute to
       ``auto-reasoning`` with a vision-themed system prompt so
       responses use vision-domain vocabulary.
    5. **``system_prompt_append``** from the workspace, appended to
       an existing system message or injected as a new one.
    6. **File attachment injection**: OWUI sends uploads in
       ``body["files"]`` but doesn't put them in ``messages``.
       Inject ``[Attached file — id, name, type]`` notes into the
       last user message so the model can reference them in tool
       calls.
    7. **Candidate selection**: ``registry.get_backend_candidates``
       returns healthy backends for the workspace.
    8. **Non-streaming branch**: iterate candidates,
       ``_try_non_streaming`` each, return first success. All-fail
       returns 502.
    9. **Streaming branch**: pick first candidate, resolve target
       model from hints, inject options, resolve effective tools,
       decide ``_has_tools``.
       - **Single candidate**: hand off directly to
         ``_stream_with_tool_loop`` (if tools) or
         ``_stream_with_preamble`` (no tools). The streaming
         helper owns semaphore lifecycle from here.
       - **Multiple candidates**: wrap in ``_stream_or_fallback``
         nested closure that watches for error chunks and falls
         back to non-streaming retry of the same backend, then
         remaining backends as SSE-wrapped non-streaming
         responses.

    **Semaphore lifecycle** — two release sites (down from five):

    * ``chat_completions.finally:`` → ``slot.release_if_attached()`` — no-op
      for streaming paths (slot was detached); releases for non-streaming.
    * ``_stream_with_tool_loop.finally:`` / ``_stream_with_preamble.finally:``
      → ``slot.release()`` — releases after the stream is fully consumed or
      the client disconnects.

    :class:`~portal.platform.inference.router.concurrency.RequestSlot` owns the three
    semaphores and the concurrent-requests gauge for the request's lifetime.

    Raises:
        HTTPException: 400 (invalid JSON body), 401 (bad auth),
            413 (body too large), 429 (semaphore timeout — global,
            per-key, or per-workspace), 502 (all backends failed
            non-streaming), 503 (registry not initialised; no
            healthy backends).
    """
    _verify_key(authorization)

    slot = RequestSlot()
    await slot.acquire_global()

    # Per-API-key semaphore (M6-T06)
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
            # Non-streaming: try each backend in priority order until one succeeds.
            # Model hint is enforced (skip backends without the hinted model) for
            # all but the last candidate, where we accept any model as fallback.
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

        # Multiple candidates — streaming with non-streaming fallback.
        # Try streaming from first backend; if it fails, fall back to non-streaming
        # from the remaining candidates.
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

    Translates Anthropic SDK requests (Claude Code, ``anthropic`` Python
    SDK, etc.) into the pipeline's OpenAI-compatible format, routes them
    through the same workspace logic as ``/v1/chat/completions``, and
    returns responses in Anthropic wire format.

    This makes Claude Code usable as a **local-model IDE** with full
    Portal 5 intelligence — set::

        export ANTHROPIC_BASE_URL=http://localhost:9099
        export ANTHROPIC_API_KEY=$PIPELINE_API_KEY
        claude --model agenticheavy

    or use ``scripts/cc-local.sh`` which handles the env vars automatically.

    Implementation: translates the request body then dispatches to
    ``/v1/chat/completions`` via ASGI-level loopback (zero network
    overhead, full routing stack, independent semaphore slot).
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
