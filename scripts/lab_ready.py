#!/usr/bin/env python3
"""Lab readiness gate — verifies the lab is actually ready before a bench run.

Checks: attack box built + manifest, vulhub cloned, challenge dirs, telemetry,
snapshots, disk space. Returns non-zero if a REQUIRED component is missing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    """Load repository lab configuration before deriving readiness constants."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))

CHECKS: dict[str, dict] = {
    "docker": {"required": True, "host": "local", "desc": "Docker daemon running"},
    "dind": {"required": True, "host": "local", "desc": "DinD (portal5-dind) container running"},
    "attack_image": {
        "required": True,
        "host": "local",
        "desc": "Attack image (portal5-attack) present",
    },
    "attack_manifest": {
        "required": True,
        "host": "local",
        "desc": "Attack image satisfies current lab-exercise tool contract",
    },
    "vulhub_clone": {
        "required": True,
        "host": "local",
        "desc": "vulhub repo cloned (~1,920 CVE dirs)",
    },
    "challenge_dirs": {
        "required": True,
        "host": "local",
        "desc": "Challenge compose dirs materialized",
    },
    "disk": {"required": True, "host": "local", "desc": "Sufficient disk space (>10GB free)"},
    "ollama": {"required": False, "host": "local", "desc": "Ollama running + models resident"},
    "dc_reachable": {
        "required": True,
        "host": "bridge",
        "desc": "DC (10.10.11.21:445) reachable from sandbox",
    },
    "srv_reachable": {
        "required": True,
        "host": "bridge",
        "desc": "SRV (10.10.11.33:445) reachable from sandbox",
    },
    "web_reachable": {
        "required": True,
        "host": "bridge",
        "desc": "Web (10.10.11.50:8080) reachable from sandbox",
    },
    "snapshots": {
        "required": False,
        "host": "proxmox",
        "desc": "Clean-baseline VM snapshots exist",
    },
}


def _check_attack_image() -> str:
    import subprocess

    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "portal5-dind",
                "docker",
                "image",
                "inspect",
                "portal5-attack:latest",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "GREEN" if result.returncode == 0 else "RED"
    except (OSError, subprocess.SubprocessError):
        return "RED"


def _check_dind() -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "portal5-dind"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "GREEN" if result.returncode == 0 and result.stdout.strip() == "true" else "RED"
    except (OSError, subprocess.SubprocessError):
        return "RED"


def _check_attack_manifest() -> str:
    """Reject absent, incomplete, or stale manifests in the actual DinD image."""
    import subprocess

    contract_path = REPO_ROOT / "config" / "attack_image_contract.json"
    expected_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "portal5-dind",
                "docker",
                "run",
                "--rm",
                "portal5-attack:latest",
                "cat",
                "/opt/portal5-attack.manifest.json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        manifest = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return "RED"
    if manifest.get("contract_sha256") != expected_hash or manifest.get("ready") is not True:
        return "RED"
    checks = [
        *manifest.get("tools", {}).values(),
        *manifest.get("files", {}).values(),
        *manifest.get("runtime_checks", {}).values(),
    ]
    return "GREEN" if checks and all(value is True for value in checks) else "RED"


def _check_vulhub_clone() -> str:
    try:
        from scripts.lab_host import _host_exec

        root = os.environ.get("LAB_VULHUB_HOST_ROOT", "/opt/vulhub")
        result = _host_exec(f"test -d {root}/.git && echo EXISTS", timeout=15)
        if result.get("ok") and "EXISTS" in result.get("output", ""):
            return "GREEN"
    except Exception:
        pass
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
            [
                "curl",
                "-sk",
                f"{os.environ.get('PROXMOX_URL', 'https://10.10.11.5:8006')}/api2/json/nodes",
            ],
            capture_output=True,
            text=True,
            timeout=10,
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


def _proxmox_vm_running(vmid: int, kind: str = "qemu") -> str:
    try:
        from scripts.lab_host import _proxmox_exec

        command = "pct status" if kind == "lxc" else "qm status"
        result = _proxmox_exec(f"{command} {vmid}", timeout=15)
        status = result.get("output", "").lower()
        return "GREEN" if result.get("ok") and "running" in status else "RED"
    except Exception:
        return "AMBER"


def _check_web_reachable() -> str:
    return _check_port_reachable(os.environ.get("LAB_TARGET_WEB", "10.10.11.50"), 8080)


def _check_dc_reachable() -> str:
    return _check_port_reachable("10.10.11.21", 445)


def _check_srv_reachable() -> str:
    return _check_port_reachable("10.10.11.33", 445)


def _check_port_reachable(host: str, port: int) -> str:
    """Probe TCP from the real disposable attack-container boundary.

    GNU ``timeout`` exits 125 when launched as PID 1 in this image even though
    the same connection succeeds below a wrapper shell. Netcat provides its
    own bounded connect timeout and therefore reports the service outcome
    directly instead of a container-init artifact.
    """
    try:
        r = __import__("subprocess").run(
            [
                "docker",
                "exec",
                "portal5-dind",
                "docker",
                "run",
                "--rm",
                "--net",
                "bridge",
                "portal5-attack:latest",
                "nc",
                "-z",
                "-w",
                "3",
                host,
                str(port),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "GREEN" if r.returncode == 0 else "RED"
    except Exception:
        return "AMBER"


def _check_snapshots() -> str:
    try:
        from scripts.lab_host import _proxmox_exec
    except Exception:
        return "AMBER"
    vmids = [
        os.environ.get("LAB_DC_VMID", "110"),
        os.environ.get("LAB_SRV_VMID", "111"),
    ]
    for vmid in vmids:
        try:
            result = _proxmox_exec(f"qm listsnapshot {int(vmid)}", timeout=15)
            lines = [line for line in result.get("output", "").splitlines() if line.strip()]
            if not result.get("ok") or len(lines) < 2:
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
        return "AMBER"
    return "GREEN" if free > 10 else "RED"


def run_readiness() -> tuple[bool, list[dict]]:
    """Return (all_required_passed, check_results)."""
    results = []
    all_passed = True
    for cid, cfg in CHECKS.items():
        fn = globals().get(f"_check_{cid}")
        status = fn() if fn else "AMBER"
        results.append(
            {"check": cid, "desc": cfg["desc"], "status": status, "required": cfg["required"]}
        )
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
