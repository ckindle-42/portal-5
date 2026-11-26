"""Host-memory admission across Ollama and oMLX (portal/platform/inference/load_guard.py)."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from portal.platform.inference import load_guard as lg
from portal.platform.inference.cluster_backends import Backend
from portal.platform.inference.load_guard import OLLAMA
from portal.platform.inference.ollama_native import OllamaNativeTransport
from portal.platform.inference.router.lifespan import _cross_engine_copies

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
        shows: dict[str, dict[str, Any]] | None = None,
        omlx: dict[str, dict[str, Any]] | None = None,
        ceiling: float = 40 * GIB,
        omlx_ok: bool = True,
        omlx_active: int = 0,
        omlx_waiting: int = 0,
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
        ollama_unload_status_code: int = 200,
        unload_status_codes: dict[str, int] | None = None,
        unload_sticks: bool = False,
        actual_sizes: dict[str, float] | None = None,
        unload_counter_drops: dict[str, float] | None = None,
        immediate_counter_drops: set[str] | None = None,
        unload_loaded_flips: set[str] | None = None,
        unload_removal_polls: dict[str, int] | None = None,
        ceiling_rise_polls: dict[str, int] | None = None,
        omlx_release_polls: dict[str, int] | None = None,
        forced_loading: set[str] | None = None,
        omit_estimated_size: set[str] | None = None,
        defer_ceiling_rise: set[str] | None = None,
    ) -> None:
        self.ollama = dict(ollama or {})
        self.tags = dict(tags or {})
        self.shows = dict(shows or {})
        self.omlx = {k: dict(v) for k, v in (omlx or {}).items()}
        self.ceiling = ceiling
        self.omlx_ok = omlx_ok
        self.omlx_active = omlx_active
        self.omlx_waiting = omlx_waiting
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
        self.ollama_unload_status_code = ollama_unload_status_code
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
        #: Accepted unloads (200/202) whose loaded-flip and counter release land
        #: only after N /v1/models/status reads.
        self.omlx_release_polls = dict(omlx_release_polls or {})
        self.pending_omlx_releases: dict[str, int] = {}
        #: Models whose admin payload omits estimated_size (the actual_size fallback).
        self.omit_estimated_size = set(omit_estimated_size or set())
        #: Models whose hidden bytes reach the ceiling one status read after the unload
        #: (the host returns the pages asynchronously).
        self.defer_ceiling_rise = set(defer_ceiling_rise or set())
        self.pending_ceiling_rises: dict[str, tuple[int, int]] = {}
        self.pending_counter_drops: dict[str, tuple[float, int]] = {}
        self.unloaded: list[str] = []
        self.events: list[tuple[str, str]] = []
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
            self.events.append(("ollama_unload", model))
            if self.ollama_unload_status_code >= 400:
                return httpx.Response(self.ollama_unload_status_code, json={"error": "rejected"})
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
            model = json.loads(req.content).get("model", "")
            return httpx.Response(200, json={"capabilities": [], **self.shows.get(model, {})})
        if path == "/api/chat":
            model = json.loads(req.content)["model"]
            self.chats.append(model)
            self.events.append(("ollama_chat", model))
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
        if name in self.omlx_release_polls and status_code in (200, 202) and not self.unload_sticks:
            self.pending_omlx_releases[name] = self.omlx_release_polls[name]
        elif status_code == 200 and not self.unload_sticks:
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
        self.events.append(("omlx_unload", name))
        return httpx.Response(status_code, json={})

    def _defer_counter_drop(self, name: str) -> None:
        """Drop the counter with the 202, or one status read later."""
        drop = self.unload_counter_drops[name]
        if name in self.immediate_counter_drops:
            self.omlx_memory = max(0.0, float(self.omlx_memory or 0) - drop)
        else:
            self.pending_counter_drops[name] = (drop, 1)

    def _apply_pending_omlx_releases(self) -> None:
        for name, polls in list(self.pending_omlx_releases.items()):
            if polls > 0:
                self.pending_omlx_releases[name] = polls - 1
            else:
                self.omlx[name]["loaded"] = False
                del self.pending_omlx_releases[name]

    def _omlx_response(self, req: httpx.Request, path: str) -> httpx.Response | None:
        if path == "/v1/models/status":
            if not self.omlx_ok:
                return httpx.Response(503)
            self._apply_pending_omlx_releases()
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
                    "waiting_requests": self.omlx_waiting,
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
            self.events.append(("omlx_chat", model))
            self.omlx.setdefault(model, {"size": 4 * GIB})["loaded"] = True
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return None

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture(autouse=True)
def _fast(monkeypatch, tmp_path):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(lg.asyncio, "sleep", lambda s, _r=real_sleep: _r(0))
    monkeypatch.setattr(lg, "_POLL_S", 0.0)
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path / "guard-locks")
    # oMLX's own prefill-safe share of its ceiling, pinned so oMLX admission
    # arithmetic does not depend on the host's ~/.omlx/settings.json.
    monkeypatch.setattr(lg, "_OMLX_PREFILL_ZONE", 0.8)
    # ...and its balanced-tier share of other apps' active memory, likewise.
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", 0.25)
    monkeypatch.delenv("LOAD_GUARD", raising=False)
    monkeypatch.delenv("OMLX_PREFILL_SAFE_ZONE_RATIO", raising=False)
    monkeypatch.delenv("OMLX_OTHER_APP_RECLAIM_RATIO", raising=False)
    monkeypatch.delenv("OMLX_MEMORY_GUARD_TIER", raising=False)
    lg.set_load_wait(None)
    monkeypatch.setattr(lg, "_WAIT_S", 0.0)  # refuse at once unless a test opts into waiting
    from portal.platform.inference.router.parallel_seat import YIELD

    YIELD._pins = 0
    YIELD._held.clear()
    YIELD._clear.set()


def guard(
    e: Engines,
    ollama_url: str | None = OLLAMA_URL,
    counterpart: Any = None,
) -> lg.LoadGuard:
    return lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=e.transport()),
        ollama_url=lambda: ollama_url,
        counterpart=counterpart,
    )


async def test_reclaim_idle_memory_reports_resident_models_that_still_hold_memory():
    e = Engines(
        ollama={"busy-qwen": 4 * GIB},
        omlx={"busy-mlx": {"size": 5 * GIB, "loaded": True, "pinned": True}},
    )
    g = guard(e)
    end = g.begin(OLLAMA, "busy-qwen")
    try:
        result = await g.reclaim_idle_memory(OLLAMA_URL, 100 * GIB)
    finally:
        end()

    assert result["unloads"] == []
    assert result["residents"] == [
        {"engine": OLLAMA, "model": "busy-qwen", "reported_gib": 4.0},
        {"engine": lg.OMLX, "model": "busy-mlx", "reported_gib": 5.0},
    ]


async def test_reclaim_idle_memory_can_evict_a_recent_idle_seat_for_a_job(caplog):
    e = Engines(ollama={"hot-seat": 6 * GIB})
    sibling = guard(e)
    sibling.begin(OLLAMA, "hot-seat")()
    g = guard(e)  # a different worker: no local _last_access for hot-seat
    g.protect(OLLAMA, "hot-seat", 900)
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        result = await g.reclaim_idle_memory(OLLAMA_URL, GIB // 25)
    assert [item["model"] for item in result["unloads"]] == ["hot-seat"]
    assert e.unload_calls == {"hot-seat": 1}
    assert "evicted hot-seat for job media (idle, hot-seat override)" in caplog.text


async def test_reclaim_idle_memory_evicts_an_idle_hot_omlx_seat_for_a_job(caplog):
    e = Engines(omlx={"hot-mlx": {"size": 5 * GIB, "loaded": True}})
    sibling = guard(e)
    sibling.begin(lg.OMLX, "hot-mlx")()
    g = guard(e)
    g.protect(lg.OMLX, "hot-mlx", 900)
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        result = await g.reclaim_idle_memory(OLLAMA_URL, GIB)
    assert result["unloads"] == [{"engine": lg.OMLX, "model": "hot-mlx", "status": "unloaded"}]
    assert e.unloaded == ["hot-mlx"]
    assert "evicted hot-mlx for job media (idle, hot-seat override)" in caplog.text


async def test_reclaim_idle_memory_never_evicts_an_active_omlx_seat_for_a_job():
    e = Engines(omlx={"hot-mlx": {"size": 5 * GIB, "loaded": True}})
    g = guard(e)
    g.protect(lg.OMLX, "hot-mlx", 900)
    end = g.begin(lg.OMLX, "hot-mlx")
    try:
        result = await g.reclaim_idle_memory(OLLAMA_URL, GIB)
    finally:
        end()
    assert result["unloads"] == []
    assert e.unloaded == []


async def test_internal_job_admission_logs_the_hot_seat_override(caplog):
    e = Engines(
        omlx={
            "hot-chat": {"size": 20 * GIB, "loaded": True},
            "job-model": {"size": 14 * GIB, "loaded": False},
        },
        ceiling=22 * GIB,
    )
    g = guard(e)
    g.protect(lg.OMLX, "hot-chat", 900)
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await g.admit_omlx("job-model", workspace_id="hunt-reasoning")
    assert release is not None
    assert e.unloaded == ["hot-chat"]
    assert "evicted hot-chat for job hunt-reasoning (idle, hot-seat override)" in caplog.text
    release()


async def test_ollama_idle_lru_orders_by_cross_worker_recency():
    """The eviction order claimed 'idle LRU' but sorted by this worker's stamps only:
    a sibling worker's fresher seat could be evicted before a truly stale one."""
    e = Engines(ollama={"aaa-fresh": 4 * GIB, "zzz-stale": 4 * GIB})
    sibling = guard(e)
    sibling.begin(OLLAMA, "aaa-fresh")()
    stale = time.time() - 300  # outside the reclaim shield, newer than zzz-stale's "never"
    lg.LoadGuard._activity_path(OLLAMA, "aaa-fresh").write_text(f"{stale:.6f}")
    g = guard(e)
    result = await g.reclaim_idle_memory(OLLAMA_URL, 3 * GIB)
    assert [u["model"] for u in result["unloads"]] == ["zzz-stale"]


