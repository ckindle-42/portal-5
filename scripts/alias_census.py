#!/usr/bin/env python3
"""Census of legacy workspace-alias references across the live (non-frozen) tree.

Walks ``git ls-files``, excludes frozen historical artifacts and archived
docs, and counts references to each of the 23 pre-collapse alias ids in
``_RETIRED_ALIAS_IDS`` below.

Until CLOSEOUT_ALIAS_REMOVAL.md's shim removal, this list was read live
from ``preinject.py``'s ``_LEGACY_WORKSPACE_ALIASES`` (the resolution
table doubled as the source of truth for "what counts as a legacy alias").
That dict no longer exists — the shim was removed once every live caller
was proven migrated (BUILD_PROGRAM_ALIAS_FINISH_V1.md Phase 4's zero-trip
gate). This is now a frozen historical vocabulary: the fixed set of ids
that were ever aliases, kept here so validate_system.py check AT can still
assert zero *new* live references to them (an id appearing is either a
regression — someone reintroduced a bare alias — or a legitimate
historical/exempted reference).

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


# Categories where a bare alias id appearing as *live, dispatched code*
# (not a comment/docstring explaining history) would be a real regression —
# a default argument, a dict key/value sent as `model=`, a CLI example that
# no longer resolves. Restricted to .py/.sh serving-path files
# (shim/integration/personas — all Python), where "comment vs code" is a
# meaningful, checkable distinction. "config" (mostly narrative JSON/YAML
# prose — MODEL_CATALOG.md, routing_descriptions.json's _note, portal.yaml
# description fields — manually verified clean at the live-value level
# during CLOSEOUT_ALIAS_REMOVAL.md) and "docs"/"tests"/"other" (markdown/
# narrative-heavy by nature) are reported but not hard-gated — see
# BUILD_PROGRAM_ALIAS_FINISH_V1.md Phase 6.
_CODE_RISK_CATEGORIES = frozenset({"shim", "integration", "personas"})

_COMMENT_MARKERS = ("#", "//")


def _classify_hit_lines(text: str, alias_pattern: re.Pattern) -> tuple[int, int]:
    """Return (code_hits, comment_hits) for all matches in ``text``.

    A match is a "comment" hit if a comment marker appears anywhere before
    it on the same line, OR the line falls inside a Python triple-quoted
    (``\"\"\"``/``'''``) docstring/comment block. Everything else counts as
    "code". Not a full parser (a `#`/`//` inside a string literal would
    still be treated as a comment marker), but sufficient for this
    classifier's purpose: distinguishing "someone hardcoded a retired id as
    a live default" from "a comment/docstring mentions history" in the
    Python files this runs against.
    """
    code = 0
    comment = 0
    in_docstring = False
    docstring_marker = None
    for line in text.splitlines():
        # Track triple-quoted block state (naive: doesn't handle a
        # triple-quote appearing inside a string on the same line as code,
        # which doesn't occur in this repo's style).
        stripped = line.strip()
        line_starts_in_docstring = in_docstring
        for marker in ('"""', "'''"):
            if marker in stripped:
                count = stripped.count(marker)
                if not in_docstring:
                    in_docstring = True
                    docstring_marker = marker
                    if count % 2 == 0:
                        in_docstring = False
                elif marker == docstring_marker and count % 2 == 1:
                    in_docstring = False

        if line_starts_in_docstring or (in_docstring and not line_starts_in_docstring):
            for _m in alias_pattern.finditer(line):
                comment += 1
            continue

        marker_pos = min(
            (line.find(m) for m in _COMMENT_MARKERS if m in line),
            default=-1,
        )
        for m in alias_pattern.finditer(line):
            if marker_pos != -1 and m.start() > marker_pos:
                comment += 1
            else:
                code += 1
    return code, comment


# Frozen historical vocabulary — the 23 pre-collapse bare workspace ids that
# used to be aliases in preinject.py's now-removed _LEGACY_WORKSPACE_ALIASES.
# Do not add to this list for new workspace changes; it exists only to keep
# the zero-live-alias assertion (validate_system.py check AT) meaningful.
_RETIRED_ALIAS_IDS: tuple[str, ...] = (
    "auto-coding-agentic",
    "auto-coding-northmini",
    "auto-coding-uncensored",
    "auto-coding-uncensored-agentic",
    "auto-agentic",
    "auto-agentic-lite",
    "auto-agentic-ornith",
    "auto-security-uncensored",
    "auto-pentest",
    "auto-blueteam",
    "auto-redteam",
    "auto-redteam-deep",
    "auto-purpleteam",
    "auto-purpleteam-deep",
    "auto-purpleteam-exec",
    "auto-devstral",
    "auto-glm",
    "auto-glm-thinking",
    "auto-mistral",
    "auto-phi4",
    "auto-gemma-e4b",
    "auto-gemma-fast",
    "auto-gemma-vision",
)


def _load_alias_ids() -> list[str]:
    """The frozen historical alias vocabulary (see _RETIRED_ALIAS_IDS)."""
    return sorted(_RETIRED_ALIAS_IDS)


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
    code_hits_by_file: dict[str, int] = {}
    frozen_total = 0
    total = 0
    code_risk_total = 0

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

        if category in _CODE_RISK_CATEGORIES:
            code_hits, _comment_hits = _classify_hit_lines(text, alias_pattern)
            if code_hits:
                code_hits_by_file[rel_path] = code_hits
                code_risk_total += code_hits

    return {
        "total": total,
        "frozen_total": frozen_total,
        "by_category": by_category,
        "by_alias": by_alias,
        "by_file": by_file,
        "alias_count": len(aliases),
        "files_with_refs": len(by_file),
        # Phase 6 hard-zero surface: non-comment alias hits in categories
        # representing live code/config (shim/integration/personas/config).
        # Must be empty for check AT to pass.
        "code_risk_total": code_risk_total,
        "code_hits_by_file": code_hits_by_file,
    }


def main() -> None:
    result = run_census()
    if "--json" in sys.argv:
        print(json.dumps(result))
        return
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
