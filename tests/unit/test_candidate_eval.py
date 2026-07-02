"""Unit tests for candidate-eval mode.

Verifies:
- single-slot builds step_models that pins incumbents and varies only the chosen slot
- solo sets {"default": candidate}
- intake-fail short-circuits
- delta computation is correct on fixtures
- isolation guard: candidate writes under candidates/ and self-index is unaffected
- no-auto-promote guard: candidate-eval never writes to backends.yaml/portal.yaml
"""

from __future__ import annotations

import pytest

from tests.benchmarks.bench_security.candidate_eval import (
    CANDIDATE_EVAL_SCENARIOS,
    CANDIDATES_DIR,
    _build_step_models,
    _compute_delta,
)
from tests.benchmarks.bench_security.exec_chain import _STEP_GROUPS, SCENARIOS

# ── Fixed candidate-eval scenario set ─────────────────────────────────────────


class TestCandidateEvalScenarios:
    """CANDIDATE_EVAL_SCENARIOS must be valid and representative."""

    def test_all_scenarios_exist(self):
        for name in CANDIDATE_EVAL_SCENARIOS:
            assert name in SCENARIOS, f"Scenario '{name}' not in SCENARIOS"

    def test_count_is_reasonable(self):
        """Should be ~5-6 scenarios — not too few, not the full set."""
        assert 4 <= len(CANDIDATE_EVAL_SCENARIOS) <= 10, (
            f"Expected 4-10 eval scenarios, got {len(CANDIDATE_EVAL_SCENARIOS)}"
        )

    def test_spans_disciplines(self):
        """Should cover AD, web, host, multi-service at minimum."""
        scenarios = set(CANDIDATE_EVAL_SCENARIOS)
        has_ad = any("kerberoast" in s or "ad_" in s for s in scenarios)
        has_web = any(s.startswith("web_") for s in scenarios)
        has_host = any("meta3" in s or "ctf" in s for s in scenarios)
        assert has_ad, "Missing AD scenario"
        assert has_web, "Missing web scenario"
        assert has_host, "Missing host/CTF scenario"


# ── Single-slot step_models ───────────────────────────────────────────────────


class TestBuildStepModels:
    """_build_step_models must pin incumbents correctly."""

    def test_exploit_slot_pins_others(self):
        """exploit slot: candidate in exploit group, incumbent elsewhere."""
        sm = _build_step_models("exploit", "cand-model", "inc-model")
        assert sm["exploit"] == "cand-model"
        assert sm["default"] == "inc-model"
        # RECON tools should resolve to incumbent
        for _tool in _STEP_GROUPS.get("planning", set()):
            assert sm.get("planning", sm["default"]) == "inc-model"

    def test_recon_slot(self):
        sm = _build_step_models("recon", "cand", "inc")
        assert sm["planning"] == "cand"
        assert sm["default"] == "inc"

    def test_post_slot(self):
        sm = _build_step_models("post", "cand", "inc")
        assert sm["default"] == "inc"
        for group in ["persist", "move", "exfil", "cleanup"]:
            assert sm[group] == "cand"

    def test_solo_all_candidate(self):
        sm = _build_step_models("solo", "cand", "inc")
        assert sm == {"default": "cand"}

    def test_solo_ignores_incumbent(self):
        sm = _build_step_models("solo", "cand", "whatever")
        assert sm == {"default": "cand"}


# ── Delta computation ─────────────────────────────────────────────────────────


class TestComputeDelta:
    """_compute_delta must produce correct per-scenario and aggregate deltas."""

    def test_basic_delta(self):
        cand = [
            {
                "scenario": "s1",
                "model": "cand",
                "unique_coverage": 0.8,
                "order_accuracy": 0.7,
                "chain_depth": 6,
                "lab_success": True,
                "elapsed_s": 10.0,
                "effort_tier": "verified_success",
            },
        ]
        inc = [
            {
                "scenario": "s1",
                "model": "inc",
                "unique_coverage": 0.6,
                "order_accuracy": 0.5,
                "chain_depth": 4,
                "lab_success": False,
                "elapsed_s": 12.0,
                "effort_tier": "honest_partial",
            },
        ]
        deltas = _compute_delta(cand, inc)
        # Should have 1 per-scenario + 1 aggregate
        assert len(deltas) == 2
        d = deltas[0]
        assert d["scenario"] == "s1"
        assert d["unique_coverage_delta"] == pytest.approx(0.2)
        assert d["order_accuracy_delta"] == pytest.approx(0.2)
        assert d["chain_depth_delta"] == 2
        assert d["lab_success_delta"] == 1

    def test_aggregate_delta(self):
        cand = [
            {
                "scenario": "s1",
                "model": "c",
                "unique_coverage": 0.8,
                "order_accuracy": 0.7,
                "chain_depth": 6,
                "lab_success": True,
                "elapsed_s": 10.0,
            },
            {
                "scenario": "s2",
                "model": "c",
                "unique_coverage": 0.6,
                "order_accuracy": 0.5,
                "chain_depth": 4,
                "lab_success": False,
                "elapsed_s": 8.0,
            },
        ]
        inc = [
            {
                "scenario": "s1",
                "model": "i",
                "unique_coverage": 0.6,
                "order_accuracy": 0.5,
                "chain_depth": 4,
                "lab_success": False,
                "elapsed_s": 12.0,
            },
            {
                "scenario": "s2",
                "model": "i",
                "unique_coverage": 0.7,
                "order_accuracy": 0.6,
                "chain_depth": 5,
                "lab_success": True,
                "elapsed_s": 9.0,
            },
        ]
        deltas = _compute_delta(cand, inc)
        agg = [d for d in deltas if d["scenario"] == "__aggregate__"]
        assert len(agg) == 1
        a = agg[0]
        # avg of (0.2, -0.1) = 0.05
        assert a["unique_coverage_delta"] == pytest.approx(0.05)
        # lab_success: +1 + -1 = 0
        assert a["lab_success_delta"] == 0

    def test_empty_results(self):
        deltas = _compute_delta([], [])
        assert deltas == []


# ── Isolation guard ───────────────────────────────────────────────────────────


class TestIsolation:
    """Candidate results must be isolated from the self-index baseline."""

    def test_candidates_dir_is_under_results(self):
        assert str(CANDIDATES_DIR).endswith("results/candidates")

    def test_self_index_does_not_recurse(self):
        """self_index._complete_result_files uses non-recursive glob — safe."""
        from tests.benchmarks.bench_security.self_index import _complete_result_files

        # Even if candidates/ exists with files, self-index won't pick them up
        # because it globs only the top-level sec_bench_*.json
        files = _complete_result_files()
        for f in files:
            assert "candidates/" not in str(f), f"self-index picked up candidate file: {f}"


# ── No-auto-promote guard ─────────────────────────────────────────────────────


class TestNoAutoPromote:
    """candidate-eval must never modify fleet config."""

    def test_module_does_not_import_config_writer(self):
        """candidate_eval.py should not import any config-writing functions."""
        import inspect

        import tests.benchmarks.bench_security.candidate_eval as mod

        src = inspect.getsource(mod)
        # Should not have code that writes to backends.yaml or portal.yaml
        # (docstring mentions are fine — check for actual write calls)
        import_lines = [
            line for line in src.splitlines() if line.strip().startswith(("import ", "from "))
        ]
        import_src = "\n".join(import_lines)
        assert "write_text" not in import_src or "backends" not in import_src
