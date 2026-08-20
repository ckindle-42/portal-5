"""bully.truth_acceptance -- acceptance measured against sealed truth, never
against the system's own output.

The X.6 run passed every acceptance criterion while detecting nothing. Its
own `per_row` carried `implant_class_ground_truth`, and the cross-tabulation
against what the grader said is unambiguous:

    ground truth        SAME   SIMILAR   ANOMALOUS
    background (c1)      161       139           0
    background (c2)      196       102           2

**Every graded entity was `background`. Not one implant appeared in either
cycle.** False-positive rate 100%, true-positive rate 0% -- and the grader
called 161 pieces of benign noise exact matches to known attack techniques.

The criterion that passed was `both_classes_notified` -- it checked that the
*grader's own labels* split into known_bad and unknown_cousin. That is
satisfiable by a run which detects nothing at all, because it compares the
system against itself. The sealed-truth column sat in the same file and no
check consulted it.

This module makes that structurally impossible. Every acceptance number here
is a join against sealed truth:

  - `detection_report` -- TP/FP/FN per implant class, with precision, recall,
    and the false-positive rate on background as first-class. A run whose
    graded population contains **no implants at all** is `INVALID`, not a
    pass: it measured background and can say nothing about detection.
  - `selection_report` -- did truth-bearing entities even reach the grader?
    X.6's implants were shipped (`all_ok: true`) but never selected, because
    `assemble_timelines` sorts richest-first and a ~1% needle never wins that
    sort. Selection bias that silently excludes every implant is the failure
    that invalidated the run, and it is invisible unless measured.
  - `poisoning_report` -- an analyst verdict of CONFIRMED on a `background`
    entity writes a benign pattern into the library as ANALYST_CONFIRMED
    malicious knowledge. X.6 did this, which is why cycle 2 matched MORE
    background as SAME (161 -> 196). Write-back must be checked against truth
    in any run using scripted verdicts.

Pure compute over a run's rows (COLD). No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "truth-acceptance-v1"

# Ground-truth values a row may carry. `background` means "no implanted
# activity" -- a concern on one is a false positive, by definition.
BACKGROUND = "background"
IMPLANT_CLASSES: tuple[str, ...] = ("known_bad", "unknown_cousin")

# Relationships that constitute raising a concern.
CONCERN_RELATIONSHIPS: frozenset[str] = frozenset({"SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED"})


@dataclass(frozen=True)
class DetectionReport:
    n_rows: int
    n_implants_graded: int
    n_background_graded: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    background_false_positive_rate: float | None
    by_implant_class: dict[str, dict[str, int]]
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_implants_graded": self.n_implants_graded,
            "n_background_graded": self.n_background_graded,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "background_false_positive_rate": self.background_false_positive_rate,
            "by_implant_class": self.by_implant_class,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def _truth(row: dict[str, Any]) -> str:
    return str(row.get("implant_class_ground_truth") or BACKGROUND)


def _raised(row: dict[str, Any]) -> bool:
    if "concern_raised" in row:
        return bool(row["concern_raised"])
    return row.get("relationship") in CONCERN_RELATIONSHIPS


def detection_report(
    rows: list[dict[str, Any]],
    *,
    max_background_fp_rate: float = 0.10,
) -> DetectionReport:
    """TP/FP/FN against sealed truth. A run with zero implants in the graded
    population is INVALID -- it measured background and cannot speak to
    detection, however its own labels happen to split."""
    n = len(rows)
    implants = [r for r in rows if _truth(r) in IMPLANT_CLASSES]
    background = [r for r in rows if _truth(r) == BACKGROUND]

    tp = sum(1 for r in implants if _raised(r))
    fn = len(implants) - tp
    fp = sum(1 for r in background if _raised(r))

    raised_total = tp + fp
    precision = (tp / raised_total) if raised_total else None
    recall = (tp / len(implants)) if implants else None
    bg_fp_rate = (fp / len(background)) if background else None

    by_class: dict[str, dict[str, int]] = {}
    for cls in IMPLANT_CLASSES:
        sub = [r for r in implants if _truth(r) == cls]
        by_class[cls] = {
            "graded": len(sub),
            "detected": sum(1 for r in sub if _raised(r)),
            "missed": sum(1 for r in sub if not _raised(r)),
        }

    reasons: list[str] = []
    verdict = "PASS"

    if not implants:
        verdict = "INVALID"
        reasons.append(
            f"no_implants_in_graded_population: {len(background)} background rows graded, "
            "0 implants -- this run measured background and cannot report detection"
        )
    if bg_fp_rate is not None and bg_fp_rate > max_background_fp_rate:
        verdict = "FAIL" if verdict != "INVALID" else verdict
        reasons.append(f"background_false_positive_rate_{bg_fp_rate:.3f}>{max_background_fp_rate}")
    if implants and tp == 0:
        verdict = "FAIL" if verdict != "INVALID" else verdict
        reasons.append("zero_true_positives_despite_implants_present")
    if precision is None and raised_total == 0:
        reasons.append("nothing_raised:precision_undefined")

    return DetectionReport(
        n_rows=n,
        n_implants_graded=len(implants),
        n_background_graded=len(background),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        background_false_positive_rate=bg_fp_rate,
        by_implant_class=by_class,
        verdict=verdict,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class SelectionReport:
    """Did truth-bearing entities reach the grader at all? X.6 shipped 182
    implant events successfully and graded zero of them, because selection
    sorts richest-first and a sparse implant never wins that sort."""

    n_implants_shipped: int
    n_implant_entities_available: int
    n_implant_entities_selected: int
    selection_recall: float | None
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_implants_shipped": self.n_implants_shipped,
            "n_implant_entities_available": self.n_implant_entities_available,
            "n_implant_entities_selected": self.n_implant_entities_selected,
            "selection_recall": self.selection_recall,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def selection_report(
    *,
    n_implants_shipped: int,
    implant_entity_ids: set[str],
    selected_entity_ids: set[str],
    min_selection_recall: float = 0.5,
) -> SelectionReport:
    avail = len(implant_entity_ids)
    picked = len(implant_entity_ids & selected_entity_ids)
    rec = (picked / avail) if avail else None
    reasons: list[str] = []
    verdict = "PASS"
    if n_implants_shipped and not avail:
        verdict = "FAIL"
        reasons.append("implants_shipped_but_no_implant_entities_resolved")
    elif rec is not None and rec < min_selection_recall:
        verdict = "FAIL"
        reasons.append(
            f"selection_recall_{rec:.3f}<{min_selection_recall}: implants were shipped "
            "but selection excluded them (richest-first bias)"
        )
    return SelectionReport(
        n_implants_shipped=n_implants_shipped,
        n_implant_entities_available=avail,
        n_implant_entities_selected=picked,
        selection_recall=rec,
        verdict=verdict,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class PoisoningReport:
    """A CONFIRMED verdict on a background entity writes benign activity into
    the library as ANALYST_CONFIRMED malicious knowledge -- irreversible trust
    damage, and the reason X.6 cycle 2 matched MORE background as SAME."""

    n_verdicts: int
    confirmed_on_background: int
    benign_on_implant: int
    poisoning_rate: float | None
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_verdicts": self.n_verdicts,
            "confirmed_on_background": self.confirmed_on_background,
            "benign_on_implant": self.benign_on_implant,
            "poisoning_rate": self.poisoning_rate,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def poisoning_report(
    verdict_rows: list[dict[str, Any]], *, max_poisoning_rate: float = 0.0
) -> PoisoningReport:
    """`verdict_rows` carry `verdict` and `implant_class_ground_truth`."""
    n = len(verdict_rows)
    conf_bg = sum(
        1 for r in verdict_rows if r.get("verdict") == "CONFIRMED" and _truth(r) == BACKGROUND
    )
    benign_imp = sum(
        1 for r in verdict_rows if r.get("verdict") == "BENIGN" and _truth(r) in IMPLANT_CLASSES
    )
    rate = (conf_bg / n) if n else None
    reasons: list[str] = []
    verdict = "PASS"
    if rate is not None and rate > max_poisoning_rate:
        verdict = "FAIL"
        reasons.append(
            f"confirmed_on_background_{conf_bg}/{n}: benign patterns written to the "
            "library as ANALYST_CONFIRMED malicious knowledge"
        )
    if benign_imp:
        reasons.append(f"benign_verdict_on_{benign_imp}_real_implants:suppressing_true_positives")
    return PoisoningReport(
        n_verdicts=n,
        confirmed_on_background=conf_bg,
        benign_on_implant=benign_imp,
        poisoning_rate=rate,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def acceptance_report(
    rows: list[dict[str, Any]],
    *,
    verdict_rows: list[dict[str, Any]] | None = None,
    selection: SelectionReport | None = None,
) -> dict[str, Any]:
    det = detection_report(rows)
    poi = poisoning_report(verdict_rows or [])
    parts = [det.verdict, poi.verdict] + ([selection.verdict] if selection else [])
    overall = "INVALID" if "INVALID" in parts else ("FAIL" if "FAIL" in parts else "PASS")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "verdict": overall,
        "detection": det.to_dict(),
        "poisoning": poi.to_dict(),
        "selection": selection.to_dict() if selection else None,
    }
