"""Request-concurrency machinery — semaphores, limits, and RequestSlot.

Owns the three semaphores (global request, per-workspace, per-API-key) and
:class:`RequestSlot`, which provides single-owner lifecycle for all three
within one request. Extracted from ``router_pipe.py`` where the same
lifecycle was split across five release sites.

Mutable singletons (``_request_semaphore``, ``_workspace_semaphores``,
``_api_key_semaphores``) live here and are **never** facade-re-exported
from ``router_pipe.py`` (A4). ``lifespan`` sets ``_request_semaphore``
directly on this module; :class:`RequestSlot` acquires and releases all
three on the request handler's behalf.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ── Limits ────────────────────────────────────────────────────────────────────

_MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "20"))

# Memory gate — updated by BackendRegistry.health_check_all() every ~30s.
# acquire_global() rejects requests before the semaphore when memory is critical,
# preventing work from being queued that would OOM mid-stream.
_MEMORY_GATE_THRESHOLD = float(os.environ.get("MEMORY_GATE_PCT", "90.0"))
_last_memory_pct: float = 0.0  # pushed here by cluster_backends.py health cycle

try:
    _SEMAPHORE_TIMEOUT = float(os.environ.get("SEMAPHORE_TIMEOUT_MS", "50")) / 1000.0
except ValueError:
    _SEMAPHORE_TIMEOUT = 0.050
    logger.warning("Invalid SEMAPHORE_TIMEOUT_MS value — must be a number. Using default: 50ms")

# ── Module-level mutable singletons (set by lifespan) ────────────────────────

_request_semaphore: asyncio.Semaphore | None = None

_workspace_semaphores: dict[str, asyncio.Semaphore] = {}
_workspace_sem_lock = asyncio.Lock()
_api_key_semaphores: dict[str, asyncio.Semaphore] = {}
_api_key_sem_lock = asyncio.Lock()


# ── Per-workspace semaphore helpers ───────────────────────────────────────────


def _get_workspace_concurrency_limit(workspace_id: str) -> int:
    """Resolve the per-workspace concurrent-request cap.

    Three-layer override chain (highest priority first):

    1. ``WORKSPACE_CONCURRENCY_<ID>`` environment variable
       (e.g. ``WORKSPACE_CONCURRENCY_AUTO_CODING=4``). The
       transformation maps kebab-case workspace ids to upper
       snake-case for env-var convention.
    2. ``max_concurrent`` field on the workspace's
       ``WORKSPACES`` entry (developer-time default).
    3. ``PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY`` environment
       variable, or the hard-coded fallback ``5`` (a single
       workspace can hold at most 25% of the default global
       cap of 20).

    The cap controls the per-workspace ``asyncio.Semaphore`` lazily
    created in ``_acquire_workspace_sem``. Bursts beyond the cap
    return HTTP 429 to the caller and increment
    ``portal5_workspace_semaphore_busy_total``.

    Args:
        workspace_id: Workspace id from the request (kebab case;
            transformed to ``UPPER_SNAKE`` for env-var lookup).

    Returns:
        Concurrent-request cap, ≥ 1.
    """
    from portal.platform.inference.router.workspaces import WORKSPACES

    env_key = f"WORKSPACE_CONCURRENCY_{workspace_id.upper().replace('-', '_')}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    ws = WORKSPACES.get(workspace_id, {})
    if "max_concurrent" in ws:
        return ws["max_concurrent"]
    return int(os.environ.get("PORTAL5_DEFAULT_WORKSPACE_CONCURRENCY", "5"))


async def _acquire_workspace_sem(workspace_id: str) -> asyncio.Semaphore:
    """Return the workspace's semaphore, creating it on first access.

    Lazy creation: the first request for a given ``workspace_id``
    builds an ``asyncio.Semaphore(limit)`` where ``limit`` comes from
    ``_get_workspace_concurrency_limit``, caches it in the
    module-level ``_workspace_semaphores`` dict, and returns it.
    Every subsequent request for the same workspace returns the
    cached semaphore.

    Race-safe via ``_workspace_sem_lock``: two concurrent requests
    for a newly-added workspace cannot both create competing
    semaphores. Without the lock, the second creation would
    overwrite the first and double the effective cap.

    The semaphores live for the process lifetime — there is no
    eviction path. Adding a new workspace via YAML + pipeline
    restart adds one ``Semaphore`` object to the process; removing
    a workspace leaves a stranded semaphore that is never used
    again (negligible memory).

    Args:
        workspace_id: The workspace key. Unknown ids still get a
            semaphore sized by the default cap.

    Returns:
        The workspace's ``asyncio.Semaphore``. Caller is expected
        to ``acquire()`` it with ``asyncio.wait_for`` and handle
        timeout as HTTP 429.
    """
    from portal.platform.inference.router.workspaces import WORKSPACES

    async with _workspace_sem_lock:
        sem_key = workspace_id if workspace_id in WORKSPACES else "_unknown"
        sem = _workspace_semaphores.get(sem_key)
        if sem is None:
            limit = _get_workspace_concurrency_limit(workspace_id)
            sem = asyncio.Semaphore(limit)
            _workspace_semaphores[sem_key] = sem
            logger.info("Workspace semaphore created: %s limit=%d", sem_key, limit)
        return sem


# ── Per-API-key semaphore helpers ─────────────────────────────────────────────


def _api_key_limit(key_hash: str) -> int:
    """Resolve the per-API-key concurrent-request cap.

    Two-layer override chain:

    1. ``API_KEY_CONCURRENCY_<PREFIX>`` env var, where ``<PREFIX>``
       is the first 8 hex chars of the key's SHA-256, uppercased
       (e.g. ``API_KEY_CONCURRENCY_A3F2D1B0=20``). Hash prefix —
       not raw key — so env vars are safe to grep and inspect;
       env vars carrying raw secrets leak via ``ps``, ``/proc``,
       and container inspection.
    2. ``PORTAL5_DEFAULT_API_KEY_CONCURRENCY`` env var, or the
       hard-coded fallback ``10`` — twice the default workspace
       cap because an API key in production is typically a service
       account running many parallel workspace queries; it should
       be able to use multiple workspaces simultaneously without
       hitting the per-key limit before the per-workspace limit
       fires.

    8-char hash prefixes provide ~32 bits of identifier space;
    collisions are theoretically possible but the pipeline's API
    key population is small in practice.

    Args:
        key_hash: Full SHA-256 hex digest of the API key. Only the
            first 8 chars are used for the env-var key.

    Returns:
        Concurrent-request cap for this API key, ≥ 1.
    """
    prefix = key_hash[:8]
    env_key = f"API_KEY_CONCURRENCY_{prefix.upper()}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    return int(os.environ.get("PORTAL5_DEFAULT_API_KEY_CONCURRENCY", "10"))


async def _acquire_api_key_sem(api_key: str) -> asyncio.Semaphore | None:
    """Return the per-API-key semaphore, creating it on first access.

    Mirrors ``_acquire_workspace_sem`` but keyed by SHA-256 hash of
    the API key. The hashing is deliberate: cached semaphores live
    in ``_api_key_semaphores`` for the process lifetime, and storing
    raw keys as dict keys would leave them in memory in readable
    form. Hash digests are one-way — a memory dump or accidental
    debug-print shows hex, not credentials.

    ``hashlib`` is imported lazily inside the function so tests that
    never present an API key don't pay the import cost.

    Returns ``None`` when ``api_key`` is empty, which is the caller's
    signal to skip per-key concurrency enforcement. This handles two
    cases: single-user deployments with no API-key setup, and
    malformed-auth-header edge cases that ``_verify_key`` accepted.

    Race-safe via ``_api_key_sem_lock`` — same pattern as the
    workspace semaphore.

    Args:
        api_key: Raw API key from the ``Authorization`` header
            (Bearer token, prefix stripped). Empty string yields
            ``None``.

    Returns:
        The per-key ``asyncio.Semaphore``, or ``None`` for empty
        input.
    """
    if not api_key:
        return None
    import hashlib

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    async with _api_key_sem_lock:
        sem = _api_key_semaphores.get(key_hash)
        if sem is None:
            limit = _api_key_limit(key_hash)
            sem = asyncio.Semaphore(limit)
            _api_key_semaphores[key_hash] = sem
        return sem


# ── RequestSlot ───────────────────────────────────────────────────────────────


class RequestSlot:
    """Owns the three request semaphores and the concurrent-requests gauge
    for exactly one request. Single release authority — replaces the
    historical five-release-site pattern in chat_completions.

    Acquisition is staged (global → api-key → workspace → mark_active),
    mirroring the original order because workspace is unknown until
    routing resolves. Release is one idempotent method: reverse-order
    semaphore release + gauge dec if held.
    """

    def __init__(self) -> None:
        self._held: list[asyncio.Semaphore] = []
        self._gauge_held = False
        self._detached = False
        self._released = False

    async def acquire_global(self) -> None:
        """Acquire the global request semaphore.

        Raises:
            HTTPException 503: memory critical, semaphore not initialised, or timeout.
        """
        if _last_memory_pct >= _MEMORY_GATE_THRESHOLD:
            raise HTTPException(
                status_code=503,
                detail=f"Server memory critical ({_last_memory_pct:.0f}%) — please retry in a moment.",
                headers={"Retry-After": "30"},
            )
        if _request_semaphore is None:
            raise HTTPException(status_code=503, detail="Request semaphore not initialised")
        try:
            await asyncio.wait_for(_request_semaphore.acquire(), timeout=_SEMAPHORE_TIMEOUT)
        except TimeoutError:
            raise HTTPException(
                status_code=503,
                detail="Server busy — too many concurrent requests. Please retry.",
                headers={"Retry-After": "5"},
            ) from None
        self._held.append(_request_semaphore)

    async def acquire_api_key(self, raw_key: str) -> None:
        """Acquire the per-API-key semaphore (no-op for empty key).

        Raises:
            HTTPException 429: timeout.
        """
        sem = await _acquire_api_key_sem(raw_key)
        if sem is None:
            return
        try:
            await asyncio.wait_for(sem.acquire(), timeout=_SEMAPHORE_TIMEOUT)
        except TimeoutError:
            raise HTTPException(
                status_code=429,
                detail="API key at concurrency limit. Please retry.",
                headers={"Retry-After": "5"},
            ) from None
        self._held.append(sem)

    async def acquire_workspace(self, workspace_id: str) -> None:
        """Acquire the per-workspace semaphore.

        Raises:
            HTTPException 429: timeout.
        """
        from portal.platform.inference.router.metrics import _workspace_semaphore_busy_total

        sem = await _acquire_workspace_sem(workspace_id)
        try:
            await asyncio.wait_for(sem.acquire(), timeout=_SEMAPHORE_TIMEOUT)
        except TimeoutError:
            if _workspace_semaphore_busy_total is not None:
                _workspace_semaphore_busy_total.labels(workspace=workspace_id).inc()
            raise HTTPException(
                status_code=429,
                detail=f"Workspace '{workspace_id}' at concurrency limit. Try again shortly.",
                headers={"Retry-After": "5"},
            ) from None
        self._held.append(sem)

    def mark_active(self) -> None:
        """Increment the concurrent-requests gauge and update peak tracking."""
        import portal.platform.inference.router.metrics as _metrics_mod
        import portal.platform.inference.router.state as _state_mod

        _metrics_mod._concurrent_requests.inc()
        self._gauge_held = True
        _state_mod._peak_concurrent = max(
            _state_mod._peak_concurrent,
            int(_metrics_mod._concurrent_requests._value.get()),
        )

    def detach(self) -> RequestSlot:
        """Transfer ownership to a streaming generator; return self for chaining."""
        self._detached = True
        return self

    def release(self) -> None:
        """Release all held semaphores in reverse order; dec gauge if held. Idempotent."""
        if self._released:
            return
        self._released = True
        import portal.platform.inference.router.metrics as _metrics_mod

        if self._gauge_held:
            _metrics_mod._concurrent_requests.dec()
            self._gauge_held = False
        for sem in reversed(self._held):
            sem.release()
        self._held.clear()

    def release_if_attached(self) -> None:
        """No-op when detached; otherwise release. Called from handler finally."""
        if not self._detached:
            self.release()
