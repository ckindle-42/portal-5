"""bully.observed_mode -- the observed investigation entry mode
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 B.3).

Provoked (the existing `orchestrator.py` hunt: DRAFT..MUTATION_READY..
EXECUTING..CLOSED, contracts.HUNT_STAGES) and observed become two entry
modes of one engine. This module owns a *separate* stage machine
(SEEDED -> SCOPING -> RELATING -> INVESTIGATING -> GRADING -> PROMOTING ->
COMPOUNDING -> CLOSED) that never touches MUTATION_READY/EXECUTING and
never imports/mutates `contracts.HUNT_STAGES` -- keeping the provoked path's
heavily-tested state machine completely unregressed (B.3 test claim) rather
than overloading one closed enum with two unrelated linear sequences.

J.1-J.3 wire the real relation/investigation/grading/promotion hooks into
this driver; B.3 establishes the mode and stage machine only -- the default
hooks here are honest no-ops/pass-throughs, never fabricated verdicts.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

OBSERVED_STAGES: tuple[str, ...] = (
    "SEEDED",
    "SCOPING",
    "RELATING",
    "INVESTIGATING",
    "GRADING",
    "PROMOTING",
    "COMPOUNDING",
    "CLOSED",
    "BLOCKED",
    "CANCELLED",
    "FAILED",
)

_TERMINAL_ADJACENT: frozenset[str] = frozenset({"BLOCKED", "CANCELLED", "FAILED"})
_MAIN_ORDER: dict[str, int] = {
    name: i
    for i, name in enumerate(
        (
            "SEEDED",
            "SCOPING",
            "RELATING",
            "INVESTIGATING",
            "GRADING",
            "PROMOTING",
            "COMPOUNDING",
            "CLOSED",
        )
    )
}

# The stages this mode never enters -- provoked-only, mutation/execution
# territory (S1-adjacent guard for B.3's own test claim).
FORBIDDEN_STAGES: frozenset[str] = frozenset({"MUTATION_READY", "EXECUTING"})


def is_legal_observed_transition(current: str, target: str) -> bool:
    if current not in OBSERVED_STAGES or target not in OBSERVED_STAGES:
        raise ValueError(f"unknown observed stage: {current!r} -> {target!r}")
    if current in ("CLOSED", "CANCELLED", "FAILED"):
        return False
    if target in _TERMINAL_ADJACENT:
        return current != "CLOSED"
    if current in ("BLOCKED", "CANCELLED", "FAILED"):
        return False
    return _MAIN_ORDER.get(target, -1) == _MAIN_ORDER.get(current, -2) + 1


@dataclass
class ObservedRun:
    run_id: str
    seed_id: str
    stages_entered: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    current_stage: str = "SEEDED"
    created_at: float = field(default_factory=time.time)

    def enter(self, stage: str) -> None:
        if not is_legal_observed_transition(self.current_stage, stage):
            raise ValueError(f"illegal observed transition: {self.current_stage} -> {stage}")
        if stage in FORBIDDEN_STAGES:  # pragma: no cover -- defensive, unreachable via enter()
            raise AssertionError("observed mode never enters mutation/execution stages")
        self.current_stage = stage
        self.stages_entered.append(stage)


def run_observed(
    seed: Any,
    *,
    scope_fn: Callable[[Any], Any],
    relate_fn: Callable[[Any], Any] | None = None,
    investigate_fn: Callable[[Any, Any], Any] | None = None,
    grade_fn: Callable[[Any, Any], Any] | None = None,
    promote_fn: Callable[[Any, Any], Any] | None = None,
    compound_fn: Callable[[Any, Any], Any] | None = None,
) -> ObservedRun:
    """Drive one observed-mode investigation seed through the stage
    sequence. Every hook is optional -- an omitted hook is a documented
    no-op (never a fabricated result), so B.3 stands on its own before
    J.1-J.3 wire the real relation/bin-gate/promotion/anchor-write-back
    behavior in behind these same seams."""
    run = ObservedRun(run_id=f"obs-{uuid.uuid4().hex[:12]}", seed_id=getattr(seed, "seed_id", ""))

    run.enter("SCOPING")
    scope = scope_fn(seed)
    run.evidence["scope"] = scope

    run.enter("RELATING")
    relation = relate_fn(scope) if relate_fn else None
    run.evidence["relation"] = relation

    run.enter("INVESTIGATING")
    investigation = investigate_fn(scope, relation) if investigate_fn else None
    run.evidence["investigation"] = investigation

    run.enter("GRADING")
    grade = grade_fn(scope, investigation) if grade_fn else None
    run.evidence["grade"] = grade

    run.enter("PROMOTING")
    promotion = promote_fn(scope, grade) if promote_fn else None
    run.evidence["promotion"] = promotion

    run.enter("COMPOUNDING")
    compounding = compound_fn(scope, promotion) if compound_fn else None
    run.evidence["compounding"] = compounding

    run.enter("CLOSED")
    return run


def run_observed_investigation(
    seed: Any,
    plane: Any,
    source_id: str,
    anchor_library: Any,
    *,
    signature_fn: Callable[[Any], Any],
    capabilities: dict[str, bool] | None = None,
    scale_cap: int = 500,
    grade_fn: Callable[[Any, Any], Any] | None = None,
    promote_fn: Callable[[Any, Any], Any] | None = None,
    compound_fn: Callable[[Any, Any], Any] | None = None,
    notify: Callable[[dict[str, Any]], None] | None = None,
    verdict_fn: Callable[[Any], str | None] | None = None,
) -> ObservedRun:
    """J.1 interlock, re-pointed (TASK_BULLY_COUSIN_RELATION_V1 C.2): SCOPING
    uses B.2's `build_scope`; RELATING calls the observed-mode cousin grader
    (`cousin_relation.relate_cousin`) on the scope and puts the
    `CousinRelation` into the run's evidence; INVESTIGATING starts from that
    relation (J.1's relation_investigation module), never a blank prompt.
    The provoked path's `relation.relate` is untouched and still runnable
    directly for the C.7 old-vs-new comparison -- it is simply no longer
    this module's call site.

    `signature_fn` adapts a `Scope`'s native records into whatever the
    relation engine's subject signature needs -- left injectable because
    that adaptation is source-specific (evidence.py's concern), not this
    module's.

    X.3: when the caller supplies `grade_fn` (producing a loop
    `contracts.CousinAssessment`, e.g. `loop_grader.build_cousin_assessment`),
    `promote_fn`/`compound_fn` default to the analyst loop hinge instead of a
    no-op -- this is the wiring that was previously entirely unbuilt. PROMOTING
    raises a concern (`analyst_loop.raise_concern`) gated ONLY by
    `compounding.should_escalate` on that grade; COMPOUNDING writes an analyst
    verdict back (`analyst_loop.record_verdict`) whenever `verdict_fn` produces
    one for the raised concern. An explicitly-supplied `promote_fn`/`compound_fn`
    always wins -- these are defaults, not an override.
    """
    from . import analyst_loop, compounding
    from . import cousin_relation as cousin_mod
    from .relation_investigation import investigate_from_relation
    from .seed_scope import build_scope

    def _scope_fn(seed: Any) -> Any:
        return build_scope(seed, plane, source_id, scale_cap=scale_cap)

    # Built once per run, not per seed -- the discriminative index is a
    # corpus statistic over the anchor library, not a property of any one
    # arrival (TASK_BULLY_COUSIN_RELATION_V1 C.2).
    index = cousin_mod.build_discriminative_index(anchor_library.records())

    # Carries the signature computed in RELATING through to PROMOTING/
    # COMPOUNDING, whose hooks are `(scope, grade)`/`(scope, promotion)` --
    # neither is handed the signature directly, and the anchor write-back
    # needs it (compounding.write_outcome_as_anchor(anchor_library, signature, ...)).
    _signature_by_scope: dict[str, Any] = {}

    def _relate_fn(scope: Any) -> Any:
        signature = signature_fn(scope)
        _signature_by_scope[scope.scope_id] = signature
        # `capabilities` is recorded as an annotation on the scope's evidence,
        # never fed into the grader: axis participation is decided per-pair by
        # what the arrival actually carries, which is strictly more honest
        # than a declared capability flag, and a capability flag must never
        # alter a measurement (C.2).
        return cousin_mod.relate_cousin(
            signature,
            anchor_library.records(),
            index=index,
            subject_id=getattr(signature, "signature_id", None),
        )

    def _default_promote_fn(scope: Any, grade: Any) -> Any:
        # `grade` is the loop's `contracts.CousinAssessment` (from `grade_fn`,
        # e.g. `loop_grader.build_cousin_assessment`); no grade, nothing to
        # raise -- honest no-op, never a fabricated concern.
        if grade is None:
            return None
        relation_view = _RelationView(verdict=grade.relationship, assessment=grade)
        escalate = compounding.should_escalate(relation_view, anchor_library)
        entities = scope.bounds.entities
        entity_id = entities[0] if entities else scope.seed_id
        return analyst_loop.raise_concern(
            assessment_id=grade.assessment_id,
            entity_id=entity_id,
            relationship=grade.relationship,
            match_level=str(grade.explanation.get("match_level", "")),
            robustness=grade.composite,
            n_sources=1,
            source_ids=(source_id,),
            aligned_spine=tuple(grade.explanation.get("aligned_spine", ())),
            resembles=grade.reference_signature_id,
            notify=notify,
            should_escalate=escalate,
        )

    def _default_compound_fn(scope: Any, promotion: Any) -> Any:
        # `promotion` is the `Concern` `_default_promote_fn` raised (or None
        # if it didn't fire). Only writes back when a verdict actually exists
        # -- this hook never invents an analyst's decision.
        if promotion is None or verdict_fn is None:
            return None
        verdict = verdict_fn(promotion)
        if verdict is None:
            return None
        signature = _signature_by_scope.get(scope.scope_id)
        return analyst_loop.record_verdict(
            promotion, verdict, anchor_library=anchor_library, signature=signature
        )

    run = run_observed(
        seed,
        scope_fn=_scope_fn,
        relate_fn=_relate_fn,
        investigate_fn=investigate_from_relation,
        grade_fn=grade_fn,
        promote_fn=promote_fn or _default_promote_fn,
        compound_fn=compound_fn or _default_compound_fn,
    )
    # Annotation only -- recorded for the run's evidence trail, never fed
    # into the grader (see _relate_fn above).
    run.evidence["capabilities_declared"] = dict(capabilities or {})
    return run


@dataclass(frozen=True)
class _RelationView:
    """Duck-typed shim matching what `compounding.should_escalate` reads off
    `relation.Relation` (`.verdict`, `.assessment.reference_signature_id`) --
    built from the loop's `CousinAssessment` rather than the legacy
    `relation.relate` path, without constructing a full `Relation`."""

    verdict: str
    assessment: Any
