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

    def _fn(model, messages, tools=None, max_tokens=2000, extra_options=None):
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

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
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
                    "evidence": ["EventCode=4769 detail"],
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


def test_expert_receives_hunters_own_multi_round_history_not_just_final_summary(monkeypatch):
    """Regression: found live 2026-07-20 (GATE-D validation). The Expert
    previously only saw reasoning_out's terminal evidence/reasoning fields —
    a one-shot compressed restatement — with the Hunter's actual multi-round
    back-and-forth thrown away. The 2-section "merged" arm never has this
    compression step (same model instance reasons and concludes), which is
    a real, distinct explanation for 3-section underperforming it, separate
    from round-budget exhaustion. The Expert must now see the Hunter's own
    accumulated investigation history at hand-off."""
    import json

    hunter_request_more = json.dumps(
        {
            "request_more": "need windows event details",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "first pass found nothing conclusive, need more detail",
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
    expert_context: dict[str, str] = {}

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model == "expert-model":
            expert_context["ctx"] = messages[-1]["content"]
            return {"content": expert_confirmed}
        if "need windows event details" not in str(messages):
            return {"content": hunter_request_more}
        return {"content": hunter_hypothesis}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert result.verdict == "CONFIRMED"
    assert "Hunter's investigation history" in expert_context["ctx"]
    # The Hunter's own first-round reasoning (not just its terminal summary)
    # must actually be present in what the Expert saw.
    assert "first pass found nothing conclusive" in expert_context["ctx"]


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

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
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


def _two_sections() -> list[bo.SectionSpec]:
    return [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="merged", model="merged-model"),
    ]


def test_two_section_ablation_arm_confirms_without_a_separate_expert(monkeypatch):
    """Slice 8 (GATE-D ablation): the 2-section 'V1 shape' arm — tool + merged
    reasoning/expert — lets one model both hunt and conclude. Only 'tool' and
    'merged' sections should appear in the trace; no 'reasoning'/'expert'."""
    import json

    calls = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        calls.append(model)
        # The merged model is called at the START of each round, before that
        # round's own tool call — round 0 has no gathered evidence yet, so it
        # must request more rather than confirm against nothing.
        if len(calls) == 1:
            return {"content": json.dumps({"request_more": "need AS-REP telemetry"})}
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
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_two_sections(), max_rounds=6)
    assert result.verdict == "CONFIRMED"
    assert result.technique_ids == ["T1558.004"]
    sections_in_trace = {t["section"] for t in result.trace}
    # Only "tool"/"merged" ever appear — no separate "reasoning"/"expert"
    # sections in the 2-section arm. A tool round now precedes confirmation
    # (round 0 has no gathered evidence yet, so it can't confirm on the spot
    # — see _cite_or_drop's docstring on why an ungrounded confirm is dropped).
    assert sections_in_trace == {"tool", "merged"}
    assert "merged-model" in calls
    assert "tool-model" not in calls  # tool section is dry-run-free here (no _call_model)


