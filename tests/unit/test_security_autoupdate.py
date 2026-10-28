"""Unit tests for scripts/security_autoupdate.py planning logic (no network, no docker)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
import scripts.check_updates as cu  # noqa: E402

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


OLD = ("python_full_version < '3.11' and sys_platform != 'darwin'",)
NEW = ("python_full_version >= '3.11' and sys_platform != 'darwin'",)


def test_plan_floors_a_fork_that_can_reach_the_fix(monkeypatch):
    monkeypatch.setattr(cu, "_pypi_requires_python", lambda n, v: ">=3.9")
    floors, unreachable = sa._plan({("pillow", "12.3.0", OLD): "13.0.0"})
    assert floors == {"pillow": "13.0.0"} and unreachable == {}


def test_plan_records_a_fork_that_cannot_reach_the_fix(monkeypatch):
    monkeypatch.setattr(cu, "_pypi_requires_python", lambda n, v: ">=3.11")
    floors, unreachable = sa._plan(
        {("pillow", "12.3.0", OLD): "13.0.0", ("filelock", "4.1.0", OLD): "4.2.1"}
    )
    assert floors == {}
    assert set(unreachable) == {("pillow", "12.3.0", OLD), ("filelock", "4.1.0", OLD)}


def test_plan_floors_an_unforked_package_without_a_pypi_lookup(monkeypatch):
    def boom(name, version):
        raise AssertionError("unforked packages must not trigger a PyPI lookup")

    monkeypatch.setattr(cu, "_pypi_requires_python", boom)
    floors, unreachable = sa._plan({("a", "1.0", ()): "1.1"})
    assert floors == {"a": "1.1"} and unreachable == {}


def test_stranded_records_a_fork_that_cannot_reach_the_fix():
    after = {
        ("pillow", "12.3.0", OLD): "13.0.0",
        ("pillow", "13.0.0", NEW): "13.0.0",
        ("filelock", "4.2.4", NEW): "4.2.4",
    }
    stranded = sa._stranded(after, {"pillow": "13.0.0", "filelock": "4.2.4"})
    assert stranded == {("pillow", "12.3.0", OLD): "13.0.0"}
    # left = 3 fixable forks - 1 stranded -> below the 3 counted before the fix
    assert len(after) - len(stranded) == 2


def test_deps_body_records_stranded_forks_and_the_skip(monkeypatch):
    body = sa._deps_body(
        {"pillow": "13.0.0"},
        ["filelock"],
        {("pillow", "12.3.0", OLD): "13.0.0"},
    )
    assert "- pillow >= 13.0.0" in body
    assert "Not resolvable alongside the rest: filelock" in body
    assert "pillow 12.3.0 (py3.10) needs 13.0.0" in body
    assert "SKIP=pytest-unit" in body


def test_commit_skips_only_the_named_hooks(monkeypatch):
    seen = []

    def fake_sh(cmd, cwd=None, timeout=900, env=None):
        seen.append((cmd, env))

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(sa, "_sh", fake_sh)
    assert sa._commit("msg", Path("uv.lock"), skip=("pytest-unit",))
    assert seen[-1][1] == {"SKIP": "pytest-unit"}
    assert seen[-1][0][:3] == ["git", "commit", "-m"]
    seen.clear()
    assert sa._commit("msg", Path("deploy/docker-compose.yml"))
    assert seen[-1][1] is None
