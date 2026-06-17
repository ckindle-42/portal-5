"""Portal 5 Pipeline — OpenAI-compatible router connecting Open WebUI to local backends.

This is the single FastAPI app that serves ``/v1/models`` and
``/v1/chat/completions`` for Open WebUI. Every Open WebUI request flows
through this file before reaching an Ollama backend.

**Module homes (after TASK_ROUTER_DECOMP_REQUESTSLOT_V1):**

The pipeline code is split across these modules. This file is the facade that
re-exports their public symbols so external import paths are unchanged.

+---------------------------+---------------------------------------------+
| Module                    | Owns                                        |
+===========================+=============================================+
| router/concurrency.py     | Three semaphores + ``RequestSlot``          |
+---------------------------+---------------------------------------------+
| router/metrics.py         | ``CollectorRegistry`` + all collectors      |
+---------------------------+---------------------------------------------+
| router/state.py           | State persistence + per-event recorders     |
+---------------------------+---------------------------------------------+
| router/power.py           | powermetrics polling, energy/cost           |
+---------------------------+---------------------------------------------+
| router/routing.py         | LLM router + keyword workspace detection    |
+---------------------------+---------------------------------------------+
| router/streaming.py       | SSE streaming: ``_stream_from_backend_*``,  |
|                           | ``_stream_with_preamble``,                  |
|                           | ``_stream_with_tool_loop`` (+impl),         |
|                           | ``_json_completion_to_sse``,                |
|                           | ``_http_client``, ``_SHOW_ROUTING_STATUS``  |
+---------------------------+---------------------------------------------+
| router/tools.py           | MCP tool dispatch (``_dispatch_tool_call``) |
+---------------------------+---------------------------------------------+
| router/workspaces.py      | ``WORKSPACES``, persona map, tool helpers   |
+---------------------------+---------------------------------------------+
| router_pipe.py (this file)| FastAPI ``app``, all ``@app`` routes,       |
|                           | option injection, warmups, lifespan, auth   |
+---------------------------+---------------------------------------------+

**File organisation (~2050 LOC):**

* L1–L260:    Module-level state (``registry``, ``_http_client``), env config.
* L261–L630:  Startup helpers (``_validate_workspace_hints``,
              ``_init_notifications``, warmups).
* L631–L790:  ``lifespan`` context manager and ``app`` instance.
* L791–L1490: Route handlers (``/health``, ``/metrics``, ``/v1/models``,
              ``/v1/chat/completions``, admin).
* L1490+:     ``_try_non_streaming`` + ``chat_completions`` handler
              (routing, semaphore acquisition via ``RequestSlot``, streaming
              dispatch delegated to ``router/streaming.py``).

**Three things to know before editing:**

1. **State persistence has delta semantics**. ``_save_state`` reads the
   file, adds the in-memory accumulators, writes atomically, then
   **resets the in-memory accumulators to zero**. The reset is critical
   — removing it inflates metrics by ``saves_per_day × workers`` on
   every restart. See ``_save_state`` and ``_load_state``.
2. **Module-level singletons are intentional**. ``registry``,
   ``_http_client`` (this file — used by warmups and ``_try_non_streaming``),
   ``router.streaming._http_client`` (injected from this file's lifespan —
   used by all streaming generators), ``_notification_dispatcher``, and
   the Prometheus metric objects are all process-global. ``lifespan``
   creates them on startup and cancels/closes them on shutdown. Tests
   stub them via direct module attribute assignment.
3. **Lazy imports protect the lean Dockerfile**. ``notifications`` is
   imported under ``TYPE_CHECKING`` for type hints and lazily inside
   ``_init_notifications`` for runtime use, so the channels package
   (and its dependencies like ``aiosmtplib``, ``APScheduler``) only
   loads when ``NOTIFICATIONS_ENABLED=true``. Same pattern for
   ``portal_pipeline.tool_registry`` inside ``_try_non_streaming``.

**Knobs (env-overridable):**

* ``MAX_REQUEST_BYTES`` (4 MB default) — request body size cap.
* ``METRICS_STATE_FILE`` (``/app/data/metrics_state.json``).
* ``LOG_LEVEL`` (``INFO``).
* ``ELECTRICITY_RATE_USD_PER_KWH`` (``0.15``) for cost-attribution metrics.
* ``PROMETHEUS_MULTIPROC_DIR`` — must be set when ``PIPELINE_WORKERS > 1``;
  ``__main__.py`` creates one if absent.
* ``STRICT_HINT_VALIDATION`` — when ``true``, an unresolvable workspace
  hint at startup raises rather than warns. See ``lifespan``.
* ``NOTIFICATIONS_ENABLED`` — gates the lazy import + setup of the
  notifications subsystem.
* ``SHOW_ROUTING_STATUS`` — when ``true``, every streaming response
  prepends ``⚡ workspace → model``. Defined in ``router/streaming.py``.
"""

