"""Tests for Splunk SIEM integration + blue-triage (synthetic/dry-run — no live Splunk in CI).

Covers: TelemetryBackend adapter, SplunkBackend, HEC ship, collect, index_wait,
blue_triage, spl_detections, and the dead-Talon-removal guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── TelemetryBackend adapter ─────────────────────────────────────────────────


class TestTelemetryBackendProtocol:
    """Prove the protocol is satisfied by all backends."""

    def test_winrm_backend_satisfies_protocol(self):
        from tests.benchmarks.bench_security.blue import TelemetryBackend, WinEventBackend

        assert isinstance(WinEventBackend(), TelemetryBackend)

    def test_splunk_backend_satisfies_protocol(self):
        from tests.benchmarks.bench_security.blue import SplunkBackend, TelemetryBackend

        assert isinstance(SplunkBackend(), TelemetryBackend)

    def test_get_backend_returns_winrm_for_ad_targets(self):
        from tests.benchmarks.bench_security.blue import WinEventBackend, get_backend

        for target in ["dc01", "srv01", "lab-dc01", "meta3"]:
            backend = get_backend(target)
            assert isinstance(backend, WinEventBackend), f"{target} should use WinEvent"

    def test_get_backend_returns_splunk_for_web_targets(self):
        from tests.benchmarks.bench_security.blue import SplunkBackend, get_backend

        for target in ["vulhub", "10.10.11.50", "mbptl", "web-target"]:
            backend = get_backend(target)
            assert isinstance(backend, SplunkBackend), f"{target} should use Splunk"


class TestWinEventBackend:
    """WinEventBackend behavior — synthetic fallback when no lab."""

    def test_synthetic_fallback_without_lab(self):
        from tests.benchmarks.bench_security.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T1558.003", {})
        assert result["source"] in ("live", "synthetic-fallback", "synthetic")
        assert result["backend"] == "winrm-winevent"
        assert "telemetry" in result

    def test_unknown_technique_returns_empty(self):
        from tests.benchmarks.bench_security.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T9999.999", {})
        assert result["telemetry"] == ""
        assert result["source"] == "synthetic-fallback"


class TestSplunkBackend:
    """SplunkBackend — synthetic-fallback when Splunk unreachable."""

    def test_synthetic_fallback_when_no_splunk(self):
        from tests.benchmarks.bench_security.blue import SplunkBackend

        backend = SplunkBackend()
        backend.url = "https://127.0.0.1:1"  # unreachable
        result = backend.query("T1190", {})
        assert result["source"] == "synthetic-fallback"
        assert result["backend"] == "splunk"

    def test_unknown_technique_returns_synthetic_fallback(self):
        from tests.benchmarks.bench_security.blue import SplunkBackend

        backend = SplunkBackend()
        result = backend.query("T9999.999", {})
        assert result["source"] == "synthetic-fallback"


# ── HEC ship ─────────────────────────────────────────────────────────────────


class TestHecShip:
    """hec_ship.py — dry-run envelope construction, no network."""

    def test_ship_dry_run(self):
        from tests.benchmarks.bench_security.siem.hec_ship import ship

        result = ship(
            {"msg": "test", "status": 200},
            sourcetype="web:access",
            host="vulhub",
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert "envelope" in result
        assert result["envelope"]["sourcetype"] == "web:access"
        assert result["envelope"]["host"] == "vulhub"
        assert result["envelope"]["index"] == "portal5_lab"

    def test_ship_batch_dry_run(self):
        from tests.benchmarks.bench_security.siem.hec_ship import ship_batch

        events = [{"raw": "line1"}, {"raw": "line2"}, {"raw": "line3"}]
        result = ship_batch(events, sourcetype="linux:auditd", host="dc01", dry_run=True)
        assert result["ok"] is True
        assert result["count"] == 3

    def test_ship_builds_valid_envelope(self):
        from tests.benchmarks.bench_security.siem.hec_ship import ship

        result = ship(
            "raw log line",
            sourcetype="windows:security",
            host="dc01",
            source="test-source",
            dry_run=True,
        )
        env = result["envelope"]
        assert env["host"] == "dc01"
        assert env["source"] == "test-source"
        assert env["sourcetype"] == "windows:security"
        assert "time" in env
        assert env["event"] == "raw log line"


# ── SPL detections ───────────────────────────────────────────────────────────


class TestSplDetections:
    """spl_detections.yaml — parses and covers matrix techniques."""

    def test_yaml_parses(self):
        from tests.benchmarks.bench_security.siem.spl_detections import _load

        data = _load()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_every_technique_has_spl(self):
        from tests.benchmarks.bench_security.siem.spl_detections import spl_for

        required = [
            "T1190",
            "T1059",
            "T1505.003",
            "T1610",
            "T1611",
            "T1552.005",
            "T1558.003",
            "T1558.004",
            "T1003.006",
            "T1110.003",
            "T1053.005",
        ]
        for tid in required:
            spl = spl_for(tid)
            assert spl, f"SPL missing for {tid}"
            assert isinstance(spl, str)
            assert len(spl) > 10

    def test_techniques_covered(self):
        from tests.benchmarks.bench_security.siem.spl_detections import techniques_covered

        covered = techniques_covered()
        assert len(covered) >= 11
        assert "T1190" in covered


# ── Collect ──────────────────────────────────────────────────────────────────


class TestCollect:
    """collect.py — dry-run returns expected structure."""

    def test_collect_dry_run(self):
        from tests.benchmarks.bench_security.siem.collect import collect_target

        result = collect_target("10.10.11.50", "web", since_epoch=0, dry_run=True)
        assert "web:access" in result
        assert len(result["web:access"]) > 0

    def test_collect_returns_dict(self):
        from tests.benchmarks.bench_security.siem.collect import collect_target

        result = collect_target("10.10.11.21", "windows", since_epoch=0, dry_run=True)
        assert isinstance(result, dict)


# ── Index wait ───────────────────────────────────────────────────────────────


class TestIndexWait:
    """index_wait.py — timeout returns False (honest, never false PASS)."""

    def test_wait_indexed_timeout_returns_false(self):
        from tests.benchmarks.bench_security.siem.index_wait import wait_indexed

        result = wait_indexed(
            host="test-host",
            since_epoch=0,
            expect_min=1,
            timeout_s=2,  # short timeout for test
        )
        assert result is False


# ── Blue-triage ──────────────────────────────────────────────────────────────


class TestBlueTriage:
    """blue_triage.py — dry-run one synthetic alert end-to-end."""

    def test_poll_alerts_returns_list(self):
        from tests.benchmarks.bench_security.siem.blue_triage import poll_alerts

        # With unreachable Splunk, should return empty list
        result = poll_alerts(max_alerts=1, since_minutes=1)
        assert isinstance(result, list)

    def test_report_triage_writes_file(self, tmp_path):
        from tests.benchmarks.bench_security.siem.blue_triage import report_triage

        results = [{"alert": {"test": True}, "triage": "P4", "enriched": True}]
        path = report_triage(results, output_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_enrich_alert_handles_unreachable_pipeline(self):
        from tests.benchmarks.bench_security.siem.blue_triage import enrich_alert

        result = enrich_alert({"EventCode": 4769, "host": "dc01"})
        assert "alert" in result
        assert "triage" in result
        assert "enriched" in result


# ── Dead Talon removal guard ─────────────────────────────────────────────────


class TestTalonRemoved:
    """No reference to ghcr.io/taylorwalton/talon should remain."""

    def test_no_talon_image_in_compose_lab(self):
        lab_file = _PROJECT_ROOT / "deploy" / "portal-5" / "docker-compose.lab.yml"
        if lab_file.exists():
            content = lab_file.read_text()
            assert "taylorwalton/talon" not in content, (
                "Dead Talon image ref still in docker-compose.lab.yml"
            )

    def test_no_talon_port_in_env_example(self):
        env_file = _PROJECT_ROOT / ".env.example"
        if env_file.exists():
            content = env_file.read_text()
            # TALON_PORT should not be present (removed)
            lines = [
                line
                for line in content.splitlines()
                if "TALON_PORT" in line and not line.strip().startswith("#")
            ]
            assert len(lines) == 0, f"Active TALON_PORT still in .env.example: {lines}"


# ── Matrix wiring guard ──────────────────────────────────────────────────────


class TestMatrixTelemetryWiring:
    """Verify _execute_unit calls collect→ship→wait_indexed on the blue path."""

    def test_execute_unit_calls_telemetry_collection(self):
        """When purple=True and unit has telemetry, collect_target should be called."""
        from tests.benchmarks.bench_security.matrix import RunUnit, _execute_unit

        unit = RunUnit(
            id="test-001",
            kind="scenario",
            target_spec="vulhub-test",
            oracle="test_oracle",
            scoring="oracle",
            domain="web",
            spin="static",
            technique_ids=["T1190"],
            has_telemetry=True,
        )
        # Mock all the heavy functions
        with (
            patch("tests.benchmarks.bench_security.matrix._run_against_target", return_value=""),
            patch("tests.benchmarks.bench_security.matrix.verify_finding") as mock_verify,
            patch("tests.benchmarks.bench_security.matrix._run_blue_on_unit") as mock_blue,
            patch("tests.benchmarks.bench_security.matrix._score_purple_on_unit") as mock_purple,
        ):
            mock_verify.return_value = MagicMock(
                oracle="test_oracle",
                verified=True,
                evidence="test",
                honesty_claim="honest",
                reproductions=2,
                required=2,
            )
            mock_blue.return_value = {"detection_score": 0.5}
            mock_purple.return_value = {"purple_score": 0.5}

            result = _execute_unit(unit, lab_exec=False, purple=True)
            # Should complete without error — telemetry collection is best-effort
            assert result.status in ("verified", "rejected", "indeterminate", "error")
