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
        "document_id": "the operator's document.pdf",
    }


def _arbiter(verdict, reason="because"):
    def fn(_model, _system, _user):
        return f'{{"verdict":"{verdict}","reason":"{reason}"}}'

    return fn


MID = (pr.RERANK_THRESHOLD_LOW + pr.RERANK_THRESHOLD_HIGH) / 2


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
