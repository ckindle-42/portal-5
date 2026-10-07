"""HOST_MEMORY_SAFETY W6: the admission gate measures host headroom."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from portal.platform.inference import load_guard as lg
from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.router import concurrency

#: Captured at import, before the conftest fixture pins it for every test.
_REAL_HOST_FREE_BYTES = lg.LoadGuard.host_free_bytes
GIB = 1024**3


async def _gate() -> None:
    slot = concurrency.RequestSlot()
    await slot.acquire_global()
    slot.release()


async def test_gate_503s_when_headroom_is_below_the_floor(monkeypatch):
    monkeypatch.setattr(concurrency, "_MEMORY_GATE_MIN_FREE_GB", 1.5)
    monkeypatch.setattr(concurrency, "_last_free_gb", 1.0)
    with pytest.raises(HTTPException) as exc:
        await _gate()
    assert exc.value.status_code == 503
    assert exc.value.headers["Retry-After"]


async def test_gate_admits_above_the_floor_and_fails_open_when_unmeasurable(monkeypatch):
    import asyncio

    monkeypatch.setattr(concurrency, "_request_semaphore", asyncio.Semaphore(2))
    monkeypatch.setattr(concurrency, "_MEMORY_GATE_MIN_FREE_GB", 1.5)
    monkeypatch.setattr(concurrency, "_last_free_gb", 8.0)
    await _gate()
    monkeypatch.setattr(concurrency, "_last_free_gb", None)
    await _gate()


async def test_host_free_bytes_is_omlx_headroom_plus_idle_ollama(monkeypatch):
    monkeypatch.setattr(lg.LoadGuard, "host_free_bytes", _REAL_HOST_FREE_BYTES)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/models/status":
            return httpx.Response(
                200, json={"final_ceiling": 10 * GIB, "current_model_memory": 7 * GIB}
            )
        if req.url.path == "/api/ps":
            models = [
                {"name": "idle", "size": 4 * GIB},
                {"name": "busy", "size": 6 * GIB},
                {"name": "router", "size": 5 * GIB},
            ]
            return httpx.Response(200, json={"models": models})
        return httpx.Response(404)

    guard = lg.LoadGuard(
        omlx_url=lambda: "http://omlx:8085",
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    guard.begin(lg.OLLAMA, "busy")
    # 3 GiB oMLX headroom + the idle model; busy and pinned are not evictable.
    assert await guard.host_free_bytes("http://ollama:11434") == 7 * GIB


async def test_host_free_bytes_is_none_when_omlx_is_unreadable(monkeypatch):
    monkeypatch.setattr(lg.LoadGuard, "host_free_bytes", _REAL_HOST_FREE_BYTES)
    guard = lg.LoadGuard(
        omlx_url=lambda: "http://omlx:8085",
        client=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(503))
        ),
    )
    assert await guard.host_free_bytes("http://ollama:11434") is None


def _registry() -> BackendRegistry:
    reg = BackendRegistry.__new__(BackendRegistry)
    reg._last_memory_pct = 0.0
    reg._memory_gate_source = None
    return reg


async def test_health_cycle_pushes_headroom_and_logs_its_source_once(monkeypatch, caplog):
    async def free(self, base):
        return 2.5 * GIB

    monkeypatch.setattr(lg.LoadGuard, "host_free_bytes", free)
    monkeypatch.setattr(lg, "GUARD", lg.LoadGuard(omlx_url=lambda: None))
    monkeypatch.setattr("shutil.which", lambda name: None)  # the container: no vm_stat
    reg = _registry()
    healthy = [SimpleNamespace(type="ollama", url="http://ollama:11434")]

    with caplog.at_level(logging.INFO):
        await reg._update_memory_gate(healthy)
        await reg._update_memory_gate(healthy)

    assert concurrency._last_free_gb == pytest.approx(2.5)
    assert sum("Memory gate source: host headroom" in r.message for r in caplog.records) == 1


async def test_health_cycle_logs_loudly_when_nothing_is_measurable(monkeypatch, caplog):
    monkeypatch.setattr(lg, "GUARD", lg.LoadGuard(omlx_url=lambda: None))
    monkeypatch.setattr("shutil.which", lambda name: None)
    reg = _registry()

    with caplog.at_level(logging.INFO):
        await reg._update_memory_gate([SimpleNamespace(type="ollama", url="http://o")])

    assert concurrency._last_free_gb is None
    assert any(r.levelno == logging.ERROR and "gate is OPEN" in r.message for r in caplog.records)