def test_has_activity_covers_cross_worker_admission_and_request_leases():
    g = lg.LoadGuard(omlx_url=lambda: None)
    admission = g._shared_process_lock("admissions.lock")
    assert admission is not None
    assert g.has_activity()
    g._release_activity_lock(admission)

    active = g._activity_lock(OLLAMA, "seat")
    assert active is not None
    assert g.has_activity()
    g._release_activity_lock(active)
    assert not g.has_activity()


async def test_omlx_cold_load_frees_its_own_idle_resident_lru_first():
    """2026-10-31 canary: idle oMLX residents were freed only after the 507 and GGUF failover."""
    e = Engines(
        omlx={
            "old-seat": {"size": 8 * GIB, "loaded": True, "last": 100},
            "new-seat": {"size": 8 * GIB, "loaded": True, "last": 200},
            "mlx": {"size": 14 * GIB, "loaded": False},
        },
        ceiling=24 * GIB,
    )
    g = guard(e)
    lg.set_load_wait("5")
    release = await g.admit_omlx("mlx")
    assert release is not None
    # Inside the 80% prefill zone one seat is short: 24 GiB ceiling leaves 17.2 GiB
    # for 14 GiB only after both 8 GiB residents go, LRU first.
    assert e.unloaded == ["old-seat", "new-seat"]
    assert "mlx" not in e.unload_calls  # the target is never self-evicted
    assert not e.omlx["old-seat"]["loaded"]
    release()


@pytest.mark.parametrize("status_code", [200, 202])
async def test_omlx_cold_load_waits_out_a_delayed_release_then_admits(status_code):
    """R2 repro: an accepted unload whose release had not yet reached oMLX's counter."""
    e = Engines(
        omlx={
            "idle": {"size": 8 * GIB, "loaded": True},
            "mlx": {"size": 14 * GIB, "loaded": False},
        },
        # 24 GiB: 80% of 16 GiB headroom is short of 14 GiB, of 24 GiB it is not.
        ceiling=24 * GIB,
        unload_status_codes={"idle": status_code},
        omlx_release_polls={"idle": 5},
    )
    g = guard(e)
    lg.set_load_wait("2")
    release = await g.admit_omlx("mlx")
    assert release is not None
    assert e.unload_calls == {"idle": 1}  # waited out, never re-posted
    assert "mlx" not in e.unload_calls
    assert not e.omlx["idle"]["loaded"]  # the release landed
    release()


