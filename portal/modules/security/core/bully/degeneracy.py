"""bully.degeneracy -- anti-degeneracy guards for anomaly, uncertainty, and
density (TASK_BULLY_RELATE_AND_INVESTIGATE_V1 G.4, guards gaming the easy
outputs).

Three cheap ways the relation engine could look good while saying nothing,
each blocked here:

1. ANOMALOUS inflation -- monitored via a rate ceiling across a batch of
   relations (the per-call "requires a positive notability signal" rule
   already lives in `relation._is_notable_novelty`, A.3).
2. Boilerplate uncertainty -- `uncertainty_reasons` must vary with input; a
   near-constant reason set across a batch fails the variance check.
3. Anchor-density blindness -- confidence is capped by local anchor
   density, and a far-nearest-anchor forces ANOMALOUS rather than a
   stretched match (`apply_density_guard`, wired into `relation.relate`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DENSITY_FLOOR = 3
FAR_ANCHOR_DISTANCE = 0.9
ANOMALOUS_RATE_CEILING = 0.5
UNCERTAINTY_MAX_REPEAT_FRACTION = 0.8


# ── anchor-density blindness ──────────────────────────────────────────────


def density_capped_confidence(
    confidence: float, anchor_count: int, *, floor: int = DENSITY_FLOOR
) -> float:
    """A sparse region (fewer anchors considered than `floor`) cannot yield
    a confident relation -- confidence is capped at the density's own
    fraction of the floor, never left to the composite-distance math alone."""
    if anchor_count >= floor:
        return confidence
    return min(confidence, anchor_count / floor)


def apply_density_guard(
    verdict: str,
    confidence: float,
    nearest_distance: float | None,
    anchor_count: int,
    *,
    floor: int = DENSITY_FLOOR,
    far_distance: float = FAR_ANCHOR_DISTANCE,
) -> tuple[str, float]:
    """A far-nearest-anchor (the least-bad candidate is still very far)
    yields ANOMALOUS_UNCLASSIFIED rather than a stretched match -- guards
    anchor bias forcing, e.g., a cloud event to resemble a Windows
    technique just because that's all the library has."""
    capped = density_capped_confidence(confidence, anchor_count, floor=floor)
    if (
        verdict != "ANOMALOUS_UNCLASSIFIED"
        and nearest_distance is not None
        and nearest_distance >= far_distance
    ):
        return "ANOMALOUS_UNCLASSIFIED", capped
    return verdict, capped


# ── ANOMALOUS inflation: rate ceiling across a batch ─────────────────────


@dataclass(frozen=True)
class AnomalyRateFinding:
    rate: float
    ceiling: float
    exceeded: bool


def check_anomaly_rate(
    relations: list[Any], *, ceiling: float = ANOMALOUS_RATE_CEILING
) -> AnomalyRateFinding:
    if not relations:
        return AnomalyRateFinding(rate=0.0, ceiling=ceiling, exceeded=False)
    rate = sum(1 for r in relations if r.verdict == "ANOMALOUS_UNCLASSIFIED") / len(relations)
    return AnomalyRateFinding(rate=rate, ceiling=ceiling, exceeded=rate > ceiling)


# ── boilerplate uncertainty: variance check across a batch ──────────────


@dataclass(frozen=True)
class UncertaintyVarianceReport:
    distinct_reason_sets: int
    total: int
    max_repeat_fraction: float
    passes: bool
    per_group_max_repeat_fraction: dict[str, float] = field(default_factory=dict)


def _group_repeat_fraction(relations: list[Any]) -> float:
    if len(relations) < 2:
        return 0.0
    counts = Counter(frozenset(r.uncertainty_reasons) for r in relations)
    return counts.most_common(1)[0][1] / len(relations)


def check_uncertainty_variance(
    relations: list[Any],
    *,
    max_repeat_fraction: float = UNCERTAINTY_MAX_REPEAT_FRACTION,
    group_by: Callable[[Any], str] | None = None,
) -> UncertaintyVarianceReport:
    """Fails when the same reason set repeats for (almost) every relation
    regardless of input -- a sign the reasons are boilerplate, not derived
    from actual per-record missing dimensions/annotations.

    `group_by` (TASK_BULLY_COUSIN_RELATION_V1 C.3b) additionally runs the
    repeat-fraction check *within* each group (e.g. per source), failing if
    any single group is near-constant even when the batch as a whole looks
    varied. Varying only *by* source is exactly the boilerplate condition
    this guard exists to catch -- M.3 passed on 4 distinct reason sets that
    mapped 1:1 onto its 5 source schemas, which is schema variety, not
    content-driven variance.
    """
    if len(relations) < 2:
        return UncertaintyVarianceReport(
            distinct_reason_sets=len(relations),
            total=len(relations),
            max_repeat_fraction=0.0,
            passes=True,
            per_group_max_repeat_fraction={},
        )
    counts = Counter(frozenset(r.uncertainty_reasons) for r in relations)
    top_fraction = counts.most_common(1)[0][1] / len(relations)
    passes = top_fraction <= max_repeat_fraction

    per_group: dict[str, float] = {}
    if group_by is not None:
        groups: dict[str, list[Any]] = {}
        for relation in relations:
            groups.setdefault(group_by(relation), []).append(relation)
        for group_id, group_relations in groups.items():
            group_fraction = _group_repeat_fraction(group_relations)
            per_group[group_id] = group_fraction
            if group_fraction > max_repeat_fraction:
                passes = False

    return UncertaintyVarianceReport(
        distinct_reason_sets=len(counts),
        total=len(relations),
        max_repeat_fraction=top_fraction,
        passes=passes,
        per_group_max_repeat_fraction=per_group,
    )
