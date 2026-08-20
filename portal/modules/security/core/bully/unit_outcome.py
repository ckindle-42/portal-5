"""bully.unit_outcome -- resolve the outcome table and emit ConcernBriefs
(V.2, TASK_BULLY_UNKNOWN_COUSIN_V1).

Combines V.1's unit-vs-type grading with N.1's known-benign types and N.2's
baseline to resolve the outcome table from
`docs/DESIGN_BULLY_UNKNOWN_COUSIN_V1.md`:

| type relation             | baseline    | outcome           | disposition |
|----------------------------|-------------|--------------------|--------------|
| EXACT malicious, known instance   | --   | KNOWN_INSTANCE     | floor        |
| EXACT malicious, unknown instance | --   | UNKNOWN_SAME       | concern      |
| SIMILAR malicious                 | --   | COUSIN             | concern      |
| EXACT/SIMILAR benign              | --   | RECOGNIZED_NORMAL  | suppress     |
| none                       | unremarkable| NORMAL             | silent       |
| none                       | remarkable  | NOVEL              | concern      |
| uncomputable                | --  | INSUFFICIENT_VIEW  | instrument   |

"Known instance" is decided by anchor *kind*, not by matching a type: a
`confirmed_finding` or `detection_coverage` anchor means this exact
occurrence (or something covered by existing detection content) is already
on file -- the floor, "existing detection owns it." An `attack_episode` or
`advisory` anchor defines a technique *type*; matching one exactly still
means the *instance* in front of us was never seen before, which is
`UNKNOWN_SAME`, not `KNOWN_INSTANCE` -- conflating "matches a known type"
with "is a known instance" is precisely the error this whole task exists to
correct (P1).

Every concern-raising outcome (`UNKNOWN_SAME`, `COUSIN`, `NOVEL`) emits a
`ConcernBrief` -- a verdict label with no brief is not actionable and does
not ship. `KNOWN_INSTANCE` never outranks a concern in report ordering
(P1, M.2 invariant #4): it is deliberately the least interesting row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .anchors import Anchor, AnchorLibrary
from .artifact_graph import ActionClassifier, GradeableUnit
from .baseline import NormalBaseline
from .unit_relation import (
    UnitTypeRelation,
    grade_unit_against_type,
    unit_shape_tokens,
    unit_vocabulary_tokens,
)

ALGORITHM_VERSION = "unit-outcome-v1"

OUTCOMES: tuple[str, ...] = (
    "UNKNOWN_SAME",
    "COUSIN",
    "NOVEL",
    "RECOGNIZED_NORMAL",
    "NORMAL",
    "INSUFFICIENT_VIEW",
    "KNOWN_INSTANCE",
)

CONCERN_OUTCOMES: frozenset[str] = frozenset({"UNKNOWN_SAME", "COUSIN", "NOVEL"})

_KNOWN_INSTANCE_KINDS: frozenset[str] = frozenset({"confirmed_finding", "detection_coverage"})

# Report ordering rank, lowest sorts first. `KNOWN_INSTANCE` is deliberately
# last -- it must never headline or outrank a concern (P1, M.2 invariant #4).
_OUTCOME_RANK: dict[str, int] = {
    "UNKNOWN_SAME": 0,
    "COUSIN": 0,
    "NOVEL": 1,
    "RECOGNIZED_NORMAL": 2,
    "NORMAL": 3,
    "INSUFFICIENT_VIEW": 3,
    "KNOWN_INSTANCE": 4,
}


@dataclass(frozen=True)
class ConcernBrief:
    """The deliverable: a concern, not a verdict."""

    unit_id: str
    level: str
    artifact_ids: tuple[str, ...]
    entities: tuple[str, ...]
    span_seconds: float | None
    outcome: str
    resembles_anchor_id: str | None
    resembles_kind: str | None
    shared_shape_features: tuple[str, ...]
    diverging_shape_features: tuple[str, ...]
    shared_vocabulary_features: tuple[str, ...]
    diverging_vocabulary_features: tuple[str, ...]
    axis_of_divergence: str | None
    remarkability: float
    confidence: float
    what_could_not_be_seen: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "level": self.level,
            "artifact_ids": list(self.artifact_ids),
            "entities": list(self.entities),
            "span_seconds": self.span_seconds,
            "outcome": self.outcome,
            "resembles_anchor_id": self.resembles_anchor_id,
            "resembles_kind": self.resembles_kind,
            "shared_shape_features": list(self.shared_shape_features),
            "diverging_shape_features": list(self.diverging_shape_features),
            "shared_vocabulary_features": list(self.shared_vocabulary_features),
            "diverging_vocabulary_features": list(self.diverging_vocabulary_features),
            "axis_of_divergence": self.axis_of_divergence,
            "remarkability": self.remarkability,
            "confidence": self.confidence,
            "what_could_not_be_seen": list(self.what_could_not_be_seen),
        }


@dataclass(frozen=True)
class UnitOutcome:
    unit: GradeableUnit
    outcome: str
    anchor: Anchor | None
    relation: UnitTypeRelation | None
    remarkability: float
    brief: ConcernBrief | None
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def report_rank(self) -> int:
        return _OUTCOME_RANK[self.outcome]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit.unit_id,
            "level": self.unit.level,
            "outcome": self.outcome,
            "anchor_id": self.anchor.anchor_id if self.anchor else None,
            "anchor_kind": self.anchor.kind if self.anchor else None,
            "relation": self.relation.to_dict() if self.relation else None,
            "remarkability": self.remarkability,
            "brief": self.brief.to_dict() if self.brief else None,
            "algorithm_version": self.algorithm_version,
        }


def _confidence_for_match(relation: UnitTypeRelation) -> float:
    distances = [
        d for d in (relation.shape.distance, relation.vocabulary.distance) if d is not None
    ]
    if not distances:
        return 0.0
    return max(0.0, 1.0 - (sum(distances) / len(distances)))


def _match_sort_key(pair: tuple[Anchor, UnitTypeRelation]) -> tuple[int, float]:
    _anchor, relation = pair
    rank = 0 if relation.overall_relation == "EXACT" else 1
    distances = [
        d for d in (relation.shape.distance, relation.vocabulary.distance) if d is not None
    ]
    distance = min(distances) if distances else 1.0
    return (rank, distance)


def _unobservable_channels(
    relation: UnitTypeRelation | None, unit: GradeableUnit | None = None
) -> tuple[str, ...]:
    """RC5 (TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1, M.4): when there is
    no matching relation (the `NOVEL` path -- no anchor matched), the old
    code hardcoded both channels unobservable regardless of whether the
    unit itself actually had shape or vocabulary content. That let a
    genuinely well-observed `NOVEL` unit carry
    `what_could_not_be_seen: ["shape", "vocabulary"]` in its brief -- the
    same signature `resolve_unit_outcome`'s own entry gate treats as
    instrument failure, just reported inconsistently downstream. Fall back
    to the unit's *own* observability, not a blanket claim, when there is
    no relation to ask."""
    if relation is None:
        if unit is None:
            return ("shape", "vocabulary")
        channels = []
        if not unit_shape_tokens(unit):
            channels.append("shape")
        if not unit_vocabulary_tokens(unit):
            channels.append("vocabulary")
        return tuple(channels)
    channels = []
    if relation.shape.unobservable:
        channels.append("shape")
    if relation.vocabulary.unobservable:
        channels.append("vocabulary")
    return tuple(channels)


def _build_brief(
    unit: GradeableUnit,
    outcome: str,
    anchor: Anchor | None,
    relation: UnitTypeRelation | None,
    remarkability: float,
) -> ConcernBrief:
    confidence = _confidence_for_match(relation) if relation else min(1.0, remarkability)
    return ConcernBrief(
        unit_id=unit.unit_id,
        level=unit.level,
        artifact_ids=unit.artifact_ids,
        entities=unit.entities,
        span_seconds=unit.span_seconds,
        outcome=outcome,
        resembles_anchor_id=anchor.anchor_id if anchor else None,
        resembles_kind=anchor.kind if anchor else None,
        shared_shape_features=relation.shape.shared_tokens if relation else (),
        diverging_shape_features=relation.shape.diverging_tokens if relation else (),
        shared_vocabulary_features=relation.vocabulary.shared_tokens if relation else (),
        diverging_vocabulary_features=relation.vocabulary.diverging_tokens if relation else (),
        axis_of_divergence=relation.delta.get("axis_of_divergence") if relation else None,
        remarkability=remarkability,
        confidence=confidence,
        what_could_not_be_seen=_unobservable_channels(relation, unit),
    )


def resolve_unit_outcome(
    unit: GradeableUnit,
    library_anchors: list[Anchor],
    baseline: NormalBaseline,
    *,
    classifier: ActionClassifier | None = None,
) -> UnitOutcome:
    """Grade `unit` against every anchor in the library (P2: never gated,
    never skipped) and resolve the outcome table."""
    if not unit_shape_tokens(unit) and not unit_vocabulary_tokens(unit):
        return UnitOutcome(
            unit=unit,
            outcome="INSUFFICIENT_VIEW",
            anchor=None,
            relation=None,
            remarkability=0.0,
            brief=None,
        )

    graded = [
        (anchor, grade_unit_against_type(unit, anchor.record, classifier=classifier))
        for anchor in library_anchors
    ]
    matches = [(a, r) for a, r in graded if r.overall_relation in ("EXACT", "SIMILAR")]
    remarkability = baseline.remarkability(unit)

    if matches:
        best_anchor, best_relation = min(matches, key=_match_sort_key)
        if best_anchor.malice == "benign":
            outcome = "RECOGNIZED_NORMAL"
        elif best_anchor.kind in _KNOWN_INSTANCE_KINDS:
            outcome = "KNOWN_INSTANCE"
        elif best_relation.overall_relation == "EXACT":
            outcome = "UNKNOWN_SAME"
        else:
            outcome = "COUSIN"
    else:
        best_anchor, best_relation = None, None
        outcome = "NOVEL" if baseline.is_remarkable(unit) else "NORMAL"

    brief = (
        _build_brief(unit, outcome, best_anchor, best_relation, remarkability)
        if outcome in CONCERN_OUTCOMES
        else None
    )
    return UnitOutcome(
        unit=unit,
        outcome=outcome,
        anchor=best_anchor,
        relation=best_relation,
        remarkability=remarkability,
        brief=brief,
    )


def resolve_unit_outcomes(
    units: list[GradeableUnit],
    library_anchors: list[Anchor],
    baseline: NormalBaseline,
    *,
    classifier: ActionClassifier | None = None,
) -> list[UnitOutcome]:
    return [
        resolve_unit_outcome(unit, library_anchors, baseline, classifier=classifier)
        for unit in units
    ]


def most_specific_outcomes(outcomes: list[UnitOutcome]) -> list[UnitOutcome]:
    """Prefer the smallest unit that matched the same type -- the most
    specific claim available. A concern-raising outcome for a larger unit is
    dropped when a strict subset of its artifacts, at a smaller unit, already
    raised the same outcome against the same anchor."""
    concern = [o for o in outcomes if o.outcome in CONCERN_OUTCOMES and o.anchor is not None]
    other = [o for o in outcomes if not (o.outcome in CONCERN_OUTCOMES and o.anchor is not None)]

    kept: list[UnitOutcome] = []
    for candidate in sorted(concern, key=lambda o: o.unit.size):
        candidate_ids = set(candidate.unit.artifact_ids)
        candidate_anchor = candidate.anchor.anchor_id if candidate.anchor else None
        redundant = any(
            existing.anchor
            and existing.anchor.anchor_id == candidate_anchor
            and set(existing.unit.artifact_ids) <= candidate_ids
            and existing.unit.unit_id != candidate.unit.unit_id
            for existing in kept
        )
        if not redundant:
            kept.append(candidate)
    return kept + other


def sort_for_report(outcomes: list[UnitOutcome]) -> list[UnitOutcome]:
    """Concern-raising outcomes first; `KNOWN_INSTANCE` never headlines
    (P1, M.2 invariant #4)."""
    return sorted(outcomes, key=lambda o: (o.report_rank, o.unit.unit_id))


# ── L.1: outcomes become types; suppression goes live ──────────────────────

ANALYST_DISPOSITIONS: tuple[str, ...] = ("BENIGN_CLOSE", "CONFIRMED_MALICIOUS")


def _unit_type_record(unit: GradeableUnit) -> dict[str, Any]:
    return {
        "action_sequence": list(unit.vocabulary),
        "event_graph": dict(unit.structural_signature),
        "parameter_families": list(unit.entities),
    }


def write_unit_outcome_as_anchor(
    library: AnchorLibrary,
    outcome: UnitOutcome,
    *,
    source_id: str,
    analyst_disposition: str,
    analyst_confirmed: bool = True,
) -> Anchor:
    """Close the compounding loop for the unit-level pipeline: an
    investigated unit's disposition becomes a typed anchor, malice carried,
    so the *next* occurrence of the same shape/vocabulary resolves
    differently.

    `BENIGN_CLOSE` writes a `benign_pattern` anchor (N.1) -- this is what
    turns `RECOGNIZED_NORMAL` suppression from dead wiring into something
    that actually fires on repeat, because `resolve_unit_outcome` already
    treats any `malice == "benign"` match as `RECOGNIZED_NORMAL`. Before
    this function existed, an analyst's benign call was never persisted, so
    a repeated benign unit only ever had a *type* library to match against,
    never an *instance* the system itself had already closed.

    `CONFIRMED_MALICIOUS` writes a `confirmed_finding` anchor -- on the next
    occurrence this becomes the `KNOWN_INSTANCE` floor row rather than a
    fresh `UNKNOWN_SAME`/`COUSIN` concern, exactly the "existing detection
    owns it" disposition."""
    if analyst_disposition not in ANALYST_DISPOSITIONS:
        raise ValueError(f"unknown analyst disposition: {analyst_disposition!r}")
    record = _unit_type_record(outcome.unit)
    if analyst_disposition == "BENIGN_CLOSE":
        return library.load_benign_pattern(
            source_id=source_id,
            record=record,
            recurrence_count=1,
        )
    return library.load_confirmed_finding(
        source_id=source_id,
        record=record,
        outcome="ESCALATE",
        analyst_confirmed=analyst_confirmed,
        derived_from=(outcome.unit.unit_id,),
    )
