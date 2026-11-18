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


def test_build_carries_the_provenance_args(monkeypatch):
    # 2026-10-18: without them every image reported build_sha "unknown" and the WFE harness
    # could not confirm the deployed build
    calls: list = []
    _patch(monkeypatch, calls)
    assert wr.main([]) == 0
    build = next(" ".join(c) for c in calls if "build" in c and "--no-cache" in c)
    assert "PORTAL_BUILD_SHA=" in build and "PORTAL_BUILD_DIRTY=" in build
