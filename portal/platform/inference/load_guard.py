"""Host-memory admission for model loads across Ollama and oMLX.

Ollama and oMLX draw on one unified-memory pool, and each engine admits a load
from its own view. On 2026-10-07 Ollama started a 22.7 GiB load with 10 GiB
system-free while oMLX loaded a 27B model; swap ran out, jetsam could not recover
and the hardware watchdog reset the Mac
(``docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md``). The pipeline's own
``MEMORY_GATE_PCT`` reads ``vm_stat``, which its container lacks, so it saw 0 %.

Every pipeline request to either engine passes ``OllamaNativeTransport``, which
reports it here. The guard keeps four things true:

1. **What is busy is known.** In-flight requests are counted per (engine, model).
   Only idle models count as evictable (Ollama) or freeable (oMLX), so concurrent
   multi-model work never admits a load that fits only by evicting a model that
   is serving a sibling request.
2. **Cold loads are serialised, generation is not.** A load of a model that is
   not resident (either engine) takes one host-wide lock, held until the model
   shows as resident (or its request ends), not for the whole response. Seats
   load one after another and then generate concurrently. Serialising oMLX loads
   too closes the incident's race (both engines measuring the same free memory).
3. **Queue, then refuse.** An Ollama cold load that does not fit waits for
   in-flight work to drain, re-checking on every request completion and at least
   every 5 s, and frees idle oMLX models on each pass. It is refused with
   HTTP 507 only when the caller's wait runs out. The wait is the request's
   ``X-Portal-Load-Wait`` header (seconds; batch callers send a large value) or
   ``LOAD_GUARD_WAIT_S``. The 507 says "would exceed", which the router already
   cascades as a capacity rejection.
4. **Fit can be asked in advance.** ``plan()`` (route ``POST /admin/load-plan``)
   says whether a set of models fits together right now, so batch work can run
   in fit-sized waves instead of discovering the answer as refusals.

Headroom is oMLX's ``final_ceiling`` minus its resident model memory (oMLX derives
the ceiling from host free + inactive memory), plus idle Ollama residents, minus
``LOAD_GUARD_MARGIN_GB``. A model's footprint is the larger of weights ×
``LOAD_GUARD_FACTOR`` and the footprint observed the last time it was resident.
oMLX's own guard still decides oMLX loads; this module only serialises them.

Fail-open: when oMLX's status cannot be read, the load is admitted. Resident
models (the router, task-router, warm seats) never wait. ``LOAD_GUARD=0`` disables
admission (tracking stays on, it is free).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import os
import time
from collections import Counter
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from portal.platform.inference.omlx_auth import OmlxKeyAuth, omlx_api_key

logger = logging.getLogger(__name__)

_GIB = 1024**3
#: Weights on disk understate the loaded footprint (KV cache, compute buffers):
#: the crash's model was ~18 GB on disk and Ollama predicted 22.7 GiB at 32K ctx.
_FACTOR = float(os.environ.get("LOAD_GUARD_FACTOR", "1.25"))
_MARGIN = float(os.environ.get("LOAD_GUARD_MARGIN_GB", "2")) * _GIB
#: Default wait for a cold load (interactive traffic). Batch callers raise it per
#: request with X-Portal-Load-Wait.
_WAIT_S = float(os.environ.get("LOAD_GUARD_WAIT_S", "120"))
_MAX_WAIT_S = 3600.0
_OMLX_LOADING_WAIT_S = 60.0
#: How long a cold load may take to show as resident before the lock is
#: released anyway (the request's own end also releases it).
_LOAD_TIMEOUT_S = 600.0
_POLL_S = 0.5

OLLAMA = "ollama"
OMLX = "omlx"

_load_wait: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "portal_load_wait", default=None
)


def set_load_wait(header: str | None) -> None:
    """Record the incoming request's ``X-Portal-Load-Wait`` (seconds) for its loads."""
    try:
        value = float(header) if header else None
    except ValueError:
        value = None
    _load_wait.set(None if value is None else max(0.0, min(value, _MAX_WAIT_S)))


def load_wait_s() -> float:
    value = _load_wait.get()
    return _WAIT_S if value is None else value


class LoadRefusedError(Exception):
    """The cold load does not fit host memory within the caller's wait."""


#: The pipeline's guard (set by lifespan); None outside the pipeline process.
GUARD: LoadGuard | None = None


