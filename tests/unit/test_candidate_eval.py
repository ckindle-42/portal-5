"""Regression tests for candidate-eval incumbent comparisons."""

import json

from portal.modules.security.core import candidate_eval


def test_solo_auto_resolves_top_level_security_incumbent(monkeypatch):
    seen: list[str] = []

    def fake_get(slot: str) -> str:
        seen.append(slot)
        return "vulnllm-incumbent"

    monkeypatch.setattr(candidate_eval, "_get_incumbent_model", fake_get)

    assert candidate_eval._resolve_incumbent("solo", None) == "vulnllm-incumbent"
    assert seen == ["recon"]


def test_solo_explicit_incumbent_wins(monkeypatch):
    def unexpected_get(slot: str) -> str:
        raise AssertionError(f"unexpected fleet lookup for {slot}")

    monkeypatch.setattr(candidate_eval, "_get_incumbent_model", unexpected_get)

    assert candidate_eval._resolve_incumbent("solo", "explicit-model") == "explicit-model"


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


def test_load_incumbent_results_validates_model(tmp_path):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"incumbent": "model-a", "incumbent_results": [{"x": 1}]}))

    assert candidate_eval._load_incumbent_results(path, "model-a") == [{"x": 1}]

    try:
        candidate_eval._load_incumbent_results(path, "model-b")
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("expected mismatched incumbent capture to fail")
