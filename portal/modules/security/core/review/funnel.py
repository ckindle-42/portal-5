"""review.funnel -- from every unit to the few an analyst should see, with no typed-in cutoffs.

Two channels, one mechanism:

* ``unusual``       -- how surprising the unit is *for this environment*
                       (``discovery.tail_remarkability`` x ``discovery.cohesion``), against a
                       baseline fit on benign data. Library-free: works on the hundredth schema.
* ``known_similar`` -- how close the unit is to the nearest known anchor (cosine of content
                       cards). This is the channel that finds cousins that are NOT unusual:
                       a known behavior in new clothes is often common-looking.

Each channel flags a unit iff its score exceeds the conformal ``(1 - alpha)`` quantile of the
scores benign calibration units obtained (``calibration``), per unit level. A unit raised by
either channel is a candidate; candidates rank by their smallest calibrated p-value. A channel
with no calibration for a level raises nothing for that level and says so
(``FunnelDecision.uncalibrated``) -- never a silent default threshold.

Why a measured funnel and not the library's defaults: the shipped ``discovery`` constants
(remarkability >= 0.6, cohesion >= 0.34), run over 6,605 benign-dominated synthetic units,
flagged 81 % of benign units and ranked implants at chance (AUROC 0.42-0.53). A funnel nobody
has measured on benign volume is a recall machine with no precision.

Observation plane: no label identifiers (see ``wall``).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..bully import artifact_graph as ag
from ..bully import baseline as baseline_mod
from ..bully import discovery
from .calibration import CalibrationSet, NullCalibration, fit_calibration

CHANNEL_UNUSUAL = "unusual"
CHANNEL_SIMILAR = "known_similar"


@dataclass(frozen=True)
class UnitScores:
    unit_id: str
    level: str
    unusual: float
    similar: float | None
    n_sources: int = 1


@dataclass(frozen=True)
class FunnelPolicy:
    """Operational settings, recorded in every stamp. ``alpha_*`` is the benign false-raise
    rate an analyst will accept per channel and level; ``levels`` are the unit levels that may
    raise a concern. The measurement plane chooses them from the recall-versus-false-raise
    curve -- they are not defaults to be trusted."""

    alpha_unusual: float
    alpha_similar: float
    levels: tuple[str, ...] = ("L2_ENTITY", "L3_CHAIN")


@dataclass(frozen=True)
class FunnelDecision:
    unit_id: str
    level: str
    unusual_p: float | None
    similar_p: float | None
    flagged_unusual: bool
    flagged_similar: bool
    n_sources: int = 1
    uncalibrated: tuple[str, ...] = field(default=())

    @property
    def flagged(self) -> bool:
        return self.flagged_unusual or self.flagged_similar

    @property
    def channels(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.flagged_unusual:
            out.append(CHANNEL_UNUSUAL)
        if self.flagged_similar:
            out.append(CHANNEL_SIMILAR)
        return tuple(out)

    @property
    def rank_p(self) -> float:
        ps = [
            p
            for p, on in (
                (self.unusual_p, self.flagged_unusual),
                (self.similar_p, self.flagged_similar),
            )
            if on and p is not None
        ]
        return min(ps) if ps else 1.0


def unusual_score(unit: ag.GradeableUnit, baseline: baseline_mod.NormalBaseline) -> float:
    """Tail remarkability damped by structural cohesion: an incoherent bucket of unrelated
    artifacts is not an episode, however rare its tokens."""
    return discovery.tail_remarkability(unit, baseline) * discovery.cohesion(unit)


def fit_baseline(
    units: Sequence[ag.GradeableUnit], environment_id: str
) -> baseline_mod.NormalBaseline:
    model = baseline_mod.NormalBaseline(environment_id=environment_id)
    for level in ag.UNIT_LEVELS:
        level_units = [u for u in units if u.level == level]
        if level_units:
            model.fit(level_units)
    return model


def baseline_to_dict(model: baseline_mod.NormalBaseline) -> dict[str, Any]:
    return {
        "environment_id": model.environment_id,
        "token_counts": {lvl: dict(c) for lvl, c in model._token_counts.items()},
        "fitted_units": dict(model._fitted_units),
    }


def baseline_from_dict(payload: dict[str, Any]) -> baseline_mod.NormalBaseline:
    model = baseline_mod.NormalBaseline(environment_id=str(payload["environment_id"]))
    for level, counts in payload["token_counts"].items():
        model._token_counts[level] = Counter({str(k): int(v) for k, v in counts.items()})
    for level, n in payload["fitted_units"].items():
        model._fitted_units[level] = int(n)
    return model


def split_units(
    units: Sequence[ag.GradeableUnit], *, salt: str = ""
) -> tuple[list[ag.GradeableUnit], list[ag.GradeableUnit]]:
    """Deterministic, content-addressed split into (baseline-fit, calibration) halves.

    A calibration sample must be held out from the model it calibrates, or in-sample tokens
    look common and every threshold is too lax."""
    fit_half: list[ag.GradeableUnit] = []
    cal_half: list[ag.GradeableUnit] = []
    for unit in units:
        digest = hashlib.sha256(f"{salt}|{unit.unit_id}".encode()).digest()[0]
        (fit_half if digest % 2 == 0 else cal_half).append(unit)
    return fit_half, cal_half


def calibrate(
    channel: str,
    level: str,
    null_scores: Sequence[float],
    alpha: float,
    *,
    basis: str,
    embedder_id: str = "",
    into: CalibrationSet | None = None,
) -> NullCalibration:
    cal = fit_calibration(channel, level, null_scores, alpha, basis=basis, embedder_id=embedder_id)
    if into is not None:
        into.put(cal)
    return cal


def decide(
    scores: Sequence[UnitScores], cals: CalibrationSet, policy: FunnelPolicy
) -> list[FunnelDecision]:
    out: list[FunnelDecision] = []
    for s in scores:
        if s.level not in policy.levels:
            continue
        missing: list[str] = []
        unusual_p: float | None = None
        similar_p: float | None = None
        flag_u = flag_s = False

        cal_u = cals.get(CHANNEL_UNUSUAL, s.level)
        if cal_u is None:
            missing.append(CHANNEL_UNUSUAL)
        else:
            unusual_p = cal_u.p_value(s.unusual)
            flag_u = cal_u.exceeds(s.unusual)

        if s.similar is not None:
            cal_s = cals.get(CHANNEL_SIMILAR, s.level)
            if cal_s is None:
                missing.append(CHANNEL_SIMILAR)
            else:
                similar_p = cal_s.p_value(s.similar)
                flag_s = cal_s.exceeds(s.similar)

        out.append(
            FunnelDecision(
                unit_id=s.unit_id,
                level=s.level,
                unusual_p=unusual_p,
                similar_p=similar_p,
                flagged_unusual=flag_u,
                flagged_similar=flag_s,
                n_sources=s.n_sources,
                uncalibrated=tuple(missing),
            )
        )
    return out


def rank(decisions: Sequence[FunnelDecision]) -> list[FunnelDecision]:
    """Flagged units first, smallest calibrated p first, then wider cross-source reach."""
    return sorted(
        decisions,
        key=lambda d: (not d.flagged, d.rank_p, -d.n_sources, d.unit_id),
    )
