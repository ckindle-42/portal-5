"""bully.mutation -- MUT, typed MutationPlans compiled to Red scenario
overlays (P3.1, I-1/I-20).

Red is a means, never modified. MUT emits **data** (a compiled scenario
overlay), never code changes to Red: the compiled overlay's `red_prompt` /
`red_order` / expectation metadata is handed unchanged to
`exec_chain._prepare_scenario` / `BenchConfig.set_scenario` /
`_run_chain_test` (all three untouched by this build). Pure module -- no SQL,
no network, no import of the lab-execution entry points themselves (MASTER
SS3: "Only orchestrator.py sequences a hunt iteration"; enforced by
`tests/security/bully/test_boundaries.py`).

`validate_and_compile` is fail-closed: unknown operator, invariant conflict,
scope violation (`perception.assert_in_lab`), missing control, or an
unapproved mutation class -> rejected with a `MutationValidationError`
*before* any overlay is produced -- never a partially compiled overlay. A
budget overrun is a distinct, non-rejecting outcome: the plan is truncated to
the configured ceiling and the truncation is recorded on the overlay
(`truncated`, `truncation_rationale`) -- I-20's "approved plan ≤ budget or
explicit truncation ... never silent overflow".

Directive/off-script/reverse-gen seeding (P3.1 build order):
  - `seed_directive_channel` wraps `blue.py::_build_evasion_feedback` (pure
    text builder, lazily imported to avoid pulling in blue.py's heavier
    transitive imports at module scope).
  - `off_script_technique_ids` wraps `emergent_gaps.py::gaps_from_trajectory`
    (pure compute over an existing `TrajectoryVerdict`).
  - `reverse_gen_seed` wraps `response_loop.py::propose_red_scenario` /
    `RESPONSE_PRIMITIVES` (module-level import; response_loop.py stays, per
    the P3 task file's "imported; module stays").
These are seeding *helpers* used by a plan-building caller (LOOP or a CLI);
`validate_and_compile` itself never calls out to them -- it only compiles the
already-assembled `MutationPlan` it is given, which keeps compilation a pure
function of its three explicit inputs.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from typing import Any

from ..emergent_gaps import gaps_from_trajectory
from ..perception import OutOfScopeError, assert_in_lab
from ..response_loop import RedScenarioDraft, propose_red_scenario
from .contracts import (
    MUTATION_OPERATORS,
    MutationOperatorSpec,
    MutationPlan,
    ScenarioOverlay,
)

DEFAULT_MAX_VARIANTS = (
    5  # fallback only -- real ceiling is hunt.yaml::mutation.max_variants_per_iteration
)

# Operators that introduce techniques not present in the reference scenario's
# red_order -- conflict with the "single_technique_only" / "no_new_techniques"
# invariants (P3.1 "invariant conflict").
_TECHNIQUE_ADDING_OPERATORS = frozenset({"OFF_SCRIPT_SUPPLY", "REVERSE_GEN_SEED"})

__all__ = [
    "MutationValidationError",
    "validate_and_compile",
    "build_plan",
    "seed_directive_channel",
    "off_script_technique_ids",
    "reverse_gen_seed",
]


class MutationValidationError(RuntimeError):
    """Fail-closed validation failure (I-1). Carries a stable `reason_code`
    so the caller's decision-event `data` field records *why*, not just
    that validation failed. No Red call is ever made on this path."""

    def __init__(self, reason_code: str, detail: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {detail}")


# ── seeding helpers (P3.1 build order) ──────────────────────────────────────


def seed_directive_channel(blue_result: dict[str, Any], scenario: dict[str, Any]) -> str:
    """Directive-channel text seed from `blue.py::_build_evasion_feedback`
    (pure text builder -- no lab call). `blue_result` may be `{}` (no prior
    round yet); the wrapped function already handles that honestly."""
    from ..blue import _build_evasion_feedback

    return _build_evasion_feedback(blue_result, scenario)


def off_script_technique_ids(verdict: Any, *, trajectory_id: str) -> list[str]:
    """Off-script variant supply from `emergent_gaps.py::gaps_from_trajectory`
    -- technique ids for landed-but-undetected steps, deduplicated,
    deterministic order (first-seen)."""
    seen: list[str] = []
    for gap in gaps_from_trajectory(verdict, trajectory_id=trajectory_id):
        if gap.technique_id not in seen:
            seen.append(gap.technique_id)
    return seen


def reverse_gen_seed(technique_id: str, detection_description: str = "") -> RedScenarioDraft:
    """Reverse-gen seed from `response_loop.py::propose_red_scenario` (a
    BLUE_ONLY gap: a detection exists with no red exercise)."""
    return propose_red_scenario(technique_id, detection_description)


# ── plan building ────────────────────────────────────────────────────────────


def _idempotency_key(
    reference_scenario: str,
    operators: tuple[MutationOperatorSpec, ...],
    invariants: tuple[str, ...],
    budget_class: str,
) -> str:
    h = hashlib.sha256()
    h.update(reference_scenario.encode("utf-8"))
    for op in operators:
        h.update(op.operator.encode("utf-8"))
        h.update(repr(sorted(op.params.items())).encode("utf-8"))
    h.update("|".join(sorted(invariants)).encode("utf-8"))
    h.update(budget_class.encode("utf-8"))
    return f"mut-idem-{h.hexdigest()[:16]}"


def build_plan(
    *,
    reference_scenario: str,
    operators: list[MutationOperatorSpec],
    invariants: tuple[str, ...] = (),
    expected_observables: dict[str, Any] | None = None,
    controls: tuple[str, ...] = (),
    replay_policy: str = "no_replay",
    allowed_targets: tuple[str, ...] = (),
    allowed_tools: tuple[str, ...] = (),
    cleanup: tuple[str, ...] = (),
    approval_ref: str | None = None,
    budget_class: str = "standard",
    proposer: str,
    plan_version: int = 1,
) -> MutationPlan:
    """Assemble a `MutationPlan` from already-decided operators (the caller
    -- LOOP or a CLI -- decides *which* seeded operators to include, using
    `seed_directive_channel`/`off_script_technique_ids`/`reverse_gen_seed`
    as needed; this function only assembles + stamps identity, it makes no
    seeding decisions itself). `idempotency_key` is content-derived so
    re-building "the same plan" from the same inputs is naturally the same
    key (I-1 IDEMPOTENCY/RETRY)."""
    ops_tuple = tuple(operators)
    idem = _idempotency_key(reference_scenario, ops_tuple, invariants, budget_class)
    return MutationPlan(
        plan_id=f"mut-{uuid.uuid4().hex[:12]}",
        plan_version=plan_version,
        reference_scenario=reference_scenario,
        operators=ops_tuple,
        invariants=invariants,
        expected_observables=expected_observables or {},
        controls=controls,
        replay_policy=replay_policy,
        allowed_targets=allowed_targets,
        allowed_tools=allowed_tools,
        cleanup=cleanup,
        approval_ref=approval_ref,
        budget_class=budget_class,
        idempotency_key=idem,
        proposer=proposer,
    )


# ── operator application (deterministic, pure) ──────────────────────────────


def _apply_reorder_steps(red_order: list[str], params: dict[str, Any]) -> list[str]:
    target_order = params.get("order")
    if not target_order or sorted(target_order) != sorted(red_order):
        # Not a legal permutation of the existing steps -- leave unchanged
        # rather than silently dropping/inventing steps.
        return red_order
    return list(target_order)


def _apply_substitute_technique(red_order: list[str], params: dict[str, Any]) -> list[str]:
    src, dst = params.get("from"), params.get("to")
    if not src or not dst:
        return red_order
    return [dst if step == src else step for step in red_order]


def _apply_vary_parameter(red_prompt: str, params: dict[str, Any]) -> str:
    placeholder, value = params.get("placeholder"), params.get("value")
    if not placeholder or value is None:
        return red_prompt
    if placeholder in red_prompt:
        return red_prompt.replace(placeholder, str(value))
    return red_prompt + f"\n[MUTATION] use {value!r} for {placeholder}."


def _apply_inject_evasion_directive(red_prompt: str, params: dict[str, Any]) -> str:
    directive = params.get("directive_text", "")
    if not directive:
        return red_prompt
    return f"{directive}\n\n{red_prompt}"


def _apply_off_script_supply(red_order: list[str], params: dict[str, Any]) -> list[str]:
    technique_ids = params.get("technique_ids") or []
    out = list(red_order)
    for tid in technique_ids:
        if tid not in out:
            out.append(tid)
    return out


def _apply_reverse_gen_seed(red_order: list[str], params: dict[str, Any]) -> list[str]:
    technique_id = params.get("technique_id")
    if not technique_id:
        return red_order
    out = list(red_order)
    if technique_id not in out:
        out.append(technique_id)
    return out


_APPLIERS_RED_ORDER = {
    "REORDER_STEPS": _apply_reorder_steps,
    "SUBSTITUTE_TECHNIQUE": _apply_substitute_technique,
    "OFF_SCRIPT_SUPPLY": _apply_off_script_supply,
    "REVERSE_GEN_SEED": _apply_reverse_gen_seed,
}
_APPLIERS_RED_PROMPT = {
    "VARY_PARAMETER": _apply_vary_parameter,
    "INJECT_EVASION_DIRECTIVE": _apply_inject_evasion_directive,
}


# ── validation ───────────────────────────────────────────────────────────────


def _validate_operators(plan: MutationPlan) -> None:
    for op in plan.operators:
        if op.operator not in MUTATION_OPERATORS:  # pragma: no cover -- DTO already guards this
            raise MutationValidationError("UNKNOWN_OPERATOR", op.operator)


def _validate_invariant_conflicts(plan: MutationPlan) -> None:
    op_names = {op.operator for op in plan.operators}
    technique_adders = op_names & _TECHNIQUE_ADDING_OPERATORS
    if technique_adders and (
        "single_technique_only" in plan.invariants or "no_new_techniques" in plan.invariants
    ):
        raise MutationValidationError(
            "INVARIANT_CONFLICT",
            f"operators {sorted(technique_adders)} add techniques, conflicting with "
            f"invariant(s) requiring no new techniques",
        )
    if "preserve_final_step" in plan.invariants:
        for op in plan.operators:
            if op.operator == "REORDER_STEPS" and not op.params.get("keep_final", False):
                raise MutationValidationError(
                    "INVARIANT_CONFLICT",
                    "REORDER_STEPS without keep_final=True conflicts with "
                    "invariant 'preserve_final_step'",
                )


def _validate_scope(plan: MutationPlan) -> None:
    for target in plan.allowed_targets:
        try:
            assert_in_lab(target)
        except OutOfScopeError as exc:
            raise MutationValidationError("SCOPE_VIOLATION", str(exc)) from exc


def _validate_controls(plan: MutationPlan) -> None:
    """M2: multi-dimensional conclusions are not attributed without controls
    (causal isolation). A plan spanning >=2 distinct operator classes must
    declare at least one control, or it is rejected honestly rather than
    letting a confounded compile through."""
    op_classes = {op.operator for op in plan.operators}
    if len(op_classes) >= 2 and not plan.controls:
        raise MutationValidationError(
            "MISSING_CONTROL",
            f"plan combines {len(op_classes)} operator classes {sorted(op_classes)} "
            f"with no declared controls -- causal isolation requires >=1",
        )


def _validate_class_approval(plan: MutationPlan, allowed_classes: list[str]) -> None:
    """`[GATE]`: a mutation class outside the per-hunt operator-confirmed
    catalog (`hunt.yaml::mutation.allowed_classes`) requires an explicit
    `approval_ref` on the plan -- never a silent pass-through."""
    if plan.approval_ref:
        return
    unapproved = {op.operator for op in plan.operators} - set(allowed_classes)
    if unapproved:
        raise MutationValidationError(
            "CLASS_NOT_APPROVED",
            f"mutation class(es) {sorted(unapproved)} not in hunt.yaml::mutation.allowed_classes "
            f"and plan carries no approval_ref (scope/mutation-class widening requires "
            f"explicit operator confirmation)",
        )


def validate_and_compile(
    plan: MutationPlan,
    *,
    reference_scenario: dict[str, Any],
    hunt_config: dict[str, Any] | None = None,
) -> ScenarioOverlay:
    """I-1: validate `plan`, then compile it into a `ScenarioOverlay`.

    Pure function of `(plan, reference_scenario, hunt_config)`: the same
    inputs always yield the same `red_order`/`red_prompt`/`expectation`
    (`created_at` is audit metadata, excluded from that guarantee).

    Fail-closed: unknown operator / invariant conflict / scope violation /
    missing control / unapproved mutation class -> `MutationValidationError`,
    no overlay produced, no Red call. A budget overrun is NOT a validation
    failure -- the plan compiles with the operator list truncated to the
    configured ceiling and `truncated`/`truncation_rationale` recorded
    (I-20: "never silent overflow").
    """
    mutation_cfg = (hunt_config or {}).get("mutation") or {}
    max_variants = mutation_cfg.get("max_variants_per_iteration", DEFAULT_MAX_VARIANTS)
    allowed_classes = mutation_cfg.get("allowed_classes") or []

    _validate_operators(plan)
    _validate_invariant_conflicts(plan)
    _validate_scope(plan)
    _validate_controls(plan)
    _validate_class_approval(plan, allowed_classes)

    truncated = len(plan.operators) > max_variants
    applied_operators = plan.operators[:max_variants] if truncated else plan.operators
    truncation_rationale = (
        f"{len(plan.operators)} planned variant(s) truncated to budget "
        f"max_variants_per_iteration={max_variants}"
        if truncated
        else None
    )

    red_order = list(reference_scenario.get("red_order", []))
    red_prompt = reference_scenario.get("red_prompt", "")
    for op in applied_operators:
        applier = _APPLIERS_RED_ORDER.get(op.operator)
        if applier is not None:
            red_order = applier(red_order, op.params)
        applier_prompt = _APPLIERS_RED_PROMPT.get(op.operator)
        if applier_prompt is not None:
            red_prompt = applier_prompt(red_prompt, op.params)

    # No operator in the P3.1 catalog mutates mission_objective itself --
    # carried through unchanged regardless of the "preserve_mission_objective"
    # invariant (that invariant exists to reject a *future* operator that
    # would touch it without this plan explicitly allowing it).
    mission_objective = reference_scenario.get("mission_objective")

    expectation = {
        "expected_observables": copy.deepcopy(plan.expected_observables),
        "controls": list(plan.controls),
        "invariants": list(plan.invariants),
        "replay_policy": plan.replay_policy,
    }

    return ScenarioOverlay(
        overlay_id=f"ov-{plan.plan_id}-{plan.plan_version}",
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        reference_scenario=plan.reference_scenario,
        red_order=tuple(red_order),
        red_prompt=red_prompt,
        mission_objective=mission_objective,
        target_host=reference_scenario.get("target_host"),
        expectation=expectation,
        applied_operators=tuple(op.operator for op in applied_operators),
        truncated=truncated,
        truncation_rationale=truncation_rationale,
    )