def _short_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settle polls advance the deadline; the autouse sleep replacement does not."""
    real_sleep = asyncio.sleep

    async def _sleep(seconds: float) -> None:
        await real_sleep(0.05)

    monkeypatch.setattr(lg.asyncio, "sleep", _sleep)


async def test_omlx_cold_load_names_a_free_that_left_ps_before_its_headroom_rose(
    caplog, monkeypatch, tmp_path
):
    """R4: an accepted unload gone from /api/ps while its settle pends still blocks, named."""
    engines = Engines(
        ollama={"seat": 2 * GIB},
        omlx={"mlx": {"size": 14 * GIB, "loaded": False}},
        ceiling=15 * GIB,
        ceiling_rise_polls={"seat": 10_000},
    )
    engines.hidden["seat"] = 2 * GIB
    guard_obj = guard(engines)
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path)
    lg.set_load_wait("0.05")
    _short_sleep(monkeypatch)
    with (
        caplog.at_level(logging.WARNING, logger=lg.logger.name),
        pytest.raises(lg.LoadRefusedError) as err,
    ):
        await guard_obj.admit_omlx("mlx")
    text = str(err.value)
    assert "seat (2.0 GiB, unload unsettled)" in text
    assert "need 14.0 GiB" in text and "waited" in text
    assert any(
        r.levelno == logging.WARNING
        and "seat" in r.getMessage()
        and "unload unsettled" in r.getMessage()
        and "waited" in r.getMessage()
        for r in caplog.records
    )
    assert engines.unload_calls == {"seat": 1}
    assert engines.ollama == {}  # the free was accepted; only the ceiling rise never landed
    assert not guard_obj._lock.locked()
    reacquired = await guard_obj._acquire(OLLAMA, time.monotonic() + 0.1, "after-settle-refusal")
    reacquired()


async def test_ollama_cold_load_refuses_and_logs_a_free_that_never_settles(
    caplog, monkeypatch, tmp_path
):
    engines = Engines(
        tags={"target": 20 * GIB},
        ollama={"stuck": 10 * GIB},
        ceiling=9 * GIB,
        unload_sticks=True,
    )
    guard_obj = guard(engines)
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path)
    lg.set_load_wait("0.05")
    _short_sleep(monkeypatch)

    with (
        caplog.at_level(logging.WARNING, logger=lg.logger.name),
        pytest.raises(lg.LoadRefusedError) as err,
    ):
        await guard_obj.admit(OLLAMA_URL, "target")

    assert err.value.reason == "free-settle"
    assert "free of stuck did not settle" in str(err.value)
    assert any("free of stuck did not settle" in record.getMessage() for record in caplog.records)
    assert not guard_obj._lock.locked()
    reacquired = await guard_obj._acquire(OLLAMA, time.monotonic() + 0.1, "after-ollama-free")
    reacquired()


async def test_omlx_make_room_exception_releases_cold_load_lock(monkeypatch, tmp_path):
    engines = Engines(
        omlx={"idle": {"size": 10 * GIB, "loaded": True}, "mlx": {"size": 14 * GIB}},
        ceiling=24 * GIB,
    )
    guard_obj = guard(engines)
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path)

    async def fail_during_make_room(*_args, **_kwargs):
        raise RuntimeError("make-room measurement failed")

    monkeypatch.setattr(guard_obj, "_advance_omlx_own_residents", fail_during_make_room)
    with pytest.raises(RuntimeError, match="make-room measurement failed"):
        await guard_obj.admit_omlx("mlx")

    assert not guard_obj._lock.locked()
    reacquired = await guard_obj._acquire(OLLAMA, time.monotonic() + 0.1, "after-make-room-error")
    reacquired()


async def test_ollama_measurement_error_keeps_latest_cold_load_lock(monkeypatch, tmp_path):
    guard_obj = guard(Engines(tags={"target": GIB}))
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path)

    async def fail_after_reacquire(_client, _base, model, deadline, held, release):
        release()
        current = await guard_obj._acquire(OLLAMA, deadline, model)
        held.append(current)
        raise RuntimeError("measurement failed after reacquire")

    monkeypatch.setattr(guard_obj, "_admit_ollama_locked", fail_after_reacquire)
    release = await guard_obj.admit(OLLAMA_URL, "target")

    assert release is not None
    release()
    assert not guard_obj._lock.locked()
    reacquired = await guard_obj._acquire(OLLAMA, time.monotonic() + 0.1, "after-measurement-error")
    reacquired()


async def test_process_cold_load_lock_timeout_is_bounded_and_logged(caplog, monkeypatch, tmp_path):
    monkeypatch.setattr(lg, "_PROCESS_LOCK_DIR", tmp_path)
    lock_path = tmp_path / "cold-load.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard_obj = lg.LoadGuard(omlx_url=lambda: None)
        with (
            caplog.at_level(logging.WARNING, logger=lg.logger.name),
            pytest.raises(lg.LoadRefusedError, match="another model load"),
        ):
            await guard_obj._acquire(OLLAMA, time.monotonic() + 0.02, "blocked-model")
        assert not guard_obj._lock.locked()
        assert any("process cold-load lock" in record.getMessage() for record in caplog.records)
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)


def test_a_sized_kv_cache_is_not_padded_by_the_weight_factor():
    """2026-11-16: 20.55 GiB of weights at 256k projected 36.3 GiB (×1.25 + 10.6 GiB KV)
    and was refused at 35.2 GiB headroom; the factor is for geometry the guard cannot size."""
    show = {
        "parameters": "num_ctx 262144\ncache-type-k q8_0\ncache-type-v q8_0",
        "model_info": {
            "general.architecture": "qwen35moe",
            "qwen35moe.block_count": 40,
            "qwen35moe.attention.head_count_kv": 4,
            "qwen35moe.attention.key_length": 128,
            "qwen35moe.attention.value_length": 128,
        },
    }
    kv = lg._ollama_kv_bytes(lg._show_values(show), 262144)
    assert kv is not None and kv / GIB == pytest.approx(10.62, abs=0.01)
    need = lg._estimate_ollama_need(int(20.55 * GIB), show, "seat")
    assert need == pytest.approx(20.55 * GIB + kv)
    assert need < 20.55 * GIB * lg._FACTOR + kv


def test_glm4moelite_sizes_its_mla_cache_as_one_latent_per_layer():
    show = {
        "parameters": "num_ctx 24576\ncache-type-k q8_0\ncache-type-v q8_0",
        "model_info": {
            "general.architecture": "glm4moelite",
            "glm4moelite.block_count": 47,
            "glm4moelite.attention.head_count_kv": 20,
            "glm4moelite.attention.key_length": 256,
            "glm4moelite.attention.value_length": 256,
            "glm4moelite.attention.kv_lora_rank": 512,
            "glm4moelite.rope.dimension_count": 64,
        },
    }
    values = lg._show_values(show)
    model = "glm-4.7-flash:Q4_K_M-ctx24k"
    weights = 19_019_270_615  # live /api/tags size

    kv = lg._ollama_kv_bytes(values, 24576)
    assert kv is not None and kv / GIB == pytest.approx(1.244, abs=0.001)
    assert lg._estimate_ollama_need(weights, show, model) / GIB == pytest.approx(18.957, abs=0.001)


async def test_a_256k_ollama_seat_admits_in_the_headroom_that_refused_it():
    """auto-general-uncensored::throwaway, 2026-11-16 03:15Z: 36.3 GiB projected against
    35.2 GiB available (oMLX headroom 37.2, no idle Ollama, margin 2) — a 1.1 GiB refusal
    of a seat that is 31.2 GiB of weights plus its sized cache."""
    model = "portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k"
    show = {
        "parameters": "num_ctx 262144",
        "model_info": {
            "general.architecture": "qwen35moe",
            "qwen35moe.block_count": 40,
            "qwen35moe.attention.head_count_kv": 4,
            "qwen35moe.attention.key_length": 128,
            "qwen35moe.attention.value_length": 128,
        },
    }
    e = Engines(
        tags={model: int(20.55 * GIB)},
        shows={model: show},
        ceiling=39.2 * GIB,
        omlx_memory=2 * GIB,
    )
    g = guard(e)
    async with httpx.AsyncClient(transport=e.transport()) as client:
        need = await g._need(client, OLLAMA_URL, model)
        capacity = await g._headroom(client)
    assert capacity is not None
    headroom, _ = capacity
    available = g._ollama_available(headroom, {}, 0.0) - lg._MARGIN
    assert available / GIB == pytest.approx(35.2)
    assert need / GIB == pytest.approx(31.175, abs=0.01)
    release = await g.admit(OLLAMA_URL, model)
    assert release is not None
    release()


async def test_the_measured_chat_need_does_not_fit_beside_the_hunt() -> None:
    """2026-11-12: final_ceiling 38.6 GiB already includes the hunt's footprint.

    Headroom 20.6 GiB is additional room, and 29.8 GiB does not fit in the
    18.6 GiB left after the 2 GiB margin. 58% host-free is a different quantity.
    """
    resident = (38.6 - 20.6) * GIB
    e = Engines(
        omlx={"gemma-4-26b-a4b-it-QAT-4bit": {"size": resident, "loaded": True}},
        ceiling=38.6 * GIB,
        omlx_memory=resident,
    )
    g = guard(e)
    async with g._client() as client:
        capacity = await g._headroom(client)
    assert capacity is not None
    headroom, used = capacity
    available = g._ollama_available(headroom, {}, 0.0) - lg._MARGIN
    assert used / GIB == pytest.approx(18.0)
    assert headroom / GIB == pytest.approx(20.6)
    assert available / GIB == pytest.approx(18.6)
    assert available < 29.8 * GIB


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


async def test_ollama_load_makes_room_from_omlx_and_keeps_its_copy_last(caplog):
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={
            "omlx-target": {"size": 22 * GIB, "loaded": True, "last": 1},
            "old-idle": {"size": 3 * GIB, "loaded": True, "last": 2},
        },
        ceiling=int(50.2 * GIB),
    )
    g = guard(e, counterpart=lambda engine, _model: "omlx-target" if engine == OLLAMA else None)

    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unloaded == ["old-idle"]
    assert e.omlx["omlx-target"]["loaded"]
    assert "evicted old-idle on omlx" in caplog.text
    assert "3.0 GiB" in caplog.text and "idle" in caplog.text
    release()


async def test_ollama_load_tries_idle_ollama_before_its_omlx_copy():
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        ollama={"old-idle": 3 * GIB},
        omlx={"omlx-target": {"size": GIB, "loaded": True}},
        ceiling=int(22.2 * GIB),
    )
    e.hidden["old-idle"] = 7 * GIB
    g = guard(e, counterpart=lambda engine, _model: "omlx-target" if engine == OLLAMA else None)

    release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unload_calls == {"old-idle": 1}
    assert e.omlx["omlx-target"]["loaded"]
    release()


async def test_ollama_load_waits_for_pending_ollama_release_before_its_omlx_copy():
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        ollama={"old-idle": GIB // 8},
        omlx={"omlx-target": {"size": GIB, "loaded": True}},
        ceiling=int(22.2 * GIB),
        defer_ceiling_rise={"old-idle"},
    )
    e.hidden["old-idle"] = 7 * GIB
    lg.set_load_wait("30")
    g = guard(e, counterpart=lambda engine, _model: "omlx-target" if engine == OLLAMA else None)

    release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unload_calls == {"old-idle": 1}
    assert e.omlx["omlx-target"]["loaded"]
    release()


async def test_ollama_load_never_evicts_its_loaded_omlx_copy_to_fit():
    """2026-11-20: the guard evicted oMLX Qwen3.8 (16.6 GiB) to load the same seat's
    Ollama GGUF, then the GGUF did not fit either — a full unload/reload on both
    engines. The seat copy is the next request's engine; refuse instead."""
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={"omlx-target": {"size": 22 * GIB, "loaded": True}},
        ceiling=int(24 * GIB),
    )
    g = guard(e, counterpart=lambda engine, _model: "omlx-target" if engine == OLLAMA else None)

    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "target")

    assert e.unloaded == []
    assert e.omlx["omlx-target"]["loaded"]


