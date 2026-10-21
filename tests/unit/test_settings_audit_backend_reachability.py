"""An unreadable oMLX is one `backend_unreachable` row, not N absent models."""

from __future__ import annotations

import json
import urllib.error

import pytest
import yaml

from tests.wfe import settings_audit as audit

REAP = "Qwen3.8-Flash-Next-REAP-288-MLX-4bit"
DFLASH = "Qwen3.8-27B-4bit"


def _backends() -> dict:
    return {
        "backends": [
            {"type": "ollama", "group": "coding", "models": [{"id": "llama3:8b"}]},
            {"type": "omlx", "group": "coding", "models": [{"id": REAP}, {"id": DFLASH}]},
        ]
    }


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def test_an_unreadable_omlx_is_one_row_naming_the_backend() -> None:
    violations: list[dict] = []
    unverifiable = audit._note_omlx_reachability(
        _backends(), "HTTPError: HTTP Error 401: Unauthorized", violations
    )
    assert unverifiable == {REAP, DFLASH}
    assert [(v["workspace"], v["kind"], v["severity"]) for v in violations] == [
        ("backend:omlx", "backend_unreachable", "FAIL")
    ]
    assert audit.OMLX in violations[0]["detail"]
    assert "401" in violations[0]["detail"]


def test_a_reachable_omlx_reports_nothing() -> None:
    violations: list[dict] = []
    assert audit._note_omlx_reachability(_backends(), None, violations) == set()
    assert violations == []


def test_inventory_reports_why_it_could_not_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*_a: object, **_k: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(audit.urllib.request, "urlopen", down)
    ids, reason = audit.omlx_inventory()
    assert ids == set()
    assert reason is not None and reason.startswith("URLError")


def test_inventory_lists_the_served_ids_when_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audit.urllib.request,
        "urlopen",
        lambda *_a, **_k: _Resp({"data": [{"id": REAP}, {"id": DFLASH}]}),
    )
    ids, reason = audit.omlx_inventory()
    assert ids == {REAP, DFLASH} and reason is None


def test_an_omlx_only_hint_is_not_absent_when_omlx_is_unreadable() -> None:
    violations: list[dict] = []
    audit._audit_workspace(
        "auto-coding::reap288",
        {"model_hint": REAP, "module": "coding"},
        set(),
        {REAP},
        {},
        violations,
        omlx=True,
        unverifiable={REAP},
    )
    assert violations == []


def test_a_reachable_backends_absence_still_fails() -> None:
    violations: list[dict] = []
    audit._audit_workspace(
        "auto-coding::reap288",
        {"model_hint": REAP, "module": "coding"},
        set(),
        {REAP},
        {},
        violations,
        omlx=True,
    )
    assert [(v["kind"], v["severity"]) for v in violations] == [("hint_absent", "FAIL")]


def test_a_model_no_backend_claims_is_still_absent_while_omlx_is_unreadable() -> None:
    violations: list[dict] = []
    audit._audit_workspace(
        "auto-general",
        {"model_hint": "gone:Q4", "module": "general"},
        set(),
        {"gone:Q4"},
        {},
        violations,
        unverifiable={REAP, DFLASH},
    )
    assert [(v["kind"], v["severity"]) for v in violations] == [("hint_absent", "FAIL")]


def test_persona_pins_on_an_unreadable_omlx_are_not_reported_absent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    personas = tmp_path / "config" / "personas"
    (personas / "bench").mkdir(parents=True)
    (personas / "qwen38coder_dflash.yaml").write_text(
        f"slug: qwen38coder-dflash\nmodel_pin: {DFLASH}\n"
    )
    (personas / "gone.yaml").write_text("slug: gone\nmodel_pin: absent:latest\n")
    monkeypatch.setattr(audit, "REPO", tmp_path)

    violations: list[dict] = []
    checked = audit._audit_personas(set(), violations, {REAP, DFLASH})
    assert checked == 2
    assert [(v["workspace"], v["kind"]) for v in violations] == [
        ("persona:gone", "persona_pin_absent")
    ]


ABSENT_KINDS = ("hint_absent", "pin_absent", "persona_pin_absent")


def _absent_omlx_models(report: dict, models: set[str]) -> set[str]:
    return {
        m
        for m in models
        for v in report["violations"]
        if v["kind"] in ABSENT_KINDS and m in v["detail"]
    }


def _offline(monkeypatch: pytest.MonkeyPatch, reason: str | None) -> None:
    def fake_post(path: str, _payload: dict, timeout: int = 60) -> dict:
        return {"models": []} if path == "/api/tags" else {}

    monkeypatch.setattr(audit, "_post", fake_post)
    monkeypatch.setattr(audit, "omlx_inventory", lambda: (set(), reason))
    monkeypatch.setattr(audit, "_audit_omlx_template", lambda *_a, **_k: None)


def test_run_audit_reports_one_row_where_the_seats_would_read_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = audit._omlx_model_ids(
        yaml.safe_load((audit.REPO / "config/backends.yaml").read_text())
    )
    assert models

    # Control: an oMLX that answers with no models is the pre-fix reading.
    _offline(monkeypatch, None)
    pre = _absent_omlx_models(audit.run_audit(), models)

    _offline(monkeypatch, "HTTPError: HTTP Error 401: Unauthorized")
    report = audit.run_audit()
    post = _absent_omlx_models(report, models)
    assert post == set() and pre - post
    assert [v["kind"] for v in report["violations"]].count("backend_unreachable") == 1
