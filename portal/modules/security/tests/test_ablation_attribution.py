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
    decide_route,
    summarize,
)


def _decision(
    *,
    best_arm="3section",
    miss_hist,
    real_recall=0.5,
    other_real_recall=0.1,
    error_rate=0.0,
    honest_blocked=False,
):
    """Minimal crafted ABLATION_DECISION.json-shaped dict for decide_route tests."""
    arm_summary = {
        "arm": best_arm,
        "n": 10,
        "hits": 0,
        "novelty": 0,
        "real_recall": real_recall,
        "miss_hist": miss_hist,
        "hallucination_rate": miss_hist.get("HALLUCINATION", 0.0),
        "nonconv_rate": miss_hist.get("NON_CONVERGENCE", 0.0),
    }
    other_arm = {**arm_summary, "real_recall": other_real_recall}
    return {
        "head": "deadbeef",
        "generated_at": "2026-07-18T00:00:00Z",
        "reps": 3,
        "corpus_n": 10,
        "error_rate": error_rate,
        "arms": {"1section": other_arm, "2section": other_arm, best_arm: arm_summary},
        "best_multi_arm": best_arm,
        "split_proven": False,
        "honest_blocked": honest_blocked,
        "block_reason": None,
    }


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
        trace=[{"role": "tool", "content": "brute force attempts, EventID 4625"}],
    )
    assert out.outcome == "HALLUCINATION"
    assert out.hallucinated == 1


def test_handoff_loss_when_wrong_conclusion_but_trace_saw_gt():
    """Same wrong verdict as the hallucination case, but a section's own
    CITED evidence list (not free-text reasoning/hypothesis prose) actually
    surfaced the GT technique — found-but-not-confirmed."""
    out = classify(
        arm="3section",
        scenario="s5",
        verdict="CONFIRMED",
        technique_ids=["T1110"],
        ground_truth={"T1558.003"},
        trace=[
            {
                "section": "reasoning",
                "raw": '{"technique_ids": [], "evidence": '
                '["EventCode=4769 TGS request noted for T1558.003"], '
                '"reasoning": "considered, but moved on", "request_more": ""}',
            }
        ],
    )
    assert out.outcome == "HANDOFF_LOSS"
    assert out.hallucinated == 1


def test_handoff_loss_when_ruled_out_but_trace_saw_gt():
    """No hallucinated techniques at all (e.g. RULED_OUT with empty
    technique_ids) but a section's own CITED evidence surfaced GT and it was
    dropped/deemed benign."""
    out = classify(
        arm="2section",
        scenario="s6",
        verdict="RULED_OUT",
        technique_ids=[],
        ground_truth={"T1558.003"},
        trace=[
            {
                "section": "merged",
                "raw": '{"technique_ids": [], "evidence": '
                '["EventCode=4769 TGS request T1558.003 noted, deemed benign"], '
                '"reasoning": "benign", "request_more": ""}',
            }
        ],
    )
    assert out.outcome == "HANDOFF_LOSS"
    assert out.hallucinated == 0


def test_hunter_miss_when_real_retrieval_is_topically_unrelated_to_ground_truth():
    """A real (`matched-exact`) tool retrieval that never mentions the ground
    truth technique's ID/parent-number/known marker anywhere in the trace is
    NOT evidence the hunter "saw" that ground truth — it's evidence of
    something else entirely. This must classify HUNTER_MISS, not HANDOFF_LOSS.

    A prior version of this test asserted the opposite (HANDOFF_LOSS), on the
    theory that any real structural retrieval should generalize to cover
    genuinely novel patterns a marker table can't recognize. Quantified live
    against the full 89-scenario ablation corpus (2026-07-22): that structural
    shortcut fired on 267/267 (100%) of both the 2-section and 3-section arms'
    records regardless of topical relevance, making HUNTER_MISS structurally
    unreachable for those arms (0.0% in both) while masking a real ~24-49%
    HUNTER_MISS rate and a real ~8-13% HALLUCINATION rate underneath it. Ground
    truth here is always a real classified MITRE ID, so ID/parent-substring
    text matching already generalizes reasonably without that shortcut's
    false-positive cost — see `_trace_mentions_any`'s docstring."""
    out = classify(
        arm="3section",
        scenario="s8",
        verdict="RULED_OUT",
        technique_ids=[],
        ground_truth={"T9999.001"},  # deliberately not in any known-marker table
        trace=[
            {"round": 1, "section": "tool", "provenance": "matched-exact", "query": "novel query"},
        ],
    )
    assert out.outcome == "HUNTER_MISS"


