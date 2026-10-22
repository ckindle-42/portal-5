"""Host-memory admission across Ollama and oMLX (portal/platform/inference/load_guard.py)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
        loading_polls: list[bool] | None = None,
        status_loading_polls: list[bool] | None = None,
        admin_loading_polls: list[bool] | None = None,
        settled_ceiling: float | None = None,
        settled_signal: str = "v1",
        omlx_memory: float | None = None,
        api_status_code: int = 200,
        admin_login_code: int = 200,
        admin_models_code: int = 200,
        unload_status_code: int = 200,
        unload_status_codes: dict[str, int] | None = None,
        unload_sticks: bool = False,
        actual_sizes: dict[str, float] | None = None,
        unload_counter_drops: dict[str, float] | None = None,
        immediate_counter_drops: set[str] | None = None,
        unload_loaded_flips: set[str] | None = None,
        unload_removal_polls: dict[str, int] | None = None,
        ceiling_rise_polls: dict[str, int] | None = None,
        forced_loading: set[str] | None = None,
        omit_estimated_size: set[str] | None = None,
        defer_ceiling_rise: set[str] | None = None,
    ) -> None:
        self.ollama = dict(ollama or {})
        self.tags = dict(tags or {})
        self.omlx = {k: dict(v) for k, v in (omlx or {}).items()}
        self.ceiling = ceiling
        self.omlx_ok = omlx_ok
        self.omlx_active = omlx_active
        self.loading_polls = list(loading_polls or [])
        self.status_loading_polls = list(status_loading_polls or [])
        self.admin_loading_polls = list(admin_loading_polls or [])
        self.settled_ceiling = settled_ceiling
        self.settled_signal = settled_signal
        self.omlx_memory = omlx_memory
        self.api_status_code = api_status_code
        self.admin_login_code = admin_login_code
        self.admin_models_code = admin_models_code
        self.unload_status_code = unload_status_code
        self.unload_status_codes = dict(unload_status_codes or {})
        self.unload_sticks = unload_sticks
        self.actual_sizes = dict(actual_sizes or {})
        self.unload_counter_drops = dict(unload_counter_drops or {})
        self.immediate_counter_drops = set(immediate_counter_drops or set())
        self.unload_loaded_flips = set(unload_loaded_flips or set())
        #: Ollama models that stay in /api/ps for N reads after their unload request.
        self.unload_removal_polls = dict(unload_removal_polls or {})
        #: Pending host-ceiling rises that land only after N status reads.
        self.ceiling_rise_polls = dict(ceiling_rise_polls or {})
        self.pending_removals: dict[str, int] = {}
        #: Models that report is_loading even while their loaded bit stays true.
        self.forced_loading = set(forced_loading or set())
        #: Models whose admin payload omits estimated_size (the actual_size fallback).
        self.omit_estimated_size = set(omit_estimated_size or set())
        #: Models whose hidden bytes reach the ceiling one status read after the unload
        #: (the host returns the pages asynchronously).
        self.defer_ceiling_rise = set(defer_ceiling_rise or set())
        self.pending_ceiling_rises: dict[str, tuple[int, int]] = {}
        self.pending_counter_drops: dict[str, tuple[float, int]] = {}
        self.unloaded: list[str] = []
        self.unload_calls: dict[str, int] = {}
        self.chats: list[str] = []
        self.request_counts: dict[str, int] = {}
        #: Bytes an Ollama resident really holds beyond its /api/ps size (Ollama 0.40's
        #: llamacpp runner under-reports); they are missing from oMLX's ceiling too.
        self.hidden: dict[str, int] = {}

    def _loading_poll(self, polls: list[bool], signal: str) -> bool:
        loading = polls.pop(0) if polls else False
        if not loading and signal == self.settled_signal and self.settled_ceiling is not None:
            self.ceiling = self.settled_ceiling
            self.settled_ceiling = None
        return loading

    def omlx_used(self) -> float:
        if self.omlx_memory is not None:
            return self.omlx_memory
        return float(sum(m["size"] for m in self.omlx.values() if m.get("loaded")))

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.request_counts[path] = self.request_counts.get(path, 0) + 1
        response = self._ollama_response(req, path)
        if response is not None:
            return response
        response = self._omlx_response(req, path)
        return response if response is not None else httpx.Response(404)

    def _ollama_response(self, req: httpx.Request, path: str) -> httpx.Response | None:
        if path == "/api/ps":
            self._apply_pending_removals()
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.ollama.items()]}
            )
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.tags.items()]}
            )
        if path == "/api/generate":  # keep_alive 0 unloads; its real bytes return to oMLX
            model = json.loads(req.content)["model"]
            self.unload_calls[model] = self.unload_calls.get(model, 0) + 1
            if self.unload_sticks:
                pass
            elif model in self.unload_removal_polls:
                self.pending_removals[model] = self.unload_removal_polls[model]
            else:
                self.ollama.pop(model, None)
            rise = self.hidden.pop(model, 0)
            if rise and model in self.defer_ceiling_rise:
                self.pending_ceiling_rises[model] = (rise, 1)
            elif rise and model in self.ceiling_rise_polls:
                self.pending_ceiling_rises[model] = (rise, self.ceiling_rise_polls[model])
            else:
                self.ceiling += rise
            return httpx.Response(200, json={"done": True})
        if path == "/api/show":
            return httpx.Response(200, json={"capabilities": []})
        if path == "/api/chat":
            model = json.loads(req.content)["model"]
            self.chats.append(model)
            self.ollama.setdefault(model, int(self.tags.get(model, 0) * 1.1))
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})
        return None

    def _apply_pending_counter_drops(self) -> None:
        for name, (size, polls) in list(self.pending_counter_drops.items()):
            if polls:
                self.pending_counter_drops[name] = (size, polls - 1)
            else:
                self.omlx_memory = max(0.0, float(self.omlx_memory or 0) - size)
                del self.pending_counter_drops[name]

    def _apply_pending_removals(self) -> None:
        for name, polls in list(self.pending_removals.items()):
            if polls:
                self.pending_removals[name] = polls - 1
            else:
                self.ollama.pop(name, None)
                del self.pending_removals[name]

    def _apply_pending_ceiling_rises(self) -> None:
        for name, (rise, reads) in list(self.pending_ceiling_rises.items()):
            if reads:
                self.pending_ceiling_rises[name] = (rise, reads - 1)
            else:
                self.ceiling += rise
                del self.pending_ceiling_rises[name]

    def _unload_response(self, name: str) -> httpx.Response:
        self.unload_calls[name] = self.unload_calls.get(name, 0) + 1
        status_code = self.unload_status_codes.get(name, self.unload_status_code)
        if status_code == 200 and not self.unload_sticks:
            self.omlx[name]["loaded"] = False
            if self.omlx_memory is not None:
                self.omlx_memory = max(
                    0.0,
                    self.omlx_memory - self.unload_counter_drops.get(name, 0.0),
                )
        elif status_code == 202:
            if name in self.unload_loaded_flips:
                self.omlx[name]["loaded"] = False
            if self.omlx_memory is not None and name in self.unload_counter_drops:
                self._defer_counter_drop(name)
        self.unloaded.append(name)
        return httpx.Response(status_code, json={})

    def _defer_counter_drop(self, name: str) -> None:
        """Drop the counter with the 202, or one status read later."""
        drop = self.unload_counter_drops[name]
        if name in self.immediate_counter_drops:
            self.omlx_memory = max(0.0, float(self.omlx_memory or 0) - drop)
        else:
            self.pending_counter_drops[name] = (drop, 1)

    def _omlx_response(self, req: httpx.Request, path: str) -> httpx.Response | None:
        if path == "/v1/models/status":
            if not self.omlx_ok:
                return httpx.Response(503)
            self._apply_pending_counter_drops()
            self._apply_pending_ceiling_rises()
            loading = self._loading_poll(self.loading_polls, "v1")
            return httpx.Response(
                200,
                json={
                    "final_ceiling": self.ceiling,
                    "current_model_memory": self.omlx_used(),
                    "models": [
                        {
                            "id": k,
                            "loaded": v.get("loaded", False),
                            "is_loading": (loading and not v.get("loaded"))
                            or k in self.forced_loading,
                            "estimated_size": v["size"],
                        }
                        for k, v in self.omlx.items()
                    ],
                },
            )
        if path == "/api/status":
            if self.api_status_code != 200:
                return httpx.Response(self.api_status_code)
            loading = self._loading_poll(self.status_loading_polls, "status")
            return httpx.Response(
                200,
                json={
                    "active_requests": self.omlx_active,
                    "waiting_requests": 0,
                    "models_loading": int(loading) + len(self.forced_loading),
                },
            )
        if path == "/admin/api/login":
            return httpx.Response(self.admin_login_code, json={"success": True})
        if path == "/admin/api/models":
            if self.admin_models_code != 200:
                return httpx.Response(self.admin_models_code)
            loading = self._loading_poll(self.admin_loading_polls, "admin")
            models = []
            for k, v in self.omlx.items():
                entry: dict[str, Any] = {
                    "id": k,
                    "loaded": v.get("loaded", False),
                    "pinned": v.get("pinned", False),
                    "actual_size": self.actual_sizes.get(k, v["size"]),
                    "last_access": v.get("last", 0),
                    "is_loading": (loading and not v.get("loaded")) or k in self.forced_loading,
                }
                if k not in self.omit_estimated_size:
                    entry["estimated_size"] = v["size"]
                models.append(entry)
            return httpx.Response(200, json=models)
        if path.endswith("/unload"):
            return self._unload_response(path.split("/")[-2])
        if path == "/v1/chat/completions":  # oMLX chat
            model = json.loads(req.content)["model"]
            self.omlx.setdefault(model, {"size": 4 * GIB})["loaded"] = True
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return None

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


def printed_wait_s(message: str) -> float:
    """The wait a refusal reports (one decimal), from 'after waiting X.Ys' or 'within the X.Ys load wait'."""
    match = re.search(r"(?:after waiting|within the) (\d+\.\d)s", message)
    assert match is not None, message
    return float(match.group(1))


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


async def test_under_reported_idle_ollama_resident_is_unloaded_and_the_load_admitted():
    # 2026-10-21 UAT: devstral idle at 1.8 GB in /api/ps but 15 GB real; kat needs ~25 GB.
    e = Engines(ollama={"devstral": int(1.8 * GIB)}, tags={"kat": 22 * GIB}, ceiling=21 * GIB)
    e.hidden["devstral"] = int(13.2 * GIB)
    release = await guard(e).admit(OLLAMA_URL, "kat")
    assert release is not None and "devstral" not in e.ollama
    release()


async def test_a_freed_ollama_resident_lifts_the_ceiling_before_the_quiet_refusal():
    """UAT 2026-10-22 (auto-coding::fast-repair): oMLX empty at 19.8 GiB headroom, a
    24.9 GiB hinted load, and devstral the only idle Ollama resident. Its freed bytes
    reach oMLX's host-derived ceiling one status read later."""
    e = Engines(
        ollama={"devstral": int(1.8 * GIB)},  # /api/ps under-reports the real 15 GiB
        tags={"kat": int(19.92 * GIB)},  # 24.9 GiB projected
        ceiling=int(19.8 * GIB),
        defer_ceiling_rise={"devstral"},
    )
    e.hidden["devstral"] = int(15 * GIB)
    lg.set_load_wait("30")
    release = await guard(e).admit(OLLAMA_URL, "kat")
    assert release is not None
    assert "devstral" not in e.ollama
    assert e.ceiling == pytest.approx(34.8 * GIB, abs=1)
    release()


