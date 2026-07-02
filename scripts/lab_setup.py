#!/usr/bin/env python3
"""Tier-1 lab provisioner — idempotent bulk downloads for cold-start setup.

Usage: python3 scripts/lab_setup.py [--skip-heavy] [--update] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))
REPO_ROOT = Path(__file__).resolve().parents[1]

STEPS: dict[str, dict] = {
    "vulhub": {
        "name": "vulhub clone",
        "heavy": True,
        "path": f"{LAB_DIR}/vulhub",
        "desc": "1,234 vulnerable Docker environments (154 families)",
    },
    "challenges": {
        "name": "purpose-built challenges",
        "heavy": False,
        "path": f"{LAB_DIR}/challenges",
        "desc": "JWT, k8s, cloud-metadata, GraphQL (vulhub gaps)",
    },
    "models": {
        "name": "security model pulls",
        "heavy": True,
        "path": "ollama",
        "desc": "Security-lane models resident for bench/loop",
    },
}


def _run(cmd: str, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"  [DRY-RUN] {cmd[:80]}")
        return True
    print(f"  EXEC: {cmd[:80]}...", end=" ", flush=True)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            print("OK")
            return True
        print(f"FAIL ({r.returncode})")
        return False
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return False


def setup_vulhub(skip_heavy: bool, dry_run: bool) -> dict:
    result = {"step": "vulhub", "status": "skipped"}
    path = Path(STEPS["vulhub"]["path"])
    if skip_heavy:
        result["reason"] = "skipped (--skip-heavy)"
        return result
    if path.exists() and (path / ".git").exists():
        result["status"] = "cached"
        result["reason"] = "already cloned"
        return result
    ok = _run(
        f"mkdir -p {path.parent} && git clone --depth 1 https://github.com/vulhub/vulhub {path}",
        dry_run,
    )
    result["status"] = "ok" if ok else "failed"
    return result


def setup_challenges(skip_heavy: bool, dry_run: bool) -> dict:
    result = {"step": "challenges", "status": "skipped"}
    path = Path(STEPS["challenges"]["path"])
    if skip_heavy:
        return result
    path.mkdir(parents=True, exist_ok=True)
    # Materialise purpose-built challenge dirs referenced in challenge_classes.yaml
    try:
        import yaml

        cc = yaml.safe_load((REPO_ROOT / "config" / "challenge_classes.yaml").read_text())
        for c in cc.get("classes", []):
            pb = c.get("purpose_built")
            if pb:
                (path / pb).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    result["status"] = "ok" if not dry_run else "dry_run"
    return result


def setup_models(skip_heavy: bool, dry_run: bool) -> dict:
    result = {"step": "models", "status": "skipped"}
    if skip_heavy:
        result["reason"] = "skipped (--skip-heavy)"
        return result
    # Reuse existing pull-models path
    ok = _run(
        f"cd {REPO_ROOT} && ./launch.sh pull-models 2>/dev/null || echo 'pull-models skipped'",
        dry_run,
    )
    result["status"] = "attempted" if ok else result["status"]
    return result


def run_setup(skip_heavy: bool = False, dry_run: bool = False, update: bool = False) -> dict:
    """Run all Tier-1 setup steps and return a report."""
    results: dict[str, dict] = {}
    print(f"\n  Lab Setup {'(dry-run)' if dry_run else ''} — Tier 1 (bulk downloads)")
    print(f"  LAB_DIR: {LAB_DIR}")
    print(f"  Skip heavy: {skip_heavy}")
    print()

    for step_id, step_config in STEPS.items():
        print(f"── {step_config['name']} ({step_config['desc']})")
        if step_id == "vulhub":
            r = setup_vulhub(skip_heavy, dry_run)
        elif step_id == "challenges":
            r = setup_challenges(skip_heavy, dry_run)
        elif step_id == "models":
            r = setup_models(skip_heavy, dry_run)
        else:
            r = {"step": step_id, "status": "unknown"}
        results[step_id] = r
        print(f"  → {r['status']}")

    print(
        f"\n  Done. {sum(1 for r in results.values() if r['status'] == 'ok')}/{len(results)} steps OK"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab Tier-1 setup — idempotent bulk downloads")
    parser.add_argument("--skip-heavy", action="store_true", help="Skip vulhub + model pulls")
    parser.add_argument(
        "--update", action="store_true", help="Update (git pull) existing downloads"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan without downloading")
    args = parser.parse_args()
    run_setup(skip_heavy=args.skip_heavy, dry_run=args.dry_run, update=args.update)


if __name__ == "__main__":
    main()
