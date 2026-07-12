"""Tests for the drift-detection gate (TASK_SEC_DRIFT_GATE_V1).

Hermetic — drift-gate metric math is pure (no I/O); canary tests mock the
HTTP layer so nothing touches a real Ollama instance.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from portal.modules.security.core.drift_gate import (
    CANARY_PROBES,
    _canary_baseline_path,
    _metric_drift,
    check_model_canary,
    drift_check,
    render_drift_markdown,
    run_canary_probe,
    save_canary_baseline,
)


class TestMetricDrift:
    def test_clear_regression_flagged(self):
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.5, 0.48],
            baseline_run_values=[[0.80, 0.82], [0.79, 0.81], [0.78, 0.80]],
        )
        assert d.status == "DRIFT-REGRESSION"
        assert d.delta is not None
        assert d.delta < 0

    def test_within_noise_is_ok(self):
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.79, 0.785],
            baseline_run_values=[[0.80, 0.805], [0.795, 0.80], [0.80, 0.798]],
        )
        assert d.status in ("OK", "DRIFT-WARN")
        assert d.status != "DRIFT-REGRESSION"

    def test_fewer_than_three_baseline_runs_is_insufficient(self):
        d = _metric_drift("blue_f1", candidate_values=[0.5], baseline_run_values=[[0.8], [0.79]])
        assert d.status == "INSUFFICIENT-BASELINE"

    def test_no_baseline_at_all_is_insufficient(self):
        d = _metric_drift("blue_f1", candidate_values=[0.5], baseline_run_values=[])
        assert d.status == "INSUFFICIENT-BASELINE"

    def test_improvement_is_ok_not_regression(self):
        d = _metric_drift(
            "blue_f1",
            candidate_values=[0.95, 0.96],
            baseline_run_values=[[0.5, 0.52], [0.51, 0.5], [0.49, 0.5]],
        )
        assert d.status == "OK"

    def test_per_metric_isolation(self):
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
    def test_drift_check_runs_against_real_results(self):
        """Smoke test against whatever result files actually exist on disk —
        must not crash, and must never emit a status outside the known set."""
        report = drift_check(window=5)
        assert "pairs" in report
        valid_statuses = {"OK", "DRIFT-WARN", "DRIFT-REGRESSION", "INSUFFICIENT-BASELINE"}
        for pair in report["pairs"]:
            for m in pair["metrics"]:
                assert m["status"] in valid_statuses

    def test_render_markdown_handles_empty(self):
        md = render_drift_markdown({"generated_at": "x", "window": 5, "pairs": []})
        assert "no purple-test series" in md

    def test_render_markdown_has_table_header(self):
        report = drift_check(window=5)
        md = render_drift_markdown(report)
        assert "| scenario |" in md

    def test_drift_is_a_flag_never_mutates_anything(self):
        """drift_check is read-only over results/ — running it twice must
        produce structurally identical pair/metric keys (no side effects)."""
        r1 = drift_check(window=5)
        r2 = drift_check(window=5)
        assert [p["scenario"] for p in r1["pairs"]] == [p["scenario"] for p in r2["pairs"]]


class TestModelCanary:
    def test_probe_suite_nonempty_and_well_formed(self):
        assert len(CANARY_PROBES) >= 10
        for probe in CANARY_PROBES:
            assert "id" in probe and "prompt" in probe and "expect_any" in probe

    def test_run_canary_probe_mocked(self):
        with patch("httpx.post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {
                "message": {
                    "content": "T1558.003 is the answer, CVE-2021-44228 also, A03, T1611, T1047, CVE-2017-0144, A10, T1557.001, T1550.002, T1558.004, T1558.001"
                }
            }
            result = run_canary_probe("fake-model")
        assert result["total"] == len(CANARY_PROBES)
        assert result["pass_count"] >= 1

    def test_flipped_probe_detected(self, tmp_path):
        model = "canary-test-model"
        with patch(
            "portal.modules.security.core.drift_gate._canary_baseline_path",
            return_value=tmp_path / "baseline.json",
        ):
            with patch("httpx.post") as mock_post:
                mock_post.return_value.raise_for_status = lambda: None
                # Baseline: all probes pass (echo every expected string).
                all_expected = " ".join(e for p in CANARY_PROBES for e in p["expect_any"])
                mock_post.return_value.json.return_value = {"message": {"content": all_expected}}
                save_canary_baseline(model)

            with patch("httpx.post") as mock_post:
                mock_post.return_value.raise_for_status = lambda: None
                # Candidate: blank response — every probe with an expectation now fails.
                mock_post.return_value.json.return_value = {"message": {"content": ""}}
                result = check_model_canary(model)

        assert result["status"] in ("LOW", "MEDIUM", "HIGH")
        assert len(result["flipped"]) > 0

    def test_identical_behavior_is_none(self, tmp_path):
        model = "canary-stable-model"
        fixed_content = "T1558.003 CVE-2021-44228 A03 T1611 T1047 CVE-2017-0144 A10 T1557.001 T1550.002 T1558.004 T1558.001"
        with (
            patch(
                "portal.modules.security.core.drift_gate._canary_baseline_path",
                return_value=tmp_path / "baseline.json",
            ),
            patch("httpx.post") as mock_post,
        ):
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"message": {"content": fixed_content}}
            save_canary_baseline(model)
            result = check_model_canary(model)

        assert result["status"] == "NONE"
        assert result["flipped"] == []

    def test_no_baseline_reports_no_baseline_status(self, tmp_path):
        with patch(
            "portal.modules.security.core.drift_gate._canary_baseline_path",
            return_value=tmp_path / "does-not-exist.json",
        ):
            result = check_model_canary("never-baselined-model")
        assert result["status"] == "NO-BASELINE"

    def test_baseline_path_is_filesystem_safe(self):
        path = _canary_baseline_path("hf.co/org/model:Q4_K_M")
        assert "/" not in path.name
        assert ":" not in path.name


class TestDriftCLI:
    def test_drift_check_cli_runs(self):
        from portal.modules.security.core.drift_cli import drift_check_main

        code = drift_check_main(["--window", "5", "--json"])
        assert code == 0

    def test_drift_check_json_is_parseable(self, capsys):
        from portal.modules.security.core.drift_cli import drift_check_main

        drift_check_main(["--window", "5", "--json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "pairs" in parsed
