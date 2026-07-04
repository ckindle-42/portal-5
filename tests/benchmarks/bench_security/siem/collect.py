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

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


def collect_target(target_ip: str, kind: str, *, since_epoch: float, dry_run: bool = False) -> dict:
    """Return {sourcetype: [lines]} scraped from the target/compose host since scenario start.

    kind: 'web' (vulhub/containers) | 'linux' (hosts) | 'windows' (AD).
    For ephemeral containers we read the compose host's captured logs (container may be gone).
    """
    out: dict[str, list[str]] = {}
    if dry_run:
        return {"web:access": ["[dry-run] GET /?x=${jndi:ldap://...} 200"]}

    if kind in ("web", "container", "linux"):
        import base64

        from scripts.lab_host import _host_exec

        def _host_exec_script(script: str, timeout: int) -> dict:
            # _host_exec runs `ssh host "pct exec <ctid> -- {cmd}"` — any bare
            # pipe/redirect/quote in `cmd` gets parsed by the shell on the
            # PROXMOX HOST (found live 2026-07-03, same issue as the port-remap
            # override-file write earlier today), not inside the LXC, so a
            # multi-stage pipeline like this silently runs its later stages on
            # the host instead of the container host. base64 + `sh -c` sidesteps
            # all of that regardless of what the script contains.
            b64 = base64.b64encode(script.encode()).decode()
            return _host_exec(f'sh -c "echo {b64} | base64 -d | sh"', timeout=timeout)

        since = int(since_epoch)
        if kind in ("web", "container"):
            # `docker ps -q` (currently-running containers) piped through xargs,
            # not a fixed `--filter ancestor=...` tag that never matched any real
            # vulhub image name — `--since @<epoch>` scopes the LOG LINES, not
            # which containers get checked, so this is correct regardless of
            # which specific CVE container is up right now.
            # `docker logs --since` doesn't accept `@<epoch>` (that's a `docker
            # run`-ism) — it wants RFC3339 or a duration. A duration computed
            # from `date +%s` ON THE REMOTE HOST at execution time avoids any
            # clock-skew/timezone mismatch a precomputed RFC3339 string would risk.
            r = _host_exec_script(
                f"docker ps -q | xargs -r -I{{}} "
                f"docker logs --since $(( $(date +%s) - {since} ))s {{}} 2>&1 | tail -500",
                timeout=30,
            )
            if r.get("ok") and r.get("output", "").strip():
                out["web:access"] = [line for line in r["output"].splitlines() if line.strip()]

        if kind in ("linux", "web", "container"):
            r = _host_exec_script(
                f"ausearch -m EXECVE -ts $(date -d @{since} '+%H:%M:%S') 2>/dev/null | tail -500 || true",
                timeout=30,
            )
            if r.get("ok") and r.get("output", "").strip():
                out["linux:auditd"] = [line for line in r["output"].splitlines() if line.strip()]

    # Windows AD events: WinEventBackend already reads these; collection forwards them to Splunk too.
    # Sandbox MCP (portal5-attack, network-enabled) is the right channel here — nxc needs
    # attacker-network reach to the DC over WinRM, unlike the docker/auditd host access above.
    if kind in ("windows", "ad"):
        mcp_call = _get_mcp_call()
        if mcp_call:
            ids = os.environ.get("LAB_WIN_EVENT_IDS", "4769,4768,4662,4698,4625,4771")
            ps = (
                f"Get-WinEvent -FilterHashtable @{{LogName='Security';Id={ids}}} "
                f"-MaxEvents 50 | Format-List Id,TimeCreated,Message"
            )
            lab_dc = os.environ.get("LAB_TARGET_DC", "10.10.11.21")
            lab_pass = os.environ.get("LAB_ADMIN_PASS", "LabAdmin1!")
            # -X (not -x) — cmd.exe doesn't know PowerShell cmdlets (same fix as
            # WinEventBackend.query in blue.py; this copy had drifted out of sync).
            code = f"nxc winrm {lab_dc} -u administrator -p '{lab_pass}' -X \"{ps}\" 2>&1"
            r = mcp_call(code, timeout=90)
            if r.get("ok") and r.get("output", "").strip():
                stdout = unwrap_mcp_stdout(r["output"])
                normalized = _normalize_windows_security_events(stdout)
                if normalized:
                    out["windows:security"] = normalized

    return out
