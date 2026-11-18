"""Tests for Splunk SIEM integration + blue-triage (synthetic/dry-run — no live Splunk in CI).

Covers: TelemetryBackend adapter, SplunkBackend, HEC ship, collect, index_wait,
blue_triage, spl_detections, and the dead-Talon-removal guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── TelemetryBackend adapter ─────────────────────────────────────────────────


class TestTelemetryBackendProtocol:
    """Prove the protocol is satisfied by all backends."""

    def test_winrm_backend_satisfies_protocol(self) -> None:
        from portal.modules.security.core.blue import WinEventBackend
        from portal.modules.security.core.telemetry import TelemetryBackend

        assert isinstance(WinEventBackend(), TelemetryBackend)

    def test_splunk_backend_satisfies_protocol(self) -> None:
        from portal.modules.security.core.blue import SplunkBackend
        from portal.modules.security.core.telemetry import TelemetryBackend

        assert isinstance(SplunkBackend(), TelemetryBackend)

    def test_contract_for_technique_returns_winevent_for_ad_targets(self) -> None:
        from portal.modules.security.core.telemetry import (
            CONTRACT_WINEVENT_AD,
            contract_for_technique,
        )

        for target in ["dc01", "srv01", "lab-dc01", "meta3"]:
            contract = contract_for_technique("T1558.003", target)
            assert contract.id == CONTRACT_WINEVENT_AD.id, f"{target} should use winevent-ad"

    def test_contract_for_technique_returns_splunk_for_web_targets(self) -> None:
        from portal.modules.security.core.telemetry import (
            CONTRACT_SPLUNK_WEB,
            contract_for_technique,
        )

        for target in ["vulhub", "10.10.11.50", "mbptl", "web-target"]:
            contract = contract_for_technique("T1190", target)
            assert contract.id == CONTRACT_SPLUNK_WEB.id, f"{target} should use splunk-web"


class TestWinEventBackend:
    """WinEventBackend behavior — synthetic fallback when no lab."""

    def test_synthetic_fallback_without_lab(self) -> None:
        from portal.modules.security.core.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T1558.003", {})
        assert result["source"] in ("live", "synthetic-fallback", "synthetic")
        assert result["backend"] == "winrm-winevent"
        assert "telemetry" in result

    def test_unknown_technique_returns_empty(self) -> None:
        from portal.modules.security.core.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T9999.999", {})
        assert result["telemetry"] == ""
        assert result["source"] == "synthetic-fallback"


class TestSplunkBackend:
    """SplunkBackend — synthetic-fallback when Splunk unreachable."""

    def test_synthetic_fallback_when_no_splunk(self) -> None:
        from portal.modules.security.core.blue import SplunkBackend

        backend = SplunkBackend()
        backend.url = "https://127.0.0.1:1"  # unreachable
        result = backend.query("T1190", {})
        assert result["source"] == "synthetic-fallback"
        assert result["backend"] == "splunk"

    def test_unknown_technique_returns_synthetic_fallback(self) -> None:
        from portal.modules.security.core.blue import SplunkBackend

        backend = SplunkBackend()
        result = backend.query("T9999.999", {})
        assert result["source"] == "synthetic-fallback"


# ── HEC ship ─────────────────────────────────────────────────────────────────


class TestHecShip:
    """hec_ship.py — dry-run envelope construction, no network."""

    def test_ship_dry_run(self) -> None:
        from portal.modules.security.core.siem.hec_ship import ship

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

    def test_ship_batch_dry_run(self) -> None:
        from portal.modules.security.core.siem.hec_ship import ship_batch

        events: list[dict[str, Any] | str] = [
            {"raw": "line1"},
            {"raw": "line2"},
            {"raw": "line3"},
        ]
        result = ship_batch(events, sourcetype="linux:auditd", host="dc01", dry_run=True)
        assert result["ok"] is True
        assert result["count"] == 3

    def test_ship_builds_valid_envelope(self) -> None:
        from portal.modules.security.core.siem.hec_ship import ship

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

    def test_yaml_parses(self) -> None:
        from portal.modules.security.core.siem.spl_detections import _load

        data = _load()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_every_technique_has_spl(self) -> None:
        from portal.modules.security.core.siem.spl_detections import spl_for

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

    def test_techniques_covered(self) -> None:
        from portal.modules.security.core.siem.spl_detections import techniques_covered

        covered = techniques_covered()
        assert len(covered) >= 11
        assert "T1190" in covered

    def test_technique_reference_returns_descriptions(self) -> None:
        from portal.modules.security.core.siem.spl_detections import technique_reference

        ref = technique_reference()
        assert isinstance(ref, dict)
        assert len(ref) >= 11
        assert "T1558.003" in ref
        assert "Kerberoasting" in ref["T1558.003"]


class TestBlueInitialPrompt:
    """blue.py's BLUE_INITIAL_PROMPT — includes the MITRE technique reference table
    so the blue model matches evidence to a sub-technique ID instead of guessing
    from general knowledge (found live 2026-07-04: sylink/sylink:8b and a
    tool-fixed CyberSecQwen-4B both reported the wrong MITRE ID on correct,
    live Kerberoasting/DCSync telemetry with no reference material in prompt)."""

    def test_prompt_includes_technique_reference(self) -> None:
        from portal.modules.security.core.blue import BLUE_INITIAL_PROMPT

        assert "T1558.003" in BLUE_INITIAL_PROMPT
        assert "Kerberoasting" in BLUE_INITIAL_PROMPT

    def test_build_blue_initial_prompt_falls_back_without_reference(self) -> None:
        from portal.modules.security.core.blue import _build_blue_initial_prompt

        with patch(
            "portal.modules.security.core.siem.spl_detections.technique_reference",
            return_value={},
        ):
            prompt = _build_blue_initial_prompt()
        assert "An alert was triggered" in prompt
        assert "MITRE technique reference" not in prompt


# ── Collect ──────────────────────────────────────────────────────────────────


class TestCollect:
    """collect.py — dry-run returns expected structure."""

    def test_collect_dry_run(self) -> None:
        from portal.modules.security.core.siem.collect import collect_target

        result = collect_target("10.10.11.50", "web", since_epoch=0, dry_run=True)
        assert "web:access" in result
        assert len(result["web:access"]) > 0

    def test_collect_returns_dict(self) -> None:
        from portal.modules.security.core.siem.collect import collect_target

        result = collect_target("10.10.11.21", "windows", since_epoch=0, dry_run=True)
        assert isinstance(result, dict)

    def test_unwrap_mcp_stdout_extracts_stdout_field(self) -> None:
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        raw = json.dumps({"success": True, "stdout": "line1\nline2", "stderr": ""})
        assert unwrap_mcp_stdout(raw) == "line1\nline2"

    def test_unwrap_mcp_stdout_passes_through_plain_text(self) -> None:
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        assert unwrap_mcp_stdout("not json at all") == "not json at all"

    def test_unwrap_mcp_stdout_passes_through_json_without_stdout_key(self) -> None:
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        raw = json.dumps({"foo": "bar"})
        assert unwrap_mcp_stdout(raw) == raw

    def test_strip_nxc_line_prefix(self) -> None:
        from portal.modules.security.core.siem.collect import strip_nxc_line_prefix

        raw = "WINRM                    10.10.11.21     5985   WIN-MVQO0PT39IO  Id          : 4769"
        assert strip_nxc_line_prefix(raw) == "Id          : 4769"

    def test_normalize_windows_security_events_kerberoasting(self) -> None:
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "Id          : 4769\n"
            "TimeCreated : 7/4/2026 12:47:32 PM\n"
            "Message     : A Kerberos service ticket was requested.\n\n"
            "              Account Information:\n"
            "                 Account Name:            arya.stark@PORTAL.LAB\n\n"
            "              Service Information:\n"
            "                 Service Name:            svc_mssql\n\n"
            "              Additional Information:\n"
            "                 Ticket Encryption Type:    0x17\n"
        )
        lines = _normalize_windows_security_events(raw)
        assert len(lines) == 1
        assert "EventCode=4769" in lines[0]
        assert "TicketEncryptionType=0x17" in lines[0]
        assert "ServiceName=svc_mssql" in lines[0]
        assert "Account=arya.stark@PORTAL.LAB" in lines[0]

    def test_normalize_windows_security_events_strips_nxc_prefix(self) -> None:
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "WINRM                    10.10.11.21     5985   WIN-MVQO0PT39IO  Id          : 4698\n"
            "WINRM                    10.10.11.21     5985   WIN-MVQO0PT39IO                 "
            "Task Name:            \\Backdoor\n"
            "WINRM                    10.10.11.21     5985   WIN-MVQO0PT39IO                 "
            "Account Name:            arya.stark\n"
        )
        lines = _normalize_windows_security_events(raw)
        assert len(lines) == 1
        assert lines[0] == "EventCode=4698 TaskName=\\Backdoor Account=arya.stark"

    def test_normalize_windows_security_events_unknown_code_keeps_bare_eventcode(self) -> None:
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = "Id          : 9999\nMessage     : Something unmapped.\n"
        lines = _normalize_windows_security_events(raw)
        assert lines == ["EventCode=9999"]

    def test_normalize_windows_security_events_process_creation(self) -> None:
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "Id          : 4688\n"
            "TimeCreated : 7/4/2026 11:01:46 AM\n"
            "Message     : A new process has been created.\n"
            "Subject:\n"
            "    Account Name:       vagrant\n"
            "Process Information:\n"
            "    New Process Name:   C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\n"
            '    Process Command Line:   "powershell.exe" -NoProfile\n'
        )
        lines = _normalize_windows_security_events(raw)
        assert len(lines) == 1
        assert "EventCode=4688" in lines[0]
        assert (
            "NewProcessName=C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
            in lines[0]
        )
        assert "Account=vagrant" in lines[0]

    def test_normalize_windows_security_events_empty_cmdline_field_not_garbled(self) -> None:
        """Regression: real Windows 4688 events append a long explanatory
        footer after the actual field values, starting with "Token Elevation
        Type indicates the type of token that was...". The old
        `Process Command Line:\\s*(.+)` regex let `\\s*` cross the newline
        past an EMPTY command-line field (auditing not enabled) and captured
        that boilerplate sentence as if it were the real command line — found
        live 2026-07-18 on every meta3_* captured scenario. An empty field
        must be omitted, never garbled."""
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "Id          : 4688\n"
            "TimeCreated : 7/17/2026 3:07:44 PM\n"
            "Message     : A new process has been created.\n"
            "Process Information:\n"
            "\tNew Process Name:\tC:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\n"
            "\tToken Elevation Type:\t%%1938\n"
            "\tProcess Command Line:\t\n"
            "\n"
            "Token Elevation Type indicates the type of token that was assigned to the "
            "new process in accordance with User Account Control policy.\n"
        )
        lines = _normalize_windows_security_events(raw)
        assert len(lines) == 1
        assert "Token Elevation Type indicates" not in lines[0]
        assert "CommandLine=" not in lines[0]
        assert (
            "NewProcessName=C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
            in lines[0]
        )

    def test_normalize_windows_security_events_real_cmdline_still_extracted(self) -> None:
        """The fix must not regress the case where auditing IS enabled and a
        real command line follows the label on the same line."""
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "Id          : 4688\n"
            "Process Information:\n"
            "\tNew Process Name:\tC:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\n"
            "\tProcess Command Line:\tpowershell.exe -enc SGVsbG8=\n"
        )
        lines = _normalize_windows_security_events(raw)
        assert "CommandLine=powershell.exe -enc SGVsbG8=" in lines[0]

    def test_normalize_windows_security_events_process_name_with_spaces_not_truncated(
        self,
    ) -> None:
        """Regression: NewProcessName/TaskName used `(\\S+)` — a real process
        path containing spaces (e.g. "C:\\Program Files\\...") got truncated
        at the first space instead of capturing the full value. Found live
        2026-07-18 while verifying the capture fix end-to-end on the DC."""
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = (
            "Id          : 4688\n"
            "Process Information:\n"
            "\tNew Process Name:\tC:\\Program Files\\Common Files\\service.exe\n"
            "\tProcess Command Line:\tC:\\Program Files\\Common Files\\service.exe -start now\n"
        )
        lines = _normalize_windows_security_events(raw)
        assert (
            lines[0]
            == "EventCode=4688 NewProcessName=C:\\Program Files\\Common Files\\service.exe "
            "CommandLine=C:\\Program Files\\Common Files\\service.exe -start now"
        )


# ── Index wait ───────────────────────────────────────────────────────────────


# ── Blue-triage ──────────────────────────────────────────────────────────────


class TestBlueTriage:
    """blue_triage.py — dry-run one synthetic alert end-to-end."""

    def test_poll_alerts_returns_list(self) -> None:
        from portal.modules.security.core.siem.blue_triage import poll_alerts

        # With unreachable Splunk, should return empty list
        result = poll_alerts(max_alerts=1, since_minutes=1)
        assert isinstance(result, list)

    def test_enrich_alert_handles_unreachable_pipeline(self) -> None:
        from portal.modules.security.core.siem.blue_triage import enrich_alert

        result = enrich_alert({"EventCode": 4769, "host": "dc01"})
        assert "alert" in result
        assert "triage" in result
        assert "enriched" in result


# ── Dead Talon removal guard ─────────────────────────────────────────────────


class TestTalonRemoved:
    """No reference to ghcr.io/taylorwalton/talon should remain."""

    def test_no_talon_port_in_env_example(self) -> None:
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


# ── Capture store (raw telemetry persistence + replay) ───────────────────────