async def test_ollama_load_refuses_when_every_omlx_resident_is_in_flight():
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={"busy": {"size": 25 * GIB, "loaded": True}},
        ceiling=int(48.2 * GIB),
    )
    g = guard(e)
    end = g.begin(lg.OMLX, "busy")

    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "target")

    assert e.unloaded == []
    end()


async def test_ollama_load_spares_a_protected_omlx_resident_when_idle_memory_fits():
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={
            "keeper": {"size": 22 * GIB, "loaded": True, "last": 1},
            "old-idle": {"size": 3 * GIB, "loaded": True, "last": 2},
        },
        ceiling=int(50.2 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "keeper", 300)

    release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unloaded == ["old-idle"]
    assert e.omlx["keeper"]["loaded"]
    release()


async def test_an_ollama_load_spends_an_idle_omlx_failover_shield_that_buys_it():
    """2026-11-26: the 25 GiB idle shield refused this load outright for its whole
    window; now it is evicted last and the load is admitted."""
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={"failover-source": {"size": 25 * GIB, "loaded": True}},
        ceiling=int(48.2 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "failover-source", failover=True)

    release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unloaded == ["failover-source"]
    assert not e.omlx["failover-source"]["loaded"]
    release()


async def test_an_ollama_load_keeps_an_omlx_failover_shield_that_cannot_buy_it():
    """A 3 GiB shield cannot cover the gap under this ceiling, so it stays and the
    refusal names the bytes it held for the loaded seat."""
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={"failover-source": {"size": 3 * GIB, "loaded": True}},
        ceiling=int(9 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "failover-source", failover=True)

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit(OLLAMA_URL, "target")

    assert e.unloaded == []
    assert e.omlx["failover-source"]["loaded"]
    assert "held for the loaded oMLX seat" in str(err.value)


async def test_omlx_load_makes_room_from_ollama_and_keeps_its_copy_last():
    e = Engines(
        ollama={"target": 22 * GIB, "old-idle": 3 * GIB},
        omlx={"omlx-target": {"size": 14 * GIB, "loaded": False}},
        ceiling=18 * GIB,
    )
    e.hidden["old-idle"] = 4 * GIB
    g = guard(e, counterpart=lambda engine, _model: "target" if engine == lg.OMLX else None)

    release = await g.admit_omlx("omlx-target")

    assert release is not None
    assert e.unload_calls == {"old-idle": 1}
    assert e.ollama == {"target": 22 * GIB}
    release()


async def test_omlx_load_refuses_rather_than_evict_its_own_ollama_copy():
    """2026-11-20 (B3): a cold oMLX load must not unload the same seat's idle GGUF
    fallback. The router serves the copy that is already loaded instead of thrashing."""
    e = Engines(
        ollama={"target": 22 * GIB},
        omlx={"omlx-target": {"size": 14 * GIB, "loaded": False}},
        ceiling=10 * GIB,
    )
    g = guard(e, counterpart=lambda engine, _model: "target" if engine == lg.OMLX else None)

    with pytest.raises(lg.LoadRefusedError):
        await g.admit_omlx("omlx-target")

    assert e.unload_calls == {}
    assert e.ollama == {"target": 22 * GIB}


async def test_free_ollama_never_unloads_the_model_it_is_admitting():
    """A pending Ollama admission must not evict the copy it is loading (B3 2026-11-20)."""
    e = Engines(ollama={"target": 10 * GIB, "old": 5 * GIB}, ceiling=40 * GIB)
    g = guard(e)

    async with httpx.AsyncClient(transport=e.transport()) as client:
        requested = await g._free_ollama(
            client,
            OLLAMA_URL,
            {"target": 10 * GIB, "old": 5 * GIB},
            want=6 * GIB,
            exclude={"target"},
        )

    assert set(requested) == {"old"}
    assert e.unload_calls == {"old": 1}


def test_cross_engine_copy_resolves_configured_aliases_both_ways():
    registry = SimpleNamespace(
        list_backends=lambda: [
            Backend(
                id="omlx-general",
                type="omlx",
                url="http://omlx:8085",
                group="general",
                models=["omlx-target"],
                aliases={
                    "ollama-target": "omlx-target",
                    "ollama-target-shortctx": "omlx-target",
                },
            ),
            Backend(
                id="ollama-general",
                type="ollama",
                url="http://ollama:11434",
                group="general",
                models=["ollama-target", "ollama-target-shortctx"],
            ),
        ]
    )

    assert _cross_engine_copies(registry, OLLAMA, "ollama-target") == {"omlx-target"}
    assert _cross_engine_copies(registry, lg.OMLX, "omlx-target") == {
        "ollama-target",
        "ollama-target-shortctx",
    }


async def test_a_sibling_workers_omlx_request_is_not_foreign_traffic():
    """2026-11-19: PIPELINE_WORKERS=2, so oMLX serving one request on the other worker made
    every idle resident look untouchable ("serves requests the pipeline did not send")."""
    e = Engines(
        tags={"target": int(12 * GIB)},
        omlx={
            "serving": {"size": 8 * GIB, "loaded": True, "last": 9},
            "idle": {"size": 8 * GIB, "loaded": True, "last": 1},
        },
        ceiling=28 * GIB,
        omlx_active=1,
    )
    g = guard(e)
    sibling = g._activity_lock(lg.OMLX, "serving")  # the other worker's in-flight request
    assert sibling is not None
    release = await g.admit(OLLAMA_URL, "target")
    assert release is not None
    assert e.unload_calls == {"idle": 1}  # the idle resident, never the one being served
    assert e.omlx["serving"]["loaded"]
    release()
    g._release_activity_lock(sibling)


NEMOTRON = "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"
QWEN_OMLX = "Qwen3.8-27B-oQ4e-mtp"
INKLING = "inkling-2-mini:ctx256k"
_NEMOTRON_NEED = 23.8 * GIB


def _nemotron_tags() -> dict[str, int]:
    return {NEMOTRON: int(_NEMOTRON_NEED / lg._FACTOR)}


