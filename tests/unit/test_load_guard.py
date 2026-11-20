"""Host-memory admission across Ollama and oMLX (portal/platform/inference/load_guard.py)."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from portal.platform.inference import load_guard as lg
from portal.platform.inference.cluster_backends import Backend
from portal.platform.inference.load_guard import OLLAMA
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
    monkeypatch.delenv("LOAD_GUARD", raising=False)
    monkeypatch.delenv("OMLX_PREFILL_SAFE_ZONE_RATIO", raising=False)
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


async def test_ollama_load_does_not_evict_a_model_in_its_failover_window():
    e = Engines(
        tags={"target": int(20.48 * GIB)},
        omlx={"failover-source": {"size": 25 * GIB, "loaded": True}},
        ceiling=int(48.2 * GIB),
    )
    g = guard(e)
    g.protect(lg.OMLX, "failover-source", failover=True)

    with pytest.raises(lg.LoadRefusedError):
        await g.admit(OLLAMA_URL, "target")

    assert e.unloaded == []
    assert e.omlx["failover-source"]["loaded"]


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
