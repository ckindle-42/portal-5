"""U.2 -- unit signature: shape apart from vocabulary (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag


def _chain(base_time: float, verbs: list[str], entity_field: str, entity_value: str) -> list[dict]:
    return [
        {"eventName": v, entity_field: entity_value, "eventTime": base_time + i * 40.0}
        for i, v in enumerate(verbs)
    ]


def test_projection_keeps_shape_and_vocabulary_in_separate_fields():
    base_time = 1_700_000_000.0
    records = _chain(base_time, ["AssumeRole", "ListBuckets", "AttachUserPolicy"], "user", "u1")
    graph = ag.build_graph(records)
    unit = next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    projection = unit.grading_projection()

    assert projection.event_graph == unit.structural_signature
    assert projection.action_sequence == unit.vocabulary
    assert set(projection.event_graph) & set(projection.action_sequence) == set()
    assert projection.attack_mappings == ()


def test_shape_channel_identical_when_class_sequences_align_despite_disjoint_vocabulary():
    base_time = 1_700_000_000.0
    aws = _chain(base_time, ["AssumeRole", "ListBuckets"], "user", "attacker")
    equivalent_verbs = _chain(base_time, ["Authenticate", "Enumerate"], "user", "attacker")

    aws_unit = next(u for u in ag.enumerate_units(ag.build_graph(aws)) if u.level == "L4_WINDOW")
    equiv_unit = next(
        u for u in ag.enumerate_units(ag.build_graph(equivalent_verbs)) if u.level == "L4_WINDOW"
    )

    aws_proj = aws_unit.grading_projection()
    equiv_proj = equiv_unit.grading_projection()

    assert set(aws_proj.action_sequence).isdisjoint(set(equiv_proj.action_sequence))
    assert aws_proj.event_graph["class_sequence"] == equiv_proj.event_graph["class_sequence"]


def test_projection_never_carries_attack_mappings_as_input():
    base_time = 1_700_000_000.0
    records = _chain(base_time, ["Logon", "PutObject"], "host", "h1")
    graph = ag.build_graph(records)
    unit = next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")
    assert unit.grading_projection().attack_mappings == ()
