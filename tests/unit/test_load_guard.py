"""Host-memory admission across Ollama and oMLX (portal/platform/inference/load_guard.py)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from portal.platform.inference import load_guard as lg
from portal.platform.inference.load_guard import OLLAMA, OMLX
from portal.platform.inference.ollama_native import OllamaNativeTransport
from portal.platform.inference.router.non_streaming import _is_capacity_error

GIB = 1024**3
OLLAMA_URL = "http://ollama:11434"
OMLX_URL = "http://omlx:8085"


class Engines:
    """A stateful fake Ollama + oMLX. /api/chat makes its model resident."""

    def __init__(
        self,
        *,
        ollama: dict[str, int] | None = None,
        tags: dict[str, int] | None = None,
        omlx: dict[str, dict[str, Any]] | None = None,
        ceiling: float = 40 * GIB,
        omlx_ok: bool = True,
        omlx_active: int = 0,
    ) -> None:
        self.ollama = dict(ollama or {})
        self.tags = dict(tags or {})
        self.omlx = {k: dict(v) for k, v in (omlx or {}).items()}
        self.ceiling = ceiling
        self.omlx_ok = omlx_ok
        self.omlx_active = omlx_active
        self.unloaded: list[str] = []
        self.chats: list[str] = []
        self.loading_polls: list[bool] = []

    def omlx_used(self) -> float:
        return float(sum(m["size"] for m in self.omlx.values() if m.get("loaded")))

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.ollama.items()]}
            )
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.tags.items()]}
            )
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": []})
        if path == "/api/chat":
            model = json.loads(req.content)["model"]
            self.chats.append(model)
            self.ollama.setdefault(model, int(self.tags.get(model, 0) * 1.1))
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})
        if path == "/v1/models/status":
            if not self.omlx_ok:
                return httpx.Response(503)
            loading = self.loading_polls.pop(0) if self.loading_polls else False
            return httpx.Response(
                200,
                json={
                    "final_ceiling": self.ceiling,
                    "current_model_memory": self.omlx_used(),
                    "models": [
                        {
                            "id": k,
                            "loaded": v.get("loaded", False),
                            "is_loading": loading and not v.get("loaded"),
                            "estimated_size": v["size"],
                        }
                        for k, v in self.omlx.items()
                    ],
                },
            )
        if path == "/api/status":
            return httpx.Response(
                200, json={"active_requests": self.omlx_active, "waiting_requests": 0}
            )
        if path == "/admin/api/login":
            return httpx.Response(200, json={"success": True})
        if path == "/admin/api/models":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": k,
                        "loaded": v.get("loaded", False),
                        "pinned": v.get("pinned", False),
                        "actual_size": v["size"],
                        "last_access": v.get("last", 0),
                    }
                    for k, v in self.omlx.items()
                ],
            )
        if path.endswith("/unload"):
            name = path.split("/")[-2]
            self.omlx[name]["loaded"] = False
            self.unloaded.append(name)
            return httpx.Response(200, json={})
        if path == "/v1/chat/completions":  # oMLX chat
            model = json.loads(req.content)["model"]
            self.omlx.setdefault(model, {"size": 4 * GIB})["loaded"] = True
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(lg.asyncio, "sleep", lambda s, _r=real_sleep: _r(0))
    monkeypatch.setattr(lg, "_POLL_S", 0.0)
    monkeypatch.delenv("LOAD_GUARD", raising=False)
    lg.set_load_wait(None)
    monkeypatch.setattr(lg, "_WAIT_S", 0.0)  # refuse at once unless a test opts into waiting


def guard(e: Engines) -> lg.LoadGuard:
    return lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=e.transport()),
    )


async def settle() -> None:
    for _ in range(50):
        await asyncio.sleep(0)


# ── Ollama admission ──────────────────────────────────────────────────────


async def test_resident_model_is_never_gated():
    e = Engines(ollama={"big": 20 * GIB}, tags={"big": 20 * GIB}, ceiling=0)
    assert await guard(e).admit(OLLAMA_URL, "big") is None


async def test_lock_is_load_scoped_released_once_resident():
    e = Engines(tags={"m": 4 * GIB})
    g = guard(e)
    release = await g.admit(OLLAMA_URL, "m")
    assert release is not None and g._lock.locked()
    e.ollama["m"] = 5 * GIB  # Ollama finished loading; the response is still streaming
    await settle()
    assert not g._lock.locked()
    assert g._observed[(OLLAMA, "m")] == 5 * GIB  # real footprint recorded
    release()  # the response's own end is idempotent


async def test_refused_load_is_a_capacity_error_and_frees_the_lock():
    # The 2026-10-07 shape: oMLX near its ceiling, an 18 GB Ollama model.
    e = Engines(
        ollama={"router": 5 * GIB},
        tags={"qwen": 18 * GIB},
        omlx={"busy": {"size": int(20.9 * GIB), "loaded": True}},
        ceiling=25.6 * GIB,
        omlx_active=1,
    )
    g = guard(e)
    end = g.begin(OMLX, "busy")
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "qwen")
    assert _is_capacity_error(str(err.value))
    assert not g._lock.locked() and e.unloaded == []
    end()


async def test_busy_ollama_resident_is_not_evictable_idle_one_is():
    e = Engines(
        ollama={"router": 5 * GIB, "seat": 20 * GIB}, tags={"qwen": 18 * GIB}, ceiling=8 * GIB
    )
    g = guard(e)
    end = g.begin(OLLAMA, "seat")  # serving a sibling request
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "qwen")
    end()  # sibling finished: now evictable (8 + 20 - 2 >= 22.5)
    release = await g.admit(OLLAMA_URL, "qwen")
    assert release is not None
    release()


async def test_pinned_router_never_counts_as_evictable():
    e = Engines(ollama={"router": 30 * GIB}, tags={"qwen": 18 * GIB}, ceiling=8 * GIB)
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "qwen")


async def test_queues_until_a_sibling_finishes_then_admits():
    e = Engines(ollama={"seat": 20 * GIB}, tags={"qwen": 18 * GIB}, ceiling=8 * GIB)
    g = guard(e)
    end = g.begin(OLLAMA, "seat")
    lg.set_load_wait("30")
    task = asyncio.create_task(g.admit(OLLAMA_URL, "qwen"))
    await settle()
    assert not task.done()  # waiting, not refused
    end()
    release = await asyncio.wait_for(task, 2)
    assert release is not None
    release()


async def test_wait_header_is_clamped_and_parsed():
    lg.set_load_wait("999999")
    assert lg.load_wait_s() == lg._MAX_WAIT_S
    lg.set_load_wait("nonsense")
    assert lg.load_wait_s() == lg._WAIT_S
    lg.set_load_wait("12.5")
    assert lg.load_wait_s() == 12.5


async def test_observed_footprint_raises_the_estimate():
    e = Engines(tags={"m": 10 * GIB}, ceiling=16 * GIB)  # 12.5 estimate fits in 14
    g = guard(e)
    g._observed[(OLLAMA, "m")] = 15 * GIB  # last time it really took 15
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "m")


async def test_unmeasurable_omlx_fails_open():
    e = Engines(tags={"m": 60 * GIB}, omlx_ok=False)
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    release()


async def test_disabled(monkeypatch):
    monkeypatch.setenv("LOAD_GUARD", "0")
    e = Engines(tags={"m": 60 * GIB}, ceiling=0)
    assert await guard(e).admit(OLLAMA_URL, "m") is None


async def test_waits_while_omlx_is_mid_load():
    e = Engines(tags={"m": 4 * GIB}, omlx={"x": {"size": GIB}})
    e.loading_polls = [True, True, False]
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None and e.loading_polls == []
    release()


# ── freeing oMLX ──────────────────────────────────────────────────────────


async def test_idle_omlx_models_are_unloaded_lru_first_busy_ones_never():
    e = Engines(
        tags={"nex": 21 * GIB},  # 26.25 needed
        omlx={
            "old-15g": {"size": 15 * GIB, "loaded": True, "last": 1},
            "busy-5g": {"size": 5 * GIB, "loaded": True, "last": 0},
            "mid-5g": {"size": 5 * GIB, "loaded": True, "last": 2},
            "new-4g": {"size": 4 * GIB, "loaded": True, "last": 3},
        },
        ceiling=38 * GIB,  # 9 GiB headroom; 19.25 to free from idle models
        omlx_active=1,  # the busy model's request, which the pipeline is tracking
    )
    g = guard(e)
    end = g.begin(OMLX, "busy-5g")
    release = await g.admit(OLLAMA_URL, "nex")
    assert release is not None
    assert e.unloaded == ["old-15g", "mid-5g"]  # LRU among idle; busy never; stops at fit
    release()
    end()


async def test_foreign_omlx_activity_blocks_freeing():
    e = Engines(
        tags={"nex": 21 * GIB},
        omlx={"idle-20g": {"size": 20 * GIB, "loaded": True}},
        ceiling=29 * GIB,
        omlx_active=1,  # a request the pipeline did not send (an IDE talking to oMLX)
    )
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "nex")
    assert e.unloaded == []


# ── oMLX serialisation ────────────────────────────────────────────────────


async def test_omlx_cold_loads_take_the_same_lock():
    e = Engines(omlx={"a": {"size": 16 * GIB}, "b": {"size": 16 * GIB}})
    g = guard(e)
    lg.set_load_wait("30")
    first = await g.admit_omlx("a")
    assert first is not None
    second = asyncio.create_task(g.admit_omlx("b"))
    await asyncio.sleep(0)
    assert not second.done()
    e.omlx["a"]["loaded"] = True  # oMLX finished loading a
    release_b = await asyncio.wait_for(second, 2)
    assert release_b is not None
    first()
    release_b()


async def test_resident_or_unknown_omlx_model_is_not_serialised():
    e = Engines(omlx={"a": {"size": GIB, "loaded": True}})
    g = guard(e)
    assert await g.admit_omlx("a") is None
    assert await g.admit_omlx("not-an-omlx-id") is None


# ── plans ─────────────────────────────────────────────────────────────────


async def test_plan_counts_only_what_the_set_adds_against_idle_capacity():
    e = Engines(
        ollama={"router": 5 * GIB, "warm": 6 * GIB, "idle": 10 * GIB},
        tags={"warm": 5 * GIB, "cold": 8 * GIB},
        omlx={
            "o-idle": {"size": 12 * GIB, "loaded": True},
            "o-cold": {"size": 16 * GIB},
        },
        ceiling=24 * GIB,  # 12 GiB headroom
    )
    plan = await guard(e).plan(OLLAMA_URL, [(OLLAMA, "warm"), (OLLAMA, "cold"), (OMLX, "o-cold")])
    assert plan["need_gib"] == pytest.approx(10 + 16)  # warm adds nothing
    assert plan["idle_ollama_gib"] == pytest.approx(10)  # router pinned; warm in the set
    assert plan["freeable_omlx_gib"] == pytest.approx(12)
    assert plan["fits"] is True  # 12 + 10 + 12 - 2 = 32 >= 26


# ── the transport ─────────────────────────────────────────────────────────


def transport(e: Engines, g: lg.LoadGuard) -> OllamaNativeTransport:
    return OllamaNativeTransport(
        e.transport(),
        is_ollama=lambda b: b == OLLAMA_URL,
        guard=g,
        is_omlx=lambda b: b == OMLX_URL,
    )


async def test_transport_refusal_is_507_and_ollama_never_sees_the_chat():
    e = Engines(tags={"qwen": 18 * GIB}, ceiling=8 * GIB)
    async with httpx.AsyncClient(transport=transport(e, guard(e))) as c:
        r = await c.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert r.status_code == 507
    assert _is_capacity_error(json.loads(r.content)["error"]["message"])
    assert e.chats == []


async def test_transport_counts_ollama_and_omlx_requests_and_settles():
    e = Engines(tags={"m": 4 * GIB}, omlx={"o": {"size": 4 * GIB}})
    g = guard(e)
    async with httpx.AsyncClient(transport=transport(e, g)) as c:
        r1 = await c.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
        async with c.stream(
            "POST", f"{OMLX_URL}/v1/chat/completions", json={"model": "o", "messages": []}
        ) as r2:
            assert g.busy(OMLX, "o") == 1  # in flight while the response is open
            await r2.aread()
    await settle()
    assert r1.status_code == 200 and r2.status_code == 200
    assert g.busy(OLLAMA, "m") == 0 and g.busy(OMLX, "o") == 0
    assert not g._lock.locked()


async def test_a_load_waiting_for_memory_does_not_block_loads_that_fit():
    e = Engines(
        ollama={"seat": 20 * GIB}, tags={"big": 18 * GIB, "small": 2 * GIB}, ceiling=8 * GIB
    )
    g = guard(e)
    end = g.begin(OLLAMA, "seat")  # keeps "big" from fitting
    lg.set_load_wait("30")
    big = asyncio.create_task(g.admit(OLLAMA_URL, "big"))
    await settle()
    assert not big.done()
    small = await asyncio.wait_for(g.admit(OLLAMA_URL, "small"), 2)  # fits: not stuck behind big
    assert small is not None
    small()
    end()
    release = await asyncio.wait_for(big, 2)
    assert release is not None
    release()


async def test_a_cancelled_admit_never_leaks_the_cold_load_lock():
    """W3: a client disconnect cancels a request mid-admission. The host-wide
    lock it held must be released, or every later cold load deadlocks."""
    e = Engines(tags={"big": 8 * GIB})
    blocked = asyncio.Event()
    never = asyncio.Event()

    async def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/models/status":  # read with the lock held
            blocked.set()
            await never.wait()
        return e.handler(req)

    g = lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    task = asyncio.ensure_future(g.admit(OLLAMA_URL, "big"))
    await asyncio.wait_for(blocked.wait(), 2)
    assert g._lock.locked()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not g._lock.locked()


async def test_a_cancelled_omlx_admit_never_leaks_the_cold_load_lock():
    e = Engines(omlx={"m": {"size": 4 * GIB}})
    polls = 0
    never = asyncio.Event()
    blocked = asyncio.Event()

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal polls
        if req.url.path == "/v1/models/status":
            polls += 1
            if polls == 2:  # the re-check after the lock is taken
                blocked.set()
                await never.wait()
        return e.handler(req)

    g = lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    task = asyncio.ensure_future(g.admit_omlx("m"))
    await asyncio.wait_for(blocked.wait(), 2)
    assert g._lock.locked()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not g._lock.locked()
