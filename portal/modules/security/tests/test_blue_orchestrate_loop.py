"""Tests for blue_orchestrate.py's deterministic section-pipeline orchestrator — Slice 5."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core import blue_orchestrate as bo
from portal.modules.security.core.agentic_blue_eval import Episode
from portal.modules.security.core.analyst_verdict import SectionOutput


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


def test_hunter_sees_own_history_and_only_new_evidence_across_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: found live 2026-07-18 — the Hunter rebuilt a fresh
    system+user pair every hunt-loop round, re-rendering the WHOLE
    accumulated evidence pile with zero memory of its own prior turns.
    Round 2's call to the reasoning model must carry round 1's user+
    assistant turn as history, and its own new user content must be ONLY
    the newly-gathered evidence — not a full re-render of round 1's
    telemetry + trigger again."""
    import json

    calls: list[dict[str, Any]] = []

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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

    def fake_run_tool_model(
        req: bo.ToolRequest,
        *,
        tool_model: str,
        episode: Episode,
        dry_run: bool = False,
    ) -> bo.ToolResult:
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


def test_expert_receives_hunters_own_multi_round_history_not_just_final_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if model == "expert-model":
            expert_context["ctx"] = messages[-1]["content"]
            return {"content": expert_confirmed}
        if "need windows event details" not in str(messages):
            return {"content": hunter_request_more}
        return {"content": hunter_hypothesis}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(
        req: bo.ToolRequest,
        *,
        tool_model: str,
        episode: Episode,
        dry_run: bool = False,
    ) -> bo.ToolResult:
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


def test_missing_role_in_sections_raises() -> None:
    incomplete = [
        bo.SectionSpec(role="tool", model="m"),
        bo.SectionSpec(role="reasoning", model="m"),
    ]
    import pytest

    with pytest.raises(ValueError):
        bo.run_blue_orchestration(_episode(), sections=incomplete, max_rounds=1)


def test_sections_shape_neither_two_nor_three_raises() -> None:
    bad = [bo.SectionSpec(role="tool", model="m"), bo.SectionSpec(role="oracle", model="m")]
    import pytest

    with pytest.raises(ValueError):
        bo.run_blue_orchestration(_episode(), sections=bad, max_rounds=1)


def test_ground_hunter_evidence_downgrades_ungrounded_citation() -> None:
    """Regression: found live 2026-07-18 — given a weak/mismatched tool
    result, the Hunter still claimed EXACT match and cited specific details
    (account names, encryption types) never actually present in what was
    retrieved. The Expert correctly refused to confirm it, but only after a
    full round was burned. Catch it one round earlier."""
    hunter_out = SectionOutput(
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
    out = bo._ground_hunter_evidence(hunter_out, tool_results)
    assert out.wants_more()
    assert "T1558.099" in out.request_more


def test_ground_hunter_evidence_passes_grounded_citation_through() -> None:
    hunter_out = SectionOutput(
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
    out = bo._ground_hunter_evidence(hunter_out, tool_results)
    assert out is hunter_out


def test_ground_hunter_evidence_skips_when_nothing_gathered_yet() -> None:
    """A hypothesis formed before any tool round has run isn't the
    mismatched-evidence failure mode this guards against — pass through."""
    hunter_out = SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        technique_ids=["T1558.099"],
        evidence=["odd ticket pattern"],
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
        section="reasoning",
    )
    out = bo._ground_hunter_evidence(hunter_out, [])
    assert out is hunter_out


def test_ground_hunter_evidence_passes_through_when_wants_more_already() -> None:
    hunter_out = SectionOutput(request_more="need more data", section="reasoning")
    out = bo._ground_hunter_evidence(hunter_out, [bo.ToolResult(query="q", raw_summary="x")])
    assert out is hunter_out


def test_hunter_stall_hands_off_to_expert_instead_of_running_out_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append(model)
        if model == "expert-model":
            return {"content": expert_ruled_out}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(
        req: bo.ToolRequest,
        *,
        tool_model: str,
        episode: Episode,
        dry_run: bool = False,
    ) -> bo.ToolResult:
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections(), max_rounds=20)
    assert result.verdict == "RULED_OUT"
    # Reached the Expert well before the 20-round budget — the stall cap
    # (3 consecutive no-hypothesis rounds) fired, not exhaustion.
    assert result.rounds < 12
    assert "expert-model" in calls


def test_stall_handoff_under_default_budget_tells_expert_no_more_evidence_possible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if model == "expert-model":
            expert_context["ctx"] = messages[-1]["content"]
            return {"content": expert_ruled_out}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(
        req: bo.ToolRequest,
        *,
        tool_model: str,
        episode: Episode,
        dry_run: bool = False,
    ) -> bo.ToolResult:
        return bo.ToolResult(query=req.spec, provenance="empty", raw_summary="")

    monkeypatch.setattr(bo, "run_tool_model", fake_run_tool_model)

    result = bo.run_blue_orchestration(_episode(), sections=_sections())  # default max_rounds=6
    assert result.verdict == "RULED_OUT"
    assert "final round" in expert_context["ctx"]
    assert "MUST render" in expert_context["ctx"]
    assert "you may still request" not in expert_context["ctx"].lower()


def test_expert_gets_one_retry_before_unresolved_when_it_ignores_final_round_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def fake_call_model(
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if model == "expert-model":
            expert_call_count["n"] += 1
            if expert_call_count["n"] == 1:
                return {"content": expert_still_refuses}
            retry_ctx["ctx"] = messages[-1]["content"]
            return {"content": expert_complies_on_retry}
        return {"content": always_wants_more}

    monkeypatch.setattr(bo, "_call_model", fake_call_model)

    def fake_run_tool_model(
        req: bo.ToolRequest,
        *,
        tool_model: str,
        episode: Episode,
        dry_run: bool = False,
    ) -> bo.ToolResult:
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


# ── V3A: Mentor ──────────────────────────────────────────────────────────


def test_mentor_prompt_scan_forbids_prescriptive_tokens() -> None:
    from scripts.validation.blue_orchestration import check_mentor_discipline

    status, detail, _subs = check_mentor_discipline()
    assert status == "PASS", detail


# ── V3B: Per-role budgets ────────────────────────────────────────────────


# ── V3C: Barrier tools ───────────────────────────────────────────────────


def test_barrier_tool_schemas_shape_static() -> None:
    names = [t["function"]["name"] for t in bo._BARRIER_TOOL_SCHEMAS]
    assert set(names) == {"emit_verdict", "escalate_anomalous", "request_more"}
    emit = next(t for t in bo._BARRIER_TOOL_SCHEMAS if t["function"]["name"] == "emit_verdict")
    enum_vals = emit["function"]["parameters"]["properties"]["verdict"]["enum"]
    assert set(enum_vals) == {"CONFIRMED", "RULED_OUT"}
    for t in bo._BARRIER_TOOL_SCHEMAS:
        assert t["function"]["parameters"]["required"]


# ── Council-unfit model warning ─────────────────────────────────────────
