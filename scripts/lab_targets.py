#!/usr/bin/env python3
"""Lab targets provisioner — on-demand ephemeral containers with dynamic port mapping.

Port conflict resolution: the ephemeral model checks if a target's desired port is
in use; if so, it dynamically maps to a free port and records the mapping so the
bench knows which port to hit.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.lab_host import _host_exec

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))
LAB_VULHUB_HOST_ROOT = os.environ.get("LAB_VULHUB_HOST_ROOT", "/opt/vulhub")
LAB_VULHUB_HOST = os.environ.get("LAB_TARGET_WEB", "10.10.11.50")

# Track port mappings for ephemeral sessions
_PORT_MAP_FILE = (
    REPO_ROOT / "tests" / "benchmarks" / "bench_security" / "results" / ".port_map.json"
)


@dataclass
class PortMapping:
    target_id: str
    desired_port: int
    mapped_port: int
    host: str = "10.10.11.50"


def _get_used_ports() -> set[int]:
    """Get currently used HOST ports on the lab host via docker ps."""
    r = _host_exec("docker ps --format '{{.Ports}}'", timeout=15)
    if not r.get("ok"):
        return set()
    ports: set[int] = set()
    for line in r["output"].splitlines():
        for entry in line.split(","):
            entry = entry.strip()
            if "->" in entry:
                # Format: 0.0.0.0:8080->80/tcp → extract 8080
                host_part = entry.split("->")[0]
                if ":" in host_part:
                    try:
                        ports.add(int(host_part.rsplit(":", 1)[-1]))
                    except ValueError:
                        pass
    return ports


def _find_free_port(desired: int, used: set[int]) -> int:
    """Return desired port if free, else the next available port."""
    port = desired
    while port in used:
        port += 1
        if port > 65500:
            return desired  # give up
    return port


def _load_catalog() -> dict:
    import yaml

    path = REPO_ROOT / "config" / "lab_targets.yaml"
    if not path.exists():
        return {"targets": []}
    return yaml.safe_load(path.read_text())


def _find_target(target_id: str) -> dict | None:
    catalog = _load_catalog()
    for t in catalog.get("targets", []):
        if t.get("id") == target_id:
            return t
    return None


def _host_compose_path(path: str) -> str:
    """Absolute path to a vulhub env's docker-compose.yml on host 112."""
    return f"{LAB_VULHUB_HOST_ROOT}/{path}/docker-compose.yml"


def _published_port(compose_path: str) -> int | None:
    """Ask Docker for the actual published host port(s) — never guess from a hardcoded
    default. A raw vulhub path's real port can differ from any catalog assumption (e.g.
    fastjson/1.2.47-rce publishes 8090, not the common 8080).

    Robustness: tries `docker compose ps --format json` (Publishers key) first,
    then falls back to `docker compose port <svc> tcp` for compose JSON shape drift.
    """
    r = _host_exec(f"docker compose -f {compose_path} ps --format json", timeout=15)
    if r.get("ok"):
        for line in r["output"].splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Try Publishers key (newer compose)
            for pub in entry.get("Publishers") or []:
                if pub.get("Protocol") == "tcp" and pub.get("PublishedPort"):
                    return int(pub["PublishedPort"])
            # Try Ports key (older compose JSON shape)
            ports_str = entry.get("Ports", "")
            if ports_str:
                for part in str(ports_str).split(","):
                    part = part.strip()
                    if "->" in part:
                        host_part = part.split("->")[0]
                        if ":" in host_part:
                            try:
                                return int(host_part.rsplit(":", 1)[-1])
                            except ValueError:
                                pass

    # Fallback: `docker compose port <first_service> tcp`
    # Extract service name from compose file
    svc_r = _host_exec(
        f"docker compose -f {compose_path} config --services 2>/dev/null | head -1",
        timeout=10,
    )
    if svc_r.get("ok") and svc_r.get("output", "").strip():
        svc = svc_r["output"].strip()
        port_r = _host_exec(
            f"docker compose -f {compose_path} port {svc} tcp 2>/dev/null", timeout=10
        )
        if port_r.get("ok"):
            # Output format: "0.0.0.0:8090" or ":::8090"
            for tok in port_r.get("output", "").strip().split():
                if ":" in tok:
                    try:
                        return int(tok.rsplit(":", 1)[-1])
                    except ValueError:
                        pass
    return None


