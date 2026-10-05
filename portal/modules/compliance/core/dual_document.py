"""The dual-document payload (DATA_TRUTH Amendment 1 DD3).

A question is a DUAL-DOCUMENT request: asking it should return the standard's
normative text AND the operator's own documents for that standard, whole, so
the model can converse about both and state the facts they contain. This
builder is the ONE delivery path both reader-facing tools use:

* ``compliance_context(mode=material, ref)`` resolves by ADDRESS — the named
  requirement, every Part of it (G8: product questions name their requirement;
  similarity missed CIP-004-7 R4 and CIP-007-6 R2);
* ``compliance_search(query)`` with no requirement resolves to the TOP-2
  distinct standards through the governing-anchor lane (G3/G8: remote_access
  resolved to CIP-003 first; the evidence sat in CIP-005 documents).

Payload order (D-DT-8's design): (a) the standard — the resolved
requirements' normative text, every Part, from the governing anchors, no fixed
body (it is readable on request through ``compliance_read``); (b) the
operator's document set for that standard — the filing folder ∪ documents
whose own traceability appendix names the standard (the DD2 ADDRESSES
assertions make the second half a store lookup) — whole, in document order,
TOC / revision-log / document-control / appendix stripped, every section
labelled ``[<document title> § <heading>] (<section_id>)`` (G6: long-context
attribution failed on every route until the document name rode on every
section); (c) the operator's notes on the standard; (d) traceability facts —
"your document maps Part x to §n" — labelled as the operator's declaration.

Sizing (DD4): the payload is priced against the workspace's declared window
minus the predict budget minus a recorded persona/tools reserve, at the
measured minimum bytes-per-token. A document that does not fit whole is
DEFERRED — listed by title with a ``compliance_read`` instruction. Sections
are never clipped and the engine is never allowed to truncate.
"""

from __future__ import annotations

import re
from typing import Any

#: bytes-per-token measured MINIMUM on this seat (conversation_window's rule:
#: under-counting tokens is the one direction a truncation guard may never err)
BYTES_PER_TOKEN = 3.17

#: persona + tool schemas + conversation overhead on the reading seat,
#: MEASURED at DD4's pipeline turn (CIP-007-6 R2 payload, oMLX): 86,969 real
#: prompt tokens for a payload the 3.17 floor prices at 91,944 — at the 3.28
#: median the payload alone accounts for the whole prompt, so the true
#: overhead is ~0; 2,000 is kept as headroom
PERSONA_TOOLS_RESERVE_TOKENS = 2_000

#: roles whose sections are structure, never the operator's operative material
STRIPPED_ROLES = frozenset(
    {"TABLE_OF_CONTENTS", "REVISION_LOG", "DOCUMENT_CONTROL", "TRACEABILITY_ASSERTION"}
)

_STD_TOKEN_RE = re.compile(r"CIP-\d{2,3}(?:-\d+(?:\.\d+)?[a-z]?)?")
_ID_STANDARD_RE = re.compile(r"^(CIP-\d{2,3}(?:-\d+(?:\.\d+)?[a-z]?)?)")


def _standard_of(requirement_id: str) -> str:
    """The standard id ('CIP-010-4') of a register requirement id. Requirement
    ids are not uniformly '... Rn' shaped ('CIP-003-9 Attachment 1 Part 6.1'
    has no R token), so the prefix is matched, never split."""
    match = _ID_STANDARD_RE.match(requirement_id)
    return match.group(1) if match else requirement_id


