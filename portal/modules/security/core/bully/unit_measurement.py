"""bully.unit_measurement -- the grading-plane measurement stack for the
unit-level pipeline (T.1-T.4, TASK_BULLY_UNKNOWN_COUSIN_V1).

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
from dataclasses import dataclass, field
from typing import Any

from .anchors import Anchor
from .artifact_graph import ActionClassifier, GradeableUnit
from .baseline import NormalBaseline
from .unit_outcome import CONCERN_OUTCOMES, UnitOutcome, resolve_unit_outcome


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


# ── T.4: leave-one-family-out -- the product test ──────────────────────────

# Controls, judgement calls recorded here and re-baselined only deliberately.
SHUFFLED_CONTROL_MAX_RATIO = 0.5
BENIGN_CONTROL_MAX_CONCERN_RATE = 0.3


def _concern_rate(
    units: list[GradeableUnit],
    library: list[Anchor],
    baseline: NormalBaseline,
    *,
    classifier: ActionClassifier | None,
) -> tuple[float, list[dict[str, Any]]]:
    if not units:
        return 0.0, []
    outcomes = [resolve_unit_outcome(u, library, baseline, classifier=classifier) for u in units]
    concerning = [o for o in outcomes if o.outcome in CONCERN_OUTCOMES]
    briefs = [o.brief.to_dict() for o in concerning if o.brief is not None]
    return len(concerning) / len(units), briefs


def _shuffled_library(library: list[Anchor], *, seed: int) -> list[Anchor]:
    """A permutation-test control: pool every anchor's `action_sequence`
    tokens across the *whole* library and redistribute them randomly,
    preserving each anchor's original sequence length. A per-anchor swap of
    whole records is not sufficient here -- grading matches on content, not
    identity, so swapping which anchor holds which already-coherent
    sequence leaves the set of matchable content completely unchanged and
    recall untouched. Shuffling the tokens themselves is what actually
    destroys the real correlation between a type's identity and its
    content, so a real signal must collapse."""
    rng = random.Random(seed)
    pool: list[str] = []
    lengths: list[int] = []
    for anchor in library:
        sequence = anchor.record.get("action_sequence") or []
        pool.extend(str(token) for token in sequence)
        lengths.append(len(sequence))
    rng.shuffle(pool)

    shuffled: list[Anchor] = []
    cursor = 0
    for anchor, length in zip(library, lengths, strict=False):
        new_sequence = pool[cursor : cursor + length]
        cursor += length
        record = dict(anchor.record)
        record["action_sequence"] = new_sequence
        shuffled.append(
            Anchor(
                anchor_id=anchor.anchor_id,
                kind=anchor.kind,
                record=record,
                provenance_tier=anchor.provenance_tier,
                label_basis=anchor.label_basis,
                grade=anchor.grade,
                source_id=anchor.source_id,
                malice=anchor.malice,
                derived_from=anchor.derived_from,
                generation_depth=anchor.generation_depth,
            )
        )
    return shuffled


@dataclass(frozen=True)
class FamilyResult:
    family: str
    n_eval_units: int
    unknown_cousin_recall: float
    sample_briefs: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "n_eval_units": self.n_eval_units,
            "unknown_cousin_recall": self.unknown_cousin_recall,
            "sample_briefs": list(self.sample_briefs),
        }


@dataclass(frozen=True)
class LeaveOneFamilyOutReport:
    """The headline measurement. `unknown_cousin_recall` is the product
    number: of instances from a technique family the library has never
    seen, what fraction still raised a concern naming a plausibly-related
    surviving type. `full_library_recall` is published beside it --
    full-library >> leave-one-out means the system is a matcher, and that
    must be stated plainly, not smoothed."""

    per_family: dict[str, FamilyResult]
    unknown_cousin_recall: float
    full_library_recall: float
    shuffled_control_recall: float
    benign_control_concern_rate: float
    controls_hold: bool
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_family": {k: v.to_dict() for k, v in self.per_family.items()},
            "unknown_cousin_recall": self.unknown_cousin_recall,
            "full_library_recall": self.full_library_recall,
            "shuffled_control_recall": self.shuffled_control_recall,
            "benign_control_concern_rate": self.benign_control_concern_rate,
            "controls_hold": self.controls_hold,
            "verdict": self.verdict,
            "matcher_warning": self.full_library_recall > 0
            and self.unknown_cousin_recall < 0.5 * self.full_library_recall,
        }


def run_leave_one_family_out(
    eval_units_by_family: dict[str, list[GradeableUnit]],
    library_by_family: dict[str, list[Anchor]],
    full_library: list[Anchor],
    baseline: NormalBaseline,
    *,
    benign_eval_units: list[GradeableUnit],
    classifier: ActionClassifier | None = None,
    shuffle_seed: int = 0,
) -> LeaveOneFamilyOutReport:
    """For each family, exclude every type belonging to it, refit nothing
    the caller has not already refit (`baseline`/`library_by_family` are the
    caller's post-exclusion state), and measure `unknown_cousin_recall` over
    that family's held-out evaluation units against everything else."""
    per_family: dict[str, FamilyResult] = {}
    all_eval_units: list[GradeableUnit] = []
    for family, units in eval_units_by_family.items():
        excluded_library = [
            anchor
            for fam, anchors in library_by_family.items()
            if fam != family
            for anchor in anchors
        ]
        recall, briefs = _concern_rate(units, excluded_library, baseline, classifier=classifier)
        per_family[family] = FamilyResult(
            family=family,
            n_eval_units=len(units),
            unknown_cousin_recall=recall,
            sample_briefs=tuple(briefs[:3]),
        )
        all_eval_units.extend(units)

    total_eval = sum(r.n_eval_units for r in per_family.values())
    unknown_cousin_recall = (
        sum(r.unknown_cousin_recall * r.n_eval_units for r in per_family.values()) / total_eval
        if total_eval
        else 0.0
    )

    full_recall, _ = _concern_rate(all_eval_units, full_library, baseline, classifier=classifier)

    shuffled = _shuffled_library(full_library, seed=shuffle_seed)
    shuffled_recall, _ = _concern_rate(all_eval_units, shuffled, baseline, classifier=classifier)

    benign_rate, _ = _concern_rate(benign_eval_units, full_library, baseline, classifier=classifier)

    shuffle_holds = shuffled_recall <= SHUFFLED_CONTROL_MAX_RATIO * max(
        unknown_cousin_recall, full_recall, 1e-9
    )
    benign_holds = benign_rate <= BENIGN_CONTROL_MAX_CONCERN_RATE
    controls_hold = shuffle_holds and benign_holds

    return LeaveOneFamilyOutReport(
        per_family=per_family,
        unknown_cousin_recall=unknown_cousin_recall,
        full_library_recall=full_recall,
        shuffled_control_recall=shuffled_recall,
        benign_control_concern_rate=benign_rate,
        controls_hold=controls_hold,
        verdict="VALID" if controls_hold else "INVALID",
    )
