"""The learning loop: verdicts become knowledge, reversals are quarantined, replay is honest,
and maturation silences an exact repeat without silencing a cousin."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core.review import verdicts
from portal.modules.security.core.review.contracts import TruthClass, Verdict
from portal.modules.security.core.review.store import ReviewStore

RECORD = {"card": "sources: a | classes: other | values: certutil -urlcache", "terms": ["certutil"]}


def seeded(
    store: ReviewStore, concern_id: str = "cn-1", *, card: str | None = None, p: float = 0.01
) -> str:
    record = dict(RECORD, card=card or RECORD["card"])
    payload: dict[str, Any] = {
        "resembles": [{"anchor_label": "cred-staging"}],
        "judge": {"verdict": "something"},
    }
    store.put_concern("run-1", concern_id, f"u-{concern_id}", "COUSIN", p, payload, record)
    return concern_id


def test_verdicts_are_append_only_and_the_machine_never_displaces_the_operator() -> None:
    store = ReviewStore()
    cid = seeded(store)
    store.append_verdict(cid, Verdict.NOTHING, actor="analyst:a")
    store.append_verdict(
        cid, Verdict.SOMETHING, actor="judge", truth_class=TruthClass.MACHINE_DERIVED
    )
    assert [v.verdict for v in store.verdicts_for(cid)] == [Verdict.NOTHING, Verdict.SOMETHING]
    effective = store.effective_verdict(cid)
    assert effective is not None and effective.verdict == Verdict.NOTHING


def test_write_back_policy_per_verdict() -> None:
    store = ReviewStore()
    bad, good, maybe = seeded(store, "cn-bad"), seeded(store, "cn-good"), seeded(store, "cn-maybe")
    out_bad = verdicts.record_verdict(store, bad, Verdict.SOMETHING, actor="analyst:a")
    out_good = verdicts.record_verdict(store, good, Verdict.NOTHING, actor="analyst:a")
    out_maybe = verdicts.record_verdict(store, maybe, Verdict.UNSURE, actor="analyst:a")
    by_id = {a.anchor_id: a for a in store.anchors()}
    assert by_id[out_bad.anchor_id or ""].kind == "confirmed_finding"
    assert by_id[out_bad.anchor_id or ""].malice == "malicious"
    assert by_id[out_good.anchor_id or ""].kind == "benign_pattern"
    assert by_id[out_good.anchor_id or ""].truth_class == TruthClass.OPERATOR_DECISION
    assert by_id[out_bad.anchor_id or ""].label == "cred-staging"
    assert out_maybe.anchor_id is None and len(by_id) == 2


def test_a_reversal_quarantines_the_anchor_it_wrote_and_replay_still_sees_it() -> None:
    store = ReviewStore()
    cid = seeded(store)
    first = verdicts.record_verdict(store, cid, Verdict.NOTHING, actor="analyst:a", at=100.0)
    second = verdicts.record_verdict(store, cid, Verdict.SOMETHING, actor="analyst:b", at=200.0)
    assert second.quarantined == [first.anchor_id]
    now = {a.anchor_id for a in store.anchors()}
    assert first.anchor_id not in now and second.anchor_id in now
    then = {a.anchor_id for a in store.anchors(as_of=150.0)}
    assert then == {first.anchor_id}  # what was believed at t=150, before the reversal
    assert verdicts.cards_from_store(store, as_of=150.0)[0].malice == "benign"
    assert first.anchor_id in {a.anchor_id for a in store.anchors(include_quarantined=True)}


def test_scripted_verdicts_must_be_labelled_and_unknown_concerns_refused() -> None:
    store = ReviewStore()
    cid = seeded(store)
    with pytest.raises(verdicts.VerdictError):
        verdicts.record_verdict(store, cid, Verdict.NOTHING, actor="analyst:a", scripted=True)
    with pytest.raises(verdicts.VerdictError):
        verdicts.record_verdict(store, cid, Verdict.NOTHING, actor="scripted:truth")
    with pytest.raises(verdicts.VerdictError):
        verdicts.record_verdict(store, "cn-missing", Verdict.NOTHING, actor="analyst:a")
    ok = verdicts.record_verdict(store, cid, Verdict.NOTHING, actor="scripted:truth", scripted=True)
    assert (
        store.verdicts_for(cid)[0].verdict_id == ok.verdict_id
        and store.verdicts_for(cid)[0].scripted
    )


def test_the_queue_is_most_surprising_first_and_hides_decided_concerns() -> None:
    store = ReviewStore()
    seeded(store, "cn-a", p=0.30)
    seeded(store, "cn-b", p=0.01)
    seeded(store, "cn-c", p=0.05)
    verdicts.record_verdict(store, "cn-c", Verdict.NOTHING, actor="analyst:a")
    verdicts.record_verdict(store, "cn-a", Verdict.UNSURE, actor="analyst:a")
    assert [c.concern_id for c in store.queue()] == ["cn-b", "cn-a"]  # unsure stays; decided leaves


def test_contradictions_are_generated_by_exception() -> None:
    store = ReviewStore()
    a, b, c = (
        seeded(store, "cn-a", card="same card"),
        seeded(store, "cn-b", card="same card"),
        seeded(store, "cn-c", card="other"),
    )
    verdicts.record_verdict(store, a, Verdict.NOTHING, actor="analyst:a")
    verdicts.record_verdict(store, b, Verdict.SOMETHING, actor="analyst:b")
    verdicts.record_verdict(store, c, Verdict.NOTHING, actor="analyst:a")
    verdicts.record_verdict(store, c, Verdict.SOMETHING, actor="analyst:a")
    kinds = {(x["kind"], tuple(x["concern_ids"])) for x in verdicts.contradictions(store)}
    assert ("same_evidence_opposite_verdicts", ("cn-a", "cn-b")) in kinds
    assert ("analyst_reversal", ("cn-c",)) in kinds
    assert ("machine_vs_operator", ("cn-a",)) in kinds  # the seeded judge said 'something'
    assert ("malicious_matches_benign_anchor", ("cn-b",)) in kinds


def test_confirmed_finding_inherits_the_techniques_it_was_raised_under() -> None:
    """Part A: the anchor record carries the ids the concern's resemblance asserted."""
    store = ReviewStore()
    payload: dict[str, Any] = {
        "resembles": [{"anchor_label": "analyst-confirmed", "techniques": ["T1059"]}],
    }
    store.put_concern("run-1", "cn-tech", "u-tech", "COUSIN", 0.01, payload, dict(RECORD))
    out = verdicts.record_verdict(store, "cn-tech", Verdict.SOMETHING, actor="analyst:a")
    assert out.anchor_id is not None
    anchor = next(a for a in store.anchors() if a.anchor_id == out.anchor_id)
    assert anchor.label == "analyst-confirmed"
    assert anchor.record.get("technique_ids") == ["T1059"]


def test_write_back_invents_no_technique_when_none_was_known() -> None:
    store = ReviewStore()
    seeded(store, "cn-plain")
    out = verdicts.record_verdict(store, "cn-plain", Verdict.SOMETHING, actor="analyst:a")
    anchor = next(a for a in store.anchors() if a.anchor_id == out.anchor_id)
    assert "technique_ids" not in anchor.record


def test_techniques_in_a_pre_data_payload_are_carried_from_the_raising_label_once() -> None:
    """Payloads written before resemblances carried techniques: the raising label's
    published ids move onto the record once, at write-back, never re-parsed again."""
    store = ReviewStore()
    payload: dict[str, Any] = {"resembles": [{"anchor_label": "T1059 encoded command"}]}
    store.put_concern("run-1", "cn-old", "u-old", "COUSIN", 0.01, payload, dict(RECORD))
    out = verdicts.record_verdict(store, "cn-old", Verdict.SOMETHING, actor="analyst:a")
    anchor = next(a for a in store.anchors() if a.anchor_id == out.anchor_id)
    assert anchor.record.get("technique_ids") == ["T1059"]
