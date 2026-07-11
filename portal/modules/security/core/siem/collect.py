"""Collect raw telemetry off a lab target after a scenario runs, for HEC shipping.

web/linux collection runs via _host_exec (admin SSH -> pct exec on the vulhub
LXC where docker/auditd actually live) — NOT the sandbox MCP execute_bash
channel red uses (found live 2026-07-03: that channel is the portal5-attack
Kali box, network-enabled to reach the lab as an attacker would, but it has no
`docker` binary at all — it's not the container host, it's the thing attacking
the container host). windows collection stays on the sandbox MCP, correctly —
nxc genuinely needs attacker-network reach to the DC over WinRM.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def unwrap_mcp_stdout(raw: str) -> str:
    """Unwrap the sandbox MCP execute_bash tool's own JSON response envelope.

    `_mcp_call` (bench_lab_exec.py) returns the execute_bash tool's raw text
    result verbatim — which for that tool is itself a JSON object,
    `{"success": bool, "stdout": "...", "stderr": "...", ...}`, not the plain
    command output. Found live 2026-07-04: every nxc/Get-WinEvent call site
    (WinEventBackend.query, _fetch_blue_telemetry's live fallback, and this
    module's windows-event collector) was treating that JSON blob as if it
    were the raw nxc output — `"EventID" in text` / regex field extraction
    were matching against `{\\n  "success": true,\\n  "stdout": "...` with the
    real content's newlines still JSON-escaped (`\\n` as two literal
    characters, not a line break), so line-based parsing silently saw one
    giant line instead of the actual per-event text. Best-effort: falls back
    to the raw string unchanged if it isn't valid JSON or has no "stdout" key,
    so a genuinely-plain-text caller isn't broken by this.
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if isinstance(obj, dict) and "stdout" in obj:
        return obj["stdout"]
    return raw


