"""validate_system HQ: the serving conformance gate (scripts/validation/wfe.py)."""

from __future__ import annotations

import urllib.request

from scripts.validation import wfe
from tests.wfe import settings_audit


def _reachable(monkeypatch):
    class _Resp:
        def read(self):
            return b"{}"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(settings_audit, "installed_tags", lambda _b: {"a:tag"})


def test_skips_without_a_live_ollama(monkeypatch):
    def down(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    status, _msg, subs = wfe.check_serving_conformance()
    assert status == "SKIP" and subs == []


def test_a_warning_fails_the_check(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(
        settings_audit,
        "run_audit",
        lambda: {
            "checked_workspaces": 1,
            "violations": [
                {
                    "workspace": "auto-math",
                    "kind": "reasoning_uncontrolled",
                    "detail": "x",
                    "severity": "WARN",
                }
            ],
        },
    )
    monkeypatch.setattr(
        settings_audit, "audit_tags", lambda t: {"checked_tags": 1, "violations": []}
    )
    status, _msg, subs = wfe.check_serving_conformance()
    assert status == "FAIL" and subs[0]["name"] == "auto-math: reasoning_uncontrolled"


def test_info_only_passes(monkeypatch):
    _reachable(monkeypatch)
    info = {"workspace": "w", "kind": "omlx_settings_no_entry", "detail": "x", "severity": "INFO"}
    monkeypatch.setattr(
        settings_audit, "run_audit", lambda: {"checked_workspaces": 1, "violations": [info]}
    )
    monkeypatch.setattr(
        settings_audit, "audit_tags", lambda t: {"checked_tags": 1, "violations": []}
    )
    status, _msg, _subs = wfe.check_serving_conformance()
    assert status == "PASS"
