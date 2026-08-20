"""R.2 -- loop grader maps pyramid-levelled relations to CousinAssessment vocab."""

from __future__ import annotations

from portal.modules.security.core.bully import loop_grader, pyramid
from portal.modules.security.core.bully.contracts import RELATIONSHIPS, RESPONSES


def _feat(token: str, role: str, raw_verb: str | None = None) -> pyramid.LeveledFeature:
    return pyramid.level_feature(token, role, raw_verb=raw_verb)


def test_cross_vocab_cousin_grades_similar_at_l3_robustness_one() -> None:
    subj = [
        _feat("a1", "ACTION", raw_verb="GetSessionToken"),
        _feat("a2", "ACTION", raw_verb="ListBuckets"),
        _feat("a3", "ACTION", raw_verb="PutRolePolicy"),
    ]
    anchor = [
        _feat("b1", "ACTION", raw_verb="kerberos tgt request"),
        _feat("b2", "ACTION", raw_verb="net user /domain"),
        _feat("b3", "ACTION", raw_verb="secretsdump"),
    ]
    grade = loop_grader.grade_for_loop(subj, "anchor-1", anchor, distance=0.45)
    assert grade.relationship == "SIMILAR"
    assert grade.relationship in RELATIONSHIPS
    assert grade.match_level == pyramid.L3_BEHAVIOR
    assert grade.robustness == 1.0


def test_tiny_distance_behaviour_grades_same() -> None:
    subj = [
        _feat("a1", "ACTION", raw_verb="assumerole"),
        _feat("a2", "ACTION", raw_verb="listbuckets"),
    ]
    anchor = [
        _feat("b1", "ACTION", raw_verb="assumerole"),
        _feat("b2", "ACTION", raw_verb="listbuckets"),
    ]
    grade = loop_grader.grade_for_loop(subj, "anchor-2", anchor, distance=0.05)
    assert grade.relationship == "SAME"
    assert grade.match_level == pyramid.L3_BEHAVIOR


def test_behaviour_matches_nothing_grades_anomalous_unclassified() -> None:
    subj = [
        _feat("a1", "ACTION", raw_verb="assumerole"),
        _feat("a2", "ACTION", raw_verb="listbuckets"),
    ]
    grade = loop_grader.grade_for_loop(subj, None, None, distance=None)
    assert grade.relationship == "ANOMALOUS_UNCLASSIFIED"
    assert grade.defense_response in RESPONSES
    assert grade.defense_response != "INDETERMINATE"


def test_blind_no_features_yields_anomalous_unclassified_indeterminate_never_different() -> None:
    """Seeded violation guard: instrument blindness must never surface as a
    false DIFFERENT (Q1)."""
    grade = loop_grader.grade_for_loop([], None, None, distance=None)
    assert grade.relationship == "ANOMALOUS_UNCLASSIFIED"
    assert grade.defense_response == "INDETERMINATE"
    assert grade.relationship != "DIFFERENT"


def test_fragile_sourcetype_only_match_is_new_not_a_behaviour_cousin() -> None:
    subj = [_feat("sourcetype=x", "CONSTANT")]
    anchor = [_feat("sourcetype=x", "CONSTANT")]
    grade = loop_grader.grade_for_loop(subj, "anchor-3", anchor, distance=0.2)
    assert grade.relationship == "NEW"
    assert grade.match_level == pyramid.L1_EPHEMERAL
    assert grade.relationship != "SAME"
    assert grade.relationship != "SIMILAR"


def test_same_only_ever_arises_from_l3_behavioural_match() -> None:
    """Seeded violation guard: no matter how close the distance, an L1/L2-only
    agreement must never be graded SAME."""
    subj = [_feat("sourcetype=x", "CONSTANT")]
    anchor = [_feat("sourcetype=x", "CONSTANT")]
    grade = loop_grader.grade_for_loop(subj, "anchor-4", anchor, distance=0.0)
    assert grade.relationship != "SAME"