async def test_busy_or_pinned_ollama_residents_are_never_unloaded():
    e = Engines(
        ollama={"router": 2 * GIB, "seat": 2 * GIB}, tags={"kat": 22 * GIB}, ceiling=10 * GIB
    )
    g = guard(e)
    end = g.begin(OLLAMA, "seat")
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "kat")
    assert set(e.ollama) == {"router", "seat"}
    end()


async def test_pinned_router_never_counts_as_evictable():
    e = Engines(ollama={"router": 30 * GIB}, tags={"qwen": 18 * GIB}, ceiling=8 * GIB)
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "qwen")
    assert lg.time.monotonic() - started < 0.5


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


@pytest.mark.parametrize("live_gib", [20, 60])
async def test_a_fixed_ceiling_keeps_the_verdict_while_final_ceiling_moves(monkeypatch, live_gib):
    """P5-OMLX-CEILING-001: the budget is the configured number, not the live ceiling."""
    monkeypatch.setattr(lg, "_CEILING", 40 * GIB)
    e = Engines(tags={"m": 20 * GIB}, ceiling=live_gib * GIB)  # 25 GiB needed
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    release()


@pytest.mark.parametrize("live_gib", [20, 60])
async def test_a_fixed_ceiling_refuses_while_final_ceiling_moves(monkeypatch, live_gib):
    monkeypatch.setattr(lg, "_CEILING", 40 * GIB)
    e = Engines(tags={"m": 36 * GIB}, ceiling=live_gib * GIB)  # 45 GiB needed
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    assert "host headroom 38.0 GiB" in str(err.value)  # 40 fixed - 2 margin


