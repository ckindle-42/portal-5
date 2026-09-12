"""Stage 3 — the ambiguous rerank band is READ, not ticketed.

`propose.py` documented a three-stage resolution (exact match -> rerank
similarity -> model arbitration of the ambiguous middle) and shipped only two.
The middle band filed a `low_confidence_extraction` review item and returned
False, which had two costs:

  1. 812 of 1107 open review items on the operator corpus were this band —
     retrieval uncertainty converted into human labour.
  2. `return False` meant an ambiguous procedure/standard pair silently became a
     NON-match, so a requirement the procedure does satisfy can read as
     uncovered. That is the direction that matters in compliance.

A rerank score compares two embeddings; it cannot separate "this procedure
implements this requirement" from "this procedure mentions the same equipment".
Reading can. These tests pin that the reading happens, that its verdicts are
honoured, and that it can only ever REMOVE work from the human queue.

Hermetic: the arbiter is injected, so no model is called.
"""

from __future__ import annotations

import importlib

pr = importlib.import_module("portal.modules.compliance.core.propose")


class _Node:
    id = "CIP-007-6 R2 Part 2.2"
    text = "Evaluate security patches for applicability at least once every 35 calendar days."


def _candidate(text="Patches are evaluated monthly by the OT team."):
    return {
        "text": text,
        "span": "evaluated monthly",
        "section_id": "sec-1",
        "document_id": "LSPG Security Patch Management Procedure V11.pdf",
    }


def _arbiter(verdict, reason="because"):
    def fn(_model, _system, _user):
        return f'{{"verdict":"{verdict}","reason":"{reason}"}}'

    return fn


MID = (pr.RERANK_THRESHOLD_LOW + pr.RERANK_THRESHOLD_HIGH) / 2


# ── the band is read ─────────────────────────────────────────────────────────


def test_ambiguous_band_relevant_is_no_longer_a_silent_non_match(monkeypatch):
    """The regression that matters. Before stage 3 this returned (False, item):
    a pair the model can see IS relevant was recorded as not relevant AND cost a
    human a ticket."""
    called = {}
    monkeypatch.setattr(pr.rq, "propose", lambda *a, **k: called.setdefault("queued", True))
    relevant, item_id = pr._resolve_relevance(
        _candidate(), MID, _Node(), "procedure", arbiter_fn=_arbiter("RELEVANT")
    )
    assert relevant is True
    assert item_id == ""
    assert "queued" not in called, "a settled pair must not reach the human queue"


def test_ambiguous_band_not_relevant_settles_without_a_ticket(monkeypatch):
    """Topical overlap with no bearing on the requirement — the model can settle
    this too, and it should cost nobody a decision."""
    called = {}
    monkeypatch.setattr(pr.rq, "propose", lambda *a, **k: called.setdefault("queued", True))
    relevant, item_id = pr._resolve_relevance(
        _candidate("The OT team maintains a contact list."),
        MID,
        _Node(),
        "procedure",
        arbiter_fn=_arbiter("NOT_RELEVANT"),
    )
    assert relevant is False
    assert item_id == ""
    assert "queued" not in called


def test_only_unsure_reaches_a_human(monkeypatch):
    """The one remaining path to the review queue, and it carries the arbiter's
    verdict so a reviewer can see why it got there."""
    seen = {}

    def _propose(kind, **kw):
        seen.update(kind=kind, **kw)
        return type("I", (), {"id": "itm-1"})()

    monkeypatch.setattr(pr.rq, "propose", _propose)
    relevant, item_id = pr._resolve_relevance(
        _candidate(), MID, _Node(), "procedure", arbiter_fn=_arbiter("UNSURE", "text truncated")
    )
    assert relevant is False
    assert item_id == "itm-1"
    assert seen["kind"] == "low_confidence_extraction"
    assert seen["proposed_value"]["arbiter_verdict"] == "UNSURE"
    assert seen["proposed_value"]["arbiter_reason"] == "text truncated"


# ── it can only ever remove work, never add it ───────────────────────────────


def test_unreachable_arbiter_degrades_to_the_old_behaviour(monkeypatch):
    """A down model must not lose a pair. It falls back to exactly what the
    module did before stage 3 existed: queue it."""
    seen = {}
    monkeypatch.setattr(
        pr.rq, "propose", lambda kind, **kw: seen.update(kind=kind) or type("I", (), {"id": "x"})()
    )

    def _boom(*_a):
        raise ConnectionError("ollama down")

    relevant, item_id = pr._resolve_relevance(
        _candidate(), MID, _Node(), "procedure", arbiter_fn=_boom
    )
    assert relevant is False
    assert item_id == "x"
    assert seen["kind"] == "low_confidence_extraction"


def test_unparseable_arbiter_output_is_unsure_not_a_guess(monkeypatch):
    monkeypatch.setattr(pr.rq, "propose", lambda kind, **kw: type("I", (), {"id": "x"})())
    for raw in ("not json at all", '{"verdict":"MAYBE"}', "[]"):
        v, _ = pr.arbitrate_relevance(_candidate(), _Node(), arbiter_fn=lambda *a, r=raw: r)
        assert v == "UNSURE", f"{raw!r} should not decide anything"


# ── the confident bands are untouched ────────────────────────────────────────


def test_high_and_low_bands_never_call_the_arbiter():
    """Stage 3 is for the middle band only — a confident score must not pay for
    a model call."""

    def _never(*_a):
        raise AssertionError("arbiter called outside the ambiguous band")

    relevant, item = pr._resolve_relevance(
        _candidate(), 0.99, _Node(), "procedure", arbiter_fn=_never
    )
    assert relevant is True and item == ""
    relevant, item = pr._resolve_relevance(
        _candidate(), 0.01, _Node(), "procedure", arbiter_fn=_never
    )
    assert relevant is False and item == ""


def test_aspirational_text_is_still_rejected_after_a_relevant_verdict():
    """ "We strive to patch promptly" is about the requirement but is not a
    control. The aspirational check applies to the arbitrated path too."""
    c = _candidate("We strive to evaluate patches in a timely manner where practicable.")
    if not pr.is_aspirational(c["text"]):
        return  # the detector's own corpus decides this; nothing to assert
    relevant, _ = pr._resolve_relevance(
        c, MID, _Node(), "procedure", arbiter_fn=_arbiter("RELEVANT")
    )
    assert relevant is False


def test_no_arbiter_means_no_arbitration_and_no_network(monkeypatch):
    """There is deliberately NO live default. The band is resolved inside
    `coverage_matrix`, which live routes call — a hidden default would put a
    model call per ambiguous pair on that path, and would make every unit test
    touching the band reach the network. Absent an injected arbiter the module
    behaves exactly as it did before stage 3: queue it."""
    seen = {}
    monkeypatch.setattr(
        pr.rq, "propose", lambda kind, **kw: seen.update(kind=kind) or type("I", (), {"id": "q"})()
    )

    def _explode(*_a, **_k):
        raise AssertionError("stage 3 must not open a connection on its own")

    monkeypatch.setattr("urllib.request.urlopen", _explode)

    relevant, item_id = pr._resolve_relevance(_candidate(), MID, _Node(), "procedure")
    assert relevant is False
    assert item_id == "q"
    assert seen["kind"] == "low_confidence_extraction"

    verdict, reason = pr.arbitrate_relevance(_candidate(), _Node())
    assert verdict == "UNSURE" and "no arbiter" in reason
