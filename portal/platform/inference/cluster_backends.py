"""Backend registry — config-driven inference backend discovery and routing.

Loaded once per pipeline process from ``config/backends.yaml`` and instantiated
as a singleton in ``router_pipe.lifespan``; no other code constructs a
``BackendRegistry``. Three backend types:

* ``ollama``            — health probed via ``/api/tags``.
* ``openai_compatible`` — vLLM and similar; health probed via ``/health``.
* ``omlx``              — third-party oMLX on Apple Silicon (OpenAI-compatible
  serving); health probed via ``/v1/models``.

A per-backend ``health_path:`` YAML key overrides the type-derived probe path.
Adding a cluster node is a YAML edit plus a pipeline restart — never a code
change. Workspace-to-group routing lives in ``workspace_routing:``; keys there
must match the ``WORKSPACES`` dict (enforced by the workspace-consistency
check). The per-request hot path ``get_backend_for_workspace`` →
``get_backend_candidates`` is cached.
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

# Pre-compiled regex — avoid re-compiling on every string expansion.
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(val: Any) -> Any:
    """Expand POSIX-style ``${VAR}`` and ``${VAR:-default}`` placeholders in ``val``.

    Recurses through dicts and lists. Non-string scalars pass through unchanged;
    missing variables with no ``:-default`` resolve to the empty string.

    Args:
        val: Any value from the parsed YAML — typically a dict, list, or str.

    Returns:
        ``val`` with all ``${...}`` references replaced. Containers are rebuilt;
        the original is not mutated.
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


def _priority_ordered(backends: list[Backend]) -> list[Backend]:
    """Sort by descending ``priority``, shuffling within equal priorities.

    All-zero priority lists shuffle exactly as before — a no-op until set.
    """
    by_priority: dict[int, list[Backend]] = {}
    for b in backends:
        by_priority.setdefault(b.priority, []).append(b)
    out: list[Backend] = []
    for prio in sorted(by_priority, reverse=True):
        tier = by_priority[prio]
        random.shuffle(tier)
        out.extend(tier)
    return out


def _default_config_path() -> str:
    """Resolve ``backends.yaml`` path across container, local-dev, and CI contexts.

    Priority: ``BACKEND_CONFIG_PATH`` env var, then ``/app/config/backends.yaml``
    (Docker mount), then ``<repo_root>/config/backends.yaml`` (local dev, walking
    up from this file).

    Returns:
        The first path that exists; the Docker path otherwise.
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
    for parent in this_file.parents:
        candidate = parent / "config" / "backends.yaml"
        if candidate.exists():
            return str(candidate)

    # Fall back to Docker path (will log an error if not found — expected in CI)
    return str(docker_path)


DEFAULT_CONFIG_PATH = _default_config_path()


@dataclass
class Backend:
    """A single inference backend — Ollama or OpenAI-compatible (vLLM).

    Instances are constructed by ``BackendRegistry._load_config`` from
    ``config/backends.yaml`` and mutated in-place only by ``_check_one``
    (``healthy``/``last_check``); treat as immutable elsewhere.

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
    type: str  # "ollama" | "openai_compatible" | "omlx"
    url: str
    group: str  # e.g., "general", "coding", "creative"
    models: list[str]
    healthy: bool = True
    last_check: float = 0.0
    consecutive_failures: int = field(default=0)
    # Per-model metadata from dict-form entries in `models:`; empty for
    # bare-string (legacy) entries, which default to supports_tools=False.
    ollama_metadata: list[dict] = field(default_factory=list)
    # Optional explicit health-probe path override (`health_path:` in YAML).
    # Wins over the type-derived default in `health_url`.
    health_path: str | None = None
    # Candidate-ordering weight within a group (`priority:` in YAML, default 0).
    # Higher tried first; equal priorities shuffle for load balancing.
    priority: int = 0
    # Hint-translation map (`aliases:` in YAML): canonical hint id → this
    # backend's native model id. Lets a workspace keep one model_hint while
    # engines are swapped underneath.
    aliases: dict[str, str] = field(default_factory=dict)

    @property
    def chat_url(self) -> str:
        """Return the OpenAI-compatible chat completions URL for this backend.

        Both Ollama (>=0.1.24) and vLLM expose /v1/chat/completions, so the
        request body format is identical regardless of backend type.
        """
        return f"{self.url.rstrip('/')}/v1/chat/completions"

    @property
    def health_url(self) -> str:
        """Return the URL to probe for liveness, dispatched by backend ``type``.

        Explicit ``health_path`` wins when set; else ``ollama`` → ``/api/tags``,
        ``omlx`` → ``/v1/models``, any other → ``/health``.
        """
        if self.health_path:
            return f"{self.url.rstrip('/')}{self.health_path}"
        if self.type == "ollama":
            return f"{self.url.rstrip('/')}/api/tags"
        if self.type == "omlx":
            return f"{self.url.rstrip('/')}/v1/models"
        return f"{self.url.rstrip('/')}/health"

    def resolve_model(self, model_hint: str) -> str | None:
        """Translate a workspace model hint to this backend's native model id.

        Returns the hint unchanged when served directly, the alias target when
        aliased, or ``None`` when this backend cannot serve the hint.
        """
        if not model_hint:
            return None
        if model_hint in self.models:
            return model_hint
        return self.aliases.get(model_hint)


