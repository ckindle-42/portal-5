"""Backend registry — config-driven inference backend discovery and routing.

This module owns the single source of truth for "which backends exist and which
are reachable right now." It is loaded once per pipeline process from
``config/backends.yaml`` and instantiated as a singleton in
``router_pipe.lifespan``; no other code constructs a ``BackendRegistry``.

Two backend types are supported:

* ``ollama``           — health probed via ``/api/tags``.
* ``openai_compatible``— vLLM and similar; health probed via ``/health``.

Operator workflow: adding a cluster node is a YAML edit and a pipeline restart
— never a code change. Workspace-to-group routing lives in the same YAML under
``workspace_routing:``; the keys there must match the ``WORKSPACES`` dict in
``router_pipe.py`` (the workspace-consistency check in CLAUDE.md §6 enforces
this).

Per-request hot path is ``get_backend_for_workspace`` → ``get_backend_candidates``;
both are cached so the steady-state cost per request is a dict lookup and a
list copy, not a YAML re-parse or a health re-scan.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

# Pre-compiled regex — avoid re-compiling on every string expansion (P5)
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(val: Any) -> Any:
    """Expand POSIX-style ``${VAR}`` and ``${VAR:-default}`` placeholders in ``val``.

    Recurses through dicts and lists so a single call expands every string in
    a parsed YAML config tree. Non-string scalars pass through unchanged.
    Missing variables with no ``:-default`` resolve to the empty string,
    matching shell semantics.

    Used by ``_load_config`` to make ``backends.yaml`` portable across the
    Docker container (where ``HOST_GATEWAY`` is ``host.docker.internal``) and
    the host (where it is empty or unset).

    Args:
        val: Any value from the parsed YAML — typically a dict, list, or str.

    Returns:
        ``val`` with all ``${...}`` references in any contained string
        replaced. Containers are rebuilt; the original is not mutated.
    """

    def _replace(m: re.Match) -> str:
        """Regex substitution callback: resolve ``${VAR}`` or ``${VAR:-default}``."""
        var, _, default = m.group(1).partition(":-")
        return os.environ.get(var, default)

    if isinstance(val, str):
        return _ENV_VAR_RE.sub(_replace, val)
    if isinstance(val, dict):
        return {k: _expand_env(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_expand_env(item) for item in val]
    return val


def _default_config_path() -> str:
    """Resolve ``backends.yaml`` path across container, local-dev, and CI contexts.

    Priority order:

    1. ``BACKEND_CONFIG_PATH`` environment variable (explicit override,
       used by tests and ad-hoc operator runs).
    2. ``/app/config/backends.yaml`` — the Docker container mount.
    3. ``<repo_root>/config/backends.yaml`` — local development, found by
       walking up to three directories from this file.

    Returns:
        The first path that exists. If none exist, returns the Docker path
        so the downstream "config not found" log in ``_load_config`` points
        at the path operators are most likely to expect.
    """
    # Explicit override always wins
    if env_path := os.environ.get("BACKEND_CONFIG_PATH"):
        return env_path

    # Docker path
    docker_path = Path("/app/config/backends.yaml")
    if docker_path.exists():
        return str(docker_path)

    # Local dev: walk up from this file to find config/backends.yaml
    this_file = Path(__file__).resolve()
    for parent in [this_file.parent, this_file.parent.parent, this_file.parent.parent.parent]:
        candidate = parent / "config" / "backends.yaml"
        if candidate.exists():
            return str(candidate)

    # Fall back to Docker path (will log an error if not found — expected in CI)
    return str(docker_path)


DEFAULT_CONFIG_PATH = _default_config_path()


@dataclass
class Backend:
    """A single inference backend — Ollama or OpenAI-compatible (vLLM).

    Instances are constructed exclusively by ``BackendRegistry._load_config``
    from entries in ``config/backends.yaml`` and are mutated in-place only by
    ``_check_one`` (which updates ``healthy`` and ``last_check``). Treat as
    effectively immutable elsewhere.

    Attributes:
        id: Stable identifier from YAML; used as the registry dict key.
        type: One of ``"ollama"``, ``"openai_compatible"``.
            Drives which URL ``health_url`` produces.
        url: Base URL (no trailing slash required); ``chat_url`` and
            ``health_url`` append the appropriate path.
        group: Routing group (e.g. ``"general"``, ``"coding"``). Workspaces
            map to one or more group names in ``workspace_routing``.
        models: Flat list of model ids served by this backend.
        healthy: Liveness flag. **Defaults to True** so requests immediately
            after startup don't 503 while the first health-check cycle is
            still running; ``_check_one`` flips it as needed.
        last_check: Monotonic wall-clock timestamp of the last health probe.
        ollama_metadata: Per-model dicts for Ollama backends when entries
            in ``models:`` are dicts (new format with explicit
            ``supports_tools``). Empty list when entries are bare strings
            (legacy format), in which case downstream tool-support checks
            fall through to the conservative default (no tool support).
    """

    id: str
    type: str  # "ollama" | "openai_compatible"
    url: str
    group: str  # e.g., "general", "coding", "creative"
    models: list[str]
    healthy: bool = True
    last_check: float = 0.0
    # Rich per-model metadata for Ollama backends. Populated from dict-form entries
    # in `models:` (e.g. `{id: foo, supports_tools: true}`). Empty list when entries
    # are bare strings (legacy format) — those models default to supports_tools=False
    # via _model_supports_tools(). See TASK_TOOL_SUPPORT_AUDIT_V1 §A2-A4.
    ollama_metadata: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ollama_metadata is None:
            self.ollama_metadata = []

    @property
    def chat_url(self) -> str:
        """Return the OpenAI-compatible chat completions URL for this backend.

        Both Ollama (>=0.1.24) and vLLM expose /v1/chat/completions.
        We always use the OpenAI-compatible endpoint so request body format
        is identical regardless of backend type.
        """
        return f"{self.url.rstrip('/')}/v1/chat/completions"

    @property
    def health_url(self) -> str:
        """Return the URL to probe for liveness, dispatched by backend ``type``.

        * ``ollama`` → ``/api/tags`` — proves the daemon is up and the model
          registry is responsive in one round-trip.
        * any other → ``/health`` — vLLM's canonical liveness path.
        """
        if self.type == "ollama":
            return f"{self.url.rstrip('/')}/api/tags"
        return f"{self.url.rstrip('/')}/health"


class BackendRegistry:
    """Singleton registry of inference backends — loads, monitors, and selects.

    Constructed exactly once per pipeline process in ``router_pipe.lifespan``.
    Concurrent reads during request handling are safe (no mutation of the
    backend list after ``_load_config``); the only mutators after construction
    are ``_check_one`` (per-backend ``healthy`` flag) and the cache helpers.

    Hot path: ``get_backend_for_workspace(ws)`` → ``get_backend_candidates(ws)``
    → cached lookup. Steady-state cost per request is a dict get and a list
    copy. The three caches that make this work are:

    * ``_cached_healthy`` — full healthy list, refreshed after each
      ``health_check_all`` cycle (every 30s by default).
    * ``_ws_group_cache`` — workspace id → list of group names, built once
      at YAML load.
    * ``_candidate_cache`` — per-workspace ordered candidate list, 5s TTL,
      invalidated immediately on health-status changes.

    Class-level (shared across all instances): ``_health_client`` and
    ``_health_semaphore``. These are intentionally shared so tests that
    construct multiple registries don't each open a connection pool; in
    production there is only one registry anyway. Call
    ``BackendRegistry.close_health_client()`` on shutdown.

    Startup behavior: ``Backend.healthy`` defaults to ``True``, so requests
    arriving before the first health-check cycle completes are routed
    optimistically rather than 503'd. The first ``health_check_all`` call
    flips any unreachable backends to unhealthy and they drop out of routing.
    """

    # Shared httpx client for health checks — single connection pool reused across
    # all health check cycles. Created lazily on first health check.
    _health_client: httpx.AsyncClient | None = None
    _health_semaphore: asyncio.Semaphore | None = None

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the registry and load ``config_path``.

        All instance state is set to safe defaults before ``_load_config`` runs,
        so a malformed or missing YAML file produces an empty-but-valid registry
        (every request will 503 with a clear log line) rather than a hard crash
        at process startup. This lets operators fix the YAML and restart only
        the pipeline container.

        Args:
            config_path: Override the auto-detected path. When ``None``, falls
                back to ``DEFAULT_CONFIG_PATH`` (resolved at import time by
                ``_default_config_path``).
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._backends: dict[str, Backend] = {}
        self._workspace_routes: dict[str, list[str]] = {}
        self._fallback_group: str = "general"
        self._health_check_interval = 30.0
        self._request_timeout = 120.0  # Match config/backends.yaml defaults.request_timeout
        self._health_timeout = 10.0  # Defensive default before _load_config() runs
        self._max_concurrent_health_checks = 2  # P3: prevent health-check storm
        # P8: cached healthy-backend list — rebuilt only after each health check
        # cycle, not on every inference request. None = uninitialized (pre-first-cycle).
        self._cached_healthy: list[Backend] | None = None
        # P9: pre-computed workspace → group list cache. Built once in _load_config.
        # Eliminates dict lookup + list construction on every get_backend_for_workspace call.
        self._ws_group_cache: dict[str, list[str]] = {}
        # P7-PERF: TTL-cached backend candidates per workspace. Rebuilt after health checks
        # or when TTL expires. Avoids list comprehension + shuffle on every request.
        self._candidate_cache: dict[str, tuple[list[Backend], float]] = {}
        self._candidate_cache_ttl: float = 5.0  # 5s TTL — short enough to react to failures

        self._load_config()

    def _load_config(self) -> None:
        """Parse ``backends.yaml``, expand env vars, populate registry state.

        Failure mode is "empty registry + logged error", never a raised exception
        — the pipeline must reach a serving state even if config is broken so
        operators can fix YAML and restart only this container. The conditions
        that trigger empty-registry-mode are:

        * config file missing,
        * YAML parse error,
        * top-level structure not a dict.

        Per-backend errors (unexpected model entry type, etc.) are logged and
        the offending entry is skipped; surrounding backends still load.

        Handles two model-entry formats in ``backends:[].models:``:

        * Bare strings (legacy) — populate ``Backend.models`` only;
          ``ollama_metadata`` stays empty and downstream tool-support checks
          fall through to the conservative default.
        * Dicts with ``id`` plus optional ``supports_tools`` etc. (new) —
          populate both ``Backend.models`` and ``Backend.ollama_metadata``.

        Also builds ``_ws_group_cache`` (one dict-copy per workspace) so
        ``get_backend_candidates`` doesn't pay the lookup cost per request.
        """
        if not os.path.exists(self.config_path):
            logger.error("Backend config not found: %s", self.config_path)
            # Graceful fallback: create empty registry
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg: dict[str, Any] = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            logger.error(
                "Failed to parse %s: %s — BackendRegistry empty, all requests will 503",
                self.config_path,
                exc,
            )
            return

        # Verify env interpolation
        sample_url = (cfg.get("backends") or [{}])[0].get("url", "")
        if "${" in sample_url:
            logger.warning(
                "backends.yaml URLs contain unexpanded env vars (e.g. %s). "
                "Adding os.path.expandvars() expansion.",
                sample_url[:60],
            )

        # Expand environment variables
        cfg = _expand_env(cfg)

        # Load backends
        for be in cfg.get("backends", []):
            # Accept `models: [str]` OR `models: [dict]`. When entries are dicts,
            # populate ollama_metadata; when strings, leave it empty.
            ollama_meta: list[dict] = []
            raw_models = be.get("models", [])
            flat_models = []
            for m in raw_models:
                if isinstance(m, dict):
                    flat_models.append(m["id"])
                    ollama_meta.append(m)
                elif isinstance(m, str):
                    flat_models.append(m)
                else:
                    logger.warning(
                        "Backend %s: unexpected model entry type %s, skipping",
                        be.get("id"),
                        type(m).__name__,
                    )
            backend = Backend(
                id=be["id"],
                type=be.get("type", "ollama"),
                url=be["url"],
                group=be.get("group", "general"),
                models=flat_models,
                ollama_metadata=ollama_meta,
            )
            self._backends[backend.id] = backend
            logger.info(
                "Registered backend: %s (%s) in group '%s' (%d models, %d with metadata)",
                backend.id,
                backend.type,
                backend.group,
                len(flat_models),
                len(ollama_meta),
            )

        # Load workspace routing
        self._workspace_routes = cfg.get("workspace_routing", {})
        # P9: pre-compute workspace → group list for O(1) get_backend_for_workspace lookups
        self._ws_group_cache = {
            ws_id: groups.copy() for ws_id, groups in self._workspace_routes.items()
        }

        # Load defaults
        defaults = cfg.get("defaults", {})
        self._fallback_group = defaults.get("fallback_group", "general")
        self._request_timeout = float(defaults.get("request_timeout", 120.0))
        self._health_check_interval = float(defaults.get("health_check_interval", 30.0))
        self._health_timeout = float(defaults.get("health_timeout", 10.0))

        logger.info(
            "BackendRegistry loaded: %d backends, %d workspace routes, request_timeout=%.0fs",
            len(self._backends),
            len(self._workspace_routes),
            self._request_timeout,
        )

    def list_backends(self) -> list[Backend]:
        """Return all registered backends."""
        return list(self._backends.values())

    def list_healthy_backends(self) -> list[Backend]:
        """Return backends currently passing health checks.

        Returns the cache populated by ``_refresh_healthy_cache`` after each
        health cycle. Before the first cycle completes ``_cached_healthy`` is
        ``None`` and we fall back to a live scan over ``_backends.values()``;
        combined with ``Backend.healthy`` defaulting to ``True``, this means
        requests arriving in the startup window are routed optimistically
        rather than 503'd.
        """
        return (
            self._cached_healthy
            if self._cached_healthy is not None
            else [b for b in self._backends.values() if b.healthy]
        )

    def _refresh_healthy_cache(self) -> None:
        """Rebuild ``_cached_healthy`` and invalidate the candidate cache.

        Called from ``health_check_all`` after every cycle. Invalidating the
        candidate cache here is the only reason ``get_backend_candidates``
        sees freshness within the 5s TTL window — without this, a backend
        going down would still be returned as a candidate until its TTL
        entries naturally expired.
        """
        self._cached_healthy = [b for b in self._backends.values() if b.healthy]
        # P7-PERF: Invalidate candidate cache when health status changes
        self._invalidate_candidate_cache()

    def get_backend_candidates(self, workspace_id: str) -> list[Backend]:
        """Return ordered list of healthy candidates for ``workspace_id``.

        Order is by group priority (from ``workspace_routing`` in YAML), then
        randomly shuffled within each group for load balancing. Three tiers
        are appended in sequence, each only contributing backends not already
        seen:

        1. The workspace's named groups, in YAML order.
        2. The configured ``fallback_group`` (default ``"general"``).
        3. Any remaining healthy backends.

        The third tier is a deliberate degrade-don't-fail safety net — an
        unusual workspace with no matching healthy backend still routes
        somewhere, with a logged warning at the call site, rather than 503'ing
        while other capacity sits idle.

        Results are cached per workspace for 5s. The cache is also invalidated
        immediately after every health-check cycle, so a backend going down
        flips out of routing within one cycle (30s default), not 5s + 30s.

        Args:
            workspace_id: A workspace id from ``WORKSPACES`` /
                ``workspace_routing``. Unknown ids route via the fallback
                group only (no error raised).

        Returns:
            Fresh list copy; safe to mutate. Empty when no backends are healthy.
        """
        # P7-PERF: Check cache first
        now = time.time()
        cached = self._candidate_cache.get(workspace_id)
        if cached is not None:
            candidates, cache_time = cached
            if now - cache_time < self._candidate_cache_ttl:
                # Return a copy to prevent mutation — shallow copy is fine since
                # Backend objects are not mutated during request handling.
                return list(candidates)

        groups = self._ws_group_cache.get(workspace_id, [self._fallback_group])
        healthy = self.list_healthy_backends()
        if not healthy:
            return []

        result: list[Backend] = []
        seen: set[str] = set()

        # Collect backends by group priority, shuffled within each group
        for group in groups:
            group_backends = [b for b in healthy if b.group == group and b.id not in seen]
            if group_backends:
                random.shuffle(group_backends)
                result.extend(group_backends)
                seen.update(b.id for b in group_backends)

        # Append fallback group backends if not already included
        fallback = [b for b in healthy if b.group == self._fallback_group and b.id not in seen]
        if fallback:
            random.shuffle(fallback)
            result.extend(fallback)
            seen.update(b.id for b in fallback)

        # Append any remaining healthy backends as absolute fallback
        remaining = [b for b in healthy if b.id not in seen]
        if remaining:
            random.shuffle(remaining)
            result.extend(remaining)

        # P7-PERF: Cache the result
        self._candidate_cache[workspace_id] = (result, now)
        return list(result)

    def _invalidate_candidate_cache(self) -> None:
        """Clear the per-workspace candidate cache.

        Called from ``_refresh_healthy_cache`` whenever health status changes.
        Forces the next ``get_backend_candidates`` call to rebuild from scratch,
        which is what lets a newly-unhealthy backend drop out of routing within
        one health cycle instead of waiting for the 5s TTL.
        """
        self._candidate_cache.clear()

    def get_backend_for_workspace(self, workspace_id: str) -> Backend | None:
        """Select the single best healthy backend for ``workspace_id``.

        Convenience wrapper around ``get_backend_candidates`` that returns the
        head of the list. Used by callers that don't need request-level
        fallback (warmups, the ``/health`` endpoint's backend counters).

        Args:
            workspace_id: Workspace identifier; see ``get_backend_candidates``.

        Returns:
            A ``Backend``, or ``None`` if no healthy backend exists anywhere
            — in which case the caller is expected to surface a 503 (the
            chat-completions handler does exactly this).
        """
        candidates = self.get_backend_candidates(workspace_id)
        return candidates[0] if candidates else None

    @classmethod
    def _get_health_semaphore(cls) -> asyncio.Semaphore:
        """Lazily-create the shared semaphore that bounds concurrent health checks.

        Class-level so all registries in a process share the cap (in production
        there is only one registry; tests construct several). The cap of 2 is
        intentionally conservative — a 30-backend cluster spreads its health
        cycle over ~15s of every 30s interval, well under the request-handling
        workers' concurrency budget.
        """
        if cls._health_semaphore is None:
            cls._health_semaphore = asyncio.Semaphore(2)
        return cls._health_semaphore

    @classmethod
    async def _get_health_client(cls, health_timeout: float) -> httpx.AsyncClient:
        """Lazily-create the shared ``httpx.AsyncClient`` used for health checks.

        A single client (10 keepalive, 20 max connections) is reused across
        every health-check cycle and every backend, so the 30s health cycle
        costs zero TCP/TLS handshakes after the first connect.

        Class-level lifetime — the client is created once per process and must
        be closed on shutdown via ``close_health_client``. ``lifespan`` in
        ``router_pipe.py`` does this in its cleanup phase.

        Args:
            health_timeout: Per-request timeout applied to every health probe
                using this client. Only honoured at first-call; later calls
                receive the same client and the original timeout.
        """
        if cls._health_client is None:
            cls._health_client = httpx.AsyncClient(
                timeout=health_timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                ),
            )
        return cls._health_client

    async def health_check_all(self) -> None:
        """Run one health-check cycle across every registered backend.

        Cycles are launched concurrently bounded by ``_get_health_semaphore``
        (default cap = 2). Per-backend exceptions are swallowed by
        ``_check_one``; this method itself never raises.

        On completion, ``_refresh_healthy_cache`` rebuilds ``_cached_healthy``
        and invalidates the candidate cache, so any health change observed in
        this cycle takes effect on the very next request.

        Called from ``start_health_loop`` on the configured interval and also
        once at startup in ``lifespan`` to ensure the first request has fresh
        data.
        """
        sem = self._get_health_semaphore()
        client = await self._get_health_client(self._health_timeout)
        await asyncio.gather(
            *[self._check_one(b, sem, client) for b in self._backends.values()],
            return_exceptions=True,
        )
        self._refresh_healthy_cache()  # P8: update cache after all checks complete
        healthy_count = len(self._cached_healthy)
        logger.info("Health check complete: %d/%d healthy", healthy_count, len(self._backends))

    async def _check_one(
        self,
        backend: Backend,
        sem: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> None:
        """Probe one backend; update ``backend.healthy`` and ``backend.last_check``.

        Standard path: HTTP 200 → healthy, anything else → unhealthy.

        Exceptions from the HTTP client are caught; this method never raises.
        The semaphore is held only for the duration of the network call.

        Args:
            backend: Backend to probe; mutated in place.
            sem: Concurrency-limiting semaphore from ``_get_health_semaphore``.
            client: Shared HTTP client from ``_get_health_client``.
        """
        async with sem:
            try:
                resp = await client.get(backend.health_url)
                backend.healthy = resp.status_code == 200
            except Exception as e:
                logger.debug("Health check failed for %s: %s", backend.id, e)
                backend.healthy = False
            finally:
                backend.last_check = time.time()

    async def start_health_loop(
        self,
        on_health_check: Callable | None = None,
    ) -> None:
        """Long-running task: health-check every ``_health_check_interval`` seconds.

        Sleeps first, then probes, so callers can invoke ``health_check_all``
        once synchronously before launching this loop to ensure the first
        request after startup has fresh data (``lifespan`` does this).

        Exits cleanly on ``asyncio.CancelledError`` (the standard shutdown
        signal from ``lifespan``); any other exception is logged and the loop
        continues — a single failing cycle never kills the registry.

        Args:
            on_health_check: Optional callback invoked with ``self`` after
                each cycle. May be sync or async; awaitable returns are
                awaited. This is how ``router_pipe.lifespan`` injects the
                notification dispatcher's threshold check without
                ``cluster_backends`` taking a dependency on notifications.
        """
        logger.info("Starting health check loop (interval: %ss)", self._health_check_interval)
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.health_check_all()
                if on_health_check is not None:
                    result = on_health_check(self)
                    if inspect.isawaitable(result):
                        await result
            except asyncio.CancelledError:
                logger.info("Health check loop cancelled")
                break
            except Exception as e:
                logger.error("Health loop error: %s", e)

    @classmethod
    async def close_health_client(cls) -> None:
        """Close the shared health-check HTTP client. Call on app shutdown."""
        if cls._health_client is not None:
            await cls._health_client.aclose()
            cls._health_client = None
            logger.debug("Health check HTTP client closed")

    @property
    def request_timeout(self) -> float:
        """Request timeout in seconds, loaded from ``defaults.request_timeout`` in YAML."""
        return self._request_timeout
