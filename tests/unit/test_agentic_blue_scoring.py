"""Unit tests for agentic_blue_eval M1 — three-tier scoring (exact/parent/tactic).

All tests use only in-memory data; no network, no Docker, no lab.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.agentic_blue_eval import (
    _parent_technique,
    _tactic_for,
    score_findings_tiered,
)


@pytest.fixture(autouse=True)
def _reset_tactic_cache():
    """Reset the tactic cache before each test to avoid stale data."""
    import portal.modules.security.core.agentic_blue_eval as _mod
    import portal.modules.security.core.siem.spl_detections as _spl

    _mod._tactic_cache = None
    _spl._cache = None
    yield
    _mod._tactic_cache = None
    _spl._cache = None


# ── _parent_technique ────────────────────────────────────────────────────────


class TestParentTechnique:
    def test_sub_to_parent(self):
        assert _parent_technique("T1558.003") == "T1558"

    def test_already_parent(self):
        assert _parent_technique("T1558") == "T1558"

    def test_various_subtechniques(self):
        assert _parent_technique("T1059.004") == "T1059"
        assert _parent_technique("T1003.006") == "T1003"
        assert _parent_technique("T1558.004") == "T1558"

    def test_empty_string(self):
        assert _parent_technique("") == ""


# ── _tactic_for ──────────────────────────────────────────────────────────────


class TestTacticFor:
    def test_known_subtechnique(self):
        assert _tactic_for("T1558.003") == "credential-access"

    def test_known_parent(self):
        assert _tactic_for("T1558") == "credential-access"

    def test_exploit_public_facing(self):
        assert _tactic_for("T1190") == "initial-access"

    def test_unknown_technique(self):
        assert _tactic_for("T9999") == ""

    def test_empty_string(self):
        assert _tactic_for("") == ""

    def test_execution_tactic(self):
        assert _tactic_for("T1059.004") == "execution"

    def test_lateral_movement(self):
        assert _tactic_for("T1210") == "lateral-movement"


# ── score_findings_tiered ────────────────────────────────────────────────────


class TestScoreFindingsTiered:
    def test_exact_match(self):
        """Exact match: detected == ground truth."""
        detected = {"T1558.003", "T1003.006"}
        ground_truth = {"T1558.003", "T1003.006"}
        result = score_findings_tiered(detected, ground_truth)
        assert result["exact"]["recall"] == 1.0
        assert result["parent"]["recall"] == 1.0
        assert result["tactic"]["recall"] == 1.0
        assert sorted(result["exact"]["true_positives"]) == ["T1003.006", "T1558.003"]

    def test_parent_near_miss(self):
        """Parent match: detected T1558 vs ground truth T1558.003."""
        detected = {"T1558"}
        ground_truth = {"T1558.003"}
        result = score_findings_tiered(detected, ground_truth)
        # Exact: 0 (T1558 != T1558.003)
        assert result["exact"]["recall"] == 0.0
        # Parent: 1.0 (parent of T1558 == parent of T1558.003 = T1558)
        assert result["parent"]["recall"] == 1.0
        assert "T1558" in result["parent"]["true_positives"]

    def test_tactic_match(self):
        """Tactic match: detected T1110 vs ground truth T1558.003 (both credential-access)."""
        detected = {"T1110"}
        ground_truth = {"T1558.003"}
        result = score_findings_tiered(detected, ground_truth)
        # Exact: 0
        assert result["exact"]["recall"] == 0.0
        # Parent: 0 (T1110 parent != T1558.003 parent)
        assert result["parent"]["recall"] == 0.0
        # Tactic: 1.0 (both are credential-access)
        assert result["tactic"]["recall"] == 1.0
        assert "T1110" in result["tactic"]["true_positives"]

    def test_no_match(self):
        """No match at any tier."""
        detected = {"T1190"}
        ground_truth = {"T1558.003"}
        result = score_findings_tiered(detected, ground_truth)
        assert result["exact"]["recall"] == 0.0
        assert result["parent"]["recall"] == 0.0
        # T1190 = initial-access, T1558.003 = credential-access → no tactic match
        assert result["tactic"]["recall"] == 0.0

    def test_mixed_tiers(self):
        """Mix of exact, parent, and tactic matches."""
        detected = {"T1558.003", "T1059", "T1110"}
        ground_truth = {"T1558.003", "T1059.004", "T1003.006"}
        result = score_findings_tiered(detected, ground_truth)
        # T1558.003 exact match
        assert "T1558.003" in result["exact"]["true_positives"]
        # T1059 parent-matches T1059.004
        assert "T1059" in result["parent"]["true_positives"]
        # T1110 tactic-matches T1003.006 (both credential-access)
        assert "T1110" in result["tactic"]["true_positives"]
        # Parent tier: at least 2/3 (exact + parent matches)
        assert result["parent"]["recall"] >= 0.667
        # Tactic tier: at least 2/3 (exact + parent, tactic may vary by cache)
        assert result["tactic"]["recall"] >= 0.667
        # Overall recall: at least 2/3 covered
        assert result["overall"]["recall"] >= 0.667

    def test_empty_ground_truth(self):
        """Empty ground truth → all recalls are 0."""
        detected = {"T1558.003"}
        ground_truth: set[str] = set()
        result = score_findings_tiered(detected, ground_truth)
        assert result["exact"]["recall"] == 0.0
        assert result["parent"]["recall"] == 0.0
        assert result["tactic"]["recall"] == 0.0

    def test_empty_detected(self):
        """Empty detected → all recalls are 0, all ground truth is false negative."""
        detected: set[str] = set()
        ground_truth = {"T1558.003", "T1003.006"}
        result = score_findings_tiered(detected, ground_truth)
        assert result["exact"]["recall"] == 0.0
        assert result["overall"]["recall"] == 0.0
        assert sorted(result["overall"]["false_negatives"]) == ["T1003.006", "T1558.003"]

    def test_false_positive_tracking(self):
        """Detected technique not matching any ground truth at any tier."""
        detected = {"T1558.003", "T9999.999"}
        ground_truth = {"T1558.003"}
        result = score_findings_tiered(detected, ground_truth)
        assert "T9999.999" in result["overall"]["false_positives"]
        assert result["exact"]["recall"] == 1.0

    def test_seven_near_misses_revealed(self):
        """The 7 near-misses from the eval: parent tier should score > exact."""
        # Simulating the near-miss pattern: right parent, wrong sub-ID
        detected = {"T1558", "T1059", "T1003"}
        ground_truth = {"T1558.003", "T1059.004", "T1003.006"}
        result = score_findings_tiered(detected, ground_truth)
        # Exact: 0 (none match exactly)
        assert result["exact"]["recall"] == 0.0
        # Parent: 1.0 (all parent-match)
        assert result["parent"]["recall"] == 1.0
        # The parent tier reveals hidden capability
        assert result["parent"]["recall"] > result["exact"]["recall"]

    def test_sibling_confusion(self):
        """Sibling sub-technique confusion: T1558.003 vs T1558.004."""
        detected = {"T1558.003"}
        ground_truth = {"T1558.004"}
        result = score_findings_tiered(detected, ground_truth)
        # Exact: 0 (different sub-technique)
        assert result["exact"]["recall"] == 0.0
        # Parent: 1.0 (same parent T1558)
        assert result["parent"]["recall"] == 1.0
        # Tactic: 1.0 (both credential-access)
        assert result["tactic"]["recall"] == 1.0

    def test_recall_never_exceeds_one(self):
        """Recall should never exceed 1.0 even with multiple detections."""
        detected = {"T1558.003", "T1558.004", "T1558", "T1110"}
        ground_truth = {"T1558.003"}
        result = score_findings_tiered(detected, ground_truth)
        assert result["exact"]["recall"] <= 1.0
        assert result["parent"]["recall"] <= 1.0
        assert result["tactic"]["recall"] <= 1.0
        assert result["overall"]["recall"] <= 1.0
