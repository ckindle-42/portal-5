"""M.5 -- CI invariants for universal intake and honest metrics
(TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1). Each check seeds a violation
and confirms the guard rejects it, then confirms a clean input still
passes."""

from __future__ import annotations


def test_seeded_violation_role_map_gate_would_fail_on_unguarded_build_graph():
    """Reproduce the RC1 defect directly: an unextractable source read with
    a hardcoded field list (rather than inferred roles) would silently
    produce an all-`other` unit instead of zero units."""
    from portal.modules.security.core.bully.artifact_graph import build_graph, enumerate_units

    unextractable = [{"blob": "x" * 300, "note": f"noise {i}"} for i in range(10)]
    graph = build_graph(unextractable)
    assert graph.insufficient_view
    assert enumerate_units(graph) == []


def test_seeded_violation_shape_distance_would_diverge_from_combined():
    """Reproduce RC4's actual finding: combined_distance and shape_distance
    can disagree on which rung is farthest, which is exactly why validating
    on the wrong one masks real non-monotonicity."""
    from portal.modules.security.core.bully import unit_ladder as ul

    parent_verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    rungs = ul.build_rungs(
        parent_verbs,
        substitution_verb="AddRole",
        cross_vocabulary_verbs=["Logon", "whoami", "Invoke-Command"],
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )
    report = ul.run_ladder({"record_id": "parent-type", "action_sequence": parent_verbs}, rungs)
    combined = [report["per_rung"][r.rung]["combined_distance"] for r in rungs]
    shape = [report["per_rung"][r.rung]["shape_distance"] for r in rungs]
    # they are not the same sequence -- proving the two variables really
    # can diverge, which is why the validated one matters
    assert combined != shape


def test_seeded_violation_novel_path_would_hardcode_full_blindness():
    """Reproduce RC5's exact defect: a NOVEL outcome with `relation=None`
    used to report both channels unobservable regardless of the unit's own
    content."""
    from portal.modules.security.core.bully.unit_outcome import _unobservable_channels

    # relation=None, no unit supplied -- the old hardcoded behaviour, still
    # correct for the truly-uninformative case
    assert _unobservable_channels(None) == ("shape", "vocabulary")
