"""scripts/omlx_memory_tier.py — settings edit only; no oMLX, no network."""

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "omlx_memory_tier", Path(__file__).resolve().parents[2] / "scripts" / "omlx_memory_tier.py"
)
tier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tier)


def _settings(tmp_path, value):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"memory": {"memory_guard_tier": value, "soft_threshold": 0.85}}))
    return p


def test_set_tier_changes_only_the_tier(tmp_path):
    p = _settings(tmp_path, "balanced")
    assert tier.set_tier("aggressive", p) is True
    assert json.loads(p.read_text())["memory"] == {
        "memory_guard_tier": "aggressive",
        "soft_threshold": 0.85,
    }


def test_set_tier_is_a_noop_when_already_set(tmp_path):
    p = _settings(tmp_path, "balanced")
    assert tier.set_tier("balanced", p) is False


def test_set_tier_rejects_unknown_tier(tmp_path):
    with pytest.raises(ValueError):
        tier.set_tier("reckless", _settings(tmp_path, "balanced"))
