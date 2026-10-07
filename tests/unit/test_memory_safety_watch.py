from __future__ import annotations

import os

from scripts import memory_safety_watch
from scripts.memory_safety_watch import _read_pids, _trip


def test_watch_trips_on_critical_pressure_or_low_swap_with_low_memory():
    assert _trip({"pressure_critical": True, "pressure_level": 4}, 1024, 20).startswith(
        "memory pressure is critical"
    )
    assert _trip(
        {"swap_free_mb": 791.3, "memory_free_pct": 12, "pressure_critical": False}, 1024, 20
    ) == ("swap free 791.3 MiB is below 1024 MiB and memory free 12% is below 20%")


def test_watch_ignores_low_swap_while_memory_is_plentiful():
    # The 2026-10-07 W2 false trip: macOS grows swap in 1 GiB files on demand,
    # so low free swap with 87% free memory is not a hazard.
    assert (
        _trip({"swap_free_mb": 791.3, "memory_free_pct": 87, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert (
        _trip({"swap_free_mb": 2048, "memory_free_pct": 10, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert _trip({"swap_free_mb": None, "memory_free_pct": None}, 1024, 20) is None


def test_watch_pid_file_ignores_invalid_and_own_pid(tmp_path):
    path = tmp_path / "pids"
    path.write_text(f"{os.getpid()}\nnot-a-pid\n42\n42\n1\n")

    assert _read_pids(path) == [42]


def test_omlx_emergency_unload_authenticates_status_and_unloads_idle_models(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {
            "OMLX_URL": "http://omlx.test:8085",
            "OMLX_API_KEY": "test-key",
        }.get(name, default),
    )

    def fake_request(url, payload=None, *, opener=None, headers=None):
        calls.append((url, payload, headers))
        if url.endswith("/api/status"):
            return {"active_requests": 0, "waiting_requests": 0}
        if url.endswith("/admin/api/models"):
            return {"models": [{"id": "idle/model", "loaded": True, "pinned": False}]}
        return {}

    monkeypatch.setattr(memory_safety_watch, "_request_json", fake_request)
    log = tmp_path / "watch.log"

    memory_safety_watch._unload_omlx(log)

    assert calls[0][0].endswith("/admin/api/login")
    assert calls[1][0].endswith("/api/status")
    assert calls[1][2] == {"Authorization": "Bearer test-key"}
    assert calls[2][0].endswith("/admin/api/models")
    assert calls[3][0].endswith("/admin/api/models/idle%2Fmodel/unload")
    assert "idle oMLX unload" in log.read_text()


def test_ollama_base_rewrites_docker_host_for_the_host_watchdog(monkeypatch):
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {"OLLAMA_URL": "http://host.docker.internal:11434/"}.get(
            name, default
        ),
    )
    assert memory_safety_watch._ollama_base() == "http://localhost:11434"


def test_omlx_unload_continues_past_a_model_already_evicted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {"OMLX_API_KEY": "k"}.get(name, default),
    )
    unloaded = []

    def fake_request(url, payload=None, *, opener=None, headers=None):
        if url.endswith("/api/status"):
            return {"active_requests": 0}
        if url.endswith("/admin/api/models"):
            return {"models": [{"id": "gone", "loaded": True}, {"id": "idle", "loaded": True}]}
        if url.endswith("/gone/unload"):
            raise OSError("400 Model not loaded")
        if url.endswith("/unload"):
            unloaded.append(url)
        return {}

    monkeypatch.setattr(memory_safety_watch, "_request_json", fake_request)
    log = tmp_path / "watch.log"
    memory_safety_watch._unload_omlx(log)

    assert unloaded and unloaded[0].endswith("/idle/unload")
    assert "oMLX unload failed model=gone" in log.read_text()
