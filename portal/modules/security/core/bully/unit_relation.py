"""bully.unit_relation -- three-way unit-vs-type grading on shape and
vocabulary channels (V.1, TASK_BULLY_UNKNOWN_COUSIN_V1).

Grades a `GradeableUnit` against a known type (an anchor record) ->
`EXACT` / `SIMILAR` / `NOT_AT_ALL`, on the shape channel and the vocabulary
channel **separately**, each with a normalized distance and a mandatory
delta. This is what lets a relation say "same shape, entirely different
vocabulary" -- exactly what an unknown instance of a known type looks like,
and unreachable when shape and vocabulary are graded as one blended axis.

**The shape channel is computed at grading time, on both sides.** A unit
already carries a `structural_signature` (U.1/U.2). A known-type anchor
typically carries only a literal `action_sequence` (attack_data's declared
verbs) -- it has no pre-populated class shape of its own. Rather than
requiring every anchor to be re-authored with one, this module classifies
the anchor's `action_sequence` through the same `ActionClassifier` (U.3)
used to build the unit's shape, so both sides land in the same class-shape
space regardless of which one started out as raw vocabulary. This is also
where the U.3 seam's effect on grading becomes directly measurable: a
better classifier closes shape-channel gaps between disjoint vocabularies
without this module changing at all.

Carries forward `cousin_relation`'s C.1 inversions, applied per channel:
normalized distance over the tokens that exist on both sides; coverage is
an annotation, never a gate; an empty side is `unobservable`, never a
penalty; a delta is mandatory on every grade; divergence can still raise
interest via an optional discriminative index.

Pure compute over injected units and anchor records (COLD).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifact_graph import DEFAULT_ACTION_CLASSIFIER, ActionClassifier, GradeableUnit

ALGORITHM_VERSION = "unit-relation-v1"

CHANNELS: tuple[str, ...] = ("shape", "vocabulary")

RELATIONS: tuple[str, ...] = ("EXACT", "SIMILAR", "NOT_AT_ALL")

# Judgement thresholds. Recorded on every grade; a change is a re-baseline,
# never a silent tune.
EXACT_MAX_DISTANCE = 0.15
SIMILAR_MAX_DISTANCE = 0.60


def _as_token_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        out: set[str] = set()
        for key, inner in value.items():
            for token in _as_token_set(inner):
                out.add(f"{key}={token}")
        return out
    if isinstance(value, (list, tuple, set)):
        out = set()
        for item in value:
            out |= _as_token_set(item)
        return out
    text = str(value).strip()
    return {text} if text else set()


def _class_shape_tokens(action_sequence: Any, classifier: ActionClassifier | None) -> set[str]:
    """Bigrams + presence over the classified action sequence -- the same
    encoding a unit's `structural_signature['class_sequence']` already
    carries, computed here for whichever side did not arrive with one."""
    clf = classifier or DEFAULT_ACTION_CLASSIFIER
    sequence = action_sequence if isinstance(action_sequence, (list, tuple)) else []
    classes = tuple(clf.classify(str(a)) for a in sequence)
    tokens: set[str] = set()
    for left, right in zip(classes, classes[1:], strict=False):
        tokens.add(f"class_bigram={left}>{right}")
    for cls in classes:
        tokens.add(f"class_present={cls}")
    return tokens


def unit_shape_tokens(unit: GradeableUnit) -> set[str]:
    """Same encoding as `_type_shape_tokens`'s fallback -- class bigrams and
    presence only -- so two sides with an identical class sequence always
    land at distance 0 regardless of which one started with a
    pre-populated `event_graph` and which one was classified on the fly."""
    signature = unit.structural_signature
    classes = tuple(signature.get("class_sequence") or ())
    tokens: set[str] = set()
    for left, right in zip(classes, classes[1:], strict=False):
        tokens.add(f"class_bigram={left}>{right}")
    for cls in classes:
        tokens.add(f"class_present={cls}")
    return tokens


def _type_shape_tokens(
    anchor_record: dict[str, Any], classifier: ActionClassifier | None
) -> set[str]:
    event_graph = anchor_record.get("event_graph")
    if isinstance(event_graph, dict) and event_graph.get("class_sequence"):
        classes = tuple(event_graph["class_sequence"])
        tokens: set[str] = set()
        for left, right in zip(classes, classes[1:], strict=False):
            tokens.add(f"class_bigram={left}>{right}")
        for cls in classes:
            tokens.add(f"class_present={cls}")
        return tokens
    return _class_shape_tokens(anchor_record.get("action_sequence"), classifier)


def unit_vocabulary_tokens(unit: GradeableUnit) -> set[str]:
    return _as_token_set(unit.vocabulary) | _as_token_set(unit.entities)


def _type_vocabulary_tokens(anchor_record: dict[str, Any]) -> set[str]:
    return _as_token_set(anchor_record.get("action_sequence")) | _as_token_set(
        anchor_record.get("parameter_families")
    )


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))


def _classify_distance(distance: float | None) -> str:
    if distance is None:
        return "NOT_AT_ALL"
    if distance <= EXACT_MAX_DISTANCE:
        return "EXACT"
    if distance <= SIMILAR_MAX_DISTANCE:
        return "SIMILAR"
    return "NOT_AT_ALL"


@dataclass(frozen=True)
class ChannelGrade:
    """One channel's directional grade. `distance is None` means
    unobservable (one side had nothing to compare), which is a distinct,
    honest state from a computed-but-large distance -- never conflated."""

    channel: str
    distance: float | None
    relation: str
    coverage: float
    shared_tokens: tuple[str, ...]
    diverging_tokens: tuple[str, ...]
    unobservable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "distance": self.distance,
            "relation": self.relation,
            "coverage": self.coverage,
            "shared_tokens": list(self.shared_tokens),
            "diverging_tokens": list(self.diverging_tokens),
            "unobservable": self.unobservable,
        }


def _grade_channel(channel: str, subject_tokens: set[str], type_tokens: set[str]) -> ChannelGrade:
    if not subject_tokens or not type_tokens:
        return ChannelGrade(
            channel=channel,
            distance=None,
            relation="NOT_AT_ALL",
            coverage=0.0,
            shared_tokens=(),
            diverging_tokens=tuple(sorted(subject_tokens | type_tokens)),
            unobservable=True,
        )
    distance = _jaccard_distance(subject_tokens, type_tokens)
    shared = subject_tokens & type_tokens
    diverging = subject_tokens ^ type_tokens
    return ChannelGrade(
        channel=channel,
        distance=distance,
        relation=_classify_distance(distance),
        coverage=1.0,
        shared_tokens=tuple(sorted(shared)),
        diverging_tokens=tuple(sorted(diverging)),
        unobservable=False,
    )


@dataclass(frozen=True)
class UnitTypeRelation:
    """The graded relation between one unit and one known type. `delta` is
    mandatory -- a relation without one is not a product an analyst can act
    on (carried from C.1 inversion 4)."""

    unit_id: str
    anchor_id: str
    shape: ChannelGrade
    vocabulary: ChannelGrade
    delta: dict[str, Any]
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def overall_relation(self) -> str:
        """The closer-matching channel decides the overall claim: same
        shape with divergent vocabulary is still `EXACT`/`SIMILAR` to the
        type -- that IS the unknown-instance signature this task exists to
        surface, not a reason to downgrade it toward `NOT_AT_ALL`."""
        order = {"EXACT": 0, "SIMILAR": 1, "NOT_AT_ALL": 2}
        return min((self.shape.relation, self.vocabulary.relation), key=lambda r: order[r])

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "anchor_id": self.anchor_id,
            "shape": self.shape.to_dict(),
            "vocabulary": self.vocabulary.to_dict(),
            "overall_relation": self.overall_relation,
            "delta": dict(self.delta),
            "algorithm_version": self.algorithm_version,
        }


def _build_delta(shape: ChannelGrade, vocabulary: ChannelGrade) -> dict[str, Any]:
    axis_of_divergence: str | None = None
    if shape.relation != "NOT_AT_ALL" and vocabulary.relation == "NOT_AT_ALL":
        axis_of_divergence = "vocabulary"
    elif vocabulary.relation != "NOT_AT_ALL" and shape.relation == "NOT_AT_ALL":
        axis_of_divergence = "shape"
    return {
        "shared_shape_features": list(shape.shared_tokens),
        "diverging_shape_features": list(shape.diverging_tokens),
        "shared_vocabulary_features": list(vocabulary.shared_tokens),
        "diverging_vocabulary_features": list(vocabulary.diverging_tokens),
        "axis_of_divergence": axis_of_divergence,
    }


def grade_unit_against_type(
    unit: GradeableUnit,
    anchor_record: dict[str, Any],
    *,
    classifier: ActionClassifier | None = None,
) -> UnitTypeRelation:
    shape = _grade_channel(
        "shape", unit_shape_tokens(unit), _type_shape_tokens(anchor_record, classifier)
    )
    vocabulary = _grade_channel(
        "vocabulary", unit_vocabulary_tokens(unit), _type_vocabulary_tokens(anchor_record)
    )
    return UnitTypeRelation(
        unit_id=unit.unit_id,
        anchor_id=str(anchor_record.get("record_id") or anchor_record.get("signature_id") or ""),
        shape=shape,
        vocabulary=vocabulary,
        delta=_build_delta(shape, vocabulary),
    )


def grade_unit_against_library(
    unit: GradeableUnit,
    anchor_records: list[dict[str, Any]],
    *,
    classifier: ActionClassifier | None = None,
) -> list[UnitTypeRelation]:
    """Every known type, graded against one unit -- no anchor is skipped or
    gated on coverage/pedigree (P2: the library is a reference frame, never
    a detection list)."""
    return [
        grade_unit_against_type(unit, record, classifier=classifier) for record in anchor_records
    ]
