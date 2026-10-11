"""Unit tests for scripts/check_updates.py check_python_deps direction-awareness
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 D2).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_updates", Path(__file__).resolve().parents[2] / "scripts" / "check_updates.py"
)
cu = importlib.util.module_from_spec(_SPEC)
sys.modules["check_updates"] = cu
_SPEC.loader.exec_module(cu)


class _R:
    def __init__(self, rc, out):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def _run_with(monkeypatch, result):
    monkeypatch.setattr(cu.subprocess, "run", lambda *a, **k: result)
    # skip the PyPI leg
    monkeypatch.setattr(Path, "read_text", lambda self: "")
    return cu.check_python_deps()


def test_venv_ahead_warns_against_uv_sync(monkeypatch):
    rep = _run_with(monkeypatch, _R(1, "- mlx==0.32.2\n~ torch==2.13.0 -> 2.11.0\n"))
    blob = "\n".join(rep.lines)
    assert "AHEAD" in blob and "Do NOT run" in blob
    assert rep.actionable


def test_venv_behind_recommends_uv_sync(monkeypatch):
    rep = _run_with(monkeypatch, _R(1, "+ somepkg==1.2.3\n"))
    blob = "\n".join(rep.lines)
    assert "behind uv.lock" in blob and "will catch it up" in blob


def test_check_run_failure_is_not_healthy(monkeypatch):
    def boom(*a, **k):
        raise subprocess.SubprocessError("uv not found")

    monkeypatch.setattr(cu.subprocess, "run", boom)
    monkeypatch.setattr(Path, "read_text", lambda self: "")
    rep = cu.check_python_deps()
    assert rep.status == "error"
    assert rep.actionable


def test_locked_packages_skips_non_pypi(monkeypatch, tmp_path):
    lock = (
        '[[package]]\nname = "a"\nversion = "1.0"\nsource = { registry = "https://pypi.org/simple" }\n\n'
        '[[package]]\nname = "portal"\nversion = "9"\nsource = { editable = "." }\n'
    )
    (tmp_path / "uv.lock").write_text(lock)
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    assert cu._locked_packages() == [("a", "1.0")]


def test_python_vulns_flags_only_fixable_as_actionable(monkeypatch):
    monkeypatch.setattr(cu, "_locked_packages", lambda: [("a", "1.0"), ("b", "2.0")])
    monkeypatch.setattr(
        cu,
        "_post_json",
        lambda url, body: {"results": [{"vulns": [{"id": "GHSA-1"}]}, {}]},
    )
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v="0": ("HIGH", "1.1", "bad"))
    rep = cu.check_python_vulns()
    assert rep.status == "behind" and rep.security and not rep.security_in_gap
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v="0": ("LOW", "", "bad"))
    assert cu.check_python_vulns().status == "current"


def test_python_vulns_osv_failure_is_error(monkeypatch):
    monkeypatch.setattr(cu, "_locked_packages", lambda: [("a", "1.0")])

    def boom(url, body):
        raise OSError("down")

    monkeypatch.setattr(cu, "_post_json", boom)
    assert cu.check_python_vulns().status == "error"


def test_vuln_fixes_takes_highest_per_vuln_lowest_fix(monkeypatch):
    fixed = {"A": ("LOW", "1.2", "a"), "B": ("HIGH", "1.5", "b"), "C": ("HIGH", "", "c")}
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v: fixed[i])
    out = cu.vuln_fixes({("pkg", "1.0"): ["A", "B", "C"]})
    assert out[("pkg", "1.0")][:2] == ("HIGH", "1.5")