async def test_cold_ollama_load_wait_is_bounded_while_omlx_turn_holds_lease(monkeypatch):
    e = Engines(
        tags=_nemotron_tags(),
        omlx={QWEN_OMLX: {"size": int(15.9 * GIB), "loaded": True}},
        ceiling=int(36.8 * GIB),
        omlx_memory=int(15.9 * GIB),
    )
    g = guard(e)
    end_turn = g.begin(lg.OMLX, QWEN_OMLX)
    now = [100.0]
    waits = 0

    def monotonic() -> float:
        return now[0]

    async def wait_change(seconds: float) -> None:
        nonlocal waits
        waits += 1
        now[0] += min(seconds, 0.05)
        if waits > 4:
            raise AssertionError("cold load kept extending its wait for the active oMLX turn")

    monkeypatch.setattr(lg.time, "monotonic", monotonic)
    monkeypatch.setattr(g, "_wait_change", wait_change)
    monkeypatch.setattr(lg, "_POLL_S", 0.05)
    lg.set_load_wait("0.1")

    try:
        with pytest.raises(lg.LoadRefusedError) as err:
            await g.admit(OLLAMA_URL, NEMOTRON)
    finally:
        end_turn()

    assert err.value.reason == "projected-exceeds"
    assert "after waiting" in str(err.value)
    assert "engine activity or memory release" in str(err.value)
    assert waits == 2


async def test_omlx_cold_load_wait_is_bounded_for_active_ollama_model(monkeypatch):
    g = guard(Engines(ollama={"active": GIB}))
    end_turn = g.begin(OLLAMA, "active")
    now = [50.0]
    waits = 0

    def monotonic() -> float:
        return now[0]

    async def wait_change(seconds: float) -> None:
        nonlocal waits
        waits += 1
        now[0] += min(seconds, 0.05)
        if waits > 4:
            raise AssertionError("oMLX load kept extending its wait for the active Ollama turn")

    monkeypatch.setattr(lg.time, "monotonic", monotonic)
    monkeypatch.setattr(g, "_wait_change", wait_change)
    monkeypatch.setattr(lg, "_POLL_S", 0.05)
    lg.set_load_wait("0.1")

    try:
        assert await g._wait_for_ollama_release(50.1, ["active"]) is False
    finally:
        end_turn()

    assert waits <= 3


def _tool_loop(e: Engines, g: lg.LoadGuard) -> OllamaNativeTransport:
    return OllamaNativeTransport(
        httpx.MockTransport(e.handler), is_ollama=lambda _base: True, guard=g
    )


async def _tool_turn(transport: OllamaNativeTransport) -> httpx.Response:
    async with httpx.AsyncClient(transport=transport) as client:
        return await client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={
                "model": NEMOTRON,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )


async def test_tool_loop_admits_nemotron_after_evicting_idle_omlx():
    """QAT 733985650: 23.8 GiB Ollama cold load, 14 GiB idle oMLX, tool-loop path."""
    e = Engines(
        tags=_nemotron_tags(),
        omlx={QWEN_OMLX: {"size": 14 * GIB, "loaded": True}},
        ceiling=int(14.6 * GIB) + 14 * GIB,
        omlx_memory=14 * GIB,
        unload_counter_drops={QWEN_OMLX: 14 * GIB},
        immediate_counter_drops={QWEN_OMLX},
    )
    g = guard(e)

    response = await _tool_turn(_tool_loop(e, g))

    assert response.status_code == 200
    assert e.unloaded == [QWEN_OMLX]
    assert e.chats == [NEMOTRON]


async def test_tool_loop_waits_for_a_sibling_ollama_resident_then_evicts_it(monkeypatch):
    """The logged quiet 507: inkling in flight on the other worker, ceiling 14.6 GiB,
    idle Ollama 0. The tool loop waits, then evicts the resident and admits Nemotron."""
    e = Engines(
        ollama={INKLING: GIB},
        tags=_nemotron_tags(),
        ceiling=int(14.6 * GIB),
    )
    e.hidden[INKLING] = int(20 * GIB)
    g = guard(e)
    sibling = g._activity_lock(OLLAMA, INKLING)
    assert sibling is not None
    assert g._sibling_workers_active()
    original_wait = lg.asyncio.wait_for
    waits = 0

    async def wait_for(awaitable: Any, timeout: float | None = None) -> Any:
        nonlocal waits
        waits += 1
        if waits == 3:
            # Loading probe, then the foreign probe, then the activity poll.
            g._release_activity_lock(sibling)
        if waits > 20:
            raise AssertionError("admission kept waiting after the sibling released")
        return await original_wait(awaitable, timeout)

    monkeypatch.setattr(lg.asyncio, "wait_for", wait_for)
    lg.set_load_wait("30")

    response = await _tool_turn(_tool_loop(e, g))
    assert waits >= 2

    assert response.status_code == 200, response.text
    assert e.unload_calls.get(INKLING) == 1
    assert e.chats == [NEMOTRON]
    assert "nothing in flight" not in response.text


async def test_tool_loop_retries_omlx_eviction_after_a_sibling_lease_drains(monkeypatch, caplog):
    """A large Ollama request waits for a sibling to release its oMLX resident."""
    model = "oversized-ollama-tag"
    idle = "idle-omlx"
    need = 29.4 * GIB
    resident = 21.0 * GIB
    e = Engines(
        tags={model: int(need / lg._FACTOR)},
        omlx={idle: {"size": int(resident), "loaded": True}},
        ceiling=int(11.1 * GIB + resident),
        omlx_memory=resident,
        unload_counter_drops={idle: resident},
        immediate_counter_drops={idle},
    )
    g = guard(e)
    sibling = g._activity_lock(lg.OMLX, idle)
    assert sibling is not None
    waits = 0

    async def release_sibling(_timeout: float) -> None:
        nonlocal waits
        waits += 1
        g._release_activity_lock(sibling)

    monkeypatch.setattr(g, "_wait_change", release_sibling)
    lg.set_load_wait("30")
    transport = OllamaNativeTransport(
        httpx.MockTransport(e.handler), is_ollama=lambda _base: True, guard=g
    )
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post(
                f"{OLLAMA_URL}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                },
            )

    assert waits >= 1
    assert response.status_code == 200, response.text
    assert e.unload_calls == {idle: 1}
    assert e.chats == [model]
    assert f"load_guard: eviction pass for {model}" in caplog.text


async def test_a_resident_omlx_seat_frees_idle_ollama_that_ate_its_prefill_share():
    """2026-11-19 auto-coding: the seat was already resident, so admission never measured;
    oMLX then aborted mid-prefill inside the room Ollama's idle residents had taken."""
    e = Engines(
        ollama={"nemotron": int(22 * GIB)},
        omlx={"seat": {"size": int(24 * GIB), "loaded": True}},
        ceiling=int(30 * GIB),
        omlx_memory=int(24 * GIB),
    )
    e.hidden["nemotron"] = int(6 * GIB)  # its release raises oMLX's host-derived ceiling
    g = guard(e)

    assert await g.admit_omlx("seat") is None

    assert e.unload_calls == {"nemotron": 1}
    assert e.omlx["seat"]["loaded"]  # never the seat the request is going to


async def test_a_resident_omlx_seat_leaves_memory_alone_inside_its_prefill_share():
    e = Engines(
        ollama={"idle": int(4 * GIB)},
        omlx={"seat": {"size": int(14 * GIB), "loaded": True}},
        ceiling=int(24 * GIB),
        omlx_memory=int(14 * GIB),
    )
    g = guard(e)

    assert await g.admit_omlx("seat") is None

    assert e.unload_calls == {}


async def test_a_resident_omlx_seat_spares_an_ollama_model_a_sibling_is_serving():
    e = Engines(
        ollama={"busy": int(20 * GIB), "idle": int(20 * GIB)},
        omlx={"seat": {"size": int(24 * GIB), "loaded": True}},
        ceiling=int(30 * GIB),
        omlx_memory=int(24 * GIB),
    )
    e.hidden["idle"] = int(8 * GIB)
    g = guard(e)
    sibling = g._activity_lock(lg.OLLAMA, "busy")
    assert sibling is not None

    assert await g.admit_omlx("seat") is None

    assert e.unload_calls == {"idle": 1}
    assert "busy" in e.ollama
    g._release_activity_lock(sibling)


