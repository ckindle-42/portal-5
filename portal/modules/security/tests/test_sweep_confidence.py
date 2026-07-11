"""Unit tests for sweep confidence — bootstrap CI and verdict logic.

All tests use only in-memory data; no network, no Docker, no lab.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core._sweep_driver import (
    _bootstrap_ci,
    _compute_arm_deltas,
    _verdict_from_ci,
)

# ── _bootstrap_ci ────────────────────────────────────────────────────────────


class TestBootstrapCi:
    def test_single_value(self):
        """Single value → CI is the value itself."""
        lo, hi = _bootstrap_ci([0.5])
        assert lo == pytest.approx(0.5, abs=0.001)
        assert hi == pytest.approx(0.5, abs=0.001)

    def test_empty(self):
        lo, hi = _bootstrap_ci([])
        assert lo == 0.0
        assert hi == 0.0

    def test_identical_values(self):
        """Identical values → CI is the value."""
        lo, hi = _bootstrap_ci([0.3, 0.3, 0.3, 0.3, 0.3])
        assert lo == pytest.approx(0.3, abs=0.001)
        assert hi == pytest.approx(0.3, abs=0.001)

    def test_ci_excludes_zero_positive(self):
        """All positive deltas → CI should exclude 0."""
        lo, hi = _bootstrap_ci([0.2, 0.3, 0.25, 0.35, 0.28, 0.32, 0.22, 0.38])
        assert lo > 0, f"CI lower bound {lo} should be > 0"

    def test_ci_excludes_zero_negative(self):
        """All negative deltas → CI should exclude 0."""
        lo, hi = _bootstrap_ci([-0.2, -0.3, -0.25, -0.35, -0.28, -0.32, -0.22, -0.38])
        assert hi < 0, f"CI upper bound {hi} should be < 0"

    def test_ci_crosses_zero(self):
        """Mixed positive/negative deltas → CI should cross 0."""
        lo, hi = _bootstrap_ci([0.3, -0.3, 0.2, -0.2, 0.1, -0.1, 0.05, -0.05])
        assert lo < 0 < hi, f"CI [{lo}, {hi}] should cross 0"

    def test_ci_width_decreases_with_more_samples(self):
        """More samples → tighter CI (on average)."""
        import random

        random.seed(42)
        small = [random.gauss(0.2, 0.1) for _ in range(5)]
        large = [random.gauss(0.2, 0.1) for _ in range(50)]
        lo_s, hi_s = _bootstrap_ci(small)
        lo_l, hi_l = _bootstrap_ci(large)
        width_small = hi_s - lo_s
        width_large = hi_l - lo_l
        assert width_large < width_small

    def test_confidence_level(self):
        """Higher confidence → wider CI."""
        deltas = [0.1, 0.2, 0.15, 0.25, 0.18, 0.22, 0.12, 0.28]
        lo_90, hi_90 = _bootstrap_ci(deltas, confidence=0.90)
        lo_99, hi_99 = _bootstrap_ci(deltas, confidence=0.99)
        assert (hi_99 - lo_99) > (hi_90 - lo_90)


# ── _verdict_from_ci ─────────────────────────────────────────────────────────


class TestVerdictFromCi:
    def test_significant_win(self):
        assert _verdict_from_ci(0.01, 0.10) == "SIGNIFICANT-WIN"
        assert _verdict_from_ci(0.001, 0.5) == "SIGNIFICANT-WIN"

    def test_significant_regression(self):
        assert _verdict_from_ci(-0.10, -0.01) == "SIGNIFICANT-REGRESSION"
        assert _verdict_from_ci(-0.5, -0.001) == "SIGNIFICANT-REGRESSION"

    def test_inconclusive_crosses_zero(self):
        assert _verdict_from_ci(-0.05, 0.05) == "INCONCLUSIVE"
        assert _verdict_from_ci(-0.1, 0.1) == "INCONCLUSIVE"

    def test_inconclusive_touches_zero(self):
        """CI touches 0 but doesn't exclude it."""
        assert _verdict_from_ci(0.0, 0.1) == "INCONCLUSIVE"
        assert _verdict_from_ci(-0.1, 0.0) == "INCONCLUSIVE"


# ── _compute_arm_deltas with CI ──────────────────────────────────────────────


def _make_result(scenario, model, raw_r=0.0, harness_r=0.0, tools_r=0.0, trials=3):
    def _arm(r):
        return {
            "tiered_summary": {
                "exact": {"mean_recall": r, "pass_at_k": int(r > 0)},
                "parent": {"mean_recall": r, "pass_at_k": int(r > 0)},
                "tactic": {"mean_recall": r, "pass_at_k": int(r > 0)},
            }
        }

    return {
        "scenario": scenario,
        "model": model,
        "_trials": trials,
        "arms": {
            "raw": _arm(raw_r),
            "tools": _arm(tools_r),
            "harness": _arm(harness_r),
        },
    }


class TestComputeArmDeltasWithCi:
    def test_paired_deltas_present(self):
        """_compute_arm_deltas now returns paired_deltas for bootstrap."""
        results = [
            _make_result("s1", "m1", raw_r=0.1, harness_r=0.3),
            _make_result("s2", "m1", raw_r=0.2, harness_r=0.5),
        ]
        deltas = _compute_arm_deltas(results)
        pd = deltas["m1"]["exact"]["paired_deltas"]
        assert len(pd) == 2
        assert pd[0] == pytest.approx(0.2, abs=0.001)
        assert pd[1] == pytest.approx(0.3, abs=0.001)

    def test_paired_deltas_negative(self):
        """Negative paired deltas when harness < raw."""
        results = [
            _make_result("s1", "m1", raw_r=0.5, harness_r=0.1),
        ]
        deltas = _compute_arm_deltas(results)
        pd = deltas["m1"]["exact"]["paired_deltas"]
        assert pd[0] == pytest.approx(-0.4, abs=0.001)

    def test_vals_lists_present(self):
        """raw_vals, harness_vals, tools_vals are in the output."""
        results = [_make_result("s1", "m1", raw_r=0.1, harness_r=0.3, tools_r=0.05)]
        deltas = _compute_arm_deltas(results)
        assert "raw_vals" in deltas["m1"]["exact"]
        assert "harness_vals" in deltas["m1"]["exact"]
        assert "tools_vals" in deltas["m1"]["exact"]