class BackendRegistry:
    """Singleton registry of inference backends — loads, monitors, and selects.

    Constructed once per pipeline process in ``router_pipe.lifespan``. Reads
    after construction are safe; the mutators are ``_check_one`` (per-backend
    ``healthy``) and the cache helpers.

    Hot path: ``get_backend_for_workspace`` → ``get_backend_candidates`` →
    cached lookup (dict get + list copy). Caches: ``_cached_healthy`` (rebuilt
    after each health cycle), ``_ws_group_cache`` (built at YAML load), and
    ``_candidate_cache`` (5s TTL, invalidated on health changes).

    Class-level ``_health_client``/``_health_semaphore`` are shared so tests
    that construct multiple registries don't each open a connection pool. Call
    ``BackendRegistry.close_health_client()`` on shutdown.

    Startup: ``Backend.healthy`` defaults to True, so requests before the first
    health cycle are routed optimistically rather than 503'd.
    """

    # Shared httpx client for health checks — single connection pool reused
    # across all health check cycles. Created lazily on first health check.
    _health_client: httpx.AsyncClient | None = None
    _health_semaphore: asyncio.Semaphore | None = None

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the registry and load ``config_path``.

        State is set to safe defaults before ``_load_config`` runs, so a
        malformed or missing YAML produces an empty-but-valid registry
        (requests 503 with a clear log line) rather than a hard crash at
        startup.

        Args:
            config_path: Override the auto-detected path; ``None`` →
                ``DEFAULT_CONFIG_PATH``.
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._backends: dict[str, Backend] = {}
        self._workspace_routes: dict[str, list[str]] = {}
        self._fallback_group: str = "general"
        self._health_check_interval = 30.0
        self._request_timeout = 120.0  # Match config/backends.yaml defaults.request_timeout
        self._health_timeout = 10.0  # Defensive default before _load_config() runs
        self._health_failure_threshold = 2
        # Cached healthy-backend list — rebuilt only after each health check
        # cycle, not on every inference request. None = pre-first-cycle.
        self._cached_healthy: list[Backend] | None = None
        # Pre-computed workspace → group list cache. Built once in _load_config.
        self._ws_group_cache: dict[str, list[str]] = {}
        # TTL-cached backend candidates per workspace. Rebuilt after health
        # checks or when the TTL expires.
        self._candidate_cache: dict[str, tuple[list[Backend], float]] = {}
        self._candidate_cache_ttl: float = 5.0  # 5s TTL — short enough to react to failures
        self._tool_support: dict[str, bool] = {}
        self._last_healthy_count: int = -1
        self._last_memory_pct: float = 0.0

        self._load_config()

    def _load_config(self) -> None:
        """Parse ``backends.yaml``, expand env vars, populate registry state.

        Failure mode is "empty registry + logged error", never a raised
        exception, so the pipeline reaches a serving state even with broken
        config (missing file, YAML parse error, non-dict top level).
        Per-backend errors are logged and the entry skipped; surrounding
        backends still load.

        Handles ``models:`` entries as bare strings (legacy; ``ollama_metadata``
        stays empty) or dicts with ``id`` plus optional ``supports_tools``
        (populates metadata). Also builds ``_ws_group_cache``.
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

        # Expand environment variables
        cfg = _expand_env(cfg)

        # Load backends
        for be in cfg.get("backends", []):
            # Accept `models: [str]` OR `models: [dict]`; dict entries populate
            # ollama_metadata, strings leave it empty.
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
                health_path=be.get("health_path"),
                priority=int(be.get("priority", 0) or 0),
                aliases={str(k): str(v) for k, v in (be.get("aliases") or {}).items()},
            )
            self._backends[backend.id] = backend
            logger.info(
                "Registered backend: %s (%s) in group '%s' (%d models, %d with metadata, "
                "priority=%d, %d aliases)",
                backend.id,
                backend.type,
                backend.group,
                len(flat_models),
                len(ollama_meta),
                backend.priority,
                len(backend.aliases),
            )

        # Load workspace routing
        self._workspace_routes = cfg.get("workspace_routing", {})
        # Pre-compute workspace → group list for O(1) lookups
        self._ws_group_cache = {
            ws_id: groups.copy() for ws_id, groups in self._workspace_routes.items()
        }

        # Load defaults
        defaults = cfg.get("defaults", {})
        self._fallback_group = defaults.get("fallback_group", "general")
        self._request_timeout = float(defaults.get("request_timeout", 120.0))
        self._health_check_interval = float(defaults.get("health_check_interval", 30.0))
        self._health_timeout = float(defaults.get("health_timeout", 10.0))
        self._health_failure_threshold = int(
            os.environ.get(
                "HEALTH_FAILURE_THRESHOLD", str(defaults.get("health_failure_threshold", 2))
            )
        )

        # Build tool support map from backend metadata
        self._tool_support = {}
        for be in self._backends.values():
            for meta in be.ollama_metadata:
                mid = meta.get("id")
                if mid:
                    self._tool_support[mid] = bool(meta.get("supports_tools", False))

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

        Uses ``_cached_healthy``; before the first cycle completes (``None``)
        falls back to a live scan, routing startup-window requests
        optimistically.
        """
        return (
            self._cached_healthy
            if self._cached_healthy is not None
            else [b for b in self._backends.values() if b.healthy]
        )

    def _refresh_healthy_cache(self) -> None:
        """Rebuild ``_cached_healthy`` and invalidate the candidate cache.

        Called from ``health_check_all`` after every cycle; the invalidation is
        what lets a health change take effect within the 5s TTL window.
        """
        self._cached_healthy = [b for b in self._backends.values() if b.healthy]
        self._invalidate_candidate_cache()

    def get_backend_candidates(self, workspace_id: str) -> list[Backend]:
        """Return ordered list of healthy candidates for ``workspace_id``.

        Order is by group priority (from ``workspace_routing``), shuffled within
        each group for load balancing. Tiers, each only contributing unseen
        backends:
        1. the workspace's named groups, in YAML order;
        2. the configured ``fallback_group`` (default ``"general"``);
        3. any remaining healthy backends (degrade-don't-fail safety net).

        Results are cached per workspace for 5s and invalidated after every
        health cycle. Unknown ids are clamped to ``"_unknown"`` as cache key.

        Args:
            workspace_id: A workspace id from ``WORKSPACES`` /
                ``workspace_routing``.

        Returns:
            Fresh list copy; safe to mutate. Empty when no backends are healthy.
        """
        # Synthetic ids like ``auto-coding::laguna`` resolve to the base
        # workspace for candidate selection; otherwise use the ordinary
        # unknown-id fallback.
        base_workspace_id = workspace_id.split("::", 1)[0]
        routing_workspace_id = (
            base_workspace_id if base_workspace_id in self._ws_group_cache else workspace_id
        )

        # Check cache first (clamp unknown workspace ids to _unknown)
        cache_key = (
            routing_workspace_id if routing_workspace_id in self._ws_group_cache else "_unknown"
        )
        now = time.time()
        cached = self._candidate_cache.get(cache_key)
        if cached is not None:
            candidates, cache_time = cached
            if now - cache_time < self._candidate_cache_ttl:
                return list(candidates)

        groups = self._ws_group_cache.get(routing_workspace_id, [self._fallback_group])
        healthy = self.list_healthy_backends()
        if not healthy:
            return []

        result: list[Backend] = []
        seen: set[str] = set()

        # Collect backends by group priority, ordered within each group by
        # descending Backend.priority, shuffled only among equal priorities.
        for group in groups:
            group_backends = [b for b in healthy if b.group == group and b.id not in seen]
            if group_backends:
                group_backends = _priority_ordered(group_backends)
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

        # Cache the result
        self._candidate_cache[cache_key] = (result, now)
        return list(result)

    def _invalidate_candidate_cache(self) -> None:
        """Clear the per-workspace candidate cache.

        Forces the next ``get_backend_candidates`` call to rebuild, so a newly
        unhealthy backend drops out within one health cycle instead of the 5s
        TTL.
        """
        self._candidate_cache.clear()

    def get_backend_for_workspace(self, workspace_id: str) -> Backend | None:
        """Select the single best healthy backend for ``workspace_id``.

        Returns the head of ``get_backend_candidates``; used by callers
        without request-level fallback (warmups, the ``/health`` endpoint).

        Args:
            workspace_id: Workspace identifier; see ``get_backend_candidates``.

        Returns:
            A ``Backend``, or ``None`` if none healthy — the caller should
            surface a 503 (the chat-completions handler does this).
        """
        candidates = self.get_backend_candidates(workspace_id)
        return candidates[0] if candidates else None

    @classmethod
    def _get_health_semaphore(cls) -> asyncio.Semaphore:
        """Lazily-create the shared semaphore that bounds concurrent health checks.

        Class-level so all registries in a process share the cap; the cap of 2
        keeps a 30-backend cluster's cycle well under the request-handling
        concurrency budget.
        """
        if cls._health_semaphore is None:
            cls._health_semaphore = asyncio.Semaphore(2)
        return cls._health_semaphore

    @classmethod
    async def _get_health_client(cls, health_timeout: float) -> httpx.AsyncClient:
        """Lazily-create the shared ``httpx.AsyncClient`` used for health checks.

        One client (10 keepalive, 20 max connections) is reused across every
        health cycle, so steady-state cycles cost zero handshakes. Class-level
        lifetime; must be closed on shutdown via ``close_health_client``.

        Args:
            health_timeout: Per-request timeout for every health probe; honoured
                only at first call.
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

        Launched concurrently bounded by ``_get_health_semaphore`` (cap 2).
        Per-backend exceptions are swallowed by ``_check_one``; this method
        never raises. On completion ``_refresh_healthy_cache`` rebuilds
        ``_cached_healthy`` and invalidates the candidate cache, so health
        changes take effect on the very next request.
        """
        sem = self._get_health_semaphore()
        client = await self._get_health_client(self._health_timeout)
        await asyncio.gather(
            *[self._check_one(b, sem, client) for b in self._backends.values()],
            return_exceptions=True,
        )
        self._refresh_healthy_cache()  # update cache after all checks complete
        healthy_count = len(self._cached_healthy)
        if healthy_count != self._last_healthy_count:
            self._last_healthy_count = healthy_count
            logger.info("Health check complete: %d/%d healthy", healthy_count, len(self._backends))
        else:
            logger.debug(
                "Health check complete: %d/%d healthy (no change)",
                healthy_count,
                len(self._backends),
            )
        try:
            from portal.platform.inference.router.monitor import memory_pct as _mp

            # Offload vm_stat to a thread so it doesn't block the event loop.
            _mem = await asyncio.get_running_loop().run_in_executor(None, _mp)
            self._last_memory_pct = _mem
            if _mem >= 90.0:
                logger.error("System memory critical: %.0f%% — OOM risk, backends may fail", _mem)
            elif _mem >= 80.0:
                logger.warning("System memory high: %.0f%%", _mem)
            # Push to admission gate — no subprocess call per request
            try:
                import portal.platform.inference.router.concurrency as _conc

                _conc._last_memory_pct = _mem
            except Exception:
                pass  # concurrency gate update is best-effort; poller continues
        except Exception:
            logger.debug("Memory poller error — skipping this tick", exc_info=True)

    async def _check_one(
        self,
        backend: Backend,
        sem: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> None:
        """Probe one backend; update ``backend.healthy`` and ``backend.last_check``.

        HTTP 200 → healthy, anything else → unhealthy; never raises. The
        semaphore is held only for the network call. Hysteresis: ``healthy``
        flips to False only after ``_health_failure_threshold`` consecutive
        failures; a success resets the counter and restores healthy immediately.

        Args:
            backend: Backend to probe; mutated in place.
            sem: Concurrency-limiting semaphore from ``_get_health_semaphore``.
            client: Shared HTTP client from ``_get_health_client``.
        """
        async with sem:
            try:
                resp = await client.get(backend.health_url)
                ok = resp.status_code == 200
            except Exception:
                ok = False
            finally:
                backend.last_check = time.time()

            if ok:
                backend.consecutive_failures = 0
                if not backend.healthy:
                    backend.healthy = True
                    logger.info("Health check recovered: %s", backend.id)
            else:
                backend.consecutive_failures += 1
                if backend.consecutive_failures >= self._health_failure_threshold:
                    if backend.healthy:
                        logger.warning(
                            "Health check failed for %s: %d consecutive failures — marking unhealthy",
                            backend.id,
                            backend.consecutive_failures,
                        )
                        backend.healthy = False
                else:
                    logger.debug(
                        "Health check failed for %s: %d/%d consecutive failures",
                        backend.id,
                        backend.consecutive_failures,
                        self._health_failure_threshold,
                    )

    async def start_health_loop(
        self,
        on_health_check: Callable | None = None,
    ) -> None:
        """Long-running task: health-check every ``_health_check_interval`` seconds.

        Sleeps first, then probes, so callers can run one synchronous
        ``health_check_all`` before launching (``lifespan`` does this). Exits
        cleanly on ``asyncio.CancelledError``; other exceptions are logged and
        the loop continues.

        Args:
            on_health_check: Optional callback invoked with ``self`` after each
                cycle; sync or async (awaitable results are awaited). Lets
                ``lifespan`` inject the notification dispatcher's threshold
                check without a dependency.
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

    @property
    def last_memory_pct(self) -> float:
        """System memory used % from the most recent health cycle (0.0 = not yet measured)."""
        return self._last_memory_pct

    @property
    def workspace_routes(self) -> dict[str, list[str]]:
        """Workspace-to-group routing map from ``config/backends.yaml``."""
        return self._workspace_routes

    def model_supports_tools(self, model_id: str) -> bool:
        """Return whether ``model_id`` declares ``supports_tools: true``.

        O(1) lookup against the pre-built ``_tool_support`` map; ``False`` for
        unknown models.
        """
        return self._tool_support.get(model_id, False)
