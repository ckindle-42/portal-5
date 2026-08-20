"""bully.unit_measurement -- the grading-plane measurement stack for the
unit-level pipeline (T.1, TASK_BULLY_UNKNOWN_COUSIN_V1).

The sealed manifest legend (`scripts.corpus_ingest.load_manifest_catalog`)
carries real ATT&CK ground truth per dataset and is currently used only to
build anchors -- `ground_truth` never appears in `scripts/bully_relate_run.py`,
so `"scored"` there means `bool(ranked_external_cousins(...))`, a
*reachability* flag, not correctness. T.1 binds the legend to the
**arriving** side (which dataset/family a unit's records came from) for
scoring only, on the grading plane defined by this module.

The hard wall holds: `unit_outcome.resolve_unit_outcome` never receives this
binding. It grades a `GradeableUnit` against anchor content alone. Only
after an outcome exists does this module attach the arriving side's known
family/malice to it, purely to score the outcome after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .unit_outcome import CONCERN_OUTCOMES, UnitOutcome


@dataclass(frozen=True)
class GroundTruth:
    """What the sealed legend says about the arriving unit's source
    dataset -- bound after grading, never fed into it."""

    family: str | None
    malice: str  # "malicious" | "benign" | "unknown"

    @property
    def is_known(self) -> bool:
        return self.family is not None or self.malice != "unknown"


@dataclass(frozen=True)
class GradingPlaneRow:
    """One unit's outcome, bound to its arriving-side ground truth. This is
    the scoring plane's own object -- it is never handed to the grader."""

    outcome: UnitOutcome
    ground_truth: GroundTruth

    @property
    def scored(self) -> bool:
        """T.1's correction: `scored` means the legend actually knows what
        this arrival is, not merely that the grader found some ranked
        anchor to compare against."""
        return self.ground_truth.is_known

    @property
    def expected_concern(self) -> bool:
        """A malicious-family arrival should raise a concern
        (`UNKNOWN_SAME`/`COUSIN`/`NOVEL`) or be `KNOWN_INSTANCE`
        (still correctly identified, just via the floor); a benign one
        should not raise a concern at all."""
        return self.ground_truth.malice == "malicious"

    @property
    def correct(self) -> bool:
        if not self.scored:
            return False
        raised = (
            self.outcome.outcome in CONCERN_OUTCOMES or self.outcome.outcome == "KNOWN_INSTANCE"
        )
        if self.expected_concern:
            return raised
        return not raised

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.to_dict(),
            "ground_truth_family": self.ground_truth.family,
            "ground_truth_malice": self.ground_truth.malice,
            "scored": self.scored,
            "correct": self.correct if self.scored else None,
        }


def bind_ground_truth(
    outcome: UnitOutcome, *, family: str | None, malice: str = "unknown"
) -> GradingPlaneRow:
    """Attach the arriving side's known family/malice to an already-resolved
    outcome. Called once per unit, strictly after `resolve_unit_outcome` --
    the ordering itself is what keeps the hard wall honest."""
    return GradingPlaneRow(outcome=outcome, ground_truth=GroundTruth(family=family, malice=malice))
