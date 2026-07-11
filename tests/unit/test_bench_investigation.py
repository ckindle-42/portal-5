"""Tests for investigation benchmark — Phase 6b.

Validates:
- Single-agent baseline runs on all scenarios
- Metrics computation (hallucination, contradiction, completeness)
- Adversarial scenarios exist and are well-formed
- Benchmark runner produces aggregate metrics
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal.modules.security.core.investigation import EvidenceStore
from portal.modules.security.core.investigation.bench_investigation import (
    ADVERSARIAL_SCENARIOS,
    compute_contradiction_detection_rate,
    compute_evidence_completeness,
    compute_hallucination_rate,
    run_benchmark,
    run_single_agent_baseline,
)
from portal.modules.security.core.investigation.evidence import EvidenceRecord

# ── Adversarial scenarios ────────────────────────────────────────────────────


class TestAdversarialScenarios:
    """Adversarial test scenarios are well-formed."""

    def test_scenarios_exist(self):
        assert len(ADVERSARIAL_SCENARIOS) >= 2

    def test_scenario_has_required_fields(self):
        for sc in ADVERSARIAL_SCENARIOS:
            assert sc.scenario_id
            assert sc.name
            assert sc.alert_text
            assert sc.expected_findings
            assert isinstance(sc.evidence, list)

    def test_scenario_has_adversarial_content(self):
        for sc in ADVERSARIAL_SCENARIOS:
            assert sc.adversarial, f"{sc.scenario_id} missing adversarial content"

    def test_scenario_to_dict(self):
        import json

        for sc in ADVERSARIAL_SCENARIOS:
            d = sc.to_dict()
            json.dumps(d)


# ── Metrics computation ──────────────────────────────────────────────────────


class TestMetrics:
    """Metrics computation is deterministic and correct."""

    def test_hallucination_rate_zero_when_all_cited(self):
        store = EvidenceStore()
        store.add(
            EvidenceRecord(
                evidence_id="ev-001",
                episode_id="",
                case_id="",
                kind="siem_hit",
                source={"system": "splunk"},
                timestamp={"collected_at": "", "event_time": ""},
                artifact={"identifiers": []},
                supports=[],
                contradicts=[],
                confidence={"source_authority": "authoritative_live", "parse_confidence": "high"},
                provenance={"collected_by_agent": "A2", "chain_of_custody": []},
            )
        )
        findings = [{"evidence_refs": ["ev-001"], "text": "found"}]
        assert compute_hallucination_rate(findings, store) == 0.0

    def test_hallucination_rate_one_when_no_evidence(self):
        store = EvidenceStore()
        findings = [{"evidence_refs": [], "text": "found"}]
        assert compute_hallucination_rate(findings, store) == 1.0

    def test_hallucination_rate_partial(self):
        store = EvidenceStore()
        store.add(
            EvidenceRecord(
                evidence_id="ev-001",
                episode_id="",
                case_id="",
                kind="siem_hit",
                source={"system": "splunk"},
                timestamp={"collected_at": "", "event_time": ""},
                artifact={"identifiers": []},
                supports=[],
                contradicts=[],
                confidence={"source_authority": "authoritative_live", "parse_confidence": "high"},
                provenance={"collected_by_agent": "A2", "chain_of_custody": []},
            )
        )
        findings = [
            {"evidence_refs": ["ev-001"]},  # valid
            {"evidence_refs": ["ev-nonexistent"]},  # hallucination
        ]
        rate = compute_hallucination_rate(findings, store)
        assert rate == 0.5

    def test_contradiction_detection_rate_zero_when_missed(self):
        findings = [{"text": "found", "contradictions": []}]
        contradictions = [{"id": "c-001", "description": "wrong technique"}]
        assert compute_contradiction_detection_rate(findings, contradictions) == 0.0

    def test_contradiction_detection_rate_one_when_detected(self):
        findings = [{"text": "found", "contradictions": ["c-001"], "notes": ""}]
        contradictions = [{"id": "c-001", "description": "wrong technique"}]
        assert compute_contradiction_detection_rate(findings, contradictions) == 1.0

    def test_contradiction_detection_rate_no_contradictions(self):
        assert compute_contradiction_detection_rate([], []) == 1.0

    def test_evidence_completeness_zero_when_missed(self):
        findings = [{"text": "found", "technique_ids": []}]
        expected = [{"technique_id": "T1190", "description": "web exploit"}]
        assert compute_evidence_completeness(findings, expected) == 0.0

    def test_evidence_completeness_one_when_found(self):
        findings = [{"text": "found", "technique_ids": ["T1190"]}]
        expected = [{"technique_id": "T1190", "description": "web exploit"}]
        assert compute_evidence_completeness(findings, expected) == 1.0


# ── Single-agent baseline ────────────────────────────────────────────────────


class TestSingleAgentBaseline:
    """Single-agent baseline runs on all scenarios."""

    def test_baseline_runs_on_all_scenarios(self):
        for sc in ADVERSARIAL_SCENARIOS:
            result = run_single_agent_baseline(sc)
            assert result.scenario_id == sc.scenario_id
            assert result.agent_type == "single_agent_baseline"
            assert "hallucination_rate" in result.metrics

    def test_baseline_preserves_evidence(self):
        sc = ADVERSARIAL_SCENARIOS[0]
        result = run_single_agent_baseline(sc)
        assert len(result.evidence_used) == len(sc.evidence)

    def test_baseline_result_to_dict(self):
        import json

        result = run_single_agent_baseline(ADVERSARIAL_SCENARIOS[0])
        json.dumps(result.to_dict())


# ── Benchmark runner ─────────────────────────────────────────────────────────


class TestBenchmarkRunner:
    """Benchmark runner produces aggregate metrics."""

    def test_run_benchmark(self):
        bench = run_benchmark()
        assert bench.scenarios_run == len(ADVERSARIAL_SCENARIOS)
        assert len(bench.results) == bench.scenarios_run
        assert "avg_hallucination_rate" in bench.aggregate_metrics

    def test_aggregate_metrics_range(self):
        bench = run_benchmark()
        for key in (
            "avg_hallucination_rate",
            "avg_contradiction_detection_rate",
            "avg_evidence_completeness",
        ):
            val = bench.aggregate_metrics[key]
            assert 0.0 <= val <= 1.0, f"{key} = {val} out of range"

    def test_benchmark_to_dict(self):
        import json

        bench = run_benchmark()
        json.dumps(bench.to_dict())
