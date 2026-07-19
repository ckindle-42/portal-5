"""Fixture-first proof of the failure-attribution instrument (I9).

Every outcome class is proven on a synthetic (verdict, techniques, trace, GT)
tuple before the instrument is trusted to judge a live ablation run. Sentinel
ATTRIBTEST_V1.
"""

from __future__ import annotations

from portal.modules.security.eval.ablation_attribution import (
    MISS_CLASSES,
    OUTCOMES,
    ArmScenarioOutcome,
    classify,
    summarize,
)


def test_hit_when_grounded_true_positive_present():
    out = classify(
        arm="3section",
        scenario="s1",
        verdict="CONFIRMED",
        technique_ids=["T1558.003", "T1078"],
        ground_truth={"T1558.003"},
        trace=[{"evidence": "kerberoast ticket request"}],
    )
    assert out.outcome == "HIT"
    assert out.grounded_tp == 1
    assert out.hallucinated == 1


def test_novelty_when_anomalous_with_grounded_similar_neighbour():
    out = classify(
        arm="3section",
        scenario="s2",
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[{"note": "unusual ticket pattern"}],
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
    )
    assert out.outcome == "NOVELTY"
    assert out.detail == "T1558.003"


def test_not_novelty_when_similar_neighbour_not_in_ground_truth():
    """SIMILAR match to something outside GT is not a scored novelty win —
    falls through to the miss taxonomy instead."""
    out = classify(
        arm="3section",
        scenario="s2b",
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[],
        match_grade="SIMILAR",
        similar_to=["T1110"],
    )
    assert out.outcome == "HUNTER_MISS"


def test_non_convergence_on_unresolved():
    out = classify(
        arm="1section",
        scenario="s3",
        verdict="UNRESOLVED",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[{"round": 1}, {"round": 2}],
    )
    assert out.outcome == "NON_CONVERGENCE"


def test_hallucination_when_wrong_conclusion_and_trace_never_saw_gt():
    out = classify(
        arm="1section",
        scenario="s4",
        verdict="CONFIRMED",
        technique_ids=["T1110"],
        ground_truth={"T1558.003"},
        trace=[{"evidence": "brute force attempts"}],
    )
    assert out.outcome == "HALLUCINATION"
    assert out.hallucinated == 1


def test_handoff_loss_when_wrong_conclusion_but_trace_saw_gt():
    """Same wrong verdict as the hallucination case, but the trace shows the
    Hunter actually surfaced the GT technique — found-but-not-confirmed."""
    out = classify(
        arm="3section",
        scenario="s5",
        verdict="CONFIRMED",
        technique_ids=["T1110"],
        ground_truth={"T1558.003"},
        trace=[{"evidence": "saw T1558.003 ticket request, but moved on"}],
    )
    assert out.outcome == "HANDOFF_LOSS"
    assert out.hallucinated == 1


def test_handoff_loss_when_ruled_out_but_trace_saw_gt():
    """No hallucinated techniques at all (e.g. RULED_OUT with empty
    technique_ids) but the trace shows GT evidence was surfaced and dropped."""
    out = classify(
        arm="2section",
        scenario="s6",
        verdict="RULED_OUT",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[{"evidence": "T1558.003 ticket noted, deemed benign"}],
    )
    assert out.outcome == "HANDOFF_LOSS"
    assert out.hallucinated == 0


def test_hunter_miss_when_gt_never_surfaced_anywhere():
    out = classify(
        arm="1section",
        scenario="s7",
        verdict="RULED_OUT",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[{"evidence": "nothing unusual"}],
    )
    assert out.outcome == "HUNTER_MISS"


def test_summarize_histogram_sums_to_one_over_misses():
    outcomes = [
        ArmScenarioOutcome("3section", "a", "HIT"),
        ArmScenarioOutcome("3section", "b", "NOVELTY"),
        ArmScenarioOutcome("3section", "c", "HUNTER_MISS"),
        ArmScenarioOutcome("3section", "d", "HALLUCINATION"),
        ArmScenarioOutcome("3section", "e", "HALLUCINATION"),
        ArmScenarioOutcome("3section", "f", "HANDOFF_LOSS"),
        ArmScenarioOutcome("3section", "g", "NON_CONVERGENCE"),
    ]
    summary = summarize("3section", outcomes)
    assert summary.n == 7
    assert summary.hits == 1
    assert summary.novelty == 1
    assert summary.real_recall == round(2 / 7, 3)
    assert set(summary.miss_hist) == set(MISS_CLASSES)
    assert abs(sum(summary.miss_hist.values()) - 1.0) < 1e-6
    assert summary.miss_hist["HALLUCINATION"] == round(2 / 5, 3)
    assert summary.hallucination_rate == round(2 / 7, 3)
    assert summary.nonconv_rate == round(1 / 7, 3)


def test_summarize_empty_outcomes_does_not_divide_by_zero():
    summary = summarize("3section", [])
    assert summary.n == 0
    assert summary.real_recall == 0.0
    assert all(v == 0.0 for v in summary.miss_hist.values())


def test_all_outcomes_reachable():
    """Sanity: OUTCOMES enumerates exactly the six classes proven above."""
    assert set(OUTCOMES) == {
        "HIT",
        "NOVELTY",
        "HUNTER_MISS",
        "HANDOFF_LOSS",
        "HALLUCINATION",
        "NON_CONVERGENCE",
    }