def test_two_section_ablation_arm_requests_more_then_confirms(monkeypatch):
    import json

    responses = [
        {
            "content": json.dumps(
                {
                    "request_more": "need event 4769",
                    "verdict": "",
                    "technique_ids": [],
                    "evidence": [],
                    "reasoning": "",
                    "match_grade": "NONE",
                    "similar_to": [],
                }
            )
        },
        {
            "content": json.dumps(
                {
                    "verdict": "CONFIRMED",
                    "technique_ids": ["T1558.004"],
                    "evidence": ["EventCode=4769"],
                    "reasoning": "confirmed",
                    "match_grade": "EXACT",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        },
    ]
    monkeypatch.setattr(bo, "_call_model", _fake_call_model_sequence(responses))

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(
            query=req.spec, provenance="matched-exact", raw_summary="EventCode=4769 detail"
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_two_sections(), max_rounds=6)
    assert result.verdict == "CONFIRMED"
    sections_in_trace = [t["section"] for t in result.trace]
    assert sections_in_trace == ["merged", "tool", "merged"]


def test_two_section_never_concluding_hits_max_rounds_unresolved(monkeypatch):
    import json

    always_wants_more = json.dumps(
        {
            "request_more": "still need more",
            "verdict": "",
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

    result = bo.run_blue_orchestration(_episode(), sections=_two_sections(), max_rounds=4)
    assert result.verdict == "UNRESOLVED"
    assert result.rounds >= 4


def test_sections_shape_neither_two_nor_three_raises():
    bad = [bo.SectionSpec(role="tool", model="m"), bo.SectionSpec(role="oracle", model="m")]
    import pytest

    with pytest.raises(ValueError):
        bo.run_blue_orchestration(_episode(), sections=bad, max_rounds=1)


def test_ground_hunter_evidence_downgrades_ungrounded_citation():
    """Regression: found live 2026-07-18 — given a weak/mismatched tool
    result, the Hunter still claimed EXACT match and cited specific details
    (account names, encryption types) never actually present in what was
    retrieved. The Expert correctly refused to confirm it, but only after a
    full round was burned. Catch it one round earlier."""
    hunter_out = bo.SectionOutput(
        verdict="CONFIRMED",
        technique_ids=["T1558.099"],
        evidence=["sAMAccountName svc_account$ RC4_HMAC_MD5 Invoke-Kerberoast"],
        match_grade="EXACT",
        section="reasoning",
    )
    tool_results = [
        bo.ToolResult(
            query="q", provenance="live-broad-fallback", raw_summary="531 events: 4624x147 4672x139"
        )
    ]
    out = bo._ground_hunter_evidence(hunter_out, tool_results, ground_truth={"T1558.003"})
    assert out.wants_more()
    assert "T1558.099" in out.request_more


def test_ground_hunter_evidence_passes_grounded_citation_through():
    hunter_out = bo.SectionOutput(
        verdict="CONFIRMED",
        technique_ids=["T1558.004"],
        evidence=["EventCode=4768 AS-REP event for svc-web"],
        match_grade="EXACT",
        section="reasoning",
    )
    tool_results = [
        bo.ToolResult(
            query="q",
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )
    ]
    out = bo._ground_hunter_evidence(hunter_out, tool_results, ground_truth={"T1558.004"})
    assert out is hunter_out


def test_ground_hunter_evidence_skips_when_nothing_gathered_yet():
    """A hypothesis formed before any tool round has run isn't the
    mismatched-evidence failure mode this guards against — pass through."""
    hunter_out = bo.SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=["T1558.099"],
        evidence=["odd ticket pattern"],
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
        section="reasoning",
    )
    out = bo._ground_hunter_evidence(hunter_out, [], ground_truth={"T1558.004"})
    assert out is hunter_out


def test_ground_hunter_evidence_passes_through_when_wants_more_already():
    hunter_out = bo.SectionOutput(request_more="need more data", section="reasoning")
    out = bo._ground_hunter_evidence(
        hunter_out, [bo.ToolResult(query="q", raw_summary="x")], ground_truth=set()
    )
    assert out is hunter_out


def test_hunter_stall_hands_off_to_expert_instead_of_running_out_the_clock(monkeypatch):
    """Regression: found live 2026-07-18, meta3_tomcat_manager — the Hunter's
    output contract has no way to say "search exhausted, nothing here"; it
    can only propose a hypothesis or request_more, so a genuinely exhausted
    search looped until max_rounds without ever reaching the Expert. After 3
    consecutive no-hypothesis rounds, the Expert must get a turn — and
    RULED_OUT (its own honest judgment, not a forced answer) must be
    reachable well before the round budget runs out."""
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
    expert_ruled_out = json.dumps(
        {
            "verdict": "RULED_OUT",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "nothing conclusive after an exhaustive search",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )

    calls = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        calls.append(model)
        if model == "expert-model":
            return {"content": expert_ruled_out}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=20)
    assert result.verdict == "RULED_OUT"
    # Reached the Expert well before the 20-round budget — the stall cap
    # (3 consecutive no-hypothesis rounds) fired, not exhaustion.
    assert result.rounds < 12
    assert "expert-model" in calls


def test_stall_handoff_under_default_budget_tells_expert_no_more_evidence_possible(monkeypatch):
    """Regression: found live 2026-07-20 (GATE-D validation). Under the
    *default* budget (max_rounds=6, stall_cap=3), a stall-triggered Expert
    hand-off always lands with 0 rounds left afterward — the old note
    ("you may still request one targeted gap") was being offered on every
    single stalled conclusion despite it being structurally impossible to
    honor; the Expert doing so anyway forced UNRESOLVED instead of the
    RULED_OUT/ANOMALOUS_UNCLASSIFIED it had just been told were valid. The
    Expert's prompt must instead say plainly there is no more budget and it
    must conclude now — not dangle a request option that can never work."""
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
    expert_ruled_out = json.dumps(
        {
            "verdict": "RULED_OUT",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "nothing conclusive",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    expert_context: dict[str, str] = {}

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model == "expert-model":
            expert_context["ctx"] = messages[-1]["content"]
            return {"content": expert_ruled_out}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections())  # default max_rounds=6
    assert result.verdict == "RULED_OUT"
    assert "final round" in expert_context["ctx"]
    assert "MUST render" in expert_context["ctx"]
    assert "you may still request" not in expert_context["ctx"].lower()


def test_expert_gets_one_retry_before_unresolved_when_it_ignores_final_round_note(monkeypatch):
    """Regression: found live 2026-07-20 (GATE-D validation) live-testing the
    fix above — even after being told plainly "this is the final round, you
    MUST render a verdict," the Expert model sometimes still returns
    verdict=None with a request_more anyway. That's a real model-compliance
    gap, not something to fabricate past (I8) — but a model ignoring an
    instruction once isn't proof it can't comply, so it gets exactly one
    retry with an even more direct nudge (same "same retry budget"
    discipline as blue._run_blue_turn's P5-SCORING-BIAS-001) before
    UNRESOLVED is accepted. The retry must not consume the tool-gather round
    budget — no new evidence is being requested, only a repeated ask."""
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
    expert_still_refuses = json.dumps(
        {
            "verdict": None,
            "technique_ids": [],
            "evidence": [],
            "reasoning": "",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "need one more thing",
        }
    )
    expert_complies_on_retry = json.dumps(
        {
            "verdict": "RULED_OUT",
            "technique_ids": [],
            "evidence": [],
            "reasoning": "nothing conclusive, no more evidence coming",
            "match_grade": "NONE",
            "similar_to": [],
            "request_more": "",
        }
    )
    expert_call_count = {"n": 0}
    retry_ctx: dict[str, str] = {}

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model == "expert-model":
            expert_call_count["n"] += 1
            if expert_call_count["n"] == 1:
                return {"content": expert_still_refuses}
            retry_ctx["ctx"] = messages[-1]["content"]
            return {"content": expert_complies_on_retry}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections())  # default max_rounds=6
    assert result.verdict == "RULED_OUT"
    assert expert_call_count["n"] == 2  # original + exactly one retry
    assert "did not render a verdict" in retry_ctx["ctx"]
    # The retry is a compliance nudge, not a new evidence-gathering round —
    # rounds must still reflect the original 6-round budget accounting, not
    # an extra round burned on the retry itself.
    assert result.rounds <= 6


def test_capture_expert_handoff_resume_matches_live_run_and_skips_rerun(monkeypatch):
    """capture_expert_handoff + resume_from_handoff must (a) produce the same
    verdict a full run_blue_orchestration call would for the same models, and
    (b) never re-invoke the tool/reasoning models on resume — the whole point
    is comparing N expert candidates without paying the tool+reasoning cost
    N times."""
    import json

    call_log: list[str] = []
    reasoning_calls = {"n": 0}

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        call_log.append(model)
        if model == "reasoning-model":
            reasoning_calls["n"] += 1
            if reasoning_calls["n"] == 1:
                # Round 0 — no tool round has run yet, so no evidence to
                # propose a technique from. Request more, matching real flow.
                return {"content": json.dumps({"request_more": "need AS-REP telemetry"})}
            return {
                "content": json.dumps(
                    {
                        "technique_ids": ["T1558.004"],
                        "evidence": ["EventCode=4768 AS-REP event for svc-web"],
                        "reasoning": "confirmed",
                        "match_grade": "EXACT",
                        "similar_to": [],
                        "request_more": "",
                    }
                )
            }
        # any expert model — same canned CONFIRMED verdict regardless of name
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
        call_log.append(tool_model)
        return bo.ToolResult(
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    live_result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert live_result.verdict == "CONFIRMED"

    call_log.clear()
    reasoning_calls["n"] = 0
    handoff = bo.capture_expert_handoff(
        _episode(),
        models={"tool": "tool-model", "reasoning": "reasoning-model", "expert": "unused"},
        max_rounds=6,
    )
    assert isinstance(handoff, bo.ExpertHandoff)
    calls_during_capture = list(call_log)
    assert "reasoning-model" in calls_during_capture

    call_log.clear()
    result_a = bo.resume_from_handoff(handoff, "expert-candidate-a")
    result_b = bo.resume_from_handoff(handoff, "expert-candidate-b")

    assert result_a.verdict == "CONFIRMED" == result_b.verdict
    assert result_a.verdict == live_result.verdict
    # Resuming twice must not re-invoke the tool or reasoning model at all —
    # only the two expert candidates should appear in the call log.
    assert call_log == ["expert-candidate-a", "expert-candidate-b"]


def test_expert_handoff_round_trips_through_json(monkeypatch):
    """ExpertHandoff must survive to_dict/from_dict — this is what makes a
    capture durable across separate script invocations, not just usable
    within one Python process."""
    import json

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "content": json.dumps(
                {
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
        return bo.ToolResult(query=req.spec, provenance="matched-exact", raw_summary="unused")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    handoff = bo.capture_expert_handoff(
        _episode(),
        models={"tool": "tool-model", "reasoning": "reasoning-model", "expert": "unused"},
        max_rounds=6,
    )
    assert isinstance(handoff, bo.ExpertHandoff)

    round_tripped = bo.ExpertHandoff.from_dict(json.loads(json.dumps(handoff.to_dict())))
    assert round_tripped.ectx == handoff.ectx
    assert round_tripped.ground_truth == handoff.ground_truth
    assert round_tripped.tool_results == handoff.tool_results
    assert round_tripped.told_expert_final_round == handoff.told_expert_final_round
    assert round_tripped.rounds == handoff.rounds


def test_capture_hunter_handoff_resume_matches_live_run_and_skips_rerun(monkeypatch):
    """capture_hunter_handoff + resume_hunter_from_handoff must (a) produce
    the same Hunter output a live run would for the round that determines
    hand-off, and (b) never re-invoke the tool model on resume — same
    contract as the Expert-side capture/resume, one level up the chain."""
    import json

    call_log: list[str] = []

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        call_log.append(model)
        if model == "reasoning-model" and call_log.count("reasoning-model") == 1:
            return {"content": json.dumps({"request_more": "need event 4769", "technique_ids": []})}
        if model.startswith("reasoning") or model.startswith("candidate"):
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
                    "evidence": ["EventCode=4769 detail"],
                    "reasoning": "confirmed",
                    "match_grade": "EXACT",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        call_log.append(tool_model)
        return bo.ToolResult(
            query=req.spec, provenance="matched-exact", raw_summary="EventCode=4769 detail"
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    live_result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert live_result.verdict == "CONFIRMED"

    call_log.clear()
    handoff = bo.capture_hunter_handoff(
        _episode(),
        models={"tool": "tool-model", "reasoning": "reasoning-model", "expert": "unused"},
        max_rounds=6,
    )
    assert isinstance(handoff, bo.HunterHandoff)
    assert "tool-model" in call_log  # the first gather round did run
    assert (
        call_log.count("reasoning-model") == 2
    )  # round 1 (request_more) + round 2 (captured, not resumed)

    call_log.clear()
    out_a = bo.resume_hunter_from_handoff(handoff, "candidate-a")
    out_b = bo.resume_hunter_from_handoff(handoff, "candidate-b")

    assert out_a.technique_ids == ["T1558.004"]
    assert out_b.technique_ids == ["T1558.004"]
    # Resuming twice must not touch the tool model at all.
    assert call_log == ["candidate-a", "candidate-b"]


def test_hunter_handoff_round_trips_through_json(monkeypatch):
    """HunterHandoff must survive to_dict/from_dict for the same durability
    reason ExpertHandoff does."""
    import json

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {"content": json.dumps({"request_more": "need more", "technique_ids": []})}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="matched-exact", raw_summary="unused")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    handoff = bo.capture_hunter_handoff(
        _episode(),
        models={"tool": "tool-model", "reasoning": "unused", "expert": "unused"},
        max_rounds=6,
    )
    assert isinstance(handoff, bo.HunterHandoff)

    round_tripped = bo.HunterHandoff.from_dict(json.loads(json.dumps(handoff.to_dict())))
    assert round_tripped.ctx == handoff.ctx
    assert round_tripped.hunter_history == handoff.hunter_history
    assert round_tripped.tool_results == handoff.tool_results
    assert round_tripped.ground_truth == handoff.ground_truth
    assert round_tripped.rounds == handoff.rounds


def test_council_dispatch_unanimous_confirmed(monkeypatch):
    """run_blue_orchestration with a multi-model reasoning roster must route
    to _run_council, gather evidence once (shared hand-off), then have every
    council member conclude from that same evidence -- unanimous CONFIRMED
    across all 3 members should surface as CONFIRMED with agreement=1.0."""
    import json

    calls = []
    lead_hunter_calls = {"n": 0}

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        calls.append(model)
        if model == "lead-hunter":
            lead_hunter_calls["n"] += 1
            if lead_hunter_calls["n"] == 1:
                # Round 0 — no tool round has run yet, request more first
                # (matches real flow, and how the other loop tests handle it).
                return {"content": json.dumps({"request_more": "need AS-REP telemetry"})}
            return {
                "content": json.dumps(
                    {
                        "technique_ids": ["T1558.004"],
                        "evidence": ["EventCode=4768 AS-REP event for svc-web"],
                        "reasoning": "AS-REP roasting pattern",
                        "match_grade": "EXACT",
                        "similar_to": [],
                        "request_more": "",
                    }
                )
            }
        # every council member call
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
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="lead-hunter"),
        bo.SectionSpec(role="reasoning", model="member-b"),
        bo.SectionSpec(role="reasoning", model="member-c"),
    ]
    result = bo.run_blue_orchestration(_episode(), sections=sections, max_rounds=6)
    assert result.verdict == "CONFIRMED"
    assert result.technique_ids == ["T1558.004"]

    council_entries = [t for t in result.trace if t.get("section") == "council_member"]
    assert len(council_entries) == 3
    assert {e["model"] for e in council_entries} == {"lead-hunter", "member-b", "member-c"}
    agreement_entry = [t for t in result.trace if t.get("section") == "agreement"][0]
    assert agreement_entry["agreement"] == 1.0


def test_council_split_with_arbiter_breaks_tie(monkeypatch):
    """3-way split (no quorum) must route to the fed arbiter, which -- when
    it renders its own conclusion -- supersedes the split verdict."""
    import json

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model == "lead-hunter":
            return {
                "content": json.dumps(
                    {
                        "technique_ids": ["T1078"],
                        "evidence": ["EventCode=4624"],
                        "reasoning": "possible valid accounts abuse",
                        "match_grade": "SIMILAR",
                        "similar_to": ["T1078"],
                        "request_more": "",
                    }
                )
            }
        if model == "member-a":
            verdict, tids = "CONFIRMED", ["T1078"]
        elif model == "member-b":
            verdict, tids = "CONFIRMED", ["T1055"]
        elif model == "member-c":
            verdict, tids = "CONFIRMED", ["T1548"]
        elif model == "arbiter-model":
            verdict, tids = "ANOMALOUS_UNCLASSIFIED", []
        else:
            raise AssertionError(f"unexpected model {model}")
        return {
            "content": json.dumps(
                {
                    "verdict": verdict,
                    "technique_ids": tids,
                    "evidence": ["EventCode=4624"],
                    "reasoning": "member verdict",
                    "match_grade": "SIMILAR",
                    "similar_to": [],
                    "request_more": "",
                }
            )
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(
            query=req.spec, provenance="matched-exact", raw_summary="EventCode=4624"
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="lead-hunter"),
        bo.SectionSpec(role="reasoning", model="member-a"),
        bo.SectionSpec(role="reasoning", model="member-b"),
        bo.SectionSpec(role="reasoning", model="member-c"),
        bo.SectionSpec(role="expert", model="arbiter-model"),
    ]
    result = bo.run_blue_orchestration(_episode(), sections=sections, max_rounds=6)

    arbiter_entries = [t for t in result.trace if t.get("section") == "arbiter"]
    assert len(arbiter_entries) == 1
    assert arbiter_entries[0]["model"] == "arbiter-model"
    # Arbiter's own ANOMALOUS_UNCLASSIFIED conclusion supersedes the 3-way split.
    assert result.verdict == "ANOMALOUS_UNCLASSIFIED"


def test_council_unresolved_when_no_handoff_reached(monkeypatch):
    """If the shared hunter loop never reaches a hand-off (budget exhausted
    mid-loop), the council has nothing to agree on -- must surface UNRESOLVED,
    not crash or fabricate a verdict."""
    import json

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        # Hunter always wants more, forever -- never triggers hand-off.
        return {"content": json.dumps({"request_more": "still need more", "technique_ids": []})}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(req, *, tool_model, ground_truth, episode, dry_run=False):
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="reasoning", model="lead-hunter"),
        bo.SectionSpec(role="reasoning", model="member-b"),
    ]
    # max_rounds=1: budget exhausts before the stall-cap (3) is ever reached,
    # so capture_expert_handoff never gets to a hand-off point.
    result = bo.run_blue_orchestration(_episode(), sections=sections, max_rounds=1)
    assert result.verdict == "UNRESOLVED"


def test_three_section_and_two_section_unaffected_by_council_dispatch(monkeypatch):
    """I7: adding council dispatch must not change _run_three_section's or
    _run_two_section's own behavior for their existing single-model callers."""
    import json

    seen_models: set[str] = set()

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        # Each role's own FIRST call happens before that round's tool call
        # has run, so it must request more rather than confirm against no
        # evidence — matches _cite_or_drop's grounding requirement.
        if model not in seen_models:
            seen_models.add(model)
            return {"content": json.dumps({"request_more": "need AS-REP telemetry"})}
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
            query=req.spec,
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    three = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert three.verdict == "CONFIRMED"
    assert not any(t.get("section") == "council_member" for t in three.trace)

    two_sections = [
        bo.SectionSpec(role="tool", model="tool-model", needs_tools=True),
        bo.SectionSpec(role="merged", model="merged-model"),
    ]
    two = bo.run_blue_orchestration(_episode(), sections=two_sections, max_rounds=6)
    assert two.verdict == "CONFIRMED"
    assert not any(t.get("section") == "council_member" for t in two.trace)


def _multichain_episode() -> Episode:
    """Episode with two real telemetry sources so evidence_diversity is
    exercisable across independent chains."""
    return Episode(
        scenario="asrep_to_lateral",
        target_host="dc01",
        techniques=["T1558.004"],
        telemetry={
            "windows:security": ["EventCode=4768 AS-REP event for svc-web"],
            "web:access": ["10.0.0.25 GET / HTTP/1.1 200"],
        },
    )


def test_multichain_independent_convergence_is_auto_confirm(monkeypatch):
    """N independent chains that each hunt their own way and converge on the
    same technique consolidate to AUTO_CONFIRM. Each chain is a FULL
    tool+reasoning+expert investigation (its own tool queries), not a shared-
    pool voter — the trace carries per-chain tags and a consolidation entry."""
    import json

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        # Every reasoning/expert model, in every chain, concludes CONFIRMED
        # T1558.004 from its own gathered evidence.
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
            query="windows:security EventCode 4768 query",
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_multichain_orchestration(
        _multichain_episode(),
        tool_model="tool-model",
        chain_models=["chain-a", "chain-b", "chain-c"],
        expert_model="expert-model",
        max_rounds=6,
    )
    assert result.verdict == "CONFIRMED"
    assert result.technique_ids == ["T1558.004"]
    consolidation = [t for t in result.trace if t.get("section") == "consolidation"]
    assert len(consolidation) == 1
    assert consolidation[0]["decision"] == "AUTO_CONFIRM"
    # Each chain's trace is tagged and preserved (independent investigations).
    chains_seen = {t.get("chain") for t in result.trace if t.get("chain")}
    assert chains_seen == {"chain-a", "chain-b", "chain-c"}


def test_multichain_divergent_chains_escalate_to_human(monkeypatch):
    """Independent chains that each surface a DIFFERENT technique consolidate
    to ESCALATE ('a human needs to look at this'), never a forced confirm."""
    import json

    # Each chain (keyed by its reasoning model name) concludes a different tech.
    per_model = {
        "chain-a": "T1558.004",
        "chain-b": "T1078",
        "chain-c": "T1021.002",
    }

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        tech = per_model.get(model, "T1558.004")
        return {
            "content": json.dumps(
                {
                    "verdict": "CONFIRMED",
                    "technique_ids": [tech],
                    "evidence": [f"evidence for {tech}"],
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
            query="q", provenance="matched-exact", raw_summary="some real evidence"
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    # No shared expert — each chain concludes with its OWN model, so the
    # divergence at the reasoning step survives to the verdict (full
    # independence, the faithful multi-chain config).
    result = bo.run_multichain_orchestration(
        _multichain_episode(),
        tool_model="tool-model",
        chain_models=["chain-a", "chain-b", "chain-c"],
        quorum=0.5,
    )
    assert result.verdict == "ANOMALOUS_UNCLASSIFIED"
    consolidation = [t for t in result.trace if t.get("section") == "consolidation"][0]
    assert consolidation["decision"] == "ESCALATE"
    assert consolidation["escalation_reason"]


def test_multichain_does_not_alter_existing_arms(monkeypatch):
    """I7: run_multichain_orchestration composes run_blue_orchestration but must
    not change 3-section / 2-section / council behaviour for their callers."""
    import json

    seen: set[str] = set()

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        if model not in seen:
            seen.add(model)
            return {"content": json.dumps({"request_more": "need telemetry"})}
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
            query="q",
            provenance="matched-exact",
            raw_summary="EventCode=4768 AS-REP event for svc-web",
        )

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    three = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=6)
    assert three.verdict == "CONFIRMED"
    # No consolidation/chain artefacts leak into a plain 3-section run.
    assert not any(t.get("section") == "consolidation" for t in three.trace)
    assert not any(t.get("chain") for t in three.trace)
