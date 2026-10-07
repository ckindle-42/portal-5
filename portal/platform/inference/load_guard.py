"""Host-memory admission for cold Ollama model loads.

Ollama and oMLX draw on one unified-memory pool, and Ollama's scheduler admits a
load from its own view: on 2026-10-07 it started a 22.7 GiB load with 10 GiB
system-free (its log: ``predicted to exceed available memory, evicting``) while
oMLX was loading a 27B model of its own. Swap ran out, jetsam could not recover
and the hardware watchdog reset the Mac. The pipeline's own memory gate
(``MEMORY_GATE_PCT``) could not help: it reads ``vm_stat``, which the pipeline
container does not have, so it always saw 0 %.

Before a chat request reaches Ollama for a model that is NOT resident, the guard

1. serialises cold loads: one at a time host-wide, held until that response
   completes (resident models never wait: the router, task-router, warm seats);
2. waits while oMLX reports a model mid-load, since that memory is not yet
   visible as used;
3. when the load does not fit and oMLX is idle (no active or waiting request),
   unloads oMLX's idle unpinned models, least recently used first, then re-measures;
4. refuses with HTTP 507 when the model's estimated footprint still exceeds host
   headroom: oMLX's ``final_ceiling`` minus its resident model memory (oMLX
   derives the ceiling from host free + inactive memory) plus what Ollama can
   evict from its own residents. The message says "would exceed", which the
   router already classifies as a capacity rejection, so it cascades or reports
   instead of loading.

Fail-open: when oMLX's status cannot be read, the request is admitted (no
measurement, no block). ``LOAD_GUARD=0`` disables the guard.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
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
_WAIT_S = float(os.environ.get("LOAD_GUARD_WAIT_S", "900"))
_OMLX_LOADING_WAIT_S = 60.0


class LoadRefusedError(Exception):
    """The cold load does not fit host memory right now."""


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
        self._sizes: dict[tuple[str, str], int] = {}

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("LOAD_GUARD", "1") != "0"

    async def _resident(self, client: httpx.AsyncClient, base: str) -> dict[str, int]:
        models = (await client.get(f"{base}/api/ps")).json().get("models") or []
        return {m["name"]: int(m.get("size") or 0) for m in models}

    async def _size(self, client: httpx.AsyncClient, base: str, model: str) -> int:
        if (base, model) not in self._sizes:
            tags = (await client.get(f"{base}/api/tags")).json().get("models") or []
            for t in tags:
                self._sizes[(base, t["name"])] = int(t.get("size") or 0)
        return self._sizes.get((base, model), 0)

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
        """Host bytes free for a new load outside oMLX, or None when unmeasurable."""
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

    async def _free_omlx(self, client: httpx.AsyncClient, want: float) -> float:
        """Unload oMLX's idle, unpinned models (least recently used first) until
        `want` bytes are freed; return bytes freed. Only when oMLX has no active
        or waiting request — never pulls a model out from under a generation.
        The mirror of backend_introspect.free_ollama_for_omlx."""
        url = (self._omlx_url() or "").rstrip("/")
        if not url:
            return 0.0
        try:
            st = (await client.get(f"{url}/api/status", auth=OmlxKeyAuth())).json()
            if st.get("active_requests") or st.get("waiting_requests"):
                return 0.0
            login = await client.post(f"{url}/admin/api/login", json={"api_key": omlx_api_key()})
            if login.status_code != 200:
                return 0.0
            models = (await client.get(f"{url}/admin/api/models")).json()
            models = models.get("models", models) if isinstance(models, dict) else models
            idle = sorted(
                (
                    m
                    for m in models
                    if m.get("loaded") and not m.get("pinned") and not m.get("is_loading")
                ),
                key=lambda m: float(m.get("last_access") or 0),
            )
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

    async def admit(self, base: str, model: str) -> Callable[[], None] | None:
        """Return a release callable when the cold-load lock was taken, None when
        no guard applies (resident model, guard off). Raises LoadRefusedError."""
        if not self.enabled() or not model:
            return None
        async with self._client() as client:
            try:
                if model in await self._resident(client, base):
                    return None
            except Exception:
                return None  # cannot see Ollama's state: fail open
            try:
                await asyncio.wait_for(self._lock.acquire(), timeout=_WAIT_S)
            except TimeoutError:
                raise LoadRefusedError(
                    f"cold load of {model} would exceed the wait for another model load "
                    f"({_WAIT_S:.0f}s)"
                ) from None
            try:
                resident = await self._resident(client, base)
                if model in resident:
                    self._lock.release()
                    return None
                need = (await self._size(client, base, model)) * _FACTOR
                headroom = await self._headroom(client)
                if headroom is not None and need:
                    evictable = sum(s for n, s in resident.items() if n != self._pinned())
                    available = headroom + evictable - _MARGIN
                    if need > available and await self._free_omlx(client, need - available):
                        headroom = await self._settled_headroom(client, headroom)
                        available = headroom + evictable - _MARGIN
                    if need > available:
                        raise LoadRefusedError(
                            f"Cannot load {model}: projected memory {need / _GIB:.1f} GiB would "
                            f"exceed host headroom {available / _GIB:.1f} GiB (oMLX headroom "
                            f"{headroom / _GIB:.1f} + Ollama evictable {evictable / _GIB:.1f} "
                            f"- margin {_MARGIN / _GIB:.0f})"
                        )
            except LoadRefusedError:
                self._lock.release()
                raise
            except Exception as e:
                logger.warning("load_guard: measurement failed for %s, admitting: %s", model, e)

        released = False

        def release() -> None:
            nonlocal released
            if not released:
                released = True
                self._lock.release()

        return release
