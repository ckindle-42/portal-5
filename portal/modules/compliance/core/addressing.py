"""Canonical addressing and traversal of captured compliance sections.

This module owns the meaning of a section id, regulatory address, glossary
term, and document reference.  MCP is only an adapter around these functions;
keeping the implementation here prevents the reader and the HTTP tool surface
from growing divergent address semantics.
"""

from __future__ import annotations

from typing import Any


def clip(text: str, max_chars: int) -> tuple[str, dict[str, Any]]:
    body = str(text or "")
    if max_chars <= 0 or len(body) <= max_chars:
        return body, {}
    return body[:max_chars], {
        "truncated": True,
        "returned_chars": max_chars,
        "total_chars": len(body),
        "omitted_chars": len(body) - max_chars,
    }


def cite_as(entry: dict[str, Any]) -> str:
    """The short, stable token a reader cites this section by (LOAD_AND_CONVERSE_V1
    §P5).

    A 20-hex id is not copyable without error — the measured failure is a
    citation carrying two dropped characters mid-hash, which resolves to
    nothing. Every tool payload that yields a section carries this token BESIDE
    the id: side letter + the id's first six hex characters, derived
    deterministically from the section's own identity, so the same token
    appears wherever the section does — search, read, requirement, material —
    and never collides with a render's numbered handles (``O1``, ``R2``).
    ``answer_contract`` resolves it by unique prefix; a prefix that is
    ambiguous resolves to nothing, never a guess.
    """
    from portal.modules.compliance.core.jurisdiction import is_operator_side

    raw = str(entry.get("section_id") or "")
    body = raw.split("#", 1)[0]
    hex_part = body.rsplit("-", 1)[-1][:6]
    letter = "O" if is_operator_side(entry.get("jurisdiction")) else "R"
    return f"{letter}-{hex_part}" if hex_part else ""


def with_cite_header(entry: dict[str, Any], text: str) -> str:
    """Prepend the short cite token to the section text a TOOL returns.

    Measured twice (LOAD_AND_CONVERSE_V1 P4 runs 1-2): shown a 20-hex id in a
    JSON field, the seat copies it with dropped or transposed characters
    mid-hash — deterministically, across independent runs — and a corrupted id
    resolves to nothing. Shown a short token ON the text it quotes from, it
    copies that. The header is explicit and the body below it is verbatim; the
    id stays in the payload beside it for every downstream consumer.
    """
    token = cite_as(entry)
    body = str(text or "")
    return f"[cite {token}]\n{body}" if token and body else body


def provenance(entry: dict[str, Any]) -> dict[str, Any]:
    """Return the complete citable identity of one captured unit."""
    return {
        "section_id": entry.get("section_id", ""),
        "cite_as": cite_as(entry),
        "document": entry.get("document_title") or entry.get("logical_id", ""),
        "logical_id": entry.get("logical_id", ""),
        "jurisdiction": entry.get("jurisdiction", ""),
        "source_kind": entry.get("source_kind", ""),
        "authority_tier": entry.get("authority_tier", ""),
        "document_number": entry.get("document_number", ""),
        "version": entry.get("version", ""),
        "revision_id": entry.get("revision_id", ""),
        "section_path": entry.get("path", ""),
        "heading_lineage": entry.get("headings", ""),
        "title": entry.get("title", ""),
        "unit_kind": entry.get("unit_kind", ""),
        "page": entry.get("page_start"),
        "effective_date": entry.get("effective_date"),
        "approved_date": entry.get("approved_date"),
        "inactive_date": entry.get("inactive_date"),
        "lifecycle_status": entry.get("lifecycle_status", ""),
        **{
            key: entry[key]
            for key in (
                "requirement_id",
                "requirement_ids",
                "relations",
                "vrf",
                "time_horizon",
                "applicable_systems",
                "lifecycle_state",
                "register_authority_tier",
                "authority_tier_disagreement",
            )
            if entry.get(key)
        },
    }


