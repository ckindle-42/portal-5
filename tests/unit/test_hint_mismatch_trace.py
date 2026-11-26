"""A substituted model_hint is a span on the turn, not only a counter."""

from __future__ import annotations

import json

from portal.platform.inference.router.trace import (
    TurnTrace,
    bounded_tool_result,
    note_hint_mismatch,
    start_trace,
)


def test_note_hint_mismatch_lands_on_the_current_turn() -> None:
    trace = start_trace("p5-hintmismatch")
    assert isinstance(trace, TurnTrace)
    note_hint_mismatch(
        workspace="auto-coding",
        hinted="wanted-tag",
        served="other-tag",
        backend="ollama-general",
        path="non_streaming",
    )
    spans = trace.to_dict()["spans"]
    assert spans[-1]["name"] == "model.hint_mismatch"
    assert spans[-1]["hinted"] == "wanted-tag"
    assert spans[-1]["served"] == "other-tag"
    assert spans[-1]["path"] == "non_streaming"


def test_tool_completion_has_a_bounded_structured_receipt() -> None:
    result = bounded_tool_result(
        {
            "success": True,
            "data": {
                "job_id": "hunt-12345678",
                "status": "COMPLETE",
                "splunk_requests": 3,
                "event_count": 5,
                "lead_count": 2,
                "artifact_url": "https://portal.invalid/files/job?token=do-not-store",
                "artifact_bytes": 4096,
                "citation": "CIP-007-6 R2 Part 2.2",
                "api_key": "also-do-not-store",
                "irrelevant": "x" * 4000,
            },
        }
    )

    receipt = result["receipt"]
    assert receipt["job_id"] == "hunt-12345678"
    assert receipt["status"] == "COMPLETE"
    assert receipt["splunk_requests"] == 3
    assert receipt["event_count"] == 5
    assert receipt["lead_count"] == 2
    assert receipt["artifact_bytes"] == 4096
    assert "token=" not in json.dumps(receipt)
    assert "api_key" not in receipt
    assert len(json.dumps(receipt, separators=(",", ":")).encode()) <= 1024