async def test_without_a_fixed_ceiling_the_live_ceiling_still_decides():
    e = Engines(tags={"m": 20 * GIB}, ceiling=20 * GIB)  # 25 needed, 18 available
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "m")


async def test_plan_uses_the_fixed_ceiling(monkeypatch):
    monkeypatch.setattr(lg, "_CEILING", 30 * GIB)
    e = Engines(
        tags={"m": 8 * GIB},
        ceiling=60 * GIB,
        omlx={"seat": {"size": 10 * GIB, "loaded": True}},
    )
    plan = await guard(e).plan(OLLAMA_URL, [(OLLAMA, "m")])
    assert plan["headroom_gib"] == pytest.approx(20)  # 30 - 10 resident
    assert plan["available_gib"] == pytest.approx(28)  # + 10 freeable - 2 margin
    assert plan["fits"] is True


@pytest.mark.parametrize("signal", ["v1", "status", "admin"])
async def test_loading_signal_waits_then_remeasures_headroom(signal):
    e = Engines(
        tags={"m": int(17.52 * GIB)},
        omlx={"swap": {"size": GIB, "loaded": False}},
        ceiling=22.8 * GIB,
        settled_ceiling=40 * GIB,
    )
    if signal == "v1":
        e.loading_polls = [True, True, False]
        e.admin_loading_polls = [True, True]
    elif signal == "status":
        e.status_loading_polls = [True, True, False]
        e.admin_loading_polls = [True, True]
        e.settled_signal = "status"
    else:
        e.loading_polls = [True, True, True]
        e.admin_loading_polls = [True, True, False]
        e.settled_signal = "admin"
    lg.set_load_wait("10")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert e.ceiling == 40 * GIB
    assert e.settled_ceiling is None
    assert e.request_counts["/v1/models/status"] >= 2
    if signal == "status":
        assert e.request_counts["/api/status"] >= 2
    if signal == "admin":
        assert e.request_counts["/admin/api/login"] >= 1
        assert e.request_counts["/admin/api/models"] >= 1
    release()


async def test_engine_transition_wait_respects_admission_deadline(monkeypatch):
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"loading": {"size": GIB, "loaded": False}},
        ceiling=8 * GIB,
        loading_polls=[True] * 100,
        status_loading_polls=[True] * 100,
    )
    lg.set_load_wait("0.06")
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert 0.05 <= elapsed < 0.5


async def test_transition_refusal_reports_the_real_elapsed_wait(monkeypatch):
    """FIX6 finding 4b: a 0.35 s stuck transition is not "after waiting 0s"."""
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"swap": {"size": GIB, "loaded": False}},
        ceiling=8 * GIB,
        loading_polls=[True] * 1000,
        status_loading_polls=[True] * 1000,
    )
    lg.set_load_wait("0.35")
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert "engine model transition still active" in str(err.value)
    assert printed_wait_s(str(err.value)) == pytest.approx(elapsed, abs=0.1)


async def test_transition_poll_releases_lock_and_headroom_is_nonblocking(monkeypatch):
    e = Engines(tags={"m": 30 * GIB}, ceiling=8 * GIB)
    lg.set_load_wait("1")
    g = guard(e)
    entered = asyncio.Event()
    never = asyncio.Event()

    async def blocked_loading(_client):
        assert not g._lock.locked()
        assert e.request_counts["/v1/models/status"] == 1
        entered.set()
        await never.wait()

    monkeypatch.setattr(g, "_omlx_loading", blocked_loading)
    task = asyncio.create_task(g.admit(OLLAMA_URL, "m"))
    await asyncio.wait_for(entered.wait(), 1)
    assert not g._lock.locked()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not g._lock.locked()


@pytest.mark.parametrize("api_status_code", [503])
async def test_unreadable_runtime_status_does_not_create_transition_wait(api_status_code):
    e = Engines(tags={"m": GIB}, ceiling=20 * GIB, api_status_code=api_status_code)
    lg.set_load_wait("0.2")
    started = lg.time.monotonic()
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert lg.time.monotonic() - started < 0.1
    release()


async def test_fitting_load_skips_transition_probe_and_agreeing_statuses_skip_login():
    e = Engines(
        tags={"m": GIB},
        omlx={"loading": {"size": GIB, "loaded": False}},
        ceiling=20 * GIB,
        loading_polls=[True],
        admin_login_code=400,
    )
    lg.set_load_wait("0.2")
    started = lg.time.monotonic()
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert lg.time.monotonic() - started < 0.1
    assert e.request_counts.get("/admin/api/login", 0) == 0
    assert e.request_counts.get("/api/status", 0) == 0
    release()

    agreeing = Engines(tags={"m": GIB}, ceiling=20 * GIB, admin_login_code=400)
    release = await guard(agreeing).admit(OLLAMA_URL, "m")
    assert release is not None
    assert agreeing.request_counts.get("/admin/api/login", 0) == 0
    release()


async def test_v1_loading_survives_unreadable_runtime_status():
    e = Engines(
        tags={"m": int(17.52 * GIB)},
        omlx={"loading": {"size": GIB, "loaded": False}},
        ceiling=22.8 * GIB,
        settled_ceiling=40 * GIB,
        settled_signal="v1",
        loading_polls=[True, True, False],
        api_status_code=503,
    )
    lg.set_load_wait("10")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert e.ceiling == 40 * GIB
    assert e.request_counts["/api/status"] >= 2
    release()


async def test_v1_loading_survives_failed_admin_login():
    e = Engines(
        tags={"m": int(17.52 * GIB)},
        omlx={"loading": {"size": GIB, "loaded": False}},
        ceiling=22.8 * GIB,
        settled_ceiling=40 * GIB,
        settled_signal="v1",
        loading_polls=[True, True, False],
        admin_login_code=400,
    )
    lg.set_load_wait("10")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert e.ceiling == 40 * GIB
    assert e.request_counts["/admin/api/login"] >= 1
    release()


