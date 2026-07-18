"""Tests for blue_orchestrate.py's deterministic section-pipeline orchestrator — Slice 5."""

from __future__ import annotations

from portal.modules.security.core import blue_orchestrate as bo
from portal.modules.security.core.agentic_blue_eval import Episode


def _episode() -> Episode:
    return Episode(
        scenario="asrep_to_lateral",
        target_host="dc01",
        techniques=["T1558.004"],
        telemetry={"windows:security": ["EventCode=4768 AS-REP event for svc-web"]},
    )


def _sections() -> list[bo.SectionSpec]:
    return [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="reasoning-model"),
        bo.SectionSpec(role="expert", model="expert-model"),
    ]


def _fake_call_model_sequence(responses):
    """responses: list of dicts, popped in order, one per _call_model call."""
    calls = {"i": 0}

    def _fn(model, messages, tools=None, max_tokens=2000):
        idx = calls["i"]
        calls["i"] += 1
        return responses[idx]

    return _fn


def test_hunter_sees_own_history_and_only_new_evidence_across_rounds(monkeypatch):
    """Regression: found live 2026-07-18 — the Hunter rebuilt a fresh
    system+user pair every hunt-loop round, re-rendering the WHOLE
    accumulated evidence pile with zero memory of its own prior turns.
    Round 2's call to the reasoning model must carry round 1's user+
    assistant turn as history, and its own new user content must be ONLY
    the newly-gathered evidence — not a full re-render of round 1's
    telemetry + trigger again."""
    import json

    calls = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000):
        calls.append({"model": model, "messages": messages})
        if model == "reasoning-model" and len(calls) == 1:
            return {"content": json.dumps({"request_more": "need event 4769", "technique_ids": []})}
        if model == "reasoning-model":
            return {
                "content": json.dumps(
                    {
                        "technique_ids": ["T1558.004"],
                        "evidence": ["EventCode=4769"],
                        "reasoning": "confirmed",
                        "match_grade": "EXACT",
                        "similar_to": [],
                        "request_more": "",
                    }
                )
            }
        return {
            "content": json.dumps(
                {
                    "verdict": "CONFIRMED",
                    "technique_ids": ["T1558.004"],
                    "evidence": ["EventCode=4768 AS-REP event for svc-web"],
                    "reasoning": "confirmed",
                    "match_grade": "EXACT",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(
            query=req.spec, provenance="matched-exact", raw_summary="EventCode=4769 detail"
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert result.verdict == "CONFIRMED"

    reasoning_calls = [c for c in calls if c["model"] == "reasoning-model"]
    assert len(reasoning_calls) == 2

    round1_messages = reasoning_calls[0]["messages"]
    round2_messages = reasoning_calls[1]["messages"]

    # Round 1: no history yet — just system + the initial framing.
    assert len(round1_messages) == 2

    # Round 2: system + round 1's own user/assistant turn (real continuity)
    # + a new user turn that is ONLY the new evidence, not a re-render.
    assert round2_messages[0]["role"] == "system"
    assert round2_messages[1] == round1_messages[1]  # round 1's user turn, verbatim
    assert round2_messages[2]["role"] == "assistant"  # the Hunter's own round-1 reply
    round2_new_turn = round2_messages[-1]["content"]
    assert "EventCode=4769 detail" in round2_new_turn
    # Must NOT re-render the trigger/discovery framing again in round 2's
    # new turn — that's already carried in history.
    from portal.modules.security.core.blue import _BLUE_SYSTEM_PROMPT_DISCOVERY

    assert _BLUE_SYSTEM_PROMPT_DISCOVERY not in round2_new_turn


def test_request_more_tool_reasoning_expert_confirmed_terminates_confirmed(monkeypatch):
    import json

    hunter_request_more = json.dumps(
        {
            "request_more": "need windows event details",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
        }
    )
    hunter_hypothesis = json.dumps(
        {
            "request_more": "",
            "technique_ids": ["T1558.004"],
            "evidence": ["EventCode=4768"],
            "reasoning": "AS-REP roasting pattern",
            "match_grade": "EXACT",
            "similar_to": [],
        }
    )
    expert_confirmed = json.dumps(
        {
            "verdict": "CONFIRMED",
            "technique_ids": ["T1558.004"],
            "evidence": ["EventCode=4768 AS-REP event for svc-web"],
            "reasoning": "confirmed",
            "match_grade": "EXACT",
            "similar_to": [],
            "request_more": "",
        }
    )

    responses = [
        {"content": hunter_request_more},  # reasoning round 1: wants more
        {"content": hunter_hypothesis},  # reasoning round 2: hypothesis
        {"content": expert_confirmed},  # expert: confirms
    ]
    # run_tool_model itself calls _call_model too (tool_model dispatch) — but
    # we drive it with dry_run's episode-telemetry path instead by patching
    # run_tool_model directly to avoid needing a 4th fake response slot.
    monkeypatch.setattr(bo, "_call_model", _fake_call_model_sequence(responses))

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert result.verdict == "CONFIRMED"
    assert result.technique_ids == ["T1558.004"]
    sections_in_trace = [t["section"] for t in result.trace]
    assert sections_in_trace == ["reasoning", "tool", "reasoning", "expert"]


def test_never_concluding_pipeline_hits_max_rounds_unresolved(monkeypatch):
    import json

    always_wants_more = json.dumps(
        {
            "request_more": "still need more",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
        }
    )
    monkeypatch.setattr(bo, "_call_model", lambda *a, **kw: {"content": always_wants_more})

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=4)
    assert result.verdict == "UNRESOLVED"
    assert result.verdict != "ANOMALOUS_UNCLASSIFIED"
    assert result.rounds >= 4


def test_similar_variant_hunt_flows_to_anomalous_unclassified(monkeypatch):
    import json

    hunter_similar = json.dumps(
        {
            "request_more": "",
            "technique_ids": ["T1558.099"],
            "evidence": ["odd ticket pattern"],
            "reasoning": "shares features with T1558.003",
            "match_grade": "SIMILAR",
            "similar_to": ["T1558.003"],
        }
    )
    expert_anomalous = json.dumps(
        {
            "verdict": "ANOMALOUS_UNCLASSIFIED",
            "technique_ids": ["T1558.099"],
            "evidence": ["odd ticket pattern"],
            "reasoning": "confirmed as a variant, not exact match",
            "match_grade": "SIMILAR",
            "similar_to": ["T1558.003"],
            "request_more": "",
        }
    )
    responses = [{"content": hunter_similar}, {"content": expert_anomalous}]
    monkeypatch.setattr(bo, "_call_model", _fake_call_model_sequence(responses))
    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert result.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert result.similar_to == ["T1558.003"]


def test_wall_clock_backstop_fires_independently(monkeypatch):
    import json
    import time

    always_wants_more = json.dumps(
        {
            "request_more": "still need more",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
        }
    )

    def slow_call_model(*a, **kw):
        time.sleep(0.05)
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", slow_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(
        _episode(), sections=_sections(), max_rounds=1000, wall_clock_s=0.12
    )
    assert result.verdict == "UNRESOLVED"
    assert result.rounds < 1000  # backstop fired well before the round cap


def test_sections_list_order_is_honored_model_swap_works(monkeypatch):
    import json

    seen_models = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000):
        seen_models.append(model)
        # Same payload serves both roles: the Hunter parser only reads
        # technique_ids/evidence/reasoning/match_grade/similar_to/request_more
        # (ignores "verdict"), so it treats this as a hypothesis to hand off;
        # the expert parser reads "verdict" and renders RULED_OUT.
        return {
            "content": json.dumps(
                {
                    "verdict": "RULED_OUT",
                    "technique_ids": ["T0000"],
                    "evidence": ["placeholder evidence"],
                    "reasoning": "no supporting evidence for the hypothesis",
                    "match_grade": "NONE",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    custom_sections = [
        bo.SectionSpec(role="tool", model="custom-tool-model"),
        bo.SectionSpec(role="reasoning", model="custom-reasoning-model"),
        bo.SectionSpec(role="expert", model="custom-expert-model"),
    ]
    result = bo.run_blue_orchestration(_episode(), sections=custom_sections, max_rounds=6)
    assert result.verdict == "RULED_OUT"
    assert "custom-reasoning-model" in seen_models
    assert "custom-expert-model" in seen_models


def test_missing_role_in_sections_raises():
    incomplete = [
        bo.SectionSpec(role="tool", model="m"),
        bo.SectionSpec(role="reasoning", model="m"),
    ]
    import pytest

    with pytest.raises(ValueError):
        bo.run_blue_orchestration(_episode(), sections=incomplete, max_rounds=1)
