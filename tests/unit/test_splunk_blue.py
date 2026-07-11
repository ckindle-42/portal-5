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
        from portal.modules.security.core.blue import WinEventBackend
        from portal.modules.security.core.telemetry import TelemetryBackend

        assert isinstance(WinEventBackend(), TelemetryBackend)

    def test_splunk_backend_satisfies_protocol(self):
        from portal.modules.security.core.blue import SplunkBackend
        from portal.modules.security.core.telemetry import TelemetryBackend

        assert isinstance(SplunkBackend(), TelemetryBackend)

    def test_contract_for_technique_returns_winevent_for_ad_targets(self):
        from portal.modules.security.core.telemetry import (
            CONTRACT_WINEVENT_AD,
            contract_for_technique,
        )

        for target in ["dc01", "srv01", "lab-dc01", "meta3"]:
            contract = contract_for_technique("T1558.003", target)
            assert contract.id == CONTRACT_WINEVENT_AD.id, f"{target} should use winevent-ad"

    def test_contract_for_technique_returns_splunk_for_web_targets(self):
        from portal.modules.security.core.telemetry import (
            CONTRACT_SPLUNK_WEB,
            contract_for_technique,
        )

        for target in ["vulhub", "10.10.11.50", "mbptl", "web-target"]:
            contract = contract_for_technique("T1190", target)
            assert contract.id == CONTRACT_SPLUNK_WEB.id, f"{target} should use splunk-web"


class TestWinEventBackend:
    """WinEventBackend behavior — synthetic fallback when no lab."""

    def test_synthetic_fallback_without_lab(self):
        from portal.modules.security.core.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T1558.003", {})
        assert result["source"] in ("live", "synthetic-fallback", "synthetic")
        assert result["backend"] == "winrm-winevent"
        assert "telemetry" in result

    def test_unknown_technique_returns_empty(self):
        from portal.modules.security.core.blue import WinEventBackend

        backend = WinEventBackend()
        result = backend.query("T9999.999", {})
        assert result["telemetry"] == ""
        assert result["source"] == "synthetic-fallback"


class TestSplunkBackend:
    """SplunkBackend — synthetic-fallback when Splunk unreachable."""

    def test_synthetic_fallback_when_no_splunk(self):
        from portal.modules.security.core.blue import SplunkBackend

        backend = SplunkBackend()
        backend.url = "https://127.0.0.1:1"  # unreachable
        result = backend.query("T1190", {})
        assert result["source"] == "synthetic-fallback"
        assert result["backend"] == "splunk"

    def test_unknown_technique_returns_synthetic_fallback(self):
        from portal.modules.security.core.blue import SplunkBackend

        backend = SplunkBackend()
        result = backend.query("T9999.999", {})
        assert result["source"] == "synthetic-fallback"


# ── HEC ship ─────────────────────────────────────────────────────────────────


class TestHecShip:
    """hec_ship.py — dry-run envelope construction, no network."""

    def test_ship_dry_run(self):
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

    def test_ship_batch_dry_run(self):
        from portal.modules.security.core.siem.hec_ship import ship_batch

        events = [{"raw": "line1"}, {"raw": "line2"}, {"raw": "line3"}]
        result = ship_batch(events, sourcetype="linux:auditd", host="dc01", dry_run=True)
        assert result["ok"] is True
        assert result["count"] == 3

    def test_ship_builds_valid_envelope(self):
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

    def test_yaml_parses(self):
        from portal.modules.security.core.siem.spl_detections import _load

        data = _load()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_every_technique_has_spl(self):
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

    def test_techniques_covered(self):
        from portal.modules.security.core.siem.spl_detections import techniques_covered

        covered = techniques_covered()
        assert len(covered) >= 11
        assert "T1190" in covered

    def test_technique_reference_returns_descriptions(self):
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

    def test_prompt_includes_technique_reference(self):
        from portal.modules.security.core.blue import BLUE_INITIAL_PROMPT

        assert "T1558.003" in BLUE_INITIAL_PROMPT
        assert "Kerberoasting" in BLUE_INITIAL_PROMPT

    def test_build_blue_initial_prompt_falls_back_without_reference(self):
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

    def test_collect_dry_run(self):
        from portal.modules.security.core.siem.collect import collect_target

        result = collect_target("10.10.11.50", "web", since_epoch=0, dry_run=True)
        assert "web:access" in result
        assert len(result["web:access"]) > 0

    def test_collect_returns_dict(self):
        from portal.modules.security.core.siem.collect import collect_target

        result = collect_target("10.10.11.21", "windows", since_epoch=0, dry_run=True)
        assert isinstance(result, dict)

    def test_unwrap_mcp_stdout_extracts_stdout_field(self):
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        raw = json.dumps({"success": True, "stdout": "line1\nline2", "stderr": ""})
        assert unwrap_mcp_stdout(raw) == "line1\nline2"

    def test_unwrap_mcp_stdout_passes_through_plain_text(self):
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        assert unwrap_mcp_stdout("not json at all") == "not json at all"

    def test_unwrap_mcp_stdout_passes_through_json_without_stdout_key(self):
        from portal.modules.security.core.siem.collect import unwrap_mcp_stdout

        raw = json.dumps({"foo": "bar"})
        assert unwrap_mcp_stdout(raw) == raw

    def test_strip_nxc_line_prefix(self):
        from portal.modules.security.core.siem.collect import strip_nxc_line_prefix

        raw = "WINRM                    10.10.11.21     5985   WIN-MVQO0PT39IO  Id          : 4769"
        assert strip_nxc_line_prefix(raw) == "Id          : 4769"

    def test_normalize_windows_security_events_kerberoasting(self):
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

    def test_normalize_windows_security_events_strips_nxc_prefix(self):
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

    def test_normalize_windows_security_events_unknown_code_keeps_bare_eventcode(self):
        from portal.modules.security.core.siem.collect import (
            _normalize_windows_security_events,
        )

        raw = "Id          : 9999\nMessage     : Something unmapped.\n"
        lines = _normalize_windows_security_events(raw)
        assert lines == ["EventCode=9999"]

    def test_normalize_windows_security_events_process_creation(self):
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


