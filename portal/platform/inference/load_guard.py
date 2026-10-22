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
   every 5 s, and frees idle oMLX models on each pass. A free it issues stays
   pending until /api/ps drops the model and oMLX's ceiling covers its bytes. It is
   refused with HTTP 507 only when the caller's wait runs out. The wait is the
   request's ``X-Portal-Load-Wait`` header (seconds; batch callers send a large
   value) or ``LOAD_GUARD_WAIT_S``. The 507 says "would exceed", which the router
   already cascades as a capacity rejection.
4. **Fit can be asked in advance.** ``plan()`` (route ``POST /admin/load-plan``)
   says whether a set of models fits together right now, so batch work can run
   in fit-sized waves instead of discovering the answer as refusals.

Headroom is oMLX's ``final_ceiling`` minus its resident model memory (oMLX derives
the ceiling from host free + inactive memory), plus idle Ollama residents, minus
``LOAD_GUARD_MARGIN_GB``. ``LOAD_GUARD_CEILING_GB`` replaces that ceiling with a
fixed budget; the balanced tier's ceiling follows free memory (P5-OMLX-CEILING-001).
A model's footprint is the larger of weights × ``LOAD_GUARD_FACTOR`` and the
footprint observed the last time it was resident.
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
#: A fixed model-memory budget (GiB). 0 budgets against oMLX's live ceiling, which
#: the balanced tier derives from host free memory, so a verdict moves with the host.
_CEILING = float(os.environ.get("LOAD_GUARD_CEILING_GB", "0") or 0) * _GIB
#: Default wait for a cold load (interactive traffic). Batch callers raise it per
#: request with X-Portal-Load-Wait.
_WAIT_S = float(os.environ.get("LOAD_GUARD_WAIT_S", "120"))
_MAX_WAIT_S = 3600.0
#: How long a cold load may take to show as resident before the lock is
#: released anyway (the request's own end also releases it).
_LOAD_TIMEOUT_S = 600.0
_POLL_S = 0.5
#: Expected settle of a guard-issued Ollama free, for a warning only: measured admin
#: unloads p50 0.78 s, p95 1.93 s, max 2.29 s (n=114, oMLX 0.7.2, 2026-10-22), doubled.
_FREE_SETTLE_EXPECTED_S = 4.6

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


def _waited_s(deadline: float) -> float:
    """Seconds of the caller's own load wait already spent (one decimal in refusals)."""
    return load_wait_s() - max(0.0, deadline - time.monotonic())


class LoadRefusedError(Exception):
    """The cold load does not fit host memory within the caller's wait."""


#: The pipeline's guard (set by lifespan); None outside the pipeline process.
GUARD: LoadGuard | None = None

#: How long the model a request just failed over FROM stays out of eviction (P-2). On the
#: V2 closeout run an oMLX timeout failed over to an Ollama cold load, load_guard freed the
#: oMLX seat to make room, and every reload of it then got HTTP 507.
FAILOVER_PROTECT_S = float(os.environ.get("LOAD_GUARD_FAILOVER_PROTECT_S", "300"))


def protect_failover(engine: str, model: str) -> None:
    """Keep the model a request just failed over from loaded for a cool-down (P-2)."""
    if GUARD is not None and engine in (OLLAMA, OMLX) and model:
        GUARD.protect(engine, model)
        logger.info(
            "load_guard: protecting %s:%s for %.0fs after a failover",
            engine,
            model,
            FAILOVER_PROTECT_S,
        )


def _budget_bytes(status: dict[str, Any]) -> float:
    """The ceiling to budget against: the fixed one when set, else oMLX's live one."""
    return _CEILING if _CEILING > 0 else float(status.get("final_ceiling") or 0)


class _Free:
    """A guard-issued Ollama free: its pages must reach oMLX's ceiling."""

    __slots__ = ("baseline", "size", "started")

    def __init__(self, size: float) -> None:
        self.baseline: float | None = None
        self.size = size
        self.started = time.monotonic()


