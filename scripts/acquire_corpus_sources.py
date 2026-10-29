#!/usr/bin/env python3
"""Verify pinned corpus source checkouts or acquire missing clean copies."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCES = {
    "attack_data": (
        "https://github.com/splunk/attack_data.git",
        "4145e8b60fd8a3d44bc2170d1eb343fe7247387b",
    ),
    "mordor": (
        "https://github.com/OTRF/Security-Datasets.git",
        "d9d40ef123d2c87d5d3df28c96bcab4f0faccc87",
    ),
    "evtx_samples": (
        "https://github.com/sbousseaden/EVTX-ATTACK-SAMPLES.git",
        "4ceed2f4706daf601c212a8f91c113dd85349a2c",
    ),
    "evtx_mitre": (
        "https://github.com/mdecrevoisier/EVTX-to-MITRE-Attack.git",
        "474856008f037ccd42753f02a631b42690195829",
    ),
    "invictus_ir": (
        "https://github.com/invictus-ir/aws_dataset.git",
        "4667aa9c26330bc3317ed8bd526f4b83cff13602",
    ),
}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    commit: str
    target: Path


def source_specs(sources_root: Path, corpora_root: Path) -> list[SourceSpec]:
    specs = [
        SourceSpec(name, url, commit, sources_root / name)
        for name, (url, commit) in SOURCES.items()
        if name != "invictus_ir"
    ]
    specs.append(
        SourceSpec(
            "invictus_ir",
            SOURCES["invictus_ir"][0],
            SOURCES["invictus_ir"][1],
            corpora_root / "invictus_ir_aws_dataset" / "repo",
        )
    )
    return specs


def _git(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, env=env
    )


def inspect_checkout(path: Path, expected_commit: str) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing", "commit": None, "dirty_paths": None}
    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode:
        return {"path": str(path), "status": "not_git", "commit": None, "dirty_paths": None}
    root = Path(top.stdout.strip())
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain")
    if commit.returncode or status.returncode:
        return {"path": str(path), "status": "invalid_git", "commit": None, "dirty_paths": None}
    actual = commit.stdout.strip()
    dirty_paths = sum(bool(line) for line in status.stdout.splitlines())
    result = {
        "path": str(path),
        "commit": actual,
        "expected_commit": expected_commit,
        "dirty_paths": dirty_paths,
        "commit_matches_expected": actual == expected_commit,
    }
    if dirty_paths or actual != expected_commit:
        result["status"] = "mismatch"
    elif _has_lfs_pointers(root):
        result["status"] = "lfs_incomplete"
    else:
        result["status"] = "verified"
    return result


def sibling_checkout(path: Path, commit: str) -> Path:
    return path.with_name(f"{path.name}.pinned-{commit[:12]}")


def _has_lfs_pointers(root: Path) -> bool:
    tracked = _git(root, "ls-files", "-z")
    if tracked.returncode:
        return True
    for name in tracked.stdout.split("\0"):
        path = root / name
        try:
            if path.is_file() and path.stat().st_size <= 1024:
                if path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"):
                    return True
        except OSError:
            return True
    return False


def acquire_checkout(spec: SourceSpec) -> dict[str, Any]:
    current = inspect_checkout(spec.target, spec.commit)
    if current["status"] == "verified":
        return current
    target = (
        spec.target
        if current["status"] == "missing"
        else sibling_checkout(spec.target, spec.commit)
    )
    alternate = inspect_checkout(target, spec.commit)
    if alternate["status"] == "verified":
        return alternate
    if target.exists():
        return {**alternate, "status": "alternate_unusable", "original_status": current["status"]}
    target.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    clone = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", spec.url, str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if clone.returncode:
        return {"path": str(target), "status": "clone_failed", "detail": clone.stderr.strip()}
    checkout = _git(target, "checkout", "--detach", spec.commit)
    if checkout.returncode:
        return {"path": str(target), "status": "checkout_failed", "detail": checkout.stderr.strip()}
    lfs = _git(target, "lfs", "ls-files", "--long")
    if lfs.returncode == 0 and lfs.stdout.strip():
        pulled = _git(target, "lfs", "pull")
        if pulled.returncode:
            return {
                "path": str(target),
                "status": "lfs_pull_failed",
                "detail": pulled.stderr.strip(),
            }
    if _has_lfs_pointers(target):
        return {"path": str(target), "status": "lfs_pointers_remain"}
    return {**inspect_checkout(target, spec.commit), "status": "acquired"}


def _tree_facts(root: Path) -> tuple[str, int, str | None]:
    tracked = _git(root, "ls-files", "-z")
    if tracked.returncode:
        raise RuntimeError(f"cannot list tracked files under {root}")
    digest = hashlib.sha256()
    size = 0
    license_name = None
    for name in sorted(part for part in tracked.stdout.split("\0") if part):
        path = root / name
        content = path.read_bytes()
        size += len(content)
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
        if Path(name).name.casefold() in {"license", "license.md", "license.txt", "license.gpl"}:
            license_name = Path(name).name
    return digest.hexdigest(), size, license_name


def update_manifest(path: Path, specs: list[SourceSpec], results: list[dict[str, Any]]) -> None:
    document = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"sources": []}
    records = document.get("sources", [])
    if not isinstance(records, list):
        raise ValueError("acquisition manifest sources must be a list")
    by_id = {str(row.get("source_id")): row for row in records if isinstance(row, dict)}
    for spec, result in zip(specs, results, strict=True):
        if result["status"] != "acquired":
            continue
        checksum, size, license_name = _tree_facts(Path(result["path"]))
        by_id[spec.name] = {
            "source_id": spec.name,
            "url": spec.url.removesuffix(".git"),
            "commit": spec.commit,
            "checksum": checksum,
            "license": license_name or "not declared",
            "bytes": size,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        }
    document["sources"] = [by_id[key] for key in sorted(by_id)]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources-root", type=Path, default=Path("/Volumes/data01/portal5_hunt/sources")
    )
    parser.add_argument(
        "--corpora-root", type=Path, default=Path("/Volumes/data01/portal5_hunt/corpora")
    )
    parser.add_argument(
        "--acquire", action="store_true", help="clone pinned sources when verification fails"
    )
    args = parser.parse_args()
    specs = source_specs(args.sources_root, args.corpora_root)
    if not args.acquire:
        results = [inspect_checkout(spec.target, spec.commit) for spec in specs]
        print(json.dumps({"mode": "VERIFY-ONLY", "sources": results}, indent=2, sort_keys=True))
        return 0 if all(result["status"] == "verified" for result in results) else 2
    manifest = args.corpora_root / "manifest.json"
    try:
        json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {"sources": []}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[BLOCKED] cannot read acquisition manifest: {type(exc).__name__}", file=sys.stderr)
        return 2
    results = [acquire_checkout(spec) for spec in specs]
    update_manifest(manifest, specs, results)
    print(json.dumps({"mode": "ACQUIRED", "sources": results}, indent=2, sort_keys=True))
    return 0 if all(result["status"] in {"verified", "acquired"} for result in results) else 2


if __name__ == "__main__":
    sys.exit(main())
