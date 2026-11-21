"""Proxmox SSH -> LXC -> docker transport for the Splunk container (LXC 301 by default).

Reuses the repo's one host transport convention (``scripts/lab_host.py``: `ssh -> pct exec`),
but through the named keys rather than a second hardcoded host, and with no shell interpolation
of anything the caller did not validate.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

DEFAULT_LXC = "301"
DEFAULT_CONTAINER = "splunk"
_SAFE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def proxmox_host() -> str:
    return os.environ.get("LAB_PROXMOX_HOST", "10.0.0.203")


def ssh_key() -> str:
    return os.path.expanduser(os.environ.get("LAB_SSH_KEY", "~/.ssh/portal-lab_id_ed25519"))


def ssh_user() -> str:
    return os.environ.get("PROXMOX_SSH_USER", "root")


def _guarded(value: str, what: str) -> str:
    if not _SAFE.match(value):
        raise ValueError(f"refusing unsafe {what}: {value!r}")
    return value


def ssh_argv(remote_cmd: str) -> list[str]:
    return [
        "ssh",
        "-i",
        ssh_key(),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=15",
        f"{ssh_user()}@{proxmox_host()}",
        remote_cmd,
    ]


def in_container(lxc_id: str, container: str, inner: str, user: str = "") -> str:
    lxc = _guarded(lxc_id, "lxc id")
    box = _guarded(container, "container name")
    as_user = f"-u {_guarded(user, 'user')} " if user else ""
    return f"pct exec {lxc} -- docker exec {as_user}-i {box} {inner}"


def install_app(
    app_root: Path, *, lxc_id: str = DEFAULT_LXC, container: str = DEFAULT_CONTAINER
) -> str:
    """Stream the rendered app into the container's apps dir (idempotent overwrite)."""
    remote = in_container(lxc_id, container, "tar -C /opt/splunk/etc/apps -xf -", user="splunk")
    tar = subprocess.Popen(
        ["tar", "-C", str(app_root.parent), "-cf", "-", app_root.name],
        stdout=subprocess.PIPE,
        env={**os.environ, "COPYFILE_DISABLE": "1"},  # no macOS ._ metadata files in the app
    )
    assert tar.stdout is not None
    run = subprocess.run(ssh_argv(remote), stdin=tar.stdout, capture_output=True, text=True)
    tar.stdout.close()
    tar.wait()
    if run.returncode != 0:
        raise RuntimeError(f"app install failed: {run.stderr.strip()[:400]}")
    return f"installed {app_root.name} into {container}:/opt/splunk/etc/apps"


def restart(*, lxc_id: str = DEFAULT_LXC, container: str = DEFAULT_CONTAINER) -> str:
    box = _guarded(container, "container name")
    run = subprocess.run(
        ssh_argv(f"pct exec {_guarded(lxc_id, 'lxc id')} -- docker restart {box}"),
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        raise RuntimeError(f"restart failed: {run.stderr.strip()[:400]}")
    return f"restarted {container} in LXC {lxc_id}"


def show_config(conf: str, *, lxc_id: str = DEFAULT_LXC, container: str = DEFAULT_CONTAINER) -> str:
    cmd = in_container(
        lxc_id, container, f"/opt/splunk/bin/splunk show config {_guarded(conf, 'conf name')}"
    )
    run = subprocess.run(ssh_argv(cmd), capture_output=True, text=True)
    return run.stdout + run.stderr
