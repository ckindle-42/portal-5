"""Discover and sweep Vulhub environments on lab LXC 112."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from scripts import lab_host

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_FILE = Path("coding_task/scratch/vulhub_sweep_state.json")
_VULHUB_ROOTS = ("/opt/vulhub", "/root/vulhub")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True)
class VulhubTarget:
    service_family: str
    cve_slug: str
    rel_path: str
    host_root: str = "/opt/vulhub"


def _discovery_command() -> str:
    roots = " ".join(_VULHUB_ROOTS)
    return (
        "sh -c 'for root in "
        f'{roots}; do if [ -d "$root" ]; then '
        'find "$root" -maxdepth 3 -type f -name docker-compose.yml -print || exit 1; '
        "fi; done'"
    )


def _parse_discovery_output(output: str) -> list[VulhubTarget]:
    discovered: dict[str, VulhubTarget] = {}
    for line in output.splitlines():
        candidate = line.strip()
        for root in _VULHUB_ROOTS:
            prefix = f"{root}/"
            if not candidate.startswith(prefix):
                continue
            parts = PurePosixPath(candidate[len(prefix) :]).parts
            if len(parts) < 2 or parts[-1] != "docker-compose.yml":
                break
            directories = parts[:-1]
            rel_path = "/".join(directories)
            if not _SAFE_PATH_RE.fullmatch(rel_path) or any(
                part in {"", ".", ".."} for part in directories
            ):
                raise ValueError(f"unsafe Vulhub path returned by discovery: {candidate}")
            family = directories[0]
            cve_slug = "/".join(directories[1:]) or family
            if rel_path not in discovered or root == "/opt/vulhub":
                discovered[rel_path] = VulhubTarget(family, cve_slug, rel_path, root)
            break
    return sorted(
        discovered.values(),
        key=lambda target: (
            target.service_family.casefold(),
            target.cve_slug.casefold(),
            target.rel_path,
        ),
    )


def discover_targets() -> list[VulhubTarget]:
    result = lab_host._host_exec_lxc(_discovery_command())
    if not result.get("ok"):
        raise RuntimeError(f"Vulhub discovery failed: {result.get('output', '')}")
    return _parse_discovery_output(str(result.get("output", "")))


def select_targets(
    targets: list[VulhubTarget], limit: int, families: list[str] | None = None
) -> list[VulhubTarget]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    allowed = {family.strip().casefold() for family in families} if families is not None else None
    grouped: dict[str, list[VulhubTarget]] = {}
    for target in targets:
        family = target.service_family.casefold()
        if allowed is None or family in allowed:
            grouped.setdefault(family, []).append(target)
    for family_targets in grouped.values():
        family_targets.sort(key=lambda target: (target.cve_slug.casefold(), target.rel_path))
    families_sorted = sorted(grouped)
    selected: list[VulhubTarget] = []
    offset = 0
    while len(selected) < limit:
        added = False
        for family in families_sorted:
            if offset < len(grouped[family]):
                selected.append(grouped[family][offset])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        offset += 1
    return selected


def splunk_index(service_family: str, cve_slug: str) -> str:
    identity = re.sub(r"[^a-z0-9]+", "_", f"{service_family}_{cve_slug}".lower()).strip("_")
    return f"hb_lab_{(identity or 'target')[:100].rstrip('_')}"


def check_clock_sync() -> float:
    before = time.time()
    result = lab_host._host_exec_lxc("date -u +%s")
    after = time.time()
    if not result.get("ok"):
        raise RuntimeError(f"LXC UTC clock check failed: {result.get('output', '')}")
    try:
        remote_epoch = int(str(result.get("output", "")).strip())
    except ValueError as exc:
        raise RuntimeError("LXC UTC clock check returned an invalid epoch") from exc
    drift = abs(remote_epoch - ((before + after) / 2))
    if drift >= 10:
        raise RuntimeError(f"LXC UTC clock drift is {drift:.1f}s; required drift is below 10s")
    return drift


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "targets": {}}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or not isinstance(state.get("targets"), dict):
        raise ValueError(f"invalid Vulhub sweep state file: {path}")
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


def _capture_payload(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for offset, character in enumerate(output):
        if character != "{":
            continue
        try:
            payload, end = decoder.raw_decode(output, offset)
        except json.JSONDecodeError:
            continue
        if not output[end:].strip() and isinstance(payload, dict):
            return payload
    raise ValueError("capture output did not end with a JSON result")


def _invoke_capture(
    target: VulhubTarget, index: str, benign_requests: int, dry_run: bool
) -> dict[str, Any]:
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "scripts.hunt_bed.lab_purple_capture",
        "--target",
        target.rel_path,
        "--index",
        index,
        "--benign-requests",
        str(benign_requests),
    ]
    if dry_run:
        command.append("--dry-run")
    environment = os.environ.copy()
    environment["LAB_VULHUB_HOST_ROOT"] = target.host_root
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env=environment,
    )
    expected_status = "dry_run" if dry_run else "complete"
    payload = _capture_payload(completed.stdout)
    if completed.returncode != 0 or payload.get("status") != expected_status:
        detail = (completed.stderr or completed.stdout).strip()[:400]
        raise RuntimeError(f"capture exited {completed.returncode}: {detail}")
    return payload


def _summary_row(target: VulhubTarget, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_family": target.service_family,
        "cve_slug": target.cve_slug,
        "rel_path": target.rel_path,
        "status": record.get("status", "failed"),
        "index": record.get("index", splunk_index(target.service_family, target.cve_slug)),
        "events_captured": record.get("events_captured", ""),
        "answer_key_path": record.get("answer_key_path", ""),
        "error": record.get("error", ""),
    }


def run_sweep(
    targets: list[VulhubTarget],
    *,
    limit: int,
    families: list[str] | None,
    benign_requests: int,
    resume: bool,
    state_file: Path,
    dry_run: bool,
) -> list[dict[str, Any]]:
    if benign_requests < 0:
        raise ValueError("benign request count must be non-negative")
    check_clock_sync()
    selected = select_targets(targets, limit, families)
    state = _load_state(state_file) if resume else _empty_state()
    rows: list[dict[str, Any]] = []
    for target in selected:
        previous = state["targets"].get(target.rel_path, {})
        if resume and previous.get("status") == "completed":
            rows.append(_summary_row(target, previous))
            continue
        index = splunk_index(target.service_family, target.cve_slug)
        try:
            payload = _invoke_capture(target, index, benign_requests, dry_run)
            record = {
                "status": "dry_run" if dry_run else "completed",
                "index": index,
                "events_captured": payload.get("events_captured", ""),
                "answer_key_path": payload.get("answer_key_path", ""),
            }
        except Exception as exc:
            record = {"status": "failed", "index": index, "error": str(exc)[:500]}
        rows.append(_summary_row(target, record))
        if not dry_run:
            state["targets"][target.rel_path] = record
            _save_state(state_file, state)
    return rows


def _print_inventory(targets: list[VulhubTarget]) -> None:
    grouped: dict[str, list[VulhubTarget]] = {}
    for target in targets:
        grouped.setdefault(target.service_family, []).append(target)
    print(f"Vulhub environments discovered: {len(targets)}")
    for family in sorted(grouped, key=str.casefold):
        print(f"{family} ({len(grouped[family])})")
        for target in grouped[family]:
            print(f"  {target.cve_slug}: {target.rel_path}")


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("family | CVE | status | index | events | answer key")
    for row in rows:
        print(
            f"{row['service_family']} | {row['cve_slug']} | {row['status']} | "
            f"{row['index']} | {row['events_captured']} | {row['answer_key_path']}"
        )
        if row["error"]:
            print(f"  error: {row['error']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto-discover and sweep lab Vulhub environments")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--families", help="comma-separated service families to include")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--benign-requests", type=int, default=150)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        targets = discover_targets()
        if args.discover_only:
            _print_inventory(targets)
            return 0
        families = (
            [family.strip() for family in args.families.split(",") if family.strip()]
            if args.families is not None
            else None
        )
        if args.families is not None and not families:
            raise ValueError("--families must include at least one service family")
        rows = run_sweep(
            targets,
            limit=args.limit,
            families=families,
            benign_requests=args.benign_requests,
            resume=args.resume,
            state_file=args.state_file,
            dry_run=args.dry_run,
        )
        _print_summary(rows)
        return 1 if any(row["status"] == "failed" for row in rows) else 0
    except Exception as exc:
        print(f"Vulhub fleet sweep failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
