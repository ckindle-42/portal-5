"""Migration discipline for the wiki spine generation loop.

Provides fence markers, substantive-remainder detection, and doc-discovery
for the migration loop described in DESIGN_WIKI_GENERATION_LOOP_V1.md.

A fully-migrated doc contains ONLY:
  (a) <!-- WIKI:GENERATED unit=<id> -->…<!-- /WIKI:GENERATED --> blocks
  (b) <!-- WIKI:HUMAN-OWNED reason="..." -->…<!-- /WIKI:HUMAN-OWNED --> fenced narrative
  (c) inert markdown structure (headings, rules, blank lines)

Any substantive line outside both fences = un-migrated content.
A fence without a non-empty reason is invalid.
A migrated doc must have >=1 generated block and bounded human-fence ratio.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ── Fence constants ──

# V2: Opening fence requires a reason attribute.
HUMAN_OWNED_START_RE = re.compile(r'<!-- WIKI:HUMAN-OWNED reason="([^"]+)" -->')
HUMAN_OWNED_END = "<!-- /WIKI:HUMAN-OWNED -->"

# Also match the OLD V1 form (no reason) so we can detect/strip it.
_HUMAN_OWNED_V1_RE = re.compile(
    r"<!-- WIKI:HUMAN-OWNED -->.*?<!-- /WIKI:HUMAN-OWNED -->",
    re.DOTALL,
)

_GENERATED_BLOCK_RE = re.compile(
    r"<!-- WIKI:GENERATED unit=[\w.-]+ -->.*?<!-- /WIKI:GENERATED -->",
    re.DOTALL,
)

# V2 form: reason-bearing fences.
_HUMAN_OWNED_RE = re.compile(
    r'<!-- WIKI:HUMAN-OWNED reason="[^"]*" -->.*?<!-- /WIKI:HUMAN-OWNED -->',
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

# ── B3 allowlist ──

_HUMAN_FENCE_MAX = 0.40
_ALLOWLIST_PATH = Path("docs/.migration_allow_human_majority.yaml")


def _load_allowlist(repo_root: Path | None = None) -> dict[str, str]:
    """Load B3 allowlist: {path: justification}. Absent file = empty."""
    import yaml

    root = repo_root or Path(".")
    p = root / _ALLOWLIST_PATH
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


# ── Core functions ──


def strip_managed_regions(text: str) -> str:
    """Remove every WIKI:GENERATED block and every WIKI:HUMAN-OWNED fence.

    Returns only the *unmanaged* remainder — content that is neither
    generated-from-units nor fenced human narrative. Handles both V1
    (no reason) and V2 (reason-bearing) fence forms.
    """
    text = _GENERATED_BLOCK_RE.sub("", text)
    text = _HUMAN_OWNED_RE.sub("", text)
    text = _HUMAN_OWNED_V1_RE.sub("", text)  # strip V1 leftovers
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


def generated_block_count(text: str) -> int:
    """Count WIKI:GENERATED blocks in the text."""
    return len(_GENERATED_BLOCK_RE.findall(text))


def fenced_human_lines(text: str) -> int:
    """Count substantive (non-inert) lines inside HUMAN-OWNED fences.

    Counts lines in both V2 (reason-bearing) and V1 (no reason) fences.
    """
    total = 0
    # V2 fences
    for m in _HUMAN_OWNED_RE.finditer(text):
        body = m.group()
        # Strip the fence tags themselves
        body = HUMAN_OWNED_START_RE.sub("", body)
        body = body.replace(HUMAN_OWNED_END, "")
        lines = _strip_inert_lines(body).strip()
        if lines:
            total += len(lines.splitlines())
    # V1 fences (leftover)
    for m in _HUMAN_OWNED_V1_RE.finditer(text):
        body = m.group()
        body = body.replace("<!-- WIKI:HUMAN-OWNED -->", "")
        body = body.replace(HUMAN_OWNED_END, "")
        lines = _strip_inert_lines(body).strip()
        if lines:
            total += len(lines.splitlines())
    return total


def total_substantive_lines(text: str) -> int:
    """Total substantive lines across the whole doc.

    This is the ratio denominator: fenced human lines + generated-block
    content lines + any remainder lines (though remainder should be empty
    for a migrated doc).
    """
    # Lines inside generated blocks
    gen_lines = 0
    for m in _GENERATED_BLOCK_RE.finditer(text):
        body = m.group()
        # Strip fence tags
        body = re.sub(r"<!-- WIKI:GENERATED unit=[\w.-]+ -->", "", body)
        body = body.replace("<!-- /WIKI:GENERATED -->", "")
        lines = _strip_inert_lines(body).strip()
        if lines:
            gen_lines += len(lines.splitlines())

    human = fenced_human_lines(text)
    remainder = substantive_remainder(text)
    remainder_lines = len(remainder.splitlines()) if remainder else 0
    return gen_lines + human + remainder_lines


def human_owned_reasons(text: str) -> list[str]:
    """Extract all HUMAN-OWNED fence reasons.

    Returns list of reason strings. A fence with no/empty reason gets
    a sentinel '[MISSING]' entry that fails validation.
    """
    reasons: list[str] = []
    for m in HUMAN_OWNED_START_RE.finditer(text):
        reasons.append(m.group(1))
    # Also check for V1 fences (no reason) — these are invalid
    v1_count = len(_HUMAN_OWNED_V1_RE.findall(text))
    # Any V1 fences that aren't matched by V2 are unreasoned
    for _ in range(v1_count):
        reasons.append("[MISSING]")
    return reasons


def doc_is_migrated(path: Path) -> bool:
    """True iff the doc is genuinely migrated — not gamed.

    All of:
      (a) substantive_remainder(text) == ""  — no un-fenced substance
      (b) generated_block_count(text) >= 1   — SOMETHING is unit-sourced
          OR the doc is on the B3 human-majority allowlist
      (c) fenced_human_ratio <= HUMAN_FENCE_MAX
          OR the doc is on the B3 allowlist
      (d) every HUMAN-OWNED fence has a non-empty reason
    """
    text = path.read_text(encoding="utf-8")

    # (a) no un-fenced substance
    if substantive_remainder(text) != "":
        return False

    # (d) every fence has a reason
    reasons = human_owned_reasons(text)
    if any(r == "[MISSING]" for r in reasons):
        return False

    gen_count = generated_block_count(text)
    human = fenced_human_lines(text)
    total = total_substantive_lines(text)

    # Check B3 allowlist
    allowlist = _load_allowlist(path.parent if path.parent != Path(".") else Path("."))
    is_allowlisted = str(path) in allowlist or path.name in allowlist

    # (b) must have >=1 generated block (unless allowlisted)
    if gen_count < 1 and not is_allowlisted:
        return False

    # (c) human-fence ratio must be bounded (unless allowlisted)
    if total > 0:
        ratio = human / max(1, total)
        if ratio > _HUMAN_FENCE_MAX and not is_allowlisted:
            return False

    return True


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
        if doc_is_migrated(p):
            continue
        text = p.read_text(encoding="utf-8")
        remainder = substantive_remainder(text)
        substantive_line_count = len(remainder.splitlines()) if remainder else 0
        # For docs with no remainder but failing other checks, count fenced lines
        if substantive_line_count == 0:
            substantive_line_count = fenced_human_lines(text)
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
