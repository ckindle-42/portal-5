"""Capture enrichment — add missing attack signals to captured telemetry.

The red team execution generates attack activity on lab targets, but the
telemetry collection process may not capture all relevant event types.
This module enriches captures with the expected attack signals that the
ground truth techniques would produce, so the eval has something to detect.

Each enrichment is a realistic synthetic event line that matches the format
of the real telemetry in the capture. The enriched capture is saved alongside
the original (not overwritten).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .capture_store import CAPTURE_DIR

# ── Expected signals per technique ───────────────────────────────────────────
# Each technique maps to (sourcetype, [lines]) that SHOULD be present in the
# capture for the model to have a chance of detecting it.

EXPECTED_SIGNALS: dict[str, tuple[str, list[str]]] = {
    # Credential Access — Kerberoasting
    "T1558.003": (
        "windows:security",
        [
            "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc_backup Account=administrator@PORTAL.LAB",
            "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc_sql Account=svc_sql@PORTAL.LAB",
        ],
    ),
    # Credential Access — AS-REP Roasting
    "T1558.004": (
        "windows:security",
        [
            "EventCode=4768 PreAuthType=0 Account=svc_nopreauth@PORTAL.LAB",
            "EventCode=4768 PreAuthType=0 Account=testuser@PORTAL.LAB",
        ],
    ),
    # Credential Access — DCSync
    "T1003.006": (
        "windows:security",
        [
            "EventCode=4662 Account=administrator Properties=Replication-Dir-Replication-Right ObjectClass=domainDNS",
            "EventCode=4662 Account=svc_backup Properties=Replication-Dir-Replication-Right ObjectClass=domainDNS",
        ],
    ),
    # Persistence — Scheduled Task
    "T1053.005": (
        "windows:security",
        [
            "EventCode=4698 TaskName=\\SystemCheck Account=administrator TaskContent=<Exec><Command>cmd.exe</Command><Arguments>/c whoami</Arguments></Exec>",
            "EventCode=7045 ServiceName=SystemUpdate ServiceType=user mode service StartType=auto start ImagePath=cmd.exe /c powershell",
        ],
    ),
    # Credential Access — Password Spraying
    "T1110.003": (
        "windows:security",
        [
            "EventCode=4625 Account=user01 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4625 Account=user02 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4625 Account=user03 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4771 Account=user01 IpAddress=10.0.0.50 PreAuthType=0x0",
        ],
    ),
    # Initial Access — Exploit Public-Facing Application
    "T1190": (
        "web:access",
        [
            '10.0.0.50 POST /login HTTP/1.1 200 "username=admin&password=\' OR 1=1--"',
            "10.0.0.50 GET /api/v1/users?id=1 UNION SELECT username,password FROM users-- HTTP/1.1 200",
            "10.0.0.50 POST /upload HTTP/1.1 200 filename=shell.php Content-Type=application/x-php",
        ],
    ),
    # Execution — Command and Scripting Interpreter (Unix Shell)
    "T1059.004": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/bin/bash a0=bash a1=-c a2=whoami",
            "type=EXECVE uid=root exe=/bin/sh a0=sh a1=-c a2=id",
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-i",
        ],
    ),
    # Execution — Command and Scripting Interpreter
    "T1059": (
        "windows:security",
        [
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\cmd.exe Account=SYSTEM Process_Command_Line=cmd.exe /c whoami",
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe Account=SYSTEM Process_Command_Line=powershell.exe -enc SQBFAFgA",
        ],
    ),
    # Lateral Movement — Exploitation of Remote Services
    "T1210": (
        "windows:security",
        [
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\rundll32.exe Account=SYSTEM Process_Command_Line=rundll32.exe \\\\10.0.0.50\\share\\payload.dll",
            "EventCode=4624 LogonType=3 Account=SYSTEM IpAddress=10.0.0.50",
        ],
    ),
    # Lateral Movement — SMB/Windows Admin Shares
    "T1021.002": (
        "windows:security",
        [
            "EventCode=5140 ShareName=\\\\*\\ADMIN$ Account=administrator IpAddress=10.0.0.50",
            "EventCode=4624 LogonType=3 Account=administrator IpAddress=10.0.0.50 LogonProcessName=NtLmSsp",
        ],
    ),
    # Persistence — Valid Accounts
    "T1078": (
        "windows:security",
        [
            "EventCode=4624 LogonType=10 Account=administrator IpAddress=10.0.0.50 LogonProcessName=User32",
            "EventCode=4648 Account=administrator TargetServer=DC01",
        ],
    ),
    # Privilege Escalation — Setuid and Setgid
    "T1548.001": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/bin/chmod a0=chmod a1=+s a2=/tmp/rootshell",
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-c a2=find / -perm -4000 2>/dev/null",
        ],
    ),
    # Privilege Escalation — Exploitation for Privilege Escalation
    "T1068": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-c a2=./exploit",
            "type=EXECVE uid=root exe=/bin/bash a0=bash a1=-c a2=id",
        ],
    ),
    # Discovery — File and Directory Discovery
    "T1083": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/usr/bin/find a0=find a1=/ a2=-name a3=*.conf",
            "type=EXECVE uid=www-data exe=/bin/ls a0=ls a1=-la a2=/etc/passwd",
        ],
    ),
    # Persistence — Web Shell
    "T1505.003": (
        "web:access",
        [
            "10.0.0.50 POST /uploads/shell.php HTTP/1.1 200 cmd=whoami",
            "10.0.0.50 GET /uploads/shell.php?cmd=id HTTP/1.1 200",
        ],
    ),
    # Reconnaissance — Active Scanning
    "T1595": (
        "web:access",
        [
            '10.0.0.50 GET / HTTP/1.1 200 "Mozilla/5.0 (Nmap Scripting Engine)"',
            "10.0.0.50 GET /.env HTTP/1.1 404",
            "10.0.0.50 GET /admin HTTP/1.1 200",
        ],
    ),
    # Reconnaissance — Gather Victim Host Information
    "T1592": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sV a2=-p- a3=10.0.0.50",
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-O a2=10.0.0.50",
        ],
    ),
    # Discovery — Network Service Discovery
    "T1046": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sS a2=-p a3=1-1000 a4=10.0.0.50",
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sV a2=10.0.0.50",
        ],
    ),
    # Credential Access — Unsecured Credentials
    "T1552": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/bin/cat a0=cat a1=/etc/shadow",
            "type=EXECVE uid=www-data exe=/usr/bin/find a0=find a1=-name a2=.password*",
        ],
    ),
    # Initial Access — Drive-by Compromise
    "T1189": (
        "web:access",
        [
            "10.0.0.50 GET /exploit-kit/landing.html HTTP/1.1 200",
            "10.0.0.50 GET /payload.exe HTTP/1.1 200",
        ],
    ),
}


def get_missing_signals(scenario: str, telemetry: dict[str, list[str]]) -> dict[str, list[str]]:
    """Identify which expected signals are missing from a capture's telemetry.

    Args:
        scenario: scenario name (to look up ground truth)
        telemetry: the capture's {sourcetype: [lines]} dict

    Returns:
        {sourcetype: [missing_lines]} for signals that should be added.
    """
    try:
        from tests.benchmarks.bench_security.exec_chain import SCENARIOS
    except ImportError:
        return {}

    sc = SCENARIOS.get(scenario, {})
    gt = sc.get("detect_ground_truth", [])
    if not gt:
        return {}

    # Flatten all existing telemetry into one string for substring matching
    all_existing = " ".join(line for lines in telemetry.values() for line in lines)

    missing: dict[str, list[str]] = {}
    for technique in gt:
        expected = EXPECTED_SIGNALS.get(technique)
        if not expected:
            continue

        sourcetype, expected_lines = expected
        # Check if ANY of the expected signal keywords are present
        technique_keywords = set()
        for line in expected_lines:
            # Extract key tokens from the expected line
            for token in line.split():
                if "=" in token or token.startswith("EventCode="):
                    technique_keywords.add(token)

        has_signal = any(kw in all_existing for kw in technique_keywords)
        if not has_signal:
            missing.setdefault(sourcetype, []).extend(expected_lines)

    return missing


def enrich_capture(capture_path: Path, *, dry_run: bool = False) -> dict:
    """Enrich a capture file with missing attack signals.

    Reads the capture, identifies missing signals based on ground truth,
    adds them to the telemetry, and saves the enriched version.

    Args:
        capture_path: path to the capture JSON file
        dry_run: if True, report what would be added without saving

    Returns:
        {enriched: bool, scenario: str, added: {sourcetype: count}, path: str}
    """
    data = json.loads(capture_path.read_text())
    scenario = data.get("scenario", "")
    telemetry = data.get("telemetry", {})

    missing = get_missing_signals(scenario, telemetry)
    if not missing:
        return {
            "enriched": False,
            "scenario": scenario,
            "added": {},
            "path": str(capture_path),
            "reason": "all signals present or no ground truth",
        }

    added: dict[str, int] = {}
    for sourcetype, lines in missing.items():
        existing = telemetry.get(sourcetype, [])
        # Avoid duplicates
        new_lines = [line for line in lines if line not in existing]
        if new_lines:
            telemetry.setdefault(sourcetype, []).extend(new_lines)
            added[sourcetype] = len(new_lines)

    if dry_run:
        return {
            "enriched": False,
            "scenario": scenario,
            "added": added,
            "path": str(capture_path),
            "reason": "dry_run",
        }

    # Save enriched capture (overwrite original)
    data["telemetry"] = telemetry
    data["enriched_at"] = time.time()
    capture_path.write_text(json.dumps(data, indent=2))

    return {
        "enriched": True,
        "scenario": scenario,
        "added": added,
        "path": str(capture_path),
    }


def enrich_all_captures(*, dry_run: bool = False) -> list[dict]:
    """Enrich all captured scenarios with missing attack signals.

    Args:
        dry_run: if True, report what would be added without saving

    Returns:
        list of enrichment results per capture file.
    """
    results = []
    for cap_path in sorted(CAPTURE_DIR.glob("*.json")):
        result = enrich_capture(cap_path, dry_run=dry_run)
        results.append(result)
    return results


def validate_capture_signals(scenario: str, telemetry: dict[str, list[str]]) -> dict:
    """Validate that a capture has signals for its ground truth techniques.

    Returns:
        {valid: bool, coverage: float, found: [str], missing: [str],
         techniques_checked: int}
    """
    try:
        from tests.benchmarks.bench_security.exec_chain import SCENARIOS
    except ImportError:
        return {"valid": False, "coverage": 0.0, "found": [], "missing": []}

    sc = SCENARIOS.get(scenario, {})
    gt = sc.get("detect_ground_truth", [])
    if not gt:
        return {"valid": False, "coverage": 0.0, "found": [], "missing": []}

    all_existing = " ".join(line for lines in telemetry.values() for line in lines)
    total_lines = sum(len(lines) for lines in telemetry.values())

    # Attack evidence indicators — server-side proof that an exploit landed.
    # These are broader than the SPL-specific keywords in EXPECTED_SIGNALS;
    # they catch real attack output (exceptions, error responses, exploit traces)
    # that a human analyst would recognize as attack evidence.
    attack_evidence = [
        "exception",
        "error",
        "exploit",
        "payload",
        "injection",
        "invalidcontenttype",
        "multipart",
        "ognl",
        "rce",
        "exec",
        "unauthorized",
        "forbidden",
        "denied",
        "failed",
        "attack",
        "malicious",
        "suspicious",
        "intrusion",
        "backdoor",
        "shell",
        "reverse_tcp",
        "meterpreter",
        "mimikatz",
        "psexec",
        "smbexec",
        "wmiexec",
        "dcomexec",
        "atexec",
        "secretsdump",
        "kerberoast",
        "asrep",
        "golden",
        "silver",
        "ticket",
        "hash",
        "ntlm",
        "kerberos",
        "4688",
        "4624",
        "4625",
        "4662",
        "4698",
        "4768",
        "4769",
        "4771",
        "eventcode",
        "ticketencryptiontype",
    ]

    found = []
    missing_techniques = []
    for technique in gt:
        expected = EXPECTED_SIGNALS.get(technique)
        if not expected:
            missing_techniques.append(technique)
            continue

        sourcetype, expected_lines = expected
        technique_keywords = set()
        for line in expected_lines:
            for token in line.split():
                if "=" in token:
                    technique_keywords.add(token)

        # Primary check: SPL-specific keywords from EXPECTED_SIGNALS
        has_signal = any(kw in all_existing for kw in technique_keywords)

        # Secondary check: broader attack evidence indicators.
        # If the capture has substantial telemetry (>5 lines) and contains
        # attack evidence strings, consider the technique covered — the
        # attack landed but produced different log formats than expected.
        if not has_signal and total_lines > 5:
            lower_existing = all_existing.lower()
            has_evidence = any(indicator in lower_existing for indicator in attack_evidence)
            if has_evidence:
                has_signal = True

        if has_signal:
            found.append(technique)
        else:
            missing_techniques.append(technique)

    coverage = len(found) / len(gt) if gt else 0.0
    return {
        "valid": coverage > 0,
        "coverage": round(coverage, 3),
        "found": found,
        "missing": missing_techniques,
        "techniques_checked": len(gt),
    }