async def test_idle_model_is_freed_before_transition_wait_and_failover_is_protected():
    e = Engines(
        tags={"m": 20 * GIB},
        omlx={
            "protected": {"size": 5 * GIB, "loaded": True},
            "free": {"size": 20 * GIB, "loaded": True},
            "loading": {"size": GIB, "loaded": False},
        },
        ceiling=35 * GIB,
        loading_polls=[True] * 100,
        status_loading_polls=[True] * 100,
    )
    g = guard(e)
    g.protect(OMLX, "protected", seconds=60)
    lg.set_load_wait("0.04")
    release = await g.admit(OLLAMA_URL, "m")
    assert release is not None
    assert e.unloaded == ["free"]
    assert e.omlx["protected"]["loaded"]
    release()


async def test_protected_model_transition_does_not_spend_the_admission_budget():
    """FIX6 finding 3: the guard never acts on a protected model's oMLX load."""
    e = Engines(
        tags={"m": 30 * GIB},  # 37.5 needed
        omlx={"seat": {"size": 8 * GIB, "loaded": True}},
        ceiling=16 * GIB,
        omlx_memory=8 * GIB,
        forced_loading={"seat"},
    )
    g = guard(e)
    g.protect(OMLX, "seat", seconds=60)
    lg.set_load_wait("0.4")
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "m")
    assert lg.time.monotonic() - started < 0.1
    assert "with nothing in flight to wait for" in str(err.value)
    assert e.unloaded == []
    assert e.omlx["seat"]["loaded"]


async def test_fitting_load_is_not_delayed_by_a_recent_guard_issued_unload():
    e = Engines(
        tags={"big": 40 * GIB, "small": GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
    )
    g = guard(e)
    lg.set_load_wait("0.05")
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "big")
    assert e.unload_calls["idle"] == 1

    lg.set_load_wait("0.2")
    started = lg.time.monotonic()
    release = await g.admit(OLLAMA_URL, "small")
    assert release is not None
    assert lg.time.monotonic() - started < 0.05
    release()


async def test_queued_omlx_unload_waits_for_memory_after_loaded_flips():
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=4 * GIB,
    )
    lg.set_load_wait("0.3")
    task = asyncio.create_task(guard(e).admit(OLLAMA_URL, "m"))
    asyncio.get_running_loop().call_later(0.03, lambda: e.omlx["idle"].update({"loaded": False}))
    asyncio.get_running_loop().call_later(0.08, lambda: setattr(e, "omlx_memory", 0.0))
    release = await asyncio.wait_for(task, 1)
    assert release is not None
    assert not e.omlx["idle"]["loaded"]
    assert e.omlx_used() == 0
    release()


@pytest.mark.parametrize(("actual_size_gib", "headroom_gib"), [(8, 30.0), (10, 32.0)])
async def test_queued_unload_settles_on_any_counter_drop_with_pinned_memory_left(
    actual_size_gib, headroom_gib
):
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={
            "idle": {"size": 8 * GIB, "loaded": True},
            "pinned": {"size": 8 * GIB, "loaded": True, "pinned": True},
        },
        ceiling=40 * GIB,
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=16 * GIB,
        actual_sizes={"idle": actual_size_gib * GIB},
        omit_estimated_size={"idle"},  # charge the queue by actual_size, not estimated_size
        unload_counter_drops={"idle": actual_size_gib * GIB},
        unload_loaded_flips={"idle"},
    )
    lg.set_load_wait("0.12")
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert elapsed < 0.08
    assert "with nothing in flight to wait for" in str(err.value)
    assert f"headroom {headroom_gib:.1f} GiB" in str(err.value)  # after the pinned charge
    assert e.omlx_used() == (16 - actual_size_gib) * GIB
    assert e.unload_calls["idle"] == 1


async def test_staged_two_202_unloads_keep_the_wait_alive_until_each_drop():
    """FIX6 finding 1: b's charge is not settled by a's counter drop."""
    e = Engines(
        tags={"m": 30 * GIB},  # 37.5 needed
        omlx={
            "a": {"size": 8 * GIB, "loaded": True, "last": 1},
            "b": {"size": 8 * GIB, "loaded": True, "last": 2},
        },
        ceiling=40 * GIB,
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=16 * GIB,
    )
    lg.set_load_wait("1.4")
    loop = asyncio.get_running_loop()
    loop.call_later(0.15, lambda: setattr(e, "omlx_memory", 8 * GIB))
    loop.call_later(0.6, lambda: setattr(e, "omlx_memory", 0.0))
    started = lg.time.monotonic()
    release = await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert release is not None
    assert 0.55 <= elapsed < 1.4  # waited for b instead of refusing after a
    assert e.unload_calls == {"a": 1, "b": 1}
    release()


async def test_202_whose_drop_lands_inside_the_free_call_refuses_quietly():
    """FIX6 finding 2: the pre-free counter is the pending baseline."""
    e = Engines(
        tags={"m": 30 * GIB},  # 37.5 needed
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        ceiling=20 * GIB,
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=16 * GIB,
        unload_counter_drops={"idle": 4 * GIB},
        immediate_counter_drops={"idle"},
    )
    lg.set_load_wait("0.8")
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    assert lg.time.monotonic() - started < 0.4
    assert "with nothing in flight to wait for" in str(err.value)
    assert e.omlx_used() == 12 * GIB
    assert e.unload_calls["idle"] == 1


async def test_omlx_200_in_the_same_pass_does_not_settle_a_queued_202():
    """The 200's own drop is not credited to the queued 202s."""
    e = Engines(
        tags={"m": 30 * GIB},  # 37.5 needed
        omlx={
            "done": {"size": 8 * GIB, "loaded": True, "last": 1},
            "a": {"size": 8 * GIB, "loaded": True, "last": 2},
            "b": {"size": 8 * GIB, "loaded": True, "last": 3},
        },
        ceiling=40 * GIB,
        omlx_memory=24 * GIB,
        unload_status_codes={"done": 200, "a": 202, "b": 202},
        unload_counter_drops={"done": 8 * GIB},
    )
    lg.set_load_wait("1.4")
    loop = asyncio.get_running_loop()
    loop.call_later(0.15, lambda: setattr(e, "omlx_memory", 8 * GIB))
    loop.call_later(0.6, lambda: setattr(e, "omlx_memory", 0.0))
    started = lg.time.monotonic()
    release = await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert release is not None
    assert 0.55 <= elapsed < 1.4
    assert e.unload_calls == {"done": 1, "a": 1, "b": 1}
    release()


