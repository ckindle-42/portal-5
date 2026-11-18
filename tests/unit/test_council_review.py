"""Council Review: isolated seats, full-roster quorum, and bounded synthesis."""

from __future__ import annotations

import pytest

from portal.platform.inference.config import CouncilSpec
from portal.platform.inference.router.council import (
    CouncilOpinion,
    _message_text,
    aggregate_opinions,
    parse_opinion,
)
from portal.platform.inference.router.workspaces import WORKSPACES


def _opinion(member_id: str, recommendation: str, *, valid: bool = True) -> CouncilOpinion:
    return CouncilOpinion(
        member_id=member_id,
        label=member_id,
        model=f"model-{member_id}",
        recommendation=recommendation,
        confidence=0.8,
        valid=valid,
    )


def test_parse_opinion_accepts_fenced_json() -> None:
    member = {"id": "evidence", "label": "Evidence", "model": "m1"}
    text = """```json
{"recommendation":"REVISE","confidence":0.9,"findings":[{"claim":"Missing test",
"evidence":["proposal says tests are TBD"],"action":"Add the test"}]}
```"""
    result = parse_opinion(member, text)
    assert result.valid is True
    assert result.recommendation == "REVISE"
    assert result.confidence == 0.9
    assert result.findings[0]["claim"] == "Missing test"


def test_invalid_output_abstains_without_becoming_a_vote() -> None:
    member = {"id": "challenger", "label": "Challenger", "model": "m2"}
    result = parse_opinion(member, "I think this looks good.")
    assert result.valid is False
    assert result.participated is False
    assert result.recommendation == "ABSTAIN"
    assert result.error


def test_council_response_never_promotes_reasoning_to_the_answer() -> None:
    embedded_vote = '{"recommendation":"SUPPORT","confidence":1.0}'
    assert (
        _message_text(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": embedded_vote,
                            "reasoning": embedded_vote,
                        }
                    }
                ]
            }
        )
        == ""
    )
    assert (
        _message_text(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"recommendation":"REVISE"}',
                            "reasoning_content": embedded_vote,
                        }
                    }
                ]
            }
        )
        == '{"recommendation":"REVISE"}'
    )


def test_quorum_uses_full_roster_not_only_participants() -> None:
    opinions = [
        _opinion("one", "SUPPORT"),
        _opinion("two", "ABSTAIN"),
        _opinion("three", "ABSTAIN", valid=False),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.33, quorum=0.66)
    assert result.decision == "ESCALATE"
    assert result.required_votes == 2
    assert result.votes["SUPPORT"] == 1


def test_two_of_three_reaches_configured_quorum_and_preserves_dissent() -> None:
    opinions = [
        _opinion("evidence", "REVISE"),
        _opinion("challenger", "REVISE"),
        _opinion("operator", "SUPPORT"),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.66, quorum=0.66)
    assert result.decision == "REVISE"
    assert result.participating == 3
    assert result.required_votes == 2
    assert result.dissent == ["operator"]


def test_low_participation_escalates_even_when_remaining_reviewers_agree() -> None:
    opinions = [
        _opinion("evidence", "SUPPORT"),
        _opinion("challenger", "SUPPORT"),
        _opinion("operator", "ABSTAIN", valid=False),
    ]
    result = aggregate_opinions(opinions, minimum_participation=0.67, quorum=0.66)
    assert result.decision == "ESCALATE"
    assert "participation" in result.rationale


def test_council_schema_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        CouncilSpec.model_validate(
            {
                "members": [
                    {"id": "same", "label": "A", "model": "m1", "system": "a"},
                    {"id": "same", "label": "B", "model": "m2", "system": "b"},
                ],
                "synthesizer_model": "m3",
            }
        )


def test_council_member_sampling_overrides_are_typed() -> None:
    spec = CouncilSpec.model_validate(
        {
            "members": [
                {
                    "id": "one",
                    "label": "One",
                    "model": "m1",
                    "system": "Review.",
                    "temperature": 0.4,
                    "top_p": 0.9,
                    "top_k": 20,
                    "min_p": 0.05,
                    "presence_penalty": 0.3,
                    "repeat_penalty": 1.1,
                },
                {"id": "two", "label": "Two", "model": "m2", "system": "Review."},
            ],
            "synthesizer_model": "m3",
        }
    )
    assert spec.members[0].temperature == 0.4
    assert spec.members[0].top_k == 20
    assert spec.members[0].repeat_penalty == 1.1


def test_production_workspace_is_explicit_and_tool_free() -> None:
    workspace = WORKSPACES["auto-council"]
    assert workspace["tools"] == []
    assert len(workspace["council"]["members"]) == 3
    assert workspace["council"]["synthesizer_model"] == workspace["model_hint"]


def test_every_configured_council_model_is_reachable() -> None:
    import yaml

    raw = yaml.safe_load(open("config/backends.yaml"))
    catalog = {
        entry["id"] if isinstance(entry, dict) else entry
        for backend in raw["backends"]
        for entry in backend.get("models", [])
    }
    council = WORKSPACES["auto-council"]["council"]
    configured = {member["model"] for member in council["members"]}
    configured.add(council["synthesizer_model"])
    decompose_model = (council.get("speed") or {}).get("decompose_model")
    if decompose_model:
        configured.add(decompose_model)
    assert configured <= catalog