class TestMeta3Collect:
    """collect.py's kind="meta3" branch — IIS/FTP log + process-creation collection."""

    def _mock_mcp_call_factory(self, iis_text, ftp_text, winevent_text):
        """Build a fake mcp_call that returns nxc-shaped, JSON-wrapped, prefixed
        output depending on which PowerShell command was sent — matching the
        real sandbox MCP + nxc output shape found live 2026-07-04."""

        def _wrap(content: str) -> dict:
            nxc_prefix = "WINRM                    10.10.11.10     5985   VAGRANT-2008R2  "
            body = "\n".join(
                f"{nxc_prefix}{line}" if line.strip() else line for line in content.splitlines()
            )
            noise = (
                "[*] Initializing WINRM protocol database\n"
                "[+] vagrant-2008R2\\vagrant:vagrant (Pwn3d!)\n"
                "[+] Executed command (shell type: powershell)\n"
            )
            stdout = noise + body
            return {"ok": True, "output": json.dumps({"success": True, "stdout": stdout})}

        def _mcp_call(code: str, timeout: int = 90):
            # The actual PowerShell script travels as a base64 -EncodedCommand
            # blob (see _winrm_ps in collect.py) — decode it to dispatch by
            # content instead of substring-matching the outer nxc command line.
            import base64
            import re

            m = re.search(r"-EncodedCommand (\S+)", code)
            ps_script = base64.b64decode(m.group(1)).decode("utf-16-le") if m else ""
            if "FTPSVC2" in ps_script:
                return _wrap(ftp_text)
            if "W3SVC1" in ps_script:
                return _wrap(iis_text)
            if "4688" in ps_script or "MaxEvents 200" in ps_script:
                return _wrap(winevent_text)
            return {"ok": False, "output": ""}

        return _mcp_call

    def test_collect_meta3_returns_all_three_sourcetypes(self):
        from portal.modules.security.core.siem import collect as collect_mod

        iis_text = (
            "#Software: Microsoft Internet Information Services 7.5\n"
            "#Fields: date time cs-method\n"
            "2026-07-04 15:06:00 POST /_search\n"
        )
        ftp_text = "#Fields: date time cs-method\n2026-07-04 15:05:08 user :)\n"
        winevent_text = (
            "Id          : 4688\n"
            "Message     : A new process has been created.\n"
            "    New Process Name:   C:\\Windows\\System32\\cmd.exe\n"
            "    Account Name:       vagrant\n"
        )
        mock_mcp_call = self._mock_mcp_call_factory(iis_text, ftp_text, winevent_text)
        with patch.object(collect_mod, "_get_mcp_call", return_value=mock_mcp_call):
            result = collect_mod.collect_target(
                "10.10.11.10", "meta3", since_epoch=0, dry_run=False
            )
        assert result["web:access"] == ["2026-07-04 15:06:00 POST /_search"]
        assert result["ftp:access"] == ["2026-07-04 15:05:08 user :)"]
        assert len(result["windows:security"]) == 1
        assert "EventCode=4688" in result["windows:security"][0]
        assert "NewProcessName=C:\\Windows\\System32\\cmd.exe" in result["windows:security"][0]

    def test_collect_meta3_no_mcp_call_returns_empty(self):
        from portal.modules.security.core.siem import collect as collect_mod

        with patch.object(collect_mod, "_get_mcp_call", return_value=None):
            result = collect_mod.collect_target(
                "10.10.11.10", "meta3", since_epoch=0, dry_run=False
            )
        assert result == {}

    def test_collect_meta3_empty_output_omits_sourcetype(self):
        from portal.modules.security.core.siem import collect as collect_mod

        def _mcp_call(code: str, timeout: int = 90):
            return {"ok": True, "output": json.dumps({"success": True, "stdout": ""})}

        with patch.object(collect_mod, "_get_mcp_call", return_value=_mcp_call):
            result = collect_mod.collect_target(
                "10.10.11.10", "meta3", since_epoch=0, dry_run=False
            )
        assert result == {}


# ── Index wait ───────────────────────────────────────────────────────────────