@pytest.mark.parametrize("actual_size_gib", [6, 8])
async def test_partial_omlx_200_uses_counter_drop_before_ollama_free(actual_size_gib):
    e = Engines(
        ollama={"devstral": int(1.8 * GIB)},
        tags={"kat": 22 * GIB},
        omlx={"mid": {"size": 10 * GIB, "loaded": True}},
        ceiling=30 * GIB,
        omlx_memory=10 * GIB,
        actual_sizes={"mid": actual_size_gib * GIB},
        unload_counter_drops={"mid": 6 * GIB},
    )
    e.hidden["devstral"] = int(13.2 * GIB)
    release = await guard(e).admit(OLLAMA_URL, "kat")
    assert release is not None
    assert e.unload_calls == {"mid": 1, "devstral": 1}
    assert "devstral" not in e.ollama
    release()


async def test_unsignaled_omlx_counter_drop_gets_one_capacity_recheck(monkeypatch):
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"pinned": {"size": 16 * GIB, "loaded": True, "pinned": True}},
        ceiling=40 * GIB,
        omlx_memory=16 * GIB,
    )
    g = guard(e)
    loading_calls = 0
    waits: list[float] = []

    async def self_unloading(client):
        nonlocal loading_calls
        loading_calls += 1
        if loading_calls == 2:
            e.omlx_memory = 8 * GIB
            return False
        return loading_calls == 1

    async def count_wait(timeout: float) -> None:
        waits.append(timeout)

    monkeypatch.setattr(g, "_omlx_loading", self_unloading)
    monkeypatch.setattr(g, "_wait_change", count_wait)
    lg.set_load_wait("0.12")
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "m")
    assert "with nothing in flight to wait for" in str(err.value)
    assert len(waits) == 2
    assert e.unloaded == []


async def test_queued_omlx_unload_waits_then_remeasures_headroom(monkeypatch):
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
    )
    g = guard(e)
    lg.set_load_wait("1")
    waiting = asyncio.Event()
    original = g._omlx_foreign_active

    async def check_unlocked(client):
        assert not g._lock.locked()
        waiting.set()
        return await original(client)

    monkeypatch.setattr(g, "_omlx_foreign_active", check_unlocked)
    task = asyncio.create_task(g.admit(OLLAMA_URL, "m"))
    await asyncio.wait_for(waiting.wait(), 1)
    assert not task.done()
    assert e.unload_calls["idle"] == 1
    asyncio.get_running_loop().call_later(0.03, lambda: e.omlx["idle"].update({"loaded": False}))
    release = await asyncio.wait_for(task, 1)
    assert release is not None
    assert e.ceiling - e.omlx_used() - 2 * GIB >= 30 * GIB * lg._FACTOR
    release()


async def test_queued_omlx_unload_refuses_at_deadline_without_reposting():
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
    )
    g = guard(e)
    lg.set_load_wait("0.06")
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert 0.05 <= elapsed < 0.5
    assert e.unload_calls["idle"] == 1
    assert not g._lock.locked()


async def test_waiting_refusal_reports_the_real_elapsed_wait():
    """FIX6 finding 4b: a 0.55 s stuck 202 is not "after waiting 1s"."""
    e = Engines(
        tags={"m": 30 * GIB},  # 37.5 needed
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=16 * GIB,
    )
    lg.set_load_wait("0.55")
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert printed_wait_s(str(err.value)) == pytest.approx(elapsed, abs=0.1)


@pytest.mark.parametrize("engine", ["ollama", "omlx"])
async def test_sticky_unload_is_not_retried_after_admission_deadline(engine):
    if engine == "ollama":
        e = Engines(
            ollama={"idle": GIB},
            tags={"m": 20 * GIB},
            ceiling=8 * GIB,
            unload_sticks=True,
        )
    else:
        e = Engines(
            tags={"m": 20 * GIB},
            omlx={"idle": {"size": GIB, "loaded": True}},
            ceiling=8 * GIB,
            unload_sticks=True,
        )
    lg.set_load_wait("0.05")
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "m")
    assert e.unload_calls["idle"] == 1


async def test_ollama_unload_that_stays_short_waits_out_the_load_budget(monkeypatch):
    e = Engines(ollama={"idle": GIB}, tags={"m": 20 * GIB}, ceiling=8 * GIB)
    g = guard(e)
    lg.set_load_wait("0.08")
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    waits: list[float] = []
    wait_change = g._wait_change

    async def track_wait(timeout: float) -> None:
        waits.append(timeout)
        await wait_change(timeout)

    monkeypatch.setattr(g, "_wait_change", track_wait)
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert not e.ollama
    assert "free of idle did not settle" in str(err.value)
    assert "load wait" in str(err.value)
    assert waits  # kept polling the unload instead of the quiet refusal
    assert elapsed >= 0.07


async def test_a_free_that_settles_past_the_load_wait_refuses(monkeypatch):
    e = Engines(ollama={"idle": GIB}, tags={"m": 20 * GIB}, ceiling=8 * GIB, unload_sticks=True)
    lg.set_load_wait("0.12")
    monkeypatch.setattr(lg, "_FREE_SETTLE_EXPECTED_S", 0.05)
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    loop = asyncio.get_running_loop()
    loop.call_later(0.3, lambda: e.ollama.pop("idle", None))
    loop.call_later(0.3, lambda: setattr(e, "ceiling", e.ceiling + GIB))
    started = lg.time.monotonic()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    elapsed = lg.time.monotonic() - started
    assert "free of idle did not settle within the 0.1s load wait" in str(err.value)
    assert 0.11 <= elapsed < 0.28  # refused at the wait, not when the pages arrived


async def test_a_settled_free_admits_early_and_logs_the_measured_settle(monkeypatch, caplog):
    e = Engines(
        ollama={"devstral": int(1.8 * GIB)},
        tags={"kat": 22 * GIB},
        ceiling=21 * GIB,
        unload_removal_polls={"devstral": 0},
        ceiling_rise_polls={"devstral": 1},
    )
    e.hidden["devstral"] = int(13.2 * GIB)
    monkeypatch.setattr(lg, "_FREE_SETTLE_EXPECTED_S", 2.0)
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    lg.set_load_wait("30")
    started = lg.time.monotonic()
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await guard(e).admit(OLLAMA_URL, "kat")
    elapsed = lg.time.monotonic() - started
    assert release is not None
    assert elapsed < 0.5  # the signal, not the wait budget, released it
    assert re.search(r"free of devstral settled in \d+\.\d+s", caplog.text)
    release()


