"""SA4.5 -- proposed-structure hypotheses + independent-basis confirmation (A2).

Hermetic: the discovery lane's proposals are recorded as hypotheses, never as
labels; nothing auto-promotes; confirmation requires and records an independent
basis; scored reports exclude unconfirmed proposals.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully.analyst_corpus import (
    T1_CONFIRMED,
    T2_PROPOSED,
    HypothesisStore,
)


def _store(tmp_path) -> HypothesisStore:
    return HypothesisStore(tmp_path / "hypotheses.jsonl")


def test_proposal_never_auto_promotes(tmp_path):
    store = _store(tmp_path)
    proposal = store.propose(
        kind="candidate_relationship",
        subject="T1558.003",
        detail={"left": "a", "right": "b", "distance": 0.21},
    )
    assert proposal["confirmed"] is False
    assert proposal["promoted_to_tier"] is None
    assert proposal["basis"] is None
    assert store.scoreable_labels() == ()  # not scoreable until confirmed


def test_confirmation_requires_and_records_independent_basis(tmp_path):
    store = _store(tmp_path)
    proposal = store.propose(kind="cluster", subject="group-A", detail={"members": ["a", "b", "c"]})
    with pytest.raises(ValueError):
        store.confirm(proposal["hypothesis_id"], basis="", basis_evidence={})
    confirmed = store.confirm(
        proposal["hypothesis_id"],
        basis="operator review of overlapping detector outcomes",
        basis_evidence={"reviewer": "sec-ops", "detectors": ["d1", "d2"]},
    )
    assert confirmed["confirmed"] is True
    assert confirmed["promoted_to_tier"] == T1_CONFIRMED
    assert "operator review" in confirmed["basis"]
    assert confirmed["basis_evidence"]["reviewer"] == "sec-ops"
    # Now it is scoreable ground truth for scored reports.
    assert [row["hypothesis_id"] for row in store.scoreable_labels()] == [proposal["hypothesis_id"]]


def test_scored_reports_exclude_unconfirmed_proposals(tmp_path):
    store = _store(tmp_path)
    store.propose(kind="recurring_type", subject="okta-mfa-fatigue", detail={"count": 3})
    store.propose(
        kind="candidate_relationship", subject="T1078", detail={"left": "x", "right": "y"}
    )
    assert store.confirmed() == ()
    assert store.unconfirmed()  # proposals exist but none are scoreable
    assert store.scoreable_labels() == ()


def test_confirm_unknown_hypothesis_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.confirm("hyp-does-not-exist", basis="operator review", basis_evidence={})


def test_second_confirm_is_rejected(tmp_path):
    store = _store(tmp_path)
    proposal = store.propose(kind="cluster", subject="group-B", detail={"members": ["a"]})
    store.confirm(
        proposal["hypothesis_id"], basis="external label", basis_evidence={"source": "osint"}
    )
    with pytest.raises(ValueError):
        store.confirm(proposal["hypothesis_id"], basis="another basis", basis_evidence={})
    rows = store.proposals()
    assert rows[0]["basis"] == "external label"  # first basis is preserved


def test_unknown_hypothesis_kind_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.propose(kind="not-a-kind", subject="x", detail={})


def test_promoted_tier_is_t1_never_t2(tmp_path):
    """A confirmed hypothesis promotes T2->T1 (an independent-basis-confirmed
    label), never to T2 -- the machine-proposed tier stays machine until an
    independent basis confirms it."""
    store = _store(tmp_path)
    proposal = store.propose(kind="candidate_relationship", subject="T1043", detail={})
    assert proposal["promoted_to_tier"] is None
    confirmed = store.confirm(
        proposal["hypothesis_id"], basis="human confirmation", basis_evidence={"analyst": "id-9"}
    )
    assert confirmed["promoted_to_tier"] == T1_CONFIRMED
    assert confirmed["promoted_to_tier"] != T2_PROPOSED
