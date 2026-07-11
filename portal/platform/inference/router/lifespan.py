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
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

import portal.platform.inference.router.concurrency as _concurrency_mod
import portal.platform.inference.router.streaming as _streaming_mod
from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.router.power import _power_polling_loop
from portal.platform.inference.router.routing import (
    _LLM_ROUTER_ENABLED,
    _LLM_ROUTER_MODEL,
    _LLM_ROUTER_OLLAMA_URL,
)
from portal.platform.inference.router.state import (
    _load_state,
    _request_count,
    _save_state,
    _state_save_loop,
)
from portal.platform.inference.router.validation import _validate_workspace_hints
from portal.platform.inference.router.workspaces import WORKSPACES

logger = logging.getLogger(__name__)

_startup_time = time.time()

# Mutable module-level singletons — set by lifespan, used by routes
_http_client: httpx.AsyncClient | None = None
registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None
_state_save_task: asyncio.Task | None = None
_notification_dispatcher = None  # type annotation deferred to TYPE_CHECKING
_notification_scheduler = None


def _init_notifications(registry: BackendRegistry) -> None:
    """Build and start the notification dispatcher + daily-summary scheduler.

    Called from ``lifespan`` only when ``NOTIFICATIONS_ENABLED=true``,
    so the notifications package never loads in environments that
    don't need it (keeps ``Dockerfile.pipeline`` lean per CLAUDE.md
    §9).

    Sequencing details that matter:

    1. **Late imports** of ``portal.platform.inference.notifications`` happen
       inside the function. The notifications package imports
       ``cluster_backends``, which is already imported at module
       top — a top-level import here would close the cycle. The
       local import breaks it.
    2. **Channels share ``_http_client``**. All five
       (Slack/Telegram/Email/Pushover/Webhook) take the pipeline's
       shared client. Giving each channel its own client would
       silently triple the connection budget — avoid.
    3. **Immediate threshold check** at line 1578 runs the
       dispatcher's threshold logic synchronously so problems
       present at startup alert immediately, not 30s later after
       the first health cycle.
    4. **Scheduler-attach-before-start**:
       ``_attach_to_pipeline`` MUST run before
       ``_notification_scheduler.start()`` because the scheduler's
       baseline snapshot reads ``_request_count`` during ``start()``.

    Mutates the module-level singletons
    ``_notification_dispatcher`` and ``_notification_scheduler``.

    Args:
        registry: The pipeline's ``BackendRegistry`` instance; the
            immediate threshold check inspects it for unhealthy
            backends.
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

    # Run threshold check on first health cycle to catch any immediate issues.
    # check_thresholds_and_alert is async; schedule it as a fire-and-forget task
    # so _init_notifications (sync) can trigger the first check without blocking.
    import asyncio as _asyncio  # noqa: PLC0415

    _asyncio.ensure_future(_notification_dispatcher.check_thresholds_and_alert(registry))

    # Schedule daily summary
    _notification_scheduler = NotificationScheduler(_notification_dispatcher)

    # Attach scheduler to pipeline metrics BEFORE starting — _init_baseline_snapshot()
    # reads _request_count during start(), so the reference must be set first.
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

    Ollama lazily loads models on first request. A cold load of an
    8B model is 10–30s (HDD) or 1–5s (SSD/NFS). Without this warmup,
    the first user request to the auto workspace eats that penalty;
    after this warmup the model is resident and the first token
    streams immediately.

    Two non-obvious choices:

    1. **Uses ``backend.models[0]``, not the workspace
       ``model_hint``.** The goal is "warm the backend's disk
       cache", not "exercise the routing logic". Whichever model
       Ollama pulls into the page cache first benefits subsequent
       loads of any other model on the same backend.
    2. **One token of output** (``num_predict: 1``). Just enough
       to force model load + a forward pass; not enough to spend
       meaningful compute.

    Failure swallowing: a non-200 response is logged at debug and
    treated as "model will load on first user request." HTTP errors
    are similarly debug-logged. A failed warmup never crashes the
    pipeline.

    Runs from ``_run_startup_warmups`` as a background task,
    parallel with ``_warmup_llm_router``.

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
        warmup_url = f"{backend.url.rstrip('/')}/api/generate"
        warmup_payload = {
            "model": backend.models[0],
            "prompt": "ok",
            "stream": False,
            "keep_alive": -1,  # int not string — Ollama 0.30.8+ rejects "-1"
            "options": {"num_predict": 1},
        }

        resp = await _http_client.post(warmup_url, json=warmup_payload)
        if resp.status_code == 200:
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

    Every request routed through the ``auto`` workspace calls
    ``_route_with_llm()``, which dispatches a generation request to
    the LLM router model BEFORE any inference happens. On a cold
    Ollama instance this adds 30–60s to the first auto request even
    when the inference model is already warm.

    This warmup fires a single minimal generate call at startup so
    the router model is resident in memory when the first user
    request arrives.

    ``keep_alive: -1`` is the load-bearing option — it tells Ollama
    to keep the router model pinned indefinitely rather than
    evicting it under memory pressure from a bigger inference
    model. Without the pin, the router would re-cold-load every
    time a large inference model displaced it.

    Skipped when ``LLM_ROUTER_ENABLED=false`` — the keyword-fallback
    router (``_detect_workspace``) handles those deployments and
    requires no warmup.

    Runs from ``_run_startup_warmups`` as a background task,
    parallel with ``_warmup_auto_model``.
    """
    if not _LLM_ROUTER_ENABLED:
        return
    if _http_client is None:
        logger.debug("LLM router warmup skipped: HTTP client not ready")
        return
    try:
        resp = await _http_client.post(
            f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
            json={
                "model": _LLM_ROUTER_MODEL,
                "prompt": "ok",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1},
            },
        )
        if resp.status_code == 200:
            logger.info("Warmup complete: LLM router model '%s' pre-loaded", _LLM_ROUTER_MODEL)
        else:
            logger.debug(
                "LLM router warmup returned HTTP %d — router will cold-load on first use",
                resp.status_code,
            )
    except Exception as e:
        logger.debug("LLM router warmup failed (non-fatal): %s", e)