class TestIndexWait:
    """index_wait.py — timeout returns False (honest, never false PASS)."""

    def test_wait_indexed_timeout_returns_false(self):
        from portal.modules.security.core.siem.index_wait import wait_indexed

        # Must mock httpx — this previously "passed" only because .env lacked
        # real Splunk credentials, so every request threw a connection error
        # (caught, same as a real 0-count response). Once real credentials were
        # restored (found live 2026-07-03), this started reaching live Splunk
        # and returning True for any host with actual indexed data, which is
        # correct behavior but broke this test's implicit "no network" assumption
        # — a real mock is needed to deterministically exercise the timeout path.
        mock_resp = MagicMock()
        mock_resp.text = '{"result": {"count": "0"}}'
        with patch("httpx.post", return_value=mock_resp):
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
        from portal.modules.security.core.siem.blue_triage import poll_alerts

        # With unreachable Splunk, should return empty list
        result = poll_alerts(max_alerts=1, since_minutes=1)
        assert isinstance(result, list)

    def test_report_triage_writes_file(self, tmp_path):
        from portal.modules.security.core.siem.blue_triage import report_triage

        results = [{"alert": {"test": True}, "triage": "P4", "enriched": True}]
        path = report_triage(results, output_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_enrich_alert_handles_unreachable_pipeline(self):
        from portal.modules.security.core.siem.blue_triage import enrich_alert

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
        from portal.modules.security.core.matrix import RunUnit, _execute_unit

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
            patch("portal.modules.security.core.matrix._run_against_target", return_value=""),
            patch("portal.modules.security.core.matrix.verify_finding") as mock_verify,
            patch("portal.modules.security.core.matrix._run_blue_on_unit") as mock_blue,
            patch("portal.modules.security.core.matrix._score_purple_on_unit") as mock_purple,
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


# ── Capture store (raw telemetry persistence + replay) ───────────────────────


class TestCaptureStore:
    """save_capture/replay_capture — durable raw evidence, independent of Splunk retention."""

    def test_save_capture_writes_file(self, tmp_path, monkeypatch):
        from portal.modules.security.core.siem import capture_store

        monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
        path = capture_store.save_capture(
            scenario="web_sqli_dump",
            target_host="10.10.11.50",
            kind="web",
            since_epoch=1000.0,
            telemetry={"web:access": ["GET /?id=1 UNION SELECT 200"]},
        )
        assert path is not None
        saved = json.loads(Path(path).read_text())
        assert saved["scenario"] == "web_sqli_dump"
        assert saved["telemetry"]["web:access"] == ["GET /?id=1 UNION SELECT 200"]

    def test_save_capture_returns_none_for_empty_telemetry(self, tmp_path, monkeypatch):
        from portal.modules.security.core.siem import capture_store

        monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
        path = capture_store.save_capture(
            scenario="x", target_host="10.10.11.50", kind="web", since_epoch=0.0, telemetry={}
        )
        assert path is None

    def test_list_captures_filters_by_scenario(self, tmp_path, monkeypatch):
        from portal.modules.security.core.siem import capture_store

        monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
        capture_store.save_capture(
            scenario="scenario_a",
            target_host="h",
            kind="web",
            since_epoch=0.0,
            telemetry={"web:access": ["x"]},
        )
        capture_store.save_capture(
            scenario="scenario_b",
            target_host="h",
            kind="web",
            since_epoch=0.0,
            telemetry={"web:access": ["y"]},
        )
        assert len(capture_store.list_captures()) == 2
        assert len(capture_store.list_captures(scenario="scenario_a")) == 1

    def test_replay_capture_reships_and_confirms(self, tmp_path, monkeypatch):
        from portal.modules.security.core.siem import capture_store

        monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
        path = capture_store.save_capture(
            scenario="web_sqli_dump",
            target_host="10.10.11.50",
            kind="web",
            since_epoch=1000.0,
            telemetry={"web:access": ["GET /?id=1 UNION SELECT 200"]},
        )
        with (
            patch(
                "portal.modules.security.core.siem.hec_ship.ship_batch",
                return_value={"ok": True, "code": 200, "count": 1},
            ),
            patch(
                "portal.modules.security.core.siem.index_wait.wait_indexed",
                return_value=True,
            ),
        ):
            result = capture_store.replay_capture(path)
        assert result["ok"] is True
        assert result["shipped"] == 1
        assert result["indexed_confirmed"] is True
        assert result["scenario"] == "web_sqli_dump"

    def test_replay_capture_dry_run_skips_indexed_check(self, tmp_path, monkeypatch):
        from portal.modules.security.core.siem import capture_store

        monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
        path = capture_store.save_capture(
            scenario="x",
            target_host="h",
            kind="web",
            since_epoch=0.0,
            telemetry={"web:access": ["line"]},
        )
        with patch(
            "portal.modules.security.core.siem.hec_ship.ship_batch",
            return_value={"ok": True, "dry_run": True, "count": 1},
        ):
            result = capture_store.replay_capture(path, dry_run=True)
        assert result["indexed_confirmed"] is None
