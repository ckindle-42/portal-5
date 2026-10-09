"""Claim aggregation keeps control margins, missing samples, and corpus limits visible."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core.review_eval import claims


def _rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, review_hit in enumerate((True, True, True, False)):
        rows.append(
            {
                "claim": "C1",
                "row_id": f"source-{index}",
                "source": f"botsv{index % 3 + 1}:source-{index}",
                "review_valid_extraction": review_hit,
                "review_has_unit": review_hit,
                "control_valid_extraction": index == 0,
                "control_has_unit": index == 0,
            }
        )
    for klass in ("known", "cousin", "novel"):
        for index, review_hit in enumerate((True, True, True, False)):
            rows.append(
                {
                    "claim": "C2",
                    "row_id": f"c2-{klass}-{index}",
                    "class": klass,
                    "workload_B": 8,
                    "review_hit": review_hit,
                    "control_hit": index == 0,
                    "review_raised": False,
                    "grounding_resolved": True,
                    "absence_receipt_verified": klass == "novel" and review_hit,
                    "alpha": 0.2,
                }
            )
    for index in range(10):
        rows.append(
            {
                "claim": "C2",
                "row_id": f"c2-benign-{index}",
                "class": "benign",
                "workload_B": 8,
                "review_hit": False,
                "control_hit": False,
                "review_raised": index == 0,
                "grounding_resolved": True,
                "absence_receipt_verified": False,
                "alpha": 0.2,
            }
        )
    rows.extend(
        [
            {
                "claim": "C3_WINDOW",
                "row_id": "window-1",
                "window_id": "window-1",
                "index": "botsv1",
                "sourcetype": "stream:http",
                "expected": 3,
                "fetched": 3,
                "corpus_size": 100,
            },
            {
                "claim": "C3_WINDOW",
                "row_id": "window-2",
                "window_id": "window-2",
                "index": "botsv1",
                "sourcetype": "stream:dns",
                "expected": 3,
                "fetched": 3,
                "corpus_size": 100,
            },
            {
                "claim": "C3_STAGE",
                "row_id": "stage-intake",
                "stage": "intake",
                "examined": 10,
                "resolved": 9,
                "duration_seconds": 2.0,
                "cause": "one explicitly blind source",
            },
        ]
    )
    for klass in ("cousin", "novel", "evidence_twin"):
        for index in range(2):
            rows.append(
                {
                    "claim": "C4",
                    "row_id": f"c4-{klass}-{index}",
                    "class": klass,
                    "evidence_twin_source": "corpus" if klass == "evidence_twin" else None,
                    "workload_B": 8,
                    "review_hit": True,
                    "control_hit": False,
                    "review_raised": False,
                    "grounding_resolved": True,
                    "absence_receipt_verified": klass == "novel",
                    "alpha": 0.2,
                }
            )
    for index in range(10):
        rows.append(
            {
                "claim": "C4",
                "row_id": f"c4-benign-{index}",
                "class": "benign",
                "workload_B": 8,
                "review_hit": False,
                "control_hit": False,
                "review_raised": False,
                "grounding_resolved": True,
                "absence_receipt_verified": False,
                "alpha": 0.2,
            }
        )
    return rows


def _evaluate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return claims.evaluate_claims(
        rows or _rows(),
        corpus_snapshots=["real:botsv1:sample", "real:portal5_lab:sample"],
        selftests_passed=True,
        captures={
            "admitted_count": 1,
            "total_count": 10,
            "rejection_reason_histogram": {"MISSING_EPISODE_ID": 4},
            "validator_rule_histogram": {},
            "missing_data_histogram": {"MISSING_EPISODE_ID": 4},
        },
        processed_fraction=0.01,
        stop_rule="plateau: last 20 percent within one bootstrap standard error",
    )


def test_claims_report_statuses_denominators_and_stop_rule() -> None:
    result = _evaluate()
    by_id = {row["claim"]: row for row in result["claims"]}
    assert result["schema"] == "review.claims.v1"
    assert result["processed_fraction"] == 0.01
    assert by_id["C1"]["sampled_sources"] == 4
    assert by_id["C2"]["cousin_comparison"]["workload_B"] == 8
    assert by_id["C2"]["false_raise"]["benign_units"] == 10
    assert by_id["C2"]["grounding"]["fraction"] == 1.0
    assert by_id["C3"]["status"] == "PROVEN"
    assert by_id["C3"]["events_expected"] == 6
    assert by_id["C3"]["full_corpus_events"] == 100
    assert by_id["C3"]["projected_full_corpus_seconds"] == pytest.approx(100 * 2 / 9)
    assert by_id["C4"]["admitted_capture_count"] == 1
    assert by_id["C4"]["rejected_capture_count"] == 9
    assert claims.validate_claims_document(result) == []


def test_c3_does_not_call_a_named_stage_difference_incomplete() -> None:
    rows = _rows()
    stage = next(row for row in rows if row.get("claim") == "C3_STAGE")
    stage["cause"] = "explicit cap receipt"
    result = _evaluate(rows)
    c3 = next(row for row in result["claims"] if row["claim"] == "C3")
    assert c3["status"] == "PROVEN"
    assert c3["stages"][0]["unexplained_difference"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"corpus_snapshots": ["proxy:fixture"]}, "real:"),
        ({"selftests_passed": False}, "self-test"),
        ({"processed_fraction": 1.1}, "processed_fraction"),
        ({"stop_rule": ""}, "stop rule"),
    ],
)
def test_claim_inputs_require_real_stamped_and_stopped_evidence(
    kwargs: dict[str, Any], message: str
) -> None:
    arguments: dict[str, Any] = {
        "corpus_snapshots": ["real:botsv1:sample"],
        "selftests_passed": True,
        "captures": {},
        "processed_fraction": 0.5,
        "stop_rule": "12 hour wall-clock budget",
    }
    arguments.update(kwargs)
    with pytest.raises(claims.ClaimEvidenceError, match=message):
        claims.evaluate_claims(_rows(), **arguments)


def test_claim_rows_reject_raw_event_text_and_non_corpus_twins() -> None:
    rows = _rows()
    rows.append({"claim": "C3_WINDOW", "row_id": "unsafe", "raw_text": "event content"})
    with pytest.raises(claims.ClaimEvidenceError, match="raw telemetry"):
        _evaluate(rows)

    rows = _rows()
    twin = next(row for row in rows if row.get("class") == "evidence_twin")
    twin["evidence_twin_source"] = "fixture"
    with pytest.raises(claims.ClaimEvidenceError, match="corpus-derived"):
        _evaluate(rows)


def test_claim_rows_require_unique_strata_and_consistent_workload() -> None:
    rows = _rows()
    rows[1]["source"] = rows[0]["source"]
    with pytest.raises(claims.ClaimEvidenceError, match="one row per stratified source"):
        _evaluate(rows)

    rows = _rows()
    rows[4]["workload_B"] = 9
    with pytest.raises(claims.ClaimEvidenceError, match="same workload B"):
        _evaluate(rows)


def test_small_samples_have_no_claim_ci_and_cannot_be_proven() -> None:
    rows = _rows()
    rows = [row for row in rows if row.get("claim") != "C1"]
    rows.extend(
        [
            {
                "claim": "C1",
                "row_id": "only-source",
                "source": "botsv1:single",
                "review_valid_extraction": True,
                "review_has_unit": True,
                "control_valid_extraction": False,
                "control_has_unit": False,
            }
        ]
    )
    c1 = next(row for row in _evaluate(rows)["claims"] if row["claim"] == "C1")
    assert c1["status"] == "UNPROVEN"
    assert c1["review_fraction"]["ci95"] is None


def test_rejection_histogram_keeps_validator_and_missing_data_separate() -> None:
    rules, missing = claims.rejection_histograms(
        {"CAPTURE_GROUND_TRUTH_INVALID": 2, "MISSING_EPISODE_ID": 3},
        rule_reasons={"CAPTURE_GROUND_TRUTH_INVALID"},
    )
    assert rules == {"CAPTURE_GROUND_TRUTH_INVALID": 2}
    assert missing == {"MISSING_EPISODE_ID": 3}
