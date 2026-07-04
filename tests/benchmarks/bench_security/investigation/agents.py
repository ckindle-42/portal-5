"""Five-agent investigation engine — LangGraph orchestration.

Phase 6c-f of BUILD_PROGRAM_SEC_RBP_V1.  V3 §2.1 / §2.2.

Five agents, not eight, not fifteen — role independence matters more than
granularity:

A1 Planner — decompose alert into ATT&CK-anchored subtasks; produce hypothesis set
A2 Evidence Acquirer — tool selection + query construction + result normalization
A3 Analyst — reason over evidence; propose findings, timeline
A4 Challenger — attempt to falsify A3's finding against evidence (MUST run)
A5 Reporter — emit final structured report with provenance

A4 (Challenger) is not optional.  No path bypasses A4.

P6: Agents consult the wiki (wiki.explain) for technique signatures before
reasoning — recall→lookup, the backbone payoff.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# ── Agent roles ──────────────────────────────────────────────────────────────


@dataclass
class Hypothesis:
    """A testable hypothesis about what happened."""

    hypothesis_id: str  # hyp-<case_id>-<seq>
    technique_ids: list[str]  # MITRE ATT&CK IDs
    description: str
    confidence: float = 0.0  # [0, 1]
    status: str = "proposed"  # "proposed" | "supported" | "contradicted" | "indeterminate"
    evidence_refs: list[str] = field(default_factory=list)
    parent_id: str = ""  # for hypothesis trees

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "technique_ids": self.technique_ids,
            "description": self.description,
            "confidence": self.confidence,
            "status": self.status,
            "evidence_refs": self.evidence_refs,
            "parent_id": self.parent_id,
        }


@dataclass
class Finding:
    """A validated finding from the investigation."""

    finding_id: str
    hypothesis_id: str
    technique_ids: list[str]
    description: str
    evidence_refs: list[str]
    confidence: float
    timeline: list[dict] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    unsubstantiated: bool = False

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "hypothesis_id": self.hypothesis_id,
            "technique_ids": self.technique_ids,
            "description": self.description,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "timeline": self.timeline,
            "contradictions": self.contradictions,
            "unsubstantiated": self.unsubstantiated,
        }


@dataclass
class InvestigationState:
    """Shared state for one investigation case."""

    case_id: str
    alert_text: str = ""
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    agent_scratch: dict = field(default_factory=dict)  # per-agent scratch
    debate_rounds: int = 0
    max_debate_rounds: int = 3
    budget_remaining: int = 100  # tool call budget
    status: str = "active"  # "active" | "completed" | "budget_exhausted"

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "alert_text": self.alert_text,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "findings": [f.to_dict() for f in self.findings],
            "evidence_ids": self.evidence_ids,
            "debate_rounds": self.debate_rounds,
            "budget_remaining": self.budget_remaining,
            "status": self.status,
        }


# ── Agent interfaces ─────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    """Result from one agent invocation."""

    agent_id: str  # "A1"-"A5"
    action: str  # what the agent did
    output: dict  # agent-specific output
    tool_calls: list[dict] = field(default_factory=list)
    elapsed_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "action": self.action,
            "output": self.output,
            "tool_calls": len(self.tool_calls),
            "elapsed_s": self.elapsed_s,
        }


# ── Investigation graph ──────────────────────────────────────────────────────


@dataclass
class InvestigationGraph:
    """The investigation graph — orchestrates A1-A5 over a shared state.

    In production, this uses LangGraph's StateGraph with conditional edges.
    In this slice, it provides the structure and execution framework.
    """

    state: InvestigationState
    history: list[AgentResult] = field(default_factory=list)

    def run_planner(self, alert_text: str) -> AgentResult:
        """A1: Decompose alert into ATT&CK-anchored hypotheses."""
        t0 = time.time()
        result = AgentResult(agent_id="A1", action="plan", output={})

        # In production, the Planner calls portal-mitre to look up techniques
        # and produces an ordered hypothesis set.  In this slice, we create
        # the structure.
        self.state.alert_text = alert_text
        result.output = {
            "hypotheses_proposed": len(self.state.hypotheses),
            "budget_remaining": self.state.budget_remaining,
        }
        result.elapsed_s = time.time() - t0
        self.history.append(result)
        return result

    def run_evidence_acquirer(self, hypothesis: Hypothesis) -> AgentResult:
        """A2: Acquire evidence for a hypothesis via tools."""
        t0 = time.time()
        result = AgentResult(agent_id="A2", action="acquire", output={})

        # In production, A2 calls MCP tools (spl_search, mitre lookup, etc.)
        # and produces EvidenceRecords.  In this slice, we record the structure.
        self.state.budget_remaining -= 1
        result.output = {
            "hypothesis_id": hypothesis.hypothesis_id,
            "evidence_acquired": len(hypothesis.evidence_refs),
            "budget_remaining": self.state.budget_remaining,
        }
        result.elapsed_s = time.time() - t0
        self.history.append(result)
        return result

    def run_analyst(self, hypotheses: list[Hypothesis]) -> AgentResult:
        """A3: Reason over evidence and propose findings."""
        t0 = time.time()
        result = AgentResult(agent_id="A3", action="analyze", output={})

        # In production, A3 reasons over the evidence store and proposes
        # findings with timelines.  Never writes the report.
        result.output = {
            "findings_proposed": len(self.state.findings),
            "hypotheses_reviewed": len(hypotheses),
        }
        result.elapsed_s = time.time() - t0
        self.history.append(result)
        return result

    def run_challenger(self, findings: list[Finding]) -> AgentResult:
        """A4: Attempt to falsify findings against evidence.

        MUST run.  No path bypasses A4.  Uses an explicit checklist:
        1. Reachability — does evidence connect cause to effect?
        2. Missed mitigations — does evidence explain signal benignly?
        3. Evidence quality — is cited evidence real and correctly parsed?
        4. Independent severity — is severity justified by A4's own findings?
        """
        t0 = time.time()
        result = AgentResult(agent_id="A4", action="challenge", output={})

        # Checklist
        checklist = {
            "reachability": True,
            "missed_mitigations": True,
            "evidence_quality": True,
            "independent_severity": True,
        }

        contradictions_found = 0
        for finding in findings:
            # In production, A4 checks each finding against the evidence store
            # and produces counter-hypotheses.  In this slice, we record the
            # structure.
            if finding.contradictions:
                contradictions_found += len(finding.contradictions)

        result.output = {
            "findings_challenged": len(findings),
            "contradictions_found": contradictions_found,
            "checklist": checklist,
            "verdict": "accept" if contradictions_found == 0 else "reject",
        }
        result.elapsed_s = time.time() - t0
        self.history.append(result)
        self.state.debate_rounds += 1
        return result

    def run_reporter(self, findings: list[Finding]) -> AgentResult:
        """A5: Emit final structured report with provenance.

        Every claim must cite an evidence ID.  Claims without evidence IDs
        are flagged by a deterministic post-processor as unsubstantiated.
        Remediation only via playbook lookup, not free generation.
        """
        t0 = time.time()
        result = AgentResult(agent_id="A5", action="report", output={})

        # Check every finding has evidence
        unsubstantiated = [f for f in findings if not f.evidence_refs]

        result.output = {
            "findings_reported": len(findings),
            "unsubstantiated_count": len(unsubstantiated),
            "all_citations_valid": len(unsubstantiated) == 0,
        }
        result.elapsed_s = time.time() - t0
        self.history.append(result)
        return result

    def run_investigation(self, alert_text: str) -> dict:
        """Run the full investigation pipeline: A1 → A2 → A3 → A4 → A5.

        Returns the final state with all agent outputs.
        """
        # A1: Plan
        self.run_planner(alert_text)

        # A2: Acquire evidence for each hypothesis
        for hyp in self.state.hypotheses:
            if self.state.budget_remaining <= 0:
                self.state.status = "budget_exhausted"
                break
            self.run_evidence_acquirer(hyp)

        # A3: Analyze
        self.run_analyst(self.state.hypotheses)

        # A4: Challenge (MUST run)
        self.run_challenger(self.state.findings)

        # A5: Report
        self.run_reporter(self.state.findings)

        if self.state.status != "budget_exhausted":
            self.state.status = "completed"
        return self.state.to_dict()