from __future__ import annotations

import asyncio
import hmac
import importlib.metadata
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CollectorRegistry, generate_latest

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)
# Ensure the logger has its own stderr handler — survives uvicorn multi-worker fork().
# Without this, logger.info() output is silently dropped when workers > 1 because
# logging.basicConfig() from __main__.py doesn't propagate to forked child processes.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_handler)
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, _log_level, logging.INFO))

from portal_pipeline.router.state import (  # noqa: E402, F401  (facade re-export)
    _STATE_FILE,
    _load_state,
    _peak_concurrent,
    _persona_usage_raw,
    _record_error,
    _record_persona,
    _req_count_by_error,
    _req_count_by_model,
    _request_count,
    _request_tps_count,
    _save_state,
    _state_save_loop,
    _total_input_tokens,
    _total_output_tokens,
    _total_tps,
)

_startup_time = time.time()

# Maximum request body size (default 4MB)
_MAX_REQUEST_BYTES: int = int(os.environ.get("MAX_REQUEST_BYTES", str(4 * 1024 * 1024)))

# Background task that periodically persists state to disk
_state_save_task: asyncio.Task | None = None


# Notification subsystem handles operational alerts and daily summaries
_notification_dispatcher: NotificationDispatcher | None = None
_notification_scheduler: NotificationScheduler | None = None

# Cached multiprocess collector registry — rebuilt only when the process
# directory changes, not on every /metrics scrape.
_mp_registry_cache: CollectorRegistry | None = None
_mp_registry_dir_cache: str | None = None

# ── Concurrency machinery (extracted to portal_pipeline.router.concurrency) ──
# Mutable singletons (_request_semaphore, _workspace_semaphores, etc.) live
# there and are NOT re-exported here (A4). Functions and limits are re-exported
# so existing callers compile unchanged.
import portal_pipeline.router.concurrency as _concurrency_mod  # noqa: E402
import portal_pipeline.router.streaming as _streaming_mod  # noqa: E402
from portal_pipeline.router.concurrency import (  # noqa: E402, F401  (facade re-export)
    _MAX_CONCURRENT,
    _SEMAPHORE_TIMEOUT,
    RequestSlot,
    _acquire_api_key_sem,
    _acquire_workspace_sem,
    _api_key_limit,
    _get_workspace_concurrency_limit,
)
from portal_pipeline.router.metrics import (  # noqa: E402, F401  (facade re-export)
    _REGISTRY,
    _concurrent_requests,
    _energy_by_workspace_ws,
    _energy_consumed_ws_total,
    _errors_total,
    _input_tokens,
    _output_tokens,
    _persona_usage,
    _power_ane_watts,
    _power_avg_1min_watts,
    _power_cpu_watts,
    _power_current_watts,
    _power_dram_watts,
    _power_gpu_watts,
    _record_response_time,
    _request_energy_ws,
    _requests_by_model,
    _requests_total,
    _response_time_seconds,
    _tokens_per_second,
    _tool_call_duration,
    _tool_call_errors,
    _tool_calls_total,
    _tool_loop_hops,
    _tool_workspace_strip,
    _total_response_time_ms,  # noqa: F401
    _workspace_semaphore_busy_total,
    _workspace_semaphore_busy_total_metric,
)
from portal_pipeline.router.power import (  # noqa: E402, F401  (facade re-export)
    _POWERMETRICS_SOCKET,
    ELECTRICITY_RATE_USD_PER_KWH,
    _power_polling_loop,
    _record_usage,
    watts_seconds_to_cost_usd,
)
from portal_pipeline.router.routing import (  # noqa: E402, F401  (facade re-export)
    _CODING_KEYWORDS,
    _LLM_ROUTER_ENABLED,
    _LLM_ROUTER_MODEL,
    _LLM_ROUTER_OLLAMA_URL,
    _SPL_KEYWORDS,
    _VALID_WORKSPACE_IDS,
    _build_router_prompt,
    _detect_workspace,
    _load_routing_config,
    _route_with_llm,
)
from portal_pipeline.router.streaming import (  # noqa: E402, F401  (facade re-export)
    _json_completion_to_sse,
    _stream_from_backend_guarded,
    _stream_with_chain,
    _stream_with_preamble,
    _stream_with_secondary_chain,
    _stream_with_tool_loop,
    _stream_with_tool_loop_impl,
)
from portal_pipeline.router.tools import (  # noqa: E402, F401  (facade re-export)
    _dispatch_tool_call,
)

# ── Workspace configuration (extracted to portal_pipeline.router.workspaces) ─
# WORKSPACES, _PERSONA_MAP, persona helpers, workspace tool helpers now live in
# portal_pipeline/router/workspaces.py. Imported here so existing code in this
# file works unchanged.
from portal_pipeline.router.workspaces import (  # noqa: E402
    _PERSONA_MAP,
    MAX_TOOL_HOPS,  # noqa: F401 — re-exported for tests and external callers
    WORKSPACES,
    _resolve_persona_tools,
    _workspace_tools,  # noqa: F401 — re-exported for tests and external callers
)

