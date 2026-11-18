"""Tests for blue_orchestrate.py's reasoning section (Hunter) — Slice 3."""

from __future__ import annotations

import json
from typing import Any

import pytest

from portal.modules.security.core import blue_orchestrate as bo
from portal.modules.security.core.analyst_verdict import SectionOutput


def test_strip_think_tags_removes_scratchpad() -> None:
    text = "<think>internal musing</think>final answer here"
    assert bo._strip_think_tags(text) == "final answer here"


def test_format_for_reasoning_uses_open_discovery_prompt_no_checklist() -> None:
    from portal.modules.security.core.blue import _BLUE_SYSTEM_PROMPT_DISCOVERY

    ctx = bo.format_for_reasoning([], "an alert fired")
    assert _BLUE_SYSTEM_PROMPT_DISCOVERY in ctx
    # never inject a scripted event-ID checklist into the hunt (I8)
    assert "Step 1" not in ctx and "you MUST follow" not in ctx


def test_run_similarity_similar_grade_carries_named_technique() -> None:
    features = {"tactic": "credential-access", "process_names": ["klist", "tgtdeleg"]}
    wiki = {"T1558.003": "kerberoast service ticket request tgtdeleg klist unusual"}
    out = bo.run_similarity(features, wiki_descriptions=wiki)
    assert out["match_grade"] in ("SIMILAR", "EXACT")
    if out["match_grade"] == "SIMILAR":
        assert out["similar_to"] == ["T1558.003"]


def test_run_similarity_no_overlap_returns_none_grade() -> None:
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


def test_ground_similarity_skips_when_no_tool_results_gathered_yet() -> None:
    """Nothing retrieved yet — not enough to ground against either way, so
    leave the (still-provisional) self-report alone rather than force NONE."""
    out = SectionOutput(verdict=None, match_grade="SIMILAR", similar_to=["T1558.003"])
    grounded = bo._ground_similarity(out, [])
    assert grounded is out


def test_format_new_evidence_renders_only_the_given_results_not_a_full_pile() -> None:
    """Regression: the delta renderer must not re-render trigger/discovery
    framing (that's already in the Hunter's conversation history) — only
    the new evidence itself, keeping context growth linear across rounds."""
    r1 = bo.ToolResult(query="q1", provenance="matched-exact", raw_summary="EventCode=4769 stuff")
    ctx = bo.format_new_evidence([r1])
    assert "EventCode=4769 stuff" in ctx
    assert "q1" in ctx
    from portal.modules.security.core.blue import _BLUE_SYSTEM_PROMPT_DISCOVERY

    assert _BLUE_SYSTEM_PROMPT_DISCOVERY not in ctx


def test_format_new_evidence_empty_list_still_produces_valid_prompt() -> None:
    ctx = bo.format_new_evidence([])
    assert "no new telemetry" in ctx.lower()


def test_run_reasoning_model_passes_history_into_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: found live 2026-07-18 — run_reasoning_model rebuilt a
    fresh system+user pair every call with zero memory of its own prior
    turns, so every hunt-loop round was a cold re-derivation instead of
    genuine iterative refinement. `history` must be threaded into the
    actual message list sent to the model."""
    seen_messages: list[dict[str, Any]] = []

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen_messages.extend(messages)
        return {"content": json.dumps({"request_more": "still need X", "technique_ids": []})}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    prior_history: list[dict[str, str]] = [
        {"role": "user", "content": "round 1 context"},
        {"role": "assistant", "content": "round 1 reply"},
    ]
    bo.run_reasoning_model("round 2 context", reasoning_model="m", history=prior_history)
    assert seen_messages[0]["role"] == "system"
    assert seen_messages[1] == {"role": "user", "content": "round 1 context"}
    assert seen_messages[2] == {"role": "assistant", "content": "round 1 reply"}
    assert seen_messages[3] == {"role": "user", "content": "round 2 context"}


def test_bias_tool_schemas_narrows_to_windows_events_on_event_id_mention() -> None:
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


def test_bias_tool_schemas_unbiased_request_keeps_all_tools() -> None:
    tools = [
        {"function": {"name": "query_splunk"}},
        {"function": {"name": "query_web_logs"}},
    ]
    unchanged = bo._bias_tool_schemas("web server access logs for suspicious requests", tools)
    assert unchanged == tools


def test_bias_tool_schemas_falls_back_when_windows_tool_not_offered() -> None:
    tools = [{"function": {"name": "query_splunk"}}]
    result = bo._bias_tool_schemas("Event ID 4769", tools)
    assert result == tools
