"""Corpus-derived evidence twins count once and only when present in a fixed proof window."""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.review.intake import event_id_for
from portal.modules.security.core.review.window import WindowBatch
from scripts.review_eval_proof import _evidence_twin_rows


def _truth_pair(event_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "class": "known",
            "dataset": "botsv1",
            "event_ids": event_ids,
            "technique": technique,
        }
        for technique in ("T1190", "T1071.001")
    ]


def test_evidence_twin_is_scored_once_when_exact_events_are_in_a_fixed_window() -> None:
    source_id = "botsv1:stream:http"
    record = {"_time": 1.0, "observable": "hash-only test fixture"}
    event_id = event_id_for(source_id, record)
    candidate = {
        "concerns": [
            {
                "group": "concerns",
                "unit_id": "unit-1",
                "priority_p": 0.01,
                "evidence_event_ids": [event_id],
            }
        ]
    }
    control = {"concerns": []}
    rows, dispositions = _evidence_twin_rows(
        _truth_pair([event_id]),
        test_batches={"window-1": WindowBatch(records_by_source={source_id: [record]})},
        candidate_summaries={"window-1": candidate},
        control_summaries={"window-1": control},
        window_order=["window-1"],
        workload_b=1,
    )

    assert len(rows) == 1
    assert rows[0]["class"] == "evidence_twin"
    assert rows[0]["evidence_twin_source"] == "corpus"
    assert rows[0]["review_hit"] is True
    assert rows[0]["control_hit"] is False
    assert rows[0]["processed_overlap_event_count"] == 1
    assert dispositions[0]["truth_item_count"] == 2
    assert dispositions[0]["status"] == "matched_to_processed_window"


def test_evidence_twin_outside_processed_windows_is_reported_but_not_scored() -> None:
    rows, dispositions = _evidence_twin_rows(
        _truth_pair(["botsv1:unprocessed-event"]),
        test_batches={"window-1": WindowBatch(records_by_source={"botsv1:stream:http": []})},
        candidate_summaries={"window-1": {"concerns": []}},
        control_summaries={"window-1": {"concerns": []}},
        window_order=["window-1"],
        workload_b=1,
    )

    assert rows == []
    assert dispositions[0]["status"] == "not_in_processed_windows"
