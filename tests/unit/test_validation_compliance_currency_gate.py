"""GS gate: a stale compliance corpus warns while the module is pre-service and
fails once it is in service. The detection itself lives in
`_compliance_corpus_currency`; this pins only the IN_SERVICE downgrade."""

from __future__ import annotations

from scripts.validation import compliance_acceptance, compliance_currency


def _stale(monkeypatch):
    monkeypatch.setattr(
        compliance_currency,
        "_compliance_corpus_currency",
        lambda: ("FAIL", "nerc_corpus is STALE", [{"retrieval_projection": "STALE"}]),
    )


def test_stale_corpus_warns_while_pre_service(monkeypatch):
    _stale(monkeypatch)
    monkeypatch.setattr(compliance_acceptance, "IN_SERVICE", False)
    status, detail, findings = compliance_currency.check_compliance_corpus_currency()
    assert status == "WARN"
    assert "IN_SERVICE" in detail and "nerc_corpus is STALE" in detail
    assert findings == [{"retrieval_projection": "STALE"}]


def test_stale_corpus_fails_once_in_service(monkeypatch):
    _stale(monkeypatch)
    monkeypatch.setattr(compliance_acceptance, "IN_SERVICE", True)
    status, detail, _ = compliance_currency.check_compliance_corpus_currency()
    assert (status, detail) == ("FAIL", "nerc_corpus is STALE")


def test_pass_is_untouched(monkeypatch):
    monkeypatch.setattr(
        compliance_currency, "_compliance_corpus_currency", lambda: ("PASS", "", [])
    )
    monkeypatch.setattr(compliance_acceptance, "IN_SERVICE", False)
    assert compliance_currency.check_compliance_corpus_currency() == ("PASS", "", [])
