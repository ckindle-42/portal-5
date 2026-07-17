"""Tests for blue_orchestrate.py's reasoning section (Hunter) — Slice 3."""

from __future__ import annotations

import json

from portal.modules.security.core import blue_orchestrate as bo


def _fake_call_model(content: str):
    def _fn(model, messages, tools=None, max_tokens=2000):
        assert tools is None  # Hunter requests data, it doesn't fetch (tools off)
        return {"content": content}

    return _fn


def test_similar_grade_yields_similar_to_and_steers_anomalous(monkeypatch):
    content = json.dumps(
        {
            "technique_ids": ["T1558.099"],
            "evidence": ["odd ticket pattern on dc01"],
            "reasoning": "shares kerberos-ticket features with T1558.003 but timing differs",
            "match_grade": "SIMILAR",
            "similar_to": ["T1558.003"],
            "request_more": "",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_reasoning_model(
        "ctx", reasoning_model="devstral-small-2", ground_truth={"T1558.003"}
    )
    assert out.match_grade == "SIMILAR"
    assert out.similar_to == ["T1558.003"]
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert out.section == "reasoning"


def test_think_wrapped_hypothesis_parses(monkeypatch):
    content = (
        "<think>let me consider the evidence carefully, checking each event...</think>"
        + json.dumps(
            {
                "technique_ids": ["T1558.004"],
                "evidence": ["EventCode=4768 AS-REP"],
                "reasoning": "AS-REP roasting confirmed",
                "match_grade": "EXACT",
                "similar_to": [],
                "request_more": "",
            }
        )
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_reasoning_model("ctx", reasoning_model="m", ground_truth={"T1558.004"})
    assert out.technique_ids == ["T1558.004"]
    assert out.verdict == "CONFIRMED"
    assert "<think>" not in out.raw or out.raw == content  # raw keeps original; parse strips


def test_insufficient_evidence_emits_request_more_not_a_guess(monkeypatch):
    content = json.dumps(
        {
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "need Splunk logs for host dc01 in the last 30 minutes",
        }
    )
    monkeypatch.setattr(bo, "_call_model", _fake_call_model(content))
    out = bo.run_reasoning_model("ctx", reasoning_model="m", ground_truth=set())
    assert out.wants_more()
    assert out.verdict is None
    assert "dc01" in out.request_more


def test_unparseable_free_text_falls_back_to_request_more_never_guesses(monkeypatch):
    monkeypatch.setattr(
        bo,
        "_call_model",
        _fake_call_model("I think something might be happening but I'm not sure."),
    )
    out = bo.run_reasoning_model("ctx", reasoning_model="m", ground_truth=set())
    assert out.wants_more()
    assert out.verdict is None
    assert not out.technique_ids


def test_dry_run_never_calls_model(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("dry_run must not call the model")

    monkeypatch.setattr(bo, "_call_model", _boom)
    out = bo.run_reasoning_model("ctx", reasoning_model="m", ground_truth=set(), dry_run=True)
    assert out.wants_more()


def test_strip_think_tags_removes_scratchpad():
    text = "<think>internal musing</think>final answer here"
    assert bo._strip_think_tags(text) == "final answer here"


def test_format_for_reasoning_uses_open_discovery_prompt_no_checklist():
    from portal.modules.security.core.blue import _BLUE_SYSTEM_PROMPT_DISCOVERY

    ctx = bo.format_for_reasoning([], "an alert fired")
    assert _BLUE_SYSTEM_PROMPT_DISCOVERY in ctx
    # never inject a scripted event-ID checklist into the hunt (I8)
    assert "Step 1" not in ctx and "you MUST follow" not in ctx


def test_run_similarity_similar_grade_carries_named_technique():
    features = {"tactic": "credential-access", "process_names": ["klist", "tgtdeleg"]}
    wiki = {"T1558.003": "kerberoast service ticket request tgtdeleg klist unusual"}
    out = bo.run_similarity(features, wiki_descriptions=wiki)
    assert out["match_grade"] in ("SIMILAR", "EXACT")
    if out["match_grade"] == "SIMILAR":
        assert out["similar_to"] == ["T1558.003"]


def test_run_similarity_no_overlap_returns_none_grade():
    out = bo.run_similarity(
        {"tactic": "zzz"}, wiki_descriptions={"T9999": "totally unrelated text"}
    )
    assert out["match_grade"] == "NONE"
    assert out["similar_to"] == []
