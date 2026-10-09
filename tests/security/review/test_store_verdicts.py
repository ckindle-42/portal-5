"""The learning loop: verdicts become knowledge, reversals are quarantined, replay is honest,
and maturation silences an exact repeat without silencing a cousin."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core.review import calibration as cal
from portal.modules.security.core.review import funnel, intake, knowledge, pipeline, verdicts
from portal.modules.security.core.review.contracts import Outcome, TruthClass, Verdict
from portal.modules.security.core.review.store import ReviewStore

from ._fakes import HashEmbedder, three_source_window

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


# ── maturation, end to end ───────────────────────────────────────────────────

POLICY = funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L2_ENTITY",))


def _flat(channel: str, value: float, embedder_id: str = "") -> cal.NullCalibration:
    return cal.fit_calibration(
        channel, "L2_ENTITY", [value] * 40, 0.05, basis="benign_slice", embedder_id=embedder_id
    )


def test_maturation_silences_the_exact_repeat_but_not_the_cousin() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(three_source_window(seed=100, n=300))
    baseline = funnel.fit_baseline([u.unit for u in window.units], "t")
    store = ReviewStore()
    config = pipeline.ReviewConfig(policy=POLICY)

    # cycle 1: nothing is known; everything unusual is raised as NOVEL.
    cals1 = cal.CalibrationSet()
    cals1.put(_flat(funnel.CHANNEL_UNUSUAL, -1.0))
    first = pipeline.review_window(
        window,
        reference=pipeline.Reference(baseline, cals1, "benign_slice"),
        index=None,
        embedder=None,
        config=config,
    )
    novel = [c for c in first.concerns if c.outcome == Outcome.NOVEL]
    assert len(novel) >= 2
    verdicts.persist_run(store, first, window)
    closed = novel[0]
    verdicts.record_verdict(store, closed.concern_id, Verdict.NOTHING, actor="analyst:alice")

    # cycle 2: the closed pattern is now knowledge; known-similar flags everything.
    cards = verdicts.cards_from_store(store)
    assert [c.malice for c in cards] == ["benign"]
    index = knowledge.AnchorIndex.build(cards, embedder)
    cals2 = cal.CalibrationSet()
    cals2.put(_flat(funnel.CHANNEL_UNUSUAL, 9.0))
    cals2.put(_flat(funnel.CHANNEL_SIMILAR, -1.0, embedder.identity))
    second = pipeline.review_window(
        window,
        reference=pipeline.Reference(baseline, cals2, "benign_slice"),
        index=index,
        embedder=embedder,
        config=config,
    )
    assert closed.unit_id in {c.unit_id for c in second.suppressed}  # the exact repeat is quiet
    cousins = [c for c in second.concerns if c.outcome == Outcome.COUSIN]
    assert cousins, "a unit that merely resembles the benign pattern must still surface"
    assert all(c.unit_id != closed.unit_id for c in second.concerns)
    assert cousins[0].resembles[0].malice == "benign"


def test_poisoned_benign_knowledge_is_quarantined_and_cycle_three_raises_again() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(
        three_source_window(seed=141, n=300, attacker="attacker-account")
    )
    baseline = funnel.fit_baseline([u.unit for u in window.units], "t")
    store = ReviewStore()
    config = pipeline.ReviewConfig(policy=POLICY)

    cycle_one_null = cal.CalibrationSet()
    cycle_one_null.put(_flat(funnel.CHANNEL_UNUSUAL, -1.0))
    cycle_one = pipeline.review_window(
        window,
        reference=pipeline.Reference(baseline, cycle_one_null, "benign_slice"),
        index=None,
        embedder=None,
        config=config,
    )
    malicious = next(
        (
            concern
            for concern in cycle_one.concerns
            if any(
                "certutil -urlcache" in window.events[ref.event_id].text.lower()
                for ref in concern.evidence
            )
        ),
        None,
    )
    assert malicious is not None  # fixture truth: this unit contains the planted attack sequence
    verdicts.persist_run(store, cycle_one, window)

    wrong = verdicts.record_verdict(
        store,
        malicious.concern_id,
        Verdict.NOTHING,
        actor="analyst:incorrect-close",
        at=cycle_one.finished_at + 1.0,
    )
    assert wrong.anchor_id is not None
    cycle_two_cards = verdicts.cards_from_store(store)
    cycle_two_index = knowledge.AnchorIndex.build(cycle_two_cards, embedder)
    cycle_two_null = cal.CalibrationSet()
    cycle_two_null.put(_flat(funnel.CHANNEL_UNUSUAL, 9.0))
    cycle_two_null.put(_flat(funnel.CHANNEL_SIMILAR, -1.0, embedder.identity))
    cycle_two = pipeline.review_window(
        window,
        reference=pipeline.Reference(baseline, cycle_two_null, "benign_slice"),
        index=cycle_two_index,
        embedder=embedder,
        config=config,
    )
    assert malicious.unit_id in {concern.unit_id for concern in cycle_two.suppressed}

    reversal = verdicts.record_verdict(
        store,
        malicious.concern_id,
        Verdict.SOMETHING,
        actor="analyst:corrected-review",
        at=cycle_one.finished_at + 2.0,
    )
    assert reversal.quarantined == [wrong.anchor_id]
    assert wrong.anchor_id not in {card.anchor_id for card in verdicts.cards_from_store(store)}
    assert wrong.anchor_id in {
        row.anchor_id for row in store.anchors(include_quarantined=True) if row.quarantined
    }

    cycle_three_index = knowledge.AnchorIndex.build(verdicts.cards_from_store(store), embedder)
    cycle_three = pipeline.review_window(
        window,
        reference=pipeline.Reference(baseline, cycle_two_null, "benign_slice"),
        index=cycle_three_index,
        embedder=embedder,
        config=config,
    )
    reopened = [concern for concern in cycle_three.concerns if concern.unit_id == malicious.unit_id]
    assert reopened and reopened[0].outcome == Outcome.KNOWN_INSTANCE
    assert any(
        item["kind"] == "analyst_reversal" and item["concern_ids"] == [malicious.concern_id]
        for item in verdicts.contradictions(store)
    )
