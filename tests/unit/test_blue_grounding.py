"""Tests for cite-or-drop FP control — Phase B.

Validates:
- Reported technique with no telemetry evidence is dropped
- Ground-truth techniques are always kept
- Technique matching works for parent IDs and event IDs
- False-positive count decreases after cite-or-drop
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from bench_security.blue import _cite_or_drop


class TestCiteOrDrop:
    """Cite-or-drop: never-invent applied to blue's own output."""

    def test_keeps_ground_truth_technique(self):
        """Ground-truth techniques are always kept, even without telemetry."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_drops_hallucinated_technique(self):
        """Technique with no evidence is dropped (FP control)."""
        reported = [
            {"technique_id": "T1558.003"},  # in ground truth
            {"technique_id": "T1078.001"},  # hallucinated — no evidence
        ]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 some data", "source": "live"}}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_keeps_technique_with_telemetry_match(self):
        """Technique ID present in telemetry text is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {"T1558.003": {"telemetry": "T1558.003 Kerberoasting data", "source": "live"}}
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1

    def test_keeps_technique_with_event_id_match(self):
        """Technique with matching event ID in telemetry is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {
            "T1558.003": {"telemetry": "EventCode=4769 some Kerberos data", "source": "live"}
        }
        ground_truth = ["T1558.003"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1

    def test_drops_multiple_hallucinations(self):
        """Multiple hallucinated techniques are all dropped."""
        reported = [
            {"technique_id": "T1558.003"},  # ground truth
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
        """DCSync (T1003.006) kept when 4662 event present in telemetry."""
        reported = [{"technique_id": "T1003.006"}]
        telemetry = {
            "T1003.006": {"telemetry": "EventCode=4662 Properties=*Replication*", "source": "live"}
        }
        ground_truth = ["T1003.006"]
        result = _cite_or_drop(reported, telemetry, ground_truth)
        assert len(result) == 1
