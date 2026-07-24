"""Capture validity — verify a capture actually contains technique-specific
evidence for its declared ground truth, honestly.

Never fabricates or credits missing evidence: a technique with no matching
signal in the real captured telemetry is reported missing, not synthesized.
An earlier version of this module (`enrich_capture`/`get_missing_signals`)
did synthesize plausible-looking signal lines into captures with gaps --
removed 2026-07-24 as unused dead code (no callers anywhere in the codebase)
that also directly contradicted this module's now-current honesty guarantee;
see validate_capture_signals' own docstring for the historical incident that
established never-fabricate as a hard rule here.
"""

from __future__ import annotations

import re

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

# Regex-based ALTERNATIVE evidence per technique, checked with OR logic
# against the EXPECTED_SIGNALS token-match above (either satisfies the
# technique -- see validate_capture_signals). Exists because a MITRE
# technique can be legitimately proven by evidence shapes EXPECTED_SIGNALS'
# single (sourcetype, [literal example lines]) format can't express: exact
# literal substrings can't match a value that legitimately varies (a uid
# number, a session token), and some techniques are provable via more than
# one real evidence channel depending on target OS/exploit class.
#
# Found live 2026-07-24: 18 vulhub-LXC scenarios declared "T1059" (bare --
# EXPECTED_SIGNALS' only entry for it is windows:security EventCode=4688,
# collected via linux:auditd's `ausearch -m EXECVE` on Linux targets) --
# confirmed live that linux:auditd can never produce telemetry from this LXC
# (Linux kernel audit is a single host-wide facility a container sharing the
# host kernel can't independently own; installing/starting auditd there fails
# immediately with "Operation not permitted" even with cap_audit_control
# present). But real, observable command-execution evidence DOES exist for
# most of these scenarios by design: reading their own red_prompt AND each
# CVE's real vulhub README (e.g. struts2 S2-045 verifies via a reflected OGNL
# math-eval header, ThinkPHP/Elasticsearch/Solr/GeoServer/Confluence/Drupal
# all explicitly run `id` and the exploit class reflects its stdout directly
# into the HTTP response body/JSON field) -- that's real, independently
# captured evidence (web:access full-haystack container logs, and now the
# network:packet capture), it just isn't literal-substring-matchable since
# the exact uid/gid numbers vary by container.
ADDITIONAL_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "T1059": [
        # `id` command output reflected into a response/log/packet capture --
        # e.g. "uid=0(root) gid=0(root) groups=0(root)". Effectively unfakeable
        # by coincidental web content; every Class-A scenario's prompt (see
        # exec_chain.py's 2026-07-24 comment block) explicitly runs `id` as
        # its own documented verification step.
        #
        # A self-callback pattern (target curls back to a listener in our own
        # attack container) was tried and abandoned 2026-07-24 for scenarios
        # whose real vulhub-documented technique is blind: it required
        # Docker-published inbound ports reachable from the lab network, and
        # Docker Desktop for Mac's own proxy/vpnkit layer resets genuinely
        # externally-LAN-sourced connections to published ports (confirmed
        # live, independent of macOS's Application Firewall and pf, both
        # checked clean). Rather than keep working around that, every
        # previously-blind scenario was swapped for a different real vulhub
        # CVE whose own documented exploit reflects command output directly
        # in the response (see exec_chain.py: vuln_hugegraph_rce,
        # vuln_druid_rce, vuln_shellshock_rce, vuln_jimureport_rce,
        # vuln_ajreport_rce, vuln_spring4shell_rce, vuln_docker_api_rce).
        r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)",
    ],
}


