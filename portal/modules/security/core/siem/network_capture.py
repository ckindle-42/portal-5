"""Episode-scoped packet capture at the DinD attack boundary.

The attack containers are short-lived children of ``portal5-dind``. Capturing
on the privileged DinD namespace observes bytes that actually crossed the
attacker boundary, independent of whether a target service chose to log them.
The resulting PCAP is primary evidence; the text rendering is a convenience
view for blue's bounded investigation context.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from .capture_store import CAPTURE_DIR

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class NetworkCapture:
    episode_id: str
    target_host: str
    remote_path: str = ""
    pid_path: str = ""
    started: bool = False
    error: str = ""
    local_pcap_path: str | None = None
    telemetry: dict[str, list[str]] = field(default_factory=dict)


def _docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def start_network_capture(episode_id: str, target_host: str | None) -> NetworkCapture:
    """Start a packet capture before red dispatches its first command."""
    safe_id = _SAFE_ID_RE.sub("_", episode_id)[:120]
    capture = NetworkCapture(episode_id=safe_id, target_host=target_host or "")
    if os.environ.get("LAB_NETWORK_CAPTURE", "true").lower() not in ("1", "true", "yes"):
        capture.error = "network capture disabled"
        return capture
    try:
        if target_host:
            ipaddress.ip_address(target_host)
    except ValueError:
        capture.error = f"target host is not a literal IP: {target_host}"
        return capture

    dind = os.environ.get("PORTAL_DIND_CONTAINER", "portal5-dind")
    capture.remote_path = f"/tmp/portal5-captures/{safe_id}.pcap"
    capture.pid_path = f"/tmp/portal5-captures/{safe_id}.pid"
    host_filter = f" host {target_host}" if target_host else ""
    script = (
        "mkdir -p /tmp/portal5-captures; "
        f"tcpdump -i any -U -s 0 -w {capture.remote_path}{host_filter} "
        f">/tmp/portal5-captures/{safe_id}.log 2>&1 & "
        f"echo $! > {capture.pid_path}"
    )
    result = _docker("exec", dind, "sh", "-lc", script)
    if result.returncode != 0:
        capture.error = (result.stderr or result.stdout or "tcpdump start failed").strip()
        return capture
    capture.started = True
    time.sleep(0.2)
    return capture


def stop_network_capture(capture: NetworkCapture) -> NetworkCapture:
    """Stop capture, persist the PCAP, and render observed packet text."""
    if not capture.started:
        return capture
    dind = os.environ.get("PORTAL_DIND_CONTAINER", "portal5-dind")
    stop_script = (
        f"test -f {capture.pid_path} && kill -INT $(cat {capture.pid_path}) 2>/dev/null || true; "
        f"for i in 1 2 3 4 5; do kill -0 $(cat {capture.pid_path}) 2>/dev/null || break; "
        "sleep 0.1; done"
    )
    _docker("exec", dind, "sh", "-lc", stop_script)

    pcap_dir = CAPTURE_DIR / "pcap"
    pcap_dir.mkdir(parents=True, exist_ok=True)
    local_path = pcap_dir / f"{capture.episode_id}.pcap"
    copied = _docker("cp", f"{dind}:{capture.remote_path}", str(local_path), timeout=60)
    if copied.returncode != 0:
        # Docker Desktop can execute/read a file in DinD yet make `docker cp`
        # report it missing (observed live on its LinuxKit overlay). Exporting
        # the exact bytes through exec is slower but preserves the primary PCAP.
        encoded = _docker("exec", dind, "base64", capture.remote_path, timeout=60)
        if encoded.returncode == 0 and encoded.stdout.strip():
            try:
                local_path.write_bytes(base64.b64decode(encoded.stdout))
                copied = subprocess.CompletedProcess(
                    copied.args,
                    0,
                    copied.stdout,
                    copied.stderr,
                )
            except (OSError, ValueError):
                pass
    if copied.returncode == 0 and local_path.exists() and local_path.stat().st_size > 24:
        capture.local_pcap_path = str(local_path)
    else:
        capture.error = (copied.stderr or "empty packet capture").strip()

    rendered = _docker(
        "exec",
        dind,
        "tcpdump",
        "-nn",
        "-tttt",
        "-A",
        "-r",
        capture.remote_path,
        timeout=60,
    )
    if rendered.returncode in (0, 1) and rendered.stdout.strip():
        # Preserve observed bytes without manufacturing protocol outcomes.
        capture.telemetry["network:packet"] = rendered.stdout.splitlines()[:2000]
    elif not capture.error:
        capture.error = (rendered.stderr or "packet rendering produced no output").strip()
    capture.started = False
    return capture
