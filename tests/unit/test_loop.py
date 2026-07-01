"""Unit tests for autonomous engagement loop (synthetic/dry-run)."""

from __future__ import annotations

import pytest

from tests.benchmarks.bench_security.loop import (
    EngagementState,
    _check_budget,
    _check_escalate,
    _check_stop,
    enforce_scope,
    run_engagement,
)
from tests.benchmarks.bench_security.playbooks import validate_playbook


class TestScopeGuard:
    def test_in_scope_allowed(self):
        assert enforce_scope("10.10.11.21", {"targets": ["10.10.11.21"]}) is True

    def test_out_of_scope_refused(self):
        assert enforce_scope("10.10.11.99", {"targets": ["10.10.11.21"]}) is False

    def test_empty_scope_allows(self):
        assert enforce_scope("any", {}) is True


class TestBudgetCheck:
    def test_iterations_exceeded(self):
        pb = {"budget": {"max_iterations": 5, "max_wall_clock_sec": 99999, "max_lab_actions": 999}}
        state = EngagementState("test", "pb", started_at=0)
        state.iterations = 6
        assert _check_budget(state, pb) is not None

    def test_hard_cap_enforced(self):
        pb = {"budget": {"max_iterations": 100, "max_wall_clock_sec": 99999, "max_lab_actions": 999}}
        state = EngagementState("test", "pb", started_at=0)
        state.iterations = 51  # exceeds HARD_MAX_ITERATIONS=50
        assert _check_budget(state, pb) is not None


class TestStopCheck:
    def test_stop_condition_met(self):
        pb = {"stop_conditions": [{"field": "compromise_confirmed", "equals": True}]}
        assert _check_stop(pb, {"compromise_confirmed": True}) is True

    def test_stop_condition_not_met(self):
        pb = {"stop_conditions": [{"field": "compromise_confirmed", "equals": True}]}
        assert _check_stop(pb, {"other": True}) is False


class TestEscalateCheck:
    def test_out_of_scope_escalation(self):
        pb = {"escalate_when": ["out_of_scope_action"]}
        state = EngagementState("test", "pb")
        state.escalations.append("out_of_scope_action")
        assert _check_escalate(state, pb) == "out_of_scope_action"


class TestRunEngagement:
    def test_invalid_playbook_rejected(self):
        with pytest.raises(FileNotFoundError):
            run_engagement("nonexistent.yaml", dry_run=True)

    def test_valid_playbook_dry_runs(self):
        result = run_engagement(
            "playbooks/security/internal-ad-pentest.yaml", dry_run=True
        )
        assert result["status"] == "dry_run"
        assert result["playbook"] == "internal-ad-pentest"
        assert "phases_plan" in result
