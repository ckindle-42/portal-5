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
                    "_resolved": resolved,
                }
            )
        entries.sort(key=lambda e: (str(e.get("ordinal", 0)), e["section_id"]))
        if entries:
            grouped.append((side, entries))
    return grouped, sections, population


#: The document neighbourhood's caps (PROVE_THEN_SCALE_V1 P3.1) — stated in the
#: rendered label, not just here, so a reader knows when context was clipped.
NEIGHBOURHOOD_MAX_SECTIONS = 6
NEIGHBOURHOOD_MAX_CHARS = 6000
NEIGHBOURHOOD_ENTRY_CHARS = 1500


def _document_neighbourhood(
    repo: Any,
    section_id: str,
    requirement_id: str,
    resolved: dict[str, Any],
    *,
    revision_cache: dict[str, list[dict[str, Any]]],
    anchored_ids: set[str],
) -> list[dict[str, Any]]:
    """One operator section's document neighbourhood, capped.

    The `choice` case failed on exactly this: the operator's §3.5.1 permits
    one-of-three while §3.4.2.1 joins all three with "and" — a section-level
    population hands the model one clause of a procedure and the answer is
    wrong through no fault of the reading. So when an operator section enters
    a population, its document comes with it:

    * the parent heading (where the section sits in the document's own tree);
    * the SIBLING sections in reading order, nearest ordinal first;
    * any other section of the SAME document the graph also ties to this
      requirement — by anchor (the population's own regulatory side, which IS
      ``sections_for_requirement``) or by a recorded edge — because procedures
      build on each other and a requirement's material inside one document is
      often scattered.

    Capped at :data:`NEIGHBOURHOOD_MAX_SECTIONS` sections and
    :data:`NEIGHBOURHOOD_MAX_CHARS` of text, each entry clipped to
    :data:`NEIGHBOURHOOD_ENTRY_CHARS`; the cap is stated in the rendered
    label. Excludes sections already in the population.
    """
    revision_id = str(resolved.get("revision_id") or "")
    if not revision_id:
        return []
    if revision_id not in revision_cache:
        rows = repo._conn.execute(
            """SELECT section_id, ordinal, heading_path, title, char_start, char_end
               FROM source_sections WHERE revision_id = ? ORDER BY ordinal""",
            (revision_id,),
        ).fetchall()
        revision_cache[revision_id] = [dict(r) for r in rows]
    doc_rows = revision_cache[revision_id]
    by_id = {str(r["section_id"]): r for r in doc_rows}
    me = by_id.get(section_id)
    if me is None:
        return []

    def _parent(path: str) -> str:
        return str(path or "").rsplit(">", 1)[0].strip()

    my_parent = _parent(str(me.get("heading_path") or ""))
    my_ordinal = int(me.get("ordinal", 0) or 0)

    edge_rows = repo._conn.execute(
        """SELECT dst_ref FROM relationship_assertions
           WHERE src_ref = ? AND relation_type IN ('IMPLEMENTS','EVIDENCES','REFERENCES')
           AND status IN ('proposed','machine_determined','approved')""",
        (requirement_id,),
    ).fetchall()
    edge_sections = {str(r[0]).partition("::")[2] for r in edge_rows}
    graph_ids = (edge_sections & set(by_id)) | (anchored_ids & set(by_id))

    candidates: list[tuple[int, str]] = []
    for row in doc_rows:
        other = str(row["section_id"])
        if other == section_id:
            continue
        is_graph = other in graph_ids
        is_sibling = bool(my_parent) and _parent(str(row.get("heading_path") or "")) == my_parent
        if not (is_graph or is_sibling):
            continue
        distance = abs(int(row.get("ordinal", 0) or 0) - my_ordinal)
        candidates.append((0 if is_graph else 1, f"{distance:06d}|{other}"))
    candidates.sort()

    text_full = repo.get_document_text(revision_id) or ""
    out: list[dict[str, Any]] = []
    budget = NEIGHBOURHOOD_MAX_CHARS
    for _rank, key in candidates:
        if len(out) >= NEIGHBOURHOOD_MAX_SECTIONS or budget <= 0:
            break
        other = key.split("|", 1)[1]
        row = by_id[other]
        start, end = int(row.get("char_start") or 0), int(row.get("char_end") or 0)
        text = text_full[start:end] if 0 <= start < end <= len(text_full) else ""
        text = text.strip()
        if not text:
            continue
        if len(text) > NEIGHBOURHOOD_ENTRY_CHARS:
            text = text[:NEIGHBOURHOOD_ENTRY_CHARS].rstrip() + "… [clipped]"
        budget -= len(text)
        out.append(
            {
                "section_id": other,
                "title": str(row.get("title") or ""),
                "headings": str(row.get("heading_path") or ""),
                "document_title": str(resolved.get("document_title") or ""),
                "text": text,
                "graph_linked": other in graph_ids,
            }
        )
    return out


