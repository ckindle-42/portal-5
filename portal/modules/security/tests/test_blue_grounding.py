"""Tests for cite-or-drop FP control — Phase B.

Validates:
- Reported technique with no telemetry evidence is dropped
- Ground-truth techniques are kept ONLY when their own cited evidence is
  grounded in real telemetry (not on label match alone — see
  test_drops_ground_truth_technique_with_fabricated_evidence)
- Technique matching works for parent IDs and event IDs
- False-positive count decreases after cite-or-drop
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.blue import _cite_or_drop


class TestCiteOrDrop:
    """Cite-or-drop: never-invent applied to blue's own output."""

    def test_keeps_ground_truth_technique_with_grounded_evidence(self):
        """Ground-truth techniques are kept when their cited evidence is
        actually grounded in real telemetry."""
        reported = [{"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"}]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 some data", "source": "live"}}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_drops_ground_truth_technique_with_fabricated_evidence(self):
        """A CORE regression test: a technique ID matching ground truth, but
        whose OWN cited evidence is fabricated (never appears in real
        telemetry), must be dropped — not kept unconditionally.

        Found live 2026-07-22 (GATE-D ablation Part II-A): the prior
        unconditional "ground truth -> always keep" exemption let
        `vuln_fastjson_rce`'s Expert cite a fabricated log line
        ("GET /api/v1/data?param=..." / source_ip=203.0.113.45) for T1190 —
        neither string appears anywhere in the real telemetry, which
        contains only benign Tomcat startup logs and plain GET / 200s — and
        score a clean HIT purely because the label happened to be correct."""
        reported = [
            {
                "technique_id": "T1190",
                "evidence": '"GET /api/v1/data?param=abc HTTP/1.1" 200 1024; source_ip=203.0.113.45',
            }
        ]
        telemetry = {
            "web:access": {
                "telemetry": 'GET / HTTP/1.1" 200 11250 (benign startup traffic only)',
                "source": "live",
            }
        }
        ground_truth = ["T1190"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert result == []

    def test_drops_hallucinated_technique(self):
        """Technique with no evidence is dropped (FP control)."""
        reported = [
            {"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"},  # in ground truth
            {"technique_id": "T1078.001", "evidence": "nothing real"},  # hallucinated
        ]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 some data", "source": "live"}}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_keeps_technique_with_telemetry_match(self):
        """Non-ground-truth technique ID present in telemetry text is kept
        (this path doesn't require a per-detection evidence field — it
        checks the technique ID itself against the whole telemetry blob)."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {"T1558.003": {"telemetry": "T1558.003 Kerberoasting data", "source": "live"}}
        ground_truth = []
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1

    def test_keeps_technique_with_event_id_match(self):
        """Technique with matching event ID in telemetry is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {
            "T1558.003": {"telemetry": "EventCode=4769 some Kerberos data", "source": "live"}
        }
        ground_truth = []
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1

    def test_drops_multiple_hallucinations(self):
        """Multiple hallucinated techniques are all dropped."""
        reported = [
            {"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"},  # ground truth
            {"technique_id": "T1078.001"},  # hallucinated
            {"technique_id": "T1021.003"},  # hallucinated
            {"technique_id": "T1059.007"},  # hallucinated
        ]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 data", "source": "live"}}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_empty_reported(self):
        """Empty reported list returns empty."""
        assert _cite_or_drop([], {}, []) == []

    def test_keeps_technique_with_parent_id_in_telemetry(self):
        """Technique with parent ID in telemetry is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {"T1558.003": {"telemetry": "Some T1558 Kerberos data", "source": "live"}}
        ground_truth = []
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1

    def test_dcsync_event_id_match(self):
        """DCSync (T1003.006) kept when its own cited evidence names the
        4662 event that's actually present in telemetry."""
        reported = [{"technique_id": "T1003.006", "evidence": "EventCode=4662 replication seen"}]
        telemetry = {
            "T1003.006": {"telemetry": "EventCode=4662 Properties=*Replication*", "source": "live"}
        }
        ground_truth = ["T1003.006"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
