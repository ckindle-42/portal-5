"""C.6 -- the constructed-cousin ladder: truth by construction, with
falsification controls (N5). Uses a small synthetic anchor library (not the
live attack_data plane, which scripts/bully_cousin_ladder.py's __main__
connects to) so this suite stays fast, deterministic, and network-free."""

from __future__ import annotations

import dataclasses

from scripts.bully_cousin_ladder import build_rungs, run_ladder, run_old_engine_arm


def _synthetic_anchors(n_boilerplate: int = 20) -> list[dict]:
    anchors = [
        {
            "record_id": f"boilerplate-{i}",
            "action_sequence": ["whoami", "net user", "ipconfig"],
            "telemetry_shape": {"source_class": "windows"},
            "context_topology": {"os": "windows"},
            "attack_mappings": [{"technique_id": "T1087"}],
        }
        for i in range(n_boilerplate)
    ]
    for j in range(12):
        anchors.append(
            {
                "record_id": f"parent-{j}",
                # A Windows-flavoured parent (same telemetry/context family
                # as the boilerplate anchors) so build_rungs' L3 rung --
                # which re-expresses behaviour under cloudtrail/aws
                # telemetry/context -- is a genuine cross-space departure
                # from this parent's own telemetry/context axes, not an
                # accidental match. "AssumeRole" (shared by every parent,
                # absent from the boilerplate anchors) is the L3 motif --
                # distinctive relative to the corpus but not uniquely
                # identifying one parent.
                "action_sequence": [
                    "AssumeRole",
                    f"reg_query-{j}",
                    "proc_create",
                    "net_connect",
                    "file_write",
                    "scheduled_task",
                    "service_create",
                    "token_impersonate",
                ],
                "telemetry_shape": {"source_class": "windows"},
                "context_topology": {"os": "windows"},
                "attack_mappings": [{"technique_id": f"T1078.{j:03d}"}],
            }
        )
    return anchors


def _parents(anchors: list[dict]) -> list[dict]:
    return [a for a in anchors if a["record_id"].startswith("parent-")]


def test_build_rungs_produces_five_levels_with_correct_parent_id():
    anchors = _synthetic_anchors()
    parent = _parents(anchors)[0]
    rungs = build_rungs(parent, rung_seed=0)
    assert [r.level for r in rungs] == [0, 1, 2, 3, 4]
    assert all(r.parent_anchor_id == parent["record_id"] for r in rungs)


def test_l0_identity_grades_exact_zero_distance():
    """L0 must be an exact self-match: distance 0.0 against its own
    parent -- a synthetic target_host leaking into context_topology would
    silently break this (the C.6 build-time bug this test pins)."""
    anchors = _synthetic_anchors()
    parents = _parents(anchors)
    report = run_ladder(anchors, parents=parents, seed=0)
    l0_rows = [r for r in report["rung_records"] if r["level"] == 0]
    assert l0_rows
    assert all(r["distance"] == 0.0 for r in l0_rows)
    assert all(r["ranked_cousins"][0][0] == r["parent_anchor_id"] for r in l0_rows)


def test_ladder_monotonicity_and_l3_recovery_on_synthetic_corpus():
    anchors = _synthetic_anchors()
    parents = _parents(anchors)
    report = run_ladder(anchors, parents=parents, seed=0)
    assert report["mean_parent_rho"] is not None
    assert report["mean_parent_rho"] >= 0.9
    assert report["valid"] is True
    assert report["negative_control_holds"] is True


def test_shuffled_anchor_control_collapses_correlation():
    anchors = _synthetic_anchors()
    parents = _parents(anchors)
    report = run_ladder(anchors, parents=parents, seed=0)
    assert report["shuffled_rho"] is None or abs(report["shuffled_rho"]) < 0.5
    assert report["shuffle_collapsed"] is True


def test_negative_control_l4_never_claims_its_own_parent():
    anchors = _synthetic_anchors()
    parents = _parents(anchors)
    report = run_ladder(anchors, parents=parents, seed=0)
    l4_rows = [r for r in report["rung_records"] if r["level"] == 4]
    assert l4_rows
    assert not any(
        r["status"] == "COUSIN_CANDIDATE" and r["matched_anchor_id"] == r["parent_anchor_id"]
        for r in l4_rows
    )


def test_broken_grader_turns_the_report_invalid():
    """N5: deliberately break the grader (force distance=0.0 for every
    pair) and confirm the report turns INVALID -- a report that can only
    ever say VALID is not a verification."""
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _synthetic_anchors()
    parents = _parents(anchors)

    orig = cr.relate_cousin

    def broken(subject, anchor_records, **kwargs):
        rel = orig(subject, anchor_records, **kwargs)
        return dataclasses.replace(rel, distance=0.0 if rel.distance is not None else None)

    cr.relate_cousin = broken
    try:
        report = run_ladder(anchors, parents=parents, seed=0)
    finally:
        cr.relate_cousin = orig

    # Forcing every distance to 0.0 collapses the level/distance variance
    # entirely -- rho becomes undefined (no variance in y), so monotonicity
    # cannot be confirmed and the report must not claim VALID.
    assert report["valid"] is False


def test_old_engine_arm_runs_and_reports_whatever_actually_happens():
    """C.6 requires recording the old engine's real outcome distribution,
    not assuming it -- this just confirms the arm executes end-to-end and
    returns a well-formed report over relation.relate, the untouched
    provoked grader."""
    anchors = _synthetic_anchors()
    parents = _parents(anchors)
    report = run_old_engine_arm(anchors, parents=parents)
    assert report["outcome_distribution"]
    assert sum(report["outcome_distribution"].values()) == len(parents) * 5
    assert report["l3_recovery_rate"] is not None
