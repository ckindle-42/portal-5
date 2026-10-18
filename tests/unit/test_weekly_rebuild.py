"""Unit tests for scripts/weekly_rebuild.py sequencing (no docker, no launch.sh)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
_SPEC = importlib.util.spec_from_file_location(
    "weekly_rebuild", _ROOT / "scripts" / "weekly_rebuild.py"
)
wr = importlib.util.module_from_spec(_SPEC)
sys.modules["weekly_rebuild"] = wr
_SPEC.loader.exec_module(wr)


def _fake_run(calls, fail_on=None):
    def run(cmd, timeout, input_=None):
        calls.append(cmd)
        rc = 1 if fail_on and fail_on in cmd else 0
        return subprocess.CompletedProcess(cmd, rc, "", "")

    return run


def _patch(monkeypatch, calls, fail_on=None):
    monkeypatch.setattr(wr, "busy", lambda: None)
    monkeypatch.setattr(wr, "_pushover", lambda *a, **k: None)
    monkeypatch.setattr(wr, "_run", _fake_run(calls, fail_on))
    monkeypatch.setattr(wr, "_pipeline_healthy", lambda: True)
    monkeypatch.setattr(wr, "_sandbox_images", lambda: True)
    monkeypatch.setattr(wr, "owui_update", lambda: (True, "open-webui: current"))
    monkeypatch.setattr(wr, "_pull_services", lambda: ["searxng", "portal-pipeline"])


def test_failed_build_never_takes_the_stack_down(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls, fail_on="build")
    assert wr.main([]) == 1
    assert not any("down" in c for c in calls)


def test_failed_pull_never_takes_the_stack_down(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls, fail_on="pull")
    assert wr.main([]) == 1
    assert not any("down" in c for c in calls)


def test_happy_path_builds_fresh_then_down_then_up(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    assert wr.main([]) == 0
    flat = [" ".join(c) for c in calls]
    build = next(i for i, c in enumerate(flat) if " build " in c)
    down = next(i for i, c in enumerate(flat) if c.endswith("launch.sh down"))
    up = next(i for i, c in enumerate(flat) if c.endswith("launch.sh up"))
    assert "--pull" in flat[build] and "--no-cache" in flat[build]
    assert build < down < up


def test_build_carries_the_provenance_args(monkeypatch):
    # 2026-10-18: without them every image reported build_sha "unknown" and the WFE harness
    # could not confirm the deployed build
    calls: list = []
    _patch(monkeypatch, calls)
    assert wr.main([]) == 0
    build = next(" ".join(c) for c in calls if "build" in c and "--no-cache" in c)
    assert "PORTAL_BUILD_SHA=" in build and "PORTAL_BUILD_DIRTY=" in build


def test_defers_while_a_sweep_runs(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    monkeypatch.setattr(wr, "busy", lambda: "bench_tps.py")
    assert wr.main([]) == 0
    assert calls == []


def test_unhealthy_up_keeps_previous_images_for_rollback(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls, fail_on="up")
    assert wr.main([]) == 1
    assert not any("prune" in c for c in calls)


def test_healthy_up_prunes_dangling_images(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    assert wr.main([]) == 0
    assert any("prune" in c for c in calls)


def test_bulk_pull_never_includes_open_webui(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    assert wr.main([]) == 0
    pull = next(c for c in calls if "pull" in c and "--ignore-buildable" in c)
    assert "open-webui" not in pull


def test_pull_services_failure_never_falls_back_to_pulling_everything(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    monkeypatch.setattr(wr, "_pull_services", lambda: [])
    assert wr.main([]) == 1
    assert not any("pull" in c for c in calls)


def test_rolled_back_open_webui_update_is_reported_as_a_problem(monkeypatch):
    calls: list = []
    _patch(monkeypatch, calls)
    monkeypatch.setattr(wr, "owui_update", lambda: (False, "open-webui: rolled back"))
    assert wr.main([]) == 1
