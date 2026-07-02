"""Unit tests for security playbooks (Gap 6)."""

from __future__ import annotations

from tests.benchmarks.bench_security.playbooks import (
    list_playbooks,
    load_playbook,
    resolve_phases,
    validate_playbook,
)


class TestValidatePlaybook:
    def test_valid_playbook_passes(self):
        pb = {
            "name": "test",
            "version": 1,
            "scope": {"targets": ["10.0.0.1"]},
            "budget": {"max_iterations": 10, "max_wall_clock_sec": 600, "max_lab_actions": 20},
            "stop_conditions": [{"field": "compromise_confirmed", "equals": True}],
            "phases": [
                {"id": "recon", "steps": [{"step": "portscan", "tool": "nmap"}]},
                {
                    "id": "exploit",
                    "depends_on": ["recon"],
                    "steps": [{"step": "sqli", "tool": "sqlmap"}],
                },
            ],
        }
        problems = validate_playbook(pb)
        assert problems == []

    def test_missing_scope_rejected(self):
        pb = {
            "budget": {"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
            "stop_conditions": [{"field": "x", "equals": True}],
            "phases": [{"id": "p1", "steps": []}],
        }
        problems = validate_playbook(pb)
        assert "missing required top-level key: scope" in problems

    def test_missing_budget_rejected(self):
        pb = {
            "scope": {"targets": ["10.0.0.1"]},
            "stop_conditions": [{"field": "x", "equals": True}],
            "phases": [{"id": "p1", "steps": []}],
        }
        problems = validate_playbook(pb)
        assert "missing required top-level key: budget" in problems

    def test_missing_stop_conditions_rejected(self):
        pb = {
            "scope": {"targets": ["10.0.0.1"]},
            "budget": {"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
            "phases": [{"id": "p1", "manual": True}],
        }
        problems = validate_playbook(pb)
        assert any("stop_conditions" in p for p in problems)

    def test_empty_scopes_targets_rejected(self):
        pb = {
            "scope": {"targets": []},
            "budget": {"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
            "stop_conditions": [{"field": "x"}],
            "phases": [{"id": "p1", "manual": True}],
        }
        problems = validate_playbook(pb)
        assert any("targets" in p for p in problems)

    def test_starter_playbooks_validate(self):
        for info in list_playbooks():
            pb = load_playbook(info["file"])
            problems = validate_playbook(pb)
            assert problems == [], f"{info['file']}: {problems}"


class TestResolvePhases:
    def test_dependency_gating(self):
        pb = {
            "name": "test",
            "version": 1,
            "scope": {"targets": ["x"]},
            "budget": {"max_iterations": 1, "max_wall_clock_sec": 1, "max_lab_actions": 1},
            "stop_conditions": [{"field": "x"}],
            "phases": [
                {"id": "recon", "steps": [{"step": "s1", "tool": "t1"}]},
                {"id": "exploit", "depends_on": ["recon"], "steps": [{"step": "s2"}]},
            ],
        }
        ready = resolve_phases(pb, {})
        assert len(ready) == 1  # only recon is ready
        assert ready[0]["id"] == "recon"
