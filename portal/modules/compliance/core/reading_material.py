"""The population as text (PROVE_THEN_SCALE_V1 P1/P3).

A requirement's scope is a deterministic fact — ``requirement_scope.population``
states it — and this module renders that fact as the material a reading reads.
No search, no tool loop, no hop ceiling: the model is handed the neighbourhood
and asked the question, which is the whole of §P1's proof and the map unit the
sweep later runs at family scale.

**Shared body first, and why the order is load-bearing.** A CIP-007-6
population is ~two-thirds the standard's own fixed body — Section 4
applicability, Section 6 background, the implementation plan, version history —
measured byte-identical for every requirement in a revision (sha-verified
across Parts). Led with, that body sits in the prompt cache's shared prefix and
the Nth reading of a standard pays prefill only for its own scope; ordered any
other way, every reading re-prefills the whole thing. On a cluster the standard
is the shard key for the same reason.

**Every entry carries its standing.** A regulatory anchor keeps its
``relation``, an operator edge keeps its ``link_status``, a note keeps its
kind — so material that is merely PROPOSED cannot pass as approved, and a
reading built on proposed edges says so in every answer that uses it
(``requirement_scope.population`` keeps the distinction; this renderer refuses
to flatten it).
"""

from __future__ import annotations

import hashlib
from typing import Any

#: The components of a revision that do not vary with the requirement — the
#: standard's own fixed body. Measured on CIP-007-6: the fixed body is 41,802
#: chars (~13.9k tokens) of every Part's material, byte-identical across
#: requirements.
FIXED_COMPONENTS = (
    "applicability",
    "background",
    "effective_dates",
    "compliance_and_evidence_retention",
    "version_history",
    "implementation_plan",
    "technical_rationale_document",
)

#: The heading a population side travels under — the label that says what a
#: passage IS and the standing it carries.
_SIDE_HEADING = {
    "regulatory": "regulatory — anchored to this requirement by the standard's own join",
    "operator": "operator — the operator's own documents, linked by a recorded edge",
    "operator_note": "operator note — the operator's recorded decision about this requirement",
}


def _section_line(section: dict[str, Any], *, max_heading: int = 0) -> str:
    """``[id] document — heading path, page N`` — where a section IS."""
    heading = str(section.get("headings") or section.get("path") or "")
    if max_heading and len(heading) > max_heading:
        heading = heading[: max_heading - 1].rstrip() + "…"
    parts = [
        str(section.get("document_title") or section.get("logical_id") or ""),
        heading,
    ]
    line = " — ".join(p for p in parts if p and p != "None")
    page = section.get("page_start")
    if page:
        line += f", page {page}"
    return f"[{section.get('section_id', '')}] {line}"


def _fixed_section_line(section: dict[str, Any]) -> str:
    """The compact label a fixed-body section travels under. The component
    header above it already names the document and the part of the standard,
    so the label is id, title and page — the id because a citation wants one,
    nothing more because this body repeats for every requirement in the
    revision and its labels sit in every prompt of the sweep."""
    title = str(section.get("title") or "").strip()
    if not title:
        title = str(section.get("headings") or "").split(">")[-1].strip()
    if len(title) > 80:
        title = title[:79].rstrip() + "…"
    page = section.get("page_start")
    return f"[{section.get('section_id', '')}] {title}" + (f" (page {page})" if page else "")


def _side_heading(side: str) -> str:
    return _SIDE_HEADING.get(side, side or "unclassified")


def fixed_body(repo: Any, logical_id: str) -> dict[str, Any]:
    """The standard's fixed body as text, byte-identical for every requirement
    of the revision — rendered once per standard and reused as the shared
    prefix. ``sha`` is recorded so a re-render that is NOT byte-identical is a
    visible event rather than a silent cache miss."""
    from portal.modules.compliance.core.reading_assembly import assemble

    payload = assemble(repo, logical_id, budget_tokens=2**31)
    if "error" in payload:
        return {"error": payload["error"], "logical_id": logical_id}
    lines: list[str] = [
        f"# {logical_id} — the standard's own fixed body",
        "",
        "This part of the standard is identical for every requirement in this "
        "revision. It is the same text every reading of this standard receives; "
        "cite it exactly as you would cite any other part of the standard.",
        "",
    ]
    for component in payload.get("components", []):
        if component["component"] not in FIXED_COMPONENTS:
            continue
        lines.append(f"## {component['component']} — {component['why']}")
        for section in component.get("sections", []):
            lines.append("")
            lines.append(_fixed_section_line(section))
            lines.append(str(section.get("text", "")).strip())
    text = "\n".join(lines).strip() + "\n"
    return {
        "logical_id": logical_id,
        "text": text,
        "chars": len(text),
        "sha": hashlib.sha256(text.encode()).hexdigest()[:12],
        "components": sorted(FIXED_COMPONENTS),
    }