def build(
    repo: Any,
    *,
    requirement_ref: str = "",
    query: str = "",
    context_limit: int = 131_072,
    predict_limit: int = 24_576,
    served_ceiling: int | None = None,
) -> dict[str, Any]:
    """Assemble the dual-document payload for one question.

    Give exactly one of ``requirement_ref`` (an address) or ``query`` (free
    text; the top-2 standards are resolved from the governing-anchor lane).
    ``served_ceiling`` is the minimum window a reachable tier-1 route actually
    serves (runtime_config.reading_route_ceiling); when it is below the
    declared limit the payload is priced under it — the guard refuses or
    routes rather than let any route truncate (DD4).
    """
    if requirement_ref:
        resolution = _resolve_by_address(repo, requirement_ref)
    else:
        resolution = _resolve_by_query(repo, query)
    if resolution.get("error"):
        return resolution
    requirement_ids: list[str] = resolution["requirement_ids"]
    standards: list[str] = resolution["standards"]

    standard_text = _standard_side(repo, requirement_ids)
    notes = _notes_side(repo, requirement_ids)
    facts = _traceability_facts(repo, requirement_ids)
    documents = _document_set(repo, standards)

    budget_tokens = max(0, context_limit - predict_limit - PERSONA_TOOLS_RESERVE_TOKENS)
    included: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    # (a)+(c)+(d) always travel; the walk adds whole documents until the budget
    used = _estimate(standard_text + notes + facts)
    # traceability-named documents first, then the folder's remainder
    ordered = sorted(
        documents,
        key=lambda doc: (0 if doc["origin"] == "traceability" else 1, doc["logical_id"]),
    )
    blocks: list[str] = []
    for doc in ordered:
        # whole documents until the budget; a document that does not fit whole
        # is deferred and listed — never clipped, never partially sent
        if used + doc["tokens"] <= budget_tokens:
            blocks.append(doc["text"])
            used += doc["tokens"]
            included.append(
                {k: doc[k] for k in ("logical_id", "title", "origin", "tokens", "sections")}
            )
        else:
            deferred.append({"logical_id": doc["logical_id"], "title": doc["title"]})
    text = "\n\n".join(block for block in (standard_text, *blocks, notes, facts) if block)
    return {
        "mode": "dual_document",
        "resolved": True,
        "requirement_refs": requirement_ids,
        "standards": standards,
        "resolution": resolution.get("detail", ""),
        "text": text,
        "documents_included": included,
        "documents_deferred": deferred,
        "notes_count": notes.count("\n[") if notes else 0,
        "window": {
            "context_limit": context_limit,
            "served_ceiling": served_ceiling,
            "predict_limit": predict_limit,
            "persona_tools_reserve": PERSONA_TOOLS_RESERVE_TOKENS,
            "budget_tokens": budget_tokens,
            "estimated_tokens": used,
            "bytes_per_token": BYTES_PER_TOKEN,
            "fits": used <= budget_tokens,
        },
        "note": (
            "the dual-document payload: the standard's normative text first, then "
            "the operator's own documents for that standard, every section labelled "
            "[document § heading] (section id); answer from what this returns and "
            "support each claim by quoting, in double quotes, the exact words it "
            "rests on"
        ),
    }


def _estimate(text: str) -> int:
    return int(len(text.encode("utf-8")) / BYTES_PER_TOKEN)


# ── resolution ───────────────────────────────────────────────────────────────


def _resolve_by_address(repo: Any, ref: str) -> dict[str, Any]:
    from portal.modules.compliance.core.reading_assembly import parse_ref

    parsed = parse_ref(ref)
    if parsed is None:
        return {
            "error": f"{ref!r} is not a regulatory address",
            "resolved": False,
            "requirement_ids": [],
            "standards": [],
        }
    standard = str(parsed)
    standard_only = _standard_of(standard)
    register = _register_ids(repo)
    if parsed.part:
        requirement_ids = [canonical for canonical in register if canonical == standard]
        return {
            "requirement_ids": requirement_ids,
            "standards": [standard_only],
            "detail": "addressed Part",
        }
    if parsed.requirement:
        requirement_ids = sorted(rid for rid in register if rid.startswith(f"{standard} "))
        return {
            "requirement_ids": requirement_ids,
            "standards": [standard_only],
            "detail": "addressed requirement: every Part",
        }
    # a whole standard: every in-force requirement
    requirement_ids = sorted(rid for rid in register if rid.startswith(f"{standard} R"))
    return {
        "requirement_ids": requirement_ids,
        "standards": [standard_only],
        "detail": "addressed standard: every requirement",
    }


def _resolve_by_query(repo: Any, query: str) -> dict[str, Any]:
    """The top-2 distinct standards through the governing-anchor lane (G3/G8):
    the fused search ranks candidates; only hits on governing-anchor sections
    count; their standards, best rank first, distinct, top two."""
    from portal.modules.compliance.core import search_service

    anchors = _anchor_sections(repo)
    if not anchors:
        return {
            "error": "no governing anchors in the register",
            "resolved": False,
            "requirement_ids": [],
            "standards": [],
        }
    standards: list[str] = []
    try:
        results = search_service.search(repo, query, top_k=50)
    except Exception as exc:  # noqa: BLE001 - a dead index falls back to text
        results = {"results": [], "search_error": str(exc)}
    for row in results.get("results") or []:
        section_id = str(row.get("section_id") or "")
        requirement_id = anchors.get(section_id)
        if not requirement_id:
            continue
        standard = _standard_of(requirement_id)
        if standard not in standards:
            standards.append(standard)
        if len(standards) == 2:
            break
    if not standards:
        # a query that names its standards outright ("CIP-003 and CIP-004")
        seen: list[str] = []
        for match in _STD_TOKEN_RE.finditer(query):
            standard = _current_standard(repo, match.group(0))
            if standard and standard not in seen:
                seen.append(standard)
        standards = seen[:2]
    if not standards:
        return {
            "error": f"no governing-anchor standard resolved for {query!r}",
            "resolved": False,
            "requirement_ids": [],
            "standards": [],
        }
    register = _register_ids(repo)
    requirement_ids = sorted(
        rid for rid in register if any(rid.startswith(f"{standard} R") for standard in standards)
    )
    return {
        "requirement_ids": requirement_ids,
        "standards": standards,
        "detail": f"top-{len(standards)} standards from the governing-anchor lane",
    }


