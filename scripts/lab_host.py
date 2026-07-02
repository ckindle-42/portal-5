#!/usr/bin/env python3
"""One transport to the live Proxmox lab host — ssh -> `pct exec 112`.

This is the single source of truth for host access. Every other module that
needs to touch LXC 112 (vulhub) on the Proxmox host (10.0.0.203) goes through
`_host_exec`. Do not duplicate the ssh invocation elsewhere.
"""

from __future__ import annotations

import os
import subprocess

PROXMOX_HOST = os.environ.get("LAB_PROXMOX_HOST", "10.0.0.203")
LAB_LXC_ID = os.environ.get("LAB_VULHUB_LXC_ID", "112")
_SSH_KEY = os.path.expanduser(os.environ.get("LAB_SSH_KEY", "~/.ssh/portal-lab_id_ed25519"))


def _host_exec(cmd: str, timeout: int = 30) -> dict:
    """Run `cmd` inside LXC 112 on the Proxmox host via ssh -> pct exec. Read-only by convention
    unless the caller's cmd itself mutates host state. Returns {ok, output}."""
    try:
        r = subprocess.run(
            [
                "ssh",
                "-i",
                _SSH_KEY,
                "-o",
                "StrictHostKeyChecking=no",
                f"root@{PROXMOX_HOST}",
                f"pct exec {LAB_LXC_ID} -- {cmd}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}
    except Exception as exc:
        return {"ok": False, "output": str(exc)}


def _proxmox_exec(cmd: str, timeout: int = 30) -> dict:
    """Run `cmd` on the Proxmox host itself (not inside LXC 112), e.g. `pct status 112`."""
    try:
        r = subprocess.run(
            [
                "ssh",
                "-i",
                _SSH_KEY,
                "-o",
                "StrictHostKeyChecking=no",
                f"root@{PROXMOX_HOST}",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}
    except Exception as exc:
        return {"ok": False, "output": str(exc)}