_raw_api_key = os.environ.get("PIPELINE_API_KEY", "")
if not _raw_api_key:
    import sys

    print(
        "FATAL: PIPELINE_API_KEY is not set. "
        "Set PIPELINE_API_KEY in .env before starting the pipeline. "
        "Example: PIPELINE_API_KEY=$(openssl rand -hex 32)",
        file=sys.stderr,
    )
    sys.exit(1)
PIPELINE_API_KEY: str = _raw_api_key

# ── Ollama per-request TTFT tuning ────────────────────────────────────────────
# keep_alive: how long Ollama keeps the model loaded after a request completes.
#   "-1" = never unload. Eliminates the 10-30s cold-start on the next request.
#   Native Ollama default is ~5 min; docker-ollama sets OLLAMA_KEEP_ALIVE=24h
#   server-wide, but native installs don't get that. Injecting it per-request
#   covers both cases reliably.
# num_batch: tokens processed per prompt-evaluation pass (Ollama default: 512).
#   2048 = 4× throughput during prefill — cuts TTFT on long conversation histories.
#   Safe upper bound: match your model's training context / 8. 2048 fits all
#   models in the catalog without exceeding their attention window.
_OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE_REQUEST", "-1")
try:
    _OLLAMA_NUM_BATCH: int = int(os.environ.get("OLLAMA_NUM_BATCH", "2048"))
except ValueError:
    _OLLAMA_NUM_BATCH = 2048
    logger.warning(
        "Invalid OLLAMA_NUM_BATCH value — must be an integer. Using default: %d", _OLLAMA_NUM_BATCH
    )

registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None

# Shared httpx client for backend inference — P1: connection pool reused across
# all streaming and completion requests, avoiding TCP/TLS handshake overhead.
_http_client: httpx.AsyncClient | None = None


def _validate_workspace_hints(registry: BackendRegistry) -> list[str]:
    """Verify every ``WORKSPACES`` ``model_hint`` resolves.

    Run once at startup from ``lifespan``. For each workspace,
    ``model_hint`` (Ollama) must be in some backend's ``models``
    list, AND that backend must be in one of the workspace's
    routing groups per ``config/backends.yaml``.

    Returns the list of failures rather than raising. The caller
    decides what to do: ``lifespan`` raises ``RuntimeError`` under
    ``STRICT_HINT_VALIDATION=true``, or logs warnings and starts
    anyway in permissive mode. Returning a list lets the operator
    see every misconfigured workspace in one startup pass instead
    of fail-on-first.

    Without this check, a typo in ``WORKSPACES`` produces silent
    fallback at request time — the workspace serves, but with a
    different model than intended.

    Args:
        registry: The pipeline's ``BackendRegistry``, already
            loaded from YAML.

    Returns:
        Human-readable error strings, one per failed hint. Empty
        list means all hints resolve.
    """
    group_models: dict[str, set[str]] = {}
    for be in registry.list_backends():
        group_models.setdefault(be.group, set()).update(be.models)

    errors: list[str] = []
    for ws_id, ws_cfg in WORKSPACES.items():
        groups = registry.workspace_routes.get(ws_id, [])
        ollama_available: set[str] = set()
        for g in groups:
            ollama_available |= group_models.get(g, set())

        hint = ws_cfg.get("model_hint")
        if not hint:
            continue
        available = ollama_available
        if hint not in available:
            errors.append(
                f"workspace={ws_id!r} model_hint={hint!r} "
                f"not in any backend's models for groups={groups}. "
                f"Add it to config/backends.yaml or correct the WORKSPACES hint."
            )
    return errors


def _model_supports_tools(model_id: str) -> bool:
    """Return whether ``model_id`` declares ``supports_tools: true`` in its metadata.

    Delegates to ``BackendRegistry.model_supports_tools`` for O(1) lookup
    against the pre-built tool-support map built during ``_load_config``.

    Args:
        model_id: Concrete model id (e.g. ``"qwen3-coder:30b"``).
            Unknown models return ``False``.

    Returns:
        ``True`` if the model's metadata explicitly declares
        ``supports_tools: true``, ``False`` otherwise.
    """
    if registry is None or not model_id:
        return False
    return registry.model_supports_tools(model_id)