def test_hunter_miss_when_only_empty_or_synthetic_provenance():
    """Tool rounds exist but every one came back empty or synthetic-fallback
    (no real match, known or novel) — genuinely no evidence was surfaced."""
    out = classify(
        arm="3section",
        scenario="s9",
        verdict="RULED_OUT",
        technique_ids=[],
        ground_truth={"T9999.001"},
        trace=[
            {"round": 1, "section": "tool", "provenance": "empty", "query": "q1"},
            {"round": 2, "section": "tool", "provenance": "synthetic-fallback", "query": "q2"},
        ],
    )
    assert out.outcome == "HUNTER_MISS"


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


# ── Phase 3: decide_route ────────────────────────────────────────────────────


def test_route_blocked_on_honest_blocked_flag():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.5,
            "HANDOFF_LOSS": 0.2,
            "HALLUCINATION": 0.2,
            "NON_CONVERGENCE": 0.1,
        },
        honest_blocked=True,
    )
    route, reason = decide_route(decision)
    assert route == "BLOCKED"


def test_route_blocked_on_high_error_rate():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.5,
            "HANDOFF_LOSS": 0.2,
            "HALLUCINATION": 0.2,
            "NON_CONVERGENCE": 0.1,
        },
        error_rate=0.25,
    )
    route, _ = decide_route(decision)
    assert route == "BLOCKED"


def test_route_blocked_on_degenerate_low_recall_no_dominant_class():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.3,
            "HANDOFF_LOSS": 0.3,
            "HALLUCINATION": 0.2,
            "NON_CONVERGENCE": 0.2,
        },
        real_recall=0.01,
        other_real_recall=0.01,
    )
    route, _ = decide_route(decision)
    assert route == "BLOCKED"


def test_route_retrieval_first_when_hunter_miss_dominates():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.6,
            "HANDOFF_LOSS": 0.2,
            "HALLUCINATION": 0.1,
            "NON_CONVERGENCE": 0.1,
        },
    )
    route, reason = decide_route(decision)
    assert route == "RETRIEVAL_FIRST"
    assert "evidence not gathered" in reason


def test_route_budget_first_when_nonconvergence_dominates_with_progress():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.1,
            "HANDOFF_LOSS": 0.1,
            "HALLUCINATION": 0.1,
            "NON_CONVERGENCE": 0.7,
        },
    )
    route, reason = decide_route(decision, nonconv_progress_frac=0.8)
    assert route == "BUDGET_FIRST"
    assert "loop cut off" in reason


def test_route_council_when_nonconvergence_dominates_without_progress():
    """Same dominant miss class as the BUDGET_FIRST case, but the trace shows
    no real progress before the budget ran out — that's not a rounds problem,
    fall through to the default COUNCIL route instead."""
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.1,
            "HANDOFF_LOSS": 0.1,
            "HALLUCINATION": 0.1,
            "NON_CONVERGENCE": 0.7,
        },
    )
    route, _ = decide_route(decision, nonconv_progress_frac=0.1)
    assert route == "COUNCIL"


def test_route_council_default_when_hallucination_or_handoff_dominates():
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.1,
            "HANDOFF_LOSS": 0.3,
            "HALLUCINATION": 0.5,
            "NON_CONVERGENCE": 0.1,
        },
    )
    route, reason = decide_route(decision)
    assert route == "COUNCIL"
    assert "cross-check" in reason


def test_route_priority_blocked_wins_over_retrieval_first():
    """Rule order matters (I10): honest_blocked short-circuits before the
    miss-class rules are ever consulted, even if HUNTER_MISS looks dominant."""
    decision = _decision(
        miss_hist={
            "HUNTER_MISS": 0.9,
            "HANDOFF_LOSS": 0.05,
            "HALLUCINATION": 0.05,
            "NON_CONVERGENCE": 0.0,
        },
        honest_blocked=True,
    )
    route, _ = decide_route(decision)
    assert route == "BLOCKED"