async def test_a_slow_free_inside_the_load_wait_admits_and_warns(monkeypatch, caplog):
    e = Engines(
        ollama={"devstral": int(1.8 * GIB)},
        tags={"kat": 22 * GIB},
        ceiling=21 * GIB,
        unload_sticks=True,  # the pages return late, not with the unload request
    )
    monkeypatch.setattr(lg, "_FREE_SETTLE_EXPECTED_S", 0.1)
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    lg.set_load_wait("30")
    loop = asyncio.get_running_loop()
    loop.call_later(0.2, lambda: e.ollama.pop("devstral", None))
    loop.call_later(0.2, lambda: setattr(e, "ceiling", e.ceiling + 13.2 * GIB))
    started = lg.time.monotonic()
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await guard(e).admit(OLLAMA_URL, "kat")
    elapsed = lg.time.monotonic() - started
    assert release is not None
    assert 0.19 <= elapsed < 2  # the wait budget, not the expected settle, bounded it
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "free of devstral settled in" in r.getMessage() and "(expected 0.1s)" in r.getMessage()
        for r in warnings
    )
    release()


async def test_partial_omlx_free_continues_to_idle_ollama_and_honors_failover(monkeypatch):
    e = Engines(
        ollama={"failover": GIB, "devstral": int(1.8 * GIB)},
        tags={"kat": 22 * GIB},
        omlx={
            "lru": {"size": GIB, "loaded": True, "last": 1},
            "mid": {"size": GIB, "loaded": True, "last": 2},
        },
        ceiling=21 * GIB,
        unload_status_codes={"lru": 202},
    )
    e.hidden["devstral"] = int(13.2 * GIB)
    g = guard(e)
    monkeypatch.setattr(lg, "GUARD", g)
    lg.protect_failover(OLLAMA, "failover")
    lg.set_load_wait("0.2")
    release = await g.admit(OLLAMA_URL, "kat")
    assert release is not None
    assert e.unload_calls == {"lru": 1, "mid": 1, "devstral": 1}
    assert e.omlx["lru"]["loaded"]
    assert not e.omlx["mid"]["loaded"]
    assert "devstral" not in e.ollama
    assert e.ollama["failover"] == GIB
    release()


async def test_queued_omlx_unload_does_not_stop_idle_lru_walk():
    e = Engines(
        tags={"m": 25 * GIB},
        omlx={
            "small": {"size": 2 * GIB, "loaded": True, "last": 1},
            "big": {"size": 30 * GIB, "loaded": True, "last": 2},
        },
        ceiling=40 * GIB,
        unload_status_codes={"small": 202},
    )
    lg.set_load_wait("0.2")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    assert list(e.unload_calls) == ["small", "big"]
    assert e.omlx["small"]["loaded"]
    assert not e.omlx["big"]["loaded"]
    release()


async def test_queued_202_that_covers_the_shortage_stops_the_idle_walk():
    """FIX6 finding 4c: queued 202 bytes count toward the shortage."""
    e = Engines(
        tags={"m": 20 * GIB},  # 25 needed
        omlx={
            "big": {"size": 24 * GIB, "loaded": True, "last": 1},
            "small": {"size": GIB, "loaded": True, "last": 2},
        },
        ceiling=30 * GIB,  # 5 GiB headroom; 22 GiB to free
        omlx_memory=25 * GIB,
        unload_status_code=202,
        unload_sticks=True,
    )
    lg.set_load_wait("0.05")
    with pytest.raises(lg.LoadRefusedError):
        await guard(e).admit(OLLAMA_URL, "m")
    assert e.unload_calls == {"big": 1}  # 24 GiB queued covers the shortage; small never posted


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


async def test_unreadable_runtime_status_frees_nothing_and_logs_the_code(caplog):
    """FIX6 finding 4a: a non-200 /api/status means "no idle models", not a JSON error."""
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 16 * GIB, "loaded": True}},
        ceiling=20 * GIB,
        omlx_memory=16 * GIB,
        api_status_code=503,
    )
    with (
        caplog.at_level(logging.WARNING, logger=lg.logger.name),
        pytest.raises(lg.LoadRefusedError) as err,
    ):
        await guard(e).admit(OLLAMA_URL, "m")
    assert "with nothing in flight to wait for" in str(err.value)
    assert e.unload_calls == {}
    assert "could not free oMLX memory" not in caplog.text
    assert "503" in caplog.text


async def test_unreadable_model_list_frees_nothing_and_logs_the_code(caplog):
    """A non-200 /admin/api/models means "no idle models", not a JSON error."""
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 16 * GIB, "loaded": True}},
        ceiling=20 * GIB,
        omlx_memory=16 * GIB,
        admin_models_code=503,
    )
    with (
        caplog.at_level(logging.WARNING, logger=lg.logger.name),
        pytest.raises(lg.LoadRefusedError),
    ):
        await guard(e).admit(OLLAMA_URL, "m")
    assert e.unload_calls == {}
    assert "could not free oMLX memory" not in caplog.text
    assert "model list returned HTTP 503" in caplog.text


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
        actual_sizes={"o-idle": 20 * GIB},  # the observed delta overstates its resident charge
    )
    plan = await guard(e).plan(OLLAMA_URL, [(OLLAMA, "warm"), (OLLAMA, "cold"), (OMLX, "o-cold")])
    assert plan["need_gib"] == pytest.approx(10 + 16)  # warm adds nothing
    assert plan["idle_ollama_gib"] == pytest.approx(10)  # router pinned; warm in the set
    assert plan["freeable_omlx_gib"] == pytest.approx(12)
    assert plan["fits"] is True  # 12 + 10 + 12 - 2 = 32 >= 26


async def test_plan_reports_active_pipeline_traffic():
    e = Engines(omlx={"seat": {"size": GIB, "loaded": True}})
    g = guard(e)
    end = g.begin(OMLX, "seat")
    busy = await g.plan(OLLAMA_URL, [(OMLX, "seat")])
    assert busy["busy"] is True and busy["busy_requests"] == 1
    end()
    idle = await g.plan(OLLAMA_URL, [(OMLX, "seat")])
    assert idle["busy"] is False and idle["busy_requests"] == 0


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


async def test_nothing_in_flight_and_nothing_to_free_refuses_without_waiting(monkeypatch):
    # 2026-10-21 UAT: a 60 GiB seat on an idle host waited the full 120 s for nothing.
    monkeypatch.setattr(lg, "_WAIT_S", 60.0)
    e = Engines(tags={"next": 55 * GIB}, ceiling=40 * GIB)
    started = asyncio.get_running_loop().time()
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "next")
    assert asyncio.get_running_loop().time() - started < 1.0
    assert "nothing in flight" in str(err.value)