def _inject_ollama_options(body: dict, workspace_id: str = "") -> dict:
    """Add Ollama-specific tuning to the outgoing request body. Returns a copy.

    Only called for backends with ``type == "ollama"``. vLLM
    does not recognise these fields and would either error or silently
    ignore them.

    Body is copied at function entry — the original is never
    mutated. The ``options`` sub-dict is deep-copied so workspace
    injections never pollute the caller's original options dict.

    Two categories of injection:

    **Global tuning** (applies to every Ollama request):

    * ``keep_alive`` (top-level): set to ``-1`` to prevent model
      unloading between requests. Eliminates the 10–30s cold-load
      cost on the next request to the same model. Native Ollama
      default is ~5 min; ``OLLAMA_KEEP_ALIVE`` env (server-wide)
      handles the Docker case but not native installs. Per-request
      injection covers both reliably.
    * ``num_batch`` (under ``options``): set to 2048 (Ollama
      default is 512). Quadruples prompt-evaluation throughput,
      cutting TTFT on long conversation histories. 2048 fits every
      model in the catalog without exceeding attention windows.

    **Workspace-driven** (only when workspace declares the field):

    * ``num_ctx`` from ``context_limit`` — big-model agentic
      workspaces need explicit context caps to bound memory use.
     * ``max_tokens`` from ``predict_limit`` — research/reasoning
       workspaces cap output tokens to prevent DeepSeek-R1 CoT
       exhaustion. Mapped to top-level ``max_tokens`` (OpenAI
       standard); verified against Ollama 0.30.7 where
       ``options.num_predict`` is ignored by
       ``/v1/chat/completions``.

    All injections use ``setdefault`` so caller-supplied values
    (e.g. Open WebUI passing its own ``keep_alive``) win. The
    pipeline never overrides what Open WebUI explicitly sets.

    Args:
        body: Outgoing request body. Not mutated.
        workspace_id: Workspace key; ``context_limit`` and
            ``predict_limit`` are looked up here. Empty string
            skips workspace-driven injection.

    Returns:
        Shallow copy of ``body`` with injections applied.
    """
    body = dict(body)
    # Deep-copy options to prevent mutating caller's dict
    body["options"] = dict(body.get("options") or {})
    ws_cfg_local = WORKSPACES.get(workspace_id, {}) if workspace_id else {}
    # Big-model context cap (P5-BIG-001): workspace context_limit tracked here as self-healing; Ollama /v1 ignores options.num_ctx (VERIFY-1, 2026-06). Set 'PARAMETER num_ctx N' in the model's Modelfile or OLLAMA_CONTEXT_LENGTH env to enforce.
    ctx_limit = ws_cfg_local.get("context_limit")
    if ctx_limit:
        body["options"].setdefault("num_ctx", ctx_limit)
    # Research/reasoning workspaces: cap output tokens to prevent CoT exhaustion.
    # Map predict_limit to top-level max_tokens; verified against Ollama
    # 0.30.7 where options.num_predict is ignored by /v1/chat/completions.
    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit:
        body.setdefault("max_tokens", predict_limit)
    # Per-workspace keep_alive override: bench workspaces use "5m" (short-lived
    # bench models shouldn't pin memory between runs); big-q8 quality lanes use
    # "10m" (long enough to absorb back-to-back queries without reload cost, but
    # not forever — a 35 GB q8 pinned by "-1" evicts the rest of the fleet).
    # Falls back to the global _OLLAMA_KEEP_ALIVE ("-1") for all other workspaces.
    # IMPORTANT: workspace-declared keep_alive is a hard override — use direct
    # assignment, not setdefault. OWUI sends its own keep_alive but doesn't know
    # about bench workspace model lifecycle; letting OWUI win here causes large
    # models to stay loaded indefinitely, blocking subsequent bench runs.
    ws_keep_alive = ws_cfg_local.get("keep_alive")
    if ws_keep_alive is not None:
        body["keep_alive"] = ws_keep_alive
    else:
        body.setdefault("keep_alive", _OLLAMA_KEEP_ALIVE)
    body["options"].setdefault("num_batch", _OLLAMA_NUM_BATCH)
    # Per-workspace thinking control: "think": false disables extended thinking
    # for Qwen3/similar models that support it. Prevents token-budget exhaustion
    # in thinking mode where the model burns all tokens in <think> and produces
    # empty output. Set in workspace config as {"think": false}.
    ws_think = ws_cfg_local.get("think")
    if ws_think is not None:
        body.setdefault("think", ws_think)
    return body