class LoadGuard:
    def __init__(
        self,
        omlx_url: Callable[[], str | None],
        pinned: Callable[[], str] = lambda: os.environ.get("LLM_ROUTER_MODEL", ""),
        client: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(timeout=10.0),
    ) -> None:
        self._omlx_url = omlx_url
        self._protected: dict[tuple[str, str], float] = {}  # (engine, model) -> monotonic deadline
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

    def protect(self, engine: str, model: str, seconds: float | None = None) -> None:
        """Exclude ``model`` from eviction for ``seconds`` (default FAILOVER_PROTECT_S)."""
        span = FAILOVER_PROTECT_S if seconds is None else seconds
        self._protected[(engine, model)] = time.monotonic() + span

    def protected(self, engine: str) -> set[str]:
        """The models of ``engine`` currently protected from eviction."""
        now = time.monotonic()
        return {m for (e, m), until in self._protected.items() if e == engine and until > now}

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

    async def _headroom(self, client: httpx.AsyncClient) -> tuple[float, float] | None:
        """Current oMLX headroom, without waiting for transition state."""
        st = await self._omlx_status(client)
        if st is None:
            return None
        used = float(st.get("current_model_memory") or 0)
        return _budget_bytes(st) - used, used

    async def _omlx_used(self, client: httpx.AsyncClient) -> float | None:
        """oMLX's memory counter: what an unload actually releases."""
        status = await self._omlx_status(client)
        if status is None or status.get("current_model_memory") is None:
            return None
        return float(status["current_model_memory"])

    @staticmethod
    def _track_counter(used: float, last_used: float | None, recheck: bool) -> tuple[float, bool]:
        """Remember the counter and flag a drop since the previous pass."""
        return used, recheck or (last_used is not None and used < last_used)

    async def host_free_bytes(self, base: str) -> float | None:
        """Memory a new load could use without waiting: oMLX's headroom plus idle
        Ollama residents. None when oMLX's status is unreadable. Feeds the
        pipeline's admission gate (MEMORY_GATE_MIN_FREE_GB)."""
        async with self._client() as client:
            st = await self._omlx_status(client)
            if st is None or st.get("final_ceiling") is None:
                return None
            headroom = _budget_bytes(st) - float(st.get("current_model_memory") or 0)
            try:
                resident = await self._resident(client, base)
            except Exception:
                resident = {}
            return headroom + self._ollama_idle(resident)

    def _ollama_idle(
        self, resident: dict[str, int], exclude: frozenset[str] | set[str] = frozenset()
    ) -> float:
        pinned = self._pinned()
        return float(
            sum(
                self._ollama_size(name, size)
                for name, size in resident.items()
                if name != pinned
                and name not in exclude
                and name not in self.protected(OLLAMA)
                and not self.busy(OLLAMA, name)
            )
        )

    def _ollama_size(self, name: str, size: int) -> int:
        return max(size, self._observed.get((OLLAMA, name), 0))

    def _ollama_available(self, headroom: float, resident: dict[str, int], idle: float) -> float:
        if _CEILING > 0:
            headroom -= sum(self._ollama_size(name, size) for name, size in resident.items())
        return headroom + idle

    async def _omlx_idle_models(
        self, client: httpx.AsyncClient, exclude: frozenset[str] | set[str] = frozenset()
    ) -> tuple[str, list[dict[str, Any]]]:
        """(oMLX url, its idle unpinned loaded models, least recently used first).
        Empty when a client outside the pipeline is using oMLX: its requests are
        invisible here, so no oMLX model can be known idle."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return "", []
        response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
        if response.status_code != 200:
            logger.warning(
                "load_guard: oMLX status returned HTTP %d; not freeing oMLX memory",
                response.status_code,
            )
            return url, []
        st = response.json()
        tracked = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        if int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked:
            logger.info("load_guard: oMLX serves requests the pipeline did not send; not freeing")
            return url, []
        login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
        if login.status_code != 200:
            return url, []
        response = await client.get(f"{url}/admin/api/models")
        if response.status_code != 200:
            logger.warning(
                "load_guard: oMLX model list returned HTTP %d; not freeing oMLX memory",
                response.status_code,
            )
            return url, []
        models = response.json()
        models = models.get("models", models) if isinstance(models, dict) else models
        idle = [
            m
            for m in models
            if m.get("loaded")
            and not m.get("pinned")
            and not m.get("is_loading")
            and m["id"] not in exclude
            and m["id"] not in self.protected(OMLX)
            and not self.busy(OMLX, m["id"])
        ]
        return url, sorted(idle, key=lambda m: float(m.get("last_access") or 0))

    @staticmethod
    def _has_loading(value: Any) -> bool:
        if isinstance(value, (int, float)):
            return value > 0
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "none"}
        return bool(value)

    @staticmethod
    def _loading_among(models: Any, protected: set[str]) -> bool:
        """Whether any reported model is loading and within reach of eviction."""
        return any(
            isinstance(m, dict) and m.get("is_loading") and m.get("id") not in protected
            for m in models or []
        )

    async def _omlx_loading(self, client: httpx.AsyncClient) -> bool:
        """Whether oMLX reports a load; a protected model's load is never acted on."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return False
        protected = self.protected(OMLX)
        status_loading = False
        try:
            status = await self._omlx_status(client)
            if status is None:
                return False
            status_loading = self._loading_among(status.get("models"), protected)
            response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
            if response.status_code != 200:
                return status_loading
            runtime = response.json()
            if not isinstance(runtime, dict):
                return status_loading
        except Exception:
            return status_loading
        runtime_loading = self._has_loading(runtime.get("models_loading"))
        if status_loading == runtime_loading:
            return status_loading
        try:
            login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
            if login.status_code != 200:
                return status_loading
            response = await client.get(f"{url}/admin/api/models")
            if response.status_code != 200:
                return status_loading
            models = response.json()
            models = models.get("models", models) if isinstance(models, dict) else models
            return self._loading_among(models, protected)
        except Exception:
            return status_loading

    async def _omlx_foreign_active(self, client: httpx.AsyncClient) -> bool:
        """Whether oMLX serves requests the pipeline is not tracking."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return False
        try:
            response = await client.get(f"{url}/api/status", auth=OmlxKeyAuth())
            if response.status_code != 200:
                return False
            st = response.json()
            if not isinstance(st, dict):
                return False
        except Exception:
            return False
        tracked = sum(n for (engine, _), n in self._busy.items() if engine == OMLX)
        return int(st.get("active_requests") or 0) + int(st.get("waiting_requests") or 0) > tracked

    async def _free_omlx(
        self, client: httpx.AsyncClient, want: float, used: float
    ) -> tuple[float, dict[str, float], float | None, float]:
        """Unload idle oMLX models; report the drop, queued work, post state, 200 bytes."""
        try:
            url, idle = await self._omlx_idle_models(client)
            queued: dict[str, float] = {}
            posted = 0.0
            covered = 0.0  # 200 plus queued 202 bytes: a queued unload can cover the shortage
            any_post = False
            for m in idle:
                if covered >= want:
                    break
                r = await client.post(f"{url}/admin/api/models/{quote(m['id'], safe='')}/unload")
                any_post = True
                size = float(m.get("estimated_size") or m.get("actual_size") or 0)
                if r.status_code == 200:
                    posted += size
                    covered += size
                    logger.info("load_guard: unloaded idle oMLX model %s", m["id"])
                elif r.status_code == 202:
                    queued[m["id"]] = size
                    covered += size
            if not any_post:
                return 0.0, queued, None, 0.0
            after = await self._omlx_used(client)
            freed = 0.0 if after is None else max(0.0, used - after)
            return freed, queued, after, posted
        except Exception as e:
            logger.warning("load_guard: could not free oMLX memory: %s", e)
            return 0.0, {}, None, 0.0

    async def _free_ollama(
        self, client: httpx.AsyncClient, base: str, resident: dict[str, int]
    ) -> set[str]:
        """Request unload of idle Ollama residents and return the requested model names."""
        idle = [n for n, size in resident.items() if size and self._ollama_idle({n: size}) > 0]
        requested: set[str] = set()
        for name in idle:
            try:
                response = await client.post(
                    f"{base}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30.0
                )
            except Exception as e:
                logger.warning("load_guard: could not unload idle Ollama model %s: %s", name, e)
                continue
            if not response.is_success:
                logger.warning(
                    "load_guard: unload of idle Ollama model %s returned HTTP %d",
                    name,
                    response.status_code,
                )
                continue
            requested.add(name)
            logger.info("load_guard: unloaded idle Ollama model %s", name)
        return requested

    @staticmethod
    def _ollama_refusal(
        model: str,
        need: float,
        available: float,
        headroom: float,
        idle: float,
        quiet: bool,
        waited: float,
    ) -> LoadRefusedError:
        reason = (
            f"after waiting {waited:.1f}s" if not quiet else "with nothing in flight to wait for"
        )
        return LoadRefusedError(
            f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
            f"exceed host headroom {available / _GIB:.1f} GiB (oMLX headroom "
            f"{headroom / _GIB:.1f} + idle Ollama {idle / _GIB:.1f} - margin "
            f"{_MARGIN / _GIB:.0f}) {reason}"
        )

    async def _wait_if_omlx_loading(
        self,
        client: httpx.AsyncClient,
        model: str,
        deadline: float,
        release: _Release,
        held: list[_Release],
    ) -> tuple[_Release, bool]:
        release()
        saw_loading = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if saw_loading:
                        raise LoadRefusedError(
                            f"Cannot load {model}: engine model transition still active "
                            f"after waiting {_waited_s(deadline):.1f}s"
                        )
                    break
                try:
                    loading = await asyncio.wait_for(self._omlx_loading(client), timeout=remaining)
                except TimeoutError:
                    if saw_loading:
                        raise LoadRefusedError(
                            f"Cannot load {model}: engine model transition still active "
                            f"after waiting {_waited_s(deadline):.1f}s"
                        ) from None
                    break
                if not loading:
                    break
                saw_loading = True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LoadRefusedError(
                        f"Cannot load {model}: engine model transition still active "
                        f"after waiting {_waited_s(deadline):.1f}s"
                    )
                await self._wait_change(min(_POLL_S, remaining))
            release = await self._acquire(deadline, model)
            held.append(release)
            return release, saw_loading
        except BaseException:
            release()
            raise

    async def _wait_if_ollama_capacity_may_change(
        self,
        client: httpx.AsyncClient,
        model: str,
        deadline: float,
        release: _Release,
        held: list[_Release],
        need: float,
        available: float,
        headroom: float,
        idle: float,
        used: float,
        activity_seen: bool,
        pending_change: bool,
        pending_free_names: list[str],
    ) -> tuple[_Release, bool]:
        remaining = deadline - time.monotonic()
        release()
        foreign_active = False
        if remaining > 0:
            try:
                foreign_active = await asyncio.wait_for(
                    self._omlx_foreign_active(client), timeout=remaining
                )
            except TimeoutError:
                if pending_free_names:
                    raise self._free_settle_refusal(
                        model, pending_free_names, need, available, _waited_s(deadline)
                    ) from None
                raise self._ollama_refusal(
                    model, need, available, headroom, idle, quiet=False, waited=_waited_s(deadline)
                ) from None
        changing = bool(self._busy) or foreign_active
        activity_seen = activity_seen or changing
        quiet = not (activity_seen or pending_change)
        remaining = deadline - time.monotonic()
        if quiet and remaining > 0:
            try:
                now = await asyncio.wait_for(self._omlx_used(client), timeout=remaining)
            except TimeoutError:
                now = None
            quiet = now is None or now >= used
            remaining = deadline - time.monotonic()
        if remaining <= 0 or quiet:
            if pending_free_names:
                raise self._free_settle_refusal(
                    model, pending_free_names, need, available, _waited_s(deadline)
                )
            raise self._ollama_refusal(
                model, need, available, headroom, idle, quiet, waited=_waited_s(deadline)
            )
        logger.info(
            "load_guard: %s needs %.1f GiB, %.1f available; waiting for engine activity",
            model,
            need / _GIB,
            available / _GIB,
        )
        await self._wait_change(min(5.0, remaining, max(_POLL_S, 0.01)))
        release = await self._acquire(deadline, model)
        held.append(release)
        return release, activity_seen

    async def _free_idle_memory(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        shortage: float,
    ) -> tuple[bool, dict[str, float], set[str], float | None, float]:
        omlx_freed, omlx_queued, after, synchronous = await self._free_omlx(client, shortage, used)
        if omlx_freed < shortage and idle:
            ollama_requested = await self._free_ollama(client, base, resident)
        else:
            ollama_requested = set()
        did_free = bool(omlx_freed or omlx_queued or ollama_requested)
        return did_free, omlx_queued, ollama_requested, after, synchronous

    async def _free_for_load(
        self,
        client: httpx.AsyncClient,
        base: str,
        resident: dict[str, int],
        idle: float,
        used: float,
        shortage: float,
        pending_omlx: dict[str, float],
        pending_ollama: dict[str, _Free],
    ) -> tuple[bool, float, float]:
        """Free idle memory and fold it in; return the queued baseline and post counter."""
        did_free, queued, requested, after, synchronous = await self._free_idle_memory(
            client, base, resident, idle, used, shortage
        )
        pending_omlx.update(queued)
        frees = {name: _Free(float(resident.get(name, 0))) for name in requested}
        if frees:
            status = await self._omlx_status(client)
            if status is not None:
                baseline = _budget_bytes(status) - float(status.get("current_model_memory") or 0)
                for free in frees.values():
                    free.baseline = baseline
        pending_ollama.update(frees)
        post = used if after is None else after
        return did_free, self._pending_baseline(used, after, synchronous), post

    @staticmethod
    def _retire_ollama_frees(
        pending: dict[str, _Free], resident: dict[str, int], headroom: float
    ) -> tuple[dict[str, _Free], list[tuple[str, float]]]:
        """Retire a free once /api/ps drops it and headroom covers its bytes."""
        now = time.monotonic()
        remaining: dict[str, _Free] = {}
        settled: list[tuple[str, float]] = []
        for name, free in pending.items():
            if free.baseline is None:
                free.baseline = headroom
            baseline = free.baseline
            landed = name not in resident and (_CEILING > 0 or headroom >= baseline + free.size)
            if landed:
                settled.append((name, now - free.started))
            else:
                remaining[name] = free
        return remaining, settled

    def _settle_ollama_frees(
        self,
        model: str,
        need: float,
        available: float,
        resident: dict[str, int],
        headroom: float,
        pending: dict[str, _Free],
        deadline: float,
    ) -> dict[str, _Free]:
        """Log landed frees, warn past the expected settle, and refuse only at the wait."""
        pending, settled = self._retire_ollama_frees(pending, resident, headroom)
        for name, elapsed in settled:
            if elapsed >= _FREE_SETTLE_EXPECTED_S:
                logger.warning(
                    "load_guard: free of %s settled in %.1fs (expected %.1fs)",
                    name,
                    elapsed,
                    _FREE_SETTLE_EXPECTED_S,
                )
            else:
                logger.info("load_guard: free of %s settled in %.1fs", name, elapsed)
        if pending and need > available and time.monotonic() >= deadline:
            raise self._free_settle_refusal(
                model, list(pending), need, available, _waited_s(deadline)
            )
        return pending

    @staticmethod
    def _free_settle_refusal(
        model: str, names: list[str], need: float, available: float, waited: float
    ) -> LoadRefusedError:
        freed = ", ".join(sorted(names))
        return LoadRefusedError(
            f"Cannot load {model}: free of {freed} did not settle within "
            f"the {waited:.1f}s load wait (projected {need / _GIB:.1f} GiB, host "
            f"headroom {available / _GIB:.1f} GiB)"
        )

    @staticmethod
    def _pending_baseline(used: float, after: float | None, synchronous: float) -> float:
        """Counter the queued drops are measured from: the pre-pass value less 200 bytes."""
        if after is None:
            return used
        return used - min(synchronous, max(0.0, used - after))

    async def _pending_omlx_unloads(
        self, client: httpx.AsyncClient, models: dict[str, float], used: float
    ) -> tuple[dict[str, float], bool, float]:
        """Retire queued unloads the counter drop covers, in post order."""
        if not models:
            return {}, False, used
        now = await self._omlx_used(client)
        if now is None or now >= used:
            return models, False, used
        drop = used - now
        remaining = dict(models)
        for name, charge in models.items():
            if charge > drop:
                break
            drop -= charge
            used -= charge
            del remaining[name]
        return remaining, len(remaining) < len(models), used

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
                    f"({_waited_s(deadline):.1f}s)"
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
            free_attempted = False
            activity_seen = False
            pending_omlx: dict[str, float] = {}
            pending_omlx_used = 0.0
            pending_ollama: dict[str, _Free] = {}
            last_used: float | None = None
            recheck = False
            try:
                while True:
                    resident = await self._resident(client, base)
                    if model in resident:
                        release()
                        return None
                    need = await self._need(client, base, model)
                    capacity = await self._headroom(client)
                    if capacity is None or not need:
                        break  # unmeasurable: fail open
                    headroom, used = capacity
                    last_used, recheck = self._track_counter(used, last_used, recheck)
                    idle = self._ollama_idle(resident)
                    available = self._ollama_available(headroom, resident, idle) - _MARGIN
                    if need > available and not free_attempted:
                        free_attempted = True
                        freed_or_queued, pending_omlx_used, last_used = await self._free_for_load(
                            client,
                            base,
                            resident,
                            idle,
                            used,
                            need - available,
                            pending_omlx,
                            pending_ollama,
                        )
                        if freed_or_queued:
                            continue
                    pending_omlx, settled, pending_omlx_used = await self._pending_omlx_unloads(
                        client, pending_omlx, pending_omlx_used
                    )
                    if settled:
                        recheck = False  # our own unload moved the counter
                        continue  # re-measure headroom before deciding
                    pending_ollama = self._settle_ollama_frees(
                        model, need, available, resident, headroom, pending_ollama, deadline
                    )
                    if need <= available:
                        break
                    release, loading_seen = await self._wait_if_omlx_loading(
                        client, model, deadline, release, held
                    )
                    if loading_seen:
                        continue
                    release, activity_seen = await self._wait_if_ollama_capacity_may_change(
                        client,
                        model,
                        deadline,
                        release,
                        held,
                        need,
                        available,
                        headroom,
                        idle,
                        used,
                        activity_seen,
                        bool(pending_omlx or pending_ollama or recheck),
                        list(pending_ollama),
                    )
                    recheck = False
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
                else (_budget_bytes(st) - float(st.get("current_model_memory") or 0))
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
                sum(float(m.get("estimated_size") or m.get("actual_size") or 0) for m in idle)
            )
        available = (
            None
            if headroom is None
            else self._ollama_available(headroom, resident, idle_ollama) + freeable_omlx - _MARGIN
        )
        busy_requests = sum(self._busy.values())
        return {
            "busy": busy_requests > 0,
            "busy_requests": busy_requests,
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
