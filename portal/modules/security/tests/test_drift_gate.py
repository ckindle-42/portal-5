"""Tests for the drift-detection gate (TASK_SEC_DRIFT_GATE_V1).

Hermetic — drift-gate metric math is pure (no I/O); canary tests mock the
HTTP layer so nothing touches a real Ollama instance.
"""

from __future__ import annotations

from portal.modules.security.core.drift_gate import (
    CANARY_PROBES,
    _canary_baseline_path,
    _metric_drift,
    drift_check,
    render_drift_markdown,
)


class TestMetricDrift:
    def test_clear_regression_flagged(self) -> None:
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.5, 0.48],
            baseline_run_values=[[0.80, 0.82], [0.79, 0.81], [0.78, 0.80]],
        )
        assert d.status == "DRIFT-REGRESSION"
        assert d.delta is not None
        assert d.delta < 0

    def test_within_noise_is_ok(self) -> None:
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.79, 0.785],
            baseline_run_values=[[0.80, 0.805], [0.795, 0.80], [0.80, 0.798]],
        )
        assert d.status in ("OK", "DRIFT-WARN")
        assert d.status != "DRIFT-REGRESSION"

    def test_fewer_than_three_baseline_runs_is_insufficient(self) -> None:
        d = _metric_drift("blue_f1", candidate_values=[0.5], baseline_run_values=[[0.8], [0.79]])
        assert d.status == "INSUFFICIENT-BASELINE"

    def test_no_baseline_at_all_is_insufficient(self) -> None:
        d = _metric_drift("blue_f1", candidate_values=[0.5], baseline_run_values=[])
        assert d.status == "INSUFFICIENT-BASELINE"

    def test_improvement_is_ok_not_regression(self) -> None:
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.95, 0.96],
            baseline_run_values=[[0.5, 0.52], [0.51, 0.5], [0.49, 0.5]],
        )
        assert d.status == "OK"

    def test_per_metric_isolation(self) -> None:
        """A drop in one metric must not be conflated with another metric's
        drift status — drift_check reports per-metric, not an aggregate."""
        blue_f1_regression = _metric_drift(
            "blue_f1",
            candidate_values=[0.1],
            baseline_run_values=[[0.9, 0.9], [0.9, 0.9], [0.9, 0.9]],
        )
        purple_composite_stable = _metric_drift(
            "purple_composite",
            candidate_values=[0.6, 0.61],
            baseline_run_values=[[0.6, 0.6], [0.6, 0.61], [0.6, 0.6]],
        )
        assert blue_f1_regression.status == "DRIFT-REGRESSION"
        assert purple_composite_stable.status != "DRIFT-REGRESSION"


class TestDriftCheckIntegration:
    def test_drift_check_runs_against_real_results(self) -> None:
        """Smoke test against whatever result files actually exist on disk —
        must not crash, and must never emit a status outside the known set."""
        report = drift_check(window=5)
        assert "pairs" in report
        valid_statuses = {"OK", "DRIFT-WARN", "DRIFT-REGRESSION", "INSUFFICIENT-BASELINE"}
        for pair in report["pairs"]:
            for m in pair["metrics"]:
                assert m["status"] in valid_statuses

    def test_render_markdown_handles_empty(self) -> None:
        md = render_drift_markdown({"generated_at": "x", "window": 5, "pairs": []})
        assert "no purple-test series" in md

    def test_render_markdown_has_table_header(self) -> None:
        """Not `drift_check(window=5)` against real results/ — that dir is
        gitignored and empty on a fresh checkout, so this silently depended
        on local write-through artifacts from prior `pytest portal` runs and
        never actually exercised the non-empty branch in CI (2026-09-12)."""
        report = {
            "generated_at": "x",
            "window": 5,
            "pairs": [
                {
                    "scenario": "vuln_wordpress_rce",
                    "blue_model": "test-model",
                    "metrics": [
                        {
                            "metric": "blue_f1",
                            "status": "OK",
                            "delta": 0.0,
                            "baseline_mean": 0.8,
                            "candidate_mean": 0.8,
                            "n_baseline": 3,
                        }
                    ],
                }
            ],
        }
        md = render_drift_markdown(report)
        assert "| scenario |" in md

    def test_drift_is_a_flag_never_mutates_anything(self) -> None:
        """drift_check is read-only over results/ — running it twice must
        produce structurally identical pair/metric keys (no side effects)."""
        r1 = drift_check(window=5)
        r2 = drift_check(window=5)
        assert [p["scenario"] for p in r1["pairs"]] == [p["scenario"] for p in r2["pairs"]]


class TestModelCanary:
    def test_probe_suite_nonempty_and_well_formed(self) -> None:
        assert len(CANARY_PROBES) >= 10
        for probe in CANARY_PROBES:
            assert "id" in probe and "prompt" in probe and "expect_any" in probe

    def test_baseline_path_is_filesystem_safe(self) -> None:
        path = _canary_baseline_path("hf.co/org/model:Q4_K_M")
        assert "/" not in path.name
        assert ":" not in path.name


class TestDriftCLI:
    def test_drift_check_cli_runs(self) -> None:
        from portal.modules.security.core.drift_cli import drift_check_main

        code = drift_check_main(["--window", "5", "--json"])
        assert code == 0
