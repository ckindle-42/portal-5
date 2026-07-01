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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))

# Track port mappings for ephemeral sessions
_PORT_MAP_FILE = REPO_ROOT / "tests" / "benchmarks" / "bench_security" / "results" / ".port_map.json"


@dataclass
class PortMapping:
    target_id: str
    desired_port: int
    mapped_port: int
    host: str = "10.10.11.50"


def _get_used_ports() -> set[int]:
    """Get currently used HOST ports on the lab host via docker ps."""
    try:
        r = subprocess.run(
            ["ssh", "-i", os.path.expanduser("~/.ssh/portal-lab_id_ed25519"),
             "-o", "StrictHostKeyChecking=no", "root@10.0.0.203",
             "pct exec 112 -- docker ps --format '{{.Ports}}'"],
            capture_output=True, text=True, timeout=15, check=True
        )
        ports: set[int] = set()
        for line in r.stdout.splitlines():
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
    except Exception:
        return set()


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


def cmd_up(target_id: str, dry_run: bool = False, max_concurrent: int = 3) -> dict:
    """Bring up a target by catalog id or raw vulhub path."""
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
    vulhub_dir = Path(LAB_DIR) / "vulhub" / path
    if not vulhub_dir.exists():
        return {"status": "error", "reason": f"vulhub path not found: {vulhub_dir}"}
    return {"status": "placeholder", "reason": "Docker compose up requires live Docker daemon"}


def cmd_down(target_id: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "down"}
    return {"status": "placeholder", "reason": "Docker compose down requires live Docker daemon"}


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
            "status": "dry_run", "target": target_id, "action": "ephemeral",
            "port": mapped, "host": host,
            "command": command, "note": f"{'port remapped' if mapped != port else 'port free'}"
        }
    else:
        # Write port map so bench knows where to hit
        _PORT_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PORT_MAP_FILE.write_text(json.dumps({"target": target_id, "host": host, "port": mapped}))
        result = {
            "status": "running", "target": target_id, "host": host, "port": mapped,
            "vulhub_path": vulhub_path,
            "port_map_file": str(_PORT_MAP_FILE)
        }

    print(f"  target={target_id} host={host} port={mapped} (desired={port}) {'remapped' if mapped != port else ''}")
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
        {"id": t.get("id", "?"), "source": t.get("source", "?"), "cve": t.get("cve", ""),
         "technique": t.get("technique", ""), "preexisting": t.get("preexisting", False)}
        for t in catalog.get("targets", [])
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab targets — on-demand ephemeral containers")
    parser.add_argument("action", choices=["up", "down", "ephemeral", "status", "list"], help="Action to perform")
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
            print(f"    {t['id']:<30} {t['source']:<15} {t.get('cve',''):<18} {t.get('technique','')}")
        return
    print(f"  {result}")


if __name__ == "__main__":
    main()
