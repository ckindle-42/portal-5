"""T.4 -- leave-one-family-out: the product test (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_measurement as um

# Two malicious families that share technique lineage (both privilege-
# escalation-shaped: auth -> enumerate -> escalate), so leaving one out
# still leaves a plausibly-related surviving type for the shape channel to
# catch -- exactly the "cousin" case T.4 exists to measure.
_FAMILY_A_TYPE = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
_FAMILY_B_TYPE = ["Logon", "net user", "Add-LocalGroupMember"]
_BENIGN_TYPE = ["ListBuckets", "ListBuckets"]


def _unit(verbs: list[str], entity: str) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    return next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")


def _library() -> tuple[anc.AnchorLibrary, dict[str, list]]:
    lib = anc.AnchorLibrary()
    a = lib.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _FAMILY_A_TYPE}, techniques=("T1078",)
    )
    b = lib.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _FAMILY_B_TYPE}, techniques=("T1098",)
    )
    # A wide pool of unrelated distractor types, so the T.4 token-pool
    # shuffle has enough vocabulary diversity to actually dilute overlap --
    # with only two anchors' worth of tokens to draw from, a shuffle keeps
    # re-drawing the same small pool and coincidentally reproduces a match.
    for i in range(30):
        lib.load_attack_episode(
            source_id="attack_data",
            record={"action_sequence": [f"Distractor{i}Verb{j}" for j in range(3)]},
            techniques=(f"T9{i:03d}",),
        )
    return lib, {"family_a": [a], "family_b": [b]}


def _baseline() -> bl.NormalBaseline:
    """Fit broadly enough that the *shape* of the malicious families (an
    auth->enumerate->escalate chain) is itself common in this environment,
    regardless of literal vocabulary -- baseline features are shape-based
    (N.2), never vocabulary-based. This isolates the signal T.4's controls
    are meant to test to the type-matching machinery (COUSIN/UNKNOWN_SAME),
    rather than letting NOVEL (baseline-driven, library-independent) carry
    recall on its own and mask what the shuffled-library control is for."""
    model = bl.NormalBaseline(environment_id="e")
    common_shape_units = [
        _unit([f"Authenticate{i}", f"Enumerate{i}", f"Grant{i}"], f"bg-{i}") for i in range(80)
    ] + [
        # matches family_b's class shape: auth -> enumerate -> other
        # (Add-LocalGroupMember does not classify as "escalate" -- the U.3
        # seam -- so this is the shape that actually needs suppressing).
        _unit([f"Authenticate{i}", f"Enumerate{i}", f"Other{i}Verb"], f"bg2-{i}")
        for i in range(80)
    ]
    model.fit([_unit(_BENIGN_TYPE, f"u{i}") for i in range(50)] + common_shape_units)
    return model


def test_headline_recall_and_full_library_recall_are_both_published():
    lib, by_family = _library()
    eval_units = {
        "family_a": [_unit(_FAMILY_A_TYPE, "attacker-a1"), _unit(_FAMILY_A_TYPE, "attacker-a2")],
        "family_b": [_unit(_FAMILY_B_TYPE, "attacker-b1")],
    }
    report = um.run_leave_one_family_out(
        eval_units,
        by_family,
        list(lib.all()),
        _baseline(),
        benign_eval_units=[_unit(_BENIGN_TYPE, f"benign-{i}") for i in range(10)],
    )
    assert 0.0 <= report.cousin_recall <= 1.0
    assert 0.0 <= report.full_library_cousin_recall <= 1.0
    assert "family_a" in report.per_family
    assert "family_b" in report.per_family


def test_full_library_recall_is_at_least_as_high_as_leave_one_out():
    """Excluding a family's own type can only remove signal, never add it."""
    lib, by_family = _library()
    eval_units = {"family_a": [_unit(_FAMILY_A_TYPE, "attacker-a1")]}
    report = um.run_leave_one_family_out(
        eval_units,
        by_family,
        list(lib.all()),
        _baseline(),
        benign_eval_units=[],
    )
    assert report.full_library_cousin_recall >= report.cousin_recall


def test_seeded_violation_shuffled_type_labels_collapse_recall():
    lib, by_family = _library()
    eval_units = {
        "family_a": [_unit(_FAMILY_A_TYPE, f"attacker-{i}") for i in range(6)],
        "family_b": [_unit(_FAMILY_B_TYPE, f"attacker-{i}") for i in range(6)],
    }
    report = um.run_leave_one_family_out(
        eval_units,
        by_family,
        list(lib.all()),
        _baseline(),
        benign_eval_units=[_unit(_BENIGN_TYPE, f"benign-{i}") for i in range(10)],
    )
    assert report.shuffled_control_cousin_recall <= um.SHUFFLED_CONTROL_MAX_RATIO * max(
        report.cousin_recall, report.full_library_cousin_recall, 1e-9
    )


def test_benign_held_out_family_does_not_raise_concern_at_same_rate():
    lib, by_family = _library()
    eval_units = {"family_a": [_unit(_FAMILY_A_TYPE, f"attacker-{i}") for i in range(6)]}
    benign_units = [_unit(_BENIGN_TYPE, f"benign-{i}") for i in range(20)]
    report = um.run_leave_one_family_out(
        eval_units, by_family, list(lib.all()), _baseline(), benign_eval_units=benign_units
    )
    assert report.benign_control_concern_rate <= um.BENIGN_CONTROL_MAX_CONCERN_RATE


def test_verdict_is_valid_when_controls_hold():
    lib, by_family = _library()
    eval_units = {
        "family_a": [_unit(_FAMILY_A_TYPE, f"a-{i}") for i in range(6)],
        "family_b": [_unit(_FAMILY_B_TYPE, f"b-{i}") for i in range(6)],
    }
    report = um.run_leave_one_family_out(
        eval_units,
        by_family,
        list(lib.all()),
        _baseline(),
        benign_eval_units=[_unit(_BENIGN_TYPE, f"benign-{i}") for i in range(20)],
    )
    assert report.verdict in ("VALID", "INVALID")
    assert report.controls_hold == (report.verdict == "VALID")


def test_seeded_violation_broken_benign_control_turns_report_invalid():
    """A benign family that raises concern at a high rate must flip the
    verdict to INVALID -- proving the control actually gates the verdict
    rather than being computed and ignored."""
    lib, by_family = _library()
    eval_units = {"family_a": [_unit(_FAMILY_A_TYPE, f"a-{i}") for i in range(6)]}
    broken_benign_units = [_unit(_FAMILY_A_TYPE, f"mislabeled-benign-{i}") for i in range(10)]
    report = um.run_leave_one_family_out(
        eval_units, by_family, list(lib.all()), _baseline(), benign_eval_units=broken_benign_units
    )
    assert report.benign_control_concern_rate > um.BENIGN_CONTROL_MAX_CONCERN_RATE
    assert report.verdict == "INVALID"