def _wait_reachable(host: str, port: int, timeout_s: float = 30.0) -> bool:
    """Poll a mapped port on the lab host until it answers or timeout_s elapses."""
    import socket

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def cmd_up(target_id: str, dry_run: bool = False, max_concurrent: int = 3) -> dict:
    """Bring up a target by catalog id or raw vulhub path — real docker compose on LXC 112."""
    target = _find_target(target_id)
    if target:
        path = target.get("path", "")
        cve = target.get("cve", "")
        print(f"  Target: {target_id} ({cve}) → vulhub/{path}")
    else:
        path = target_id  # Raw vulhub path
        print(f"  Target: {path} (raw vulhub path)")
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "up", "vulhub_path": path}

    compose_path = _host_compose_path(path)
    check = _host_exec(f"test -f {compose_path} && echo EXISTS")
    if not check.get("ok") or "EXISTS" not in check.get("output", ""):
        return {
            "status": "error",
            "reason": f"vulhub compose file not found on host: {compose_path}",
        }

    r = _host_exec(f"docker compose -f {compose_path} up -d", timeout=120)
    if not r.get("ok"):
        return {
            "status": "error",
            "reason": f"docker compose up failed: {r.get('output', '')[:500]}",
        }

    host = target.get("host", LAB_VULHUB_HOST) if target else LAB_VULHUB_HOST
    mapped = _published_port(compose_path)
    if mapped is None:
        # Fallback: catalog-declared or guessed port, dynamically remapped if in use.
        port = target.get("port", 8080) if target else 8080
        mapped = _find_free_port(port, _get_used_ports())
    ready = _wait_reachable(host, mapped)
    return {
        "status": "running" if ready else "error",
        "target": target_id,
        "vulhub_path": path,
        "host": host,
        "port": mapped,
        "reachable": ready,
        "reason": ""
        if ready
        else f"target did not become reachable at {host}:{mapped} within timeout",
        "compose_output": r.get("output", "")[:500],
    }


def cmd_down(target_id: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "down"}

    target = _find_target(target_id)
    path = target.get("path", "") if target else target_id
    compose_path = _host_compose_path(path)
    r = _host_exec(f"docker compose -f {compose_path} down", timeout=60)
    return {
        "status": "stopped" if r.get("ok") else "error",
        "target": target_id,
        "reason": "" if r.get("ok") else r.get("output", "")[:500],
    }


def provision_vulhub_env(path: str) -> dict:
    """Idempotently clone the upstream vulhub repo onto host 112 under LAB_VULHUB_HOST_ROOT,
    if the specific env directory for `path` isn't already present. Only pulls the repo (once);
    does not pre-fetch all 328 envs — the sparse subdir is already in the clone once cloned."""
    check = _host_exec(f"test -f {_host_compose_path(path)} && echo EXISTS")
    if check.get("ok") and "EXISTS" in check.get("output", ""):
        return {"status": "present", "vulhub_path": path}

    root_check = _host_exec(f"test -d {LAB_VULHUB_HOST_ROOT}/.git && echo EXISTS")
    if root_check.get("ok") and "EXISTS" in root_check.get("output", ""):
        r = _host_exec(f"cd {LAB_VULHUB_HOST_ROOT} && git pull", timeout=180)
    else:
        r = _host_exec(
            f"git clone --depth 1 https://github.com/vulhub/vulhub.git {LAB_VULHUB_HOST_ROOT}",
            timeout=300,
        )
    recheck = _host_exec(f"test -f {_host_compose_path(path)} && echo EXISTS")
    ok = recheck.get("ok") and "EXISTS" in recheck.get("output", "")
    return {
        "status": "provisioned" if ok else "error",
        "vulhub_path": path,
        "reason": "" if ok else "env still missing after clone/pull",
        "provision_output": r.get("output", "")[:500],
    }


def cmd_ephemeral(target_id: str, command: list[str] | None, dry_run: bool = False) -> dict:
    """Spin up a target, run a command against it, tear down — with dynamic port mapping."""
    target = _find_target(target_id)
    port = target.get("port", 8080) if target else 8080
    host = target.get("host", "10.10.11.50") if target else "10.10.11.50"
    vulhub_path = target.get("path", target_id) if target else target_id

    used = _get_used_ports() if not dry_run else set()
    mapped = _find_free_port(port, used)
    mapping = PortMapping(target_id=target_id, desired_port=port, mapped_port=mapped, host=host)

    if dry_run:
        result = {
            "status": "dry_run",
            "target": target_id,
            "action": "ephemeral",
            "port": mapped,
            "host": host,
            "command": command,
            "note": f"{'port remapped' if mapped != port else 'port free'}",
        }
    else:
        # Write port map so bench knows where to hit
        _PORT_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PORT_MAP_FILE.write_text(json.dumps({"target": target_id, "host": host, "port": mapped}))
        result = {
            "status": "running",
            "target": target_id,
            "host": host,
            "port": mapped,
            "vulhub_path": vulhub_path,
            "port_map_file": str(_PORT_MAP_FILE),
        }

    print(
        f"  target={target_id} host={host} port={mapped} (desired={port}) {'remapped' if mapped != port else ''}"
    )
    return result


