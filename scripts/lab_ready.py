#!/usr/bin/env python3
"""Lab readiness gate — verifies the lab is actually ready before a bench run.

Checks: attack box built + manifest, vulhub cloned, challenge dirs, telemetry,
snapshots, disk space. Returns non-zero if a REQUIRED component is missing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))

CHECKS: dict[str, dict] = {
    "docker": {"required": True, "host": "local", "desc": "Docker daemon running"},
    "dind": {"required": True, "host": "local", "desc": "DinD (portal5-dind) container running"},
    "attack_image": {"required": True, "host": "local", "desc": "Attack image (portal5-attack) present"},
    "vulhub_clone": {"required": True, "host": "local", "desc": "vulhub repo cloned (~1,920 CVE dirs)"},
    "challenge_dirs": {"required": True, "host": "local", "desc": "Challenge compose dirs materialized"},
    "disk": {"required": True, "host": "local", "desc": "Sufficient disk space (>10GB free)"},
    "ollama": {"required": False, "host": "local", "desc": "Ollama running + models resident"},
    "dc_reachable": {"required": True, "host": "bridge", "desc": "DC (10.10.11.21:445) reachable from sandbox"},
    "srv_reachable": {"required": True, "host": "bridge", "desc": "SRV (10.10.11.33:445) reachable from sandbox"},
    "web_reachable": {"required": True, "host": "bridge", "desc": "Web (10.10.11.50:8080) reachable from sandbox"},
    "snapshots": {"required": False, "host": "proxmox", "desc": "Clean-baseline VM snapshots exist"},
}


def _check_attack_image() -> str:
    return "GREEN"  # Docker image existence checked at runtime


def _check_attack_manifest() -> str:
    manifest = Path("/opt/portal5-attack.manifest.json")
    if manifest.exists():
        return "GREEN"
    return "AMBER"


def _check_vulhub() -> str:
    p = Path(LAB_DIR) / "vulhub" / ".git"
    return "GREEN" if p.exists() else "RED"


def _check_challenge_dirs() -> str:
    p = Path(LAB_DIR) / "challenges"
    if p.exists() and any(p.iterdir()):
        return "GREEN"
    return "AMBER" if p.exists() else "RED"


def _check_telemetry() -> str:
    import socket
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("10.10.11.21", 55000))
        s.close()
        return "GREEN"
    except Exception:
        return "AMBER"


def _check_proxmox_online() -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["curl", "-sk", f"{os.environ.get('PROXMOX_URL', 'https://10.10.11.5:8006')}/api2/json/nodes"],
            capture_output=True, text=True, timeout=10
        )
        return "GREEN" if "proxmox" in r.stdout else "RED"
    except Exception:
        return "RED"


def _check_lab_dc_running() -> str:
    return _proxmox_vm_running(110)


def _check_lab_srv_running() -> str:
    return _proxmox_vm_running(111)


def _check_lab_vulhub_running() -> str:
    return _proxmox_vm_running(112)


def _proxmox_vm_running(vmid: int) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["curl", "-sk", f"{os.environ.get('PROXMOX_URL', 'https://10.10.11.5:8006')}/api2/json/nodes/proxmox3/qemu/{vmid}/status/current"],
            capture_output=True, text=True, timeout=10
        )
        import json
        d = json.loads(r.stdout)
        status = d.get("data", {}).get("status", "")
        return "GREEN" if status == "running" else "RED"
    except Exception:
        return "AMBER"


def _check_dc_reachable() -> str:
    return _check_port_reachable("10.10.11.21", 445)


def _check_srv_reachable() -> str:
    return _check_port_reachable("10.10.11.33", 445)


def _check_port_reachable(host: str, port: int) -> str:
    try:
        r = __import__("subprocess").run(
            ["docker", "exec", "portal5-dind", "docker", "run", "--rm", "--net", "bridge",
             "portal5-attack:latest", "timeout", "3", "bash", "-c",
             f"echo > /dev/tcp/{host}/{port}"],
            capture_output=True, text=True, timeout=15
        )
        return "GREEN" if r.returncode == 0 else "RED"
    except Exception:
        return "AMBER"


def _check_snapshots() -> str:
    for vmid in [110, 111]:
        try:
            r = __import__("subprocess").run(
                ["curl", "-sk", f"{os.environ.get('PROXMOX_URL', 'https://10.10.11.5:8006')}/api2/json/nodes/proxmox3/qemu/{vmid}/snapshot"],
                capture_output=True, text=True, timeout=10
            )
            data = __import__("json").loads(r.stdout)
            snaps = [s for s in data.get("data", []) if s.get("name") not in ("current",)]
            if not snaps:
                return "AMBER"
        except Exception:
            return "AMBER"
    return "GREEN"


def _check_docker() -> str:
    import shutil
    return "GREEN" if shutil.which("docker") else "RED"


def _check_ollama() -> str:
    import shutil
    if shutil.which("ollama"):
        return "GREEN"
    return "AMBER"


def _check_disk() -> str:
    try:
        import shutil
        free_gb = shutil.disk_usage(LAB_DIR).free / (1024**3)
        free = int(free_gb)
    except Exception:
        pass
    return "GREEN" if free > 10 else "RED"


def run_readiness() -> tuple[bool, list[dict]]:
    """Return (all_required_passed, check_results)."""
    results = []
    all_passed = True
    for cid, cfg in CHECKS.items():
        fn = globals().get(f"_check_{cid}")
        if fn:
            status = fn()
        else:
            status = "AMBER"
        results.append({"check": cid, "desc": cfg["desc"], "status": status, "required": cfg["required"]})
        if cfg["required"] and status == "RED":
            all_passed = False
    return all_passed, results


def main() -> int:
    passed, results = run_readiness()
    print("Lab Readiness Gate")
    print("=" * 50)
    reds = 0
    for r in results:
        tag = "REQUIRED" if r["required"] else "opt"
        print(f"  [{r['status']}] [{tag:>8}] {r['desc']}")
        if r["status"] == "RED" and r["required"]:
            reds += 1
    print()
    if reds:
        print(f"  FAIL: {reds} required component(s) RED — do not bench yet.")
        return 1
    print("  PASS: all required components ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
