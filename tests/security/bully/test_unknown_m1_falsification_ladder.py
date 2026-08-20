"""M.1 -- combination-level falsification ladder (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_ladder as ul
from portal.modules.security.core.bully import unit_relation as ur

_PARENT_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
_PARENT_TYPE = {"record_id": "parent-type", "action_sequence": _PARENT_VERBS}


def _rungs() -> list[ul.Rung]:
    return ul.build_rungs(
        _PARENT_VERBS,
        # Classifies to "escalate", same as the verb it replaces
        # (AttachUserPolicy) -- a one-step *content* change that leaves the
        # class shape untouched, smaller than L2's full reorder.
        substitution_verb="AddRole",
        # Both classify to [auth, enumerate, escalate] under the
        # deterministic table, disjoint literal vocabulary from the parent.
        cross_vocabulary_verbs=["Authenticate", "Enumerate", "Grant"],
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )


def test_ladder_is_monotonic_and_valid():
    report = ul.run_ladder(_PARENT_TYPE, _rungs())
    assert report["verdict"] == "VALID"
    assert report["monotonicity_valid"]
    assert report["rho"] is not None
    assert report["rho"] >= ul.RHO_MONOTONICITY_FLOOR


def test_shuffle_control_collapses_correlation():
    report = ul.run_ladder(_PARENT_TYPE, _rungs())
    assert report["shuffle_collapsed"]


def test_negative_control_unrelated_rung_is_farthest():
    report = ul.run_ladder(_PARENT_TYPE, _rungs())
    assert report["negative_control_holds"]
    assert report["per_rung"]["L4_UNRELATED"]["overall_relation"] == "NOT_AT_ALL"


def test_identity_rung_grades_exact():
    report = ul.run_ladder(_PARENT_TYPE, _rungs())
    assert report["per_rung"]["L0_IDENTITY"]["combined_distance"] < 0.2


def test_cross_vocabulary_rung_still_shows_shape_signal():
    """The U.3 seam's payoff, made visible: shape distance stays low even
    though the vocabulary is entirely disjoint."""
    report = ul.run_ladder(_PARENT_TYPE, _rungs())
    l3 = report["per_rung"]["L3_CROSS_VOCABULARY"]
    assert l3["shape_distance"] is not None
    assert l3["shape_distance"] < 0.6
    assert l3["vocabulary_distance"] is None or l3["vocabulary_distance"] > 0.6


def test_seeded_violation_broken_grader_turns_report_invalid():
    def _broken_grade_fn(unit, anchor_record, *, classifier=None):
        return ur.grade_unit_against_type(unit, {"record_id": "always-empty"})

    report = ul.run_ladder(_PARENT_TYPE, _rungs(), grade_fn=_broken_grade_fn)
    assert report["verdict"] == "INVALID"


def test_individually_normal_combination_surfaces_as_a_concern():
    library = anc.AnchorLibrary()
    baseline = bl.NormalBaseline(environment_id="e")

    chain_verbs = [
        "AssumeRole",
        "GetSessionToken",
        "AttachUserPolicy",
        "PutBucketPolicy",
        "DeleteBucket",
        "PutObject",
    ]

    def _l1(verbs: list[str], entity: str):
        records = [{"eventName": v, "user": entity, "eventTime": 0.0} for v in verbs]
        graph = ag.build_graph(records)
        return next(u for u in ag.enumerate_units(graph) if u.level == "L1_ARTIFACT")

    # Each verb individually is common in this environment -- fit L1 units
    # for every one of them, across many entities, so no single artifact is
    # remarkable on its own. Never fit the 6-step *combination* itself.
    fit_units = []
    for verb in chain_verbs:
        for i in range(20):
            fit_units.append(_l1([verb], f"benign-{verb}-{i}"))
    baseline.fit(fit_units)

    result = ul.individually_normal_case_surfaces(chain_verbs, library=library, baseline=baseline)
    assert result["passes"], result
