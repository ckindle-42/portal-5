"""Unit tests for scripts/security_autoupdate.py planning logic (no network, no docker)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
_SPEC = importlib.util.spec_from_file_location(
    "security_autoupdate", _ROOT / "scripts" / "security_autoupdate.py"
)
sa = importlib.util.module_from_spec(_SPEC)
sys.modules["security_autoupdate"] = sa
_SPEC.loader.exec_module(sa)

COMPOSE = """
  grafana:
    image: grafana/grafana:10.4.2
  searx:
    image: searxng/searxng:latest
  wm:
    image: wazuh/wazuh-manager:4.9.2
  wi:
    image: wazuh/wazuh-indexer:4.9.2
"""


def test_pin_plan_bumps_patch_only_and_skips_floating(monkeypatch):
    monkeypatch.setattr(
        sa, "_hub_patches", lambda repo, tag: ["10.4.5", "10.4.19"] if "grafana" in repo else []
    )
    refs, plan = sa._pin_plan(COMPOSE)
    assert plan == {"grafana/grafana": "10.4.19"}
    assert "searxng/searxng" not in refs


def test_pin_plan_wazuh_is_all_or_nothing(monkeypatch):
    monkeypatch.setattr(
        sa, "_hub_patches", lambda repo, tag: ["4.9.3"] if repo.endswith("manager") else []
    )
    _, plan = sa._pin_plan(COMPOSE)
    assert plan == {}


def test_resolve_falls_back_to_floors_then_per_package(tmp_path, monkeypatch):
    (tmp_path / "uv.lock").write_text("orig")
    calls = []

    def fake_lock(work, floors, op):
        calls.append((dict(floors), op))
        return op == ">=" and "bad" not in floors

    monkeypatch.setattr(sa, "_lock_with", fake_lock)
    applied = sa._resolve(tmp_path, {"a": "1", "bad": "2"})
    assert applied == {"a": "1"}
    assert calls[0][1] == "==" and calls[1][1] == ">="
