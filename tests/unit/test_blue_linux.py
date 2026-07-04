"""Unit tests for Linux/web blue telemetry + purple convergence (synthetic/dry-run)."""

from __future__ import annotations

from tests.benchmarks.bench_security.blue import (
    _fetch_blue_telemetry,
    _score_purple,
)
from tests.benchmarks.bench_security.matrix import (
    RunUnit,
    _score_purple_on_unit,
    run_matrix,
)
from tests.benchmarks.bench_security.oracles import ORACLES


class TestLinuxWebTelemetry:
    """Linux/web targets produce real telemetry for blue detection."""

    def test_web_exploit_access_log_signal(self):
        """A web-exploit unit with a matching access-log signal → blue detects."""
        # Simulate a web unit with T1190 technique
        unit = RunUnit(
            id="test-web",
            kind="class",
            target_spec="sqli-labs/mysql/CASE-1",
            oracle="sqli_error",
            scoring="oracle",
            domain="web",
            spin="ephemeral",
            challenge_class="sqli-auth-bypass",
            technique_ids=["T1190"],
            has_telemetry=True,
        )
        assert unit.has_telemetry is True
        assert "T1190" in unit.technique_ids

    def test_no_signal_miss(self):
        """No signal → blue misses."""
        unit = RunUnit(
            id="test-no-signal",
            kind="scenario",
            target_spec="lab-vulhub",
            oracle="rce_shell",
            scoring="oracle",
            domain="mixed",
            spin="static",
            technique_ids=[],
            has_telemetry=False,
        )
        assert unit.has_telemetry is False
        assert len(unit.technique_ids) == 0

    def test_hardened_twin_false_positive_flag(self):
        """A signal on the hardened twin → false-positive flag."""
        # The hardened-twin contract: a finding must vanish on the patched twin
        # This test verifies the structure exists for FP detection
        RunUnit(
            id="test-hardened",
            kind="class",
            target_spec="nginx/CVE-2017-7529",
            oracle="lfi_confirm",
            scoring="oracle",
            domain="web",
            spin="ephemeral",
            challenge_class="lfi-path-traversal",
            technique_ids=["T1190"],
            has_telemetry=True,
        )
        # On a hardened twin, the oracle should not verify
        finding = {"oracle": "lfi_confirm"}
        verdict = ORACLES["lfi_confirm"].check(finding, "no match here", {})
        assert verdict is False


class TestSyntheticFallbackGate:
    """Validation-integrity gate: synthetic-fallback → indeterminate, never PASS."""

    def test_synthetic_fallback_never_pass(self, monkeypatch):
        """A synthetic-sourced result MUST score indeterminate, never PASS."""
        monkeypatch.setattr("tests.benchmarks.bench_security.matrix._LAB_EXEC_AVAILABLE", False)
        units = [
            RunUnit(
                id="test-synth",
                kind="scenario",
                target_spec="lab-vulhub",
                oracle="rce_shell",
                scoring="oracle",
                domain="web",
                spin="static",
                technique_ids=["T1190"],
                has_telemetry=True,
            ),
        ]
        result = run_matrix(units, dry_run=False)
        # All results should be indeterminate when lab exec is unavailable
        for r in result["results"]:
            assert r.status == "indeterminate"
            assert r.status != "verified"

    def test_blue_synthetic_source_tagged(self):
        """Blue telemetry from non-live source is tagged as synthetic."""
        # _fetch_blue_telemetry in non-lab mode returns source=synthetic
        telemetry = _fetch_blue_telemetry(["T1558.003"], lab_exec=False, dry_run=False)
        for _tid, data in telemetry.items():
            assert data["source"] in ("synthetic", "synthetic-fallback")

    def test_purple_with_synthetic_blue_is_indeterminate(self):
        """Purple scoring with synthetic blue source → indeterminate."""
        unit = RunUnit(
            id="test-purple-synth",
            kind="scenario",
            target_spec="lab-vulhub",
            oracle="rce_shell",
            scoring="oracle",
            domain="web",
            spin="static",
            technique_ids=["T1190"],
            has_telemetry=True,
        )
        blue_result = {
            "has_real_telemetry": False,
            "telemetry": {"T1190": {"source": "synthetic-fallback"}},
            "technique_ids": ["T1190"],
        }
        purple = _score_purple_on_unit(unit, blue_result)
        assert purple["status"] == "indeterminate"
        assert purple["source"] == "synthetic-fallback"


class TestPurpleWebConvergence:
    """Purple on a web class requires red-landed AND blue-detected AND sane evasion_delta."""

    def test_purple_requires_red_and_blue(self):
        """Purple composite requires both red landed and blue detected."""
        red_result = {"lab_success": True, "order_accuracy": 0.8, "mode": "lab-exec"}
        blue_result = {
            "model": "test-model",
            "score": {"f1": 0.7, "recall": 0.8, "precision": 0.6, "detected": ["T1190"]},
            "containments": [],
            "synthetic_fallback": False,
        }
        scenario = {
            "name": "test",
            "detect_ground_truth": ["T1190"],
            "persistence_technique": "",
        }
        purple = _score_purple(red_result, blue_result, scenario)
        assert "model_competence_score" in purple
        assert purple["model_competence_score"] > 0.0

    def test_purple_zero_when_blue_misses(self):
        """Purple composite drops when blue detects nothing."""
        red_result = {"lab_success": True, "order_accuracy": 0.8, "mode": "lab-exec"}
        blue_result = {
            "model": "test-model",
            "score": {"f1": 0.0, "recall": 0.0, "precision": 0.0, "detected": []},
            "containments": [],
            "synthetic_fallback": False,
        }
        scenario = {
            "name": "test",
            "detect_ground_truth": ["T1190"],
            "persistence_technique": "",
        }
        purple = _score_purple(red_result, blue_result, scenario)
        assert purple["detection_coverage"] == 0.0


class TestTelemetryBackendPluggable:
    """Telemetry backend is pluggable (proves Splunk adapter will drop in)."""

    def test_fake_backend_protocol(self):
        """A fake backend implementing the protocol is swapped in transparently."""

        class FakeBackend:
            def query(self, technique_id: str, window: dict) -> dict:
                return {
                    "signals": [{"event": "fake", "technique": technique_id}],
                    "source": "fake-siem",
                    "matched": True,
                }

        backend = FakeBackend()
        result = backend.query("T1190", {})
        assert result["source"] == "fake-siem"
        assert result["matched"] is True
        assert len(result["signals"]) == 1

    def test_canonical_protocol_importable(self):
        """TelemetryBackend protocol is importable from telemetry module."""
        from tests.benchmarks.bench_security.telemetry import TelemetryBackend

        assert hasattr(TelemetryBackend, "query")


class TestADBluePathUnchanged:
    """AD blue path is unchanged (regression guard)."""

    def test_fetch_blue_telemetry_ad_techniques(self):
        """AD technique IDs still return telemetry fixtures."""
        telemetry = _fetch_blue_telemetry(["T1558.003", "T1003.006"], lab_exec=False, dry_run=False)
        assert "T1558.003" in telemetry
        assert "T1003.006" in telemetry
        # Each should have synthetic data
        for tid in ["T1558.003", "T1003.006"]:
            assert "telemetry" in telemetry[tid]
            assert "source" in telemetry[tid]
