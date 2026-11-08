"""V.1 -- three-way unit-vs-type grading on shape and vocabulary channels
(TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from dataclasses import replace

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_relation as ur


def _unit_from_chain(
    verbs: list[str], entity_value: str, base_time: float = 1_700_000_000.0
) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity_value, "eventTime": base_time + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    level = "L1_ARTIFACT" if len(records) < 2 else "L4_WINDOW"
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


def test_unclassified_gap_matches_anchor_on_classified_projection():
    unit = _unit_from_chain(["AssumeRole", "ListBuckets"], "attacker")
    unit = replace(
        unit,
        structural_signature={
            **unit.structural_signature,
            "class_sequence": ["auth", "", "enumerate"],
        },
    )
    anchor = {
        "record_id": "type-1",
        "event_graph": {"class_sequence": ["auth", "enumerate"]},
    }

    relation = ur.grade_unit_against_type(unit, anchor)

    assert relation.shape.distance == 0.0
    assert relation.shape.relation == "EXACT"
    assert relation.overall_relation == "EXACT"
    assert not relation.shape.diverging_tokens
    baseline_tokens = bl._feature_tokens(unit)
    assert "class_bigram=auth>enumerate" in baseline_tokens
    assert not any(token.startswith("class_present=") for token in baseline_tokens)
    assert "class_bigram=auth>" not in baseline_tokens
    assert "class_bigram=>enumerate" not in baseline_tokens
    empty_unit = replace(
        unit,
        structural_signature={**unit.structural_signature, "class_sequence": [""]},
    )
    assert not ur.unit_shape_tokens(empty_unit)
    assert not any(token.startswith("class_") for token in bl._feature_tokens(empty_unit))


def test_provenance_and_window_local_entities_do_not_change_same_shape_grade():
    unit = _unit_from_chain(["AssumeRole", "ListBuckets"], "attacker")
    unit = replace(
        unit,
        structural_signature={
            **unit.structural_signature,
            "class_sequence": ["auth", "enumerate"],
        },
        vocabulary=("XmlWinEventLog:Security", "XmlWinEventLog"),
        entities=("entity=ent-1111111111",),
        provenance_tokens=(
            "XmlWinEventLog:Security",
            "source=XmlWinEventLog:Security",
            "XmlWinEventLog",
            "sourcetype=XmlWinEventLog",
        ),
    )
    anchor = {
        "record_id": "cross-source-type",
        "source": "Sysmon:Operational",
        "sourcetype": "sysmon:linux",
        "action_sequence": ["Sysmon:Operational", "sysmon:linux"],
        "parameter_families": ["entity=ent-2222222222"],
        "event_graph": {"class_sequence": ["auth", "enumerate"]},
    }

    relation = ur.grade_unit_against_type(unit, anchor)

    assert relation.shape.distance == 0.0
    assert relation.overall_relation == "EXACT"
    assert relation.algorithm_version == "unit-relation-v3"
    assert relation.vocabulary.unobservable
    assert not ur.unit_vocabulary_tokens(unit)
    assert not ur._type_vocabulary_tokens(anchor)


def test_artifact_graph_carries_source_metadata_as_nonbehavioral_provenance():
    records = [
        {
            "eventName": verb,
            "source": "XmlWinEventLog:Security",
            "sourcetype": "XmlWinEventLog",
            "user": "attacker",
            "eventTime": 1_700_000_000.0 + i * 40.0,
        }
        for i, verb in enumerate(("AssumeRole", "ListBuckets"))
    ]
    graph = ag.build_graph(records)
    unit = next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    assert "XmlWinEventLog:Security" in unit.provenance_tokens
    assert "sourcetype=XmlWinEventLog" in unit.provenance_tokens


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
