"""Tests for blue_orchestrate.py's reasoning section (Hunter) — Slice 3."""

from __future__ import annotations

import json

from portal.modules.security.core import blue_orchestrate as bo


def _fake_call_model(content: str):
    def _fn(model, messages, tools=None, max_tokens=2000, extra_options=None):
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


# ── _ground_similarity: root-cause fix for NOVELTY structurally reading 0 ────
# (GATE-D ablation, 2026-07-19/20): run_similarity() existed and was
# unit-tested above in isolation, but was never called from the live Hunter/
# Expert/merged flow — match_grade/similar_to were pure LLM self-report,
# untethered from the wiki-grounded engine. These tests prove the grounding
# helper actually overrides an unverified self-report with the deterministic
# computation, rather than trusting whatever the model claimed.


def test_ground_similarity_overrides_unverified_self_report_with_grounded_grade(monkeypatch):
    monkeypatch.setattr(
        bo,
        "_wiki_technique_descriptions_cache",
        {"T1558.003": "kerberoast service ticket request tgtdeleg klist unusual"},
    )
    tool_results = [
        bo.ToolResult(
            query="q1",
            provenance="matched-exact",
            raw_summary="klist tgtdeleg unusual service ticket request observed",
        )
    ]
    # Model self-reported EXACT/NONE with no similar_to at all — should be
    # overridden by the grounded SIMILAR/EXACT computation from real overlap.
    out = bo.SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=[],
        match_grade="NONE",
        similar_to=[],
        section="reasoning",
    )
    grounded = bo._ground_similarity(out, tool_results)
    assert grounded.match_grade in ("SIMILAR", "EXACT")
    assert grounded.similar_to == ["T1558.003"]
    # verdict/technique_ids/section pass through untouched — only the
    # similarity axis is grounded, not the separately-gated verdict axis.
    assert grounded.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert grounded.section == "reasoning"


def test_ground_similarity_corrects_a_claimed_similarity_that_does_not_hold_up(monkeypatch):
    """The model claims SIMILAR to a specific technique, but the actual
    gathered telemetry has zero overlap with any wiki description — the
    unverified claim must not stand (never-invent extended to similarity)."""
    monkeypatch.setattr(
        bo,
        "_wiki_technique_descriptions_cache",
        {"T1558.003": "kerberoast service ticket request tgtdeleg klist unusual"},
    )
    tool_results = [
        bo.ToolResult(query="q1", provenance="empty", raw_summary="no matching events found")
    ]
    out = bo.SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
        section="expert",
    )
    grounded = bo._ground_similarity(out, tool_results)
    assert grounded.match_grade == "NONE"
    assert grounded.similar_to == []


def test_ground_similarity_skips_when_no_tool_results_gathered_yet():
    """Nothing retrieved yet — not enough to ground against either way, so
    leave the (still-provisional) self-report alone rather than force NONE."""
    out = bo.SectionOutput(verdict=None, match_grade="SIMILAR", similar_to=["T1558.003"])
    grounded = bo._ground_similarity(out, [])
    assert grounded is out


def test_ground_similarity_skips_when_wiki_not_seeded(monkeypatch):
    monkeypatch.setattr(bo, "_wiki_technique_descriptions_cache", {})
    tool_results = [bo.ToolResult(query="q1", provenance="matched-exact", raw_summary="anything")]
    out = bo.SectionOutput(match_grade="SIMILAR", similar_to=["T1558.003"])
    grounded = bo._ground_similarity(out, tool_results)
    assert grounded is out


def test_format_new_evidence_renders_only_the_given_results_not_a_full_pile():
    """Regression: the delta renderer must not re-render trigger/discovery
    framing (that's already in the Hunter's conversation history) — only
    the new evidence itself, keeping context growth linear across rounds."""
    r1 = bo.ToolResult(query="q1", provenance="matched-exact", raw_summary="EventCode=4769 stuff")
    ctx = bo.format_new_evidence([r1])
    assert "EventCode=4769 stuff" in ctx
    assert "q1" in ctx
    from portal.modules.security.core.blue import _BLUE_SYSTEM_PROMPT_DISCOVERY

    assert _BLUE_SYSTEM_PROMPT_DISCOVERY not in ctx


def test_format_new_evidence_empty_list_still_produces_valid_prompt():
    ctx = bo.format_new_evidence([])
    assert "no new telemetry" in ctx.lower()


def test_run_reasoning_model_passes_history_into_messages(monkeypatch):
    """Regression: found live 2026-07-18 — run_reasoning_model rebuilt a
    fresh system+user pair every call with zero memory of its own prior
    turns, so every hunt-loop round was a cold re-derivation instead of
    genuine iterative refinement. `history` must be threaded into the
    actual message list sent to the model."""
    seen_messages = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        seen_messages.extend(messages)
        return {"content": json.dumps({"request_more": "still need X", "technique_ids": []})}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    prior_history = [
        {"role": "user", "content": "round 1 context"},
        {"role": "assistant", "content": "round 1 reply"},
    ]
    bo.run_reasoning_model(
        "round 2 context", reasoning_model="m", ground_truth=set(), history=prior_history
    )
    assert seen_messages[0]["role"] == "system"
    assert seen_messages[1] == {"role": "user", "content": "round 1 context"}
    assert seen_messages[2] == {"role": "assistant", "content": "round 1 reply"}
    assert seen_messages[3] == {"role": "user", "content": "round 2 context"}


def test_run_reasoning_model_without_history_is_unchanged(monkeypatch):
    """Backward compat: omitting `history` (existing callers, isolated
    probes) must produce the same single-turn message shape as before."""
    seen_messages = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        seen_messages.extend(messages)
        return {"content": json.dumps({"request_more": "x", "technique_ids": []})}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    bo.run_reasoning_model("ctx", reasoning_model="m", ground_truth=set())
    assert len(seen_messages) == 2
    assert seen_messages[0]["role"] == "system"
    assert seen_messages[1] == {"role": "user", "content": "ctx"}


def test_bias_tool_schemas_narrows_to_windows_events_on_event_id_mention():
    """Regression: found live 2026-07-18 — a Hunter request naming Event ID
    4769 by name still let the tool model pick query_network_traffic, a
    plausible-sounding but wrong tool, returning a useless generic summary
    the Hunter then embellished past. Deterministically narrow the offered
    tools when the request is this unambiguous."""
    tools = [
        {"function": {"name": "query_splunk"}},
        {"function": {"name": "query_windows_events"}},
        {"function": {"name": "query_web_logs"}},
        {"function": {"name": "query_network_traffic"}},
    ]
    narrowed = bo._bias_tool_schemas("Windows Security event logs, Event ID 4769", tools)
    assert [t["function"]["name"] for t in narrowed] == ["query_windows_events"]


def test_bias_tool_schemas_unbiased_request_keeps_all_tools():
    tools = [
        {"function": {"name": "query_splunk"}},
        {"function": {"name": "query_web_logs"}},
    ]
    unchanged = bo._bias_tool_schemas("web server access logs for suspicious requests", tools)
    assert unchanged == tools


def test_bias_tool_schemas_falls_back_when_windows_tool_not_offered():
    tools = [{"function": {"name": "query_splunk"}}]
    result = bo._bias_tool_schemas("Event ID 4769", tools)
    assert result == tools