class LoadGuard:
    def __init__(
        self,
        omlx_url: Callable[[], str | None],
        pinned: Callable[[], str] = lambda: os.environ.get("LLM_ROUTER_MODEL", ""),
        client: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(timeout=10.0),
    ) -> None:
        self._omlx_url = omlx_url
        self._pinned = pinned
        self._client = client
        self._lock = asyncio.Lock()
        self._busy: Counter[tuple[str, str]] = Counter()
        self._changed = asyncio.Event()
        self._sizes: dict[tuple[str, str], int] = {}
        self._observed: dict[tuple[str, str], int] = {}

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("LOAD_GUARD", "1") != "0"

    # ── in-flight tracking ────────────────────────────────────────────────

    def begin(self, engine: str, model: str) -> Callable[[], None]:
        """Count one in-flight request; return its idempotent end()."""
        key = (engine, model)
        self._busy[key] += 1
        ended = False

        def end() -> None:
            nonlocal ended
            if ended:
                return
            ended = True
            self._busy[key] -= 1
            if self._busy[key] <= 0:
                del self._busy[key]
            # Wake every waiter, then arm a fresh event for the next change.
            event, self._changed = self._changed, asyncio.Event()
            event.set()

        return end

    def busy(self, engine: str, model: str) -> int:
        return self._busy.get((engine, model), 0)

    async def _wait_change(self, timeout: float) -> None:
        event = self._changed
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=max(0.0, timeout))

    # ── engine state ──────────────────────────────────────────────────────

    async def _resident(self, client: httpx.AsyncClient, base: str) -> dict[str, int]:
        models = (await client.get(f"{base}/api/ps")).json().get("models") or []
        return {m["name"]: int(m.get("size") or 0) for m in models}

    async def _need(self, client: httpx.AsyncClient, base: str, model: str) -> float:
        if (base, model) not in self._sizes:
            tags = (await client.get(f"{base}/api/tags")).json().get("models") or []
            for t in tags:
                self._sizes[(base, t["name"])] = int(t.get("size") or 0)
        estimate = self._sizes.get((base, model), 0) * _FACTOR
        return max(estimate, float(self._observed.get((OLLAMA, model), 0)))

    async def _omlx_status(self, client: httpx.AsyncClient) -> dict[str, Any] | None:
        url = self._omlx_url()
        if not url:
            return None
        try:
            r = await client.get(f"{url.rstrip('/')}/v1/models/status", auth=OmlxKeyAuth())
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    async def _headroom(self, client: httpx.AsyncClient) -> float | None:
        """Host bytes free for a new load outside oMLX, or None when unmeasurable.
        Waits (bounded) while oMLX is mid-load: that memory is not yet counted."""
        deadline = time.monotonic() + _OMLX_LOADING_WAIT_S
        while True:
            st = await self._omlx_status(client)
            if st is None:
                return None
            loading = [m["id"] for m in st.get("models") or [] if m.get("is_loading")]
            if not loading or time.monotonic() > deadline:
                if loading:
                    logger.warning("load_guard: oMLX still loading %s; measuring anyway", loading)
                return float(st.get("final_ceiling") or 0) - float(
                    st.get("current_model_memory") or 0
                )
            await asyncio.sleep(1.0)

    def _ollama_idle(
        self, resident: dict[str, int], exclude: frozenset[str] | set[str] = frozenset()
    ) -> float:
        pinned = self._pinned()
        return float(
            sum(
                size
                for name, size in resident.items()
                if name != pinned and name not in exclude and not self.busy(OLLAMA, name)
            )
        )

    async def _omlx_idle_models(
        self, client: httpx.AsyncClient, exclude: frozenset[str] | set[str] = frozenset()
    ) -> tuple[str, list[dict[str, Any]]]:
        """(oMLX url, its idle unpinned loaded models, least recently used first).
        Empty when a client outside the pipeline is using oMLX: its requests are
        invisible here, so no oMLX model can be known idle."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return "", []
        st = (await client.get(f"{url}/api/status", auth=OmlxKeyAuth())).json()
        tracked = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        if int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked:
            logger.info("load_guard: oMLX serves requests the pipeline did not send; not freeing")
            return url, []
        login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
        if login.status_code != 200:
            return url, []
        models = (await client.get(f"{url}/admin/api/models")).json()
        models = models.get("models", models) if isinstance(models, dict) else models
        idle = [
            m
            for m in models
            if m.get("loaded")
            and not m.get("pinned")
            and not m.get("is_loading")
            and m["id"] not in exclude
            and not self.busy(OMLX, m["id"])
        ]
        return url, sorted(idle, key=lambda m: float(m.get("last_access") or 0))

    async def _free_omlx(self, client: httpx.AsyncClient, want: float) -> float:
        """Unload idle oMLX models (LRU first) until `want` bytes are freed.
        The mirror of backend_introspect.free_ollama_for_omlx."""
        try:
            url, idle = await self._omlx_idle_models(client)
            freed = 0.0
            for m in idle:
                if freed >= want:
                    break
                r = await client.post(f"{url}/admin/api/models/{quote(m['id'], safe='')}/unload")
                if r.status_code == 200:
                    freed += float(m.get("actual_size") or m.get("estimated_size") or 0)
                    logger.info("load_guard: unloaded idle oMLX model %s", m["id"])
            return freed
        except Exception as e:
            logger.warning("load_guard: could not free oMLX memory: %s", e)
            return 0.0

    async def _settled_headroom(self, client: httpx.AsyncClient, before: float) -> float:
        """Headroom after an unload, once oMLX's accounting reflects it (≤ 15 s)."""
        deadline = time.monotonic() + 15.0
        headroom = before
        while time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            headroom = await self._headroom(client) or before
            if headroom > before:
                break
        return headroom

    # ── the cold-load lock ───────────────────────────────────────────────

    async def _acquire(self, deadline: float, what: str) -> _Release:
        # Uncontended: take it now. wait_for with a zero timeout refuses even a
        # free lock, which would turn X-Portal-Load-Wait: 0 into "always refuse".
        if self._lock.locked():
            try:
                await asyncio.wait_for(
                    self._lock.acquire(), timeout=max(0.0, deadline - time.monotonic())
                )
            except TimeoutError:
                raise LoadRefusedError(
                    f"cold load of {what} would exceed its wait for another model load "
                    f"({load_wait_s():.0f}s)"
                ) from None
        else:
            await self._lock.acquire()
        return _Release(self._lock)

    async def _release_when_resident(
        self, engine: str, base: str, model: str, release: _Release
    ) -> None:
        """Release the lock once the model is resident; record its real footprint.
        Stops early when the request's own end already released it."""
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        try:
            async with self._client() as client:
                while time.monotonic() < deadline and not release.released:
                    try:
                        if engine == OLLAMA:
                            resident = await self._resident(client, base)
                            if model in resident:
                                self._observed[(OLLAMA, model)] = max(
                                    resident[model], self._observed.get((OLLAMA, model), 0)
                                )
                                return
                        else:
                            st = await self._omlx_status(client)
                            entry = _omlx_entry(st, model)
                            if entry is None or (
                                entry.get("loaded") and not entry.get("is_loading")
                            ):
                                return
                    except Exception:
                        pass
                    await asyncio.sleep(_POLL_S)
        finally:
            release()

    # ── admission ─────────────────────────────────────────────────────────

    async def admit(self, base: str, model: str) -> Callable[[], None] | None:
        """Admit an Ollama request. Return the lock's release callable when this is
        a cold load (also released automatically once the model is resident), None
        when no lock is needed. Raises LoadRefusedError."""
        if not self.enabled() or not model:
            return None
        deadline = time.monotonic() + load_wait_s()
        held: list[_Release] = []
        try:
            release = await self._admit_ollama(base, model, deadline, held)
        except asyncio.CancelledError:
            # The caller gave up (client disconnect, W3): never leak the
            # host-wide cold-load lock, or every later cold load deadlocks.
            for r in held:
                r()
            raise
        if release is None:
            return None
        asyncio.get_running_loop().create_task(
            self._release_when_resident(OLLAMA, base, model, release)
        )
        return release

    async def _admit_ollama(
        self, base: str, model: str, deadline: float, held: list[_Release]
    ) -> _Release | None:
        async with self._client() as client:
            try:
                if model in await self._resident(client, base):
                    return None
            except Exception:
                return None  # cannot see Ollama's state: fail open
            release = await self._acquire(deadline, model)
            held.append(release)
            try:
                while True:
                    resident = await self._resident(client, base)
                    if model in resident:
                        release()
                        return None
                    need = await self._need(client, base, model)
                    headroom = await self._headroom(client)
                    if headroom is None or not need:
                        break  # unmeasurable: fail open
                    idle = self._ollama_idle(resident)
                    available = headroom + idle - _MARGIN
                    if need <= available:
                        break
                    if await self._free_omlx(client, need - available):
                        # Re-measure whatever the deadline: the unload is done, and
                        # each pass frees different (idle) models, so this ends.
                        await self._settled_headroom(client, headroom)
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LoadRefusedError(
                            f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
                            f"exceed host headroom {available / _GIB:.1f} GiB (oMLX headroom "
                            f"{headroom / _GIB:.1f} + idle Ollama {idle / _GIB:.1f} - margin "
                            f"{_MARGIN / _GIB:.0f}) after waiting {load_wait_s():.0f}s"
                        )
                    logger.info(
                        "load_guard: %s needs %.1f GiB, %.1f available; waiting for in-flight work",
                        model,
                        need / _GIB,
                        available / _GIB,
                    )
                    # Wait without the lock: other cold loads that fit go ahead.
                    release()
                    await self._wait_change(min(5.0, remaining))
                    release = await self._acquire(deadline, model)
                    held.append(release)
            except LoadRefusedError:
                release()
                raise
            except Exception as e:
                logger.warning("load_guard: measurement failed for %s, admitting: %s", model, e)
        return release

    async def admit_omlx(self, model: str) -> Callable[[], None] | None:
        """Serialise an oMLX cold load with every other cold load (oMLX's own guard
        decides whether it fits). Return the lock's release callable or None."""
        if not self.enabled() or not model:
            return None
        deadline = time.monotonic() + load_wait_s()
        release: _Release | None = None
        try:
            async with self._client() as client:
                entry = _omlx_entry(await self._omlx_status(client), model)
                if entry is None or entry.get("loaded"):
                    return None
                release = await self._acquire(deadline, model)
                entry = _omlx_entry(await self._omlx_status(client), model)
                if entry is None or entry.get("loaded"):
                    release()
                    return None
        except asyncio.CancelledError:
            if release is not None:
                release()  # never leak the cold-load lock to a cancelled caller
            raise
        asyncio.get_running_loop().create_task(
            self._release_when_resident(OMLX, "", model, release)
        )
        return release

    async def plan(self, ollama_base: str, models: list[tuple[str, str]]) -> dict[str, Any]:
        """Whether `models` ((engine, model) pairs) fit together right now.

        Pure measurement, no side effects. Counts what the set would add (models
        not yet resident), against headroom plus idle Ollama residents and idle
        oMLX models outside the set."""
        names = {m for _, m in models}
        async with self._client() as client:
            resident = await self._resident(client, ollama_base)
            st = await self._omlx_status(client)
            headroom = (
                None
                if st is None
                else (
                    float(st.get("final_ceiling") or 0) - float(st.get("current_model_memory") or 0)
                )
            )
            need = 0.0
            per_model = []
            for engine, model in models:
                if engine == OLLAMA:
                    loaded = model in resident
                    size = 0.0 if loaded else await self._need(client, ollama_base, model)
                else:
                    entry = _omlx_entry(st, model) or {}
                    loaded = bool(entry.get("loaded"))
                    size = 0.0 if loaded else float(entry.get("estimated_size") or 0)
                need += size
                per_model.append(
                    {"engine": engine, "model": model, "resident": loaded, "adds_gib": size / _GIB}
                )
            idle_ollama = self._ollama_idle(resident, exclude=names)
            try:
                _, idle = await self._omlx_idle_models(client, exclude=names)
            except Exception:
                idle = []
            freeable_omlx = float(
                sum(float(m.get("actual_size") or m.get("estimated_size") or 0) for m in idle)
            )
        available = None if headroom is None else headroom + idle_ollama + freeable_omlx - _MARGIN
        return {
            "fits": None if available is None else need <= available,
            "need_gib": need / _GIB,
            "available_gib": None if available is None else available / _GIB,
            "headroom_gib": None if headroom is None else headroom / _GIB,
            "idle_ollama_gib": idle_ollama / _GIB,
            "freeable_omlx_gib": freeable_omlx / _GIB,
            "models": per_model,
        }


class _Release:
    """Idempotent release of the cold-load lock; knows whether it has run."""

    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock
        self.released = False

    def __call__(self) -> None:
        if not self.released:
            self.released = True
            self._lock.release()


def _omlx_entry(status: dict[str, Any] | None, model: str) -> dict[str, Any] | None:
    for m in (status or {}).get("models") or []:
        if m.get("id") == model:
            return m  # type: ignore[no-any-return]
    return None
