"""R.3c -- techniques are log-series; cousinhood by sequence alignment."""

from __future__ import annotations

from portal.modules.security.core.bully import loop_grader
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.series_cousin import (
    BehaviouralSeries,
    decide_cousin,
)


def _series(sid, spine, technique=None):
    return BehaviouralSeries(
        series_id=sid, spine=tuple(spine), n_logs=len(spine), technique=technique
    )


KNOWN_4LOG = _series("known-1", ["auth", "enumerate", "escalate", "collect"], technique="T1078")


def test_inserted_step_grades_cousin_not_exact() -> None:
    observed = _series("obs-1", ["auth", "enumerate", "lateral", "escalate", "collect"])
    result = decide_cousin(observed, [KNOWN_4LOG])
    assert result.relation == "COUSIN"
    assert result.relation != "EXACT"


def test_seeded_violation_set_overlap_wrongly_reads_exact() -> None:
    """Seeded violation: grading by set overlap (ignoring order/length) would
    treat the inserted-step observation as EXACT because the class SET
    matches, and assert that (wrong) approach is wrong."""
    observed_classes = {"auth", "enumerate", "lateral", "escalate", "collect"}
    known_classes = set(KNOWN_4LOG.spine)
    # set-overlap grader would call this EXACT because known_classes subset
    assert known_classes <= observed_classes
    # but the real alignment grader (tested above) correctly says COUSIN
    observed = _series("obs-1b", ["auth", "enumerate", "lateral", "escalate", "collect"])
    result = decide_cousin(observed, [KNOWN_4LOG])
    assert result.relation != "EXACT"


def test_reversed_order_grades_novel_not_a_match() -> None:
    observed = _series("obs-2", ["escalate", "enumerate", "auth", "collect"])
    result = decide_cousin(observed, [KNOWN_4LOG])
    assert result.relation in ("NOVEL", "NONE")
    assert result.relation not in ("EXACT", "COUSIN")


def test_repeated_generic_class_does_not_produce_cousin() -> None:
    observed = _series("obs-3", ["execute", "execute", "execute"])
    library = [_series("known-2", ["execute", "execute", "execute", "execute"])]
    result = decide_cousin(observed, library)
    # single distinct class repeated is not a real backbone
    assert result.relation != "COUSIN"


def test_single_log_observation_is_none() -> None:
    observed = _series("obs-4", ["auth"])
    result = decide_cousin(observed, [KNOWN_4LOG])
    assert result.relation in ("NONE", "NOVEL")
    assert not observed.is_multi_log


def test_exact_match_of_full_known_series() -> None:
    observed = _series("obs-5", ["auth", "enumerate", "escalate", "collect"])
    result = decide_cousin(observed, [KNOWN_4LOG])
    assert result.relation == "EXACT"


def test_distance_normalized_by_known_series_length_comparable_across_techniques() -> None:
    short_known = _series("known-short", ["auth", "escalate"])
    long_known = _series(
        "known-long", ["auth", "enumerate", "escalate", "collect", "destroy", "c2_exfil"]
    )
    obs_short = _series("obs-short", ["auth", "escalate"])
    obs_long = _series(
        "obs-long", ["auth", "enumerate", "escalate", "collect", "destroy", "c2_exfil"]
    )
    r_short = decide_cousin(obs_short, [short_known])
    r_long = decide_cousin(obs_long, [long_known])
    assert r_short.relation == "EXACT"
    assert r_long.relation == "EXACT"
    assert r_short.distance <= EXACT_TOLERANCE
    assert r_long.distance <= EXACT_TOLERANCE


EXACT_TOLERANCE = 0.15


def test_load_attack_episode_builds_multi_log_series_from_ordered_logs() -> None:
    lib = AnchorLibrary()
    logs = [
        {"verb": "AssumeRole"},
        {"verb": "ListBuckets"},
        {"verb": "PutRolePolicy"},
    ]
    anchor = lib.load_attack_episode(
        source_id="attack_data",
        record={"family": "aws-priv-esc"},
        techniques=("T1078",),
        logs=logs,
        action_of=lambda log: log["verb"],
    )
    assert anchor.behavioural_series is not None
    assert anchor.behavioural_series.is_multi_log
    assert anchor.behavioural_series.n_logs == 3
    assert "auth" in anchor.behavioural_series.spine


def test_load_attack_episode_single_log_series_is_flagged_thin() -> None:
    lib = AnchorLibrary()
    anchor = lib.load_attack_episode(
        source_id="attack_data",
        record={"family": "x"},
        logs=[{"verb": "AssumeRole"}],
        action_of=lambda log: log["verb"],
    )
    assert anchor.behavioural_series is not None
    assert anchor.behavioural_series.is_multi_log is False


def test_load_attack_episode_without_logs_carries_no_series() -> None:
    lib = AnchorLibrary()
    anchor = lib.load_attack_episode(source_id="attack_data", record={"family": "x"})
    assert anchor.behavioural_series is None


def test_grade_series_for_loop_maps_exact_cousin_novel_none_to_relationships() -> None:
    known = BehaviouralSeries(
        series_id="known-1", spine=("auth", "enumerate", "escalate", "collect"), n_logs=4
    )
    exact_observed = BehaviouralSeries(
        series_id="obs-exact", spine=("auth", "enumerate", "escalate", "collect"), n_logs=4
    )
    cousin_observed = BehaviouralSeries(
        series_id="obs-cousin",
        spine=("auth", "enumerate", "lateral", "escalate", "collect"),
        n_logs=5,
    )
    novel_observed = BehaviouralSeries(
        series_id="obs-novel", spine=("persist", "evade", "c2_exfil"), n_logs=3
    )

    exact_grade = loop_grader.grade_series_for_loop(exact_observed, [known])
    assert exact_grade.relationship == "SAME"

    cousin_grade = loop_grader.grade_series_for_loop(cousin_observed, [known])
    assert cousin_grade.relationship == "SIMILAR"

    novel_grade = loop_grader.grade_series_for_loop(novel_observed, [known])
    assert novel_grade.relationship == "ANOMALOUS_UNCLASSIFIED"


def test_grade_series_for_loop_blank_spine_is_anomalous_unclassified_indeterminate() -> None:
    blank = BehaviouralSeries(series_id="obs-blank", spine=(), n_logs=1)
    grade = loop_grader.grade_series_for_loop(blank, [])
    assert grade.relationship == "ANOMALOUS_UNCLASSIFIED"
    assert grade.defense_response == "INDETERMINATE"


def test_build_cousin_assessment_from_series_emits_valid_dto() -> None:
    """R.6 wiring: build_cousin_assessment_from_series is what the milestone
    run script uses to record a series-alignment grade through the SAME
    CousinAssessment DTO orchestrator._analyzing emits."""
    from portal.modules.security.core.bully import signatures as signatures_mod

    known = BehaviouralSeries(
        series_id="known-1", spine=("auth", "enumerate", "escalate", "collect"), n_logs=4
    )
    observed = BehaviouralSeries(
        series_id="obs-1", spine=("auth", "enumerate", "lateral", "escalate", "collect"), n_logs=5
    )
    sig = signatures_mod.build_signature(
        {"episode_id": "ep-1"}, {"action_sequence": list(observed.spine)}
    )
    assessment = loop_grader.build_cousin_assessment_from_series(sig, observed, [known])
    assert assessment.relationship == "SIMILAR"
    assert assessment.nonsemantic_channels >= 2
    assert assessment.explanation["grader"] == "loop-grader-v1"
