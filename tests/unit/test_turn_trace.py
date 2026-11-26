"""Unit tests for the per-turn operational trace (no network, no live stack)."""

from __future__ import annotations


def test_redaction_spares_token_counts_but_not_credentials():
    # wfe_math_20261018c: "<redacted>" token counts in /v1/trace crashed the WFE runner
    from portal.platform.inference.router.trace import redact

    out = redact(
        {
            "reasoning_tokens": 12,
            "answer_tokens": 30,
            "max_tokens": 512,
            "access_token": "s3cret",
            "x-token": "s3cret",
            "api_key": "k",
            "portal_timings": {"answer_tokens": 30, "authorization": "Bearer x"},
        }
    )
    assert out["reasoning_tokens"] == 12 and out["answer_tokens"] == 30 and out["max_tokens"] == 512
    assert out["access_token"] == out["x-token"] == out["api_key"] == "<redacted>"
    assert out["portal_timings"] == {"answer_tokens": 30, "authorization": "<redacted>"}


def test_recent_traces_summary_carries_requested_and_owui_task(monkeypatch, tmp_path):
    # bench_security_qat.newest_trace and qat _trace_row_matches match summaries on
    # `requested`, and both skip OWUI task rows: the summary must carry both fields.
    from portal.platform.inference.router import trace

    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    trace._write(
        "p5-aaaaaaaaaaaa",
        {
            "correlation_id": "p5-aaaaaaaaaaaa",
            "workspace": "s3-canonical",
            "requested": "sec-analyst",
            "outcome": "ok",
        },
    )
    trace._write(
        "p5-bbbbbbbbbbbb",
        {
            "correlation_id": "p5-bbbbbbbbbbbb",
            "workspace": "s3-canonical",
            "outcome": "complete",
            "owui_task": True,
        },
    )
    rows = {row["correlation_id"]: row for row in trace.recent_traces(limit=5)}
    assert rows["p5-aaaaaaaaaaaa"]["requested"] == "sec-analyst"
    assert rows["p5-bbbbbbbbbbbb"]["owui_task"] is True