def _init_notifications(registry: BackendRegistry) -> None:
    """Build and start the notification dispatcher + daily-summary scheduler.

    Called from ``lifespan`` only when ``NOTIFICATIONS_ENABLED=true``,
    so the notifications package never loads in environments that
    don't need it (keeps ``Dockerfile.pipeline`` lean per CLAUDE.md
    §9).

    Sequencing details that matter:

    1. **Late imports** of ``portal_pipeline.notifications`` happen
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
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler
    from portal_pipeline.notifications.channels import (
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
    from portal_pipeline.notifications import scheduler as notif_scheduler

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
            "keep_alive": "-1",
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
    import portal_pipeline.router.routing as _routing_mod

    _routing_mod._http_client = _http_client
    _streaming_mod._http_client = _http_client
    registry = BackendRegistry()
    hint_errors = _validate_workspace_hints(registry)
    if hint_errors:
        for e in hint_errors:
            logger.error("HINT VALIDATION: %s", e)
        if os.environ.get("STRICT_HINT_VALIDATION", "false").lower() in ("true", "1", "yes"):
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

    async def _on_health(r: BackendRegistry) -> None:
        """Callback for the health-check loop: dispatch threshold alerts."""
        if _notification_dispatcher:
            await _notification_dispatcher.check_thresholds_and_alert(r)

    _health_task = asyncio.create_task(registry.start_health_loop(on_health_check=_on_health))

    # Background task: persist metrics state to disk every 60s
    _state_save_task = asyncio.create_task(_state_save_loop(interval=60))

    yield

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


try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"
app = FastAPI(title="Portal Pipeline", version=_PKG_VERSION, lifespan=lifespan)


def _verify_key(authorization: str | None) -> None:
    """Validate the Authorization header against ``PIPELINE_API_KEY``.

    Uses ``hmac.compare_digest`` for constant-time comparison —
    naive ``==`` is vulnerable to timing attacks that can probe a
    remote API key byte-by-byte by measuring response latency.

    Accepts both ``"Bearer <key>"`` and bare ``"<key>"`` forms;
    ``removeprefix`` is a no-op if the prefix isn't present.

    Args:
        authorization: Raw ``Authorization`` header value, or
            ``None`` when the header is absent.

    Raises:
        HTTPException: 401 when the header is missing or the key
            doesn't match.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PIPELINE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
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


@app.get("/health/all")
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
    from portal_pipeline.tool_registry import MCP_SERVERS

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
            os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
            "/api/tags",
        )
        mcp_probes = {
            f"mcp_{server_id}": _probe(url, "/health") for server_id, url in MCP_SERVERS.items()
        }
        mcp_results_list = await asyncio.gather(*mcp_probes.values(), return_exceptions=True)
        mcp_results = dict(zip(mcp_probes.keys(), mcp_results_list, strict=True))

    return {**pipeline_result, "ollama": ollama_result, **mcp_results}


PORTAL5_ADMIN_KEY = os.environ.get("PORTAL5_ADMIN_KEY", os.environ.get("PIPELINE_API_KEY", ""))


def _verify_admin_key(authorization: str | None) -> None:
    """Validate Authorization against ``PORTAL5_ADMIN_KEY``.

    Same contract as ``_verify_key`` but checks the admin key for
    write-side endpoints (currently ``/admin/refresh-tools``).

    ``PORTAL5_ADMIN_KEY`` defaults to ``PIPELINE_API_KEY`` if unset
    (line 1853), so single-user / single-key deployments don't have
    to set two env vars. Production with separated concerns sets
    them differently.

    Constant-time comparison via ``hmac.compare_digest``.

    Args:
        authorization: Raw ``Authorization`` header value.

    Raises:
        HTTPException: 401 when the header is missing or the key
            doesn't match.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PORTAL5_ADMIN_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin key")


@app.post("/admin/refresh-tools")
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
    from portal_pipeline.tool_registry import tool_registry

    n = await tool_registry.refresh(force=True)
    return {"refreshed": True, "tools_registered": n, "names": tool_registry.list_tool_names()}


@app.post("/notifications/test")
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

    from portal_pipeline.notifications.events import AlertEvent, EventType, SummaryEvent

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
        timestamp=datetime.now(timezone.utc),
        report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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


@app.get("/metrics")
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
            from prometheus_client import multiprocess

            _mp_registry_cache = CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
        prometheus_output = generate_latest(_mp_registry_cache).decode("utf-8")
    else:
        prometheus_output = generate_latest(_REGISTRY).decode("utf-8")
    return PlainTextResponse("\n".join(lines) + "\n" + prometheus_output)


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)) -> dict:
    """GET /v1/models — OpenAI-compatible model catalogue.

    Returns one entry per ``WORKSPACES`` key. Per CLAUDE.md, Portal
    5 is Open WebUI's sole model source — OWUI sees workspaces as
    models, never the underlying Ollama models. The user
    picks a workspace in the OWUI model picker; that selection
    becomes the ``model`` field on the chat-completions request
    and is what ``chat_completions`` routes on.

    Per-entry fields:

    * ``id`` — workspace key (e.g. ``"auto-coding"``).
    * ``name`` — human display name from ``WORKSPACES``.
    * ``category`` — OWUI grouping. Derived from the workspace id
      (``bench-*`` → ``"benchmark"``; ``auto-X`` → ``"X"``; else
      the id itself), or explicitly overridden by ``category:`` in
      the workspace's ``WORKSPACES`` entry.
    * ``tags`` — non-standard OWUI extension; defaults to
      ``[category]`` if not set in ``WORKSPACES``.
    * ``tools`` — the workspace's default tool whitelist (the
      pipeline applies persona-level overrides at request time).
    * ``is_benchmark`` — convenience flag for OWUI UI; ``True``
      for ``bench-*`` workspaces.

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
    return {"object": "list", "data": models}


