"""Build deterministic defensive security fixtures for the real-use suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "tests/wfe/suites/realuse_sec_v1.jsonl"
FIXTURE_ROOT = Path("tests/fixtures/realuse_sec_v1")
MANIFEST = FIXTURE_ROOT / "manifest.sha256"
WORKSPACES = {
    "auto-security": 6,
    "auto-security::blueteam": 6,
    "auto-spl": 6,
    "auto-compliance": 6,
    "auto-compliance::reading": 6,
}


def _sigma(title: str, technique: str, fields: dict[str, Any]) -> str:
    field_lines = "\n".join(f"    {name}: {value}" for name, value in fields.items())
    return (
        f"title: {title}\n"
        "status: experimental\n"
        f"description: Detects the supplied defensive test event for {technique}.\n"
        "references:\n"
        f"  - https://attack.mitre.org/techniques/{technique.replace('.', '/')}/\n"
        "author: Portal real-use fixture\n"
        "date: 2026-10-29\n"
        "tags:\n"
        f"  - attack.{technique.lower()}\n"
        "logsource:\n"
        "  product: windows\n"
        "  service: security\n"
        "detection:\n"
        "  selection:\n"
        f"{field_lines}\n"
        "  condition: selection\n"
        "falsepositives:\n"
        "  - Approved administrative activity\n"
        "level: medium\n"
    )


FIXTURES = {
    "tests/fixtures/realuse_sec_v1/events/auth_failures.json": json.dumps(
        {
            "events": [
                {
                    "EventID": 4625,
                    "TimeCreated": f"2026-10-29T10:0{minute}:00Z",
                    "Computer": "WS-17",
                    "TargetUserName": "jlee",
                    "IpAddress": "198.51.100.24",
                    "LogonType": 3,
                }
                for minute in range(5)
            ]
            + [
                {
                    "EventID": 4624,
                    "TimeCreated": "2026-10-29T10:06:00Z",
                    "Computer": "WS-17",
                    "TargetUserName": "jlee",
                    "IpAddress": "198.51.100.24",
                    "LogonType": 3,
                }
            ]
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/rdp_logon.json": json.dumps(
        {
            "EventID": 4624,
            "TimeCreated": "2026-10-29T11:14:00Z",
            "Computer": "ENG-04",
            "TargetUserName": "svc_backup",
            "IpAddress": "10.40.8.41",
            "LogonType": 10,
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/account_created.json": json.dumps(
        {
            "EventID": 4720,
            "TimeCreated": "2026-10-29T12:03:00Z",
            "Computer": "DC-02",
            "SubjectUserName": "helpdesk7",
            "TargetUserName": "svc_patch2",
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/powershell_process.json": json.dumps(
        {
            "EventID": 4688,
            "TimeCreated": "2026-10-29T12:18:00Z",
            "Computer": "APP-11",
            "NewProcessName": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "ProcessCommandLine": "powershell.exe -NoProfile -EncodedCommand <redacted-fixture>",
            "ParentProcessName": "C:\\Windows\\System32\\wscript.exe",
            "SubjectUserName": "batchsvc",
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/task_created.json": json.dumps(
        {
            "EventID": 4698,
            "TimeCreated": "2026-10-29T12:32:00Z",
            "Computer": "OPS-03",
            "SubjectUserName": "operator2",
            "TaskName": r"\\TelemetryRefresh",
            "TaskContent": "<Command>C:\\Tools\\refresh.exe</Command>",
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/log_cleared.json": json.dumps(
        {
            "EventID": 1102,
            "TimeCreated": "2026-10-29T12:48:00Z",
            "Computer": "FS-08",
            "SubjectUserName": "svc_ops",
            "Channel": "Security",
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/registry_access.json": json.dumps(
        {
            "EventID": 13,
            "Provider": "Microsoft-Windows-Sysmon",
            "TimeCreated": "2026-10-29T13:02:00Z",
            "Computer": "ENG-09",
            "Image": "C:\\Users\\Public\\diag.exe",
            "TargetObject": "HKLM\\Software\\Example\\Credentials\\LastUser",
            "Details": "ops_reader",
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/events/ssh_spray.log": (
        "Oct 29 13:10:01 bastion sshd[401]: Failed password for alice from 203.0.113.77 port 41001\n"
        "Oct 29 13:10:03 bastion sshd[402]: Failed password for bob from 203.0.113.77 port 41002\n"
        "Oct 29 13:10:05 bastion sshd[403]: Failed password for carol from 203.0.113.77 port 41003\n"
        "Oct 29 13:10:07 bastion sshd[404]: Failed password for dave from 203.0.113.77 port 41004\n"
        "Oct 29 13:10:09 bastion sshd[405]: Failed password for erin from 203.0.113.77 port 41005\n"
        "Oct 29 13:10:11 bastion sshd[406]: Failed password for frank from 203.0.113.77 port 41006\n"
    ),
    "tests/fixtures/realuse_sec_v1/network/dns_pcap_summary.txt": (
        "Synthetic pcap summary; no packet capture or live endpoint is included.\n"
        "Packets: 240; interval: 60 seconds; source: 10.20.4.8; destination: 203.0.113.90.\n"
        "DNS queries: 12 for cdn-update.example.invalid; response: 203.0.113.90.\n"
        "Fields: frame.time, ip.src, ip.dst, dns.qry.name, dns.a.\n"
    ),
    "tests/fixtures/realuse_sec_v1/network/modbus_pcap_summary.txt": (
        "Synthetic pcap summary; no packet capture or live endpoint is included.\n"
        "Flow: 10.20.7.12:51022 -> 10.20.7.40:502/TCP; two Modbus write-multiple-registers requests.\n"
        "Function code: 16; unit id: 3; no response body or process attribution is available.\n"
        "Fields: frame.time, ip.src, ip.dst, tcp.dstport, modbus.func_code, modbus.unit_id.\n"
    ),
    "tests/fixtures/realuse_sec_v1/vulnerability/log4j_triage.json": json.dumps(
        {
            "cve_id": "CVE-2021-44228",
            "package": "log4j-core",
            "version": "2.14.1",
            "installed_on": "app-11",
            "cvss_v3": 10.0,
            "epss": 0.97,
            "kev": True,
            "internet_facing": True,
        },
        indent=2,
    )
    + "\n",
    "tests/fixtures/realuse_sec_v1/sigma/failed_logons.yml": _sigma(
        "Repeated Network Logon Failures",
        "T1110.001",
        {"EventID": 4625, "LogonType": 3},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/rdp_logon.yml": _sigma(
        "Remote Interactive Logon",
        "T1021.001",
        {"EventID": 4624, "LogonType": 10},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/account_created.yml": _sigma(
        "Unexpected Local Account Creation",
        "T1136.001",
        {"EventID": 4720, "TargetUserName|startswith": "svc_"},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/powershell_process.yml": _sigma(
        "PowerShell Encoded Command",
        "T1059.001",
        {"EventID": 4688, "ProcessCommandLine|contains": "-EncodedCommand"},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/task_created.yml": _sigma(
        "Scheduled Task Creation",
        "T1053.005",
        {"EventID": 4698},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/log_cleared.yml": _sigma(
        "Windows Security Log Cleared",
        "T1070.001",
        {"EventID": 1102, "Channel": "Security"},
    ),
    "tests/fixtures/realuse_sec_v1/sigma/registry_access.yml": _sigma(
        "Credential Registry Value Read",
        "T1552.002",
        {"EventID": 13, "TargetObject|contains": "\\Credentials\\"},
    ),
    "tests/fixtures/realuse_sec_v1/spl/failed_logons.spl": (
        "index=wineventlog EventID=4625 LogonType=3 | stats count by IpAddress TargetUserName | where count >= 5\n"
    ),
    "tests/fixtures/realuse_sec_v1/spl/dns_beacon.spl": (
        "index=network sourcetype=dns | stats count dc(ip.dst) as destinations by ip.src dns.qry.name | where count >= 10 AND destinations=1\n"
    ),
    "tests/fixtures/realuse_sec_v1/yara/powershell_marker.yar": (
        "rule SuspiciousScriptMarkers {\n"
        "    meta:\n"
        '        description = "Synthetic marker check for a defensive training fixture"\n'
        "    strings:\n"
        '        $a = "FromBase64String" ascii\n'
        '        $b = "Invoke-Expression" ascii nocase\n'
        "    condition:\n"
        "        all of them\n"
        "}\n"
    ),
    "tests/fixtures/realuse_sec_v1/yara/loader_marker.yar": (
        "rule SyntheticLoaderMarkers {\n"
        "    strings:\n"
        '        $a = "WinHttpRequest" ascii nocase\n'
        '        $b = "VirtualAlloc" ascii nocase\n'
        "    condition:\n"
        "        any of them\n"
        "}\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/patch_evaluation_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: assess newly released security patches for applicability on every covered system no less often than every 35 calendar days, and record the evaluation date and source.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/patch_action_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: after an applicable patch evaluation, apply the patch or create or revise a dated mitigation plan within 35 calendar days.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/event_review_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: keep applicable event logs for 90 days, review a defined sample at least every 15 days, and retain reviewer, date, and disposition.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/config_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: after a change that deviates from the approved configuration baseline, update the baseline record within 30 calendar days and retain change approval.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/config_monitor_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: monitor the approved baseline for unauthorized changes at least once every 35 calendar days and document any detected change.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/access_review_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: verify the necessary accounts, role groups, and associated privileges for electronic access at least once every 15 calendar months; preserve the dated review and approvals.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/physical_alarm_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: alert the incident-response contacts no later than 15 minutes after detecting unauthorized access through a physical access point.\n"
    ),
    "tests/fixtures/realuse_sec_v1/compliance/recovery_test_excerpt.txt": (
        "Practice excerpt written for this suite, not a quotation: exercise each applicable recovery plan at least once every 36 calendar months in an environment representative of production.\n"
    ),
}


def _jsonl() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SUITE.read_text(encoding="utf-8").splitlines() if line]


def _workspace_tools(workspace: str) -> set[str]:
    cfg = yaml.safe_load((ROOT / "config/portal.yaml").read_text(encoding="utf-8"))
    base, _, variant = workspace.partition("::")
    row = cfg["workspaces"][base]
    if variant:
        return set(row["variants"][variant].get("tools", row.get("tools", [])))
    return set(row.get("tools", []))


def _validate_suite(rows: list[dict[str, Any]]) -> None:
    from tests.wfe import controls

    if len(rows) != sum(WORKSPACES.values()):
        raise AssertionError(f"expected {sum(WORKSPACES.values())} tasks, got {len(rows)}")
    counts = dict.fromkeys(WORKSPACES, 0)
    for row in rows:
        workspace = row["workspace"]
        if workspace not in counts:
            raise AssertionError(f"workspace outside declared real-use scope: {workspace}")
        counts[workspace] += 1
        if len(row.get("turns", [])) < 2:
            raise AssertionError(f"{row['id']}: expected a multi-turn scenario")
        if failures := controls.schema_failures(row):
            raise AssertionError("; ".join(map(str, failures)))
        expected = {tool for turn in row["turns"] for tool in turn.get("expect_tools", [])}
        missing = expected - _workspace_tools(workspace)
        if missing:
            raise AssertionError(
                f"{row['id']}: tools not allowed in {workspace}: {sorted(missing)}"
            )
        for fixture in row.get("fixtures", []):
            if fixture not in FIXTURES:
                raise AssertionError(f"{row['id']}: fixture absent from builder: {fixture}")
    if counts != WORKSPACES:
        raise AssertionError(f"workspace task counts differ: {counts}")


def _expected_bytes() -> dict[Path, bytes]:
    return {Path(path): text.encode("utf-8") for path, text in FIXTURES.items()}


def build() -> dict[Path, str]:
    rows = _jsonl()
    _validate_suite(rows)
    files = _expected_bytes()
    hashes: dict[Path, str] = {}
    for rel, raw in sorted(files.items()):
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[rel] = hashlib.sha256(raw).hexdigest()
    manifest = "".join(f"{digest}  {rel.as_posix()}\n" for rel, digest in sorted(hashes.items()))
    target = ROOT / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest, encoding="utf-8")
    return hashes


def check() -> dict[Path, str]:
    rows = _jsonl()
    _validate_suite(rows)
    expected = _expected_bytes()
    actual_paths = {
        path.relative_to(ROOT)
        for path in (ROOT / FIXTURE_ROOT).rglob("*")
        if path.is_file() and path != ROOT / MANIFEST
    }
    if actual_paths != set(expected):
        raise AssertionError(
            f"fixture path mismatch: missing={sorted(set(expected) - actual_paths)} extra={sorted(actual_paths - set(expected))}"
        )
    actual = {rel: (ROOT / rel).read_bytes() for rel in expected}
    for rel, raw in expected.items():
        if actual[rel] != raw:
            raise AssertionError(f"fixture differs from builder: {rel}")
    hashes = {rel: hashlib.sha256(raw).hexdigest() for rel, raw in actual.items()}
    manifest = "".join(f"{digest}  {rel.as_posix()}\n" for rel, digest in sorted(hashes.items()))
    if (ROOT / MANIFEST).read_text(encoding="utf-8") != manifest:
        raise AssertionError("fixture manifest differs from generated files")
    _check_evtx_fixtures(actual)
    _check_sigma_and_yara()
    return hashes


def _check_evtx_fixtures(files: dict[Path, bytes]) -> None:
    auth = json.loads(files[Path("tests/fixtures/realuse_sec_v1/events/auth_failures.json")])
    assert len(auth["events"]) == 6
    assert sum(event["EventID"] == 4625 for event in auth["events"]) == 5
    assert auth["events"][0]["IpAddress"] == "198.51.100.24"
    assert (
        json.loads(files[Path("tests/fixtures/realuse_sec_v1/events/rdp_logon.json")])["LogonType"]
        == 10
    )
    assert (
        "Function code: 16"
        in files[Path("tests/fixtures/realuse_sec_v1/network/modbus_pcap_summary.txt")].decode()
    )
    assert (
        json.loads(files[Path("tests/fixtures/realuse_sec_v1/vulnerability/log4j_triage.json")])[
            "cve_id"
        ]
        == "CVE-2021-44228"
    )


def _check_sigma_and_yara() -> None:
    from portal.modules.detection.tools.detection_mcp import (
        compile_yara,
        convert_sigma,
        validate_sigma,
    )
    from portal.modules.security.tools.detections_mcp import spl_validate_syntax

    for path, text in FIXTURES.items():
        if path.endswith(".yml"):
            result = validate_sigma(text)
            if not result.get("valid") or result.get("rule_count") != 1:
                raise AssertionError(f"invalid Sigma fixture {path}: {result}")
    for path in (
        "tests/fixtures/realuse_sec_v1/sigma/rdp_logon.yml",
        "tests/fixtures/realuse_sec_v1/sigma/log_cleared.yml",
    ):
        result = convert_sigma(FIXTURES[path], target="splunk")
        if not result.get("valid") or not result.get("queries"):
            raise AssertionError(f"Sigma fixture did not convert {path}: {result}")
    for path, text in FIXTURES.items():
        if path.endswith(".yar"):
            result = compile_yara(text)
            if not result.get("valid"):
                raise AssertionError(f"invalid YARA fixture {path}: {result}")
        if path.endswith(".spl"):
            result = spl_validate_syntax(text)
            if not result.get("ok"):
                raise AssertionError(f"invalid SPL fixture {path}: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify suite fixtures without writing"
    )
    args = parser.parse_args()
    hashes = check() if args.check else build()
    print(f"realuse_sec_v1 fixtures: {len(hashes)} paths, manifest {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
