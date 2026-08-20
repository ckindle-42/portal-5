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

Pure compute over injected `GradeableUnit`s. No I/O, no model calls (COLD).
"""

from __future__ import annotations

from collections import Counter
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
    tokens.add(f"level={unit.level}")
    return tokens


@dataclass
class NormalBaseline:
    """A per-environment frequency model. `fit` observes units; its one job
    is `remarkability` -- how unusual a unit is for *this* environment. It
    is never used to classify a unit as a known type; that is the anchor
    library's job (`anchors.py`, N.1)."""

    environment_id: str
    _token_counts: Counter[str] = field(default_factory=Counter)
    _fitted_units: int = 0

    def fit(self, units: list[GradeableUnit]) -> None:
        for unit in units:
            self._fitted_units += 1
            for token in _feature_tokens(unit):
                self._token_counts[token] += 1

    @property
    def fitted_units(self) -> int:
        return self._fitted_units

    def token_frequency(self, token: str) -> float:
        if self._fitted_units == 0:
            return 0.0
        return self._token_counts.get(token, 0) / self._fitted_units

    def remarkability(self, unit: GradeableUnit) -> float:
        """1.0 minus the mean observed frequency of `unit`'s feature tokens.
        A token never seen in fitting contributes maximal (1.0) rarity, so a
        genuinely novel combination scores near 1.0 against a populated
        baseline, while a routine one -- built from tokens the environment
        produces constantly -- scores near 0.0. An empty baseline (nothing
        fitted yet) can never call anything remarkable: 0.0, not a crash and
        not a false positive."""
        if self._fitted_units == 0 or not (tokens := _feature_tokens(unit)):
            return 0.0
        rarities = [1.0 - self.token_frequency(t) for t in tokens]
        return sum(rarities) / len(rarities)

    def is_remarkable(
        self, unit: GradeableUnit, *, threshold: float = REMARKABLE_MIN_SCORE
    ) -> bool:
        return self.remarkability(unit) >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "fitted_units": self._fitted_units,
            "distinct_tokens": len(self._token_counts),
        }
