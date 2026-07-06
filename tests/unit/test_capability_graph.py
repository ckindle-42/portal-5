"""Tests for capability graph + gap engine — Phase 3 of BUILD_PROGRAM.

Validates:
- Stable-ID entities (Procedure, Detection, Gap)
- Deterministic gap classification from reason codes
- Synthetic/indeterminate episode never counts as COVERED
- Coverage tiers compute correct denominators
- Navigator JSON validates
- Graph seeding from existing assets
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from bench_security.capability_graph import (
    CapabilityGraph,
    Detection,
    Gap,
    Procedure,
    build_gap,
    classify_gap,
    generate_coverage_json,
    generate_markdown_heatmap,
    generate_navigator_layer,
    seed_graph_from_assets,
    update_graph_from_episode,
)

# ── Stable-ID entities ───────────────────────────────────────────────────────


class TestEntities:
    """Procedure, Detection, Gap have stable IDs and correct shapes."""

    def test_procedure_is_hashable(self):
        p = Procedure("proc-test", "test", frozenset({"T1190"}))
        assert p.procedure_id == "proc-test"
        assert hash(p) is not None  # hashable

    def test_detection_fields(self):
        d = Detection("det-T1190", "T1190", spl="search ...", description="web exploit")
        assert d.detection_id == "det-T1190"
        assert d.technique_id == "T1190"
        assert d.status == "active"

    def test_gap_to_dict(self):
        g = Gap(
            gap_id="gap-test",
            procedure_id="proc-test",
            technique_id="T1190",
            axes={
                "red": "RED_LANDED",
                "telemetry": "TELEMETRY_OBSERVED",
                "detection": "DETECTION_NO_HIT",
                "response": "RESPONSE_NOT_TESTED",
            },
            summary="RED_ONLY",
            reason_codes=["RED_LANDED", "TELEMETRY_OBSERVED"],
        )
        d = g.__dict__
        assert d["gap_id"] == "gap-test"
        json.dumps(d)  # JSON-safe


# ── Gap classification (deterministic) ───────────────────────────────────────


class TestGapClassification:
    """Gap classification is pure code over reason codes."""

    def test_covered_when_red_landed_and_detected(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_OBSERVED",
                detection_status="DETECTION_CONFIRMED",
            )
            == "COVERED"
        )

    def test_red_only_when_landed_no_detection(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_OBSERVED",
                detection_status="DETECTION_NO_HIT",
            )
            == "RED_ONLY"
        )

    def test_red_only_when_detection_missing(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_OBSERVED",
                detection_status="DETECTION_MISSING",
            )
            == "RED_ONLY"
        )

    def test_blue_only_when_detection_exists_but_not_exercised(self):
        assert (
            classify_gap(
                red_status="RED_NOT_RUN",
                telemetry_status="TELEMETRY_NOT_REQUIRED",
                detection_status="DETECTION_NO_HIT",
            )
            == "BLUE_ONLY"
        )

    def test_neither_when_no_red_no_detection(self):
        assert (
            classify_gap(
                red_status="RED_NOT_RUN",
                telemetry_status="TELEMETRY_NOT_REQUIRED",
                detection_status="DETECTION_NOT_RUN",
            )
            == "NEITHER"
        )

    def test_blocked_when_telemetry_failed(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_COLLECTION_FAILED",
                detection_status="DETECTION_NO_HIT",
            )
            == "BLOCKED"
        )

    def test_blocked_when_telemetry_not_indexed(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_NOT_INDEXED",
                detection_status="DETECTION_NO_HIT",
            )
            == "BLOCKED"
        )

    def test_blocked_when_telemetry_not_configured(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_NOT_CONFIGURED",
                detection_status="DETECTION_NO_HIT",
            )
            == "BLOCKED"
        )

    def test_blocked_when_synthetic(self):
        assert (
            classify_gap(
                red_status="RED_LANDED",
                telemetry_status="TELEMETRY_OBSERVED",
                detection_status="DETECTION_HIT_UNATTRIBUTED",
                used_synthetic=True,
            )
            == "BLOCKED"
        )

    def test_neither_when_red_failed(self):
        assert (
            classify_gap(
                red_status="RED_EXECUTION_FAILED",
                telemetry_status="TELEMETRY_OBSERVED",
                detection_status="DETECTION_NO_HIT",
            )
            == "NEITHER"
        )

    def test_synthetic_never_covered(self):
        """HEADLINE: synthetic telemetry NEVER yields COVERED."""
        result = classify_gap(
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_OBSERVED",
            detection_status="DETECTION_CONFIRMED",
            used_synthetic=True,
        )
        assert result != "COVERED", "Synthetic must NEVER yield COVERED"
        assert result == "BLOCKED"

    def test_indeterminate_never_covered(self):
        """Telemetry failure never yields COVERED."""
        for tel_status in ("TELEMETRY_COLLECTION_FAILED", "TELEMETRY_NOT_INDEXED"):
            result = classify_gap(
                red_status="RED_LANDED",
                telemetry_status=tel_status,
                detection_status="DETECTION_CONFIRMED",
            )
            assert result != "COVERED", f"{tel_status} must NOT yield COVERED"


# ── build_gap ────────────────────────────────────────────────────────────────


class TestBuildGap:
    """build_gap creates correct Gap from procedure + episode data."""

    def test_build_gap_with_episode(self):
        proc = Procedure("proc-test", "test", frozenset({"T1190"}))
        episode_data = {
            "red_status": "RED_LANDED",
            "telemetry_status": "TELEMETRY_OBSERVED",
            "detection_status": "DETECTION_CONFIRMED",
            "response_status": "RESPONSE_NOT_TESTED",
            "used_synthetic": False,
        }
        gap = build_gap(proc, "T1190", episode_data)
        assert gap.summary == "COVERED"
        assert gap.procedure_id == "proc-test"
        assert gap.technique_id == "T1190"
        assert "RED_LANDED" in gap.reason_codes

    def test_build_gap_without_episode(self):
        proc = Procedure("proc-test", "test", frozenset({"T1190"}))
        gap = build_gap(proc, "T1190", None)
        assert gap.summary == "NEITHER"
        assert gap.axes["red"] == "RED_NOT_RUN"


# ── Capability graph ─────────────────────────────────────────────────────────


class TestCapabilityGraph:
    """Capability graph stores and queries procedures, detections, gaps."""

    def test_add_and_query(self):
        graph = CapabilityGraph()
        proc = Procedure("proc-a", "scenario_a", frozenset({"T1190", "T1059"}))
        det = Detection("det-T1190", "T1190")
        graph.add_procedure(proc)
        graph.add_detection(det)

        assert "proc-a" in graph.procedures
        assert "det-T1190" in graph.detections
        assert graph.techniques_exercised() == {"T1190", "T1059"}
        assert graph.techniques_detected() == {"T1190"}

    def test_coverage_gaps_filter(self):
        graph = CapabilityGraph()
        proc = Procedure("proc-a", "s", frozenset({"T1190"}))
        graph.add_procedure(proc)
        graph.add_gap(Gap("gap-1", "proc-a", "T1190", {}, "COVERED", []))
        graph.add_gap(Gap("gap-2", "proc-a", "T1059", {}, "RED_ONLY", []))

        gaps = graph.coverage_gaps()
        assert len(gaps) == 1
        assert gaps[0].summary == "RED_ONLY"

    def test_summary_counts(self):
        graph = CapabilityGraph()
        graph.add_gap(Gap("g1", "p", "T1", {}, "COVERED", []))
        graph.add_gap(Gap("g2", "p", "T2", {}, "RED_ONLY", []))
        graph.add_gap(Gap("g3", "p", "T3", {}, "RED_ONLY", []))
        graph.add_gap(Gap("g4", "p", "T4", {}, "BLOCKED", []))

        counts = graph.summary_counts()
        assert counts["COVERED"] == 1
        assert counts["RED_ONLY"] == 2
        assert counts["BLOCKED"] == 1
        assert counts["NEITHER"] == 0

    def test_to_dict_is_json_safe(self):
        graph = CapabilityGraph()
        graph.add_procedure(Procedure("p", "s", frozenset({"T1"})))
        d = graph.to_dict()
        json.dumps(d)


# ── Graph seeding ────────────────────────────────────────────────────────────


class TestGraphSeeding:
    """Graph seeds from existing SCENARIOS + spl_detections."""

    def test_seed_graph_creates_procedures(self):
        graph = seed_graph_from_assets()
        assert len(graph.procedures) > 0
        # Should have at least 50 scenarios
        assert len(graph.procedures) >= 50

    def test_seed_graph_creates_detections(self):
        graph = seed_graph_from_assets()
        assert len(graph.detections) >= 29

    def test_seed_graph_creates_gaps(self):
        graph = seed_graph_from_assets()
        assert len(graph.gaps) > 0
        # All initial gaps should be NEITHER (no episodes yet)
        for gap in graph.gaps.values():
            assert gap.summary == "NEITHER"

    def test_seed_graph_techniques_exercised(self):
        graph = seed_graph_from_assets()
        techniques = graph.techniques_exercised()
        assert "T1190" in techniques
        assert "T1558.003" in techniques

    def test_seed_graph_techniques_detected(self):
        graph = seed_graph_from_assets()
        detected = graph.techniques_detected()
        assert "T1190" in detected
        assert len(detected) >= 29


# ── Graph update from episodes ───────────────────────────────────────────────


class TestGraphUpdate:
    """Graph updates correctly from episode outcomes."""

    def test_update_marks_covered(self):
        graph = seed_graph_from_assets()
        episode = {
            "scenario": "web_sqli_dump",
            "red_status": "RED_LANDED",
            "telemetry_status": "TELEMETRY_OBSERVED",
            "detection_status": "DETECTION_CONFIRMED",
            "response_status": "RESPONSE_NOT_TESTED",
            "used_synthetic": False,
        }
        update_graph_from_episode(graph, episode)
        # web_sqli_dump has T1190 in detect_ground_truth
        gap_id = "gap-proc-web_sqli_dump-T1190"
        assert gap_id in graph.gaps
        assert graph.gaps[gap_id].summary == "COVERED"

    def test_update_marks_red_only(self):
        graph = seed_graph_from_assets()
        episode = {
            "scenario": "web_sqli_dump",
            "red_status": "RED_LANDED",
            "telemetry_status": "TELEMETRY_OBSERVED",
            "detection_status": "DETECTION_NO_HIT",
            "response_status": "RESPONSE_NOT_TESTED",
            "used_synthetic": False,
        }
        update_graph_from_episode(graph, episode)
        gap_id = "gap-proc-web_sqli_dump-T1190"
        assert graph.gaps[gap_id].summary == "RED_ONLY"

    def test_update_ignores_unknown_scenario(self):
        graph = seed_graph_from_assets()
        gap_count_before = len(graph.gaps)
        episode = {"scenario": "nonexistent_scenario"}
        update_graph_from_episode(graph, episode)
        assert len(graph.gaps) == gap_count_before


# ── Coverage map artifacts ───────────────────────────────────────────────────


class TestCoverageMap:
    """Coverage map artifacts validate."""

    def test_coverage_json_structure(self):
        graph = seed_graph_from_assets()
        cov = generate_coverage_json(graph)
        assert "per_technique" in cov
        assert "tiers" in cov
        assert "summary" in cov
        assert cov["technique_count"] > 0

    def test_coverage_json_tiers(self):
        graph = seed_graph_from_assets()
        cov = generate_coverage_json(graph)
        tiers = cov["tiers"]
        assert tiers["eligible"] > 0
        assert tiers["exercised"] > 0
        assert tiers["detected"] > 0
        assert 0 <= tiers["exercised_pct"] <= 100
        assert 0 <= tiers["detected_pct"] <= 100

    def test_coverage_json_is_json_safe(self):
        graph = seed_graph_from_assets()
        cov = generate_coverage_json(graph)
        json.dumps(cov)

    def test_navigator_layer_structure(self):
        graph = seed_graph_from_assets()
        layer = generate_navigator_layer(graph)
        assert layer["name"] == "Portal 5 Capability Coverage"
        assert layer["domain"] == "enterprise-attack"
        assert len(layer["techniques"]) > 0
        json.dumps(layer)

    def test_markdown_heatmap_not_empty(self):
        graph = seed_graph_from_assets()
        md = generate_markdown_heatmap(graph)
        assert "Capability Coverage Heatmap" in md
        assert "T1190" in md
        assert "COVERED" in md or "NEITHER" in md

    def test_per_technique_has_four_bars(self):
        graph = seed_graph_from_assets()
        cov = generate_coverage_json(graph)
        for tid, info in cov["per_technique"].items():
            assert "exercise" in info, f"{tid} missing exercise"
            assert "telemetry" in info, f"{tid} missing telemetry"
            assert "detection" in info, f"{tid} missing detection"
            assert "response" in info, f"{tid} missing response"
            assert "summary" in info, f"{tid} missing summary"