async def test_a_resident_omlx_seat_with_nothing_idle_still_dispatches():
    e = Engines(
        omlx={"seat": {"size": int(24 * GIB), "loaded": True}},
        ceiling=int(25 * GIB),
        omlx_memory=int(24 * GIB),
    )
    g = guard(e)

    assert await g.admit_omlx("seat") is None  # fail open: the engine gets its chance

    assert e.unload_calls == {}


async def test_wait_header_is_clamped_and_parsed():
    lg.set_load_wait("999999")
    assert lg.load_wait_s() == lg._MAX_WAIT_S
    lg.set_load_wait("nonsense")
    assert lg.load_wait_s() == lg._WAIT_S
    lg.set_load_wait("12.5")
    assert lg.load_wait_s() == 12.5


_REAL_HOST_FREE_BYTES = lg.LoadGuard.host_free_bytes


async def test_host_free_bytes_includes_idle_omlx_residents():
    e = Engines(
        omlx={
            "a": {"size": int(20 * GIB), "loaded": True},
            "b": {"size": int(17 * GIB), "loaded": True},
        },
        ceiling=int(32 * GIB),
        omlx_memory=int(37 * GIB),
    )
    g = guard(e)

    free = await _REAL_HOST_FREE_BYTES(g, OLLAMA_URL)

    assert free is not None
    assert free == pytest.approx(32 * GIB)


async def test_host_free_bytes_excludes_omlx_when_foreign_active():
    e = Engines(
        omlx={"a": {"size": int(37 * GIB), "loaded": True}},
        ceiling=int(32 * GIB),
        omlx_memory=int(37 * GIB),
        omlx_active=1,
    )
    g = guard(e)

    free = await _REAL_HOST_FREE_BYTES(g, OLLAMA_URL)

    assert free is not None
    assert free == pytest.approx(-5 * GIB)


async def test_omlx_status_syncs_unloaded_hot_seat():
    from portal.platform.inference.router import placement

    e = Engines(
        omlx={"stale-model": {"size": int(16 * GIB), "loaded": False}},
        ceiling=int(32 * GIB),
        omlx_memory=0,
    )
    g = guard(e)
    placement.note_omlx_activity(OMLX_URL, "stale-model")
    assert placement.TRACKER.hot_model(placement.engine_key(OMLX_URL), 900) == "stale-model"

    await _REAL_HOST_FREE_BYTES(g, OLLAMA_URL)

    assert placement.TRACKER.hot_model(placement.engine_key(OMLX_URL), 900) is None


# ── the cross-engine ceiling (2026-11-20) ───────────────────────────────────
# oMLX derives its ceiling from host free + inactive memory, so an Ollama resident
# takes all but the engine's `other_app_reclaim_ratio` of its footprint off the room
# a loaded oMLX seat prefills in. Recorded live from oMLX 0.8.0 on 2026-11-20.
RECORDED_STATUS_080: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "omlx_status_080.json").read_text()
)
RECORDED_SEAT = "gemma-4-26b-a4b-it-QAT-4bit"


class RecordedOmlx:
    """The captured 0.8.0 /v1/models/status plus the Ollama reads a cold load makes."""

    def __init__(self, *, tags: dict[str, int], ollama: dict[str, int] | None = None) -> None:
        self.tags = tags
        self.ollama = dict(ollama or {})
        self.request_counts: dict[str, int] = {}

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.request_counts[path] = self.request_counts.get(path, 0) + 1
        if path == "/v1/models/status":
            return httpx.Response(200, json=RECORDED_STATUS_080)
        if path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.ollama.items()]}
            )
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": s} for n, s in self.tags.items()]}
            )
        if path == "/api/show":
            return httpx.Response(200, json={})
        if path == "/api/status":
            return httpx.Response(200, json={"active_requests": 0, "waiting_requests": 0})
        if path == "/api/generate":
            self.ollama.pop(json.loads(req.content)["model"], None)
            return httpx.Response(200, json={"done": True})
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def recorded_guard(e: RecordedOmlx) -> lg.LoadGuard:
    return lg.LoadGuard(
        omlx_url=lambda: OMLX_URL,
        pinned=lambda: "router",
        client=lambda: httpx.AsyncClient(transport=e.transport()),
        ollama_url=lambda: OLLAMA_URL,
    )


async def test_omlx_engine_busy_reads_active_and_waiting_requests():
    active = recorded_guard(Engines(omlx_active=1))
    queued = recorded_guard(Engines(omlx_waiting=1))
    idle = recorded_guard(Engines())
    local = recorded_guard(Engines())
    local._omlx_in_flight = lambda: 1

    assert await active.omlx_engine_busy()
    assert await queued.omlx_engine_busy()
    assert not await idle.omlx_engine_busy()
    assert await local.omlx_engine_busy()


def test_the_recorded_080_status_is_the_ceiling_the_guard_budgets():
    """0.8.0 exposes final_ceiling (its hard limit: min static, dynamic, Metal cap) and
    current_model_memory, not dynamic_ceiling_bytes or the phys footprint."""
    ceiling = RECORDED_STATUS_080["final_ceiling"]
    assert ceiling > 0
    assert lg._budget_bytes(RECORDED_STATUS_080) == ceiling
    seat = next(m for m in RECORDED_STATUS_080["models"] if m["loaded"])
    assert seat["id"] == RECORDED_SEAT and seat["actual_size"] > 0
    cap = lg._omlx_ollama_load_cap(RECORDED_STATUS_080, seat["actual_size"])
    assert cap is not None
    # 80% of 30.6 GiB less the 2 GiB margin leaves the 15.2 GiB seat 7.27 GiB of
    # room, which a balanced-tier Ollama resident eats at 0.75 bytes per byte.
    assert cap / GIB == pytest.approx(12.116, abs=0.01)


def test_the_reclaim_share_follows_the_engine_memory_tier(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"

    def write(tier: str) -> None:
        settings.write_text(json.dumps({"memory": {"memory_guard_tier": tier}}))

    monkeypatch.delenv("OMLX_OTHER_APP_RECLAIM_RATIO", raising=False)
    monkeypatch.delenv("OMLX_MEMORY_GUARD_TIER", raising=False)
    for tier, ratio in (("safe", 0.0), ("balanced", 0.25), ("aggressive", 0.5), ("custom", 1.0)):
        write(tier)
        assert lg._omlx_reclaim_ratio(settings) == ratio
    monkeypatch.setenv("OMLX_OTHER_APP_RECLAIM_RATIO", "0.5")
    assert lg._omlx_reclaim_ratio(settings) == 0.5


async def test_an_ollama_load_that_would_squeeze_the_loaded_seat_is_refused(caplog):
    """Property 1: 12.5 GiB fits oMLX's raw 13.4 GiB headroom but would leave the
    recorded 15.2 GiB seat below its prefill share, so the load is refused."""
    e = RecordedOmlx(tags={"target": 10 * GIB})
    g = recorded_guard(e)
    g.protect(lg.OMLX, RECORDED_SEAT, failover=True)

    with (
        caplog.at_level(logging.INFO, logger=lg.logger.name),
        pytest.raises(lg.LoadRefusedError) as err,
    ):
        await g.admit(OLLAMA_URL, "target")

    assert "held for the loaded oMLX seat" in str(err.value)
    assert "12.5 GiB" in str(err.value)
    assert any("held so the loaded oMLX seat" in r.getMessage() for r in caplog.records)
    assert e.request_counts.get("/admin/api/models") is None  # the kept seat was never touched


async def test_an_ollama_load_never_squeezes_its_loaded_omlx_copy(caplog):
    """The 2026-11-20 shape: the seat's oMLX copy is not evictable, so the GGUF load
    is refused instead of taking the copy's prefill room."""
    e = Engines(
        tags={"target": 10 * GIB},
        omlx={"omlx-target": {"size": int(16 * GIB), "loaded": True}},
        ceiling=int(30 * GIB),
        omlx_memory=int(16 * GIB),
    )
    g = guard(e, counterpart=lambda engine, _model: {"omlx-target"})

    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "target")

    assert e.unloaded == []
    assert e.omlx["omlx-target"]["loaded"]