async def test_foreign_omlx_work_keeps_the_load_waiting_instead_of_refusing_at_once(monkeypatch):
    # An IDE talking to oMLX directly is invisible to _busy; its finish may free room.
    monkeypatch.setattr(lg, "_WAIT_S", 0.3)
    e = Engines(tags={"next": 55 * GIB}, ceiling=40 * GIB, omlx_active=1)
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "next")
    assert "after waiting" in str(err.value)


async def test_slow_foreign_activity_probe_refuses_instead_of_failing_open(monkeypatch):
    e = Engines(tags={"next": 30 * GIB}, ceiling=8 * GIB)
    g = guard(e)
    lg.set_load_wait("0.05")
    never = asyncio.Event()

    async def blocked_probe(_client):
        await never.wait()

    monkeypatch.setattr(g, "_omlx_foreign_active", blocked_probe)
    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "next")
    assert not g._lock.locked()


# ── metrics ───────────────────────────────────────────────────────────────

_ADMISSIONS = "portal5_load_guard_admissions_total"
_UNLOADS = "portal5_load_guard_unloads_total"
_REFUSALS = "portal5_load_guard_refusals_total"
_WAIT_COUNT = "portal5_load_guard_wait_seconds_count"
_SETTLE_COUNT = "portal5_load_guard_free_settle_seconds_count"
_HEADROOM = "portal5_load_guard_headroom_bytes"
_CEILING = "portal5_load_guard_ceiling_bytes"


def metric_value(name: str, **labels: str) -> float | None:
    from portal.platform.inference.router.metrics import _REGISTRY

    for family in _REGISTRY.collect():
        for sample in family.samples:
            if sample.name == name and all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    return None


def wait_count(engine: str, waited_on: str) -> float:
    return metric_value(_WAIT_COUNT, engine=engine, waited_on=waited_on) or 0.0


def settle_count(engine: str) -> float:
    return metric_value(_SETTLE_COUNT, engine=engine) or 0.0


async def test_a_fitting_cold_load_counts_admitted_immediately_and_sets_the_gauges():
    e = Engines(tags={"m": GIB}, ceiling=40 * GIB)
    before = metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_immediately")
    waited = metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_after_wait")
    waits = wait_count(OLLAMA, "in_flight")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None
    release()
    assert (
        metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_immediately")
        == (before or 0) + 1
    )
    assert (metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_after_wait") or 0.0) == (
        waited or 0.0
    )
    assert wait_count(OLLAMA, "in_flight") == waits  # nothing was waited on
    assert metric_value(_HEADROOM) == pytest.approx(38 * GIB)  # 40 ceiling - 2 margin
    assert metric_value(_CEILING) == pytest.approx(40 * GIB)


async def test_a_load_that_waited_for_a_sibling_counts_admitted_after_wait():
    e = Engines(ollama={"seat": 20 * GIB}, tags={"qwen": 18 * GIB}, ceiling=8 * GIB)
    g = guard(e)
    end = g.begin(OLLAMA, "seat")
    lg.set_load_wait("30")
    before = metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_after_wait")
    waits = wait_count(OLLAMA, "in_flight")
    task = asyncio.create_task(g.admit(OLLAMA_URL, "qwen"))
    await settle()
    assert not task.done()
    end()
    release = await asyncio.wait_for(task, 2)
    assert release is not None
    release()
    assert (
        metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_after_wait") == (before or 0) + 1
    )
    assert wait_count(OLLAMA, "in_flight") > waits


async def test_a_quiet_refusal_counts_refused_with_reason_quiet():
    e = Engines(tags={"next": 55 * GIB}, ceiling=40 * GIB)
    before = metric_value(_REFUSALS, engine=OLLAMA, reason="quiet")
    refused = metric_value(_ADMISSIONS, engine=OLLAMA, outcome="refused")
    waits = wait_count(OLLAMA, "in_flight")
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "next")
    assert "nothing in flight" in str(err.value)
    assert metric_value(_ADMISSIONS, engine=OLLAMA, outcome="refused") == (refused or 0) + 1
    assert metric_value(_REFUSALS, engine=OLLAMA, reason="quiet") == (before or 0) + 1
    assert wait_count(OLLAMA, "in_flight") == waits  # a quiet refusal waits on nothing


async def test_a_refusal_after_waiting_counts_projected_exceeds():
    # oMLX busy with a tracked request: the guard waits, runs out, reports the projection.
    e = Engines(
        ollama={"router": 5 * GIB},
        tags={"qwen": 18 * GIB},
        omlx={"busy": {"size": int(20.9 * GIB), "loaded": True}},
        ceiling=25.6 * GIB,
        omlx_active=1,
    )
    g = guard(e)
    end = g.begin(OMLX, "busy")
    before = metric_value(_REFUSALS, engine=OLLAMA, reason="projected-exceeds")
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "qwen")
    assert "after waiting" in str(err.value)
    end()
    assert metric_value(_REFUSALS, engine=OLLAMA, reason="projected-exceeds") == (before or 0) + 1


async def test_a_transition_refusal_counts_reason_transition_active():
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"loading": {"size": GIB, "loaded": False}},
        ceiling=8 * GIB,
        loading_polls=[True] * 100,
        status_loading_polls=[True] * 100,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lg, "_POLL_S", 0.01)  # burn the deadline inside the poll budget
    lg.set_load_wait("0.06")
    before = metric_value(_REFUSALS, engine=OLLAMA, reason="transition-active")
    waits = wait_count(OLLAMA, "engine_transition")
    try:
        with pytest.raises(lg.LoadRefusedError) as err:
            await guard(e).admit(OLLAMA_URL, "m")
        assert "transition still active" in str(err.value)
    finally:
        monkeypatch.undo()
    assert metric_value(_REFUSALS, engine=OLLAMA, reason="transition-active") == (before or 0) + 1
    assert wait_count(OLLAMA, "engine_transition") > waits


