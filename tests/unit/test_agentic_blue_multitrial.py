"""Unit tests for agentic_blue_eval M2 — multi-trial aggregation.

All tests use only in-memory data; no network, no Docker, no lab.
"""

from __future__ import annotations

import pytest

from tests.benchmarks.bench_security._sweep_driver import (
    _aggregate_trials,
    _classify_cell,
    _mean_stdev,
)

# ── _classify_cell ───────────────────────────────────────────────────────────


class TestClassifyCell:
    def test_all_pass_is_reliable(self):
        assert _classify_cell(3, 3) == "reliable"

    def test_none_pass_is_incapable(self):
        assert _classify_cell(0, 3) == "incapable"

    def test_partial_is_unreliable(self):
        assert _classify_cell(1, 3) == "unreliable"
        assert _classify_cell(2, 3) == "unreliable"

    def test_single_trial_pass(self):
        assert _classify_cell(1, 1) == "reliable"

    def test_single_trial_fail(self):
        assert _classify_cell(0, 1) == "incapable"


# ── _mean_stdev ──────────────────────────────────────────────────────────────


class TestMeanStdev:
    def test_empty(self):
        mean, std = _mean_stdev([])
        assert mean == 0.0
        assert std == 0.0

    def test_single_value(self):
        mean, std = _mean_stdev([0.5])
        assert mean == 0.5
        assert std == 0.0

    def test_identical_values(self):
        mean, std = _mean_stdev([0.3, 0.3, 0.3])
        assert mean == pytest.approx(0.3)
        assert std == 0.0

    def test_varied_values(self):
        mean, std = _mean_stdev([0.0, 0.5, 1.0])
        assert mean == pytest.approx(0.5)
        assert std > 0.0

    def test_known_stdev(self):
        # Values: [0, 1], mean=0.5, variance=0.25, stdev=0.5
        mean, std = _mean_stdev([0.0, 1.0])
        assert mean == pytest.approx(0.5)
        assert std == pytest.approx(0.5)


# ── _aggregate_trials ────────────────────────────────────────────────────────


def _make_trial(arm: str, exact_recall: float, parent_recall: float, tactic_recall: float) -> dict:
    """Helper to build a minimal trial result dict."""
    return {
        "arms": {
            arm: {
                "tiered": {
                    "exact": {"recall": exact_recall},
                    "parent": {"recall": parent_recall},
                    "tactic": {"recall": tactic_recall},
                    "overall": {"recall": tactic_recall},
                },
            }
        }
    }


class TestAggregateTrials:
    def test_single_trial(self):
        """Single trial aggregation."""
        trials = [_make_trial("harness", 0.0, 1.0, 1.0)]
        result = _aggregate_trials(trials)
        assert "harness" in result
        ts = result["harness"]["tiered_summary"]
        assert ts["exact"]["pass_at_k"] == 0
        assert ts["parent"]["pass_at_k"] == 1
        assert ts["exact"]["classification"] == "incapable"
        assert ts["parent"]["classification"] == "reliable"

    def test_three_trials_all_pass(self):
        """All 3 trials pass at parent tier → reliable."""
        trials = [
            _make_trial("harness", 0.0, 1.0, 1.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
        ]
        result = _aggregate_trials(trials)
        ts = result["harness"]["tiered_summary"]
        assert ts["parent"]["pass_at_k"] == 3
        assert ts["parent"]["pass_rate"] == 1.0
        assert ts["parent"]["classification"] == "reliable"
        assert ts["exact"]["classification"] == "incapable"

    def test_three_trials_partial_pass(self):
        """1/3 trials pass at exact tier → unreliable."""
        trials = [
            _make_trial("harness", 1.0, 1.0, 1.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
        ]
        result = _aggregate_trials(trials)
        ts = result["harness"]["tiered_summary"]
        assert ts["exact"]["pass_at_k"] == 1
        assert ts["exact"]["pass_rate"] == pytest.approx(0.333, abs=0.01)
        assert ts["exact"]["classification"] == "unreliable"

    def test_mean_recall(self):
        """Mean recall computed correctly."""
        trials = [
            _make_trial("harness", 0.0, 0.5, 1.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
            _make_trial("harness", 0.0, 0.0, 0.5),
        ]
        result = _aggregate_trials(trials)
        ts = result["harness"]["tiered_summary"]
        assert ts["parent"]["mean_recall"] == pytest.approx(0.5, abs=0.01)
        assert ts["tactic"]["mean_recall"] == pytest.approx(0.833, abs=0.01)

    def test_stdev_computed(self):
        """Stdev is computed for varied recall values."""
        trials = [
            _make_trial("harness", 0.0, 0.0, 0.0),
            _make_trial("harness", 0.0, 1.0, 1.0),
        ]
        result = _aggregate_trials(trials)
        ts = result["harness"]["tiered_summary"]
        assert ts["parent"]["stdev_recall"] == pytest.approx(0.5, abs=0.01)

    def test_per_trial_values(self):
        """Per-trial values are recorded."""
        trials = [
            _make_trial("harness", 0.0, 0.5, 1.0),
            _make_trial("harness", 1.0, 1.0, 1.0),
        ]
        result = _aggregate_trials(trials)
        ts = result["harness"]["tiered_summary"]
        assert ts["exact"]["per_trial"] == [0.0, 1.0]
        assert ts["parent"]["per_trial"] == [0.5, 1.0]

    def test_multiple_arms(self):
        """Multiple arms aggregated independently."""
        trials = [
            {
                "arms": {
                    "raw": {
                        "tiered": {
                            "exact": {"recall": 0.0},
                            "parent": {"recall": 0.0},
                            "tactic": {"recall": 0.0},
                            "overall": {"recall": 0.0},
                        }
                    },
                    "harness": {
                        "tiered": {
                            "exact": {"recall": 0.0},
                            "parent": {"recall": 1.0},
                            "tactic": {"recall": 1.0},
                            "overall": {"recall": 1.0},
                        }
                    },
                }
            }
        ]
        result = _aggregate_trials(trials)
        assert result["raw"]["tiered_summary"]["parent"]["classification"] == "incapable"
        assert result["harness"]["tiered_summary"]["parent"]["classification"] == "reliable"

    def test_empty_trials(self):
        """Empty trial list returns empty dict."""
        assert _aggregate_trials([]) == {}

    def test_trials_count_recorded(self):
        """Trial count is recorded in output."""
        trials = [_make_trial("harness", 0.0, 1.0, 1.0)] * 5
        result = _aggregate_trials(trials)
        assert result["harness"]["trials"] == 5

    def test_last_trial_preserved(self):
        """Last trial detail is preserved for inspection."""
        trials = [
            _make_trial("harness", 0.0, 0.0, 0.0),
            _make_trial("harness", 1.0, 1.0, 1.0),
        ]
        result = _aggregate_trials(trials)
        last = result["harness"]["last_trial"]
        assert last["tiered"]["exact"]["recall"] == 1.0
