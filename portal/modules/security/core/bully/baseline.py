"""bully.baseline -- the normal baseline: a frequency model over unit-level
features, scored against, never matched (N.2, TASK_BULLY_UNKNOWN_COUSIN_V1).

Known types (`anchors.py`) are patterns you can match. This is the other
kind of object: a per-environment distribution you can only score against.
You cannot match a distribution, and you cannot score against a pattern set
-- conflating them is what produced C.7's 79% `NOVEL_NOTABLE`: with no
baseline, every ordinary record was reported as notable novelty.

Fitted from observed data (the units actually seen in this environment),
never from the type library -- fitting from the anchors would just be
`cousin_relation.build_discriminative_index` wearing a different name, and
that is precisely the wrong corpus for "is this unusual for this
environment specifically."

RC3 (TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1, E.4) -- the M.3 run fit on
L1/L2 units and scored L4 units. `_feature_tokens` used to emit
`level={unit.level}` plus size/span/edge-kind buckets that L1/L2 units
structurally cannot produce (a single artifact has no multi-edge mix; a
bare pair has a narrow span range), so every scored L4 unit carried
never-seen tokens and scored ~0.95 remarkable regardless of content --
proven with this module's own code: fit N copies of a unit and score that
identical unit, and the *only* configuration that should return ~0.0
returned ~0.7 under the old tokens. That also means the M.3 conclusion that
invictus's benign control failing (1.0) was because the environment is
compromised was wrong -- perfectly clean data failed identically under a
fit/score level mismatch. The fix: drop the `level=` token, and partition
fitted statistics *by* `GradeableUnit.level` -- fit and score always
compare within the same level's pool, structurally, never across levels.
Scoring against a level nothing has been fitted for returns 0.0 honestly
(consistent with the existing "empty baseline never remarkable" rule, M.2
invariant #10) instead of a silent, content-independent 0.95. A caller that
wants a combination judged against genuinely comparable data fits that
level explicitly -- e.g. `individually_normal_case_surfaces` fits both its
L1_ARTIFACT baseline (individual artifacts are routine) and an L4_WINDOW
baseline of other, unrelated benign combinations, so the flagship
combination is judged remarkable *relative to normal combinations*, not by
an accidental level mismatch.

Pure compute over injected `GradeableUnit`s. No I/O, no model calls (COLD).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .artifact_graph import GradeableUnit

ALGORITHM_VERSION = "baseline-v1"

# `NOVEL` requires a *positive* remarkability signal, never mere absence of
# a match (M.2 invariant #10). This threshold is judgement, recorded on
# every relation; a change to it is a re-baseline, not a silent tune.
REMARKABLE_MIN_SCORE = 0.6

_SIZE_BUCKET_EDGES: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
_SPAN_BUCKET_EDGES: tuple[float, ...] = (0.0, 30.0, 120.0, 300.0, 900.0, 3600.0)


def _bucket(value: float, edges: tuple[float, ...]) -> str:
    for edge in edges:
        if value <= edge:
            return f"<={edge:g}"
    return f">{edges[-1]:g}"


def _feature_tokens(unit: GradeableUnit) -> set[str]:
    """Unit-level features the baseline fits over: action-class n-grams,
    entity-role profiles, unit size, span, and edge-kind mixes -- the same
    shape vocabulary U.1/U.2 already compute, never the anchor library."""
    tokens: set[str] = set()
    classes = tuple(unit.structural_signature.get("class_sequence") or ())
    for left, right in zip(classes, classes[1:], strict=False):
        tokens.add(f"class_bigram={left}>{right}")
    if len(classes) == 1:
        tokens.add(f"class_unigram={classes[0]}")
    for role in unit.structural_signature.get("entity_role_profile") or {}:
        tokens.add(f"entity_role={role}")
    tokens.add(f"size_bucket={_bucket(float(unit.size), _SIZE_BUCKET_EDGES)}")
    if unit.span_seconds is not None:
        tokens.add(f"span_bucket={_bucket(unit.span_seconds, _SPAN_BUCKET_EDGES)}")
    if unit.edge_kinds:
        tokens.add(f"edge_mix={'+'.join(sorted(unit.edge_kinds))}")
    return tokens


@dataclass
class NormalBaseline:
    """A per-environment frequency model. `fit` observes units; its one job
    is `remarkability` -- how unusual a unit is for *this* environment. It
    is never used to classify a unit as a known type; that is the anchor
    library's job (`anchors.py`, N.1).

    Statistics are partitioned by `GradeableUnit.level` (RC3, E.4):
    size/span/edge-kind buckets are level-dependent by construction (a
    single artifact has no multi-edge mix; a window has a wide span range),
    so comparing across levels always produced never-seen tokens and an
    inflated, content-independent remarkability regardless of what the
    scored unit actually contains. `fit` may be called with units from
    several levels (each call's batch is grouped internally); `remarkability`
    always compares a unit against *its own level's* pool, never another
    level's, so the level a unit is scored at can never itself manufacture
    remarkability."""

    environment_id: str
    _token_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    _fitted_units: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def fit(self, units: list[GradeableUnit]) -> None:
        for unit in units:
            self._fitted_units[unit.level] += 1
            for token in _feature_tokens(unit):
                self._token_counts[unit.level][token] += 1

    @property
    def fitted_units(self) -> int:
        return sum(self._fitted_units.values())

    def fitted_units_at(self, level: str) -> int:
        return self._fitted_units.get(level, 0)

    def token_frequency(self, token: str, *, level: str) -> float:
        fitted = self._fitted_units.get(level, 0)
        if fitted == 0:
            return 0.0
        return self._token_counts[level].get(token, 0) / fitted

    def remarkability(self, unit: GradeableUnit) -> float:
        """1.0 minus the mean observed frequency of `unit`'s feature tokens,
        computed against the pool fitted at `unit.level` only. A token never
        seen in that level's fitting contributes maximal (1.0) rarity, so a
        genuinely novel combination scores near 1.0 against a populated
        same-level baseline, while a routine one -- built from tokens the
        environment produces constantly at that level -- scores near 0.0.
        A level with nothing fitted yet can never call anything remarkable:
        0.0, not a crash, not a false positive, and never a level-mismatch
        floor (RC3)."""
        fitted = self._fitted_units.get(unit.level, 0)
        if fitted == 0 or not (tokens := _feature_tokens(unit)):
            return 0.0
        rarities = [1.0 - self.token_frequency(t, level=unit.level) for t in tokens]
        return sum(rarities) / len(rarities)

    def is_remarkable(
        self, unit: GradeableUnit, *, threshold: float = REMARKABLE_MIN_SCORE
    ) -> bool:
        return self.remarkability(unit) >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "fitted_units": self.fitted_units,
            "fitted_units_by_level": dict(self._fitted_units),
            "distinct_tokens": sum(len(c) for c in self._token_counts.values()),
        }