def _register_ids(repo: Any) -> list[str]:
    """Every requirement id anchored in the register (any relation), as the
    resolution pool — currency filters the TEXT, not the address space."""
    rows = repo._conn.execute("select distinct requirement_id from requirement_sections").fetchall()
    return sorted(str(row[0]) for row in rows)


def _anchor_sections(repo: Any) -> dict[str, str]:
    """section_id → requirement_id for the CURRENT governing anchors."""
    from portal.modules.compliance.core.section_index import _governing_revisions

    governing = _governing_revisions(repo, "US")
    rows = repo._conn.execute(
        "select section_id, requirement_id, revision_id from requirement_sections"
        " where relation='governing'"
    ).fetchall()
    anchors: dict[str, str] = {}
    for section_id, requirement_id, revision_id in rows:
        if revision_id in governing:
            anchors.setdefault(str(section_id), str(requirement_id))
    return anchors


def _current_standard(repo: Any, standard_number: str) -> str | None:
    """The in-force register standard for 'CIP-010' → 'CIP-010-4', if any."""
    for rid in _register_ids(repo):
        base = _standard_of(rid)
        if base == standard_number or re.match(rf"{re.escape(standard_number)}-\d", base):
            return base
    return None


# ── payload sides ────────────────────────────────────────────────────────────


def _standard_side(repo: Any, requirement_ids: list[str]) -> str:
    """(a) the standard: every resolved Part's normative text, requirement by
    requirement, from the CURRENT governing anchor spans. No fixed body."""
    from portal.modules.compliance.core.section_index import _governing_revisions

    governing = _governing_revisions(repo, "US")
    cache: dict[str, str] = {}
    spans: dict[str, tuple[str, int, int]] = {}
    rows = repo._conn.execute(
        "select requirement_id, revision_id, char_start, char_end from requirement_sections"
        " where relation='governing'"
    ).fetchall()
    for requirement_id, revision_id, char_start, char_end in rows:
        requirement_id = str(requirement_id)
        if requirement_id in spans:
            continue
        if revision_id in governing:
            spans[requirement_id] = (str(revision_id), int(char_start), int(char_end))
        else:
            spans.setdefault(requirement_id, (str(revision_id), int(char_start), int(char_end)))
    blocks: list[str] = []
    last_requirement: str | None = None
    for requirement_id in requirement_ids:
        requirement, _, part = requirement_id.partition(" Part ")
        if requirement != last_requirement:
            blocks.append(f"== {requirement} ==")
            last_requirement = requirement
        span = spans.get(requirement_id)
        if not span:
            continue
        if span[0] not in cache:
            cache[span[0]] = repo.get_document_text(span[0]) or ""
        text = cache[span[0]][span[1] : span[2]].strip()
        if text:
            blocks.append(f"{requirement_id}: {text}" if part else text)
    return "\n".join(blocks)


def _notes_side(repo: Any, requirement_ids: list[str]) -> str:
    """(c) the operator's notes on the resolved requirements."""
    from portal.modules.compliance.core.notes import notes_for

    blocks: list[str] = []
    for requirement_id in requirement_ids:
        for note in notes_for(repo, requirement_id):
            body = str(note.get("text") or "").strip()
            if body:
                blocks.append(f"[operator note on {requirement_id}] {body}")
    return "\n\n".join(blocks)


def _traceability_facts(repo: Any, requirement_ids: list[str]) -> str:
    """(d) 'your <document> maps <Part> to §<heading>' — the DD2 assertions,
    labelled as the operator's declaration."""
    if not requirement_ids:
        return ""
    wanted = set(requirement_ids)
    placeholders = ",".join("?" * len(wanted))
    rows = repo._conn.execute(
        "select src_ref, dst_ref, dst_revision_id, citations_json from relationship_assertions"
        f" where derivation='operator_traceability' and relation_type='IMPLEMENTS'"
        f" and src_ref in ({placeholders})",
        sorted(wanted),
    ).fetchall()
    facts: list[str] = []
    seen: set[tuple[str, str]] = set()
    for src_ref, dst_ref, dst_revision_id, _citations in rows:
        pair = (str(src_ref), str(dst_ref))
        if pair in seen:
            continue
        seen.add(pair)
        heading = _section_heading(repo, str(dst_ref))
        document = _document_title(repo, str(dst_revision_id)) if dst_revision_id else ""
        facts.append(f"your {document or 'document'} maps {src_ref} to §{heading or dst_ref}")
    if not facts:
        return ""
    return (
        "traceability (the operator's own declaration, machine-read from its "
        "appendix):\n" + "\n".join(f"- {fact}" for fact in sorted(facts))
    )


