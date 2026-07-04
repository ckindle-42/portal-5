"""Continuous Evaluation + Content Growth.

Phase 8 of BUILD_PROGRAM_SEC_RBP_V1.  The system feeds itself.

Components:
1. Closed investigation cases → bench_investigation corpus (regression grows)
2. Analyst-feedback pipeline (feedback → growth loop input, never inference)
3. Content growth: blue scenarios, oracle coverage, ICS/compliance content
4. Observability: coverage map integration
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .capability_graph import CapabilityGraph, CoverageSummary, generate_coverage_json

# ── Corpus growth ────────────────────────────────────────────────────────────


@dataclass
class CorpusEntry:
    """A regression test case derived from a closed investigation."""

    entry_id: str  # corpus-<case_id>-<seq>
    case_id: str
    scenario_id: str
    alert_text: str
    expected_findings: list[dict]
    evidence_summary: list[dict]
    outcome: str  # "verified" | "rejected" | "indeterminate"
    metrics: dict = field(default_factory=dict)
    added_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "alert_text": self.alert_text,
            "expected_findings_count": len(self.expected_findings),
            "evidence_summary_count": len(self.evidence_summary),
            "outcome": self.outcome,
            "metrics": self.metrics,
            "added_at": self.added_at,
        }


class RegressionCorpus:
    """Growing corpus of regression test cases from closed investigations.

    Cases are added automatically when an investigation closes.  The corpus
    is the basis for bench_investigation — it grows over time, making the
    benchmark harder and more representative.
    """

    def __init__(self, corpus_path: str | Path = ":memory:") -> None:
        self._path = str(corpus_path)
        self._entries: dict[str, CorpusEntry] = {}

    def add(self, entry: CorpusEntry) -> None:
        """Add a corpus entry from a closed investigation."""
        entry.added_at = time.time()
        self._entries[entry.entry_id] = entry

    def get(self, entry_id: str) -> CorpusEntry | None:
        return self._entries.get(entry_id)

    def list_all(self) -> list[CorpusEntry]:
        return list(self._entries.values())

    def count(self) -> int:
        return len(self._entries)

    def to_dict(self) -> dict:
        return {
            "count": self.count(),
            "entries": {k: v.to_dict() for k, v in self._entries.items()},
        }


def close_case_to_corpus(
    corpus: RegressionCorpus,
    case_id: str,
    scenario_id: str,
    alert_text: str,
    expected_findings: list[dict],
    evidence_summary: list[dict],
    outcome: str,
    metrics: dict | None = None,
) -> CorpusEntry:
    """Convert a closed investigation case into a regression corpus entry.

    This is the automatic path from investigation → benchmark growth.
    """
    entry = CorpusEntry(
        entry_id=f"corpus-{case_id}-{int(time.time())}",
        case_id=case_id,
        scenario_id=scenario_id,
        alert_text=alert_text,
        expected_findings=expected_findings,
        evidence_summary=evidence_summary,
        outcome=outcome,
        metrics=metrics or {},
    )
    corpus.add(entry)
    return entry


# ── Analyst feedback ─────────────────────────────────────────────────────────


@dataclass
class AnalystFeedback:
    """Feedback from an analyst on an investigation result.

    This is the ONLY path from case-derived data to long-term memory.
    Agents NEVER have long-term memory — analyst confirm-only at case close.
    """

    feedback_id: str
    case_id: str
    analyst_id: str
    feedback_type: str  # "correction" | "enhancement" | "confirmation"
    content: dict  # what the analyst changed/confirmed
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "case_id": self.case_id,
            "analyst_id": self.analyst_id,
            "feedback_type": self.feedback_type,
            "content": self.content,
            "created_at": self.created_at,
        }


class AnalystFeedbackStore:
    """Store for analyst feedback.  Feeds growth loop, never inference."""

    def __init__(self) -> None:
        self._feedback: dict[str, AnalystFeedback] = {}

    def add(self, feedback: AnalystFeedback) -> None:
        feedback.created_at = time.time()
        self._feedback[feedback.feedback_id] = feedback

    def for_case(self, case_id: str) -> list[AnalystFeedback]:
        return [f for f in self._feedback.values() if f.case_id == case_id]

    def count(self) -> int:
        return len(self._feedback)


# ── Content growth ───────────────────────────────────────────────────────────


@dataclass
class ContentGap:
    """A content gap that needs to be filled."""

    gap_type: str  # "blue_scenario" | "oracle" | "ics_content" | "compliance"
    description: str
    technique_ids: list[str] = field(default_factory=list)
    priority: str = "medium"  # "low" | "medium" | "high"
    status: str = "identified"  # "identified" | "in_progress" | "filled"

    def to_dict(self) -> dict:
        return {
            "gap_type": self.gap_type,
            "description": self.description,
            "technique_ids": self.technique_ids,
            "priority": self.priority,
            "status": self.status,
        }


def identify_content_gaps(graph: CapabilityGraph) -> list[ContentGap]:
    """Identify content gaps that need to be filled.

    Scans for:
    - Blue-side scenarios (only ~5 blueteam at HEAD)
    - Oracle coverage (10 scenarios have none)
    - ICS/compliance content gaps
    """
    gaps: list[ContentGap] = []

    # Count blue-only scenarios
    blue_gaps = [g for g in graph.gaps.values() if g.summary == CoverageSummary.BLUE_ONLY.value]
    if blue_gaps:
        gaps.append(
            ContentGap(
                gap_type="blue_scenario",
                description=f"{len(blue_gaps)} techniques have detections but no exercise scenarios",
                technique_ids=[g.technique_id for g in blue_gaps[:10]],
                priority="high",
            )
        )

    # Techniques without detections
    no_detection = [
        g for g in graph.gaps.values() if g.axes.get("detection") == "DETECTION_MISSING"
    ]
    if no_detection:
        unique_techniques = list({g.technique_id for g in no_detection})
        gaps.append(
            ContentGap(
                gap_type="oracle",
                description=f"{len(unique_techniques)} techniques have no detection rules",
                technique_ids=unique_techniques[:10],
                priority="medium",
            )
        )

    return gaps


# ── Observability ────────────────────────────────────────────────────────────


def generate_dashboard_data(graph: CapabilityGraph) -> dict:
    """Generate data for an observability dashboard.

    Integrates with Grafana/Prometheus or a dedicated workspace.
    """
    coverage = generate_coverage_json(graph)
    summary = graph.summary_counts()

    return {
        "generated_at": time.time(),
        "coverage": coverage,
        "summary": summary,
        "total_procedures": len(graph.procedures),
        "total_detections": len(graph.detections),
        "total_gaps": len(graph.gaps),
        "health": {
            "coverage_pct": coverage["tiers"].get("exercised_pct", 0),
            "detection_pct": coverage["tiers"].get("detected_pct", 0),
            "blocked_count": summary.get("BLOCKED", 0),
        },
    }


# ── Compliance overlay ───────────────────────────────────────────────────────


@dataclass
class ComplianceMapping:
    """Maps techniques to compliance frameworks."""

    framework: str  # "CIP-007" | "NIST-800-53" | "ISO-27001" | etc.
    control_id: str
    technique_ids: list[str]
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "control_id": self.control_id,
            "technique_ids": self.technique_ids,
            "description": self.description,
        }


# Example compliance mappings (ICS-focused)
COMPLIANCE_MAPPINGS = [
    ComplianceMapping(
        framework="CIP-007",
        control_id="CIP-007-R5",
        technique_ids=["T1190", "T1059", "T1078"],
        description="System Access Controls — electronic access controls for BES Cyber Systems",
    ),
    ComplianceMapping(
        framework="CIP-007",
        control_id="CIP-007-R6",
        technique_ids=["T1110", "T1110.003"],
        description="Security Event Monitoring — malicious communications detection",
    ),
    ComplianceMapping(
        framework="NIST-800-53",
        control_id="AC-2",
        technique_ids=["T1078", "T1078.004"],
        description="Account Management — manage information system accounts",
    ),
    ComplianceMapping(
        framework="NIST-800-53",
        control_id="SI-4",
        technique_ids=["T1190", "T1059", "T1003", "T1558.003"],
        description="System Monitoring — monitor the system to detect attacks",
    ),
]


def compliance_coverage(
    graph: CapabilityGraph,
    framework: str = "CIP-007",
) -> dict:
    """Compute compliance coverage for a specific framework.

    Returns per-control coverage status.
    """
    relevant = [m for m in COMPLIANCE_MAPPINGS if m.framework == framework]
    controls = []

    for mapping in relevant:
        # Check how many techniques are covered
        covered = 0
        total = len(mapping.technique_ids)
        for tid in mapping.technique_ids:
            has_detection = any(d.technique_id == tid for d in graph.detections.values())
            has_exercise = any(tid in p.technique_ids for p in graph.procedures.values())
            if has_detection and has_exercise:
                covered += 1

        controls.append(
            {
                "control_id": mapping.control_id,
                "description": mapping.description,
                "techniques_total": total,
                "techniques_covered": covered,
                "coverage_pct": round(covered / total * 100, 1) if total else 0,
            }
        )

    total_techniques = sum(c["techniques_total"] for c in controls)
    covered_techniques = sum(c["techniques_covered"] for c in controls)

    return {
        "framework": framework,
        "controls": controls,
        "overall_coverage_pct": round(covered_techniques / total_techniques * 100, 1)
        if total_techniques
        else 0,
    }