@app.get("/v1/backends")
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
        if _tools_arr:
            req_body["tools"] = _tools_arr
            req_body.setdefault("tool_choice", "auto")
            logger.info(
                "Tool-call (non-stream): workspace=%s persona=%s model=%s exposed %d tools",
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

            if _ns_tool_calls and _ns_tools:
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


@app.post("/v1/chat/completions")
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

    :class:`~portal_pipeline.router.concurrency.RequestSlot` owns the three
    semaphores and the concurrent-requests gauge for the request's lifetime.

    Raises:
        HTTPException: 400 (invalid JSON body), 401 (bad auth),
            413 (body too large), 429 (semaphore timeout — global,
            per-key, or per-workspace), 502 (all backends failed
            non-streaming), 503 (registry not initialised; no
            healthy backends).
    """
    _verify_key(authorization)

    content_length = int(request.headers.get("content-length", 0))
    if content_length > _MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {_MAX_REQUEST_BYTES // 1024 // 1024}MB)",
        )

    slot = RequestSlot()
    await slot.acquire_global()

    # Per-API-key semaphore (M6-T06)
    _api_key_raw = authorization.removeprefix("Bearer ").strip() if authorization else ""
    await slot.acquire_api_key(_api_key_raw)

    workspace_id: str = "unknown"
    start_time = time.monotonic()
    try:
        if registry is None:
            raise HTTPException(status_code=503, detail="Backend registry not initialised")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        workspace_id = body.get("model") or "auto"
        # Resolve persona slug → workspace_model (e.g. "dailydriver" → "auto-daily")
        if workspace_id not in WORKSPACES:
            _persona_ws = _PERSONA_MAP.get(workspace_id, {}).get("workspace_model")
            if _persona_ws and _persona_ws in WORKSPACES:
                workspace_id = _persona_ws
        stream = body.get("stream", False)

        # Content-aware routing for 'auto' workspace
        # Primary path: LLM-based intent classification (P5-FUT-006).
        # Fallback: weighted keyword scoring (_detect_workspace).
        # This lets users ask security/coding/reasoning questions through 'auto'
        # and get the right specialist model without manually switching workspaces.
        if workspace_id == "auto":
            messages = body.get("messages", [])
            # LLM router first — semantic intent, ~100ms, falls back on timeout/low confidence
            detected = await _route_with_llm(messages)
            if detected:
                logger.info(
                    "Auto-routing (LLM): detected workspace '%s' from message content", detected
                )
                workspace_id = detected
            else:
                # Keyword fallback — deterministic, zero-latency
                detected = _detect_workspace(messages)
                if detected:
                    logger.info(
                        "Auto-routing (keywords): detected workspace '%s' from message content",
                        detected,
                    )
                    workspace_id = detected

        # auto-vision text-only fallback: vision-language models (qwen3-vl:32b, Gemma 4)
        # return empty content when no image is provided. Detect absence of image_url
        # content parts and reroute to auto-reasoning for text-only queries, so users
        # always receive a meaningful response from the auto-vision workspace.
        if workspace_id == "auto-vision":
            messages = body.get("messages", [])
            has_image = any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for msg in messages
                for part in (msg.get("content", []) if isinstance(msg.get("content"), list) else [])
            )
            if not has_image:
                logger.info(
                    "auto-vision: no image_url in request — rerouting to auto-reasoning "
                    "with vision system context injected"
                )
                workspace_id = "auto-reasoning"
                # Inject a system message so the reasoning model responds with
                # vision-domain vocabulary (image, visual, diagram, detect, etc.)
                # This ensures auto-vision text-only queries return domain-relevant
                # responses describing visual analysis capabilities rather than
                # generic reasoning answers.
                messages = body.get("messages", [])
                has_system = any(m.get("role") == "system" for m in messages)
                if not has_system:
                    vision_system = {
                        "role": "system",
                        "content": (
                            "You are a vision AI assistant. When answering questions about "
                            "your capabilities, focus on visual analysis tasks: image "
                            "understanding, diagram interpretation, visual element detection, "
                            "object recognition, scene description, chart reading, and "
                            "multimodal reasoning from images and diagrams."
                        ),
                    }
                    body = {**body, "messages": [vision_system] + messages}

        # Workspace-level system_prompt_append — appended to existing system message
        # or injected as a new system message if none is present.
        _prompt_append = WORKSPACES.get(workspace_id, {}).get("system_prompt_append", "")
        if _prompt_append:
            messages = body.get("messages", [])
            sys_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), None)
            if sys_idx is not None:
                updated = dict(messages[sys_idx])
                updated["content"] = updated.get("content", "") + _prompt_append
                messages = list(messages)
                messages[sys_idx] = updated
                body = {**body, "messages": messages}
            else:
                body = {
                    **body,
                    "messages": [{"role": "system", "content": _prompt_append}] + messages,
                }

        # File attachment injection — OWUI sends uploaded files in body["files"] but
        # does not include them in the messages array. Inject a note into the last
        # user message so the model can reference audio/document file IDs in tool calls.
        _attached_files = body.get("files") or []
        if _attached_files:
            _file_notes: list[str] = []
            for _f in _attached_files:
                _fid = _f.get("id") or ""
                _fname = _f.get("name") or _f.get("filename") or ""
                _ftype = _f.get("type") or _f.get("meta", {}).get("content_type") or ""
                if _fid or _fname:
                    _file_notes.append(
                        f"[Attached file — id: {_fid!r}, name: {_fname!r}, type: {_ftype!r}]"
                    )
            if _file_notes:
                _msgs = list(body.get("messages", []))
                _note = "\n".join(_file_notes)
                # Append to last user message so the model sees it in context
                for _i in range(len(_msgs) - 1, -1, -1):
                    if _msgs[_i].get("role") == "user":
                        _c = _msgs[_i].get("content", "")
                        if isinstance(_c, str):
                            _msgs[_i] = {**_msgs[_i], "content": _c + "\n\n" + _note}
                        elif isinstance(_c, list):
                            _msgs[_i] = {
                                **_msgs[_i],
                                "content": _c + [{"type": "text", "text": _note}],
                            }
                        break
                body = {**body, "messages": _msgs}
                logger.debug("Injected %d file reference(s) into messages", len(_file_notes))

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

        if not stream:
            # Non-streaming: try each backend in priority order until one succeeds.
            # Model hint is enforced (skip backends without the hinted model) for
            # all but the last candidate, where we accept any model as fallback.
            # Log the routing decision here — mirrors the streaming-path log at line ~1443
            # so that S3-19 log validation and operational log parsing work regardless
            # of whether the client requested streaming or non-streaming mode.
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
                        route_header.split(";")[2]
                        if len(route_header.split(";")) > 2
                        else "unknown"
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
                            primary_data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
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

        # Streaming: try first backend. If the stream yields an error chunk early,
        # fall back to non-streaming with remaining candidates.
        backend = candidates[0]
        ws_cfg = WORKSPACES.get(workspace_id, {})
        model_hint = ws_cfg.get("model_hint", "")
        _chain = ws_cfg.get("chain") or []
        _secondary_model = ws_cfg.get("secondary_model", "")
        _tertiary_model = ws_cfg.get("tertiary_model", "")

        # Pick target model from Ollama hint
        if model_hint:
            if model_hint in backend.models:
                target_model = model_hint
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
        else:
            if not backend.models:
                logger.warning(
                    "Backend %s has empty models list — cannot resolve. Skipping.",
                    backend.id,
                )
                raise HTTPException(
                    502, f"Backend {backend.id} has an empty models list — fix config/backends.yaml"
                )
            target_model = backend.models[0]

        logger.info(
            "Stream routing: workspace=%s backend=%s model=%s (1/%d candidates)",
            workspace_id,
            backend.id,
            target_model,
            len(candidates),
        )

        backend_body = {**body, "model": target_model}

        # Inject keep_alive + num_batch for Ollama.
        if backend.type == "ollama":
            backend_body = _inject_ollama_options(backend_body, workspace_id)

        # Resolve effective tool list for this request (M2)
        persona_data = _PERSONA_MAP.get(persona, {})
        effective_tools = _resolve_persona_tools(persona_data, workspace_id)
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
        _has_tools = bool(effective_tools) and backend_supports_tools
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

        if _has_tools:
            from portal_pipeline.tool_registry import tool_registry

            await tool_registry.refresh()
            tools_array = tool_registry.get_openai_tools(effective_tools)
            if tools_array:
                backend_body["tools"] = tools_array
                backend_body["tool_choice"] = backend_body.get("tool_choice", "auto")
                logger.info(
                    "Tool-call: workspace=%s persona=%s exposed %d tools",
                    workspace_id,
                    persona,
                    len(tools_array),
                )
            else:
                _has_tools = False

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
            if _has_tools:
                _stream_fn = _stream_with_tool_loop(
                    backend.chat_url,
                    backend_body,
                    slot.detach(),
                    workspace_id,
                    target_model,
                    persona,
                    set(effective_tools),
                    start_time,
                )
            elif _chain:
                _stream_fn = _stream_with_chain(
                    backend.chat_url,
                    backend_body,
                    slot.detach(),
                    workspace_id=workspace_id,
                    primary_model=target_model,
                    chain=_chain,
                    start_time=start_time,
                    persona=persona,
                )
            elif _secondary_model:
                _stream_fn = _stream_with_secondary_chain(
                    backend.chat_url,
                    backend_body,
                    slot.detach(),
                    workspace_id=workspace_id,
                    model=target_model,
                    secondary_model=_secondary_model,
                    tertiary_model=_tertiary_model,
                    start_time=start_time,
                )
            else:
                _stream_fn = _stream_with_preamble(
                    backend.chat_url,
                    backend_body,
                    slot.detach(),
                    workspace_id=workspace_id,
                    model=target_model,
                    start_time=start_time,
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

        async def _stream_or_fallback() -> AsyncIterator[bytes]:
            """Streaming wrapper for the multi-candidate path; falls back to non-streaming.

            Nested closure inside ``chat_completions`` because it closes
            over ~13 locals from the request handler (backend, body,
            semaphores, target_model, etc.). Lifting it to module scope
            would require parameter-passing every one of those — the
            closure is the right abstraction here.

            Behaviour:

            1. Stream from ``backend`` (first candidate) via either
               ``_stream_with_tool_loop`` or ``_stream_with_preamble``
               depending on ``_has_tools``.
            2. Detect failure by either:
               - Substring check ``b'"error"' in chunk`` (the explicit
                 error envelopes emitted by ``_stream_from_backend_guarded``).
                 False-positive risk if a model's content happens to include
                 ``"error"`` literally — accepted, because that chunk would
                 also contain real content and the fallback then produces
                 the same answer the streaming variant would have, just
                 slower.
               - Exception from the inner generator.
            3. On failure, retry the **same backend** in non-streaming
               via ``_try_non_streaming`` with ``enforce_hint=True``.
            4. If that succeeds, wrap the JSON response as SSE (role chunk,
               content chunk, per-tool-call chunks, done chunk, ``[DONE]``)
               and yield. OWUI cannot tolerate a Content-Type switch
               mid-stream — once we've started SSE we must keep emitting SSE.
            5. If that also fails, try **remaining** candidates non-streaming.
               The ``_try_non_streaming`` call iterates all remaining
               candidates in order; fixed in
               ``TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS``.

            Semaphore release is delegated to the streaming function
            (``_stream_with_tool_loop`` or ``_stream_with_preamble``) via
            their own ``try/finally``. This closure does not own
            semaphores.
            """
            stream_failed = False
            _error_buffer = None
            try:
                if _has_tools:
                    _inner_stream = _stream_with_tool_loop(
                        backend.chat_url,
                        backend_body,
                        slot.detach(),
                        workspace_id,
                        target_model,
                        persona,
                        set(effective_tools),
                        start_time,
                    )
                elif _chain:
                    _inner_stream = _stream_with_chain(
                        backend.chat_url,
                        backend_body,
                        slot.detach(),
                        workspace_id=workspace_id,
                        primary_model=target_model,
                        chain=_chain,
                        start_time=start_time,
                        persona=persona,
                    )
                elif _secondary_model:
                    _inner_stream = _stream_with_secondary_chain(
                        backend.chat_url,
                        backend_body,
                        slot.detach(),
                        workspace_id=workspace_id,
                        model=target_model,
                        secondary_model=_secondary_model,
                        tertiary_model=_tertiary_model,
                        start_time=start_time,
                    )
                else:
                    _inner_stream = _stream_with_preamble(
                        backend.chat_url,
                        backend_body,
                        slot.detach(),
                        workspace_id=workspace_id,
                        model=target_model,
                        start_time=start_time,
                    )
                async for chunk in _inner_stream:
                    if b'"error"' in chunk:
                        stream_failed = True
                        _error_buffer = chunk
                        continue
                    yield chunk
            except Exception:
                stream_failed = True

            if stream_failed:
                logger.info(
                    "Stream from %s failed, retrying same backend in non-streaming for workspace=%s",
                    backend.id,
                    workspace_id,
                )
                fallback_body = {**body, "stream": False}
                result = await _try_non_streaming(
                    backend,
                    fallback_body,
                    workspace_id,
                    start_time,
                    enforce_hint=True,
                    persona=persona,
                )
                if result is not None:
                    data = json.loads(result.body)
                    for frame in _json_completion_to_sse(data, workspace_id):
                        yield frame
                    return

                if remaining:
                    logger.info(
                        "Non-streaming retry on %s failed, falling back to remaining backends for workspace=%s",
                        backend.id,
                        workspace_id,
                    )
                    for j, fb in enumerate(remaining):
                        fb_last = j == len(remaining) - 1
                        result = await _try_non_streaming(
                            fb,
                            fallback_body,
                            workspace_id,
                            start_time,
                            enforce_hint=not fb_last,
                            persona=persona,
                        )
                        if result is not None:
                            data = json.loads(result.body)
                            for frame in _json_completion_to_sse(data, workspace_id):
                                yield frame
                            return

                if _error_buffer:
                    yield _error_buffer
                else:
                    yield b'data: {"error": "All backends failed"}\n\n'
                yield b"data: [DONE]\n\n"
                _record_error(workspace_id, "all_backends_failed")

        slot.detach()
        _streaming_response = StreamingResponse(
            _stream_or_fallback(),
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