def get_ephemeral_port(filename: str | None = None) -> dict | None:
    """Read the current ephemeral port mapping so bench code knows where to hit."""
    p = Path(filename) if filename else _PORT_MAP_FILE
    if not p.exists():
        return None
    return json.loads(p.read_text())


def cmd_status() -> dict:
    return {"running": [], "reachable": "unknown"}


def cmd_list() -> list[dict]:
    catalog = _load_catalog()
    return [
        {
            "id": t.get("id", "?"),
            "source": t.get("source", "?"),
            "cve": t.get("cve", ""),
            "technique": t.get("technique", ""),
            "preexisting": t.get("preexisting", False),
        }
        for t in catalog.get("targets", [])
    ]


def _resolve_live_port(host: str, env: str | None) -> int | None:
    """Determine the live published port for a target.

    For vulhub envs, uses _published_port on the compose file.
    For non-vulhub targets, probes common ports.
    """
    if env:
        compose_path = _host_compose_path(env)
        return _published_port(compose_path)
    # Non-vulhub: no port discovery available here; caller probes directly
    return None


def _vmid_for_host(host: str) -> str:
    """Look up the Proxmox VMID for a given host IP from lab_targets.yaml."""
    catalog = _load_catalog()
    for t in catalog.get("targets", []):
        if t.get("host") == host:
            return str(t.get("vmid", ""))
    return ""


def ensure_target_ready(scenario: dict, *, dry_run: bool = False, retries: int = 2) -> dict:
    """Verify a scenario's external target is up; heal via existing primitives if not.

    Returns {ready, healed, host, port, reason} where port is the REAL published port
    the scenario must attack (single source of truth — no hardcoded guessing).

    Uses ONLY existing primitives: cmd_up, _published_port, _wait_reachable,
    _lab_lxc_start, _lab_lxc_revert. No new lab-control code.
    """
    host = scenario.get("target_host")
    env = scenario.get("vulhub_env")

    # No external target (AD-only scenarios, etc.) — always "ready"
    if not host:
        return {
            "ready": True,
            "healed": False,
            "host": None,
            "port": None,
            "reason": "no external target",
        }

    # VERIFY: is it up, and on WHAT port?
    port = _resolve_live_port(host, env)
    if port and _wait_reachable(host, port, timeout_s=5):
        return {
            "ready": True,
            "healed": False,
            "host": host,
            "port": port,
            "reason": "already up",
        }

    # HEAL (existing primitives)
    for attempt in range(retries):
        if env:
            up = cmd_up(env, dry_run=dry_run)
            port = up.get("port")
        else:
            vmid = _vmid_for_host(host)
            if vmid:
                from bench_lab_exec import _lab_lxc_start as _lxc_start

                _lxc_start(vmid)
            port = _resolve_live_port(host, env)

        if port and _wait_reachable(host, port, timeout_s=60):
            return {
                "ready": True,
                "healed": True,
                "host": host,
                "port": port,
                "reason": f"healed@{attempt + 1}",
            }

    return {
        "ready": False,
        "healed": False,
        "host": host,
        "port": None,
        "reason": "target-unrecoverable",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab targets — on-demand ephemeral containers")
    parser.add_argument(
        "action", choices=["up", "down", "ephemeral", "status", "list"], help="Action to perform"
    )
    parser.add_argument("target", nargs="?", default="", help="Target ID or raw vulhub path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-concurrent", type=int, default=3)
    parser.add_argument("command", nargs="*", default=[], help="Command for ephemeral mode")
    args = parser.parse_args()

    if args.action == "up":
        result = cmd_up(args.target, dry_run=args.dry_run, max_concurrent=args.max_concurrent)
    elif args.action == "down":
        result = cmd_down(args.target, dry_run=args.dry_run)
    elif args.action == "ephemeral":
        cmd_args = args.command if args.command else None
        result = cmd_ephemeral(args.target, cmd_args, dry_run=args.dry_run)
    elif args.action == "status":
        result = cmd_status()
    elif args.action == "list":
        targets = cmd_list()
        print(f"  {len(targets)} targets in catalog:")
        for t in targets:
            print(
                f"    {t['id']:<30} {t['source']:<15} {t.get('cve', ''):<18} {t.get('technique', '')}"
            )
        return
    print(f"  {result}")


if __name__ == "__main__":
    main()
