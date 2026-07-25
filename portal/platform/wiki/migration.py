"""Migration discipline for the wiki spine generation loop.

Provides fence markers, substantive-remainder detection, and doc-discovery
for the migration loop described in DESIGN_WIKI_GENERATION_LOOP_V1.md.

A fully-migrated doc contains ONLY:
  (a) <!-- WIKI:GENERATED unit=<id> -->…<!-- /WIKI:GENERATED --> blocks
  (b) <!-- WIKI:HUMAN-OWNED -->…<!-- /WIKI:HUMAN-OWNED --> fenced narrative
  (c) inert markdown structure (headings, rules, blank lines)

Any substantive line outside both fences = un-migrated content.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ── Fence constants (mirroring render.py _BLOCK_START/_BLOCK_END style) ──

HUMAN_OWNED_START = "<!-- WIKI:HUMAN-OWNED -->"
HUMAN_OWNED_END = "<!-- /WIKI:HUMAN-OWNED -->"

_GENERATED_BLOCK_RE = re.compile(
    r"<!-- WIKI:GENERATED unit=[\w.-]+ -->.*?<!-- /WIKI:GENERATED -->",
    re.DOTALL,
)
_HUMAN_OWNED_RE = re.compile(
    r"<!-- WIKI:HUMAN-OWNED -->.*?<!-- /WIKI:HUMAN-OWNED -->",
    re.DOTALL,
)

# Lines that are inert markdown structure (no substantive content).
_INERT_RE = re.compile(
    r"^\s*$"  # blank line
    r"|^\s*#{1,6}\s+\S.*$"  # heading with content (structural)
    r"|^\s*---+\s*$"  # horizontal rule
    r"|^\s*\*\*\*+\s*$"  # horizontal rule (asterisk form)
    r"|^\s*[-*+]\s*$"  # empty list item scaffold
    r"|^\s*>\s*$"  # empty blockquote line
    r"|^\s*\|[-:|\s]+\|$"  # markdown table separator row only (|---|---|)
    r"|^\s*<!--(?!.*WIKI:).*-->\s*$"  # HTML comment that is NOT a WIKI fence
    r"|^\s*<[^>]+>\s*$"  # standalone HTML tag (e.g. <br>, <details>)
    r"|^\s*$",  # blank (duplicate, harmless)
    re.MULTILINE,
)


def strip_managed_regions(text: str) -> str:
    """Remove every WIKI:GENERATED block and every WIKI:HUMAN-OWNED fence.

    Returns only the *unmanaged* remainder — content that is neither
    generated-from-units nor fenced human narrative.
    """
    text = _GENERATED_BLOCK_RE.sub("", text)
    text = _HUMAN_OWNED_RE.sub("", text)
    return text


def _strip_inert_lines(text: str) -> str:
    """Remove inert markdown structure lines, returning only substantive ones."""
    lines = text.splitlines()
    substantive = []
    for line in lines:
        if not _INERT_RE.match(line):
            substantive.append(line)
    return "\n".join(substantive)


def substantive_remainder(text: str) -> str:
    """The unmanaged remainder with inert markdown stripped.

    Returns only lines that are substantive AND outside managed fences.
    Non-empty result = the doc still holds un-migrated substance.
    """
    unmanaged = strip_managed_regions(text)
    return _strip_inert_lines(unmanaged).strip()


def doc_is_migrated(path: Path) -> bool:
    """True iff the doc is fully a shell (generated blocks + fenced human prose + inert structure)."""
    text = path.read_text(encoding="utf-8")
    return substantive_remainder(text) == ""


# ── Discovery ──


def _git_churn(path: str, repo_root: Path) -> int:
    """Count recent commits touching this path (last 30 commits on HEAD)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-30", "HEAD", "--", path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return len([ln for ln in result.stdout.splitlines() if ln.strip()])
    except Exception:
        return 0


def discover_unmigrated_docs(
    repo_root: Path,
    *,
    exclude: tuple[str, ...] = ("CLAUDE.md",),
) -> list[dict]:
    """Walk the doc surface and return docs that are NOT fully migrated.

    Returns [{path, substantive_lines, priority}] for each un-migrated doc,
    sorted by priority desc then path.  Priority = git-churn score + boost
    for high-value seed docs.

    CLAUDE.md is hard-excluded — an assertion enforces it can never appear.
    """
    from portal.platform.wiki.render import TIER1_DOCS

    # Also include any doc tracked by the ledger that is not in TIER1_DOCS.
    ledger_docs = _ledger_doc_paths(repo_root)
    all_rel = sorted(set(TIER1_DOCS) | ledger_docs)

    # Assertion: CLAUDE.md must never appear in output.
    assert "CLAUDE.md" not in all_rel or "CLAUDE.md" in exclude, (
        "CLAUDE.md must be excluded from migration discovery"
    )

    # Seed docs get a priority boost.
    seed_boost = {
        "docs/SECURITY_BENCH_EXEC.md": 50,
        "docs/HOWTO.md": 40,
        "docs/ADMIN_GUIDE.md": 35,
        "README.md": 30,
        "docs/USER_GUIDE.md": 25,
        "config/MODEL_CATALOG.md": 20,
        "KNOWN_LIMITATIONS.md": 15,
    }

    results: list[dict] = []
    for rel in all_rel:
        if rel in exclude:
            continue
        p = repo_root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        remainder = substantive_remainder(text)
        if remainder == "":
            continue  # already migrated
        substantive_line_count = len(remainder.splitlines())
        churn = _git_churn(rel, repo_root)
        boost = seed_boost.get(rel, 0)
        results.append(
            {
                "path": rel,
                "substantive_lines": substantive_line_count,
                "priority": churn + boost,
            }
        )

    results.sort(key=lambda d: (-d["priority"], d["path"]))
    return results


def _ledger_doc_paths(repo_root: Path) -> set[str]:
    """Extract doc paths from docs/.doc_ledger.yaml."""
    import yaml

    ledger_path = repo_root / "docs" / ".doc_ledger.yaml"
    if not ledger_path.exists():
        return set()
    data = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
    return set((data.get("docs") or {}).keys())