async def test_a_cold_load_lock_timeout_counts_reason_deadline():
    e = Engines(omlx={"a": {"size": 16 * GIB}, "b": {"size": 16 * GIB}})
    g = guard(e)
    lg.set_load_wait("30")
    first = await g.admit_omlx("a")
    assert first is not None
    lg.set_load_wait("0.05")
    before = metric_value(_REFUSALS, engine=OMLX, reason="deadline")
    waits = wait_count(OMLX, "in_flight")
    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit_omlx("b")
    assert "another model load" in str(err.value)
    assert metric_value(_REFUSALS, engine=OMLX, reason="deadline") == (before or 0) + 1
    assert wait_count(OMLX, "in_flight") == waits + 1  # the lock wait, once
    first()


async def test_unloads_count_by_engine_and_reason():
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        ceiling=40 * GIB,
    )
    before_omlx = metric_value(_UNLOADS, engine=OMLX, reason="idle_omlx")
    release = await guard(e).admit(OLLAMA_URL, "m")
    assert release is not None and e.unloaded == ["idle"]
    release()
    assert metric_value(_UNLOADS, engine=OMLX, reason="idle_omlx") == (before_omlx or 0) + 1

    queued = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        ceiling=40 * GIB,
        unload_status_code=202,
        unload_sticks=True,
    )
    lg.set_load_wait("0.06")
    before_queued = metric_value(_UNLOADS, engine=OMLX, reason="queued_202")
    with pytest.raises(lg.LoadRefusedError):
        await guard(queued).admit(OLLAMA_URL, "m")
    assert metric_value(_UNLOADS, engine=OMLX, reason="queued_202") == (before_queued or 0) + 1

    hidden = Engines(ollama={"devstral": int(1.8 * GIB)}, tags={"kat": 22 * GIB}, ceiling=21 * GIB)
    hidden.hidden["devstral"] = int(13.2 * GIB)
    before_ollama = metric_value(_UNLOADS, engine=OLLAMA, reason="idle_ollama")
    release = await guard(hidden).admit(OLLAMA_URL, "kat")
    assert release is not None and "devstral" not in hidden.ollama
    release()
    assert metric_value(_UNLOADS, engine=OLLAMA, reason="idle_ollama") == (before_ollama or 0) + 1


async def test_warm_loads_are_not_counted_as_admissions():
    e = Engines(
        omlx={"a": {"size": GIB, "loaded": True}},
        ollama={"m": 5 * GIB},
        tags={"m": GIB},
        ceiling=40 * GIB,
    )
    g = guard(e)
    before_omlx = metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_immediately")
    before_ollama = metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_immediately")
    assert await g.admit_omlx("a") is None
    assert await g.admit(OLLAMA_URL, "m") is None
    assert metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_immediately") == (
        before_omlx or 0
    )
    assert metric_value(_ADMISSIONS, engine=OLLAMA, outcome="admitted_immediately") == (
        before_ollama or 0
    )


async def test_omlx_cold_loads_count_immediate_then_after_wait():
    e = Engines(omlx={"a": {"size": 16 * GIB}, "b": {"size": 16 * GIB}})
    g = guard(e)
    lg.set_load_wait("30")
    before_imm = metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_immediately")
    before_wait = metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_after_wait")
    first = await g.admit_omlx("a")
    assert first is not None
    assert (
        metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_immediately")
        == (before_imm or 0) + 1
    )
    second = asyncio.create_task(g.admit_omlx("b"))
    await asyncio.sleep(0)
    assert not second.done()
    e.omlx["a"]["loaded"] = True
    release_b = await asyncio.wait_for(second, 2)
    assert release_b is not None
    assert (
        metric_value(_ADMISSIONS, engine=OMLX, outcome="admitted_after_wait")
        == (before_wait or 0) + 1
    )
    first()
    release_b()


async def test_a_free_that_never_settles_counts_reason_free_settle_and_the_stage(monkeypatch):
    e = Engines(ollama={"idle": GIB}, tags={"m": 20 * GIB}, ceiling=8 * GIB, unload_sticks=True)
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    lg.set_load_wait("0.06")
    before = metric_value(_REFUSALS, engine=OLLAMA, reason="free-settle")
    quiet = metric_value(_REFUSALS, engine=OLLAMA, reason="quiet")
    projected = metric_value(_REFUSALS, engine=OLLAMA, reason="projected-exceeds")
    waits = wait_count(OLLAMA, "free_settle")
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    assert "free of idle did not settle" in str(err.value)
    assert metric_value(_REFUSALS, engine=OLLAMA, reason="free-settle") == (before or 0) + 1
    assert (metric_value(_REFUSALS, engine=OLLAMA, reason="quiet") or 0.0) == (quiet or 0.0)
    assert (metric_value(_REFUSALS, engine=OLLAMA, reason="projected-exceeds") or 0.0) == (
        projected or 0.0
    )
    assert wait_count(OLLAMA, "free_settle") > waits


async def test_settle_seconds_record_each_landed_free_by_engine(monkeypatch):
    monkeypatch.setattr(lg, "_POLL_S", 0.01)
    lg.set_load_wait("1")
    ollama = Engines(
        ollama={"devstral": int(1.8 * GIB)},
        tags={"kat": 22 * GIB},
        ceiling=21 * GIB,
        unload_removal_polls={"devstral": 0},
        ceiling_rise_polls={"devstral": 1},
    )
    ollama.hidden["devstral"] = int(13.2 * GIB)
    before = settle_count(OLLAMA)
    release = await guard(ollama).admit(OLLAMA_URL, "kat")
    assert release is not None and "devstral" not in ollama.ollama
    release()
    assert settle_count(OLLAMA) == before + 1

    queued = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
        omlx_memory=4 * GIB,
    )
    before = settle_count(OMLX)
    task = asyncio.create_task(guard(queued).admit(OLLAMA_URL, "m"))
    asyncio.get_running_loop().call_later(0.05, lambda: setattr(queued, "omlx_memory", 0.0))
    release = await asyncio.wait_for(task, 2)
    assert release is not None
    release()
    assert settle_count(OMLX) == before + 1


async def test_a_queued_omlx_unload_that_never_settles_counts_reason_free_settle():
    e = Engines(
        tags={"m": 30 * GIB},
        omlx={"idle": {"size": 4 * GIB, "loaded": True}},
        unload_status_code=202,
        unload_sticks=True,
    )
    lg.set_load_wait("0.06")
    before = metric_value(_REFUSALS, engine=OLLAMA, reason="free-settle")
    with pytest.raises(lg.LoadRefusedError) as err:
        await guard(e).admit(OLLAMA_URL, "m")
    assert "free of idle did not settle" in str(err.value)
    assert metric_value(_REFUSALS, engine=OLLAMA, reason="free-settle") == (before or 0) + 1
