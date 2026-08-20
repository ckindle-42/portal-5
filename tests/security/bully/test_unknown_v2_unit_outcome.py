"""V.2 -- unit outcome and the concern brief (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_outcome as uo

_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]


def _unit(verbs: list[str], entity: str) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    level = "L1_ARTIFACT" if len(records) < 2 else "L4_WINDOW"
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


def _empty_baseline() -> bl.NormalBaseline:
    return bl.NormalBaseline(environment_id="test")


def test_exact_match_to_detection_coverage_is_known_instance_floor():
    library = anc.AnchorLibrary()
    library.load_detection_coverage(source_id="det", detection_id="det-1", techniques=("T1078",))
    library._anchors["det-1"].record.update({"action_sequence": _VERBS})
    unit = _unit(_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), _empty_baseline())
    assert outcome.outcome == "KNOWN_INSTANCE"
    assert outcome.brief is None


def test_exact_match_to_attack_episode_is_unknown_same_a_concern():
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _VERBS}, techniques=("T1078",)
    )
    unit = _unit(_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), _empty_baseline())
    assert outcome.outcome == "UNKNOWN_SAME"
    assert outcome.outcome in uo.CONCERN_OUTCOMES
    assert outcome.brief is not None


def test_similar_but_not_exact_match_is_cousin_a_concern():
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "ListBuckets", "DeleteBucket"]},
        techniques=("T1078",),
    )
    unit = _unit(_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), _empty_baseline())
    assert outcome.outcome in ("COUSIN", "UNKNOWN_SAME")
    assert outcome.brief is not None


def test_benign_pattern_match_is_recognized_normal_and_suppressed():
    library = anc.AnchorLibrary()
    library.load_benign_pattern(
        source_id="corpus", record={"action_sequence": _VERBS}, recurrence_count=10
    )
    unit = _unit(_VERBS, "someone")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), _empty_baseline())
    assert outcome.outcome == "RECOGNIZED_NORMAL"
    assert outcome.outcome not in uo.CONCERN_OUTCOMES


def test_no_match_and_unremarkable_is_normal_and_silent():
    unit = _unit(["ListBuckets"], "u1")
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
    outcome = uo.resolve_unit_outcome(unit, [], model)
    assert outcome.outcome == "NORMAL"
    assert outcome.brief is None


def test_no_match_but_remarkable_is_novel_a_concern():
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
    unit = _unit(_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, [], model)
    assert outcome.outcome == "NOVEL"
    assert outcome.brief is not None


def test_uncomputable_unit_is_insufficient_view_never_novel():
    empty_unit = ag.GradeableUnit(
        unit_id="u-empty",
        level="L1_ARTIFACT",
        artifact_ids=("a0",),
        entities=(),
        action_classes=(),
        edge_kinds=(),
        span_seconds=None,
        structural_signature={},
        vocabulary=(),
        source_ids=(),
    )
    outcome = uo.resolve_unit_outcome(empty_unit, [], _empty_baseline())
    assert outcome.outcome == "INSUFFICIENT_VIEW"
    assert outcome.outcome != "NOVEL"


def test_seeded_known_instance_never_ranks_above_cousin_or_novel():
    """M.2 invariant #4 / P1: KNOWN_INSTANCE must never headline."""
    library = anc.AnchorLibrary()
    library.load_detection_coverage(source_id="det", detection_id="det-1")
    library._anchors["det-1"].record.update({"action_sequence": _VERBS})
    known_unit = _unit(_VERBS, "known-attacker")
    known_outcome = uo.resolve_unit_outcome(known_unit, list(library.all()), _empty_baseline())
    assert known_outcome.outcome == "KNOWN_INSTANCE"

    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
    novel_unit = _unit(["AssumeRole", "GetSessionToken", "PutBucketPolicy"], "novel-attacker")
    novel_outcome = uo.resolve_unit_outcome(novel_unit, [], model)
    assert novel_outcome.outcome == "NOVEL"

    ranked = uo.sort_for_report([known_outcome, novel_outcome])
    assert ranked[0].outcome != "KNOWN_INSTANCE"
    assert ranked[-1].outcome == "KNOWN_INSTANCE"