def _document_set(repo: Any, standards: list[str]) -> list[dict[str, Any]]:
    """(b) per standard: the filing folder ∪ the traceability-named documents,
    whole, in document order, structure stripped, sections labelled."""
    documents: dict[str, dict[str, Any]] = {}
    for standard in standards:
        folder = standard.rsplit("-", 1)[0] if standard.count("-") >= 2 else standard
        folder_docs = [
            str(row[0])
            for row in repo._conn.execute(
                "select logical_id from source_documents where logical_id like ?",
                (f"{folder}/%",),
            ).fetchall()
        ]
        named = [
            str(row[0])
            for row in repo._conn.execute(
                "select distinct src_ref from relationship_assertions"
                " where derivation='operator_traceability' and relation_type='ADDRESSES'"
                " and dst_ref like ?",
                (f"{standard} R%",),
            ).fetchall()
        ]
        for logical_id in folder_docs + named:
            origin = "traceability" if logical_id in named else "folder"
            if logical_id in documents:
                if origin == "traceability":
                    documents[logical_id]["origin"] = "traceability"
                continue
            doc = _render_document(repo, logical_id, origin)
            if doc:
                documents[logical_id] = doc
    return list(documents.values())


def _governing_all(repo: Any) -> set[str]:
    """The governing revision of every document, across jurisdictions — the
    operator corpus is jurisdiction 'internal', the register 'US'; both use
    the store's own currency rule."""
    from portal.modules.compliance.core.section_index import _governing_revisions

    jurisdictions = [
        str(row[0])
        for row in repo._conn.execute(
            "select distinct jurisdiction from source_documents"
        ).fetchall()
    ]
    governing: set[str] = set()
    for jurisdiction in jurisdictions:
        governing |= _governing_revisions(repo, jurisdiction)
    return governing


def _render_document(repo: Any, logical_id: str, origin: str) -> dict[str, Any] | None:
    governing = _governing_all(repo)
    row = repo._conn.execute(
        "select title from source_documents where logical_id = ?", (logical_id,)
    ).fetchone()
    title = str(row[0]) if row and row[0] else logical_id
    revision = repo._conn.execute(
        "select revision_id from document_revisions where logical_id = ?",
        (logical_id,),
    ).fetchall()
    live = [str(r[0]) for r in revision if str(r[0]) in governing]
    if not live:
        return None
    sections = repo._conn.execute(
        "select section_id, heading_path, path, role, char_start, char_end, ordinal"
        " from source_sections where revision_id = ? order by ordinal",
        (live[0],),
    ).fetchall()
    full = repo.get_document_text(live[0]) or ""
    blocks: list[str] = []
    for section_id, heading_path, path, role, char_start, char_end, _ordinal in sections:
        if role in STRIPPED_ROLES:
            continue
        start, end = int(char_start or 0), int(char_end or 0)
        if not (0 <= start < end <= len(full)):
            continue
        text = full[start:end].strip()
        if not text:
            continue
        heading = str(heading_path or path or "").strip()
        blocks.append(f"[{title} § {heading}] ({section_id})\n{text}")
    if not blocks:
        return None
    return {
        "logical_id": logical_id,
        "title": title,
        "origin": origin,
        "sections": len(blocks),
        "tokens": _estimate("\n\n".join(blocks)),
        "text": f"## {title} ({logical_id})\n\n" + "\n\n".join(blocks),
    }


def _section_heading(repo: Any, section_id: str) -> str:
    row = repo._conn.execute(
        "select heading_path, path from source_sections where section_id = ?",
        (section_id,),
    ).fetchone()
    if not row:
        return ""
    return str(row[0] or row[1] or "").strip()


def _document_title(repo: Any, revision_id: str) -> str:
    row = repo._conn.execute(
        "select d.title from source_documents d join document_revisions r"
        " on r.logical_id = d.logical_id where r.revision_id = ?",
        (revision_id,),
    ).fetchone()
    return str(row[0]) if row and row[0] else ""
