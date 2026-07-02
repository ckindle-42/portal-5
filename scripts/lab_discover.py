#!/usr/bin/env python3
"""Phase 0 — read-only discovery of live lab host state (LXC 112, vulhub).

Probes the Proxmox host via the one proven transport (_host_exec / _proxmox_exec in
scripts/lab_host.py) and reports actual state. Writes nothing to the host and changes
no bench code — every later phase (resolution, spin-up, dispatch) builds on what this
reports, not on assumptions.

Usage: python3 -m scripts.lab_discover
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.lab_host import LAB_LXC_ID, PROXMOX_HOST, _host_exec, _proxmox_exec

REPO_ROOT = Path(__file__).resolve().parents[1]
_VULHUB_ROOTS = ["/opt/vulhub", "/root/vulhub", "/srv/vulhub", "~/vulhub"]
UPSTREAM_VULHUB_TOTAL = 328


def _lxc_running() -> bool:
    r = _proxmox_exec(f"pct status {LAB_LXC_ID}")
    return r.get("ok", False) and "status: running" in r.get("output", "").lower()


def _docker_up() -> bool:
    r = _host_exec("docker info", timeout=15)
    return r.get("ok", False) and "server version" in r.get("output", "").lower()


def _find_vulhub_root() -> tuple[str, int]:
    """Search likely vulhub roots on 112; return (root_or_empty, docker_compose_count)."""
    cmd = (
        "bash -lc 'for d in " + " ".join(_VULHUB_ROOTS) + "; do "
        # docker-compose.yml lives at root/category/env/docker-compose.yml (depth 3).
        # `; true` at the end so a missing later root (exit 1 from `[ -d ]`) doesn't make
        # the whole probe look like it failed even after an earlier root was found.
        '[ -d "$d" ] && echo "FOUND:$d" && find "$d" -maxdepth 3 -name docker-compose.yml | wc -l; done; true\''
    )
    r = _host_exec(cmd, timeout=30)
    if not r.get("ok"):
        return "", 0
    lines = r["output"].splitlines()
    for i, line in enumerate(lines):
        if line.startswith("FOUND:"):
            root = line[len("FOUND:") :].strip()
            count = 0
            if i + 1 < len(lines):
                try:
                    count = int(lines[i + 1].strip())
                except ValueError:
                    count = 0
            return root, count
    return "", 0


def _top_level_categories(root: str) -> list[str]:
    if not root:
        return []
    r = _host_exec(
        f"bash -lc 'ls -1d {root}/*/ 2>/dev/null | xargs -n1 basename | head -400'", timeout=15
    )
    if not r.get("ok"):
        return []
    return [ln.strip() for ln in r["output"].splitlines() if ln.strip() and not ln.startswith(".")]


def _docker_ps() -> str:
    r = _host_exec("docker ps --format '{{.Names}}: {{.Ports}}'", timeout=15)
    return r.get("output", "").strip() if r.get("ok") else ""


def _used_ports() -> list[int]:
    from scripts.lab_targets import _get_used_ports

    return sorted(_get_used_ports())


def discover() -> dict:
    lxc_running = _lxc_running()
    docker_up = _docker_up() if lxc_running else False
    vulhub_root, compose_count = _find_vulhub_root() if docker_up else ("", 0)
    categories = _top_level_categories(vulhub_root)
    ps_output = _docker_ps() if docker_up else ""
    ports = _used_ports() if docker_up else []

    return {
        "host": PROXMOX_HOST,
        "lxc_id": LAB_LXC_ID,
        "lxc_running": lxc_running,
        "docker_up": docker_up,
        "vulhub_root": vulhub_root,
        "vulhub_envs_found": compose_count,
        "vulhub_envs_upstream_total": UPSTREAM_VULHUB_TOTAL,
        "vulhub_top_level_categories": categories,
        "docker_ps": ps_output,
        "used_host_ports": ports,
    }


def main() -> int:
    result = discover()
    out_path = REPO_ROOT / "lab_discovery.json"
    out_path.write_text(json.dumps(result, indent=2))

    print("Lab discovery report")
    print(f"  Proxmox host:      {result['host']}")
    print(f"  LXC {result['lxc_id']} running:  {result['lxc_running']}")
    print(f"  Docker daemon up:  {result['docker_up']}")
    print(f"  Vulhub root:       {result['vulhub_root'] or '(not found)'}")
    print(
        f"  Vulhub envs found: {result['vulhub_envs_found']}"
        f" / {result['vulhub_envs_upstream_total']} upstream"
    )
    print(f"  Categories:        {len(result['vulhub_top_level_categories'])}")
    print(f"  Used host ports:   {result['used_host_ports']}")
    print(f"  Written to:        {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
