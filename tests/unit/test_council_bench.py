"""Deterministic tests for the council bench: scoring, labels, and fixture shape.

No live calls. The HTTP boundary is never exercised; ``build_request`` is checked
because it is the one place where a case's label could leak to a reviewer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.council_bench import (
    Case,
    _merge_echo,
    build_request,
    extract_timings,
    key_issue_hit,
    load_cases,
    override_echo,
    percentile,
    run_bench,
    score_case,
    summarise,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "council" / "cases.json"


def _case(**overrides: object) -> Case:
    base: dict[str, object] = {
        "id": "case-x",
        "category": "hidden_flaw",
        "submission": "A proposal with no marker in it.",
        "expected_outcome": "REVISE",
        "key_issue": "The key issue.",
        "key_issue_markers": ("marker",),
    }
    base.update(overrides)
    return Case(**base)  # type: ignore[arg-type]


def _reviewer(
    recommendation: str = "REVISE",
    *,
    claim: str = "A finding",
    evidence: list[str] | None = None,
    valid: bool = True,
    error: str = "",
) -> dict[str, object]:
    return {
        "member_id": "evidence",
        "model": "m1",
        "recommendation": recommendation,
        "valid": valid,
        "error": error,
        "findings": [{"claim": claim, "evidence": evidence or [], "action": "do it"}],
        "missing_evidence": [],
        "strongest_objection": "",
        "conditions_to_change": [],
    }


def _payload(
    decision: str = "REVISE",
    reviewers: list[dict[str, object]] | None = None,
    synthesis: str = "",
) -> dict[str, object]:
    return {
        "portal_council": {
            "aggregate": {
                "decision": decision,
                "votes": {"SUPPORT": 0, "REVISE": 2, "REJECT": 0},
                "participation": 0.667,
                "participating": 2,
                "roster": 3,
                "dissent": [],
            },
            "reviewers": reviewers or [],
        },
        "choices": [{"message": {"content": synthesis}}],
    }


# ── Fixture ──────────────────────────────────────────────────────────────────


def test_fixture_is_the_fixed_twenty_case_set() -> None:
    cases = load_cases(FIXTURE)
    assert len(cases) == 20
    assert len({case.id for case in cases}) == 20
    assert {case.category for case in cases} >= {
        "clear_support",
        "clear_reject",
        "hidden_flaw",
        "missing_evidence",
        "stale_claim",
        "operational_risk",
        "split",
    }
    assert all(case.key_issue_markers for case in cases)
    assert {case.expected_outcome for case in cases} <= {"SUPPORT", "REVISE", "REJECT"}


def test_loader_rejects_a_marker_that_already_appears_in_the_submission(tmp_path: Path) -> None:
    payload = {
        "cases": [
            {
                "id": "leaky",
                "category": "hidden_flaw",
                "submission": "This submission says stale in plain text.",
                "expected_outcome": "REVISE",
                "key_issue": "It is stale.",
                "key_issue_markers": ["stale"],
            }
        ]
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="already appear"):
        load_cases(path)


def test_request_carries_only_the_submission() -> None:
    case = load_cases(FIXTURE)[0]
    body = build_request(case)
    assert body == {
        "model": "auto-council",
        "stream": False,
        "messages": [{"role": "user", "content": case.submission}],
    }
    serialised = json.dumps(body).lower()
    for answer in (case.id, case.category, case.expected_outcome, case.key_issue):
        assert answer.lower() not in serialised
    for marker in case.key_issue_markers:
        assert marker not in serialised


def test_override_uses_the_documented_body_key() -> None:
    body = build_request(_case(), {"mode": "early_quorum"})
    assert body["portal_council_config"] == {"mode": "early_quorum"}


def test_a_whole_run_never_sends_a_label() -> None:
    cases = load_cases(FIXTURE)[:3]
    sent: list[dict[str, object]] = []

    def post(body: dict[str, object]) -> dict[str, object]:
        sent.append(body)
        return _payload("SUPPORT")

    run = run_bench(cases, post=post, label="default", override=None)
    assert run["summary"]["errors"] == 0
    for body, case in zip(sent, cases, strict=True):
        assert body["messages"] == [{"role": "user", "content": case.submission}]
        serialised = json.dumps(body)
        for answer in (case.id, case.category, case.expected_outcome, case.key_issue):
            assert answer not in serialised
        for marker in case.key_issue_markers:
            assert marker not in serialised.lower()


# ── Scoring ──────────────────────────────────────────────────────────────────


def test_outcome_accepts_the_label_and_declared_alternatives() -> None:
    revise = _case()
    assert score_case(revise, _payload("REVISE"), 1.0)["outcome_ok"] is True
    assert score_case(revise, _payload("REJECT"), 1.0)["outcome_ok"] is False

    split = _case(expected_outcome="REVISE", acceptable_outcomes=("REVISE", "ESCALATE"))
    assert score_case(split, _payload("ESCALATE"), 1.0)["outcome_ok"] is True


def test_key_issue_hit_in_an_evidence_backed_finding() -> None:
    payload = _payload(reviewers=[_reviewer(claim="The marker is the flaw", evidence=["quote"])])
    record = score_case(_case(), payload, 1.0)
    assert record["key_issue_hit"] is True
    assert record["key_issue_source"] == "reviewers"
    assert record["key_issue_evidence_backed"] is True


def test_key_issue_hit_without_evidence_is_not_backed() -> None:
    payload = _payload(reviewers=[_reviewer(claim="The marker is the flaw")])
    record = score_case(_case(), payload, 1.0)
    assert record["key_issue_hit"] is True
    assert record["key_issue_evidence_backed"] is False


def test_key_issue_hit_falls_back_to_the_synthesis() -> None:
    record = score_case(_case(), _payload(synthesis="This review names the marker."), 1.0)
    assert record["key_issue_hit"] is True
    assert record["key_issue_source"] == "synthesis"
    assert record["key_issue_evidence_backed"] is False


def test_key_issue_miss_when_nobody_names_it() -> None:
    hit, source, backed = key_issue_hit(_case(), [_reviewer(claim="Unrelated")], "Unrelated.")
    assert (hit, source, backed) == (False, "", False)


def test_key_issue_matching_ignores_hyphens() -> None:
    case = _case(key_issue_markers=("test-only", "low-risk"))
    assert key_issue_hit(case, [_reviewer(claim="This is a test only change")], "")[0] is True
    assert key_issue_hit(case, [_reviewer(claim="A low risk change")], "")[0] is True


def test_score_records_seat_votes_and_participation() -> None:
    reviewers = [
        _reviewer("SUPPORT"),
        _reviewer("ABSTAIN"),
        _reviewer("ABSTAIN", valid=False, error="skipped by early quorum"),
    ]
    record = score_case(_case(), _payload("REVISE", reviewers), 2.5)
    assert record["votes"] == {"SUPPORT": 0, "REVISE": 2, "REJECT": 0}
    assert record["roster"] == 3
    assert [seat["participated"] for seat in record["seats"]] == [True, False, False]
    assert record["seats"][2]["error"] == "skipped by early quorum"
    assert record["wall_s"] == 2.5


def test_malformed_response_is_an_error_miss() -> None:
    record = score_case(_case(), {}, 1.0)
    assert record["decision"] == ""
    assert record["outcome_ok"] is False
    assert record["key_issue_hit"] is False
    assert "portal_council" in record["error"]


# ── Aggregation ──────────────────────────────────────────────────────────────


def test_percentile_is_nearest_rank() -> None:
    assert percentile([], 90) is None
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 90) == 5.0
    with pytest.raises(ValueError):
        percentile([1.0], 0)


def test_summary_reports_accuracy_recall_and_time() -> None:
    case = _case()
    hit = _payload("REVISE", [_reviewer(claim="The marker is the flaw", evidence=["quote"])])
    miss = _payload("SUPPORT", [_reviewer(claim="Unrelated")])
    records = [
        score_case(case, hit, 1.0),
        score_case(case, miss, 2.0),
        score_case(case, hit, 3.0),
        score_case(case, miss, 10.0),
    ]
    summary = summarise(records)
    assert summary["cases"] == 4
    assert summary["accuracy"] == 0.5
    assert summary["key_issue_recall"] == 0.5
    assert summary["median_wall_s"] == 2.5
    assert summary["p90_wall_s"] == 10.0
    assert summary["by_category"]["hidden_flaw"]["cases"] == 4
    assert summary["seats"]["evidence"]["appearances"] == 4


# ── Timings and override echo ────────────────────────────────────────────────


def test_extract_timings_from_a_stage_list() -> None:
    payload = {
        "portal_council": {
            "timings": {
                "total_s": 12.5,
                "stages": [
                    {
                        "role": "reviewer",
                        "member_id": "evidence",
                        "model": "granite",
                        "cold_load_s": 1.5,
                        "prefill_s": 0.4,
                        "decode_s": 2.0,
                        "tokens": 300,
                        "wall_s": 3.9,
                    }
                ],
            }
        }
    }
    timings = extract_timings(payload)
    assert timings["source"] == "portal_council.timings"
    assert timings["total_wall_s"] == 12.5
    assert timings["stages"][0] == {
        "role": "reviewer",
        "member_id": "evidence",
        "model": "granite",
        "cold_load_s": 1.5,
        "prefill_s": 0.4,
        "decode_s": 2.0,
        "tokens": 300.0,
        "wall_s": 3.9,
    }


def test_extract_timings_reads_seats_and_synthesizer() -> None:
    payload = {
        "portal_council": {
            "timings": {
                "seats": [{"member_id": "evidence", "total_s": 4.0}],
                "synthesizer": {"model": "qwen", "elapsed_s": 5.0},
            }
        }
    }
    timings = extract_timings(payload)
    assert [stage["role"] for stage in timings["stages"]] == ["reviewer", "synthesizer"]
    assert timings["stages"][0]["wall_s"] == 4.0
    assert timings["stages"][1]["model"] == "qwen"


def test_extract_timings_absent() -> None:
    assert extract_timings({}) == {"source": "", "stages": [], "total_wall_s": None}
    assert extract_timings({"portal_council": {"timings": {"total_s": 9.5}}}) == {
        "source": "portal_council.timings",
        "stages": [],
        "total_wall_s": 9.5,
    }


def test_override_echo_is_explicit_about_what_it_saw() -> None:
    override = {"mode": "early_quorum"}
    assert override_echo({"portal_council": {"mode": "early_quorum"}}, override) == "applied"
    assert override_echo({"portal_council": {"mode": "default"}}, override) == "not_applied"
    assert override_echo({"portal_council": {}}, override) == "unverified"
    assert override_echo({}, override) == "unverified"


def test_echo_status_folds_honestly() -> None:
    assert _merge_echo("unverified", "applied") == "applied"
    assert _merge_echo("applied", "unverified") == "partially_applied"
    assert _merge_echo("applied", "not_applied") == "not_applied"
    assert _merge_echo("unverified", "unverified") == "unverified"
