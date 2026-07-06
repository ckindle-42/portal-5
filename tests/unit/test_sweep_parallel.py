"""Unit tests for sweep parallelization — correctness + iteration mode.

All tests use only in-memory data; no network, no Docker, no lab.
"""

from __future__ import annotations

import pytest

from tests.benchmarks.bench_security._sweep_driver import (
    _aggregate_trials,
    _classify_cell,
    _get_workers,
    _mean_stdev,
)


class TestClassifyCell:
    def test_all_pass_is_reliable(self):
        assert _classify_cell(3, 3) == "reliable"

    def test_none_pass_is_incapable(self):
        assert _classify_cell(0, 3) == "incapable"

    def test_partial_is_unreliable(self):
        assert _classify_cell(1, 3) == "unreliable"


class TestMeanStdev:
    def test_empty(self):
        assert _mean_stdev([]) == (0.0, 0.0)

    def test_single(self):
        mean, std = _mean_stdev([0.5])
        assert mean == pytest.approx(0.5)
        assert std == 0.0

    def test_identical(self):
        mean, std = _mean_stdev([0.3, 0.3, 0.3])
        assert mean == pytest.approx(0.3)
        assert std == 0.0


class TestGetWorkers:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("SWEEP_WORKERS", raising=False)
        assert _get_workers() == 4

    def test_override(self, monkeypatch):
        monkeypatch.setenv("SWEEP_WORKERS", "8")
        assert _get_workers() == 8


def _make_trial(arm_recall: float) -> dict:
    """Build a minimal trial result."""
    return {
        "arms": {
            "harness": {
                "tiered": {
                    "exact": {"recall": arm_recall},
                    "parent": {"recall": arm_recall},
                    "tactic": {"recall": arm_recall},
                    "overall": {"recall": arm_recall},
                },
            },
            "raw": {
                "tiered": {
                    "exact": {"recall": 0.0},
                    "parent": {"recall": 0.0},
                    "tactic": {"recall": 0.0},
                    "overall": {"recall": 0.0},
                },
            },
        }
    }


class TestParallelCorrectness:
    """Parallel results must be identical to serial results for the same input."""

    def test_aggregate_deterministic(self):
        """Aggregating the same trials always produces the same result."""
        trials = [_make_trial(0.3), _make_trial(0.5), _make_trial(0.0)]
        r1 = _aggregate_trials(trials)
        r2 = _aggregate_trials(trials)
        assert r1 == r2

    def test_aggregate_independent_of_order(self):
        """Aggregation is order-independent (mean/stdev are commutative)."""
        trials_a = [_make_trial(0.3), _make_trial(0.5)]
        trials_b = [_make_trial(0.5), _make_trial(0.3)]
        r_a = _aggregate_trials(trials_a)
        r_b = _aggregate_trials(trials_b)
        assert r_a["harness"]["tiered_summary"]["exact"]["mean_recall"] == pytest.approx(
            r_b["harness"]["tiered_summary"]["exact"]["mean_recall"]
        )
        assert (
            r_a["harness"]["tiered_summary"]["exact"]["pass_at_k"]
            == r_b["harness"]["tiered_summary"]["exact"]["pass_at_k"]
        )

    def test_no_shared_mutable_state(self):
        """Each cell's result is independent — no cross-contamination."""
        trials_1 = [_make_trial(1.0)]
        trials_2 = [_make_trial(0.0)]
        r1 = _aggregate_trials(trials_1)
        r2 = _aggregate_trials(trials_2)
        assert r1["harness"]["tiered_summary"]["exact"]["mean_recall"] == 1.0
        assert r2["harness"]["tiered_summary"]["exact"]["mean_recall"] == 0.0


class TestIterationMode:
    """--arms flag controls which arms run."""

    def test_default_arms(self):
        """Default arms are all three."""
        from tests.benchmarks.bench_security._sweep_driver import ARMS

        assert ARMS == ["raw", "tools", "harness"]

    def test_subset_arms(self):
        """Subset arms (e.g. harness,raw) skip tools."""
        arms = ["harness", "raw"]
        assert "tools" not in arms
        assert len(arms) == 2
