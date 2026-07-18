"""Tests for blue_orchestrate.py's expert section (fed, no tools) — Slice 4."""

from __future__ import annotations

import json

from portal.modules.security.core import blue_orchestrate as bo


def _fake_call_model(content: str):
    def _fn(model, messages, tools=None, max_tokens=2000):
        assert tools is None  # expert never gets tools (fed, no-tools)
        return {"content": content}

    return _fn


def test_supports_tools_false_expert_id_is_accepted(monkeypatch):
    """Nothing in run_expert_model checks backends.yaml supports_tools — this
    is the require_tools=False path that makes a supports_tools:false model
    usable at all."""
    content = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T1558.004"],
            "evidence": ["EventCode=4768 AS-REP roasting"],
            "reasoning": "clear AS-REP roasting pattern",
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
    out = bo.run_expert_model(
        "ctx",
        expert_model="hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0",
        ground_truth={"T1558.004"},
        tool_results=tool_results,
    )
    assert out.verdict == "CONFIRMED"
    assert out.section == "expert"


def test_confirmed_failing_cite_or_drop_downgrades_to_anomalous(monkeypatch):
    content = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T1499"],  # not in ground truth, not in telemetry
            "evidence": ["a vague hunch"],
            "reasoning": "seems plausible",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    tool_results = [
        bo.ToolResult(query="q", provenance="empty", raw_summary="nothing relevant here")
    ]
    out = bo.run_expert_model(
        "ctx",
        expert_model="m",
        ground_truth={"T1558.004"},
        tool_results=tool_results,
        hunter_similar_to=["T1558.003"],
    )
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert out.similar_to == ["T1558.003"]


def test_confirmed_with_ground_truth_technique_survives_cite_or_drop(monkeypatch):
    content = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T1558.004"],
            "evidence": ["confirmed via 4768"],
            "reasoning": "matches ground truth",
            "match_grade": "EXACT",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth={"T1558.004"}, tool_results=[])
    assert out.verdict == "CONFIRMED"
    assert out.technique_ids == ["T1558.004"]


def test_expert_request_more_round_trips(monkeypatch):
    content = json.dumps(
        {
            "verdict": None,
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "need the exact source IP for the 4625 failures",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth=set())
    assert out.wants_more()
    assert "4625" in out.request_more
    assert out.section == "expert"


def test_ruled_out_is_a_valid_conclusion_without_citation_check(monkeypatch):
    content = json.dumps(
        {
            "verdict": "RULED_OUT",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "no supporting evidence found for the hunter's hypothesis",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth=set())
    assert out.verdict == "RULED_OUT"


def test_dry_run_never_calls_model(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("dry_run must not call the model")

    monkeypatch.setattr(bo, "_call_model", _boom)
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth=set(), dry_run=True)
    assert out.wants_more()


def test_unparseable_output_becomes_request_more(monkeypatch):
    monkeypatch.setattr(bo, "_call_model", _fake_call_model("hmm, unclear, not sure honestly"))
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth=set())
    assert out.wants_more()
    assert out.verdict is None


def test_confirmed_with_malformed_technique_id_downgrades_to_anomalous(monkeypatch):
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
    out = bo.run_expert_model(
        "ctx", expert_model="m", ground_truth={"T1558.004"}, tool_results=tool_results
    )
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert "did not parse as real MITRE IDs" in out.reasoning


def test_anomalous_unclassified_never_requires_a_valid_technique_id(monkeypatch):
    """I8: novelty is a legitimate outcome. A SIMILAR/novel finding is never
    required to name a real, resolvable technique ID — only CONFIRMED is."""
    content = json.dumps(
        {
            "verdict": "ANOMALOUS_UNCLASSIFIED",
            "technique_ids": ["unknown-novel-pattern"],
            "evidence": ["odd but real telemetry pattern"],
            "reasoning": "shares no known signature",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_expert_model("ctx", expert_model="m", ground_truth=set())
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert out.technique_ids == ["unknown-novel-pattern"]


def test_format_for_expert_carries_hunter_hypothesis():
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