async def _run_startup_warmups(registry: BackendRegistry) -> None:
    """Fire startup warmups in parallel; never raises.

    Both ``_warmup_auto_model`` and ``_warmup_llm_router`` already
    swallow their own exceptions internally. The
    ``return_exceptions=True`` on ``asyncio.gather`` is
    belt-and-suspenders — even if one of them somehow does raise
    (a future refactor regression), the other still completes and
    this function doesn't propagate.

    Launched as a background task from ``lifespan`` so pipeline
    startup is not blocked. The first user request after startup
    may arrive before warmups finish; that's fine — the warmups
    only optimize, they don't gate.

    Args:
        registry: Forwarded to ``_warmup_auto_model``.
    """
    await asyncio.gather(
        _warmup_auto_model(registry),
        _warmup_llm_router(),
        return_exceptions=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifecycle — create singletons on startup, tear down on shutdown.

    This is the single point of process-lifecycle truth for the
    pipeline. Every module-level singleton (``registry``,
    ``_http_client``, ``_request_semaphore``,
    ``_notification_dispatcher``, ``_notification_scheduler``, the
    three background tasks ``_health_task``, ``_state_save_task``,
    and the unnamed power-polling task) is created here, mutated
    only by serving code, and torn down here.

    **Startup sequence** (before ``yield``):

    1. Create ``_request_semaphore`` bounded by ``_MAX_CONCURRENT``.
    2. Pre-create the Prometheus multiproc dir (P5-FIX prevents
       worker race when ``PIPELINE_WORKERS > 1``).
    3. Create the shared ``_http_client`` with 300s body timeout
       (cold-loading 32B models can take 2–4 min; 120s caused S3-18
       streaming timeouts) and 5s connect timeout (local backends
       should bind immediately).
    4. Construct ``BackendRegistry`` (reads ``backends.yaml``).
    5. Validate ``WORKSPACES`` hints against backend models. In
       ``STRICT_HINT_VALIDATION=true`` mode, unresolvable hints
       raise ``RuntimeError`` and the container fails to start. In
       the default permissive mode, hints log warnings and the
       pipeline serves anyway — hint failures surface as silent
       fallbacks at request time.
    6. Run one synchronous health check so the first request has
       fresh health data.
    7. Load persisted metrics state from ``_STATE_FILE`` (peak only).
    8. Launch background warmup task (parallel auto-model + LLM
       router).
    9. Launch background power-polling task (graceful if daemon
       absent).
    10. If ``NOTIFICATIONS_ENABLED=true``, initialise the dispatcher
        and scheduler.
    11. Launch background health-check loop with the ``_on_health``
        callback that fires threshold alerts.
    12. Launch background state-save loop (60s interval).

    **Shutdown sequence** (after ``yield``, in roughly LIFO order):

    1. Final ``_save_state`` synchronously — must run before
       cancelling the save-loop task; a cancelled task can't await.
    2. Cancel ``_state_save_task`` and ``_health_task``.
    3. Close ``_http_client`` — after tasks so an in-flight request
       cancellation doesn't observe a closed pool.
    4. Stop the notification scheduler (if running).
    5. Close ``BackendRegistry``'s class-level health-check client.

    Args:
        app: The FastAPI app. Not used directly inside the function
            — required by the asynccontextmanager interface.

    Yields:
        Nothing. The yield separates startup from shutdown; request
        handling runs in the time the yield is suspended.
    """
    global registry, _health_task, _http_client
    global _notification_dispatcher, _notification_scheduler, _state_save_task
    _concurrency_mod._request_semaphore = asyncio.Semaphore(_concurrency_mod._MAX_CONCURRENT)
    # P5-FIX: pre-create Prometheus multiproc dir at startup so workers don't race.
    if mp_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        os.makedirs(mp_dir, exist_ok=True)
    # P1: create shared client with a connection pool sized for concurrent inference
    # Safety-net timeout: per-request timeouts in _try_non_streaming are the
    # operative control (registry.request_timeout + reasoning modifier).
    # This client-level value is the absolute upper bound — raise to 600s so
    # reasoning workspaces (which get 600s per-request) are never clamped by it.
    # connect stays 5s — local backends should bind immediately.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(600.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
        ),
    )
    # Propagate shared client to the routing module (needed by _route_with_llm)
    import portal.platform.inference.router.routing as _routing_mod

    _routing_mod._http_client = _http_client
    _streaming_mod._http_client = _http_client
    registry = BackendRegistry()
    # Push registry + _http_client to modules that cannot capture them at import time.
    # Same pattern as _routing_mod/_streaming_mod above.
    import portal.platform.inference.router.handlers as _handlers_mod  # noqa: PLC0415
    import portal.platform.inference.router.non_streaming as _non_streaming_mod  # noqa: PLC0415
    import portal.platform.inference.router.validation as _validation_mod  # noqa: PLC0415

    _handlers_mod.registry = registry
    _non_streaming_mod.registry = registry
    _non_streaming_mod._http_client = _http_client
    _validation_mod.registry = registry
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
            # "-ctx" only appears in our derived-tag convention (e.g. -ctx32k),
            # so a simple substring check is robust without a brittle suffix list.
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
    # Pre-warm: load the inference model AND the LLM router model in parallel so
    # the first 'auto' request is not penalized by two sequential cold-loads:
    # (1) router model classification (~30-60s if cold) then
    # (2) inference model generation (~10-30s if cold).
    # Both fire simultaneously as background tasks — startup is not blocked.
    asyncio.create_task(_run_startup_warmups(registry))
    # Power metrics polling (M6-T02) — graceful if daemon not running
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
        _health_task = asyncio.create_task(registry.start_health_loop(on_health_check=_on_health))
        _state_save_task = asyncio.create_task(_state_save_loop(interval=60))

    yield

    if _in_test_mode:
        return

    # Final state save on shutdown
    _save_state()
    if _state_save_task:
        _state_save_task.cancel()
    if _health_task:
        _health_task.cancel()
    if _http_client:
        await _http_client.aclose()
    if _notification_scheduler:
        _notification_scheduler.stop()
    await BackendRegistry.close_health_client()
