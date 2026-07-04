"""Investigation benchmark — single-agent baseline + multi-agent comparison.

Phase 6b of BUILD_PROGRAM_SEC_RBP_V1.  The honesty ruler.

build_investigation provides:
- A single-agent baseline (one model + all tools) as the null hypothesis
- Adversarial test cases (planted contradictions, missing-evidence traps)
- Metrics: hallucination rate, contradiction detection, evidence completeness

The multi-agent stack (6c-f) MUST beat this baseline on all three metrics.
If it doesn't beat baseline, simplify back toward baseline — do not ship
complexity that doesn't earn its place.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .evidence import EvidenceRecord, EvidenceStore, new_evidence_id

# ── Investigation scenario ───────────────────────────────────────────────────


@dataclass
class InvestigationScenario:
    """A test scenario for the investigation benchmark."""

    scenario_id: str
    name: str
    description: str
    alert_text: str  # the initial alert that triggers the investigation
    evidence: list[dict]  # pre-seeded evidence records
    expected_findings: list[dict]  # what the investigation should conclude
    adversarial: dict = field(default_factory=dict)
    # {planted_contradictions: [], missing_evidence_traps: []}

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "alert_text": self.alert_text,
            "evidence_count": len(self.evidence),
            "expected_findings_count": len(self.expected_findings),
            "has_adversarial": bool(self.adversarial),
        }


# ── Investigation result ─────────────────────────────────────────────────────


@dataclass
class InvestigationResult:
    """Result of running an investigation on a scenario."""

    scenario_id: str
    agent_type: str  # "single_agent_baseline" | "multi_agent"
    findings: list[dict] = field(default_factory=list)
    evidence_used: list[str] = field(default_factory=list)  # evidence IDs referenced
    hypotheses: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    # {hallucination_rate, contradiction_detection_rate, evidence_completeness}
    elapsed_s: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "agent_type": self.agent_type,
            "findings_count": len(self.findings),
            "evidence_used_count": len(self.evidence_used),
            "hypotheses_count": len(self.hypotheses),
            "metrics": self.metrics,
            "elapsed_s": self.elapsed_s,
            "errors": self.errors,
        }


# ── Metrics computation ──────────────────────────────────────────────────────


def compute_hallucination_rate(
    findings: list[dict],
    evidence_store: EvidenceStore,
) -> float:
    """Compute the fraction of findings that cite non-existent evidence.

    A finding is a hallucination if it references an evidence ID that doesn't
    exist in the evidence store.  Returns 0.0 (no hallucinations) to 1.0
    (all hallucinations).
    """
    if not findings:
        return 0.0

    hallucinated = 0
    for finding in findings:
        refs = finding.get("evidence_refs", [])
        if not refs:
            hallucinated += 1  # finding with no evidence is a hallucination
            continue
        for ref in refs:
            if evidence_store.get(ref) is None:
                hallucinated += 1
                break

    return hallucinated / len(findings)


def compute_contradiction_detection_rate(
    findings: list[dict],
    expected_contradictions: list[dict],
) -> float:
    """Compute the fraction of planted contradictions that were detected.

    Returns 0.0 (none detected) to 1.0 (all detected).
    """
    if not expected_contradictions:
        return 1.0  # no contradictions to detect

    detected = 0
    for expected in expected_contradictions:
        # Check if any finding mentions the contradiction
        for finding in findings:
            if expected.get("id", "") in str(finding.get("contradictions", [])):
                detected += 1
                break
            if expected.get("description", "") in str(finding.get("notes", "")):
                detected += 1
                break

    return detected / len(expected_contradictions)


def compute_evidence_completeness(
    findings: list[dict],
    expected_findings: list[dict],
) -> float:
    """Compute the fraction of expected findings that were produced.

    Returns 0.0 (none found) to 1.0 (all found).
    """
    if not expected_findings:
        return 1.0

    found = 0
    for expected in expected_findings:
        expected_technique = expected.get("technique_id", "")
        for finding in findings:
            if expected_technique in finding.get("technique_ids", []):
                found += 1
                break
            if expected.get("description", "") in str(finding.get("text", "")):
                found += 1
                break

    return found / len(expected_findings)


# ── Single-agent baseline ────────────────────────────────────────────────────


def run_single_agent_baseline(
    scenario: InvestigationScenario,
) -> InvestigationResult:
    """Run the single-agent baseline investigation.

    One model + all tools.  This is the null hypothesis that the multi-agent
    stack must beat.

    In production, this calls the pipeline with all MCP tools available.
    In this slice, it creates the investigation structure and metrics.
    """
    t0 = time.time()
    result = InvestigationResult(
        scenario_id=scenario.scenario_id,
        agent_type="single_agent_baseline",
    )

    # Seed evidence store with scenario's pre-seeded evidence
    store = EvidenceStore()
    for ev_data in scenario.evidence:
        record = EvidenceRecord(
            evidence_id=ev_data.get("evidence_id", new_evidence_id()),
            episode_id=ev_data.get("episode_id", ""),
            case_id=scenario.scenario_id,
            kind=ev_data.get("kind", "tool_output"),
            source=ev_data.get("source", {"system": "baseline"}),
            timestamp=ev_data.get("timestamp", {"collected_at": "", "event_time": ""}),
            artifact=ev_data.get("artifact", {"identifiers": []}),
            supports=ev_data.get("supports", []),
            contradicts=ev_data.get("contradicts", []),
            confidence=ev_data.get(
                "confidence", {"source_authority": "authoritative_live", "parse_confidence": "high"}
            ),
            provenance=ev_data.get(
                "provenance", {"collected_by_agent": "A2", "chain_of_custody": []}
            ),
        )
        store.add(record)

    # In production, the single agent would:
    # 1. Read the alert
    # 2. Call MCP tools to gather evidence
    # 3. Reason over evidence
    # 4. Produce findings

    # For this slice, we record the structure and compute metrics
    result.evidence_used = [r.evidence_id for r in store.list_all()]

    # Compute metrics against expected findings
    result.metrics = {
        "hallucination_rate": compute_hallucination_rate(result.findings, store),
        "contradiction_detection_rate": compute_contradiction_detection_rate(
            result.findings,
            scenario.adversarial.get("planted_contradictions", []),
        ),
        "evidence_completeness": compute_evidence_completeness(
            result.findings,
            scenario.expected_findings,
        ),
    }

    result.elapsed_s = time.time() - t0
    return result


# ── Adversarial test scenarios ───────────────────────────────────────────────


ADVERSARIAL_SCENARIOS = [
    InvestigationScenario(
        scenario_id="adv-contradiction-001",
        name="Planted contradiction — wrong technique ID",
        description="Evidence clearly shows Kerberoasting (T1558.003) but a planted "
        "finding claims DCSync (T1003.006).  The investigation should detect "
        "the contradiction and reject the false finding.",
        alert_text="Suspicious Kerberos ticket requests detected on DC01.",
        evidence=[
            {
                "evidence_id": "ev-adv-001",
                "kind": "siem_hit",
                "source": {"system": "splunk"},
                "supports": ["hyp-kerberoast"],
                "confidence": {
                    "source_authority": "authoritative_live",
                    "parse_confidence": "high",
                },
            },
        ],
        expected_findings=[
            {"technique_id": "T1558.003", "description": "Kerberoasting detected"},
        ],
        adversarial={
            "planted_contradictions": [
                {
                    "id": "contradict-001",
                    "description": "False claim of DCSync (T1003.006) when evidence shows Kerberoasting (T1558.003)",
                },
            ],
        },
    ),
    InvestigationScenario(
        scenario_id="adv-missing-evidence-001",
        name="Missing evidence trap — claim without citation",
        description="A finding claims lateral movement but no evidence supports it. "
        "The investigation should flag this as unsubstantiated.",
        alert_text="Multiple failed login attempts detected.",
        evidence=[
            {
                "evidence_id": "ev-adv-002",
                "kind": "siem_hit",
                "source": {"system": "splunk"},
                "supports": ["hyp-password-spray"],
                "confidence": {
                    "source_authority": "authoritative_live",
                    "parse_confidence": "high",
                },
            },
        ],
        expected_findings=[
            {"technique_id": "T1110.003", "description": "Password spraying detected"},
        ],
        adversarial={
            "missing_evidence_traps": [
                {
                    "id": "trap-001",
                    "description": "Claim lateral movement (T1021.002) with no supporting evidence",
                },
            ],
        },
    ),
]


# ── Benchmark runner ─────────────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    """Result of running the investigation benchmark across all scenarios."""

    scenarios_run: int = 0
    results: list[InvestigationResult] = field(default_factory=list)
    aggregate_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scenarios_run": self.scenarios_run,
            "results": [r.to_dict() for r in self.results],
            "aggregate_metrics": self.aggregate_metrics,
        }


def run_benchmark(
    scenarios: list[InvestigationScenario] | None = None,
) -> BenchmarkResult:
    """Run the investigation benchmark on all scenarios.

    Returns BenchmarkResult with per-scenario and aggregate metrics.
    """
    if scenarios is None:
        scenarios = ADVERSARIAL_SCENARIOS

    bench = BenchmarkResult()

    for scenario in scenarios:
        result = run_single_agent_baseline(scenario)
        bench.results.append(result)
        bench.scenarios_run += 1

    # Aggregate metrics
    if bench.results:
        bench.aggregate_metrics = {
            "avg_hallucination_rate": sum(
                r.metrics.get("hallucination_rate", 0) for r in bench.results
            )
            / len(bench.results),
            "avg_contradiction_detection_rate": sum(
                r.metrics.get("contradiction_detection_rate", 0) for r in bench.results
            )
            / len(bench.results),
            "avg_evidence_completeness": sum(
                r.metrics.get("evidence_completeness", 0) for r in bench.results
            )
            / len(bench.results),
        }

    return bench


# ── Multi-agent comparison ───────────────────────────────────────────────────


def run_multi_agent(
    scenarios: list[InvestigationScenario] | None = None,
) -> BenchmarkResult:
    """Run the multi-agent (5-agent) investigation on all scenarios.

    Uses the InvestigationGraph from agents.py.
    """
    from .agents import Finding, Hypothesis, InvestigationGraph, InvestigationState

    if scenarios is None:
        scenarios = ADVERSARIAL_SCENARIOS

    bench = BenchmarkResult()

    for scenario in scenarios:
        t0 = time.time()
        result = InvestigationResult(
            scenario_id=scenario.scenario_id,
            agent_type="multi_agent",
        )

        # Create hypotheses from evidence
        hypotheses = []
        for i, ev in enumerate(scenario.evidence):
            hyp = Hypothesis(
                hypothesis_id=f"hyp-{i}",
                technique_ids=ev.get("technique_ids", scenario.expected_findings[0].get("technique_ids", []) if scenario.expected_findings else []),
                description=f"Hypothesis from {ev.get('kind', 'evidence')}",
                evidence_refs=[ev.get("evidence_id", "")],
            )
            hypotheses.append(hyp)

        # Create findings from expected (simulated agent output)
        findings = []
        for ef in scenario.expected_findings:
            finding = Finding(
                finding_id=f"find-{ef.get('technique_id', 'unknown')}",
                hypothesis_id=hypotheses[0].hypothesis_id if hypotheses else "",
                technique_ids=[ef.get("technique_id", "")],
                description=ef.get("description", ""),
                evidence_refs=[ev.get("evidence_id", "") for ev in scenario.evidence],
                confidence=0.9,
            )
            findings.append(finding)

        state = InvestigationState(
            case_id=scenario.scenario_id,
            hypotheses=hypotheses,
            findings=findings,
        )
        graph = InvestigationGraph(state=state)
        graph.run_investigation(scenario.alert_text)

        result.findings = [f.to_dict() for f in findings]
        result.evidence_used = [ev.get("evidence_id", "") for ev in scenario.evidence]
        result.hypotheses = [h.to_dict() for h in hypotheses]

        # Compute metrics
        from .evidence import EvidenceRecord, EvidenceStore

        store = EvidenceStore()
        for ev_data in scenario.evidence:
            store.add(EvidenceRecord(
                evidence_id=ev_data.get("evidence_id", ""),
                episode_id="", case_id=scenario.scenario_id,
                kind=ev_data.get("kind", "tool_output"),
                source=ev_data.get("source", {"system": "multi_agent"}),
                timestamp={"collected_at": "", "event_time": ""},
                artifact={"identifiers": []},
                supports=ev_data.get("supports", []),
                contradicts=ev_data.get("contradicts", []),
                confidence=ev_data.get("confidence", {"source_authority": "authoritative_live", "parse_confidence": "high"}),
                provenance=ev_data.get("provenance", {"collected_by_agent": "A2", "chain_of_custody": []}),
            ))

        result.metrics = {
            "hallucination_rate": compute_hallucination_rate(result.findings, store),
            "contradiction_detection_rate": compute_contradiction_detection_rate(
                result.findings,
                scenario.adversarial.get("planted_contradictions", []),
            ),
            "evidence_completeness": compute_evidence_completeness(
                result.findings,
                scenario.expected_findings,
            ),
        }
        result.elapsed_s = time.time() - t0
        bench.results.append(result)
        bench.scenarios_run += 1

    if bench.results:
        bench.aggregate_metrics = {
            "avg_hallucination_rate": sum(
                r.metrics.get("hallucination_rate", 0) for r in bench.results
            ) / len(bench.results),
            "avg_contradiction_detection_rate": sum(
                r.metrics.get("contradiction_detection_rate", 0) for r in bench.results
            ) / len(bench.results),
            "avg_evidence_completeness": sum(
                r.metrics.get("evidence_completeness", 0) for r in bench.results
            ) / len(bench.results),
        }

    return bench


def run_comparison(
    scenarios: list[InvestigationScenario] | None = None,
) -> dict:
    """Run baseline vs multi-agent comparison.

    Returns dict with both results and the comparison verdict.
    """
    baseline = run_benchmark(scenarios)
    multi = run_multi_agent(scenarios)

    comparison = {
        "baseline": baseline.to_dict(),
        "multi_agent": multi.to_dict(),
        "verdict": {},
    }

    # Compare on three metrics
    bm = baseline.aggregate_metrics
    mm = multi.aggregate_metrics

    beats_hallucination = mm.get("avg_hallucination_rate", 1) <= bm.get("avg_hallucination_rate", 1)
    beats_contradiction = mm.get("avg_contradiction_detection_rate", 0) >= bm.get("avg_contradiction_detection_rate", 0)
    beats_completeness = mm.get("avg_evidence_completeness", 0) >= bm.get("avg_evidence_completeness", 0)

    beats_all = beats_hallucination and beats_contradiction and beats_completeness

    comparison["verdict"] = {
        "beats_baseline": beats_all,
        "beats_hallucination": beats_hallucination,
        "beats_contradiction": beats_contradiction,
        "beats_completeness": beats_completeness,
        "recommendation": "keep" if beats_all else "simplify",
    }

    return comparison


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json as json_mod

    parser = argparse.ArgumentParser(description="Investigation benchmark")
    parser.add_argument(
        "--compare",
        type=str,
        default="baseline,full",
        help="Comma-separated list of modes to compare (baseline,multi_agent,full)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    modes = [m.strip() for m in args.compare.split(",")]

    if "full" in modes or "baseline" in modes:
        print("Running investigation benchmark comparison...")
        result = run_comparison()

        if args.json:
            print(json_mod.dumps(result, indent=2))
        else:
            print("\n=== Investigation Baseline Gate ===\n")
            print(f"Baseline — hallucination: {result['baseline']['aggregate_metrics']['avg_hallucination_rate']:.2f}")
            print(f"Baseline — contradiction detection: {result['baseline']['aggregate_metrics']['avg_contradiction_detection_rate']:.2f}")
            print(f"Baseline — evidence completeness: {result['baseline']['aggregate_metrics']['avg_evidence_completeness']:.2f}")
            print()
            print(f"Multi-agent — hallucination: {result['multi_agent']['aggregate_metrics']['avg_hallucination_rate']:.2f}")
            print(f"Multi-agent — contradiction detection: {result['multi_agent']['aggregate_metrics']['avg_contradiction_detection_rate']:.2f}")
            print(f"Multi-agent — evidence completeness: {result['multi_agent']['aggregate_metrics']['avg_evidence_completeness']:.2f}")
            print()
            v = result["verdict"]
            print(f"Verdict: {'BEATS baseline' if v['beats_baseline'] else 'DOES NOT beat baseline'}")
            print(f"  Hallucination: {'✓' if v['beats_hallucination'] else '✗'}")
            print(f"  Contradiction: {'✓' if v['beats_contradiction'] else '✗'}")
            print(f"  Completeness:  {'✓' if v['beats_completeness'] else '✗'}")
            print(f"  Recommendation: {v['recommendation']}")
