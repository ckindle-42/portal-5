"""The calibrated funnel and the deterministic pipeline, on production-shaped windows."""

from __future__ import annotations

import pytest

from portal.modules.security.core.review import calibration as cal
from portal.modules.security.core.review import funnel, intake, knowledge, pipeline
from portal.modules.security.core.review.contracts import (
    Channel,
    JudgeRecord,
    Outcome,
    ReviewConcern,
    ReviewResult,
    Verdict,
)

from ._fakes import HashEmbedder, three_source_window

LEVELS = ("L2_ENTITY",)
POLICY = funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=LEVELS)


def _flat_cal(channel: str, value: float, *, embedder_id: str = "") -> cal.NullCalibration:
    return cal.fit_calibration(
        channel, "L2_ENTITY", [value] * 40, 0.05, basis="benign_slice", embedder_id=embedder_id
    )


def _always_similar_reference(window: intake.IntakeResult) -> pipeline.Reference:
    cset = cal.CalibrationSet()
    cset.put(_flat_cal(funnel.CHANNEL_UNUSUAL, 9.0))  # nothing is unusual
    cset.put(_flat_cal(funnel.CHANNEL_SIMILAR, -1.0, embedder_id=HashEmbedder.identity))
    model = funnel.fit_baseline([u.unit for u in window.units], "t")
    return pipeline.Reference(model, cset, "benign_slice")


# ── funnel ────────────────────────────────────────────────────────────────────


def test_uncalibrated_channels_raise_nothing_and_say_so() -> None:
    scores = [funnel.UnitScores("u1", "L2_ENTITY", unusual=0.99, similar=0.99)]
    (decision,) = funnel.decide(scores, cal.CalibrationSet(), POLICY)
    assert not decision.flagged
    assert set(decision.uncalibrated) == {funnel.CHANNEL_UNUSUAL, funnel.CHANNEL_SIMILAR}


def test_decide_flags_above_threshold_and_ranks_by_calibrated_p() -> None:
    cset = cal.CalibrationSet()
    cset.put(
        cal.fit_calibration("unusual", "L2_ENTITY", [i / 100 for i in range(100)], 0.1, basis="b")
    )
    scores = [
        funnel.UnitScores("low", "L2_ENTITY", unusual=0.50, similar=None),
        funnel.UnitScores("high", "L2_ENTITY", unusual=0.99, similar=None),
        funnel.UnitScores("mid", "L2_ENTITY", unusual=0.93, similar=None),
        funnel.UnitScores("chain", "L3_CHAIN", unusual=0.99, similar=None),  # level not enabled
    ]
    ranked = funnel.rank(funnel.decide(scores, cset, POLICY))
    assert [d.unit_id for d in ranked] == ["high", "mid", "low"]
    assert [d.flagged for d in ranked] == [True, True, False]


def test_split_is_deterministic_and_disjoint() -> None:
    result = intake.build_window_units(three_source_window(seed=1, n=200))
    units = [u.unit for u in result.units]
    fit_a, cal_a = funnel.split_units(units, salt="x")
    fit_b, cal_b = funnel.split_units(units, salt="x")
    assert [u.unit_id for u in fit_a] == [u.unit_id for u in fit_b]
    assert not {u.unit_id for u in fit_a} & {u.unit_id for u in cal_a}
    assert len(fit_a) + len(cal_a) == len(units)


def test_baseline_survives_a_roundtrip() -> None:
    result = intake.build_window_units(three_source_window(seed=2, n=200))
    units = [u.unit for u in result.units]
    model = funnel.fit_baseline(units, "env")
    again = funnel.baseline_from_dict(funnel.baseline_to_dict(model))
    probe = [u for u in units if u.level == "L2_ENTITY"][:5]
    assert [funnel.unusual_score(u, model) for u in probe] == [
        funnel.unusual_score(u, again) for u in probe
    ]


# ── pipeline ──────────────────────────────────────────────────────────────────


def _known_attack_index(embedder: HashEmbedder) -> knowledge.AnchorIndex:
    known = intake.build_window_units(three_source_window(seed=30, n=300, attacker="evil_known"))
    episode = [
        u
        for u in known.units
        if u.unit.level == "L2_ENTITY" and any("certutil" in t for t in u.terms)
    ]
    assert episode
    anchors = pipeline.anchors_from_units(
        episode[:1], kind="attack_episode", label="cred-staging", malice="malicious", prefix="kb"
    )
    return knowledge.AnchorIndex.build(knowledge.cards_from_anchors(anchors), embedder)


