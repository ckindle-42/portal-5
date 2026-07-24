"""The red transcript is an audit/counterfactual plane, never sensor evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from portal.modules.security.core.siem.collect import reconstruct_attack_telemetry


def _blob(tele: dict[str, list[str]]) -> str:
    return " ".join(ln for lines in tele.values() for ln in lines).lower()


class TestReconstructAttackTelemetry:
    def test_payload_is_retained_without_manufacturing_sensor_shapes(self):
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
        assert set(tele) == {"transcript:command"}
        assert "@type" in _blob(tele)
        row = json.loads(tele["transcript:command"][0])
        assert row["evidence_origin"] == "transcript_counterfactual"
        assert row["claimed_target"] == "10.10.11.50"

    def test_command_does_not_become_ids_waf_or_syslog_evidence(self):
        calls = [{"name": "execute_bash", "args": {"cmd": "some-obscure-tool --do-a-thing"}}]
        tele = reconstruct_attack_telemetry(calls, target_host="t")
        assert not ({"ids:alert", "web:access", "linux:syslog"} & set(tele))
        assert "some-obscure-tool" in _blob(tele)

    def test_dispatch_failure_is_preserved_not_promoted(self):
        calls = [
            {
                "name": "execute_bash",
                "args": {"cmd": "curl http://10.0.0.1/?cmd=id"},
                "dispatch_ok": False,
                "dispatch_output": "connection refused",
            }
        ]
        row = json.loads(
            reconstruct_attack_telemetry(calls, target_host="10.0.0.1")["transcript:command"][0]
        )
        assert row["dispatch_ok"] is False
        assert "status" not in row

    def test_empty_and_blank_commands_ignored(self):
        assert reconstruct_attack_telemetry([]) == {}
        assert reconstruct_attack_telemetry([{"name": "x", "args": {}}]) == {}
        assert reconstruct_attack_telemetry([{"name": "x", "args": {"cmd": "  "}}]) == {}
