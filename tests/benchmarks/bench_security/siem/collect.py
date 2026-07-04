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

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


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
                out["windows:security"] = [
                    line for line in r["output"].splitlines() if line.strip()
                ]

    return out
