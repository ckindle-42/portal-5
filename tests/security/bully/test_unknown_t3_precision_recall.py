"""T.3 -- precision and recall per level, per outcome (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_measurement as um
from portal.modules.security.core.bully import unit_outcome as uo


def _unit(verbs: list[str], entity: str, level: str = "L4_WINDOW") -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


def test_known_instance_reported_separately_as_floor_never_headline():
    library = anc.AnchorLibrary()
    library.load_detection_coverage(source_id="det", detection_id="det-1")
    library._anchors["det-1"].record.update({"action_sequence": ["AssumeRole", "ListBuckets"]})
    baseline = bl.NormalBaseline(environment_id="e")

    outcome = uo.resolve_unit_outcome(
        _unit(["AssumeRole", "ListBuckets"], "u1"), list(library.all()), baseline
    )
    row = um.bind_ground_truth(outcome, family="T1078", malice="malicious")
    report = um.precision_recall_report([row])

    assert report["known_instance_floor"]["floor_metric"] is True
    assert report["known_instance_floor"]["count"] == 1
    assert "known_instance_floor" not in report["overall"]


def test_precision_and_recall_computed_over_scored_rows_only():
    baseline = bl.NormalBaseline(environment_id="e")
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "AttachUserPolicy"]},
        techniques=("T1078",),
    )

    hit = uo.resolve_unit_outcome(
        _unit(["AssumeRole", "AttachUserPolicy"], "u1"), list(library.all()), baseline
    )
    miss = uo.resolve_unit_outcome(_unit(["ListBuckets"], "u2", level="L1_ARTIFACT"), [], baseline)
    rows = [
        um.bind_ground_truth(hit, family="T1078", malice="malicious"),
        um.bind_ground_truth(miss, family="T1078", malice="malicious"),
        um.bind_ground_truth(miss, family=None, malice="unknown"),  # unscored, excluded
    ]
    report = um.precision_recall_report(rows)
    assert report["scored_count"] == 2
    assert report["unscored_count"] == 1
    assert report["overall"]["recall"] == 0.5


def test_per_level_breakdown_present():
    baseline = bl.NormalBaseline(environment_id="e")
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="a", record={"action_sequence": ["ListBuckets"]}, techniques=("T1078",)
    )
    l1_unit = _unit(["ListBuckets"], "u1", level="L1_ARTIFACT")
    outcome = uo.resolve_unit_outcome(l1_unit, list(library.all()), baseline)
    row = um.bind_ground_truth(outcome, family="T1078", malice="malicious")
    report = um.precision_recall_report([row])
    assert "L1_ARTIFACT" in report["per_level"]
