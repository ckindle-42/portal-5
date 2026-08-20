"""Y.1 -- acceptance measured against sealed truth, never against the
system's own output. See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md."""

from __future__ import annotations

import json
from pathlib import Path

from portal.modules.security.core.bully import truth_acceptance as ta

REPO_ROOT = Path(__file__).resolve().parents[3]
X6_JSON = REPO_ROOT / "docs" / "BULLY_ANALYST_LOOP_RUN_X6_V1.json"


def test_x6_per_row_yields_invalid() -> None:
    """Permanent regression test: the real X.6 run detected zero implants
    and must be reported INVALID, however its own labels happened to split."""
    report = json.loads(X6_JSON.read_text())
    rows = [r for r in report["per_row"] if r["cycle"] == 1]
    det = ta.detection_report(rows)
    assert det.n_implants_graded == 0
    assert det.n_background_graded == 300
    assert det.false_positives == 300
    assert det.background_false_positive_rate == 1.0
    assert det.verdict == "INVALID"
    assert any("no_implants_in_graded_population" in r for r in det.reasons)


def _row(truth: str, relationship: str) -> dict:
    return {"implant_class_ground_truth": truth, "relationship": relationship}


def test_population_with_implants_and_good_detection_passes() -> None:
    rows = (
        [_row("known_bad", "SAME") for _ in range(8)]
        + [_row("known_bad", "NONE") for _ in range(2)]
        + [_row("unknown_cousin", "SIMILAR") for _ in range(5)]
        + [_row("background", "NONE") for _ in range(90)]
        + [_row("background", "SAME") for _ in range(3)]
    )
    det = ta.detection_report(rows)
    assert det.n_implants_graded == 15
    assert det.true_positives == 13
    assert det.false_negatives == 2
    assert det.false_positives == 3
    assert det.verdict == "PASS"


def test_background_only_population_is_invalid_regardless_of_label_split() -> None:
    """A run that mislabels 100% of background as known_bad/unknown_cousin-
    shaped relationships in a way that satisfies a two-bucket split is still
    INVALID: this is exactly the vacuous `both_classes_notified` failure."""
    rows = [_row("background", "SAME") for _ in range(150)] + [
        _row("background", "SIMILAR") for _ in range(150)
    ]
    det = ta.detection_report(rows)
    assert det.n_implants_graded == 0
    assert det.verdict == "INVALID"


def test_confirmed_verdict_on_background_fails_poisoning_report() -> None:
    verdict_rows = [
        {"verdict": "CONFIRMED", "implant_class_ground_truth": "background"},
        {"verdict": "BENIGN", "implant_class_ground_truth": "background"},
    ]
    poi = ta.poisoning_report(verdict_rows)
    assert poi.confirmed_on_background == 1
    assert poi.verdict == "FAIL"
    assert any("confirmed_on_background" in r for r in poi.reasons)


def test_clean_verdicts_pass_poisoning_report() -> None:
    verdict_rows = [
        {"verdict": "CONFIRMED", "implant_class_ground_truth": "known_bad"},
        {"verdict": "BENIGN", "implant_class_ground_truth": "background"},
    ]
    poi = ta.poisoning_report(verdict_rows)
    assert poi.confirmed_on_background == 0
    assert poi.verdict == "PASS"


def test_implants_shipped_but_none_selected_fails_selection_report() -> None:
    sel = ta.selection_report(
        n_implants_shipped=182,
        implant_entity_ids={"e1", "e2", "e3"},
        selected_entity_ids={"bg1", "bg2"},
    )
    assert sel.selection_recall == 0.0
    assert sel.verdict == "FAIL"


def test_implants_shipped_and_selected_passes_selection_report() -> None:
    sel = ta.selection_report(
        n_implants_shipped=182,
        implant_entity_ids={"e1", "e2", "e3"},
        selected_entity_ids={"e1", "e2", "e3", "bg1"},
    )
    assert sel.selection_recall == 1.0
    assert sel.verdict == "PASS"


def test_acceptance_report_overall_verdict_is_invalid_when_any_part_invalid() -> None:
    rows = [_row("background", "SAME") for _ in range(5)]
    report = ta.acceptance_report(rows)
    assert report["verdict"] == "INVALID"
    assert report["detection"]["verdict"] == "INVALID"
