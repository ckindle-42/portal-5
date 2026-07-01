#!/usr/bin/env python3
"""Lab targets provisioner — on-demand ephemeral containers from lab_targets.yaml.

Usage: python3 scripts/lab_targets.py up <id|vulhub-path> [--dry-run]
       python3 scripts/lab_targets.py down <id> [--dry-run]
       python3 scripts/lab_targets.py ephemeral <id> -- <cmd> [--dry-run]
       python3 scripts/lab_targets.py status
       python3 scripts/lab_targets.py list
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))


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
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "ephemeral", "command": command}
    return {"status": "placeholder", "reason": "ephemeral requires live Docker daemon"}


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
        cmd_list = args.command if args.command else None
        result = cmd_ephemeral(args.target, cmd_list, dry_run=args.dry_run)
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
