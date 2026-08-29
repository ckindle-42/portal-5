"""Render targeted views from the canonical layer.

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.
Managed-block rendering added by DESIGN_WIKI_GENERATION_LOOP_V1.md F2.

`render_admin_guide`/`render_architecture_map` below are the original
docs/generated/ proof-of-concept renderers (kept for the `portal_wiki
render --all/--check` CLI's existing drift gate). The primary mechanism
is now `render_all_generated_blocks`: it writes INTO the real Tier-1 docs
the operator reads, replacing only the content between
`<!-- WIKI:GENERATED unit=<id> -->` / `<!-- /WIKI:GENERATED -->` markers —
narrative prose outside markers is human-owned and untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

from portal.platform.wiki.migration import doc_is_migrated
from portal.platform.wiki.store import load_all, load_unit

_BLOCK_START = "<!-- WIKI:GENERATED unit={unit_id} -->"
_BLOCK_END = "<!-- /WIKI:GENERATED -->"
_MARKER_RE = re.compile(r"<!-- WIKI:GENERATED unit=([\w.-]+) -->")

_HUMAN_OWNED_START_RE = re.compile(r"<!-- WIKI:HUMAN-OWNED -->")
_HUMAN_OWNED_END_RE = re.compile(r"<!-- /WIKI:HUMAN-OWNED -->")


def _find_unit_ids_outside_human_owned(text: str) -> list[str]:
    """Find WIKI:GENERATED unit IDs that are NOT inside a HUMAN-OWNED fence."""
    # Build set of character ranges that are inside HUMAN-OWNED fences.
    human_ranges: list[tuple[int, int]] = []
    for m in _HUMAN_OWNED_START_RE.finditer(text):
        end = _HUMAN_OWNED_END_RE.search(text, m.end())
        if end:
            human_ranges.append((m.start(), end.end()))

    def _in_human_owned(pos: int) -> bool:
        return any(start <= pos < end for start, end in human_ranges)

    return [m.group(1) for m in _MARKER_RE.finditer(text) if not _in_human_owned(m.start())]


# Tier-1 living docs eligible for generated fact-blocks (CLAUDE.md §Rule 12 /
# DESIGN_WIKI_GENERATION_LOOP_V1.md §4 scope). This is also the migration
# domain — the set of docs the generation loop operates over. CLAUDE.md is
# explicitly excluded: it stays hand-authored as the agent entry point.
# Docs are only touched if they actually contain a marker — this list is the
# search scope, not a mandate that every doc has one.
TIER1_DOCS = (
    "README.md",
    "P5_ROADMAP.md",
    "KNOWN_ISSUES.md",
    "KNOWN_LIMITATIONS.md",
    "docs/HOWTO.md",
    "docs/ADMIN_GUIDE.md",
    "docs/SECURITY_BENCH_EXEC.md",
    "docs/USER_GUIDE.md",
    "docs/CLUSTER_SCALE.md",
    "docs/ALERTS.md",
    "docs/PERFORMANCE.md",
    "docs/MCP_DEV_TOOLING.md",
    "docs/COMPLIANCE_FALLBACK_POLICY.md",
    "docs/BACKUP_RESTORE.md",
    "docs/LAB_SETUP.md",
    "docs/PERSONA_MATRIX_CI.md",
    "docs/AGENT_LOOP.md",
    "docs/DESIGN_WIKI_GENERATION_LOOP_V1.md",
    "docs/security/corpus_injection.md",
    "config/MODEL_CATALOG.md",
    "tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md",
    "tests/PORTAL5_BENCH_EXECUTE_V4.md",
    "tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md",
)


def render_unit_into_doc(doc_path: Path, unit_id: str) -> bool:
    """Replace the `<!-- WIKI:GENERATED unit=<unit_id> -->` block in
    `doc_path` with the unit's current body. Returns True if the doc's
    content changed. Raises if the doc has no such marker — markers are
    added once, by hand, at the point in the doc where the fact belongs;
    this function only ever fills them in, never invents a location.
    """
    unit = load_unit(unit_id)
    if unit is None:
        raise ValueError(f"No such wiki unit: {unit_id!r}")

    text = doc_path.read_text(encoding="utf-8")
    start = _BLOCK_START.format(unit_id=unit_id)
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(_BLOCK_END), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"No managed block for unit={unit_id!r} found in {doc_path}")

    replacement = f"{start}\n{unit.body}\n{_BLOCK_END}"
    new_text = pattern.sub(lambda _m: replacement, text, count=1)
    changed = new_text != text
    if changed:
        doc_path.write_text(new_text, encoding="utf-8")
    return changed


def render_all_generated_blocks(repo_root: Path, doc_paths: list[Path] | None = None) -> list[Path]:
    """Scan Tier-1 docs for WIKI:GENERATED markers and re-render each block
    from its unit's current body. Returns the list of docs that changed.
    """
    if doc_paths is None:
        doc_paths = [repo_root / rel for rel in TIER1_DOCS]

    changed_docs: list[Path] = []
    for doc_path in doc_paths:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        unit_ids = _find_unit_ids_outside_human_owned(text)
        doc_changed = False
        for unit_id in unit_ids:
            if render_unit_into_doc(doc_path, unit_id):
                doc_changed = True
        if doc_changed:
            changed_docs.append(doc_path)
    return changed_docs


def check_generated_blocks_current(
    repo_root: Path,
    doc_paths: list[Path] | None = None,
    unit_ids: set[str] | None = None,
) -> list[str]:
    """Read-only drift check: which docs have a generated block that does
    NOT match its unit's current body right now. Empty list = clean. Used
    by the validate gate — does not write anything.

    `unit_ids`, if given, scopes the check to that set (P0 A4: AW governs
    the KEEP-FACT set only — see `claims.fact_unit_ids`).
    """
    if doc_paths is None:
        doc_paths = [repo_root / rel for rel in TIER1_DOCS]

    drifted: list[str] = []
    for doc_path in doc_paths:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        for unit_id in _find_unit_ids_outside_human_owned(text):
            if unit_ids is not None and unit_id not in unit_ids:
                continue
            unit = load_unit(unit_id)
            if unit is None:
                drifted.append(f"{doc_path}: block references missing unit {unit_id!r}")
                continue
            start = _BLOCK_START.format(unit_id=unit_id)
            pattern = re.compile(re.escape(start) + r"\n(.*?)\n" + re.escape(_BLOCK_END), re.DOTALL)
            m = pattern.search(text)
            if m is None:
                drifted.append(f"{doc_path}: malformed block for unit {unit_id!r}")
            elif m.group(1) != unit.body:
                drifted.append(f"{doc_path}: block for unit {unit_id!r} does not match unit body")
    return drifted


def render_report(repo_root: Path) -> dict:
    """Migration progress report over the doc surface.

    Returns {migrated: [...], unmigrated: [...], gamed: [...], blocks_total: int,
    coverage_pct: float, human_ratio: {path: ratio}}.
    coverage_pct = migrated / (migrated + unmigrated) over TIER1_DOCS (excl CLAUDE.md).
    gamed = docs that pass V1 substantive_remainder check but fail V2 (no generated
    blocks or human-fence ratio exceeded) — these are the fence-everything cheats.
    """
    from portal.platform.wiki.migration import (
        _HUMAN_FENCE_MAX,
        fenced_human_lines,
        generated_block_count,
        human_owned_reasons,
        substantive_remainder,
        total_substantive_lines,
    )

    migrated: list[str] = []
    unmigrated: list[str] = []
    gamed: list[str] = []
    blocks_total = 0
    human_ratio: dict[str, float] = {}

    for rel in TIER1_DOCS:
        p = repo_root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        blocks_total += len(_MARKER_RE.findall(text))
        if doc_is_migrated(p):
            migrated.append(rel)
            # Report human ratio for migrated docs
            total = total_substantive_lines(text)
            if total > 0:
                ratio = fenced_human_lines(text) / total
                human_ratio[rel] = round(ratio, 3)
        else:
            # Check if this is a "gamed" doc: passes V1 check (no remainder)
            # but fails V2 (no generated blocks or ratio exceeded)
            remainder = substantive_remainder(text)
            gen_count = generated_block_count(text)
            human = fenced_human_lines(text)
            total = total_substantive_lines(text)
            reasons = human_owned_reasons(text)
            has_bad_reason = any(r == "[MISSING]" for r in reasons)
            ratio = human / max(1, total) if total > 0 else 0

            if remainder == "" and (gen_count < 1 or ratio > _HUMAN_FENCE_MAX or has_bad_reason):
                gamed.append(rel)
            else:
                unmigrated.append(rel)

    total = len(migrated) + len(unmigrated) + len(gamed)
    coverage_pct = (len(migrated) / total * 100) if total else 0.0
    return {
        "migrated": migrated,
        "unmigrated": unmigrated,
        "gamed": gamed,
        "blocks_total": blocks_total,
        "coverage_pct": round(coverage_pct, 1),
        "human_ratio": human_ratio,
    }


def render_admin_guide(output_dir: Path | None = None) -> Path:
    """Render an admin guide from canonical units."""
    units = load_all()
    why_units = [u for u in units if u.kind == "why"]
    what_units = [u for u in units if u.kind == "what"]

    lines = [
        "<!-- GENERATED FROM portal_wiki/canonical/ — edit the source unit, not this file -->",
        "",
        "# Portal 5 Admin Guide",
        "",
        f"*Deterministic projection of {len(units)} canonical units.*",
        "",
        "## Architecture Overview",
        "",
    ]

    # Architecture from why-units
    for unit in sorted(why_units, key=lambda u: u.title)[:10]:
        lines.append(f"### {unit.title}")
        lines.append(f"*Source: {unit.sources[0].path if unit.sources else 'unknown'}*")
        lines.append("")
        lines.append(unit.body[:500])
        lines.append("")

    # Components from what-units
    lines.extend(
        [
            "## Components",
            "",
        ]
    )
    for unit in sorted(what_units, key=lambda u: u.title)[:15]:
        lines.append(f"- **{unit.title}**: {len(unit.sources)} source(s)")

    lines.extend(
        [
            "",
            "---",
            f"*{len(units)} knowledge units referenced.*",
        ]
    )

    content = "\n".join(lines)
    output_dir = output_dir or Path("docs/generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ADMIN_GUIDE.md"
    path.write_text(content, encoding="utf-8")
    return path


def render_architecture_map(output_dir: Path | None = None) -> Path:
    """Render an architecture map from canonical units."""
    units = load_all()

    lines = [
        "<!-- GENERATED FROM portal_wiki/canonical/ — edit the source unit, not this file -->",
        "",
        "# Portal 5 Architecture Map",
        "",
        f"*Deterministic projection of {len(units)} canonical units.*",
        "",
        "## Knowledge Layer",
        "",
        "| Unit ID | Kind | Sources |",
        "|---------|------|---------|",
    ]

    for unit in sorted(units, key=lambda u: u.id):
        src_count = len(unit.sources)
        lines.append(f"| `{unit.id}` | {unit.kind} | {src_count} |")

    lines.extend(
        [
            "",
            f"**Total:** {len(units)} units",
            "",
            "## Source Distribution",
            "",
        ]
    )

    # Count sources by type
    source_types: dict[str, int] = {}
    for unit in units:
        for src in unit.sources:
            source_types[src.type] = source_types.get(src.type, 0) + 1

    for stype, count in sorted(source_types.items()):
        lines.append(f"- **{stype}**: {count} references")

    content = "\n".join(lines)
    output_dir = output_dir or Path("docs/generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ARCHITECTURE_MAP.md"
    path.write_text(content, encoding="utf-8")
    return path
