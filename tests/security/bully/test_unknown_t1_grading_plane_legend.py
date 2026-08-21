"""T.1 -- legend bound on the grading plane (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_measurement as um
from portal.modules.security.core.bully import unit_outcome as uo

_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]


def _unit() -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": "attacker", "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(_VERBS)
    ]
    graph = ag.build_graph(records)
    return next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")


def test_scored_means_legend_knows_not_merely_reachable():
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _VERBS}, techniques=("T1078",)
    )
    # D.2, discovery-first: a library match alone no longer surfaces a
    # concern (D1) -- fit an unrelated benign L4_WINDOW shape so the probe
    # is remarkable for a reason other than an empty baseline.
    model = bl.NormalBaseline(environment_id="e")
    benign_cycle = ["ListBuckets", "GetObject", "DescribeInstances"]

    def _benign(entity: str) -> ag.GradeableUnit:
        records = [
            {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
            for i, v in enumerate(benign_cycle[: len(_VERBS)])
        ]
        graph = ag.build_graph(records)
        return next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    model.fit([_benign(f"benign-{i}") for i in range(50)])
    outcome = uo.resolve_unit_outcome(_unit(), list(library.all()), model)
    assert outcome.outcome == "UNKNOWN_SAME"

    unscored_row = um.bind_ground_truth(outcome, family=None, malice="unknown")
    assert not unscored_row.scored

    scored_row = um.bind_ground_truth(outcome, family="T1078", malice="malicious")
    assert scored_row.scored
    assert scored_row.correct


def test_malicious_family_graded_normal_is_incorrect():
    outcome = uo.resolve_unit_outcome(_unit(), [], bl.NormalBaseline(environment_id="e"))
    assert outcome.outcome == "NORMAL"
    row = um.bind_ground_truth(outcome, family="T1078", malice="malicious")
    assert row.scored
    assert not row.correct


def test_benign_family_graded_normal_is_correct():
    outcome = uo.resolve_unit_outcome(_unit(), [], bl.NormalBaseline(environment_id="e"))
    row = um.bind_ground_truth(outcome, family=None, malice="benign")
    assert row.scored
    assert row.correct


def test_unscored_row_is_never_counted_correct():
    outcome = uo.resolve_unit_outcome(_unit(), [], bl.NormalBaseline(environment_id="e"))
    row = um.bind_ground_truth(outcome, family=None, malice="unknown")
    assert not row.scored
    assert not row.correct
