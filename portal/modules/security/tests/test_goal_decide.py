"""Tests for goal-driven decide (TASK_SEC_GOAL_DECIDE_V1, Stage 2).

Hermetic — no model/lab. All decide/loop calls use the deterministic
fallback (workspace=None), so results are reproducible.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.goal import EngagementGoal, validate_goal
from portal.modules.security.core.goal_decide import decide_next_action
from portal.modules.security.core.goal_eval import eval_proposals
from portal.modules.security.core.loop import run_goal_engagement
from portal.modules.security.core.oracles import ORACLES

_BOUNDED_KWARGS = {
    "scope": {"targets": ["10.10.11.50"]},
    "budget": {"max_iterations": 5, "max_wall_clock_sec": 300, "max_lab_actions": 10},
}


class TestValidateGoal:
    def test_no_scope_rejected(self):
        g = EngagementGoal(intent="poke it", role="red", budget={"max_iterations": 1})
        problems = validate_goal(g)
        assert any("scope" in p for p in problems)

    def test_no_budget_rejected(self):
        g = EngagementGoal(intent="poke it", role="red", scope={"targets": ["x"]})
        problems = validate_goal(g)
        assert any("budget" in p for p in problems)

    def test_incomplete_budget_rejected(self):
        g = EngagementGoal(
            intent="poke it", role="red", scope={"targets": ["x"]}, budget={"max_iterations": 5}
        )
        problems = validate_goal(g)
        assert any("max_wall_clock_sec" in p for p in problems)

    def test_bounded_goal_accepted(self):
        g = EngagementGoal(intent="poke it", role="red", targets=["x"], **_BOUNDED_KWARGS)
        assert validate_goal(g) == []

    def test_invalid_role_rejected(self):
        g = EngagementGoal(intent="poke it", role="purple-ish", targets=["x"], **_BOUNDED_KWARGS)
        problems = validate_goal(g)
        assert any("role" in p for p in problems)


class TestDecideNextAction:
    def test_smb_observations_propose_in_domain_capability(self):
        g = EngagementGoal(intent="poke this machine", role="red", targets=["x"], **_BOUNDED_KWARGS)
        decision = decide_next_action(g, {"open_ports": [445]}, [])
        assert decision["outcome"] == "proposed"
        assert "smb" in decision["action"] or "meta3_smb" in decision["action"]

    def test_decision_has_reason_confidence_oracle(self):
        g = EngagementGoal(intent="poke this machine", role="red", targets=["x"], **_BOUNDED_KWARGS)
        decision = decide_next_action(g, {"open_ports": [445]}, [])
        assert decision["reason"]
        assert 0.0 <= decision["confidence"] <= 1.0
        if decision["expected_oracle"] is not None:
            assert decision["expected_oracle"] in ORACLES

    def test_no_matching_observations_declines(self):
        g = EngagementGoal(
            intent="poke this machine",
            role="red",
            targets=["x"],
            domain_hint="mainframe",  # no capability is tagged with this domain — zero candidates
            scope={"targets": ["x"]},
            budget={"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
        )
        decision = decide_next_action(g, {"open_ports": [999999]}, [])
        assert decision["outcome"] == "no_applicable_capability"
        assert decision["action"] is None

    def test_never_proposes_out_of_domain(self):
        g = EngagementGoal(
            intent="poke this machine",
            role="red",
            targets=["x"],
            domain_hint="ad",
            **_BOUNDED_KWARGS,
        )
        decision = decide_next_action(g, {"open_ports": [445]}, [])
        assert decision["outcome"] == "proposed"


class TestRunGoalEngagement:
    def test_produces_ordered_plan_under_budget(self):
        g = EngagementGoal(
            intent="poke this machine", role="red", targets=["10.10.11.50"], **_BOUNDED_KWARGS
        )
        report = run_goal_engagement(g, dry_run=True)
        assert report["status"] == "completed"
        assert report["iterations"] <= g.budget["max_iterations"]
        assert len(report["plan"]) == report["iterations"]

    def test_stops_with_no_applicable_capability(self):
        g = EngagementGoal(
            intent="poke this machine",
            role="red",
            targets=["10.10.11.50"],
            domain_hint="mainframe",  # no capability tagged with this domain
            scope={"targets": ["10.10.11.50"]},
            budget={"max_iterations": 5, "max_wall_clock_sec": 300, "max_lab_actions": 10},
        )
        report = run_goal_engagement(g, dry_run=True)
        assert report["stop_reason"] == "no_applicable_capability"
        assert report["plan"] == []

    def test_out_of_scope_target_refused_and_escalated(self):
        g = EngagementGoal(
            intent="poke this machine",
            role="red",
            targets=["10.10.99.99"],
            scope={"targets": ["10.10.11.50"]},
            budget={"max_iterations": 5, "max_wall_clock_sec": 300, "max_lab_actions": 10},
        )
        report = run_goal_engagement(g, dry_run=True)
        assert report["stop_reason"] == "escalated:out_of_scope_action"
        assert any("out_of_scope_action" in e for e in report["escalations"])

    def test_goal_without_bounds_rejected(self):
        g = EngagementGoal(intent="poke this machine", role="red")
        report = run_goal_engagement(g, dry_run=True)
        assert report["status"] == "rejected"
        assert report["stop_reason"] == "invalid_goal"

    def test_live_actuation_raises_not_implemented(self):
        g = EngagementGoal(
            intent="poke this machine", role="red", targets=["10.10.11.50"], **_BOUNDED_KWARGS
        )
        with pytest.raises(NotImplementedError):
            run_goal_engagement(g, dry_run=False)

    def test_respects_max_steps_override(self):
        g = EngagementGoal(
            intent="poke this machine", role="red", targets=["10.10.11.50"], **_BOUNDED_KWARGS
        )
        report = run_goal_engagement(g, dry_run=True, max_steps=2)
        assert report["iterations"] <= 2


class TestEvalProposals:
    def test_returns_per_target_and_aggregate(self):
        result = eval_proposals(role="red")
        assert "per_target" in result
        assert "aggregate" in result
        assert result["aggregate"]["targets_evaluated"] == len(result["per_target"])

    def test_aggregate_rates_in_range(self):
        result = eval_proposals(role="red")
        agg = result["aggregate"]
        for key in ("relevance_rate", "grounding_rate", "non_flailing_rate", "coverage_rate"):
            assert 0.0 <= agg[key] <= 1.0

    def test_custom_targets(self):
        targets = [
            {
                "name": "custom-smb",
                "observations": {"open_ports": [445]},
                "domain_hint": "ad",
                "expected_technique": "smb_probe",
            }
        ]
        result = eval_proposals(targets, role="red")
        assert len(result["per_target"]) == 1
        assert result["per_target"][0]["target"] == "custom-smb"
