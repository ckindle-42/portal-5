"""Tests for blue_orchestrate.py's expert section (fed, no tools) — Slice 4."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from portal.modules.security.core import blue_orchestrate as bo


def _fake_call_model(content: str) -> Callable[..., dict[str, Any]]:
    def _fn(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert tools is None  # expert never gets tools (fed, no-tools)
        return {"content": content}

    return _fn


def test_confirmed_with_grounded_evidence_survives_cite_or_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CONFIRMED claim survives cite_or_drop when its OWN cited evidence
    is actually grounded in real telemetry. The gate is label-blind
    (2026-07-23) — grounded evidence is the bar, for correct and incorrect
    labels alike (found live 2026-07-22: an unconditional ground-truth
    exemption let fabricated evidence through, see blue._cite_or_drop's
    docstring)."""
    content = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T1558.004"],
            "evidence": ["EventCode=4768 AS-REP roasting confirmed"],
            "reasoning": "matches ground truth",
            "match_grade": "EXACT",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    tool_results = [
        bo.ToolResult(
            query="q",
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP roasting event for svc-web on dc01",
        )
    ]
    out = bo.run_expert_model("ctx", expert_model="m", tool_results=tool_results)
    assert out.verdict == "CONFIRMED"
    assert out.technique_ids == ["T1558.004"]


def test_confirmed_with_malformed_technique_id_downgrades_to_anomalous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: found live 2026-07-18 — a literal 'T....' slipped through
    as a CONFIRMED technique_id. CONFIRMED claims a specific known match, so
    a claim that doesn't even parse as a real MITRE ID doesn't hold up —
    same class of problem as evidence that fails citation. This is NOT a
    general requirement that every finding resolve to a known ID (I8):
    ANOMALOUS_UNCLASSIFIED/RULED_OUT are never held to this."""
    content = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T...."],
            "evidence": ["EventCode=4768 AS-REP roasting"],
            "reasoning": "",
            "match_grade": "EXACT",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    tool_results = [
        bo.ToolResult(
            query="q",
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP roasting event",
        )
    ]
    out = bo.run_expert_model("ctx", expert_model="m", tool_results=tool_results)
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert "did not parse as real MITRE IDs" in out.reasoning


def test_format_for_expert_carries_hunter_hypothesis() -> None:
    from portal.modules.security.core.analyst_verdict import SectionOutput

    hunter_out = SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=["T1558.099"],
        evidence=["odd ticket pattern"],
        reasoning="shares features with T1558.003",
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
        section="reasoning",
    )
    ctx = bo.format_for_expert(hunter_out, [], "an alert fired")
    assert "T1558.099" in ctx
    assert "T1558.003" in ctx
    assert "SIMILAR" in ctx
