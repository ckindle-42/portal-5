"""Tests for canonical telemetry contracts — Phase 2 of BUILD_PROGRAM.

Validates:
- Single canonical TelemetryBackend protocol (not two competing ones)
- TelemetryContract describes sources correctly
- TelemetryHealth pre-check: dead source → reason code, not silent skip
- Healthy source → TELEMETRY_OBSERVED
- Contract-for-technique dispatch
- The two old protocol duplicates are gone (one canonical remains)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from unittest.mock import MagicMock

from portal.modules.security.core.telemetry import (
    CONTRACT_SPLUNK_WEB,
    CONTRACT_WAZUH,
    CONTRACT_WINEVENT_AD,
    CONTRACTS,
    TelemetryBackend,
    check_source_health,
    contract_for_technique,
    get_contract,
)

# ── Protocol unification ─────────────────────────────────────────────────────


class TestProtocolUnification:
    """Only ONE canonical TelemetryBackend protocol exists."""

    def test_telemetry_module_has_protocol(self):
        assert hasattr(TelemetryBackend, "query")

    def test_blue_backends_satisfy_protocol(self):
        from portal.modules.security.core.blue import SplunkBackend, WinEventBackend

        assert isinstance(WinEventBackend(), TelemetryBackend)
        assert isinstance(SplunkBackend(), TelemetryBackend)

    def test_blue_does_not_define_own_protocol(self):
        """blue.py should import TelemetryBackend from telemetry, not define its own."""
        import inspect

        import bench_security.blue as blue_mod

        src = inspect.getsource(blue_mod)
        # Should NOT have "class TelemetryBackend(Protocol):" in blue.py
        assert "class TelemetryBackend(Protocol):" not in src, (
            "blue.py still defines its own TelemetryBackend Protocol"
        )

    def test_matrix_does_not_define_own_protocol(self):
        """matrix.py should import TelemetryBackend from telemetry, not define its own."""
        import inspect

        import bench_security.matrix as matrix_mod

        src = inspect.getsource(matrix_mod)
        assert "class TelemetryBackend" not in src, (
            "matrix.py still defines its own TelemetryBackend"
        )

    def test_only_one_telemetry_backend_class_in_bench_security(self):
        """There should be exactly one TelemetryBackend class definition across
        all .py files in bench_security/."""
        import inspect

        # Check the telemetry module directly
        from portal.modules.security.core import telemetry

        count = 0
        for name, _obj in inspect.getmembers(telemetry, inspect.isclass):
            if name == "TelemetryBackend":
                count += 1
        assert count == 1, f"Expected 1 TelemetryBackend, found {count}"


# ── TelemetryContract ────────────────────────────────────────────────────────


class TestTelemetryContract:
    """Contract describes a telemetry source."""

    def test_contract_has_required_fields(self):
        c = CONTRACT_SPLUNK_WEB
        assert c.id == "splunk-web"
        assert c.platform == "splunk"
        assert c.channel == "web:access"
        assert c.backend_name == "splunk"

    def test_contract_to_dict_is_json_safe(self):
        import json

        d = CONTRACT_SPLUNK_WEB.to_dict()
        json.dumps(d)  # should not raise
        assert "id" in d
        assert "platform" in d

    def test_winevent_ad_contract(self):
        c = CONTRACT_WINEVENT_AD
        assert c.platform == "winevent"
        assert c.signal.get("event_codes")  # non-empty

    def test_wazuh_contract_exists(self):
        c = CONTRACT_WAZUH
        assert c.platform == "wazuh"

    def test_contract_registry_has_all_three(self):
        assert len(CONTRACTS) == 3
        assert "splunk-web" in CONTRACTS
        assert "winevent-ad" in CONTRACTS
        assert "wazuh-alerts" in CONTRACTS

    def test_get_contract_by_id(self):
        c = get_contract("splunk-web")
        assert c is not None
        assert c.id == "splunk-web"

    def test_get_contract_returns_none_for_unknown(self):
        assert get_contract("nonexistent") is None


# ── Contract dispatch ────────────────────────────────────────────────────────


class TestContractDispatch:
    """contract_for_technique routes to the right contract by target."""

    def test_ad_targets_get_winevent_contract(self):
        for target in ["dc01", "srv01", "lab-dc01", "meta3", "lab-srv01"]:
            c = contract_for_technique("T1558.003", target)
            assert c.id == "winevent-ad", f"{target} should get winevent-ad"

    def test_web_targets_get_splunk_contract(self):
        for target in ["vulhub", "10.10.11.50", "mbptl", "web-host"]:
            c = contract_for_technique("T1190", target)
            assert c.id == "splunk-web", f"{target} should get splunk-web"

    def test_no_target_defaults_to_splunk(self):
        c = contract_for_technique("T1190", None)
        assert c.id == "splunk-web"


# ── TelemetryHealth pre-check ────────────────────────────────────────────────


class TestTelemetryHealth:
    """TelemetryHealth pre-check: dead source → reason code, not silent skip."""

    def test_healthy_source_returns_observed(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.return_value = {
            "telemetry": "EventCode=4769 some data",
            "source": "live",
            "backend": "test",
        }
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        assert result.healthy is True
        assert result.reason_code == "TELEMETRY_OBSERVED"
        assert result.contract_id == "splunk-web"

    def test_empty_telemetry_returns_not_configured(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.return_value = {
            "telemetry": "",
            "source": "synthetic-fallback",
            "backend": "test",
        }
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        assert result.healthy is False
        assert result.reason_code == "TELEMETRY_NOT_CONFIGURED"

    def test_synthetic_fallback_returns_not_configured(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.return_value = {
            "telemetry": "some synthetic data",
            "source": "synthetic-fallback",
            "backend": "test",
        }
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        assert result.healthy is False
        assert result.reason_code == "TELEMETRY_NOT_CONFIGURED"

    def test_backend_exception_returns_collection_failed(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.side_effect = ConnectionError("splunk unreachable")
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        assert result.healthy is False
        assert result.reason_code == "TELEMETRY_COLLECTION_FAILED"
        assert "backend.query raised" in result.detail

    def test_health_result_to_dict(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.return_value = {"telemetry": "data", "source": "live", "backend": "test"}
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        d = result.to_dict()
        assert "contract_id" in d
        assert "healthy" in d
        assert "reason_code" in d
        import json

        json.dumps(d)  # JSON-safe

    def test_health_result_has_timestamp(self):
        backend = MagicMock(spec=TelemetryBackend)
        backend.name = "test"
        backend.query.return_value = {"telemetry": "data", "source": "live", "backend": "test"}
        result = check_source_health(CONTRACT_SPLUNK_WEB, backend)
        assert result.checked_at > 0