def test_a_cousin_of_a_known_attack_is_raised_with_resolvable_evidence() -> None:
    embedder = HashEmbedder()
    index = _known_attack_index(embedder)
    benign = intake.build_window_units(three_source_window(seed=40, n=900))
    reference = pipeline.build_reference(
        benign, policy=POLICY, index=index, embedder=embedder, environment_id="t"
    )
    assert reference.calibrations.get(funnel.CHANNEL_SIMILAR, "L2_ENTITY") is not None
    window = intake.build_window_units(three_source_window(seed=41, n=900, attacker="evil_new"))
    result = pipeline.review_window(
        window,
        reference=reference,
        index=index,
        embedder=embedder,
        config=pipeline.ReviewConfig(policy=POLICY),
    )
    hit = [
        c
        for c in result.concerns
        if Channel.KNOWN_SIMILAR in c.channels
        and any("certutil" in window.events[e.event_id].text for e in c.evidence)
    ]
    assert hit, "the cousin of the known attack must be raised through the known-similar channel"
    assert hit[0].resembles and hit[0].resembles[0].anchor_label == "cred-staging"
    for concern in result.concerns:
        assert all(e.event_id in window.events for e in concern.evidence)
    assert result.fingerprint["embedder"] == embedder.identity
    names = {r.name for r in result.receipts}
    assert {"intake.units", "funnel.scored", "funnel.flagged", "outcomes"} <= names


def test_benign_lookalike_suppression_is_a_policy() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(three_source_window(seed=50, n=300))
    target = [u for u in window.units if u.unit.level == "L2_ENTITY"][0]
    anchors = pipeline.anchors_from_units(
        [target], kind="benign_pattern", label="known-benign", malice="benign", prefix="bn"
    )
    index = knowledge.AnchorIndex.build(knowledge.cards_from_anchors(anchors), embedder)
    assert knowledge.explain(target.unit, index.cards[0].record)[0] == "EXACT"
    reference = _always_similar_reference(window)

    def run(policy: str) -> ReviewResult:
        return pipeline.review_window(
            window,
            reference=reference,
            index=index,
            embedder=embedder,
            config=pipeline.ReviewConfig(policy=POLICY, suppress_benign=policy),
        )

    exact = run("exact_only")
    assert target.unit.unit_id in {c.unit_id for c in exact.suppressed}
    never = run("never")
    assert not never.suppressed
    assert any(
        c.unit_id == target.unit.unit_id and c.outcome == Outcome.COUSIN for c in never.concerns
    )


def test_novel_concerns_carry_an_absence_receipt() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(three_source_window(seed=60, n=300))
    index = _known_attack_index(embedder)
    cset = cal.CalibrationSet()
    cset.put(_flat_cal(funnel.CHANNEL_UNUSUAL, -1.0))  # everything is unusual
    cset.put(
        _flat_cal(funnel.CHANNEL_SIMILAR, 9.0, embedder_id=embedder.identity)
    )  # nothing similar
    model = funnel.fit_baseline([u.unit for u in window.units], "t")
    result = pipeline.review_window(
        window,
        reference=pipeline.Reference(model, cset, "benign_slice"),
        index=index,
        embedder=embedder,
        config=pipeline.ReviewConfig(policy=POLICY),
    )
    novel = [c for c in result.concerns if c.outcome == Outcome.NOVEL]
    assert novel
    for concern in novel:
        assert concern.absence is not None
        assert concern.absence.population == index.population
        assert "searched 1 anchors" in concern.absence.statement
        assert concern.absence.calibration_id


def test_a_channel_that_cannot_be_certified_is_reported_not_guessed() -> None:
    benign = intake.build_window_units(three_source_window(seed=70, n=60))
    tiny = funnel.FunnelPolicy(
        alpha_unusual=0.001, alpha_similar=0.001, levels=("L2_ENTITY", "L3_CHAIN")
    )
    reference = pipeline.build_reference(
        benign, policy=tiny, index=None, embedder=None, environment_id="t"
    )
    assert reference.degraded and all("cannot certify" in d for d in reference.degraded)
    assert reference.calibrations.ids() == []


def test_default_defense_response_is_indeterminate_never_covered() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(three_source_window(seed=80, n=200))
    result = pipeline.review_window(
        window,
        reference=_always_similar_reference(window),
        index=_known_attack_index(embedder),
        embedder=embedder,
        config=pipeline.ReviewConfig(policy=POLICY),
    )
    assert result.concerns
    assert {c.defense_response.value for c in result.concerns} == {"INDETERMINATE"}


def test_judge_stage_is_optional_and_receipted() -> None:
    embedder = HashEmbedder()
    window = intake.build_window_units(three_source_window(seed=90, n=200))
    calls: list[str] = []

    def judge(concern: ReviewConcern, _w: intake.IntakeResult) -> JudgeRecord:
        calls.append(concern.concern_id)
        return JudgeRecord(model="fake", verdict=Verdict.UNSURE)

    result = pipeline.review_window(
        window,
        reference=_always_similar_reference(window),
        index=_known_attack_index(embedder),
        embedder=embedder,
        config=pipeline.ReviewConfig(policy=POLICY, judge_max=2),
        judge=judge,
    )
    assert len(calls) == min(2, len(result.concerns))
    receipt = [r for r in result.receipts if r.name == "judge"][0]
    assert (receipt.examined, receipt.resolved) == (len(result.concerns), len(calls))


def test_cancel_callback_aborts_the_run() -> None:
    window = intake.build_window_units(three_source_window(seed=95, n=100))

    def cancel() -> None:
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        pipeline.review_window(
            window,
            reference=_always_similar_reference(window),
            index=_known_attack_index(HashEmbedder()),
            embedder=HashEmbedder(),
            config=pipeline.ReviewConfig(policy=POLICY),
            cancel=cancel,
        )
