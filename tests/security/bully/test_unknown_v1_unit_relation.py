"""V.1 -- three-way unit-vs-type grading on shape and vocabulary channels
(TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import unit_relation as ur


def _unit_from_chain(
    verbs: list[str], entity_value: str, base_time: float = 0.0
) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity_value, "eventTime": base_time + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    level = "L1_ARTIFACT" if len(records) < 2 else "L4_WINDOW"
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


def test_identical_chain_grades_exact_on_both_channels():
    verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    unit = _unit_from_chain(verbs, "attacker")
    anchor = {
        "record_id": "type-1",
        "action_sequence": verbs,
        "parameter_families": list(unit.entities),
    }
    relation = ur.grade_unit_against_type(unit, anchor)
    assert relation.shape.relation == "EXACT"
    assert relation.vocabulary.relation == "EXACT"
    assert relation.overall_relation == "EXACT"


def test_same_shape_disjoint_vocabulary_still_matches_on_shape_channel():
    """The flagship case: a new-tooling instance of a known type. Vocabulary
    is unrecognisable; the classifier bridges the verbs to the same class
    shape, so the shape channel still reads EXACT/SIMILAR."""
    known_verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    unseen_verbs = ["Authenticate", "Enumerate", "AddRole"]
    unit = _unit_from_chain(unseen_verbs, "attacker")
    anchor = {"record_id": "type-1", "action_sequence": known_verbs}

    relation = ur.grade_unit_against_type(unit, anchor)

    assert set(unit.vocabulary).isdisjoint(set(known_verbs))
    assert relation.vocabulary.relation == "NOT_AT_ALL"
    assert relation.shape.relation in ("EXACT", "SIMILAR")
    assert relation.overall_relation in ("EXACT", "SIMILAR")
    assert relation.delta["axis_of_divergence"] == "vocabulary"


def test_unrelated_unit_grades_not_at_all_on_both_channels():
    unit = _unit_from_chain(["ListBuckets"], "benign-user")
    anchor = {
        "record_id": "type-ransomware",
        "action_sequence": ["encrypt_files", "delete_shadow_copies", "drop_ransom_note"],
    }
    relation = ur.grade_unit_against_type(unit, anchor)
    assert relation.shape.relation == "NOT_AT_ALL"
    assert relation.vocabulary.relation == "NOT_AT_ALL"
    assert relation.overall_relation == "NOT_AT_ALL"


def test_empty_side_is_unobservable_never_a_penalty():
    unit = _unit_from_chain(["ListBuckets"], "u1")
    anchor: dict = {"record_id": "type-empty"}
    relation = ur.grade_unit_against_type(unit, anchor)
    assert relation.vocabulary.unobservable
    assert relation.vocabulary.distance is None
    assert relation.vocabulary.relation == "NOT_AT_ALL"


def test_delta_is_always_present():
    unit = _unit_from_chain(["ListBuckets"], "u1")
    anchor = {"record_id": "t1", "action_sequence": ["ListBuckets"]}
    relation = ur.grade_unit_against_type(unit, anchor)
    assert relation.delta
    assert "shared_vocabulary_features" in relation.delta


def test_grade_unit_against_library_grades_every_type_no_gate():
    unit = _unit_from_chain(["ListBuckets"], "u1")
    library = [
        {"record_id": "weak-type"},  # no label_basis-equivalent content, never skipped
        {"record_id": "matching-type", "action_sequence": ["ListBuckets"]},
    ]
    relations = ur.grade_unit_against_library(unit, library)
    assert len(relations) == 2
    assert {r.anchor_id for r in relations} == {"weak-type", "matching-type"}