def _population_blocks(
    repo: Any, ref: str, *, valid_at: str = ""
) -> tuple[list[tuple[str, list[dict[str, Any]]]], dict[str, dict[str, Any]], dict[str, Any]]:
    """The requirement-specific side of the material, grouped by side in reading
    order (regulatory anchors, then operator edges, then notes), with each
    section's resolved text."""
    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.section_index import resolve_sections

    population = requirement_scope.population(repo, ref, valid_at=valid_at)
    sections = population.get("sections") or {}
    texts = resolve_sections(repo, list(sections))
    order = ("regulatory", "operator", "operator_note")
    grouped: list[tuple[str, list[dict[str, Any]]]] = []
    for side in order:
        entries = []
        for section_id, entry in sections.items():
            if entry.get("side") != side:
                continue
            resolved = dict(texts.get(section_id) or {})
            standing = ""
            if side == "regulatory":
                standing = (
                    f"anchored as {entry.get('relation', '')} for {entry.get('requirement_id', '')}"
                )
            elif side == "operator":
                standing = (
                    f"{entry.get('link_status', '')} edge to {entry.get('requirement_id', '')}"
                )
            elif side == "operator_note":
                standing = f"note on {entry.get('requirement_id', '')}"
            entries.append(
                {
                    "section_id": section_id,
                    "standing": standing,
                    "text": str(resolved.get("text", "")).strip(),
                    "headings": str(resolved.get("headings", "")),
                    "document_title": str(resolved.get("document_title") or ""),
                    "logical_id": str(resolved.get("logical_id") or ""),
                    "page_start": resolved.get("page_start"),
                    "ordinal": resolved.get("ordinal", 0),
                }
            )
        entries.sort(key=lambda e: (str(e.get("ordinal", 0)), e["section_id"]))
        if entries:
            grouped.append((side, entries))
    return grouped, sections, population


def render(
    repo: Any,
    ref: str,
    *,
    question: str = "",
    fixed: dict[str, Any] | None = None,
    valid_at: str = "",
) -> dict[str, Any]:
    """One requirement's population as the material a reading reads — one
    message, fixed body first, the question last.

    Ordered shared body first, then the requirement's own scope — regulatory
    anchors, operator edges, operator notes — every entry labelled with its
    side and standing. Returns the text plus the numbers the campaign reports:
    total, fixed-body share, and per-side section counts.
    """
    from portal.modules.compliance.core.reading_assembly import parse_ref

    parsed = parse_ref(ref)
    if parsed is None:
        return {"error": f"{ref!r} is not a regulatory address", "ref": ref}
    logical_id = parsed.logical_id
    if fixed is None:
        fixed = fixed_body(repo, logical_id)
    if "error" in fixed:
        return {"error": fixed["error"], "ref": ref}
    grouped, sections, population = _population_blocks(repo, ref, valid_at=valid_at)

    # The fixed body is the FIRST thing in the message and is byte-identical
    # for every requirement of the revision — that is what makes it a shared
    # cache prefix across a standard-ordered sweep. Everything that varies with
    # the ref (header, standing instructions, the scope, the question) comes
    # AFTER it; a per-ref line above the fixed body would break the prefix at
    # byte ~30 and re-prefill the whole body on every call.
    scope_lines: list[str] = [f"# This reading: {ref}", ""]
    scope_lines.extend(
        [
            "You are given the complete material for this question — every section "
            "the standard's own join and the operator's recorded edges place in this "
            "requirement's scope, plus the standard's fixed body above. Nothing here "
            "needs a search: everything is in this message, each entry labelled with "
            "what it is and the standing it carries. Answer only from this material; "
            "cite section ids in square brackets for every claim, and quote the text "
            "verbatim where the exact words matter. If the material does not contain "
            "the answer, say so plainly.",
            "",
            f"## {ref}'s own scope",
        ]
    )
    for side, entries in grouped:
        scope_lines.append("")
        scope_lines.append(f"### {_side_heading(side)} ({len(entries)} section(s))")
        for entry in entries:
            scope_lines.append("")
            line = _section_line(entry)
            if entry["standing"]:
                line += f" — standing: {entry['standing']}"
            scope_lines.append(line)
            scope_lines.append(entry["text"])
    scope_lines.append("")
    scope_lines.append("## The question")
    if question:
        scope_lines.append("")
        scope_lines.append(question)
    text = fixed["text"].rstrip() + "\n\n" + "\n".join(scope_lines).rstrip() + "\n"
    fixed_chars = int(fixed["chars"])
    return {
        "ref": ref,
        "text": text,
        "chars": len(text),
        "fixed_chars": fixed_chars,
        "population_chars": len(text) - fixed_chars,
        "fixed_sha": fixed["sha"],
        "n_sections": len(sections),
        "by_side": {side: len(entries) for side, entries in grouped},
        "population_detail": population.get("detail", ""),
        "population_method": population.get("population_method", ""),
    }


__all__ = ["FIXED_COMPONENTS", "fixed_body", "render"]
