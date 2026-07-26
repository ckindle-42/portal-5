"""Tests for the V6 hunt-and-notify scoreboard."""

from __future__ import annotations

from portal.modules.security.core import notify_scoreboard as ns
from portal.modules.security.core import recall_attribution as ra


def _cell(
    *,
    expected: str = "T1558.004",
    verdict: str = "RULED_OUT",
    reported: list[str] | None = None,
    oracle: str = ra.PRESENT,
    match_grade: str | None = "SIMILAR",
) -> dict:
    cell = {
        "label": expected.lower(),
        "technique_expected": expected,
        "model_arm": "synthetic",
        "status": "done",
        "verdict": verdict,
        "technique_ids": reported or [],
        "oracle_result": oracle,
    }
    if match_grade is not None:
        cell["match_grade"] = match_grade
    return cell


def test_axis_1_anomaly_is_a_full_catch_and_ruled_out_is_not():
    result = ns.score_arm(
        [
            _cell(verdict="ANOMALOUS_UNCLASSIFIED"),
            _cell(expected="T1558.003", verdict="RULED_OUT"),
        ]
    )
    axis = result["axis_1_notify_recall"]
    assert axis["raw"] == {"notified": 1, "eligible": 2, "rate": 0.5}
    assert axis["fair"] == {"notified": 1, "eligible": 2, "rate": 0.5}


def test_fair_denominator_excludes_absent_and_present_silence_is_real_miss():
    result = ns.score_arm(
        [
            _cell(expected="T1558.003", verdict="RULED_OUT", oracle=ra.ABSENT),
            _cell(expected="T1558.004", verdict="RULED_OUT", oracle=ra.PRESENT),
        ]
    )
    axis = result["axis_1_notify_recall"]
    assert axis["fair"] == {"notified": 0, "eligible": 1, "rate": 0.0}
    assert axis["evidence_never_shown"] == 1
    assert axis["real_misses"] == 1
    assert axis["real_misses_by_technique"] == [{"technique": "T1558.004", "verdict": "RULED_OUT"}]


def test_axis_2_required_ordering_and_notification_classes():
    cells = [
        _cell(verdict="CONFIRMED", reported=["T1558.004"]),
        _cell(expected="T1558.003", verdict="CONFIRMED", reported=["T1053.005"]),
        _cell(expected="T1110.003", verdict="ANOMALOUS_UNCLASSIFIED"),
    ]
    axis = ns.score_arm(cells)["axis_2_notification_trustworthiness"]
    ranks = axis["ordinal_ranks"]
    assert ranks[ns.CONFIRMED_CORRECT] > ranks[ns.HONEST_ANOMALY]
    assert ranks[ns.HONEST_ANOMALY] > ranks[ns.CONFIRMED_WRONG]
    assert axis["confirmed_correct"] == 1
    assert axis["honest_anomaly"] == 1
    assert axis["confirmed_wrong"] == 1


def test_axis_3_is_conditional_on_catches_and_silence_is_not_a_zero():
    result = ns.score_arm(
        [
            _cell(verdict="CONFIRMED", reported=["T1558.004"]),
            _cell(expected="T1558.003", verdict="ANOMALOUS_UNCLASSIFIED"),
            _cell(expected="T1053.005", verdict="RULED_OUT"),
        ]
    )
    axis = result["axis_3_mapping_quality_given_catch"]
    assert axis["caught_cells"] == 2
    assert axis["mapping_categories"] == {
        "exact": 1,
        "parent": 0,
        "tactic": 0,
        "unclassified": 1,
        "incorrect": 0,
    }
    assert axis["silent_cells_excluded"] == 1


def test_all_attack_corpus_reports_benign_precision_as_unmeasurable():
    gap = ns.score_arm([_cell(verdict="ANOMALOUS_UNCLASSIFIED")])["measurement_gaps"][
        "notification_precision_on_benign_activity"
    ]
    assert gap["status"] == "UNMEASURABLE"
    assert gap["value"] is None
    assert "no benign cells" in gap["reason"]


def test_missing_historical_match_grade_is_unknown_not_inferred():
    axis = ns.score_arm([_cell(verdict="CONFIRMED", reported=["T1558.004"], match_grade=None)])[
        "axis_3_mapping_quality_given_catch"
    ]
    assert axis["match_grades"] == {"UNKNOWN": 1}


def test_deterministic_for_same_input():
    cells = [
        _cell(verdict="ANOMALOUS_UNCLASSIFIED", oracle=ra.INDETERMINATE),
        _cell(expected="T1558.003", verdict="RULED_OUT", oracle=ra.ABSENT),
    ]
    assert ns.score_arm(cells) == ns.score_arm(cells)
