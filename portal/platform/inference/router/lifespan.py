"""FastAPI lifespan + startup wiring.

The ``lifespan`` async context manager runs on app startup/shutdown.
It loads the backend registry, validates workspace hints, initializes
notifications, runs model warmups, and tears them down cleanly on exit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
from fastapi import FastAPI

import portal.platform.inference.load_guard as _load_guard_mod
import portal.platform.inference.router.concurrency as _concurrency_mod
import portal.platform.inference.router.council as _council_mod
import portal.platform.inference.router.streaming as _streaming_mod
from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.load_guard import LoadGuard
from portal.platform.inference.ollama_native import OllamaNativeTransport
from portal.platform.inference.omlx_auth import OmlxKeyAuth
from portal.platform.inference.router.power import (
    INTERNAL_WARMUP_WORKSPACE,
    _power_polling_loop,
    _record_engine_call,
)
from portal.platform.inference.router.routing import (
    _LLM_ROUTER_ENABLED,
    _LLM_ROUTER_MODEL,
    warm_router_model,
)
from portal.platform.inference.router.state import (
    _load_state,
    _request_count,
    _save_state,
    _state_save_loop,
)
from portal.platform.inference.router.validation import (
    _validate_workspace_hints,
    warn_unset_thinking_mode,
)
from portal.platform.inference.router.workspaces import WORKSPACES
from portal.platform.inference.tool_registry import tool_registry

logger = logging.getLogger(__name__)

_startup_time = time.time()

# Mutable module-level singletons — set by lifespan, used by routes
_http_client: httpx.AsyncClient | None = None
_ollama_native_client: httpx.AsyncClient | None = None
registry: BackendRegistry | None = None
_health_task: asyncio.Task[Any] | None = None
_state_save_task: asyncio.Task[Any] | None = None
_tool_registry_task: asyncio.Task[Any] | None = None
_preferred_resident_task: asyncio.Task[Any] | None = None
_notification_dispatcher = None  # type annotation deferred to TYPE_CHECKING
_notification_scheduler = None


def _init_notifications(registry: BackendRegistry) -> None:
    """Build and start the notification dispatcher + daily-summary scheduler.

    Called from ``lifespan`` only when ``NOTIFICATIONS_ENABLED=true``.

    Sequencing that matters: notifications are late-imported here (the package
    imports ``cluster_backends``, already loaded — a top-level import would
    close a cycle); channels share ``_http_client``; an immediate threshold
    check alerts on problems present at startup; ``_attach_to_pipeline`` must
    run before ``NotificationScheduler.start()`` because its baseline snapshot
    reads ``_request_count`` during ``start()``.

    Mutates the module-level ``_notification_dispatcher`` and
    ``_notification_scheduler``.

    Args:
        registry: The pipeline's ``BackendRegistry``; the immediate threshold
            check inspects it for unhealthy backends.
    """
    global _notification_dispatcher, _notification_scheduler
    # Late import to avoid circular dependency — notifications imports cluster_backends
    from portal.platform.inference.notifications import (
        NotificationDispatcher,
        NotificationScheduler,
    )
    from portal.platform.inference.notifications.channels import (
        EmailChannel,
        PushoverChannel,
        SlackChannel,
        TelegramChannel,
        WebhookChannel,
    )

    _notification_dispatcher = NotificationDispatcher()

    # Register configured channels — share the pipeline's HTTP connection pool
    _notification_dispatcher.add_channel(SlackChannel(_http_client))
    _notification_dispatcher.add_channel(TelegramChannel(_http_client))
    _notification_dispatcher.add_channel(EmailChannel(_http_client))
    _notification_dispatcher.add_channel(PushoverChannel(_http_client))
    _notification_dispatcher.add_channel(WebhookChannel(_http_client))

    # Run threshold check on first health cycle — fire-and-forget so the sync
    # init doesn't block.
    import asyncio as _asyncio  # noqa: PLC0415

    _asyncio.ensure_future(_notification_dispatcher.check_thresholds_and_alert(registry))

    # Schedule daily summary
    _notification_scheduler = NotificationScheduler(_notification_dispatcher)

    # Attach scheduler to pipeline metrics BEFORE starting — the baseline
    # snapshot reads _request_count during start().
    from portal.platform.inference.notifications import scheduler as notif_scheduler

    notif_scheduler._attach_to_pipeline(
        _notification_dispatcher,
        _request_count,
        _startup_time,
        registry,
    )

    _notification_scheduler.start()


async def _warmup_auto_model(registry: BackendRegistry) -> None:
    """Pre-load the ``auto`` workspace's default backend with a 1-token request.

    Ollama lazily loads models on first request; this makes the model resident
    so the first user request streams immediately. Uses ``backend.models[0]``
    (not the workspace ``model_hint``) — the goal is warming the backend's disk
    cache, not exercising routing. ``num_predict: 1`` forces a load + forward
    pass without meaningful compute. Failures are logged and swallowed — a
    failed warmup never crashes the pipeline.

    Runs from ``_run_startup_warmups`` as a background task, parallel with
    ``_warmup_llm_router``.

    Args:
        registry: The pipeline's ``BackendRegistry`` instance.
    """
    if _http_client is None:
        logger.debug("Warmup skipped: HTTP client not ready")
        return
    try:
        backend = registry.get_backend_for_workspace("auto")
        if backend is None:
            logger.debug("Warmup skipped: no healthy auto backend")
            return

        # Minimal prompt: one token of output, fastest model already in memory.
        # If backend.models is empty, the backend is misconfigured — skip warmup.
        if not backend.models:
            logger.warning(
                "Warmup skipped: backend %s has empty models list — check config/backends.yaml",
                backend.id,
            )
            return
        if backend.type == "omlx":
            # oMLX has no /api/generate nor keep_alive — its EnginePool owns
            # residency. Warm via the OpenAI-compatible endpoint normal traffic
            # uses.
            warmup_url = f"{backend.url.rstrip('/')}/v1/chat/completions"
            warmup_payload = {
                "model": backend.models[0],
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 1,
                "stream": False,
            }
        else:
            warmup_url = f"{backend.url.rstrip('/')}/api/generate"
            warmup_payload = {
                "model": backend.models[0],
                "prompt": "ok",
                "stream": False,
                "keep_alive": -1,  # int not string — Ollama 0.30.8+ rejects "-1"
                # num_ctx caps the warmed runner's reserved KV-cache; without
                # it the default (full context × OLLAMA_NUM_PARALLEL) pins tens
                # of GiB forever via keep_alive: -1.
                "options": {"num_predict": 1, "num_ctx": 8192},
            }

        async def _guarded_warmup() -> httpx.Response:
            release = None
            end = None
            guard = _load_guard_mod.GUARD
            try:
                if backend.type == "ollama" and guard is not None:
                    release = await guard.admit(backend.url, str(warmup_payload["model"]))
                    end = guard.begin(_load_guard_mod.OLLAMA, str(warmup_payload["model"]))
                return await _http_client.post(warmup_url, json=warmup_payload)
            finally:
                if end is not None:
                    end()
                if release is not None:
                    release()

        resp = await _guarded_warmup()
        if resp.status_code == 200:
            try:
                warmup_body = resp.json()
            except Exception:
                warmup_body = {}
            _record_engine_call(
                str(warmup_payload["model"]), INTERNAL_WARMUP_WORKSPACE, warmup_body
            )
            logger.info(
                "Warmup complete: %s model '%s' pre-loaded",
                backend.type,
                warmup_payload["model"],
            )
        else:
            logger.warning(
                "Warmup backend %s returned HTTP %d — will load on first use",
                backend.id,
                resp.status_code,
            )
    except Exception as e:
        logger.debug("Model warmup failed (non-fatal): %s", e)


async def _warmup_llm_router() -> None:
    """Pre-load the LLM intent-router model with a pinned 1-token request.

    Every auto-routed request calls ``_route_with_llm()`` first; on a cold
    Ollama this adds 30–60s to the first auto request. ``keep_alive: -1`` pins
    the router model so a larger inference model doesn't evict it under memory
    pressure. ``options.num_ctx`` must match the 2048 used by the real routing
    call — an uncapped default reserves tens of GiB and forces the same
    eviction this warmup exists to prevent.

    Skipped when ``LLM_ROUTER_ENABLED=false`` (keyword-fallback routing).

    Runs from ``_run_startup_warmups`` as a background task, parallel with
    ``_warmup_auto_model``.
    """
    if not _LLM_ROUTER_ENABLED:
        return
    if _http_client is None:
        logger.debug("LLM router warmup skipped: HTTP client not ready")
        return
    # The routing call itself (routing.warm_router_model): a trivial prompt
    # loaded the weights but left the routing prefix uncached, so the first
    # real request still overran its 1 s deadline.
    status = await warm_router_model()
    if status == 200:
        logger.info("Warmup complete: LLM router model '%s' pre-loaded", _LLM_ROUTER_MODEL)
    else:
        logger.debug(
            "LLM router warmup returned HTTP %d — router will cold-load on first use", status
        )


#: Seconds a preferred resident is protected from eviction (refreshed every tick). It
#: is never pinned: protected idle memory yields to another seat's admission.
_PREFERRED_RESIDENT_PROTECT_S = 3600.0
#: The keeper's re-check interval: the load lands at startup or at the first idle moment.
_PREFERRED_RESIDENT_INTERVAL_S = 60.0


def _preferred_resident_targets(
    registry: BackendRegistry,
) -> list[tuple[Any, str, str, dict[str, Any]]]:
    """(backend, engine, model, generate options) per ``defaults.preferred_residents``.

    The backend is the first candidate that actually serves the seat's hint, not the
    group's priority head: ``auto-daily`` routes through group ``general`` whose head is
    ``omlx-general``, and an Ollama tag posted to oMLX is a 404 (2026-11-16). ``model``
    is the resolved native id, as a request would send it.

    A hint whose tag bakes ``num_ctx`` (the ``-ctx`` derived-tag convention) gets none:
    otherwise the warm load would pin a runner with a context the seat never asked for.
    """
    targets: list[tuple[Any, str, str, dict[str, Any]]] = []
    for ws_id in registry.preferred_residents:
        ws = WORKSPACES.get(ws_id) or {}
        hint = str(ws.get("model_hint") or "")
        backend: Any = None
        model = ""
        for candidate in registry.get_backend_candidates(ws_id):
            resolved = (
                candidate.resolve_model(hint) if candidate.type in ("ollama", "omlx") else None
            )
            if resolved:  # the first backend that really serves the hint, not the group head
                backend, model = candidate, resolved
                break
        if backend is None:
            logger.warning(
                "preferred resident %s: no healthy backend serves %r — skipped", ws_id, hint
            )
            continue
        options: dict[str, Any] = {"num_predict": 1}
        if "-ctx" not in model:
            options["num_ctx"] = int(ws.get("context_limit") or 8192)
        targets.append((backend, backend.type, model, options))
    return targets


async def _warm_preferred_resident(
    backend: Any,
    engine: str,
    model: str,
    options: dict[str, Any],
    guard: LoadGuard,
    ollama_base: str,
) -> str:
    """Make one preferred resident resident, if the host has room to spare right now.

    Returns ``resident``/``loaded``, or the reason it was left for the next tick. Only
    loads when nothing is in flight and the model fits the headroom the host already
    has, so a seat's admission never waits behind the warm-up.
    """
    plan = await guard.plan(ollama_base, [(engine, model)])
    rows = plan.get("models") or []
    headroom = plan.get("headroom_gib")
    if rows and rows[0].get("resident"):
        return "resident"
    if plan.get("busy"):
        return "waiting for in-flight work"
    if headroom is None:
        return "waiting for a readable oMLX ceiling"
    need = float(plan.get("need_gib") or 0)
    if need > float(headroom):
        return f"waiting: needs {need:.1f} GiB, headroom {float(headroom):.1f} GiB"
    _load_guard_mod.set_load_wait("5")  # never queue behind another seat's cold load
    if engine == _load_guard_mod.OLLAMA:
        release = await guard.admit(backend.url, model)
        end = guard.begin(_load_guard_mod.OLLAMA, model)
        try:
            # keep_alive: -1 keeps the daily driver loaded until the guard frees it.
            resp = await _http_client.post(  # type: ignore[union-attr]
                f"{backend.url.rstrip('/')}/api/generate",
                json={
                    "model": model,
                    "prompt": "ok",
                    "stream": False,
                    "keep_alive": -1,
                    "options": options,
                },
            )
        finally:
            end()
            if release is not None:
                release()
    else:
        await guard.admit_omlx(model)  # oMLX owns residency; no keep_alive to send
        resp = await _http_client.post(  # type: ignore[union-attr]
            f"{backend.url.rstrip('/')}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 1,
                "stream": False,
            },
        )
    if resp.status_code != 200:
        return f"HTTP {resp.status_code} from {backend.url}"
    return "loaded"


async def _keep_preferred_residents(registry: BackendRegistry) -> None:
    """Warm ``defaults.preferred_residents`` at startup, then re-assert their protection.

    A cold 23.7 GiB daily driver is a 40 s first token for the most-used path
    (2026-11-16); this keeps it resident with ``keep_alive``. A load that does not fit
    is retried on the interval, so it lands at the first idle moment instead of
    competing with a seat's admission. Protection never pins: the guard evicts it
    before it would refuse another seat. Never raises; cancelled at shutdown.
    """
    guard = _load_guard_mod.GUARD
    if guard is None:
        return
    ollama_base = next((b.url for b in registry.list_backends() if b.type == "ollama"), "")
    if not ollama_base:  # nothing to measure against; the keeper waits for a backend
        return
    # One line per transition, not one per tick: a persistent failure logs once.
    last: dict[str, str] = {}
    while True:
        for backend, engine, model, options in _preferred_resident_targets(registry):
            try:
                guard.protect(engine, model, _PREFERRED_RESIDENT_PROTECT_S)
                status = await _warm_preferred_resident(
                    backend, engine, model, options, guard, ollama_base
                )
            except Exception as e:  # a warm-up never crashes the pipeline
                status = f"error: {e}"
            if last.get(model) == status or (
                status in ("resident", "loaded") and last.get(model) in ("resident", "loaded")
            ):
                continue  # one line per transition: loaded-then-resident is one state
            last[model] = status
            if status in ("resident", "loaded"):
                logger.info(
                    "Preferred resident %s on %s (%s): %s — kept warm, yields to a seat",
                    model,
                    backend.id,
                    backend.url,
                    status,
                )
            else:
                logger.warning(
                    "Preferred resident %s on %s (%s): %s — retrying when the host is idle",
                    model,
                    backend.id,
                    backend.url,
                    status,
                )
        await asyncio.sleep(_PREFERRED_RESIDENT_INTERVAL_S)


async def _run_startup_warmups(registry: BackendRegistry) -> None:
    """Fire startup warmups in parallel; never raises.

    Both warmups swallow their own exceptions; ``return_exceptions=True`` is
    belt-and-suspenders. Launched as a background task so startup isn't
    blocked — warmups optimize, they don't gate.

    Args:
        registry: Forwarded to ``_warmup_auto_model``.
    """
    await asyncio.gather(
        _warmup_auto_model(registry),
        _warmup_llm_router(),
        return_exceptions=True,
    )


async def _refresh_tool_registry_at_startup() -> None:
    """One forced tool-registry refresh so the first request doesn't miss; never raises."""
    try:
        count = await tool_registry.refresh(force=True)
        logger.info("Startup tool registry refresh: %d tools discovered", count)
    except Exception as e:
        logger.warning("Startup tool registry refresh failed (non-fatal): %s", e)


