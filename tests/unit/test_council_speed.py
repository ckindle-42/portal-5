"""Council speed modes: timings, early quorum, one resident model, progress, decompose."""

from __future__ import annotations

import pytest

from portal.platform.inference.router.council import (
    CouncilConfigError,
    CouncilOpinion,
    claim_disposition,
    decision_from_settled,
    prepare_council_request,
    votes_decide_outcome,
)
from portal.platform.inference.router.workspaces import WORKSPACES


def _opinion(member_id: str, recommendation: str, *, valid: bool = True) -> CouncilOpinion:
    return CouncilOpinion(
        member_id=member_id,
        label=member_id,
        model=f"model-{member_id}",
        recommendation=recommendation if valid else "ABSTAIN",
        confidence=0.8,
        valid=valid,
    )


def test_two_agreeing_votes_lock_the_coded_decision() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66)
        == "SUPPORT"
    )


def test_a_split_does_not_lock_before_the_last_seat() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "REVISE")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66) is None
    )


def test_one_vote_does_not_lock_when_the_tail_can_outvote_it() -> None:
    opinions = [_opinion("evidence", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=2, minimum_participation=0.3, quorum=0.3) is None
    )


def test_participation_floor_keeps_the_last_seat() -> None:
    opinions = [_opinion("evidence", "SUPPORT"), _opinion("challenger", "SUPPORT")]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=1.0, quorum=0.66) is None
    )


def test_two_non_votes_lock_escalate() -> None:
    opinions = [
        _opinion("evidence", "SUPPORT", valid=False),
        _opinion("challenger", "SUPPORT", valid=False),
    ]
    assert (
        votes_decide_outcome(opinions, remaining=1, minimum_participation=0.66, quorum=0.66)
        == "ESCALATE"
    )


def test_claim_rules_settle_or_escalate() -> None:
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "no", "stale": "no"})
        == "supported"
    )
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "no", "stale": "yes"})
        == "stale"
    )
    assert (
        claim_disposition({"evidence_present": "no", "contradicted": "no", "stale": "no"})
        == "missing"
    )
    assert (
        claim_disposition({"evidence_present": "unsure", "contradicted": "no", "stale": "no"})
        == "escalate"
    )
    assert (
        claim_disposition({"evidence_present": "yes", "contradicted": "yes", "stale": "no"})
        == "escalate"
    )
    assert decision_from_settled(["supported", "supported"]) == "SUPPORT"
    assert decision_from_settled(["supported", "stale"]) == "REVISE"
    assert decision_from_settled(["contradicted"]) == "REJECT"
    assert decision_from_settled(["contradicted", "supported"]) == "REVISE"


def _members() -> list[dict]:
    return [
        {"id": "evidence", "label": "Evidence", "model": "evidence-model", "system": "Audit."},
        {
            "id": "challenger",
            "label": "Challenger",
            "model": "challenger-model",
            "system": "Challenge.",
        },
        {"id": "operator", "label": "Operator", "model": "operator-model", "system": "Operate."},
    ]


def _council(**overrides: object) -> dict:
    council = {
        "members": _members(),
        "synthesizer_model": "synth",
        "minimum_participation": 0.66,
        "quorum": 0.66,
        "reviewer_max_tokens": 8192,
        "synthesizer_max_tokens": 1024,
    }
    council.update(overrides)
    return council


def _body(text: str = "UNIQUE_ORIGINAL_SENTENCE about the proposal.") -> dict:
    return {"messages": [{"role": "user", "content": text}]}


def test_production_speed_defaults_leave_seat_budgets_unset() -> None:
    council = WORKSPACES["auto-council"]["council"]
    speed = council["speed"]
    assert speed["early_quorum"] is False
    assert speed["single_model"] is False
    assert speed["progress"] is False
    assert speed["decompose"] is False
    assert speed["decompose_model"] == "granite4.1:8b-ctx16k"
    assert "resident_model" not in speed
    by_id = {member["id"]: member for member in council["members"]}
    for seat in ("evidence", "challenger", "operator"):
        assert "max_tokens" not in by_id[seat]
        assert "reasoning_max_tokens" not in by_id[seat]
        assert "think" not in by_id[seat]
    assert council["reviewer_max_tokens"] == 8192


def _echo_applied(payload: dict, override: dict) -> bool:
    """Same check the council bench uses for portal_council.applied_config."""
    portal = payload.get("portal_council")
    if not isinstance(portal, dict):
        return False
    bucket = portal.get("applied_config")
    if not isinstance(bucket, dict):
        return False
    return all(bucket.get(key) == value for key, value in override.items())


def test_absent_override_returns_the_workspace_block() -> None:
    council = _council()
    assert prepare_council_request(council, _body()) is council


def test_unknown_override_key_names_itself() -> None:
    with pytest.raises(CouncilConfigError, match="unknown keys: mode"):
        prepare_council_request(_council(), {"portal_council_config": {"mode": "early_quorum"}})


def test_override_type_and_seat_errors_are_specific() -> None:
    council = _council()
    with pytest.raises(CouncilConfigError, match="must be an object"):
        prepare_council_request(council, {"portal_council_config": ["early_quorum"]})
    with pytest.raises(CouncilConfigError, match="early_quorum must be a boolean"):
        prepare_council_request(council, {"portal_council_config": {"early_quorum": "yes"}})
    with pytest.raises(CouncilConfigError, match="unknown seat: outsider"):
        prepare_council_request(
            council,
            {"portal_council_config": {"members": {"outsider": {"model": "other"}}}},
        )
    with pytest.raises(CouncilConfigError, match="unknown keys: temperature"):
        prepare_council_request(
            council,
            {"portal_council_config": {"members": {"evidence": {"temperature": 0.9}}}},
        )
    with pytest.raises(CouncilConfigError, match="max_tokens must be an integer >= 64"):
        prepare_council_request(
            council,
            {"portal_council_config": {"members": {"evidence": {"max_tokens": True}}}},
        )


def test_override_merges_one_request_and_leaves_the_workspace_block() -> None:
    council = _council()
    original_model = council["members"][0]["model"]
    override = {
        "early_quorum": True,
        "single_model": True,
        "single_model_model": "resident-model",
        "progress": False,
        "decompose": False,
        "decompose_model": "decompose-model",
        "synthesizer_model": "other-synth",
        "members": {
            "evidence": {"model": "evidence-override", "max_tokens": 128, "think": False},
            "operator": {"reasoning_max_tokens": 64},
        },
    }
    merged = prepare_council_request(council, {"portal_council_config": override})
    assert merged is not council
    assert council["members"][0]["model"] == original_model
    assert "max_tokens" not in council["members"][0]
    assert merged["synthesizer_model"] == "other-synth"
    assert merged["speed"]["early_quorum"] is True
    assert merged["speed"]["resident_model"] == "resident-model"
    assert merged["speed"]["decompose_model"] == "decompose-model"
    evidence = next(member for member in merged["members"] if member["id"] == "evidence")
    assert evidence["model"] == "evidence-override"
    assert evidence["max_tokens"] == 128
    assert evidence["think"] is False
    operator = next(member for member in merged["members"] if member["id"] == "operator")
    assert operator["model"] == "operator-model"
    assert operator["reasoning_max_tokens"] == 64
    assert _echo_applied(
        {"portal_council": {"applied_config": merged["_applied_config"]}}, override
    )
