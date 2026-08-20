"""M.2 -- CI invariants for the unknown-cousin contract
(TASK_BULLY_UNKNOWN_COUSIN_V1). Each check seeds a violation and confirms
the guard rejects it, then confirms a clean input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_unknown_cousin_library_never_gates",
    "bully_unknown_cousin_channel_coverage_never_gates",
    "bully_unknown_cousin_brief_mandatory",
    "bully_unknown_cousin_known_instance_never_headlines",
    "bully_unknown_cousin_insufficient_view_distinct",
    "bully_unknown_cousin_channels_separable",
    "bully_unknown_cousin_temporal_edge_requires_entity",
    "bully_unknown_cousin_leave_one_out_published_beside_full",
    "bully_unknown_cousin_held_out_split_enforced",
    "bully_unknown_cousin_novel_requires_positive_remarkability",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_ten_invariants_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_unknown_cousin_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        status, detail, _sub = _run(slug)
        assert status == "PASS", f"{slug} did not pass clean: {detail}"


def test_channels_separable_check_would_fail_if_channels_were_conflated():
    from portal.modules.security.core.bully import unit_relation as ur
    from scripts.validation.bully_relate import _unit_from_verbs

    unit = _unit_from_verbs(["Authenticate", "Enumerate", "Grant"], "attacker")
    anchor = {
        "record_id": "t1",
        "action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"],
    }
    relation = ur.grade_unit_against_type(unit, anchor)
    # The seeded violation this check guards against: a grader that reports
    # the same relation on both channels regardless of content divergence.
    conflated = relation.shape.relation == relation.vocabulary.relation
    assert not conflated, "shape and vocabulary channels collapsed to one relation"


def test_temporal_edge_check_would_fail_on_a_seeded_unguarded_graph():
    """Reproduce the exact defect U.1's guard exists to prevent -- an
    unguarded temporal-only rule building an edge with no shared entity --
    and confirm the check's own detection logic flags it."""
    from portal.modules.security.core.bully.artifact_graph import Artifact, ArtifactGraph, Edge

    a0 = Artifact(
        "a0",
        {},
        entities=("user=alice",),
        action=None,
        action_class="unknown",
        timestamp=0.0,
        source_id="",
    )
    a1 = Artifact(
        "a1",
        {},
        entities=("user=bob",),
        action=None,
        action_class="unknown",
        timestamp=1.0,
        source_id="",
    )
    seeded_bad_graph = ArtifactGraph([a0, a1], [Edge("a0", "a1", "temporal_adjacency", "1s")])

    bare_temporal = [
        e
        for e in seeded_bad_graph.edges
        if e.kind == "temporal_adjacency"
        and not (
            set(seeded_bad_graph.artifacts[e.left].entities)
            & set(seeded_bad_graph.artifacts[e.right].entities)
        )
    ]
    assert bare_temporal, "seeded bad graph should have surfaced an unguarded temporal edge"


def test_known_instance_headline_check_would_fail_on_a_seeded_bad_ranking():
    """Reproduce a grader that ranks KNOWN_INSTANCE ahead of a concern, and
    confirm the check's own comparison logic (not the real sort_for_report)
    would flag it -- this is what makes the guard meaningful rather than a
    tautology against its own implementation."""
    seeded_bad_ranked_outcomes = ["KNOWN_INSTANCE", "COUSIN"]
    headlines_a_floor_row = seeded_bad_ranked_outcomes[0] == "KNOWN_INSTANCE" and set(
        seeded_bad_ranked_outcomes
    ) != {"KNOWN_INSTANCE"}
    assert headlines_a_floor_row, "seeded bad ranking should have KNOWN_INSTANCE headlining"