def _is_ollama_backend(registry: BackendRegistry, base_url: str) -> bool:
    """True only for a base URL the registry positively knows is Ollama."""
    return _is_backend_type(registry, base_url, "ollama")


def _is_backend_type(registry: BackendRegistry, base_url: str, kind: str) -> bool:
    needle = base_url.rstrip("/")
    return any(b.type == kind and b.url.rstrip("/") == needle for b in registry.list_backends())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifecycle — create singletons on startup, tear down on shutdown.

    The single point of process-lifecycle truth: every module-level singleton
    (``registry``, ``_http_client``, ``_request_semaphore``, the notification
    dispatcher/scheduler, and the background tasks ``_health_task``,
    ``_state_save_task``, power-polling) is created here and torn down here.

    Startup: create ``_request_semaphore``; pre-create the Prometheus multiproc
    dir (worker race when ``PIPELINE_WORKERS > 1``); create ``_http_client``
    with a 600s body / 5s connect timeout (cold-loading 32B models takes 2–4
    min); construct ``BackendRegistry``; validate ``WORKSPACES`` hints
    (``STRICT_HINT_VALIDATION=true`` raises on unresolvable hints); run one
    synchronous health check; load persisted metrics state; launch warmups,
    power polling, notifications, the tool-registry refresh, the health loop,
    and the state-save loop.

    Shutdown (roughly LIFO): final synchronous ``_save_state`` before the save
    task is cancelled; cancel ``_state_save_task``/``_health_task`` and the
    startup tool-registry refresh; close ``_http_client`` after tasks; stop
    the notification scheduler; close the registry's health-check client.

    Args:
        app: The FastAPI app. Not used directly — required by the
            asynccontextmanager interface.

    Yields:
        Nothing. The yield separates startup from shutdown; request handling
        runs while it is suspended.
    """
    global registry, _health_task, _http_client, _ollama_native_client
    global _notification_dispatcher, _notification_scheduler, _state_save_task
    global _tool_registry_task
    global _preferred_resident_task
    _concurrency_mod._request_semaphore = asyncio.Semaphore(_concurrency_mod._MAX_CONCURRENT)
    # Pre-create Prometheus multiproc dir at startup so workers don't race.
    if mp_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        os.makedirs(mp_dir, exist_ok=True)
    # Streaming uses a 600s read idle timeout; non-streaming applies request-specific sizing.
    # Connect stays 5s because local backends should bind immediately.
    registry = BackendRegistry()
    _guard = LoadGuard(
        omlx_url=lambda: next((b.url for b in registry.list_backends() if b.type == "omlx"), None),
        ollama_url=lambda: next(
            (b.url for b in registry.list_backends() if b.type == "ollama"), None
        ),
    )
    _load_guard_mod.GUARD = _guard
    # Ollama backends are served from native /api/chat behind the unchanged
    # OpenAI surface: /v1 drops most sampling and `think` (ollama_native.py).
    # The limits live on the transport, which is what enforces them once a
    # custom transport is supplied.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(600.0, connect=5.0),
        auth=OmlxKeyAuth(),
        transport=OllamaNativeTransport(
            httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            ),
            is_ollama=lambda base: _is_ollama_backend(registry, base),
            # Host-memory admission across both engines (load_guard.py).
            guard=_guard,
            is_omlx=lambda base: _is_backend_type(registry, base, "omlx"),
        ),
    )
    # Native MCP callers preserve Ollama's exact HTTP schema here; this client
    # intentionally bypasses the /v1 translating transport above.
    _ollama_native_client = httpx.AsyncClient(
        timeout=httpx.Timeout(600.0, connect=5.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    )
    from portal.platform.inference.router import ollama_passthrough as _ollama_passthrough

    _ollama_passthrough.configure(registry, _ollama_native_client)
    # Propagate shared client to the routing module (needed by _route_with_llm)
    import portal.platform.inference.router.routing as _routing_mod

    _routing_mod._http_client = _http_client
    _streaming_mod._http_client = _http_client
    _council_mod._http_client = _http_client
    # Push registry + _http_client to modules that can't capture them at import time.
    import portal.platform.inference.router.handlers as _handlers_mod  # noqa: PLC0415
    import portal.platform.inference.router.non_streaming as _non_streaming_mod  # noqa: PLC0415
    import portal.platform.inference.router.validation as _validation_mod  # noqa: PLC0415

    _handlers_mod.registry = registry
    _non_streaming_mod.registry = registry
    _non_streaming_mod._http_client = _http_client
    _validation_mod.registry = registry
    for _w in warn_unset_thinking_mode():
        logger.warning("THINK MODE: %s", _w)
    hint_errors = _validate_workspace_hints(registry)
    if hint_errors:
        for e in hint_errors:
            logger.error("HINT VALIDATION: %s", e)
        if os.environ.get("STRICT_HINT_VALIDATION", "true").lower() in ("true", "1", "yes"):
            raise RuntimeError(
                f"STRICT_HINT_VALIDATION=true and {len(hint_errors)} hint(s) failed validation. "
                "See logs above. Set STRICT_HINT_VALIDATION=false to start anyway."
            )
        else:
            logger.warning(
                "HINT VALIDATION: %d hint(s) failed but STRICT_HINT_VALIDATION=false — starting anyway. "
                "Hints will silently fall back at request time. Fix backends.yaml or WORKSPACES.",
                len(hint_errors),
            )
    for ws_id, ws_cfg in WORKSPACES.items():
        ctx_limit = ws_cfg.get("context_limit")
        hint = ws_cfg.get("model_hint", "")
        if ctx_limit:
            # "-ctx" only appears in the derived-tag convention (e.g. -ctx32k),
            # so a substring check is robust without a brittle suffix list.
            if "-ctx" in hint:
                logger.info(
                    "workspace=%s context_limit=%d enforced via derived tag %s",
                    ws_id,
                    ctx_limit,
                    hint,
                )
            else:
                logger.warning(
                    "workspace=%s declares context_limit=%d but Ollama /v1 ignores options.num_ctx — "
                    "use './launch.sh apply-model-params' to bake num_ctx=%d into the model tag, "
                    "or set PARAMETER num_ctx in a Modelfile manually",
                    ws_id,
                    ctx_limit,
                    ctx_limit,
                )

    await registry.health_check_all()
    # Load persisted metrics state from disk (survives restarts)
    _load_state()
    # Pre-warm inference + LLM router models in parallel as background tasks —
    # startup is not blocked.
    asyncio.create_task(_run_startup_warmups(registry))
    # Keep `defaults.preferred_residents` warm (loaded at up, or at the first idle
    # moment) — a cold daily driver is a 40 s first token on the most-used path.
    if _guard is not None and registry.preferred_residents:
        _preferred_resident_task = asyncio.create_task(_keep_preferred_residents(registry))
    # Power metrics polling — graceful if daemon not running
    asyncio.create_task(_power_polling_loop())
    healthy = registry.list_healthy_backends()
    logger.info("Portal Pipeline started. Healthy backends: %d", len(healthy))
    if not healthy:
        logger.warning(
            "No healthy backends on startup — check Ollama is running and "
            "config/backends.yaml URLs are reachable from this container"
        )

    # ── Notifications: alerts + daily summaries ──────────────────────────────
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes"):
        _init_notifications(registry)
        _handlers_mod._notification_dispatcher = _notification_dispatcher

    _in_test_mode = os.environ.get("UNIT_TEST_MODE", "0") == "1"

    async def _on_health(r: BackendRegistry) -> None:
        """Callback for the health-check loop: dispatch threshold alerts."""
        if _notification_dispatcher:
            await _notification_dispatcher.check_thresholds_and_alert(r)

    if not _in_test_mode:
        # Warm the tool registry so the first request's auto-context recall doesn't miss.
        _tool_registry_task = asyncio.create_task(_refresh_tool_registry_at_startup())
        _health_task = asyncio.create_task(registry.start_health_loop(on_health_check=_on_health))
        _state_save_task = asyncio.create_task(_state_save_loop(interval=60))

    yield

    if _tool_registry_task is not None:
        _tool_registry_task.cancel()
        with suppress(asyncio.CancelledError):
            await _tool_registry_task

    if _preferred_resident_task is not None:
        _preferred_resident_task.cancel()
        with suppress(asyncio.CancelledError):
            await _preferred_resident_task

    if _in_test_mode:
        if _ollama_native_client:
            await _ollama_native_client.aclose()
        _ollama_passthrough.configure(None, None)
        return

    # Final state save on shutdown
    _save_state()
    if _state_save_task:
        _state_save_task.cancel()
    if _health_task:
        _health_task.cancel()
    if _http_client:
        await _http_client.aclose()
    if _ollama_native_client:
        await _ollama_native_client.aclose()
    _ollama_passthrough.configure(None, None)
    if _notification_scheduler:
        _notification_scheduler.stop()
    await BackendRegistry.close_health_client()
