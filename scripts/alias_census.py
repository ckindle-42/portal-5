#!/usr/bin/env python3
"""Census of legacy workspace-alias references across the live (non-frozen) tree.

Walks ``git ls-files``, excludes frozen historical artifacts and archived
docs, and counts references to each of the 23 ids in
``_LEGACY_WORKSPACE_ALIASES`` (the single source of truth for the alias
list — read live, never hardcoded here).

Used by the alias-retirement build program (coding_task/cleanup/
BUILD_PROGRAM_ALIAS_RETIRE_V1.md) as the before/after measurement: the
program's goal is to drive the "live" total to zero while leaving frozen
artifacts untouched.

Usage:
    python3 scripts/alias_census.py            # human + JSON to stdout
    python3 scripts/alias_census.py --json      # JSON only
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirrors BUILD_PROGRAM_ALIAS_RETIRE_V1.md's is_frozen() guard exactly —
# these paths/patterns are point-in-time historical records, never rewritten.
_FROZEN_RE = re.compile(
    r"/results/|_snapshot|RESULTS|[0-9]{8}T[0-9]{6}|\.jsonl$|\.bak-|\.old$|\.attack$|/fixtures/|/_archive"
)

# Category classification by path prefix, per DESIGN_ALIAS_RETIRE_V1.md §4.
_CATEGORY_RULES: list[tuple[str, str]] = [
    ("portal/platform/inference/router/preinject.py", "shim"),
    ("portal/platform/inference/router/", "shim"),
    ("config/personas/", "personas"),
    ("config/", "config"),
    ("tests/", "tests"),
    ("portal/modules/security/core/", "integration"),
    ("portal_channels/", "integration"),
    ("deploy/", "integration"),
    ("scripts/lib/", "integration"),
    ("scripts/update_workspace_tools.py", "integration"),
    ("scripts/openwebui_init.py", "integration"),
    ("portal/platform/mcp_host/", "integration"),
    ("portal/modules/coding/tools/code_sandbox_mcp.py", "integration"),
    ("docs/", "docs"),
    ("portal_wiki/canonical/", "docs"),
    ("README.md", "docs"),
    ("CHANGELOG.md", "docs"),
    ("CLAUDE.md", "docs"),
]


def _categorize(path: str) -> str:
    for prefix, category in _CATEGORY_RULES:
        if path.startswith(prefix) or path == prefix:
            return category
    return "other"


def _is_frozen(path: str) -> bool:
    return bool(_FROZEN_RE.search(path))


def _load_alias_ids() -> list[str]:
    """Read the authoritative alias list live from preinject.py — never hardcoded."""
    sys.path.insert(0, str(REPO_ROOT))
    from portal.platform.inference.router.preinject import _LEGACY_WORKSPACE_ALIASES

    return sorted(_LEGACY_WORKSPACE_ALIASES.keys())


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [
        line
        for line in out.stdout.splitlines()
        if line and not line.startswith(".claude/worktrees/")
    ]


def run_census() -> dict:
    aliases = _load_alias_ids()
    alias_pattern = re.compile(r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b")

    files = _tracked_files()
    by_file: dict[str, dict[str, int]] = {}
    by_category: dict[str, int] = {}
    by_alias: dict[str, int] = {}
    frozen_total = 0
    total = 0

    for rel_path in files:
        frozen = _is_frozen(rel_path)
        fpath = REPO_ROOT / rel_path
        try:
            text = fpath.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        matches = alias_pattern.findall(text)
        if not matches:
            continue
        if frozen:
            frozen_total += len(matches)
            continue

        count = len(matches)
        total += count
        by_file[rel_path] = {}
        for m in matches:
            by_file[rel_path][m] = by_file[rel_path].get(m, 0) + 1
            by_alias[m] = by_alias.get(m, 0) + 1
        category = _categorize(rel_path)
        by_category[category] = by_category.get(category, 0) + count

    return {
        "total": total,
        "frozen_total": frozen_total,
        "by_category": by_category,
        "by_alias": by_alias,
        "by_file": by_file,
        "alias_count": len(aliases),
        "files_with_refs": len(by_file),
    }


def main() -> None:
    result = run_census()
    if "--json" in sys.argv:
        print(json.dumps(result))
        return
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