async def test_an_idle_ollama_resident_is_evicted_to_restore_the_seat_prefill_room():
    """Property 1's evict half: the idle resident's release lifts the ceiling and the
    loud load is admitted with the loaded seat's share intact."""
    e = Engines(
        tags={"target": 10 * GIB},
        ollama={"idle": 6 * GIB},
        omlx={"seat": {"size": int(16 * GIB), "loaded": True}},
        ceiling=int(30 * GIB),
        omlx_memory=int(16 * GIB),
    )
    e.hidden["idle"] = 6 * GIB
    g = guard(e)
    g.protect(lg.OMLX, "seat", failover=True)
    lg.set_load_wait("5")

    release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert e.unload_calls == {"idle": 1}
    assert e.omlx["seat"]["loaded"]
    release()


async def test_an_omlx_load_is_refused_when_a_pinned_ollama_resident_leaves_no_room():
    """Property 2's refusal half: the resident cannot be evicted, so oMLX's load is
    not admitted into a prefill share the resident has already taken."""
    e = Engines(
        ollama={"router": int(22 * GIB)},
        omlx={"mlx": {"size": int(14 * GIB), "loaded": False}},
        ceiling=int(18 * GIB),
    )
    g = guard(e)

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit_omlx("mlx")

    assert "router (22.0 GiB, pinned)" in str(err.value)
    assert e.unload_calls == {}


async def test_an_idle_ollama_resident_is_evicted_before_an_omlx_load_is_refused():
    """Property 2's evict half: the 24.6 GiB resident the incident left behind is
    unloaded first, and its release lets the seat load."""
    e = Engines(
        ollama={"nemotron": int(24.6 * GIB)},
        omlx={"mlx": {"size": int(14 * GIB), "loaded": False}},
        ceiling=int(19 * GIB),
    )
    e.hidden["nemotron"] = int(24.6 * GIB)
    g = guard(e)
    lg.set_load_wait("5")

    release = await g.admit_omlx("mlx")

    assert release is not None
    assert e.unload_calls == {"nemotron": 1}
    assert "nemotron" not in e.ollama
    release()


async def test_unreadable_omlx_status_fails_open_and_says_so(caplog):
    """Property 3: no oMLX numbers means the previous admission path, logged."""
    e = Engines(tags={"target": 10 * GIB}, omlx_ok=False)
    g = guard(e)

    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert any("oMLX status unreadable" in r.getMessage() for r in caplog.records)
    release()


async def test_an_unknown_reclaim_share_admits_on_the_previous_path_and_says_so(
    caplog, monkeypatch
):
    """Property 3: the ceiling projection needs the engine's reclaim share; without it
    the guard does not invent one."""
    e = Engines(
        tags={"target": 10 * GIB},
        omlx={"seat": {"size": int(16 * GIB), "loaded": True}},
        ceiling=int(34 * GIB),
        omlx_memory=int(16 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "seat", failover=True)
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", None)

    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await g.admit(OLLAMA_URL, "target")

    assert release is not None
    assert any("cannot project oMLX's ceiling" in r.getMessage() for r in caplog.records)
    release()


#: The GGUF whose empty answer was "failover protected" in the 2026-11-20 live log.
NEMOTRON = "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"


def test_a_failed_model_is_the_first_eviction_candidate_not_a_shield():
    """Property 2: the model a hop failed on leads the eviction order and holds nothing back."""
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    g.note_failure(lg.OLLAMA, NEMOTRON)

    assert lg.model_key(NEMOTRON) in g.failed(lg.OLLAMA)
    assert g._ollama_hold_reason(NEMOTRON, include_protected=True) is None
    resident = {"other": 5 * GIB, NEMOTRON: 22 * GIB}
    assert g._unfreed_idle_ollama(resident, set())[0] == NEMOTRON


def test_a_failure_drops_a_failover_shield_the_model_already_had():
    """The live bug's exact shape: a 300 s shield on a model that then failed."""
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    g.protect(lg.OLLAMA, NEMOTRON, failover=True)

    g.note_failure(lg.OLLAMA, NEMOTRON)

    assert g.failover_protected(lg.OLLAMA) == set()


async def test_an_idle_failover_shield_yields_and_the_healthy_seat_loads(caplog):
    """The 2026-11-20 receipt's shape under the 2026-11-26 contract: the 22.9 GiB
    resident was "failover protected" and idle, so it is evicted and the 16.6 GiB
    seat loads instead of being refused for 300 s."""
    e = Engines(
        ollama={NEMOTRON: int(22.9 * GIB)},
        omlx={"Qwen3.8-27B-oQ4e-mtp": {"size": int(16.6 * GIB), "loaded": False}},
        ceiling=int(14 * GIB),
    )
    e.hidden[NEMOTRON] = int(22.9 * GIB)
    g = guard(e)
    g.protect(lg.OLLAMA, NEMOTRON, failover=True)

    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        release = await g.admit_omlx("Qwen3.8-27B-oQ4e-mtp")

    assert release is not None
    assert e.unload_calls == {NEMOTRON: 1}
    assert NEMOTRON not in e.ollama
    release()


async def test_a_failover_shield_that_cannot_buy_the_load_is_kept_and_named():
    """Protection orders eviction but does not have to be spent: a 2 GiB shield cannot
    cover the 7.4 GiB gap, so it stays resident and the refusal still names it."""
    e = Engines(
        ollama={NEMOTRON: int(2 * GIB)},
        omlx={"Qwen3.8-27B-oQ4e-mtp": {"size": int(16.6 * GIB), "loaded": False}},
        ceiling=int(14 * GIB),
    )
    g = guard(e)
    g.protect(lg.OLLAMA, NEMOTRON, failover=True)

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit_omlx("Qwen3.8-27B-oQ4e-mtp")

    assert "(2.0 GiB, failover protected)" in str(err.value)
    assert e.unload_calls == {}
    assert NEMOTRON in e.ollama


async def test_the_model_that_just_failed_is_evicted_and_the_healthy_seat_loads():
    """Property 2's fix: the same 22.9 GiB, now the first eviction candidate, frees the seat."""
    e = Engines(
        ollama={NEMOTRON: int(22.9 * GIB)},
        omlx={"Qwen3.8-27B-oQ4e-mtp": {"size": int(16.6 * GIB), "loaded": False}},
        ceiling=int(14 * GIB),
    )
    e.hidden[NEMOTRON] = int(22.9 * GIB)
    g = guard(e)
    g.protect(lg.OLLAMA, NEMOTRON, failover=True)  # what the old failure path set
    g.note_failure(lg.OLLAMA, NEMOTRON)  # what the failure now does instead

    release = await g.admit_omlx("Qwen3.8-27B-oQ4e-mtp")

    assert release is not None
    assert e.unload_calls == {NEMOTRON: 1}
    release()


#: The 2026-11-26 canary receipt (~02:00Z): the shield had served a failover 300 s
#: earlier and sat idle, and every oMLX seat after the first died on it.
QWEN_GGUF = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k"


async def test_the_logged_sequence_the_shield_does_not_block_the_other_engine():
    """The 2026-11-26 receipt: the idle 17.5 GiB failover shield left oMLX 11.4 GiB
    against the 15.3 GiB QAT seat and refused it; now the shield is evicted and the
    seat loads."""
    e = Engines(
        ollama={QWEN_GGUF: int(17.5 * GIB)},
        omlx={"gemma-4-26b-a4b-it-QAT-4bit": {"size": int(15.3 * GIB), "loaded": False}},
        ceiling=int(16.75 * GIB),  # 0.8 zone - 2 margin = the receipt's 11.4 GiB
    )
    e.hidden[QWEN_GGUF] = int(17.5 * GIB)
    g = guard(e)
    g.protect(lg.OLLAMA, QWEN_GGUF, failover=True)

    release = await g.admit_omlx("gemma-4-26b-a4b-it-QAT-4bit")

    assert release is not None
    assert e.unload_calls == {QWEN_GGUF: 1}
    assert QWEN_GGUF not in e.ollama
    release()


async def test_the_logged_ollama_refusal_now_counts_the_idle_shield():
    """The second receipt line: "oMLX headroom 16.8 + idle Ollama 0.0 - margin 2"
    refused a 14.9 GiB cold load while a 17.5 GiB idle shield sat resident. The
    math now counts it, so the load is admitted without spending the shield."""
    inkling = "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"
    e = Engines(
        tags={inkling: int(14.9 * GIB)},
        ollama={QWEN_GGUF: int(17.5 * GIB)},
        omlx={},
        ceiling=int(10 * GIB),
    )
    g = guard(e)
    g.protect(lg.OLLAMA, QWEN_GGUF, failover=True)

    release = await g.admit(OLLAMA_URL, inkling)

    assert release is not None
    assert e.unload_calls == {}  # the shield was never needed
    assert QWEN_GGUF in e.ollama
    release()


async def test_the_headroom_math_counts_idle_shields_of_both_kinds():
    """Property 2: "idle Ollama 0.0" while a 17.5 GiB idle shield was resident is the
    lie that produced the quiet refusal; idle shields are reclaimable, busy is not."""
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "router")
    resident = {QWEN_GGUF: int(17.5 * GIB), "router": int(6 * GIB)}
    g.protect(lg.OLLAMA, QWEN_GGUF, failover=True)
    g.protect(lg.OLLAMA, "keeper-seat", 300)

    assert g._ollama_reclaimable(resident) == 17.5 * GIB  # the shield, not the pin
    assert g._ollama_idle(resident) == 0.0  # ordinary passes still spare it
    end = g.begin(lg.OLLAMA, QWEN_GGUF)
    assert g._ollama_reclaimable(resident) == 0.0  # in flight is untouchable
    end()


