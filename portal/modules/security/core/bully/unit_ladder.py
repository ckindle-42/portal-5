"""bully.unit_ladder -- combination-level falsification instrument
(M.1, TASK_BULLY_UNKNOWN_COUSIN_V1).

A report that can only produce numbers is not a verification (carried from
C.6's N5). This constructs ground truth at the **combination** level -- the
unit this whole task exists to make gradeable -- rather than at the single-
record level C.6 used:

    L0_IDENTITY          the unit, unchanged
    L1_SUBSTITUTION       one verb replaced
    L2_REORDERED          same verbs, different order (shape channel should
                           register the change; vocabulary should not --
                           Jaccard is order-invariant)
    L3_CROSS_VOCABULARY   same class shape, entirely disjoint literal verbs
                           (the U.3 seam's payoff, measured directly)
    L4_UNRELATED          nothing shared

Ground-truth distance should increase monotonically L0->L4
(`RHO_MONOTONICITY_FLOOR = 0.9`). A shuffled-rung-label control must
collapse that correlation; a deliberately broken grader must turn the
report `INVALID`, never a quietly wrong number.

Separately -- not part of the monotonic ladder, but the flagship claim this
whole task exists to verify -- a combination whose every individual
artifact is unremarkable must still surface as a concern at combination
level (`individually_normal_case_surfaces`).

Pure compute over constructed data (COLD).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Protocol

from scipy import stats

from .anchors import AnchorLibrary
from .artifact_graph import ActionClassifier, GradeableUnit, build_graph, enumerate_units
from .baseline import NormalBaseline
from .unit_outcome import CONCERN_OUTCOMES, resolve_unit_outcome
from .unit_relation import UnitTypeRelation, grade_unit_against_type

RHO_MONOTONICITY_FLOOR = 0.9
# Ratio, not an absolute ceiling: with only five rungs, the expected |rho|
# of a random label permutation is already ~0.4 (verified numerically over
# all 120 permutations of 5 items), so a fixed absolute ceiling like 0.3 is
# unreachable by construction and would make the control meaningless. The
# real signal must still collapse *relative to the true rho*.
SHUFFLE_COLLAPSE_MAX_RATIO = 0.7

RUNG_LEVELS: dict[str, int] = {
    "L0_IDENTITY": 0,
    "L1_SUBSTITUTION": 1,
    "L2_REORDERED": 2,
    "L3_CROSS_VOCABULARY": 3,
    "L4_UNRELATED": 4,
}


class GradeFn(Protocol):
    def __call__(
        self,
        unit: GradeableUnit,
        anchor_record: dict[str, Any],
        *,
        classifier: ActionClassifier | None = None,
    ) -> UnitTypeRelation: ...


_EPOCH_BASE = 1_700_000_000.0


def unit_from_verbs(verbs: list[str], *, entity: str) -> GradeableUnit:
    """`eventTime` must land in the epoch-plausible numeric range field-role
    inference (`field_roles._parse_time`) requires -- a bare small offset
    (`i * 40.0`) is structurally indistinguishable from a small-int field
    like a count or an EventID, which must never be misread as a
    timestamp."""
    records = [
        {"eventName": v, "user": entity, "eventTime": _EPOCH_BASE + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = build_graph(records)
    return next(u for u in enumerate_units(graph) if u.level == "L4_WINDOW")


@dataclass(frozen=True)
class Rung:
    rung: str
    level: int
    unit: GradeableUnit


def build_rungs(
    parent_verbs: list[str],
    *,
    substitution_verb: str,
    cross_vocabulary_verbs: list[str],
    unrelated_verbs: list[str],
) -> list[Rung]:
    """`cross_vocabulary_verbs` must classify to the same class sequence as
    `parent_verbs` under the deterministic classifier while sharing no
    literal token with it -- the caller constructs this pairing explicitly
    (there is no general inverse of the classifier)."""
    identity = unit_from_verbs(parent_verbs, entity="l0")
    substituted = [*parent_verbs[:-1], substitution_verb]
    reordered = list(reversed(parent_verbs))
    return [
        Rung("L0_IDENTITY", 0, identity),
        Rung("L1_SUBSTITUTION", 1, unit_from_verbs(substituted, entity="l1")),
        Rung("L2_REORDERED", 2, unit_from_verbs(reordered, entity="l2")),
        Rung("L3_CROSS_VOCABULARY", 3, unit_from_verbs(cross_vocabulary_verbs, entity="l3")),
        Rung("L4_UNRELATED", 4, unit_from_verbs(unrelated_verbs, entity="l4")),
    ]


def _combined_distance(relation: UnitTypeRelation) -> float:
    """Mean of the two channel distances, unobservable treated as maximal
    (1.0) -- reported for visibility, but no longer what the ladder is
    validated on (U.3', RC4): `combined_distance` was 0.9999 on the M.3 run
    while the variable that actually decides a unit's outcome
    (`shape_distance`) was non-monotone across the same rungs
    (0.0, 0.0, 0.571, 0.0, 1.0) -- the headline number said nothing about
    the variable the grader acts on."""
    distances = [
        d if d is not None else 1.0 for d in (relation.shape.distance, relation.vocabulary.distance)
    ]
    return sum(distances) / len(distances)


def _shape_distance(relation: UnitTypeRelation) -> float:
    """The deciding variable (RC4): `resolve_unit_outcome` classifies
    EXACT/SIMILAR/NONE off `relation.shape`, never off the combined mean.
    Unobservable is still treated as maximal (1.0), matching
    `_combined_distance`'s convention, so the two scales stay comparable."""
    return relation.shape.distance if relation.shape.distance is not None else 1.0


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    rho, _p = stats.spearmanr(xs, ys)
    if rho != rho:  # NaN guard
        return None
    return float(rho)


def run_ladder(
    parent_type_record: dict[str, Any],
    rungs: list[Rung],
    *,
    grade_fn: GradeFn = grade_unit_against_type,
    shuffle_seed: int = 0,
) -> dict[str, Any]:
    """Grade every rung against `parent_type_record`, check monotonicity,
    the shuffle control, the negative control (L4 must be the farthest
    rung), and report VALID/INVALID -- never numbers alone.

    Validated on `shape_distance` (RC4, U.3'): that is the variable
    `UnitTypeRelation.overall_relation` -- and so `resolve_unit_outcome` --
    actually decides on (the closer-matching channel wins; shape alone can
    make a relation EXACT/SIMILAR). `combined_distance` is still published
    per rung for reference, but a report validated on it can look perfect
    (rho 0.9999 on the M.3 run) while the deciding variable is non-monotone
    underneath, which is exactly what happened."""
    levels: list[float] = []
    shape_distances: list[float] = []
    per_rung: dict[str, dict[str, Any]] = {}
    for rung in rungs:
        relation = grade_fn(rung.unit, parent_type_record)
        shape_distance = _shape_distance(relation)
        levels.append(float(rung.level))
        shape_distances.append(shape_distance)
        per_rung[rung.rung] = {
            "level": rung.level,
            "combined_distance": _combined_distance(relation),
            "shape_distance": relation.shape.distance,
            "shape_distance_validated": shape_distance,
            "vocabulary_distance": relation.vocabulary.distance,
            "overall_relation": relation.overall_relation,
        }

    rho = _spearman(levels, shape_distances)
    monotonicity_valid = rho is not None and rho >= RHO_MONOTONICITY_FLOOR

    # A single shuffle of this few rungs has high variance -- average the
    # magnitude over many independent shuffles rather than risk one lucky
    # (or unlucky) draw deciding the control.
    rng = random.Random(shuffle_seed)
    trial_rhos: list[float] = []
    for _ in range(50):
        shuffled_levels = levels[:]
        rng.shuffle(shuffled_levels)
        trial_rho = _spearman(shuffled_levels, shape_distances)
        if trial_rho is not None:
            trial_rhos.append(abs(trial_rho))
    shuffled_rho = (sum(trial_rhos) / len(trial_rhos)) if trial_rhos else None
    shuffle_collapsed = shuffled_rho is None or (
        rho is not None and shuffled_rho <= SHUFFLE_COLLAPSE_MAX_RATIO * abs(rho)
    )

    unrelated_entry = per_rung.get("L4_UNRELATED")
    negative_control_holds = unrelated_entry is not None and unrelated_entry[
        "shape_distance_validated"
    ] == max(shape_distances)

    valid = monotonicity_valid and shuffle_collapsed and negative_control_holds
    return {
        "per_rung": per_rung,
        "rho": rho,
        "shuffled_rho": shuffled_rho,
        "monotonicity_valid": monotonicity_valid,
        "shuffle_collapsed": shuffle_collapsed,
        "negative_control_holds": negative_control_holds,
        "verdict": "VALID" if valid else "INVALID",
        "validated_variable": "shape_distance",
    }


def individually_normal_case_surfaces(
    artifact_verbs: list[str],
    *,
    library: AnchorLibrary,
    baseline: NormalBaseline,
    entity: str = "combo-actor",
) -> dict[str, Any]:
    """The flagship claim: build a chain from `artifact_verbs`, confirm
    every one of its L1_ARTIFACT units is individually `NORMAL`, then
    confirm the L4_WINDOW combination still raises a concern. `False` here
    is the single most important failure this instrument can report.

    `baseline` must carry fitted statistics at *both* levels (RC3, E.4):
    L1_ARTIFACT so the individual-normalcy check means something, and
    L4_WINDOW -- from other, unrelated benign combinations -- so the
    flagship combination is judged remarkable relative to genuinely normal
    combinations, never by an accidental level mismatch. A baseline with no
    L4_WINDOW data fitted will honestly score the combination 0.0 remarkable
    (never a silent floor), which correctly fails this claim rather than
    faking success."""
    records = [
        {"eventName": v, "user": entity, "eventTime": _EPOCH_BASE + i * 40.0}
        for i, v in enumerate(artifact_verbs)
    ]
    graph = build_graph(records)
    units = enumerate_units(graph)

    individual_units = [u for u in units if u.level == "L1_ARTIFACT"]
    combination_unit = next(u for u in units if u.level == "L4_WINDOW")

    individual_outcomes = [
        resolve_unit_outcome(u, list(library.all()), baseline) for u in individual_units
    ]
    combination_outcome = resolve_unit_outcome(combination_unit, list(library.all()), baseline)

    all_individually_normal = all(o.outcome == "NORMAL" for o in individual_outcomes)
    combination_surfaces = combination_outcome.outcome in CONCERN_OUTCOMES

    return {
        "all_individually_normal": all_individually_normal,
        "individual_outcomes": [o.outcome for o in individual_outcomes],
        "combination_outcome": combination_outcome.outcome,
        "combination_surfaces": combination_surfaces,
        "passes": all_individually_normal and combination_surfaces,
    }
