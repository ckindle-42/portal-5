"""The R1 experiment changes one declared variable per arm."""

from __future__ import annotations

import json

from tests.benchmarks.compliance_judgment_r1_experiment import (
    _SEAT_SYSTEM,
    messages_for_arm,
    production_packet,
)
from tests.benchmarks.compliance_judgment_r1_experiment_v2 import frozen_manifest


def _case() -> dict:
    return {
        "id": "HOLD-1",
        "governing_ref": "REQ-HOLD-1",
        "governing_text": "Review access no less often than every 90 days.",
        "premises": ["The packet is complete."],
        "candidate_text": "Access is reviewed every 30 days.",
        "packet_complete": True,
        "source_ref_ids": ["REQ-HOLD-1", "EVID-HOLD-1"],
        "gold_label": "SUPPORTED",
        "gold_citation": ["REQ-HOLD-1", "EVID-HOLD-1"],
        "gold_rationale": "A 30-day interval is stricter than 90 days.",
    }


def test_user_role_arm_changes_only_the_first_message_role():
    case = _case()
    baseline = messages_for_arm(case, "production")
    treatment = messages_for_arm(case, "user_role")
    assert baseline[0] == {"role": "system", "content": _SEAT_SYSTEM}
    assert treatment[0] == {"role": "user", "content": _SEAT_SYSTEM}
    assert baseline[1] == treatment[1]


def test_contract_arm_exposes_explicit_completeness_and_exact_ids():
    case = _case()
    packet = production_packet(case)
    assert packet["source_refs"] == ["EVID-HOLD-1", "REQ-HOLD-1"]
    assert packet["acquisition_completeness"] == "COMPLETE"
    prompt, request = messages_for_arm(case, "explicit_contract")
    assert prompt["role"] == "system"
    assert request["role"] == "user"
    assert "acquisition_completeness COMPLETE" in prompt["content"]
    assert "source_refs verbatim" in prompt["content"]
    visible_packet = json.loads(request["content"])
    assert visible_packet["source_refs"] == ["EVID-HOLD-1", "REQ-HOLD-1"]
    assert "gold_label" not in visible_packet
    assert "gold_rationale" not in visible_packet


def test_v2_manifest_matches_live_production_caller_and_workspace_budget():
    policy = frozen_manifest()["applied_policy_expected_from_workspace"]
    assert policy["production_caller_answer_budget"] == 8192
    assert policy["production_caller_think_argument"] is False
    assert policy["production_caller_reasoning_allowance_applied"] == 0
    assert policy["expected_applied_output_limit"] == 8192
    assert policy["workspace_think_policy"] is True
    assert policy["enable_thinking"] is True
    assert policy["workspace_context_limit"] == 65536
