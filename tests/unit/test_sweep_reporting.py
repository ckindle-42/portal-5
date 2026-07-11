"""Unit tests for sweep reporting — arm-vs-arm deltas, not misleading single winner.

All tests use only in-memory data; no network, no Docker, no lab.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core._sweep_driver import _compute_arm_deltas


def _make_result(
    scenario: str,
    model: str,
    exact_raw: float = 0.0,
    exact_tools: float = 0.0,
    exact_harness: float = 0.0,
    parent_raw: float = 0.0,
    parent_tools: float = 0.0,
    parent_harness: float = 0.0,
    tactic_raw: float = 0.0,
    tactic_tools: float = 0.0,
    tactic_harness: float = 0.0,
    trials: int = 3,
) -> dict:
    """Build a minimal sweep result dict for testing."""

    def _arm(erm, prm, trm):
        return {
            "tiered_summary": {
                "exact": {
                    "mean_recall": erm,
                    "pass_at_k": int(erm > 0),
                    "classification": "reliable" if erm > 0 else "incapable",
                },
                "parent": {
                    "mean_recall": prm,
                    "pass_at_k": int(prm > 0),
                    "classification": "reliable" if prm > 0 else "incapable",
                },
                "tactic": {
                    "mean_recall": trm,
                    "pass_at_k": int(trm > 0),
                    "classification": "reliable" if trm > 0 else "incapable",
                },
            }
        }

    return {
        "scenario": scenario,
        "model": model,
        "_trials": trials,
        "arms": {
            "raw": _arm(exact_raw, parent_raw, tactic_raw),
            "tools": _arm(exact_tools, parent_tools, tactic_tools),
            "harness": _arm(exact_harness, parent_harness, tactic_harness),
        },
    }


class TestComputeArmDeltas:
    def test_single_model_single_scenario(self):
        results = [
            _make_result(
                "kerberoast",
                "granite",
                exact_raw=0.0,
                exact_harness=0.333,
                parent_raw=0.111,
                parent_harness=0.333,
                tactic_raw=0.222,
                tactic_harness=0.333,
            )
        ]
        deltas = _compute_arm_deltas(results)
        assert "granite" in deltas
        g = deltas["granite"]
        assert g["exact"]["delta_raw"] == pytest.approx(0.333, abs=0.001)
        assert g["parent"]["delta_raw"] == pytest.approx(0.222, abs=0.001)
        assert g["tactic"]["delta_raw"] == pytest.approx(0.111, abs=0.001)

    def test_harness_minus_raw_positive(self):
        """Harness > raw → positive delta."""
        results = [_make_result("s1", "m1", exact_harness=0.5, exact_raw=0.1)]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_raw"] == pytest.approx(0.4, abs=0.001)

    def test_harness_minus_raw_negative(self):
        """Harness < raw → negative delta (red flag)."""
        results = [_make_result("s1", "m1", exact_harness=0.1, exact_raw=0.5)]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_raw"] == pytest.approx(-0.4, abs=0.001)

    def test_harness_minus_tools(self):
        """Harness vs tools delta computed correctly."""
        results = [_make_result("s1", "m1", exact_harness=0.6, exact_tools=0.2)]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_tools"] == pytest.approx(0.4, abs=0.001)

    def test_averages_across_scenarios(self):
        """Multiple scenarios are averaged."""
        results = [
            _make_result("s1", "m1", exact_harness=0.6, exact_raw=0.2),
            _make_result("s2", "m1", exact_harness=0.4, exact_raw=0.0),
        ]
        deltas = _compute_arm_deltas(results)
        # avg harness = (0.6 + 0.4) / 2 = 0.5
        # avg raw = (0.2 + 0.0) / 2 = 0.1
        # delta = 0.5 - 0.1 = 0.4
        assert deltas["m1"]["exact"]["harness"] == pytest.approx(0.5, abs=0.001)
        assert deltas["m1"]["exact"]["raw"] == pytest.approx(0.1, abs=0.001)
        assert deltas["m1"]["exact"]["delta_raw"] == pytest.approx(0.4, abs=0.001)

    def test_multiple_models(self):
        """Each model computed independently."""
        results = [
            _make_result("s1", "m1", exact_harness=0.5, exact_raw=0.1),
            _make_result("s1", "m2", exact_harness=0.3, exact_raw=0.3),
        ]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_raw"] == pytest.approx(0.4, abs=0.001)
        assert deltas["m2"]["exact"]["delta_raw"] == pytest.approx(0.0, abs=0.001)

    def test_empty_results(self):
        assert _compute_arm_deltas([]) == {}

    def test_all_tiers_computed(self):
        """All three tiers have deltas computed."""
        results = [
            _make_result(
                "s1",
                "m1",
                exact_harness=0.5,
                exact_raw=0.1,
                parent_harness=0.6,
                parent_raw=0.2,
                tactic_harness=0.7,
                tactic_raw=0.3,
            )
        ]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_raw"] == pytest.approx(0.4, abs=0.001)
        assert deltas["m1"]["parent"]["delta_raw"] == pytest.approx(0.4, abs=0.001)
        assert deltas["m1"]["tactic"]["delta_raw"] == pytest.approx(0.4, abs=0.001)

    def test_seat_config_from_harness_only(self):
        """Seat config selection must use harness arm, not raw."""
        results = [
            _make_result(
                "s1",
                "m1",
                exact_raw=0.9,
                exact_harness=0.3,
                parent_raw=0.9,
                parent_harness=0.3,
                tactic_raw=0.9,
                tactic_harness=0.3,
            )
        ]
        deltas = _compute_arm_deltas(results)
        # Even though raw=0.9 > harness=0.3, the harness values are what matter for seat
        h_score = (
            deltas["m1"]["exact"]["harness"] * 2.0
            + deltas["m1"]["parent"]["harness"] * 1.5
            + deltas["m1"]["tactic"]["harness"] * 1.0
        )
        raw_score = (
            deltas["m1"]["exact"]["raw"] * 2.0
            + deltas["m1"]["parent"]["raw"] * 1.5
            + deltas["m1"]["tactic"]["raw"] * 1.0
        )
        # raw_score > h_score, but seat must still come from harness
        assert raw_score > h_score
        # The delta is negative → red flag
        assert deltas["m1"]["exact"]["delta_raw"] < 0

    def test_red_flag_negative_delta(self):
        """Negative delta is detectable as a red flag."""
        results = [_make_result("s1", "m1", exact_harness=0.1, exact_raw=0.5)]
        deltas = _compute_arm_deltas(results)
        assert deltas["m1"]["exact"]["delta_raw"] < 0
