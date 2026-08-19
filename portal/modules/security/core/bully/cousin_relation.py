"""bully.cousin_relation -- the observed-mode cousin grader
(TASK_BULLY_COUSIN_RELATION_V1 C.1).

The product is the *cousin*: "you will not always know what this is, but is
it like something we know, and how does it differ?" Known-bad matching is
the floor and is already solved -- if a thing is defined we can find it.
This module exists for the undefined thing that is nonetheless related.

Why this is a separate grader and not a `cousin_engine` retrofit: the
provoked path's core invariant (I-6 -- a missing dimension is a *failure*,
distances are never renormalized) is correct when subject and reference are
both episodes in one feature space (parent -> mutated child). Observed mode
compares a sparse, heterogeneous *arrival* against a richly-labelled
*anchor*: there, a missing dimension means "we hold a partial view", not
"the harness failed". Those are opposite semantics for the same word, and
overloading one function with both is what made every real arrival grade
`ANOMALOUS_UNCLASSIFIED` before any content was compared. `cousin_engine`
is left untouched; the provoked path keeps its invariant.

Five inversions relative to the provoked grader:

1. **Normalized distance.** `D = sum(w_i*d_i) / sum(w_i)` over the axes the
   two sides actually share, so distance is comparable across sources with
   different schemas. The provoked composite (unnormalized) ranges over
   [0, mass], which makes a sparse source's distance silently incomparable
   with a rich source's.
2. **Coverage is an annotation, never a gate.** The shared weight-mass is
   reported as `coverage` and dampens `confidence`; it never refuses a
   classification. (S1: annotate and degrade honestly, never deny use.)
3. **Directional and asymmetric.** An axis the *arrival* cannot speak to is
   `unobservable` -- excluded and itemised, never a penalty. In particular
   the `attack` axis is never required of the arrival: technique identity
   is what relating is meant to *produce*, so requiring it as an input is
   circular. A technique-labelled anchor instead yields
   `hypothesized_techniques` as an output.
4. **The delta is mandatory.** Every cousin states what is shared, what
   diverges, and on which axis. A relation without a delta is not a
   product an analyst can act on.
5. **Divergence can raise interest.** Shared features are weighted by
   discriminative power (IDF over the anchor corpus), so a rare motif held
   in common amid broad divergence scores as a strong cousin -- the exact
   case fixed global axis weights cannot express.

`INSUFFICIENT_VIEW` (we could not compute a relation) and `NOVEL_NOTABLE`
(we computed one and it matches nothing, but the thing is distinctive) are
separate statuses. Collapsing them -- as `ANOMALOUS_UNCLASSIFIED` did --
hides instrument failure inside what looks like a discovery.

Pure compute over injected data: no network, no model calls, no training
(COLD).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "cousin-relation-v1"

# Axis weights are shared with the provoked grader's vocabulary so the two
# remain comparable in review; the *arithmetic* over them differs (normalized
# here, deliberately unnormalized there).
AXIS_WEIGHTS: dict[str, float] = {
    "behavior": 0.30,
    "telemetry": 0.20,
    "semantic": 0.25,
    "attack": 0.15,
    "context": 0.10,
}

AXES: tuple[str, ...] = tuple(AXIS_WEIGHTS)

# A cousin is a *graded* relation, not a band membership. This bound only
# separates "close enough to be worth naming a parent" from "far from
# everything"; it is recorded in every report and a change to it is a
# re-baseline, not a tweak.
COUSIN_MAX_DISTANCE = 0.75

# NOVEL_NOTABLE requires a *positive* signal -- distinctive content -- never
# mere absence of a match (that would be anomaly inflation).
NOVELTY_MIN_DISTINCTIVENESS = 0.35

STATUSES: tuple[str, ...] = (
    "COUSIN_CANDIDATE",
    "NOVEL_NOTABLE",
    "INSUFFICIENT_VIEW",
    "NO_RELATION",
)

# Advisory labels for humans reading a distance. Derived downstream, never
# used to gate anything -- the distance and the delta are the product.
_LABEL_BANDS: tuple[tuple[float, str], ...] = (
    (0.05, "SAME"),
    (0.30, "NEAR_COUSIN"),
    (0.55, "COUSIN"),
    (0.75, "DISTANT_COUSIN"),
)


def derive_label(distance: float | None) -> str:
    """Human-facing band for a normalized distance. Advisory only: nothing
    in this module branches on the result."""
    if distance is None:
        return "UNCOMPUTED"
    for upper, label in _LABEL_BANDS:
        if distance <= upper:
            return label
    return "UNRELATED"


# ── feature extraction ─────────────────────────────────────────────────────


def _as_token_set(value: Any) -> set[str]:
    """Flatten any signature/record field into comparable string tokens."""
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


def _subject_axis_features(subject: Any) -> dict[str, set[str]]:
    attack = {
        str(m.get("technique_id"))
        for m in (getattr(subject, "attack_mappings", None) or [])
        if isinstance(m, dict) and m.get("technique_id")
    }
    return {
        "behavior": _as_token_set(getattr(subject, "action_sequence", None)),
        "telemetry": _as_token_set(getattr(subject, "telemetry_shape", None)),
        "semantic": _as_token_set(getattr(subject, "parameter_families", None))
        | _as_token_set(getattr(subject, "event_graph", None)),
        "attack": attack,
        "context": _as_token_set(getattr(subject, "context_topology", None)),
    }


def _anchor_axis_features(record: dict[str, Any]) -> dict[str, set[str]]:
    raw_attack = record.get("attack_mappings") or record.get("technique_ids") or []
    attack = {
        str(m.get("technique_id")) if isinstance(m, dict) else str(m)
        for m in raw_attack
        if (m.get("technique_id") if isinstance(m, dict) else m)
    }
    behavior = _as_token_set(record.get("action_sequence")) or _as_token_set(
        (record.get("behavior_sequence") or "").split()
    )
    return {
        "behavior": behavior,
        "telemetry": _as_token_set(record.get("telemetry_shape")),
        "semantic": _as_token_set(record.get("parameter_families"))
        | _as_token_set(record.get("event_graph")),
        "attack": attack,
        "context": _as_token_set(record.get("context_topology")),
    }


def _jaccard_distance(a: set[str], b: set[str], index: DiscriminativeIndex | None = None) -> float:
    """Salience-weighted Jaccard distance.

    With an index, tokens are weighted by discriminative power, so a rare
    motif held in common closes more distance than a boilerplate one that
    every anchor carries. This is inversion 5: divergence alone must not
    dominate when what *is* shared is highly informative. Without an index
    it degrades to plain set Jaccard.
    """
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    if index is None:
        return 1.0 - (len(a & b) / len(union))
    union_salience = index.salience(union)
    if union_salience <= 0:
        return 1.0 - (len(a & b) / len(union))
    return 1.0 - (index.salience(a & b) / union_salience)


# ── discriminative weighting: rare shared features matter more ─────────────


@dataclass(frozen=True)
class DiscriminativeIndex:
    """IDF over the anchor corpus. A feature held by nearly every anchor
    explains nothing; a rare one held in common is the strongest cousin
    signal there is."""

    idf: dict[str, float]
    anchor_count: int

    def weight(self, token: str) -> float:
        return self.idf.get(token, self.default_weight)

    @property
    def default_weight(self) -> float:
        """An unseen token is maximally rare, hence maximally informative.
        Deliberately the df=0 evaluation of the same idf formula used in
        `build_discriminative_index`, so no in-index token can ever exceed
        it and `distinctiveness` stays bounded in [0, 1]."""
        if not self.anchor_count:
            return 1.0
        return math.log((self.anchor_count + 1) / 1.0) + 1.0

    def salience(self, tokens: set[str]) -> float:
        return sum(self.weight(t) for t in tokens)


def build_discriminative_index(anchor_records: list[dict[str, Any]]) -> DiscriminativeIndex:
    document_frequency: dict[str, int] = {}
    for record in anchor_records:
        tokens: set[str] = set()
        for axis_tokens in _anchor_axis_features(record).values():
            tokens |= axis_tokens
        for token in tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1
    total = len(anchor_records)
    idf = {
        token: math.log((total + 1) / (count + 1)) + 1.0
        for token, count in document_frequency.items()
    }
    return DiscriminativeIndex(idf=idf, anchor_count=total)


# ── the relation product ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RelationDelta:
    """What is shared, what diverges, and where. Mandatory on every emitted
    cousin -- this is the content an analyst acts on."""

    shared_features: tuple[str, ...]
    diverging_features: tuple[str, ...]
    axis_of_divergence: str | None
    unobservable_dimensions: tuple[str, ...]
    unanchored_dimensions: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.shared_features and not self.diverging_features

    def to_dict(self) -> dict[str, Any]:
        return {
            "shared_features": list(self.shared_features),
            "diverging_features": list(self.diverging_features),
            "axis_of_divergence": self.axis_of_divergence,
            "unobservable_dimensions": list(self.unobservable_dimensions),
            "unanchored_dimensions": list(self.unanchored_dimensions),
        }


@dataclass(frozen=True)
class CousinRelation:
    """The graded relation. `distance` + `delta` are the product; `status`
    and `label` are conveniences derived from them."""

    relation_id: str
    subject_id: str
    anchor_id: str | None
    distance: float | None
    status: str
    coverage: float
    confidence: float
    distinctiveness: float
    shared_salience: float
    delta: RelationDelta
    hypothesized_techniques: tuple[str, ...]
    axis_distances: dict[str, float | None]
    shared_dimensions: tuple[str, ...]
    ranked_cousins: tuple[tuple[str, float], ...]
    uncertainty_reasons: tuple[str, ...]
    anchors_considered: int
    algorithm_version: str = ALGORITHM_VERSION
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return derive_label(self.distance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "subject_id": self.subject_id,
            "anchor_id": self.anchor_id,
            "distance": self.distance,
            "label": self.label,
            "status": self.status,
            "coverage": self.coverage,
            "confidence": self.confidence,
            "distinctiveness": self.distinctiveness,
            "shared_salience": self.shared_salience,
            "delta": self.delta.to_dict(),
            "hypothesized_techniques": list(self.hypothesized_techniques),
            "axis_distances": dict(self.axis_distances),
            "shared_dimensions": list(self.shared_dimensions),
            "ranked_cousins": [list(pair) for pair in self.ranked_cousins],
            "uncertainty_reasons": list(self.uncertainty_reasons),
            "anchors_considered": self.anchors_considered,
            "algorithm_version": self.algorithm_version,
            "thresholds": dict(self.thresholds),
        }


@dataclass(frozen=True)
class _PairGrade:
    anchor_id: str
    distance: float | None
    coverage: float
    axis_distances: dict[str, float | None]
    shared_dimensions: tuple[str, ...]
    unobservable: tuple[str, ...]
    unanchored: tuple[str, ...]
    shared_tokens: set[str]
    diverging_tokens: set[str]
    hypothesized_techniques: tuple[str, ...]
    axis_of_divergence: str | None


def grade_pair(
    subject_features: dict[str, set[str]],
    anchor_record: dict[str, Any],
    *,
    anchor_id: str,
    index: DiscriminativeIndex | None = None,
) -> _PairGrade:
    """Directional grade of one arrival against one anchor.

    A dimension the arrival lacks is `unobservable` -- excluded from the
    distance and itemised, never charged as distance or as a penalty. A
    dimension the anchor lacks is `unanchored`. The distance is normalized
    over what remains, so it is comparable with any other pair's distance
    regardless of how much each side happened to carry.
    """
    anchor_features = _anchor_axis_features(anchor_record)
    axis_distances: dict[str, float | None] = {}
    shared_dimensions: list[str] = []
    unobservable: list[str] = []
    unanchored: list[str] = []
    shared_tokens: set[str] = set()
    diverging_tokens: set[str] = set()

    weighted_sum = 0.0
    weight_mass = 0.0

    for axis in AXES:
        subject_tokens = subject_features.get(axis) or set()
        anchor_tokens = anchor_features.get(axis) or set()
        if not subject_tokens:
            axis_distances[axis] = None
            unobservable.append(axis)
            continue
        if not anchor_tokens:
            axis_distances[axis] = None
            unanchored.append(axis)
            continue
        distance = _jaccard_distance(subject_tokens, anchor_tokens, index)
        axis_distances[axis] = distance
        shared_dimensions.append(axis)
        weight = AXIS_WEIGHTS[axis]
        weighted_sum += weight * distance
        weight_mass += weight
        shared_tokens |= subject_tokens & anchor_tokens
        diverging_tokens |= subject_tokens ^ anchor_tokens

    # Normalized: comparable across sources. `coverage` carries the "how
    # much of the picture did we actually see" information separately.
    pair_distance: float | None = (weighted_sum / weight_mass) if weight_mass else None
    coverage = weight_mass  # already in [0, 1]: AXIS_WEIGHTS sums to 1.0

    # The attack axis is an OUTPUT, never an input requirement: when the
    # anchor is technique-labelled and the arrival is not, that label is the
    # hypothesis the relation produces.
    hypothesized: tuple[str, ...] = ()
    if not (subject_features.get("attack") or set()):
        hypothesized = tuple(sorted(anchor_features.get("attack") or set()))

    graded = {a: d for a, d in axis_distances.items() if d is not None}
    axis_of_divergence = max(graded, key=lambda a: graded[a]) if graded else None

    return _PairGrade(
        anchor_id=anchor_id,
        distance=pair_distance,
        coverage=coverage,
        axis_distances=axis_distances,
        shared_dimensions=tuple(shared_dimensions),
        unobservable=tuple(unobservable),
        unanchored=tuple(unanchored),
        shared_tokens=shared_tokens,
        diverging_tokens=diverging_tokens,
        hypothesized_techniques=hypothesized,
        axis_of_divergence=axis_of_divergence,
    )


def _uncertainty_reasons(
    best: _PairGrade | None,
    *,
    distinctiveness: float,
    anchors_considered: int,
    margin: float | None,
) -> tuple[str, ...]:
    """Itemised and derived from this specific pair -- never a constant set.
    Reasons must vary with input *within* one source, not merely across
    sources (which schema shape alone would satisfy)."""
    reasons: list[str] = []
    if best is None:
        return ("no_comparable_anchor:relation_uncomputable",)
    for axis in best.unobservable:
        reasons.append(f"unobservable_dimension:{axis}")
    for axis in best.unanchored:
        reasons.append(f"unanchored_dimension:{axis}")
    if best.coverage < 0.5:
        reasons.append(f"partial_view:coverage_{best.coverage:.2f}")
    if margin is not None and margin < 0.05:
        reasons.append(f"ambiguous_parent:margin_{margin:.3f}")
    if best.axis_of_divergence:
        reasons.append(f"divergence_axis:{best.axis_of_divergence}")
    if anchors_considered < 3:
        reasons.append(f"thin_anchor_coverage:{anchors_considered}")
    if distinctiveness < NOVELTY_MIN_DISTINCTIVENESS:
        reasons.append(f"low_distinctiveness:{distinctiveness:.2f}")
    return tuple(reasons)


def relate_cousin(
    subject: Any,
    anchor_records: list[dict[str, Any]],
    *,
    index: DiscriminativeIndex | None = None,
    subject_id: str | None = None,
    top_k: int = 5,
    cousin_max_distance: float = COUSIN_MAX_DISTANCE,
    novelty_min_distinctiveness: float = NOVELTY_MIN_DISTINCTIVENESS,
) -> CousinRelation:
    """Grade one arrival against every anchor and emit the graded relation.

    No gate anywhere refuses to classify on coverage, schema shape, channel
    count, or label pedigree. Where a relation cannot be computed at all --
    no anchor shares a single dimension with the arrival -- that is reported
    as `INSUFFICIENT_VIEW`, which is an instrument finding, explicitly not
    the same thing as `NOVEL_NOTABLE`.
    """
    index = index if index is not None else build_discriminative_index(anchor_records)
    subject_features = _subject_axis_features(subject)
    subject_tokens: set[str] = set()
    for tokens in subject_features.values():
        subject_tokens |= tokens

    grades: list[_PairGrade] = []
    for record in anchor_records:
        anchor_id = str(record.get("record_id") or record.get("signature_id") or "")
        grade = grade_pair(subject_features, record, anchor_id=anchor_id, index=index)
        if grade.distance is not None:
            grades.append(grade)

    grades.sort(key=lambda g: (g.distance if g.distance is not None else 1.0, g.anchor_id))
    best = grades[0] if grades else None
    ranked = tuple(
        (g.anchor_id, round(g.distance, 6)) for g in grades[:top_k] if g.distance is not None
    )

    # Distinctiveness: how unusual is this arrival at all, independent of
    # whether anything matched. This is the positive signal NOVEL_NOTABLE
    # requires -- absence of a match alone can never produce it.
    total_salience = index.salience(subject_tokens)
    max_possible = index.default_weight * len(subject_tokens) if subject_tokens else 0.0
    distinctiveness = min(1.0, total_salience / max_possible) if max_possible else 0.0

    shared_salience = 0.0
    if best is not None and total_salience > 0:
        shared_salience = index.salience(best.shared_tokens) / total_salience

    margin: float | None = None
    if len(grades) >= 2 and grades[0].distance is not None and grades[1].distance is not None:
        margin = grades[1].distance - grades[0].distance

    # Confidence predicts whether the *cousin claim* is right. It is a
    # distinct quantity from coverage: coverage only dampens it, and can
    # never by itself decide a status.
    if best is None:
        confidence = 0.0
    else:
        margin_factor = 1.0 if margin is None else min(1.0, 0.5 + margin * 5.0)
        proximity = 1.0 - (best.distance if best.distance is not None else 1.0)
        confidence = proximity * margin_factor * (0.5 + 0.5 * best.coverage)
        confidence = max(0.0, min(1.0, confidence))

    if best is None:
        status = "INSUFFICIENT_VIEW"
    elif best.distance is not None and best.distance <= cousin_max_distance:
        status = "COUSIN_CANDIDATE"
    elif distinctiveness >= novelty_min_distinctiveness:
        status = "NOVEL_NOTABLE"
    else:
        status = "NO_RELATION"

    # Overclaim guard: a nearest-but-far anchor is not a parent. Outside
    # COUSIN_CANDIDATE we publish the distance profile (`ranked_cousins`,
    # `distance`) but name no parent and hypothesize no technique -- that
    # is exactly the anchor-bias forcing that makes a cloud event "resemble"
    # a Windows technique because the library holds nothing else.
    is_cousin = status == "COUSIN_CANDIDATE"
    claimed_anchor_id = best.anchor_id if (best and is_cousin) else None
    claimed_techniques = best.hypothesized_techniques if (best and is_cousin) else ()

    delta = RelationDelta(
        shared_features=tuple(sorted(best.shared_tokens)[:32]) if best else (),
        diverging_features=tuple(sorted(best.diverging_tokens)[:32]) if best else (),
        axis_of_divergence=(best.axis_of_divergence if (best and is_cousin) else None),
        unobservable_dimensions=best.unobservable if best else tuple(AXES),
        unanchored_dimensions=best.unanchored if best else (),
    )

    return CousinRelation(
        relation_id=f"cr-{uuid.uuid4().hex[:12]}",
        subject_id=subject_id or str(getattr(subject, "signature_id", "")),
        anchor_id=claimed_anchor_id,
        distance=best.distance if best else None,
        status=status,
        coverage=best.coverage if best else 0.0,
        confidence=confidence,
        distinctiveness=distinctiveness,
        shared_salience=shared_salience,
        delta=delta,
        hypothesized_techniques=claimed_techniques,
        axis_distances=dict(best.axis_distances) if best else dict.fromkeys(AXES),
        shared_dimensions=best.shared_dimensions if best else (),
        ranked_cousins=ranked,
        uncertainty_reasons=_uncertainty_reasons(
            best,
            distinctiveness=distinctiveness,
            anchors_considered=len(grades),
            margin=margin,
        ),
        anchors_considered=len(grades),
        thresholds={
            "cousin_max_distance": cousin_max_distance,
            "novelty_min_distinctiveness": novelty_min_distinctiveness,
        },
    )