def validate_capture_signals(scenario: str, telemetry: dict[str, list[str]]) -> dict:
    """Validate that a capture has TECHNIQUE-SPECIFIC signals for its ground
    truth techniques.

    Returns:
        {valid: bool, coverage: float, found: [str], missing: [str],
         unchecked: [str], techniques_checked: int}

    `coverage` is computed only over the CHECKABLE subset (techniques with an
    `EXPECTED_SIGNALS` entry) — `unchecked` techniques (no entry exists yet)
    are never silently credited as found, and never count against the capture
    either; they're an honest gap in verification coverage, not a pass/fail.

    A prior version of this function had a "broader attack evidence" fallback:
    if a technique's specific keywords didn't match, or it had no
    `EXPECTED_SIGNALS` entry at all, it fell back to checking whether ANY of
    ~35 generic words ("error", "failed", "denied", "exception",
    "unauthorized"...) appeared ANYWHERE in the capture's combined telemetry —
    and if so, credited EVERY missing/unchecked technique as "found",
    regardless of which technique it was or whether that word had anything to
    do with it. Found live 2026-07-22 (GATE-D ablation Part II-A, prompted by
    a user architecture question about whether captures are genuinely
    replayable): `meta3_ssh_brute`'s capture — which has NO SSH telemetry
    source at all, only thin FTP auth-failure noise, web-scan noise, and
    generic Windows process events — was certified `coverage: 1.0, valid:
    true, found: [T1110.003, T1078, T1059]` purely because one FTP `530`
    failure line matched "denied"/"failed" once. Checked across all 422
    on-disk captures with this fallback still active: 352 (83.4%) showed
    `coverage: 1.00` — a near-universal rubber stamp, not a real quality
    signal. This gate exists specifically so downstream consumers (the
    89-scenario ablation corpus, any future re-ablation) can trust that a
    capture marked valid actually contains evidence of what it claims to —
    the whole point of "capture once, replay for blue/purple forever" is
    that the capture is trustworthy without needing a fresh live check.
    """
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS
    except ImportError:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    sc = SCENARIOS.get(scenario, {})
    gt = sc.get("detect_ground_truth", [])
    if not gt:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    all_existing = " ".join(line for lines in telemetry.values() for line in lines)

    found = []
    missing_techniques = []
    unchecked = []
    for technique in gt:
        expected = EXPECTED_SIGNALS.get(technique)
        extra_patterns = ADDITIONAL_SIGNAL_PATTERNS.get(technique, [])
        if not expected and not extra_patterns:
            unchecked.append(technique)
            continue

        _sourcetype, expected_lines = expected or ("", [])
        # A technique is found only if ONE example line's FULL field set is
        # present (AND within that line's own tokens), not any single token
        # pooled across every example (OR across lines is fine — two example
        # lines are two legitimate variants of the same technique).
        #
        # Found live 2026-07-23 (first scenario of the post-fix recapture run,
        # kerberoast_to_da): pooling every field=value token across all lines
        # and accepting ANY single one anywhere in the telemetry let a bare,
        # generic token from one technique's example (e.g. T1053.005's
        # "Account=administrator") false-match a completely unrelated real
        # event (a Kerberoasting 4769 line that also happens to involve the
        # administrator account) — and a bare "EventCode=4662" (used for many
        # unrelated Windows auditing operations) false-matched T1003.006/DCSync
        # without its actually-discriminating
        # "Properties=Replication-Dir-Replication-Right" value ever appearing.
        # Both non-Kerberoasting ground-truth techniques were credited as
        # "found" purely from these coincidental generic-token overlaps.
        has_signal = False
        for line in expected_lines:
            line_tokens = {tok for tok in line.split() if "=" in tok}
            if line_tokens and all(tok in all_existing for tok in line_tokens):
                has_signal = True
                break
        if not has_signal:
            for pattern in extra_patterns:
                if re.search(pattern, all_existing):
                    has_signal = True
                    break
        if has_signal:
            found.append(technique)
        else:
            missing_techniques.append(technique)

    checked_n = len(found) + len(missing_techniques)
    coverage = len(found) / checked_n if checked_n else 0.0
    return {
        "valid": checked_n > 0 and len(found) == checked_n,
        "coverage": round(coverage, 3),
        "found": found,
        "missing": missing_techniques,
        "unchecked": unchecked,
        "techniques_checked": checked_n,
    }
