"""Regression tests for candidate-eval incumbent comparisons."""

from portal.modules.security.core import candidate_eval


def test_delta_excludes_indeterminate_scenario():
    candidate = [
        {"scenario": "ready", "unique_coverage": 0.5, "order_accuracy": 1.0},
        {"scenario": "blocked", "outcome": "indeterminate"},
    ]
    incumbent = [
        {"scenario": "ready", "unique_coverage": 0.25, "order_accuracy": 1.0},
        {"scenario": "blocked", "unique_coverage": 1.0, "order_accuracy": 1.0},
    ]

    deltas = candidate_eval._compute_delta(candidate, incumbent)

    assert [row["scenario"] for row in deltas] == ["ready", "__aggregate__"]
    assert deltas[-1]["unique_coverage_delta"] == 0.25
