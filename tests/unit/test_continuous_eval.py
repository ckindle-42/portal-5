"""Tests for continuous evaluation + content growth — Phase 8.

Validates:
- Corpus growth from closed cases
- Analyst feedback pipeline
- Content gap identification
- Observability dashboard data
- Compliance overlay computes coverage
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal.modules.security.core.capability_graph import seed_graph_from_assets
from portal.modules.security.core.continuous_eval import (
    AnalystFeedback,
    AnalystFeedbackStore,
    ContentGap,
    RegressionCorpus,
    close_case_to_corpus,
    compliance_coverage,
    generate_dashboard_data,
    identify_content_gaps,
)

# ── Corpus growth ────────────────────────────────────────────────────────────


class TestCorpusGrowth:
    """Closed investigation cases → regression corpus."""

    def test_corpus_add_and_count(self):
        corpus = RegressionCorpus()
        assert corpus.count() == 0

        entry = close_case_to_corpus(
            corpus,
            case_id="case-001",
            scenario_id="web_sqli_dump",
            alert_text="SQL injection detected",
            expected_findings=[{"technique_id": "T1190"}],
            evidence_summary=[{"kind": "siem_hit"}],
            outcome="verified",
        )
        assert corpus.count() == 1
        assert entry.case_id == "case-001"

    def test_corpus_entry_to_dict(self):
        corpus = RegressionCorpus()
        entry = close_case_to_corpus(
            corpus,
            "case-001",
            "test",
            "alert",
            [{"technique_id": "T1190"}],
            [],
            "verified",
        )
        d = entry.to_dict()
        json.dumps(d)

    def test_corpus_list_all(self):
        corpus = RegressionCorpus()
        close_case_to_corpus(corpus, "c1", "s1", "a1", [], [], "verified")
        close_case_to_corpus(corpus, "c2", "s2", "a2", [], [], "rejected")
        assert len(corpus.list_all()) == 2


# ── Analyst feedback ─────────────────────────────────────────────────────────


class TestAnalystFeedback:
    """Analyst feedback pipeline — feeds growth loop, never inference."""

    def test_feedback_store(self):
        store = AnalystFeedbackStore()
        feedback = AnalystFeedback(
            feedback_id="fb-001",
            case_id="case-001",
            analyst_id="analyst-1",
            feedback_type="correction",
            content={"corrected_technique": "T1558.003"},
        )
        store.add(feedback)
        assert store.count() == 1

    def test_feedback_for_case(self):
        store = AnalystFeedbackStore()
        store.add(AnalystFeedback("fb-1", "c1", "a1", "correction", {}))
        store.add(AnalystFeedback("fb-2", "c2", "a1", "confirmation", {}))
        store.add(AnalystFeedback("fb-3", "c1", "a2", "enhancement", {}))
        assert len(store.for_case("c1")) == 2

    def test_feedback_to_dict(self):
        feedback = AnalystFeedback("fb-001", "c1", "a1", "correction", {"x": 1})
        d = feedback.to_dict()
        json.dumps(d)


# ── Content gaps ─────────────────────────────────────────────────────────────


class TestContentGaps:
    """Content gap identification scans for blue scenarios, oracles, ICS."""

    def test_identify_gaps(self):
        graph = seed_graph_from_assets()
        # Create some BLUE_ONLY and DETECTION_MISSING gaps
        for gap in list(graph.gaps.values())[:3]:
            gap.summary = "BLUE_ONLY"
            gap.axes["detection"] = "DETECTION_NO_HIT"
        for gap in list(graph.gaps.values())[3:6]:
            gap.axes["detection"] = "DETECTION_MISSING"
        gaps = identify_content_gaps(graph)
        assert len(gaps) > 0

    def test_gap_to_dict(self):
        gap = ContentGap(
            gap_type="blue_scenario",
            description="test",
            technique_ids=["T1190"],
        )
        d = gap.to_dict()
        json.dumps(d)


# ── Observability ────────────────────────────────────────────────────────────


class TestObservability:
    """Dashboard data generation."""

    def test_dashboard_data(self):
        graph = seed_graph_from_assets()
        data = generate_dashboard_data(graph)
        assert "coverage" in data
        assert "summary" in data
        assert "health" in data
        json.dumps(data)

    def test_health_metrics(self):
        graph = seed_graph_from_assets()
        data = generate_dashboard_data(graph)
        health = data["health"]
        assert 0 <= health["coverage_pct"] <= 100
        assert 0 <= health["detection_pct"] <= 100


# ── Compliance overlay ───────────────────────────────────────────────────────


class TestComplianceOverlay:
    """Compliance coverage computation."""

    def test_compliance_coverage(self):
        graph = seed_graph_from_assets()
        result = compliance_coverage(graph, "CIP-007")
        assert result["framework"] == "CIP-007"
        assert len(result["controls"]) > 0
        assert 0 <= result["overall_coverage_pct"] <= 100

    def test_nist_compliance(self):
        graph = seed_graph_from_assets()
        result = compliance_coverage(graph, "NIST-800-53")
        assert result["framework"] == "NIST-800-53"

    def test_compliance_to_dict(self):
        graph = seed_graph_from_assets()
        result = compliance_coverage(graph)
        json.dumps(result)
