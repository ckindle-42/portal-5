"""T2 P3.4 (O6) — `contextualize` must never be enabled on a security-readable KB.

Seeded-violation test in the style of the Bully's gate GP: the gate FAILs when a
KB whose id names a discovery / corroboration path carries `contextualize: true`
in its stamped stage set, and PASSes otherwise. The risk it guards: heading text
carries technique names and scenario family, and the Bully's grading wall
requires lineage never reach the cousin engine.
"""

from __future__ import annotations

import pytest

from scripts.validation.rag_runtime import _SECURITY_KB_RE, check_contextualize_not_on_security_kb


@pytest.mark.parametrize(
    "kb_id,is_security",
    [
        ("bully_corpus", True),
        ("security-detections", True),
        ("mitre_attack", True),
        ("htb_writeups", True),
        ("purpleteam_scenario_v3", True),
        ("compliance_nerc_cip", False),
        ("ot_policies", False),
        ("research_papers", False),
        ("ragEval", False),
    ],
)
def test_security_kb_pattern(kb_id, is_security):
    assert bool(_SECURITY_KB_RE.search(kb_id)) is is_security


def _fake_store(monkeypatch, kbs: dict[str, dict]):
    from portal.platform import lance_guard
    from portal.platform.retrieval import store

    monkeypatch.setattr(lance_guard, "require_lance_dir", lambda *a, **k: None)
    monkeypatch.setattr(store, "list_kbs", lambda *a, **k: list(kbs))
    monkeypatch.setattr(store, "read_stamp", lambda kb: kbs[kb])


def test_gate_fails_on_a_seeded_violation(monkeypatch):
    _fake_store(
        monkeypatch,
        {
            "compliance_kb": {"stage_set": {"contextualize": False}},
            "bully_corpus": {"stage_set": {"contextualize": True}},  # the plant
        },
    )
    status, detail, subs = check_contextualize_not_on_security_kb()
    assert status == "FAIL"
    assert any(s["name"] == "bully_corpus" for s in subs)


def test_gate_passes_when_contextualize_is_only_on_non_security_kbs(monkeypatch):
    _fake_store(
        monkeypatch,
        {
            "compliance_kb": {"stage_set": {"contextualize": True}},
            "ot_policies": {"stage_set": {"contextualize": True}},
            "bully_corpus": {"stage_set": {"contextualize": False}},
        },
    )
    status, _detail, _subs = check_contextualize_not_on_security_kb()
    assert status == "PASS"