def within_clocks(entry: dict[str, Any], valid_at: str, known_at: str) -> tuple[bool, str]:
    effective = str(entry.get("effective_date") or "")
    inactive = str(entry.get("inactive_date") or "")
    if valid_at:
        if effective and effective > valid_at:
            return False, f"not effective at {valid_at} (effective {effective})"
        if inactive and inactive <= valid_at:
            return False, f"retired at {valid_at} (inactive from {inactive})"
    if known_at:
        recorded_from = str(entry.get("recorded_from") or "")[:10]
        recorded_to = entry.get("recorded_to")
        if recorded_from and recorded_from > known_at:
            return False, (
                f"UNKNOWN_KNOWLEDGE: the store recorded this revision on {recorded_from}, "
                f"after the requested known_at {known_at}"
            )
        if recorded_to and str(recorded_to)[:10] <= known_at:
            return False, (
                f"superseded in the store by {str(recorded_to)[:10]}, at or before the "
                f"requested known_at {known_at}"
            )
    return True, ""


def resolve_by_address(repo: Any, ref: str) -> dict[str, dict[str, Any]]:
    """Resolve a regulatory address, glossary term, or whole document."""
    from portal.modules.compliance.core import reading_assembly, section_index
    from portal.modules.compliance.core.glossary import glossary_index

    parsed = reading_assembly.parse_ref(ref)
    if parsed is not None:
        assembly = reading_assembly.assemble(repo, ref, include=["requirement"])
        ids = [
            section["section_id"]
            for component in assembly.get("components", [])
            for section in component.get("sections", [])
        ]
        if ids:
            return section_index.resolve_sections(repo, ids)
    entries = glossary_index(repo).get(ref.strip().lower())
    if entries:
        return section_index.resolve_sections(repo, [entry["section_id"] for entry in entries])
    ids = section_index.sections_in_scope(repo, logical_id=ref)
    return section_index.resolve_sections(repo, ids[:200]) if ids else {}


def neighbors(repo: Any, entry: dict[str, Any], max_chars: int) -> dict[str, Any]:
    from portal.modules.compliance.core import section_index

    rows = repo._conn.execute(
        """SELECT section_id FROM source_sections
           WHERE revision_id = ? AND heading_path = ? AND char_start >= 0
           ORDER BY ordinal""",
        (entry.get("revision_id"), entry.get("heading_path", "")),
    ).fetchall()
    siblings = section_index.resolve_sections(repo, [str(row[0]) for row in rows])
    return {
        "heading_path": entry.get("heading_path", ""),
        "siblings": [
            {**provenance(section), "text": clip(section.get("text", ""), max_chars)[0]}
            for section in sorted(siblings.values(), key=lambda item: item.get("ordinal", 0))
        ],
    }


def addressed_hits(repo: Any, query: str, max_chars: int) -> list[dict[str, Any]]:
    """Resolve an exact regulatory address before lexical retrieval."""
    from portal.modules.compliance.core import reading_assembly, section_index

    if reading_assembly.parse_ref(query) is None:
        return []
    out: list[dict[str, Any]] = []
    for section_id, entry in resolve_by_address(repo, query).items():
        text, note = clip(entry.get("text", ""), max_chars)
        out.append(
            {
                **provenance(entry),
                "section_id": section_id,
                "kb_id": section_index.CORPUS_FOR_JURISDICTION.get(
                    str(entry.get("jurisdiction", "")), ""
                ),
                "match": "address",
                "score": None,
                "text": text,
                **note,
            }
        )
    order = {"table_row": 0, "prose": 1, "list_item": 2, "table": 3}
    out.sort(key=lambda hit: (order.get(str(hit.get("unit_kind")), 4), hit.get("page") or 0))
    return out


__all__ = [
    "addressed_hits",
    "clip",
    "neighbors",
    "provenance",
    "resolve_by_address",
    "within_clocks",
]
