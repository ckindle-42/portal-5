"""Collect raw telemetry off a lab target after a scenario runs, for HEC shipping.

Uses the sandbox MCP execute_bash (same channel the red chain uses) to read logs.
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

    mcp_call = _get_mcp_call()
    if not mcp_call:
        return out

    if kind in ("web", "container"):
        r = mcp_call(
            f"docker logs --since {int(since_epoch)} $(docker ps -q --filter ancestor-scan) 2>&1 "
            f"| tail -500 || journalctl --since @{int(since_epoch)} -u docker 2>&1 | tail -500",
            timeout=30,
        )
        if r.get("ok") and r.get("output", "").strip():
            out["web:access"] = [line for line in r["output"].splitlines() if line.strip()]

    if kind in ("linux", "web", "container"):
        r = mcp_call(
            f"ausearch -m EXECVE -ts $(date -d @{int(since_epoch)} '+%H:%M:%S') 2>/dev/null "
            f"| tail -500 || true",
            timeout=30,
        )
        if r.get("ok") and r.get("output", "").strip():
            out["linux:auditd"] = [line for line in r["output"].splitlines() if line.strip()]

    # Windows AD events: WinEventBackend already reads these; collection forwards them to Splunk too
    if kind in ("windows", "ad"):
        ids = os.environ.get("LAB_WIN_EVENT_IDS", "4769,4768,4662,4698,4625,4771")
        ps = (
            f"Get-WinEvent -FilterHashtable @{{LogName='Security';Id={ids}}} "
            f"-MaxEvents 50 | Format-List Id,TimeCreated,Message"
        )
        lab_dc = os.environ.get("LAB_TARGET_DC", "10.10.11.21")
        lab_pass = os.environ.get("LAB_ADMIN_PASS", "LabAdmin1!")
        code = f"nxc winrm {lab_dc} -u administrator -p '{lab_pass}' -x \"{ps}\" 2>&1"
        r = mcp_call(code, timeout=90)
        if r.get("ok") and r.get("output", "").strip():
            out["windows:security"] = [line for line in r["output"].splitlines() if line.strip()]

    return out
