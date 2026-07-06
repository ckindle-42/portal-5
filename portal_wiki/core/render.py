"""Render targeted views from the canonical layer.

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

Generates focused docs FROM canonical units, marked GENERATED, additive
to existing docs.
"""

from __future__ import annotations

import time
from pathlib import Path

from portal_wiki.core.store import load_all


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
        f"*Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}*",
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
        f"*Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}*",
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