async def test_host_free_bytes_counts_idle_shields_on_both_engines():
    """Property 2's other half: an idle failover-protected oMLX resident is
    reclaimable memory too, on both engines."""
    e = Engines(
        ollama={QWEN_GGUF: int(17.5 * GIB)},
        omlx={"mlx-shield": {"size": 20 * GIB, "loaded": True}},
        ceiling=int(50 * GIB),
        omlx_memory=int(20 * GIB),
    )
    g = guard(e)
    g.protect(lg.OLLAMA, QWEN_GGUF, failover=True)
    g.protect(lg.OMLX, "mlx-shield", failover=True)

    # 30 GiB headroom + 17.5 GiB Ollama shield + 20 GiB oMLX shield
    actual = await _REAL_HOST_FREE_BYTES(g, OLLAMA_URL)
    assert actual is not None
    assert actual == 30 * GIB + int(17.5 * GIB) + 20 * GIB


async def test_the_shield_refusal_message_reports_the_real_idle_bytes():
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    resident = {QWEN_GGUF: int(17.5 * GIB)}
    idle = g._ollama_reclaimable(resident)
    available = g._ollama_available(int(16.8 * GIB), resident, idle) - lg._MARGIN

    err = lg.LoadGuard._ollama_refusal(
        "inkling",
        int(14.9 * GIB),
        available,
        int(16.8 * GIB),
        idle,
        quiet=True,
        waited=0.0,
    )

    assert "(oMLX headroom 16.8 + idle Ollama 17.5 - margin 2)" in str(err)


def test_the_yield_spends_keeper_shields_before_failover_shields():
    """Protection ordering: the keeper's preferred resident yields first; the seat
    that served a failover is the last resident asked to give up its memory."""
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    g.protect(lg.OLLAMA, "keeper", 300)
    g.protect(lg.OLLAMA, "shield", failover=True)
    resident = {"keeper": int(8 * GIB), "shield": int(17.5 * GIB)}

    names = [
        n
        for n in resident
        if g._ollama_hold_reason(n) in ("protected", "failover protected")
        and g._ollama_hold_reason(n, include_protected=True) is None
    ]
    names.sort(key=lambda n: g._ollama_hold_reason(n) != "protected")

    assert names == ["keeper", "shield"]


async def test_an_omlx_cold_load_spends_an_idle_omlx_failover_shield_that_buys_it():
    """The shield on the same engine as the cold load: the ordinary pass spares it,
    and just before the refusal it is the last thing that can buy the admission."""
    e = Engines(
        omlx={
            "shield": {"size": 20 * GIB, "loaded": True},
            "mlx": {"size": 14 * GIB, "loaded": False},
        },
        ceiling=int(22 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "shield", failover=True)

    release = await g.admit_omlx("mlx")

    assert release is not None
    assert e.unloaded == ["shield"]
    assert not e.omlx["shield"]["loaded"]
    release()


async def test_an_omlx_cold_load_keeps_an_omlx_failover_shield_that_cannot_buy_it():
    """A 1 GiB shield cannot cover the 2.8 GiB gap: it stays, and the refusal names
    it "failover protected" — protection was never spent for nothing."""
    e = Engines(
        omlx={
            "shield": {"size": 1 * GIB, "loaded": True},
            "mlx": {"size": 16 * GIB, "loaded": False},
        },
        ceiling=int(20 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "shield", failover=True)

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit_omlx("mlx")

    assert e.unloaded == []
    assert e.omlx["shield"]["loaded"]
    assert "(1.0 GiB, failover protected)" in str(err.value)


async def test_an_omlx_cold_load_frees_idle_residents_before_any_shield():
    """Ordering: ordinary idle memory goes first; the shield only yields when
    nothing else covers the shortage."""
    e = Engines(
        omlx={
            "idle": {"size": 16 * GIB, "loaded": True, "last": 1},
            "shield": {"size": 20 * GIB, "loaded": True, "last": 2},
            "mlx": {"size": 14 * GIB, "loaded": False},
        },
        ceiling=int(40 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "shield", failover=True)

    release = await g.admit_omlx("mlx")

    assert release is not None
    assert e.unloaded == ["idle"]  # the shield was never needed
    assert e.omlx["shield"]["loaded"]
    release()


async def test_a_busy_failover_shield_is_untouchable():
    """Only in-flight work is untouchable, and it stays untouchable under shields:
    a busy shield is never yielded and the refusal names it busy."""
    e = Engines(
        ollama={QWEN_GGUF: int(3 * GIB)},
        omlx={"gemma-4-26b-a4b-it-QAT-4bit": {"size": int(15.3 * GIB), "loaded": False}},
        ceiling=int(16.75 * GIB),
    )
    g = guard(e)
    g.protect(lg.OLLAMA, QWEN_GGUF, failover=True)
    end = g.begin(lg.OLLAMA, QWEN_GGUF)

    with pytest.raises(lg.LoadRefusedError) as err:
        await g.admit_omlx("gemma-4-26b-a4b-it-QAT-4bit")

    end()
    assert e.unload_calls == {}
    assert QWEN_GGUF in e.ollama
    assert "(3.0 GiB, busy)" in str(err.value)
