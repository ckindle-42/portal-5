"""Tests for investigation agents — Phase 6c-f.

Validates:
- Five agent roles exist and are distinct
- Investigation graph orchestrates A1-A5
- A4 (Challenger) MUST run — no path bypasses it
- Every finding cites an evidence ID (A5 enforcement)
- Budget mechanism works
- Hypothesis/Finding/State data structures
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from bench_security.investigation.agents import (
    AgentResult,
    Finding,
    Hypothesis,
    InvestigationGraph,
    InvestigationState,
)

# ── Data structures ──────────────────────────────────────────────────────────


class TestDataStructures:
    """Hypothesis, Finding, InvestigationState have correct shapes."""

    def test_hypothesis_to_dict(self):
        h = Hypothesis(
            hypothesis_id="hyp-001",
            technique_ids=["T1558.003"],
            description="Kerberoasting",
            confidence=0.8,
            status="supported",
            evidence_refs=["ev-001"],
        )
        d = h.to_dict()
        assert d["hypothesis_id"] == "hyp-001"
        json.dumps(d)

    def test_finding_to_dict(self):
        f = Finding(
            finding_id="find-001",
            hypothesis_id="hyp-001",
            technique_ids=["T1558.003"],
            description="Kerberoasting detected",
            evidence_refs=["ev-001"],
            confidence=0.9,
        )
        d = f.to_dict()
        assert d["finding_id"] == "find-001"
        json.dumps(d)

    def test_investigation_state_to_dict(self):
        state = InvestigationState(case_id="case-001", alert_text="test alert")
        d = state.to_dict()
        assert d["case_id"] == "case-001"
        json.dumps(d)

    def test_agent_result_to_dict(self):
        r = AgentResult(agent_id="A1", action="plan", output={"test": True})
        d = r.to_dict()
        assert d["agent_id"] == "A1"
        json.dumps(d)


# ── Investigation graph ──────────────────────────────────────────────────────


class TestInvestigationGraph:
    """Investigation graph orchestrates A1-A5."""

    def test_graph_creation(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        assert graph.state.case_id == "case-001"
        assert graph.history == []

    def test_planner_runs(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_planner("Suspicious Kerberos activity")
        assert result.agent_id == "A1"
        assert result.action == "plan"
        assert len(graph.history) == 1

    def test_evidence_acquirer_runs(self):
        state = InvestigationState(
            case_id="case-001",
            hypotheses=[Hypothesis(hyp_id, ["T1190"], "test") for hyp_id in ["hyp-001"]],
        )
        graph = InvestigationGraph(state=state)
        result = graph.run_evidence_acquirer(state.hypotheses[0])
        assert result.agent_id == "A2"
        assert state.budget_remaining == 99

    def test_analyst_runs(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_analyst([])
        assert result.agent_id == "A3"

    def test_challenger_runs(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_challenger([])
        assert result.agent_id == "A4"
        assert result.output["verdict"] == "accept"
        assert state.debate_rounds == 1

    def test_reporter_runs(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_reporter([])
        assert result.agent_id == "A5"
        assert result.output["all_citations_valid"] is True

    def test_reporter_flags_unsubstantiated(self):
        f = Finding(
            finding_id="f-001",
            hypothesis_id="h-001",
            technique_ids=["T1190"],
            description="test",
            evidence_refs=[],  # no evidence — unsubstantiated
            confidence=0.5,
        )
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_reporter([f])
        assert result.output["unsubstantiated_count"] == 1
        assert result.output["all_citations_valid"] is False


# ── Full investigation pipeline ──────────────────────────────────────────────


class TestFullPipeline:
    """Full investigation pipeline: A1 → A2 → A3 → A4 → A5."""

    def test_full_pipeline_completes(self):
        state = InvestigationState(
            case_id="case-001",
            hypotheses=[
                Hypothesis("hyp-001", ["T1558.003"], "Kerberoasting"),
            ],
            findings=[
                Finding(
                    "f-001", "hyp-001", ["T1558.003"], "Kerberoasting detected", ["ev-001"], 0.9
                ),
            ],
        )
        graph = InvestigationGraph(state=state)
        result = graph.run_investigation("Suspicious Kerberos activity")
        assert result["status"] == "completed"
        assert len(graph.history) >= 5  # at least A1-A5

    def test_challenger_always_runs(self):
        """No path bypasses A4."""
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        graph.run_investigation("test")
        agent_ids = [h.agent_id for h in graph.history]
        assert "A4" in agent_ids

    def test_budget_decrements(self):
        state = InvestigationState(
            case_id="case-001",
            hypotheses=[Hypothesis(f"hyp-{i}", ["T1190"], f"test {i}") for i in range(5)],
            budget_remaining=3,
        )
        graph = InvestigationGraph(state=state)
        graph.run_investigation("test")
        assert state.budget_remaining == 0
        assert state.status == "budget_exhausted"


# ── A4 Challenger checklist ──────────────────────────────────────────────────


class TestChallengerChecklist:
    """A4 runs an explicit checklist, not free-form disagreement."""

    def test_checklist_has_four_items(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_challenger([])
        checklist = result.output["checklist"]
        assert "reachability" in checklist
        assert "missed_mitigations" in checklist
        assert "evidence_quality" in checklist
        assert "independent_severity" in checklist

    def test_checklist_default_pass(self):
        state = InvestigationState(case_id="case-001")
        graph = InvestigationGraph(state=state)
        result = graph.run_challenger([])
        for v in result.output["checklist"].values():
            assert v is True
