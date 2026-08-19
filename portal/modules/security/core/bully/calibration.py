"""bully.calibration -- confidence calibration + downstream honouring
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 G.1, guards confidence-as-decoration).

A stated confidence must predict observed correctness. This module bins
relations by stated confidence, measures realised accuracy per bin on
score-eligible rows, and publishes a calibration curve + a Brier-style
score. Over-confidence (stated >> realised) blocks release of the relation
engine -- it is a defect, not a note (S4/S5). Downstream honouring:
escalation requires a confidence threshold *and* independent evidence; a
caller that ignores confidence is rejected here, not trusted to remember.

Pure compute over injected (confidence, correct) pairs -- no I/O, no
training (COLD). Calibration is always recomputed from whatever records the
caller passes; nothing here is a hand-set constant.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BIN_COUNT = 5
OVERCONFIDENCE_THRESHOLD = 0.20  # stated - realised, per bin, before it's a defect


@dataclass(frozen=True)
class ScoredRelation:
    confidence: float
    correct: bool


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float | None
    realised_accuracy: float | None

    @property
    def overconfident(self) -> bool:
        if self.mean_confidence is None or self.realised_accuracy is None:
            return False
        return (self.mean_confidence - self.realised_accuracy) > OVERCONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class CalibrationReport:
    bins: tuple[CalibrationBin, ...]
    brier_score: float | None
    scored_count: int
    overconfident: bool

    @property
    def blocks_release(self) -> bool:
        """Over-confidence blocks release of the relation engine (G.1) --
        never just a note in the report."""
        return self.overconfident


def brier_score(records: list[ScoredRelation]) -> float | None:
    if not records:
        return None
    return sum((r.confidence - float(r.correct)) ** 2 for r in records) / len(records)


def bin_by_confidence(
    records: list[ScoredRelation], *, bin_count: int = DEFAULT_BIN_COUNT
) -> tuple[CalibrationBin, ...]:
    width = 1.0 / bin_count
    bins: list[CalibrationBin] = []
    for i in range(bin_count):
        lower, upper = i * width, (i + 1) * width
        members = [
            r
            for r in records
            if lower <= r.confidence < upper or (upper == 1.0 and r.confidence == 1.0)
        ]
        if not members:
            bins.append(CalibrationBin(lower, upper, 0, None, None))
            continue
        mean_conf = sum(r.confidence for r in members) / len(members)
        accuracy = sum(1 for r in members if r.correct) / len(members)
        bins.append(CalibrationBin(lower, upper, len(members), mean_conf, accuracy))
    return tuple(bins)


def calibration_report(
    records: list[ScoredRelation], *, bin_count: int = DEFAULT_BIN_COUNT
) -> CalibrationReport:
    """Recomputed from `records` every call -- never a hand-set constant
    (S4/S5: calibration is measured, not assumed)."""
    bins = bin_by_confidence(records, bin_count=bin_count)
    return CalibrationReport(
        bins=bins,
        brier_score=brier_score(records),
        scored_count=len(records),
        overconfident=any(b.overconfident for b in bins),
    )


# ── downstream honouring: escalation requires threshold AND evidence ────────

ESCALATION_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class EscalationDecision:
    allowed: bool
    reasons: tuple[str, ...]


def gate_escalation(
    confidence: float,
    *,
    has_independent_evidence: bool,
    threshold: float = ESCALATION_CONFIDENCE_THRESHOLD,
) -> EscalationDecision:
    """A consumer that escalates on confidence alone -- or on evidence
    alone -- is ignoring the other half of the contract (G.1's "downstream
    honouring"); both are required."""
    reasons: list[str] = []
    if confidence < threshold:
        reasons.append(f"confidence {confidence:.2f} below threshold {threshold:.2f}")
    if not has_independent_evidence:
        reasons.append("no independent evidence")
    return EscalationDecision(allowed=not reasons, reasons=tuple(reasons))
