"""Host-memory admission for cold Ollama loads (portal/platform/inference/load_guard.py)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from portal.platform.inference import load_guard as lg
from portal.platform.inference.ollama_native import OllamaNativeTransport
from portal.platform.inference.router.non_streaming import _is_capacity_error

GIB = 1024**3
OLLAMA = "http://ollama:11434"
OMLX = "http://omlx:8085"


def _engines(
    resident: dict[str, int],
    sizes: dict[str, int],
    ceiling: float = 40 * GIB,
    omlx_used: float = 0,
    omlx_ok: bool = True,
    loading: list[bool] | None = None,
):
    """A fake Ollama + oMLX pair. `loading` is consumed one status call at a time."""
    loading = list(loading or [])

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in resident.items()]}
            )
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in sizes.items()]}
            )
        if path == "/v1/models/status":
            if not omlx_ok:
                return httpx.Response(503)
            busy = loading.pop(0) if loading else False
            return httpx.Response(
                200,
                json={
                    "final_ceiling": ceiling,
                    "current_model_memory": omlx_used,
                    "models": [{"id": "m", "is_loading": busy}],
                },
            )
        if path == "/api/chat":
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": []})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


_CURRENT: dict[str, httpx.MockTransport] = {}


@pytest.fixture
def engines(monkeypatch):
    def install(**kw):
        _CURRENT["t"] = _engines(**kw)
        return _CURRENT["t"]

    monkeypatch.delenv("LOAD_GUARD", raising=False)
    return install


def _guard() -> lg.LoadGuard:
    return lg.LoadGuard(
        omlx_url=lambda: OMLX,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=_CURRENT["t"]),
    )


async def test_resident_model_is_never_gated(engines):
    engines(resident={"big": 20 * GIB}, sizes={"big": 20 * GIB}, ceiling=0)
    assert await _guard().admit(OLLAMA, "big") is None


async def test_cold_model_that_fits_takes_the_lock(engines):
    engines(resident={}, sizes={"m": 10 * GIB}, ceiling=40 * GIB)
    g = _guard()
    release = await g.admit(OLLAMA, "m")
    assert release is not None and g._lock.locked()
    release()
    release()  # idempotent
    assert not g._lock.locked()


async def test_cold_model_too_big_is_refused_as_capacity_error(engines):
    # The 2026-10-07 shape: oMLX 20.9 of a 25.6 GiB ceiling, an 18 GB model.
    engines(
        resident={"router": 5 * GIB},
        sizes={"qwen": 18 * GIB},
        ceiling=25.6 * GIB,
        omlx_used=20.9 * GIB,
    )
    g = _guard()
    with pytest.raises(lg.LoadRefusedError) as e:
        await g.admit(OLLAMA, "qwen")
    assert _is_capacity_error(str(e.value))
    assert not g._lock.locked()


async def test_ollama_evictable_residents_count_but_the_pinned_router_does_not(engines):
    # 6 GiB oMLX headroom + 20 GiB evictable seat - 2 margin covers 18 * 1.25.
    engines(
        resident={"router": 5 * GIB, "seat": 20 * GIB},
        sizes={"qwen": 18 * GIB},
        ceiling=26 * GIB,
        omlx_used=20 * GIB,
    )
    release = await _guard().admit(OLLAMA, "qwen")
    assert release is not None
    release()


async def test_second_cold_load_waits_for_the_first(engines):
    engines(resident={}, sizes={"a": 5 * GIB, "b": 5 * GIB})
    g = _guard()
    first = await g.admit(OLLAMA, "a")
    second = asyncio.create_task(g.admit(OLLAMA, "b"))
    await asyncio.sleep(0.05)
    assert not second.done()
    first()
    release_b = await asyncio.wait_for(second, 2)
    assert release_b is not None
    release_b()


async def test_unmeasurable_omlx_fails_open(engines):
    engines(resident={}, sizes={"m": 60 * GIB}, omlx_ok=False)
    release = await _guard().admit(OLLAMA, "m")
    assert release is not None
    release()


async def test_disabled(engines, monkeypatch):
    engines(resident={}, sizes={"m": 60 * GIB}, ceiling=0)
    monkeypatch.setenv("LOAD_GUARD", "0")
    assert await _guard().admit(OLLAMA, "m") is None


async def test_waits_while_omlx_is_mid_load(engines, monkeypatch):
    monkeypatch.setattr(lg.asyncio, "sleep", lambda s, _real=asyncio.sleep: _real(0))
    engines(resident={}, sizes={"m": 5 * GIB}, loading=[True, True, False])
    g = _guard()
    release = await g.admit(OLLAMA, "m")
    assert release is not None
    release()


async def test_transport_returns_507_and_never_calls_ollama_chat(engines):
    engines(resident={}, sizes={"qwen": 18 * GIB}, ceiling=25 * GIB, omlx_used=21 * GIB)
    seen: list[str] = []

    def inner(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return httpx.Response(200, json={"capabilities": []})

    t = OllamaNativeTransport(httpx.MockTransport(inner), is_ollama=lambda b: True, guard=_guard())
    async with httpx.AsyncClient(transport=t) as c:
        r = await c.post(
            f"{OLLAMA}/v1/chat/completions",
            json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert r.status_code == 507
    assert _is_capacity_error(json.loads(r.content)["error"]["message"])
    assert "/api/chat" not in seen


async def test_transport_releases_the_lock_after_a_non_streamed_answer(engines):
    engines(resident={}, sizes={"m": 4 * GIB})
    g = _guard()
    t = OllamaNativeTransport(_CURRENT["t"], is_ollama=lambda b: True, guard=g)
    async with httpx.AsyncClient(transport=t) as c:
        r = await c.post(
            f"{OLLAMA}/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert r.status_code == 200
    assert not g._lock.locked()


def _omlx_holding(idle_models: dict[str, int], active: int, ceiling: float, unloaded: list[str]):
    """Ollama empty; oMLX holding `idle_models` (bytes) under `ceiling`."""
    held = dict(idle_models)

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "nex", "size": 21 * GIB}]})
        if path == "/v1/models/status":
            return httpx.Response(
                200,
                json={
                    "final_ceiling": ceiling,
                    "current_model_memory": sum(held.values()),
                    "models": [],
                },
            )
        if path == "/api/status":
            return httpx.Response(200, json={"active_requests": active, "waiting_requests": 0})
        if path == "/admin/api/login":
            return httpx.Response(200, json={"success": True})
        if path == "/admin/api/models":
            return httpx.Response(
                200,
                json=[
                    {"id": n, "loaded": True, "pinned": False, "actual_size": s, "last_access": i}
                    for i, (n, s) in enumerate(held.items())
                ],
            )
        if path.endswith("/unload"):
            name = path.split("/")[-2]
            held.pop(name, None)
            unloaded.append(name)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_idle_omlx_models_are_unloaded_lru_first_to_fit(monkeypatch):
    monkeypatch.setattr(lg.asyncio, "sleep", lambda s, _real=asyncio.sleep: _real(0))
    unloaded: list[str] = []
    # The live 2026-10-07 shape: 24 GiB idle on oMLX, a 21 GiB Ollama model.
    _CURRENT["t"] = _omlx_holding(
        {"old-15g": 15 * GIB, "mid-5g": 5 * GIB, "new-4g": 4 * GIB},
        active=0,
        ceiling=33 * GIB,  # 9 GiB headroom: 26.25 needed -> 19.25 to free -> 15 + 5
        unloaded=unloaded,
    )
    release = await _guard().admit(OLLAMA, "nex")
    assert release is not None
    release()
    assert unloaded[0] == "old-15g"  # least recently used first
    assert "new-4g" not in unloaded  # stops once the load fits


async def test_busy_omlx_is_never_unloaded(monkeypatch):
    unloaded: list[str] = []
    _CURRENT["t"] = _omlx_holding(
        {"busy-20g": 20 * GIB}, active=1, ceiling=31.6 * GIB, unloaded=unloaded
    )
    with pytest.raises(lg.LoadRefusedError):
        await _guard().admit(OLLAMA, "nex")
    assert unloaded == []
