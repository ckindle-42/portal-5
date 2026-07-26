"""Deterministic scoring tests for the platform Council Review bench."""

from __future__ import annotations

from portal.modules.security.core.council_review_bench import (
    ReviewTask,
    catches_known_flaw,
    score_case,
    summarize,
)
from portal.platform.inference.router.council import CouncilOpinion


def _opinion(member: str, recommendation: str, *, evidence: bool = True) -> dict:
    return {
        "member_id": member,
        "recommendation": recommendation,
        "valid": True,
        "participated": recommendation != "ABSTAIN",
        "findings": [
            {
                "claim": "The plan omits a dry-run gate",
                "evidence": ["No dry-run is planned"] if evidence else [],
                "action": "Add dry-run review",
            }
        ],
    }


def _payload(decision: str, reviewers: list[dict], *, dissent: list[str] | None = None) -> dict:
    return {
        "portal_council": {
            "aggregate": {"decision": decision, "dissent": dissent or []},
            "reviewers": reviewers,
        },
        "choices": [
            {
                "message": {
                    "content": (
                        f"**Code-determined decision: {decision}**\n" + " ".join(dissent or [])
                    )
                }
            }
        ],
    }


def test_flaw_catch_requires_evidence() -> None:
    task = ReviewTask("flaw", "Flaw", "source", "material", ("dry-run",))
    assert catches_known_flaw(task, [_opinion("a", "REVISE")])
    assert not catches_known_flaw(task, [_opinion("a", "REVISE", evidence=False)])


def test_thin_material_abstention_and_synthesizer_fidelity() -> None:
    task = ReviewTask("thin", "Thin", "source", "material", thin_material=True)
    solo = CouncilOpinion("solo", "Solo", "m", "ABSTAIN", valid=True)
    case = score_case(
        task,
        council_payload=_payload(
            "ESCALATE",
            [_opinion("a", "ABSTAIN"), _opinion("b", "ABSTAIN")],
        ),
        solo_opinion=solo,
        council_latency_s=2.0,
        solo_latency_s=1.0,
    )
    assert case["council"]["honest_abstention"] is True
    assert case["solo"]["honest_abstention"] is True
    assert case["council"]["machine_decision_preserved"] is True


def test_solo_baseline_delta_and_dead_seat_detection() -> None:
    cases = [
        {
            "known_flaw": True,
            "thin_material": False,
            "council": {
                "flaw_caught_with_evidence": True,
                "honest_abstention": False,
                "machine_decision_preserved": True,
                "dissent_preserved_in_synthesis": True,
                "latency_s": 2.0,
                "estimated_output_tokens": 20,
            },
            "solo": {
                "flaw_caught_with_evidence": False,
                "honest_abstention": False,
                "latency_s": 1.0,
                "estimated_output_tokens": 10,
            },
            "_reviewers": [
                {"member_id": "live", "participated": True},
                {"member_id": "dead", "participated": False},
            ],
        }
    ]
    result = summarize(cases)
    assert result["flaw_catch_delta"] == 1
    assert result["dead_seats"] == ["dead"]
    assert result["earns_place_for_blue_borderline"] is False


def test_summarize_refuses_missing_solo_baseline() -> None:
    try:
        summarize([])
    except ValueError as exc:
        assert "solo baseline" in str(exc)
    else:
        raise AssertionError("missing baseline should fail")
