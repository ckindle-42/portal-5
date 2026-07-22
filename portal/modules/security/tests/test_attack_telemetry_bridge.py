"""Tests for reconstruct_attack_telemetry — bridging red's OWN authoritative
record of the attack into the capture blue detects against.

Found live 2026-07-22 (GATE-D ablation Part II-A, user architecture question):
the RBP evidence chain was severed — red recorded exactly what it sent
(tools_called_args: real fastjson/log4shell/SQLi payloads), but post-hoc
target-log collection was lossy (66/89 hollow captures) and red's own
transcript was never merged into what blue sees. A network IDS / WAF / full
packet capture in a real SOC WOULD carry these request lines and payloads;
bridging them is a faithful reconstruction of telemetry that should exist,
provenance-tagged (ids:alert), never fabricated.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from portal.modules.security.core.siem.collect import reconstruct_attack_telemetry


def _blob(tele: dict[str, list[str]]) -> str:
    return " ".join(ln for lines in tele.values() for ln in lines).lower()


class TestReconstructAttackTelemetry:
    def test_post_body_payload_reaches_ids_alert(self):
        """A fastjson deserialization POST body payload — which a standard
        access log would NOT record but an IDS/network capture would — must be
        present in the reconstructed telemetry."""
        calls = [
            {
                "name": "execute_bash",
                "args": {
                    "cmd": "curl -s -X POST http://10.10.11.50:8090/api "
                    '-d "{\\"@type\\":\\"java.lang.AutoCloseable\\"}"'
                },
            }
        ]
        tele = reconstruct_attack_telemetry(calls, target_host="10.10.11.50")
        assert "ids:alert" in tele
        assert "@type" in _blob(tele)

    def test_url_encoded_sqli_is_decoded_for_detection(self):
        """A URL-encoded SQLi payload must appear DECODED in the web:access
        line (as a WAF/IDS normalizes it), so signature detection can match
        the readable 'UNION SELECT' form."""
        calls = [
            {
                "name": "execute_bash",
                "args": {
                    "cmd": "curl -s 'http://10.10.11.50/vuln.aspx?"
                    "id=1%20UNION%20SELECT%20username,password%20FROM%20users--'"
                },
            }
        ]
        tele = reconstruct_attack_telemetry(calls, target_host="10.10.11.50")
        assert "web:access" in tele
        assert "union select" in _blob(tele)

    def test_get_request_becomes_web_access_line(self):
        calls = [
            {"name": "execute_bash", "args": {"cmd": "curl http://10.10.11.50/../../etc/passwd"}}
        ]
        tele = reconstruct_attack_telemetry(calls, target_host="10.10.11.50")
        assert any("GET" in ln for ln in tele.get("web:access", []))

    def test_ssh_bruteforce_becomes_syslog_auth_line(self):
        calls = [
            {
                "name": "execute_bash",
                "args": {"cmd": "sshpass -p vagrant ssh vagrant@10.10.11.13 whoami"},
            }
        ]
        tele = reconstruct_attack_telemetry(calls, target_host="10.10.11.13")
        assert "linux:syslog" in tele
        assert "sshd" in _blob(tele)

    def test_every_command_always_produces_an_ids_line(self):
        """Even a command with no parseable URL/auth must still surface as a
        real artifact — the ids:alert line is the guaranteed-present record."""
        calls = [{"name": "execute_bash", "args": {"cmd": "some-obscure-tool --do-a-thing"}}]
        tele = reconstruct_attack_telemetry(calls, target_host="t")
        assert len(tele.get("ids:alert", [])) == 1
        assert "some-obscure-tool" in _blob(tele)

    def test_empty_and_blank_commands_ignored(self):
        assert reconstruct_attack_telemetry([]) == {}
        assert reconstruct_attack_telemetry([{"name": "x", "args": {}}]) == {}
        assert reconstruct_attack_telemetry([{"name": "x", "args": {"cmd": "  "}}]) == {}