def _standing_instruction(extra: str) -> str:
    """The material's standing instruction, plus an optional A6.1 candidate
    sentence (tried separately, measured on all six cases, never tuned
    against the one case that failed)."""
    base = (
        "You are given the complete material for this question — every section "
        "the standard's own join and the operator's recorded edges place in this "
        "requirement's scope, plus the standard's fixed body above. Nothing here "
        "needs a search: everything is in this message, each entry labelled with "
        "what it is and the standing it carries. Answer only from this material; "
        "cite section ids in square brackets for every claim, and quote the text "
        "verbatim where the exact words matter. If the material does not contain "
        "the answer, say so plainly."
    )
    return f"{base} {extra.strip()}" if extra else base


def render(
    repo: Any,
    ref: str,
    *,
    question: str = "",
    fixed: dict[str, Any] | None = None,
    valid_at: str = "",
    neighbourhood: bool = True,
    extra_instruction: str = "",
) -> dict[str, Any]:
    """One requirement's population as the material a reading reads — one
    message, fixed body first, the question last.

    Ordered shared body first, then the requirement's own scope — regulatory
    anchors, operator edges, operator notes — every entry labelled with its
    side and standing. Operator sections arrive with their **document
    neighbourhood** (P3.1): parent heading, siblings in reading order, and the
    same document's other sections the graph ties to this requirement —
    capped, and the cap stated in the label. Returns the text plus the numbers
    the campaign reports: total, fixed-body share, and per-side section
    counts.

    ``extra_instruction`` appends one sentence to the standing instruction —
    the A6.1 measurement hook: candidate instructions are tried separately,
    each measured on all six cases, and never tuned against the one case that
    failed. It rides AFTER the fixed body, so a variant changes no byte of the
    shared prefix.
    """
    from portal.modules.compliance.core.reading_assembly import parse_ref

    parsed = parse_ref(ref)
    if parsed is None:
        return {"error": f"{ref!r} is not a regulatory address", "ref": ref}
    if fixed is None:
        # the fixed body is per REVISION — address the standard the way the
        # assembly's own parser expects (the plain standard id, not the
        # document's logical_id, which is not a regulatory address)
        fixed = fixed_body(repo, parsed.standard)
    if "error" in fixed:
        return {"error": fixed["error"], "ref": ref}
    grouped, sections, population = _population_blocks(repo, ref, valid_at=valid_at)
    revision_cache: dict[str, list[dict[str, Any]]] = {}
    anchored_ids = {
        entry["section_id"]
        for side, entries in grouped
        if side == "regulatory"
        for entry in entries
    }
    neighbourhood_sections = 0
    if neighbourhood:
        for side, entries in grouped:
            if side != "operator":
                continue
            for entry in entries:
                neighbours = _document_neighbourhood(
                    repo,
                    entry["section_id"],
                    ref,
                    entry["_resolved"],
                    revision_cache=revision_cache,
                    anchored_ids=anchored_ids,
                )
                entry["neighbourhood"] = neighbours
                neighbourhood_sections += len(neighbours)

    # The fixed body is the FIRST thing in the message and is byte-identical
    # for every requirement of the revision — that is what makes it a shared
    # cache prefix across a standard-ordered sweep. Everything that varies with
    # the ref (header, standing instructions, the scope, the question) comes
    # AFTER it; a per-ref line above the fixed body would break the prefix at
    # byte ~30 and re-prefill the whole body on every call.
    scope_lines: list[str] = [f"# This reading: {ref}", ""]
    scope_lines.extend(
        [
            _standing_instruction(extra_instruction),
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
            for neighbour in entry.get("neighbourhood", []):
                scope_lines.append("")
                scope_lines.append(
                    f"> document neighbourhood of {entry['section_id']} "
                    f"(same document, graph-linked to this requirement or a sibling clause; "
                    f"capped at {NEIGHBOURHOOD_MAX_SECTIONS} sections / "
                    f"{NEIGHBOURHOOD_MAX_CHARS} chars):"
                )
                scope_lines.append(f"> [{neighbour['section_id']}] {neighbour['title']}")
                scope_lines.append("> " + neighbour["text"].replace("\n", "\n> "))
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
        "n_neighbourhood_sections": neighbourhood_sections,
        "by_side": {side: len(entries) for side, entries in grouped},
        "population_detail": population.get("detail", ""),
        "population_method": population.get("population_method", ""),
    }


__all__ = ["FIXED_COMPONENTS", "fixed_body", "render"]
