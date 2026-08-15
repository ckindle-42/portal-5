"""P3.1 -- MUT typed MutationPlans compiled to Red scenario overlays.

Hermetic (no network, no lab). FINAL_VALIDATION C9 "Mutation director":
plans are structurally valid, within budget (truncation recorded),
scope-guarded (out-of-lab rejected), and produce no Red-internals edits.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import mutation
from portal.modules.security.core.bully.contracts import MutationOperatorSpec, MutationPlan

_REFERENCE_SCENARIO = {
    "name": "kerberoast_to_da",
    "target_host": "10.10.11.21",  # in-lab (LAB_CIDR 10.10.11.0/24)
    "red_order": [
        "start_lab_target",
        "run_nmap_scan",
        "check_cve",
        "exploit_service",
        "establish_persistence",
        "lateral_move",
        "exfiltrate_data",
        "revert_lab_target",
    ],
    "red_prompt": "Attack $TARGET_HOST using the standard chain.",
    "mission_objective": None,
}

_HUNT_CONFIG = {
    "mutation": {
        "max_variants_per_iteration": 5,
        "allowed_classes": [
            "REORDER_STEPS",
            "SUBSTITUTE_TECHNIQUE",
            "VARY_PARAMETER",
            "INJECT_EVASION_DIRECTIVE",
            "OFF_SCRIPT_SUPPLY",
            "REVERSE_GEN_SEED",
        ],
    }
}


def _plan(**overrides) -> MutationPlan:
    defaults = {
        "reference_scenario": "kerberoast_to_da",
        "operators": [
            MutationOperatorSpec(
                operator="SUBSTITUTE_TECHNIQUE",
                params={"from": "establish_persistence", "to": "establish_persistence_alt"},
            )
        ],
        "invariants": (),
        "controls": (),
        "allowed_targets": ("10.10.11.21",),
        "proposer": "system:mut-test",
        "budget_class": "standard",
    }
    defaults.update(overrides)
    return mutation.build_plan(**defaults)


# ── happy path ────────────────────────────────────────────────────────────


def test_compiles_a_valid_plan_into_an_overlay():
    plan = _plan()
    overlay = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
    )
    assert overlay.plan_id == plan.plan_id
    assert "establish_persistence_alt" in overlay.red_order
    assert "establish_persistence" not in overlay.red_order
    assert overlay.truncated is False
    assert overlay.truncation_rationale is None


# ── C9: scope violation rejected, no Red call ───────────────────────────────


def test_scope_violation_rejected_before_any_compile():
    plan = _plan(allowed_targets=("8.8.8.8",))  # outside LAB_CIDR
    with pytest.raises(mutation.MutationValidationError) as exc:
        mutation.validate_and_compile(
            plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
        )
    assert exc.value.reason_code == "SCOPE_VIOLATION"


# ── C9: budget truncation recorded, never silent overflow ──────────────────


def test_budget_truncation_recorded_not_silent():
    ops = [
        MutationOperatorSpec(operator="VARY_PARAMETER", params={"placeholder": "$X", "value": i})
        for i in range(8)
    ]
    plan = _plan(operators=ops, controls=("matched_control_a",))
    small_budget_config = {
        "mutation": {"max_variants_per_iteration": 3, "allowed_classes": ["VARY_PARAMETER"]}
    }
    overlay = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=small_budget_config
    )
    assert overlay.truncated is True
    assert overlay.truncation_rationale is not None
    assert "3" in overlay.truncation_rationale
    assert len(overlay.applied_operators) == 3


# ── C9: byte-identical recompile of the same plan version ──────────────────


def test_recompile_is_byte_identical_for_the_same_plan_version():
    plan = _plan()
    overlay_1 = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
    )
    overlay_2 = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
    )
    # created_at is audit metadata only (module docstring) -- everything else
    # that defines the *render* must match exactly, including overlay_id
    # (deterministic in the plan, not random).
    assert overlay_1.overlay_id == overlay_2.overlay_id
    assert overlay_1.red_order == overlay_2.red_order
    assert overlay_1.red_prompt == overlay_2.red_prompt
    assert overlay_1.expectation == overlay_2.expectation
    assert overlay_1.applied_operators == overlay_2.applied_operators
    assert overlay_1.truncated == overlay_2.truncated


# ── C9: unknown operator -> rejected (never partially compiled) ────────────


def test_unknown_operator_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown mutation operator"):
        MutationOperatorSpec(operator="DOES_NOT_EXIST", params={})


def test_unknown_operator_from_dict_rejected_never_partially_compiled():
    """A plan loaded from an untrusted dict (e.g. a stored record) with a
    bogus operator name must fail at the boundary, not compile partially."""
    with pytest.raises(ValueError, match="unknown mutation operator"):
        MutationOperatorSpec.from_dict({"operator": "NOT_A_REAL_OPERATOR", "params": {}})


# ── invariant conflict ───────────────────────────────────────────────────


def test_invariant_conflict_rejected():
    plan = _plan(
        operators=[
            MutationOperatorSpec(operator="OFF_SCRIPT_SUPPLY", params={"technique_ids": ["T1200"]})
        ],
        invariants=("no_new_techniques",),
    )
    with pytest.raises(mutation.MutationValidationError) as exc:
        mutation.validate_and_compile(
            plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
        )
    assert exc.value.reason_code == "INVARIANT_CONFLICT"


# ── missing control (M2 causal isolation) ───────────────────────────────


def test_multi_dimensional_plan_without_controls_is_rejected():
    ops = [
        MutationOperatorSpec(
            operator="REORDER_STEPS",
            params={"order": list(_REFERENCE_SCENARIO["red_order"]), "keep_final": True},
        ),
        MutationOperatorSpec(operator="VARY_PARAMETER", params={"placeholder": "$X", "value": "y"}),
    ]
    plan = _plan(operators=ops, controls=())
    with pytest.raises(mutation.MutationValidationError) as exc:
        mutation.validate_and_compile(
            plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
        )
    assert exc.value.reason_code == "MISSING_CONTROL"


def test_multi_dimensional_plan_with_a_control_advances():
    ops = [
        MutationOperatorSpec(
            operator="REORDER_STEPS",
            params={"order": list(_REFERENCE_SCENARIO["red_order"]), "keep_final": True},
        ),
        MutationOperatorSpec(operator="VARY_PARAMETER", params={"placeholder": "$X", "value": "y"}),
    ]
    plan = _plan(operators=ops, controls=("matched_control_a",))
    overlay = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=_HUNT_CONFIG
    )
    assert overlay.expectation["controls"] == ["matched_control_a"]


# ── unapproved mutation class `[GATE]` ──────────────────────────────────


def test_unapproved_class_without_approval_ref_rejected():
    plan = _plan()
    narrow_config = {"mutation": {"max_variants_per_iteration": 5, "allowed_classes": []}}
    with pytest.raises(mutation.MutationValidationError) as exc:
        mutation.validate_and_compile(
            plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=narrow_config
        )
    assert exc.value.reason_code == "CLASS_NOT_APPROVED"


def test_unapproved_class_with_approval_ref_advances():
    plan = _plan(approval_ref="operator:alice-2026-08-15")
    narrow_config = {"mutation": {"max_variants_per_iteration": 5, "allowed_classes": []}}
    overlay = mutation.validate_and_compile(
        plan, reference_scenario=_REFERENCE_SCENARIO, hunt_config=narrow_config
    )
    assert overlay is not None


# ── seeding helpers ───────────────────────────────────────────────────────


def test_seed_directive_channel_no_prior_detections():
    text = mutation.seed_directive_channel({}, _REFERENCE_SCENARIO)
    assert "SIEM Feedback" in text


def test_off_script_technique_ids_deduplicates():
    from portal.modules.security.core.trajectory_score import StepRecord, TrajectoryVerdict

    steps = [
        StepRecord(
            step_id="s1",
            capability_id="cap1",
            red_status="RED_LANDED",
            detection_status="DETECTION_NO_HIT",
            used_synthetic=False,
        ),
        StepRecord(
            step_id="s2",
            capability_id="cap1",
            red_status="RED_LANDED",
            detection_status="DETECTION_MISSING",
            used_synthetic=False,
        ),
    ]
    verdict = TrajectoryVerdict(
        objective_class="lateral_move",
        verdict="RED_ONLY",
        objective_reached=True,
        synthetic_present=False,
        landed_steps=2,
        steps=steps,
    )
    ids = mutation.off_script_technique_ids(verdict, trajectory_id="traj-1")
    # StepRecord carries no technique_id field -- emergent_gaps falls back to
    # "cap:<capability_id>" (module docstring / _step_technique).
    assert ids == ["cap:cap1"]


def test_reverse_gen_seed_wraps_response_loop():
    draft = mutation.reverse_gen_seed("T1190", "web app exploit detection")
    assert draft.technique_id == "T1190"
    assert draft.draft_id == "red-draft-T1190"
