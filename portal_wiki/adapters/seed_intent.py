"""Seed canonical knowledge from intent sources (CLAUDE.md, design docs, RFCs).

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

Ingests "why" knowledge — architecture rationale, security decisions, design
principles — as WHY units, each citing its design-doc source.
"""

from __future__ import annotations

import re
from pathlib import Path

from portal_wiki.core.schema import KnowledgeUnit, SourceRef
from portal_wiki.core.store import save_unit

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _sanitize_id(text: str) -> str:
    """Make a string filesystem-safe for use as a unit ID."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:50]


def _read_file(rel_path: str) -> str:
    """Read a file relative to repo root."""
    full = _REPO_ROOT / rel_path
    if full.exists():
        return full.read_text(encoding="utf-8", errors="replace")
    return ""


def seed_intent(dry_run: bool = False) -> list[KnowledgeUnit]:
    """Seed WHY units from intent sources.

    Returns list of units created.
    """
    units: list[KnowledgeUnit] = []

    # CLAUDE.md — the architectural law
    claude_content = _read_file("CLAUDE.md")
    if claude_content:
        # Extract key sections
        sections = _extract_sections(claude_content)
        for section_title, section_body in sections.items():
            if len(section_body.strip()) < 50:
                continue
            unit_id = f"unit-claude-{_sanitize_id(section_title)}"
            try:
                unit = KnowledgeUnit(
                    id=unit_id,
                    kind="why",
                    title=f"CLAUDE.md — {section_title}",
                    sources=[SourceRef(type="design", path="CLAUDE.md", section=section_title)],
                    body=section_body[:2000],
                    tags=["claude", "architecture", "law"],
                )
                units.append(unit)
                if not dry_run:
                    save_unit(unit)
            except ValueError:
                continue

    # Design docs
    for doc_path in sorted(_REPO_ROOT.glob("docs/*.md")):
        rel = str(doc_path.relative_to(_REPO_ROOT))
        content = doc_path.read_text(encoding="utf-8", errors="replace")
        if len(content) < 100:
            continue

        sections = _extract_sections(content)
        for section_title, section_body in sections.items():
            if len(section_body.strip()) < 50:
                continue
            unit_id = f"unit-{doc_path.stem}-{_sanitize_id(section_title)}"
            try:
                unit = KnowledgeUnit(
                    id=unit_id,
                    kind="why",
                    title=f"{doc_path.stem} — {section_title}",
                    sources=[SourceRef(type="design", path=rel, section=section_title)],
                    body=section_body[:2000],
                    tags=["docs", doc_path.stem],
                )
                units.append(unit)
                if not dry_run:
                    save_unit(unit)
            except ValueError:
                continue

    return units


def _extract_sections(content: str) -> dict[str, str]:
    """Extract markdown sections as {title: body}."""
    sections: dict[str, str] = {}
    current_title = "Introduction"
    current_body: list[str] = []

    for line in content.split("\n"):
        if line.startswith("#"):
            if current_body:
                sections[current_title] = "\n".join(current_body)
            current_title = line.lstrip("#").strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        sections[current_title] = "\n".join(current_body)

    return sections