# Field names each SPL detection (siem/spl_detections.yaml) actually filters on,
# per EventCode. Get-WinEvent's raw `Message` text uses human-readable labels
# ("Account Name:", "Ticket Encryption Type:") that never match those SPL
# filters as-is — Splunk's default key=value auto-extraction only works if we
# ship it already normalized to EventCode=/TicketEncryptionType=/etc.
_WINDOWS_EVENT_FIELD_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "4769": [  # Kerberoasting (T1558.003)
        ("TicketEncryptionType", r"Ticket Encryption Type:\s*(\S+)"),
        ("ServiceName", r"Service Name:\s*(\S+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4768": [  # AS-REP roasting (T1558.004)
        ("PreAuthType", r"Pre-Authentication Type:\s*(\S+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4662": [  # DCSync (T1003.006)
        ("Properties", r"Properties:\s*(.+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4698": [  # Scheduled task persistence (T1053.005)
        ("TaskName", r"Task Name:\s*(\S+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4625": [  # Failed logon (T1110.003, password spray)
        ("IpAddress", r"Source Network Address:\s*(\S+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4771": [  # Kerberos pre-auth failed (T1110.003, password spray)
        ("IpAddress", r"Client Address:\s*(\S+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
    "4688": [  # Process creation (T1059/T1059.004/T1548.001/T1068 command exec + privesc)
        ("NewProcessName", r"New Process Name:\s*(\S+)"),
        ("CommandLine", r"Process Command Line:\s*(.+)"),
        ("Account", r"Account Name:\s*(\S+)"),
    ],
}


# nxc prefixes EVERY output line with its own fixed-width status columns —
# "WINRM   10.10.11.21   5985   WIN-MVQO0PT39IO  <actual content>" — so "Id"
# is never at true line-start the way Format-List normally produces it.
_NXC_LINE_PREFIX = re.compile(r"^[A-Za-z0-9_-]+\s+[\d.]+\s+\d+\s+\S+\s{2,}", re.MULTILINE)


def strip_nxc_line_prefix(text: str) -> str:
    """Strip nxc's per-line status-column prefix, exposing the real PowerShell
    output underneath. Shared with blue.py's WinEventBackend.query and
    _fetch_blue_telemetry's live nxc fallback — both feed this text straight to
    a model as "telemetry," and the unstripped prefix was real noise on every
    single line, not just a formatting nuisance for this module's own parser.
    """
    return _NXC_LINE_PREFIX.sub("", text)


def _normalize_windows_security_events(raw_text: str) -> list[str]:
    """Turn Get-WinEvent's `Format-List Id,TimeCreated,Message` output into flat
    EventCode=... key=value lines that match what siem/spl_detections.yaml's SPL
    queries actually filter on.

    Best-effort: an event whose EventCode we recognize but whose expected fields
    don't match (Windows message text formatting drift, redacted fields, etc.)
    still ships as `EventCode=<id>` alone rather than being dropped — a partial
    match is still evidence the event fired, even if a specific SPL field filter
    then can't match it.
    """
    raw_text = _NXC_LINE_PREFIX.sub("", raw_text)
    blocks = re.split(r"(?=^\s*Id\s*:\s*\d+)", raw_text, flags=re.MULTILINE)
    lines: list[str] = []
    for block in blocks:
        m = re.search(r"^\s*Id\s*:\s*(\d+)", block, re.MULTILINE)
        if not m:
            continue
        event_code = m.group(1)
        fields = [f"EventCode={event_code}"]
        for name, pattern in _WINDOWS_EVENT_FIELD_PATTERNS.get(event_code, []):
            fm = re.search(pattern, block)
            if fm:
                fields.append(f"{name}={fm.group(1)}")
        lines.append(" ".join(fields))
    return lines


def _get_mcp_call():
    """Lazy import _mcp_call to avoid circular imports."""
    try:
        from tests.benchmarks.bench_lab_exec import _mcp_call

        return _mcp_call
    except ImportError:
        return None


def enable_meta3_audit_policies(target_ip: str) -> dict:
    """Enable process creation auditing and command-line logging on Meta3.

    Meta3 (Metasploitable3-Windows) has process creation auditing OFF by default.
    Without it, exploitation techniques (T1059, T1059.004, T1548.001, T1068)
    generate zero Windows Security Event Log evidence.

    Enables:
    1. Process Creation audit subcategory (EventCode 4688)
    2. Command-line logging in process creation events (registry key)

    Returns:
        {ok: bool, audit_enabled: bool, cmdline_logging: bool, error: str}
    """
    mcp_call = _get_mcp_call()
    if not mcp_call:
        return {"ok": False, "error": "MCP call not available"}

    import base64

    meta3_user = os.environ.get("LAB_META3_USER", "vagrant")
    meta3_pass = os.environ.get("LAB_META3_PASS", "vagrant")

    def _winrm_ps(ps_script: str, timeout: int) -> str:
        b64 = base64.b64encode(ps_script.encode("utf-16-le")).decode()
        code = (
            f"nxc winrm {target_ip} -u {meta3_user} -p {meta3_pass} "
            f'-X "powershell -NoProfile -EncodedCommand {b64}" 2>&1'
        )
        r = mcp_call(code, timeout=timeout)
        if not (r.get("ok") and r.get("output", "").strip()):
            return ""
        return strip_nxc_line_prefix(unwrap_mcp_stdout(r["output"]))

    result = {"ok": False, "audit_enabled": False, "cmdline_logging": False, "error": ""}

    # Enable Process Creation auditing
    audit_out = _winrm_ps(
        "auditpol /set /subcategory:'Process Creation' /success:enable 2>&1; "
        "auditpol /get /subcategory:'Process Creation' 2>&1",
        60,
    )
    result["audit_enabled"] = (
        "enable" in audit_out.lower() or "process creation" in audit_out.lower()
    )

    # Enable command-line logging in process creation events
    # Registry: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit
    # Value: ProcessCreationIncludeCmdLine_Enabled = 1
    cmd_out = _winrm_ps(
        "New-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System\\Audit' "
        "-Name 'ProcessCreationIncludeCmdLine_Enabled' -Value 1 -PropertyType DWord -Force 2>&1; "
        "Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System\\Audit' "
        "-Name 'ProcessCreationIncludeCmdLine_Enabled' 2>&1",
        60,
    )
    result["cmdline_logging"] = "1" in cmd_out or "ProcessCreationIncludeCmdLine" in cmd_out

    result["ok"] = result["audit_enabled"] or result["cmdline_logging"]
    if not result["ok"]:
        result["error"] = (
            f"Failed to enable audit policies. audit_out={audit_out[:200]}, cmd_out={cmd_out[:200]}"
        )

    return result


def collect_target(
    target_ip: str,
    kind: str,
    *,
    since_epoch: float,
    dry_run: bool = False,
    target_port: int | None = None,
    lxc_id: str | None = None,
) -> dict:
    """Return {sourcetype: [lines]} scraped from the target/compose host since scenario start.

    kind: 'web' (vulhub/containers) | 'linux' (hosts) | 'windows' (AD).
    For ephemeral containers we read the compose host's captured logs (container may be gone).
    target_port: if set, collect only from the container serving this port.
    lxc_id: Proxmox LXC ID to collect from (default: vulhub LXC 112).
        Set to '300' for MBPTL targets.
    """
    out: dict[str, list[str]] = {}
    if dry_run:
        return {"web:access": ["[dry-run] GET /?x=${jndi:ldap://...} 200"]}

    if kind in ("web", "container", "linux"):
        import base64

        from scripts.lab_host import _host_exec_lxc

        # Use the correct LXC for collection (default: vulhub 112, MBPTL: 300)
        _target_lxc = lxc_id or "112"

        def _exec_fn(cmd: str, timeout: int = 30) -> dict:
            return _host_exec_lxc(cmd, lxc_id=_target_lxc, timeout=timeout)

        def _host_exec_script(script: str, timeout: int) -> dict:
            b64 = base64.b64encode(script.encode()).decode()
            return _exec_fn(f'sh -c "echo {b64} | base64 -d | sh"', timeout=timeout)

        since = int(since_epoch)
        if kind in ("web", "container"):
            # FULL HAYSTACK: collect ALL docker container logs from the host.
            # A SOC analyst sees everything — all containers, all services —
            # and must find the attack signal in that noise.
            r = _host_exec_script(
                "for name in $(docker ps --format '{{.Names}}'); do "
                'echo "--- container: $name ---"; '
                f'docker logs --since $(( $(date +%s) - {since} ))s "$name" 2>&1; '
                "done | tail -1000",
                timeout=60,
            )
            if r.get("ok") and r.get("output", "").strip():
                out["web:access"] = [line for line in r["output"].splitlines() if line.strip()]

            # Also collect web server access/error/auth logs from inside ALL containers.
            r2 = _host_exec_script(
                "for cid in $(docker ps -q); do "
                "docker exec $cid sh -c '"
                "find /var/log /usr/local/tomcat/logs /usr/local/nginx/logs "
                "/var/log/apache2 /var/log/nginx /var/log/httpd /var/log/lighttpd "
                "/var/log/caddy /tmp /opt/*/logs /usr/local/*/logs "
                "-maxdepth 3 "
                '\\( -name "*access*" -o -name "*request*" -o -name "*error*" '
                '-o -name "*auth*" -o -name "*syslog*" -o -name "*messages*" \\) '
                '\\( -name "*.log" -o -name "*.txt" -o -name "*.log.*" \\) '
                "-type f 2>/dev/null"
                "' 2>/dev/null | while read logfile; do "
                'docker exec $cid cat "$logfile" 2>/dev/null; '
                "done; "
                "done | tail -500",
                timeout=60,
            )
            if r2.get("ok") and r2.get("output", "").strip():
                access_lines = [
                    line
                    for line in r2["output"].splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                if access_lines:
                    out.setdefault("web:access", []).extend(access_lines)

            # System-level logs from the host (auth, syslog, audit)
            r3 = _host_exec_script(
                f"cat /var/log/auth.log 2>/dev/null | tail -100; "
                f"cat /var/log/syslog 2>/dev/null | tail -100; "
                f"journalctl --since @{since} -n 100 --no-pager 2>/dev/null || true",
                timeout=30,
            )
            if r3.get("ok") and r3.get("output", "").strip():
                sys_lines = [line for line in r3["output"].splitlines() if line.strip()]
                if sys_lines:
                    out.setdefault("linux:syslog", []).extend(sys_lines)

        if kind in ("linux", "web", "container"):
            r = _host_exec_script(
                f"ausearch -m EXECVE -ts $(date -d @{since} '+%H:%M:%S') 2>/dev/null | tail -500 || true",
                timeout=30,
            )
            if r.get("ok") and r.get("output", "").strip():
                out["linux:auditd"] = [line for line in r["output"].splitlines() if line.strip()]

    # Windows AD events — capture ALL Security events.
    # In a real SOC, the analyst sees everything and must find the signal.
    # Two-pass collection: (1) all events compact (Id+TimeCreated) for the full
    # picture, (2) attack-relevant events with full Message detail for grounding.
    if kind in ("windows", "ad"):
        mcp_call = _get_mcp_call()
        if mcp_call:
            import base64

            lab_dc = os.environ.get("LAB_TARGET_DC", "10.10.11.21")
            lab_pass = os.environ.get("LAB_ADMIN_PASS", "LabAdmin1!")
            # Pre-initialize nxc (first call creates workspace dirs in ephemeral sandbox)
            mcp_call(
                f"nxc winrm {lab_dc} -u administrator -p '{lab_pass}' -X \"whoami\" 2>&1",
                timeout=60,
            )

            # Pass 1: ALL events — compact format (Id + TimeCreated only).
            # This gives the model the full event landscape including background
            # noise (logon/logoff, privilege use, etc.) without blowing up output size.
            ps_all = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'} -MaxEvents 500 "
                "| ForEach-Object { $_.Id.ToString() + ' ' + $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') }"
            )
            b64_all = base64.b64encode(ps_all.encode("utf-16-le")).decode()
            code_all = (
                f"nxc winrm {lab_dc} -u administrator -p '{lab_pass}' "
                f'-X "powershell -NoProfile -EncodedCommand {b64_all}" 2>&1'
            )
            r_all = mcp_call(code_all, timeout=120)
            all_events: list[str] = []
            if r_all.get("ok") and r_all.get("output", "").strip():
                stdout_all = unwrap_mcp_stdout(r_all["output"])
                for line in stdout_all.splitlines():
                    line = strip_nxc_line_prefix(line).strip()
                    # Format: "4624 2026-07-06 10:30:45"
                    parts = line.split(None, 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        all_events.append(f"EventCode={parts[0]} TimeCreated={parts[1]}")

            # Pass 2: Attack-relevant events with full Message detail.
            # These are the events the model needs to examine closely.
            attack_ids = "4769,4768,4662,4698,4625,4771,4688,4702,4770,5140"
            ps_detail = (
                f"Get-WinEvent -FilterHashtable @{{LogName='Security';Id={attack_ids}}} "
                "-MaxEvents 100 | Format-List Id,TimeCreated,Message"
            )
            b64_detail = base64.b64encode(ps_detail.encode("utf-16-le")).decode()
            code_detail = (
                f"nxc winrm {lab_dc} -u administrator -p '{lab_pass}' "
                f'-X "powershell -NoProfile -EncodedCommand {b64_detail}" 2>&1'
            )
            r_detail = mcp_call(code_detail, timeout=120)
            detailed_events: list[str] = []
            if r_detail.get("ok") and r_detail.get("output", "").strip():
                stdout_detail = unwrap_mcp_stdout(r_detail["output"])
                detailed_events = _normalize_windows_security_events(stdout_detail)

            # Merge: all compact events + detailed attack events (detailed takes precedence).
            # The model sees the full landscape AND has the detail it needs for grounding.
            merged = list(all_events)  # copy
            detail_codes = set()
            for de in detailed_events:
                if "EventCode=" in de:
                    detail_codes.add(de.split("EventCode=")[1].split()[0])
            # Remove compact entries for event codes we have detailed versions of
            merged = [
                e
                for e in merged
                if not any(
                    f"EventCode={c}" in e and e.startswith(f"EventCode={c}") and "Account=" not in e
                    for c in detail_codes
                )
            ]
            merged.extend(detailed_events)

            if merged:
                out["windows:security"] = merged

    # meta3 (Metasploitable3-Windows, standalone Vagrant box, not domain-joined).
    # Capture ALL Security events + IIS/FTP logs — model must find the signal.
    if kind == "meta3":
        mcp_call = _get_mcp_call()
        if mcp_call:
            import base64

            meta3_user = os.environ.get("LAB_META3_USER", "vagrant")
            meta3_pass = os.environ.get("LAB_META3_PASS", "vagrant")

            # Pre-initialize nxc (first call creates workspace dirs — output is
            # just init noise, not command output). Second call gets real results.
            mcp_call(
                f'nxc winrm {target_ip} -u {meta3_user} -p {meta3_pass} -X "whoami" 2>&1',
                timeout=60,
            )

            def _winrm_ps(ps_script: str, timeout: int) -> str:
                b64 = base64.b64encode(ps_script.encode("utf-16-le")).decode()
                code = (
                    f"nxc winrm {target_ip} -u {meta3_user} -p {meta3_pass} "
                    f'-X "powershell -NoProfile -EncodedCommand {b64}" 2>&1'
                )
                r = mcp_call(code, timeout=timeout)
                if not (r.get("ok") and r.get("output", "").strip()):
                    return ""
                return strip_nxc_line_prefix(unwrap_mcp_stdout(r["output"]))

            def _real_log_lines(text: str) -> list[str]:
                return [
                    ln
                    for ln in text.splitlines()
                    if ln.strip()
                    and not ln.startswith("#")
                    and not ln.lstrip().startswith(("[*]", "[+]", "[-]"))
                ]

            # IIS access logs (T1190 — web exploit evidence)
            iis_out = _winrm_ps(
                "Get-ChildItem C:\\inetpub\\logs\\LogFiles\\W3SVC1 -ErrorAction SilentlyContinue "
                "| Sort LastWriteTime -Descending | Select -First 1 "
                "| Get-Content -Tail 500",
                90,
            )
            if iis_out:
                lines = _real_log_lines(iis_out)
                if lines:
                    out["web:access"] = lines

            # FTP service logs
            ftp_out = _winrm_ps(
                "Get-ChildItem C:\\inetpub\\logs\\LogFiles\\FTPSVC2 -ErrorAction SilentlyContinue "
                "| Sort LastWriteTime -Descending | Select -First 1 "
                "| Get-Content -Tail 500",
                90,
            )
            if ftp_out:
                lines = _real_log_lines(ftp_out)
                if lines:
                    out["ftp:access"] = lines

            # ALL Windows Security events — not just specific IDs.
            # In a real SOC, the analyst sees everything.
            proc_out = _winrm_ps(
                "Get-WinEvent -FilterHashtable @{LogName='Security'} "
                "-MaxEvents 200 -ErrorAction SilentlyContinue "
                "| Format-List Id,TimeCreated,Message",
                120,
            )
            if proc_out:
                normalized = _normalize_windows_security_events(proc_out)
                if normalized:
                    out["windows:security"] = normalized

    return out
