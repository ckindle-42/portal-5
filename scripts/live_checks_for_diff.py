#!/usr/bin/env python3
"""Map a git diff (or file list) to the minimal live checks the orchestrator runs after merge.

Reads ``config/live_check_map.yaml`` and prints copy-pasteable commands (rebuild hint,
``smoke_stream.sh``, ``portal trace``, targeted ``tests.qat`` scenarios/phases, and any
domain proof scripts). Zero network or inference calls — purely resolves the plan.

Usage:
    uv run python scripts/live_checks_for_diff.py --base origin/main
    uv run python scripts/live_checks_for_diff.py --files portal/modules/documents/tools/doc_mcp.py
    uv run python scripts/live_checks_for_diff.py --base HEAD~1 --json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP_PATH = REPO_ROOT / "config" / "live_check_map.yaml"


@dataclass
class LiveCheckPlan:
    changed_files: list[str]
    matched_rules: list[str] = field(default_factory=list)
    rebuild_required: bool = False
    smoke_stream: bool = False
    trace_sections: list[str] = field(default_factory=list)
    qat_phases: list[str] = field(default_factory=list)
    qat_scenarios: list[str] = field(default_factory=list)
    extra_commands: list[str] = field(default_factory=list)
    unmapped_product_files: list[str] = field(default_factory=list)

    def commands(self) -> list[str]:
        cmds: list[str] = []
        if self.rebuild_required:
            cmds.append("./launch.sh rebuild && ./launch.sh up")
        if self.smoke_stream:
            cmds.append("./scripts/smoke_stream.sh")
        if self.trace_sections:
            sec_flags = " ".join(f"--section {s}" for s in self.trace_sections)
            cmds.append(f"uv run portal trace --json {sec_flags}")
        if self.qat_phases:
            ph_flags = " ".join(f"--phase {p}" for p in self.qat_phases)
            cmds.append(f"uv run --extra dev python -m tests.qat {ph_flags}")
        if self.qat_scenarios:
            sc_flags = " ".join(f"--scenario {s}" for s in self.qat_scenarios)
            cmds.append(f"uv run --extra dev python -m tests.qat {sc_flags}")
        cmds.extend(self.extra_commands)
        return cmds

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_files": self.changed_files,
            "matched_rules": self.matched_rules,
            "rebuild_required": self.rebuild_required,
            "smoke_stream": self.smoke_stream,
            "trace_sections": self.trace_sections,
            "qat_phases": self.qat_phases,
            "qat_scenarios": self.qat_scenarios,
            "extra_commands": self.extra_commands,
            "unmapped_product_files": self.unmapped_product_files,
            "commands": self.commands(),
        }


def _glob_match(path: str, pattern: str) -> bool:
    """Match repo-relative path against glob supporting ``**`` directory wildcards."""
    norm = path.lstrip("./")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return norm == prefix or norm.startswith(prefix + "/")
    return fnmatch.fnmatch(norm, pattern)


def _dedup_extend(dest: list[str], items: list[str]) -> None:
    seen = set(dest)
    for item in items:
        if item not in seen:
            dest.append(item)
            seen.add(item)


def load_map(map_path: Path = DEFAULT_MAP_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError(f"Invalid live check map: {map_path}")
    return raw


def resolve_checks(changed_files: list[str], *, map_path: Path = DEFAULT_MAP_PATH) -> LiveCheckPlan:
    cfg = load_map(map_path)
    rebuild_globs: list[str] = cfg.get("rebuild_globs") or []
    rules: list[dict[str, Any]] = cfg["rules"]

    norm_files = [f.strip().lstrip("./") for f in changed_files if f.strip()]
    plan = LiveCheckPlan(changed_files=norm_files)

    for f in norm_files:
        if any(_glob_match(f, g) for g in rebuild_globs):
            plan.rebuild_required = True
        matched_any = False
        for rule in rules:
            if rule.get("only_if_unmatched") and matched_any:
                continue
            globs = rule.get("globs") or []
            if any(_glob_match(f, g) for g in globs):
                matched_any = True
                if rule["id"] not in plan.matched_rules:
                    plan.matched_rules.append(rule["id"])
                if rule.get("smoke_stream"):
                    plan.smoke_stream = True
                _dedup_extend(plan.trace_sections, rule.get("trace_sections") or [])
                _dedup_extend(plan.qat_phases, rule.get("qat_phases") or [])
                _dedup_extend(plan.qat_scenarios, rule.get("qat_scenarios") or [])
                _dedup_extend(plan.extra_commands, rule.get("extra_commands") or [])
        if not matched_any and f.startswith("portal/") and "/tests/" not in f:
            plan.unmapped_product_files.append(f)
    return plan


def _git_diff_files(base: str, staged: bool = False) -> list[str]:
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    else:
        cmd.append(f"{base}...HEAD")
    out = subprocess.check_output(cmd, cwd=REPO_ROOT, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve live checks for changed repo paths.")
    ap.add_argument("--base", default="origin/main", help="Git ref to diff against HEAD")
    ap.add_argument("--staged", action="store_true", help="Inspect staged files instead of diff")
    ap.add_argument("--files", nargs="+", help="Explicit repo-relative file paths")
    ap.add_argument(
        "--map", type=Path, default=DEFAULT_MAP_PATH, help="Path to live_check_map.yaml"
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON plan")
    args = ap.parse_args(argv)

    files = args.files if args.files is not None else _git_diff_files(args.base, staged=args.staged)
    plan = resolve_checks(files, map_path=args.map)

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    print(f"Changed files : {len(plan.changed_files)}")
    print(f"Matched rules : {', '.join(plan.matched_rules) or '(none — no live check required)'}")
    print(f"Rebuild needed: {'yes' if plan.rebuild_required else 'no'}")
    if plan.unmapped_product_files:
        print(f"WARN unmapped : {', '.join(plan.unmapped_product_files)}")
    cmds = plan.commands()
    if cmds:
        print("\nOrchestrator live checks:")
        for c in cmds:
            print(f"  {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
