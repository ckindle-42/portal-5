"""bully.unit_measurement -- the grading-plane measurement stack for the
unit-level pipeline (T.1-T.3, TASK_BULLY_UNKNOWN_COUSIN_V1).

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

T.2 closes the other half of the same wall: attack_data seeds are drawn
from the same dataset root that built the anchors, so an "arrival" is
already in the type library before evaluation starts unless datasets are
explicitly split into a type half and an evaluation half. `HeldOutSplit`
makes that split a first-class, checkable object rather than an assumption.
"""

from __future__ import annotations

import random
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


class ContaminationError(ValueError):
    """Raised when an evaluation artifact's dataset also contributed a type
    -- the defect T.2 exists to catch, not silently tolerate."""


@dataclass(frozen=True)
class HeldOutSplit:
    """Dataset keys partitioned into a type-library half and an evaluation
    half. Disjoint by construction -- overlap is a contamination bug, not a
    valid split, so it raises rather than being silently allowed."""

    type_dataset_keys: frozenset[str]
    eval_dataset_keys: frozenset[str]

    def __post_init__(self) -> None:
        overlap = self.type_dataset_keys & self.eval_dataset_keys
        if overlap:
            raise ContaminationError(
                f"held-out split contaminated: datasets in both halves: {sorted(overlap)}"
            )

    def contaminates(self, evaluation_dataset_key: str) -> bool:
        """True if an evaluation artifact's dataset also contributed a type
        -- attack_data seeds drawn from the same root that built the
        anchors are already "in the library" before evaluation starts,
        unless this returns False for every evaluation artifact used."""
        return evaluation_dataset_key in self.type_dataset_keys


def split_datasets(
    dataset_keys: list[str], *, type_fraction: float = 0.5, seed: int = 0
) -> HeldOutSplit:
    """Deterministic (seeded) split of dataset keys into type-library and
    evaluation halves. Sorted before shuffling so the split is reproducible
    across runs regardless of input order."""
    ordered = sorted(set(dataset_keys))
    rng = random.Random(seed)
    rng.shuffle(ordered)
    cut = round(len(ordered) * type_fraction)
    return HeldOutSplit(
        type_dataset_keys=frozenset(ordered[:cut]), eval_dataset_keys=frozenset(ordered[cut:])
    )


def assert_no_contamination(evaluation_dataset_keys: list[str], split: HeldOutSplit) -> None:
    """Fails loudly on an unsplit or contaminated run rather than silently
    scoring against a library the evaluation data helped build."""
    offenders = [key for key in evaluation_dataset_keys if split.contaminates(key)]
    if offenders:
        raise ContaminationError(
            f"evaluation datasets also contributed a type: {sorted(set(offenders))}"
        )


# ── T.3: precision/recall per unit level and outcome class ─────────────────


def _level_report(rows: list[GradingPlaneRow]) -> dict[str, Any]:
    from collections import Counter

    outcome_counts = Counter(r.outcome.outcome for r in rows)
    true_positive = sum(1 for r in rows if r.expected_concern and r.correct)
    false_negative = sum(1 for r in rows if r.expected_concern and not r.correct)
    false_positive = sum(1 for r in rows if not r.expected_concern and not r.correct)
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else None
    )
    return {
        "n": len(rows),
        "outcome_distribution": dict(outcome_counts),
        "precision": precision,
        "recall": recall,
    }


def precision_recall_report(rows: list[GradingPlaneRow]) -> dict[str, Any]:
    """Real accuracy against the legend: per unit level and per outcome
    class, over scored rows only. `KNOWN_INSTANCE` is reported separately
    and labelled a floor metric (P1) -- it must never be read as the
    headline number."""
    scored = [r for r in rows if r.scored]
    levels = sorted({r.outcome.unit.level for r in scored})
    per_level = {
        level: _level_report([r for r in scored if r.outcome.unit.level == level])
        for level in levels
    }

    known_instance_rows = [r for r in scored if r.outcome.outcome == "KNOWN_INSTANCE"]
    return {
        "scored_count": len(scored),
        "unscored_count": len(rows) - len(scored),
        "per_level": per_level,
        "overall": _level_report(scored),
        "known_instance_floor": {
            "floor_metric": True,
            "note": "existing detection owns these; never the headline (P1)",
            "count": len(known_instance_rows),
            "fraction_of_scored": len(known_instance_rows) / len(scored) if scored else 0.0,
        },
    }
