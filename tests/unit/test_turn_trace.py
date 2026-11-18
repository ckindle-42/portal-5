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
