"""Wiring the reader (BILATERAL_CORPUS_V1 P6).

What this module builds is **the conditions for reading**, not a reading
procedure. There is no schema here, no field list, no outcome vocabulary and no
canonical stored reading of a requirement. There is no canonical reading of R2 —
there is a reading for *are we stricter than we need to be* and a different one
for *what would an auditor ask for*, and collapsing them into one artifact is the
mistake §0 names, in a new place.

What the module does is narrow and mechanical:

1. **Hand over the whole neighbourhood.** The reading call receives
   :func:`reading_assembly.assemble` output — every Part row with its cells, the
   Measures, the Guidelines and Technical Basis, the Rationale, the VSL rows,
   Section 4 applicability, Section 6 background and its reading conventions, the
   resolved Glossary terms, the implementation plan, the operator's linked
   sections in full, and the operator's own notes. Nothing is filtered on the
   model's behalf and nothing is marked ineligible to cite. What the budget could
   not hold is stated in the payload and repeated to the model, so it knows what
   it has not seen.

2. **Ask the question that was actually asked.** The prompt carries the
   analyst's question and the material. It does not decompose the question into
   stages, does not demand an output shape, and does not tell the model how to
   weigh a Measure against the Technical Basis against the requirement text.

3. **Verify citations; adjudicate nothing.** Every cited id is resolved against
   the pinned revision and **reported with what it resolves to** — a regulatory
   Part, a Measure, a GTB passage, an operator procedure, an operator note, a
   prior answer — so the reader and the analyst can both see what the argument
   rests on. A quantity the answer claims is checked against the text it cited.
   An unresolvable citation is named. **No code here decides that a citation is
   disqualified**, and no code here decides whether the answer is right.

4. **Keep the conversation.** Question, answer, citations, timestamp, model,
   latency and any operator correction are retained and projected into the
   corpus, labelled ``derived``. A stored answer is one analyst's notes pinned to
   the revisions it read: never a fact, never promoted by age, always outranked
   by a :mod:`~core.notes` note, and marked superseded when a revision it cited
   moves.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

#: Section ids as they appear in an answer. Both extractors' prefixes plus the
#: split sub-unit suffix, so an id the model copied from the material resolves
#: exactly as the model saw it.
CITATION_RE = re.compile(r"\b((?:c|i)section-[0-9a-f]{20}(?:#\d+)?)\b")

#: A quantity claim in an answer: "35 calendar days", "30 days", "three years".
_QUANTITY_RE = re.compile(
    r"\b(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:calendar\s+|business\s+|working\s+)?(day|days|month|months|year|years|hour|hours)\b",
    re.I,
)

_WORD_NUMBERS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}

SYSTEM_PROMPT = """You are reading with a compliance analyst.

You have two bodies of material in front of you: NERC regulatory text, and the \
operator's own policies, procedures, work instructions and recorded decisions. \
Both are verbatim. Each passage is labelled with what it is and where it came \
from, and carries a section id.

Answer the analyst's question in prose. Cite the section id of any passage you \
rely on, inline, as you go — an argument the analyst cannot follow back to the \
text is not usable. Quote where quoting is clearer than paraphrase.

Say plainly when the material you have been given cannot settle something, and \
say what would settle it. If part of the neighbourhood was omitted for budget, \
it is named at the end of the material; take that into account.

Do not invent a section id. Do not treat the standard as evidence that the \
operator does anything."""


def _render_material(context: dict[str, Any]) -> str:
    """The assembly, as text the model reads. Structure only — every label says
    what a passage IS and where it came from, never what it means."""
    lines: list[str] = []
    revision = context.get("revision", {})
    lines.append(
        f"# {context.get('ref')} — {context.get('standard')} "
        f"(revision {revision.get('version') or 'unversioned'}, "
        f"effective {revision.get('effective_date') or 'unstated'}"
        + (f", inactive from {revision['inactive_date']}" if revision.get("inactive_date") else "")
        + f", read as at {context.get('valid_at')})"
    )
    for component in context.get("components", []):
        lines.append(f"\n## {component['component']} — {component['why']}")
        for section in component.get("sections", []):
            head = " / ".join(
                part
                for part in (section.get("headings"), section.get("title"))
                if part and part not in (section.get("headings") if part else "",)
            ) or str(section.get("headings") or section.get("title") or "")
            page = f", page {section['page']}" if section.get("page") else ""
            link = section.get("link_status")
            label = (
                f" [{link} link, {section.get('link_derivation') or 'unrecorded'}]" if link else ""
            )
            lines.append(f"\n[{section.get('section_id')}] {head}{page}{label}")
            if section.get("cells"):
                for cell in section["cells"]:
                    lines.append(f"    {cell['column']}: {cell['text']}")
            else:
                lines.append(str(section.get("text", "")).strip())
    notes = context.get("operator_notes") or []
    if notes:
        lines.append("\n## operator notes — the operator's own recorded decisions")
        for note in notes:
            lines.append(
                f"\n[{note['section_id']}] {note['kind']} about {note['subject_ref']}, "
                f"recorded {note['created_at'][:10]}"
                + (f" by {note['author']}" if note.get("author") else "")
            )
            lines.append(str(note.get("text", "")).strip())
    omitted = context.get("omitted") or []
    if omitted:
        lines.append("\n## omitted for budget — you have NOT seen these")
        for entry in omitted:
            lines.append(
                f"- {entry['component']}: {entry['sections']} sections "
                f"(~{entry['tokens']} tokens) — {entry['why']}"
            )
    return "\n".join(lines)


# ── citation verification (the one mechanical check that survives) ──────────


def _normalise_quantity(match: re.Match[str]) -> tuple[str, str]:
    number = match.group(1).lower()
    return _WORD_NUMBERS.get(number, number), match.group(2).lower().rstrip("s")


def verify_citations(repo: Any, answer: str, material: str = "") -> dict[str, Any]:
    """Resolve every id the answer cited, and report what each one IS.

    This adjudicates nothing. It reports:

    * whether the id resolves at all, in the pinned revision;
    * **what it resolves to** — jurisdiction, source kind, heading lineage,
      page — so an argument resting on the standard quoting itself as the
      operator's control is visible as exactly that, rather than passing as
      verified support (the ``_verify_duties`` defect, fixed here by resolving
      and labelling BOTH sides instead of checking one);
    * whether a quantity the answer claims appears in the text it cited.
    """
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    cited = list(dict.fromkeys(CITATION_RE.findall(answer)))
    resolved = resolve_sections(repo, cited)
    entries: list[dict[str, Any]] = []
    for ref in cited:
        entry = resolved.get(parent_section_id(ref))
        if entry is None:
            entries.append(
                {
                    "cited_ref": ref,
                    "resolved": False,
                    "detail": "does not resolve to any section in this store",
                }
            )
            continue
        entries.append(
            {
                "cited_ref": ref,
                "resolved": True,
                "resolves_to": _what_it_is(entry),
                "jurisdiction": entry.get("jurisdiction", ""),
                "source_kind": entry.get("source_kind", ""),
                "document": entry.get("document_title") or entry.get("logical_id", ""),
                "heading_lineage": entry.get("headings", ""),
                "page": entry.get("page_start"),
                "revision_id": entry.get("revision_id", ""),
                "effective_date": entry.get("effective_date"),
                "detail": "",
            }
        )

    cited_text = "\n".join(
        str(resolved[parent_section_id(r)].get("text", ""))
        for r in cited
        if parent_section_id(r) in resolved
    )
    haystack = cited_text + "\n" + material
    quantities: list[dict[str, Any]] = []
    for match in _QUANTITY_RE.finditer(answer):
        number, unit = _normalise_quantity(match)
        pattern = re.compile(rf"\b{re.escape(number)}\s+\S*\s?{unit}", re.I)
        word = next((w for w, d in _WORD_NUMBERS.items() if d == number), "")
        alt = re.compile(rf"\b{word}\s+\S*\s?{unit}", re.I) if word else None
        found = bool(pattern.search(haystack)) or bool(alt and alt.search(haystack))
        quantities.append(
            {
                "claim": match.group(0),
                "number": number,
                "unit": unit,
                "appears_in_cited_text": found,
            }
        )

    unresolved = [e["cited_ref"] for e in entries if not e["resolved"]]
    unsupported = [q["claim"] for q in quantities if not q["appears_in_cited_text"]]
    return {
        "citations": entries,
        "num_cited": len(entries),
        "unresolvable": unresolved,
        "quantities": quantities,
        "quantities_not_in_cited_text": unsupported,
        "note": (
            "resolution and quantity presence only — nothing here judges whether "
            "the answer is right, and no citation is disqualified"
        ),
    }


def _what_it_is(entry: dict[str, Any]) -> str:
    """A plain label for what a citation resolves to, from the section's own
    position and its document's own kind. No judgement, no eligibility."""
    kind = str(entry.get("source_kind") or "")
    heading = str(entry.get("headings") or "").lower()
    if kind == "glossary":
        return "NERC Glossary term"
    if kind == "operator_note":
        return "operator note — the operator's own recorded decision"
    if kind == "derived_answer":
        return "a stored answer from an earlier conversation, not a fact"
    if kind == "regulatory_standard":
        if "technical basis" in heading:
            return "regulatory — Guidelines and Technical Basis (interpretive, the standard's own)"
        if "compliance" in heading:
            return "regulatory — compliance and evidence retention"
        if "version history" in heading:
            return "regulatory — version history"
        if entry.get("unit_kind") == "table_row" and "requirements and measures" in heading:
            return "regulatory — a requirements table row (Part, Applicable Systems, Requirements, Measures)"
        return "regulatory — standard text"
    if kind in ("implementation_plan", "technical_rationale", "rsaw"):
        return f"regulatory companion document — {kind.replace('_', ' ')}"
    if str(entry.get("jurisdiction")) == "internal":
        return f"operator document — {kind.replace('_', ' ') or 'unclassified'}"
    return kind or "unclassified source"


# ── the reading call ────────────────────────────────────────────────────────


def read(
    repo: Any,
    question: str,
    ref: str,
    *,
    model: str,
    budget_tokens: int = 60_000,
    num_ctx: int = 0,
    reasoning_effort: bool | str | None = None,
    answer_tokens: int = 3072,
    valid_at: str = "",
    thread_id: str = "",
    store: bool = True,
    timeout: int = 900,
) -> dict[str, Any]:
    """One reading. Assemble, ask, verify the citations, keep the answer."""
    from portal.modules.compliance.core.notes import notes_for
    from portal.modules.compliance.core.reading_assembly import CHARS_PER_TOKEN, assemble
    from portal.modules.compliance.core.reading_transport import chat

    context = assemble(repo, ref, budget_tokens=budget_tokens, valid_at=valid_at)
    if "error" in context:
        return {"error": context["error"], "ref": ref}
    context["operator_notes"] = notes_for(repo, ref)
    material = _render_material(context)
    # the window must hold the material AND the answer, with room for the
    # chat template's own overhead — a context that truncates the material is
    # the keyhole again, silently.
    needed = (len(material) // CHARS_PER_TOKEN) + answer_tokens + 2048
    window = num_ctx or max(8192, 1 << (needed - 1).bit_length())

    result = chat(
        model,
        SYSTEM_PROMPT,
        f"{question}\n\n---\n\n{material}",
        budget=answer_tokens,
        fmt=None,
        think=reasoning_effort,
        num_ctx=window,
        timeout=timeout,
    )
    answer = result.content.strip()
    verification = verify_citations(repo, answer, material)
    payload: dict[str, Any] = {
        "question": question,
        "ref": context["ref"],
        "answer": answer,
        "thinking_chars": len(result.thinking),
        "model": model,
        "num_ctx": window,
        "material_chars": len(material),
        "material_tokens": len(material) // CHARS_PER_TOKEN,
        "components": [c["component"] for c in context["components"]],
        "omitted": context["omitted"],
        "verification": verification,
        "latency": {
            "elapsed_s": round(float(result.get("elapsed", 0)), 2),
            "load_duration_s": result.get("load_duration_s"),
            "prompt_eval_duration_s": result.get("prompt_eval_duration_s"),
            "eval_duration_s": result.get("eval_duration_s"),
            "eval_count": result.get("eval_count"),
            "prompt_eval_count": result.get("prompt_eval_count"),
            "prompt_bytes": result.get("prompt_bytes"),
        },
        "reasoning_effort": result.get("reasoning_effort"),
        "reasoning_downgraded": result.get("downgraded", ""),
    }
    if store:
        payload["answer_id"] = store_answer(repo, payload, context, thread_id=thread_id)
    return payload


# ── the conversation corpus ─────────────────────────────────────────────────


def store_answer(
    repo: Any, payload: dict[str, Any], context: dict[str, Any], *, thread_id: str = ""
) -> str:
    """Retain one answer, its citations and its provenance, and project it into
    the corpus as a ``derived`` source.

    A stored answer is never a fact. It is one analyst's notes pinned to the
    revisions it read, and it says so wherever it is returned.
    """
    from pathlib import Path

    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.temporal import now_iso

    asked_at = now_iso()
    answer_id = (
        "answer-"
        + hashlib.sha256(
            f"{payload['question']}|{payload['answer']}|{asked_at}".encode()
        ).hexdigest()[:20]
    )
    latency = payload.get("latency", {})
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO conversation_answers(answer_id, thread_id, asked_at, question,
                   answer, model, subject_ref, elapsed_s, eval_count, prompt_bytes,
                   load_duration_s, reasoning_effort, num_ctx, org_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'default')
               ON CONFLICT(answer_id) DO NOTHING""",
            (
                answer_id,
                thread_id,
                asked_at,
                payload["question"],
                payload["answer"],
                payload.get("model", ""),
                payload.get("ref", ""),
                float(latency.get("elapsed_s") or 0),
                int(latency.get("eval_count") or 0),
                int(latency.get("prompt_bytes") or 0),
                float(latency.get("load_duration_s") or 0),
                str(payload.get("reasoning_effort", "")),
                int(payload.get("num_ctx") or 0),
            ),
        )
        repo._conn.executemany(
            """INSERT INTO answer_citations(answer_id, cited_ref, resolved, resolves_to,
                   revision_id, jurisdiction, source_kind, detail)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(answer_id, cited_ref) DO NOTHING""",
            [
                (
                    answer_id,
                    entry["cited_ref"],
                    1 if entry["resolved"] else 0,
                    entry.get("resolves_to", ""),
                    entry.get("revision_id", ""),
                    entry.get("jurisdiction", ""),
                    entry.get("source_kind", ""),
                    entry.get("detail", ""),
                )
                for entry in payload["verification"]["citations"]
            ],
        )

    logical_id = f"answer/{answer_id}"
    body = (
        f"Q: {payload['question']}\n\n{payload['answer']}\n\n"
        f"[stored answer about {payload.get('ref', '')}, read from revision "
        f"{context.get('revision_id', '')} by {payload.get('model', '')} on {asked_at[:10]}. "
        f"One analyst's notes pinned to the revisions it read — not a fact, and outranked "
        f"by any operator note on the same subject.]\n"
    )
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=payload["question"][:120],
            issuer=payload.get("model", ""),
            source_kind="derived_answer",
            jurisdiction="derived",
        )
    )
    revision = repo.add_document_revision(
        logical_id, logical_id, body.encode(), binding_effect="descriptive"
    )
    store_capture(
        repo,
        revision.revision_id,
        CapturedDocument(
            path=Path(logical_id),
            page_count=1,
            full_text=body,
            units=[
                CapturedUnit(
                    ordinal=0,
                    unit_kind="prose",
                    heading_path=f"stored answer about {payload.get('ref', '')}",
                    title=payload["question"][:120],
                    page_start=1,
                    page_end=1,
                    char_start=0,
                    char_end=len(body),
                    text=body,
                )
            ],
            extractor="conversation",
            extractor_version="1",
            reader_strings=(payload["answer"],),
        ),
    )
    return answer_id


def supersede_answers_for_revisions(repo: Any, revision_ids: list[str]) -> list[str]:
    """Mark stored answers superseded when a revision they cited moves.

    An answer is pinned to what it read. When that text is replaced, the answer
    is not wrong — it is about a document that no longer governs, which is a
    different thing and must be visible as one.
    """
    from portal.modules.compliance.core.temporal import now_iso

    if not revision_ids:
        return []
    marks = ",".join("?" for _ in revision_ids)
    rows = repo._conn.execute(
        f"""SELECT DISTINCT a.answer_id FROM conversation_answers a
            JOIN answer_citations c ON c.answer_id = a.answer_id
            WHERE c.revision_id IN ({marks}) AND a.superseded_at IS NULL""",  # noqa: S608
        tuple(revision_ids),
    ).fetchall()
    ids = [str(r[0]) for r in rows]
    if ids:
        stamp = now_iso()
        with repo._lock, repo._conn:
            repo._conn.executemany(
                "UPDATE conversation_answers SET superseded_at = ? WHERE answer_id = ?",
                [(stamp, answer_id) for answer_id in ids],
            )
    return ids


def record_correction(
    repo: Any, answer_id: str, correction: str, author: str = ""
) -> dict[str, Any]:
    """An operator's correction of a stored answer. Recorded as a NOTE about the
    answer — the operator's word outranks the reading, and both remain."""
    from portal.modules.compliance.core.notes import write_note

    note = write_note(
        repo,
        subject_ref=answer_id,
        body=correction,
        kind="correction",
        author=author,
    )
    with repo._lock, repo._conn:
        repo._conn.execute(
            "UPDATE conversation_answers SET correction_of = ? WHERE answer_id = ?",
            (note["note_id"], answer_id),
        )
    return note


def answers_for(
    repo: Any, subject_ref: str = "", *, include_superseded: bool = True
) -> list[dict[str, Any]]:
    """Stored answers about a subject, newest first, each with its citations and
    its standing relative to any operator note on the same subject."""
    clause = "WHERE subject_ref = ?" if subject_ref else ""
    params: tuple[Any, ...] = (subject_ref,) if subject_ref else ()
    if not include_superseded:
        clause += (" AND " if clause else "WHERE ") + "superseded_at IS NULL"
    rows = repo._conn.execute(
        f"SELECT * FROM conversation_answers {clause} ORDER BY asked_at DESC LIMIT 200",  # noqa: S608
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    notes = {
        str(r[0])
        for r in repo._conn.execute(
            "SELECT subject_ref FROM operator_notes WHERE subject_ref = ?", (subject_ref,)
        ).fetchall()
    }
    for row in rows:
        entry = dict(row)
        entry["citations"] = [
            dict(c)
            for c in repo._conn.execute(
                "SELECT * FROM answer_citations WHERE answer_id = ?", (entry["answer_id"],)
            ).fetchall()
        ]
        entry["standing"] = (
            "one analyst's notes pinned to the revisions it read — "
            + ("SUPERSEDED: a revision it cited has moved" if entry["superseded_at"] else "current")
            + ("; an operator note on this subject outranks it" if notes else "")
        )
        out.append(entry)
    return out


# ── standing questions ──────────────────────────────────────────────────────


def add_standing_question(repo: Any, question: str, subject_ref: str = "") -> str:
    """A question the operator already cares about. Run on ingest and on every
    auto-sync change — that IS the initial assessment, rather than a schema
    filled in by a machine nobody asked."""
    from portal.modules.compliance.core.temporal import now_iso

    question_id = "sq-" + hashlib.sha256(f"{question}|{subject_ref}".encode()).hexdigest()[:16]
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO standing_questions(question_id, question, subject_ref, created_at,
                   active, org_id) VALUES (?,?,?,?,1,'default')
               ON CONFLICT(question_id) DO UPDATE SET active = 1""",
            (question_id, question, subject_ref, now_iso()),
        )
    return question_id


def standing_questions(repo: Any, subject_ref: str = "") -> list[dict[str, Any]]:
    clause = "WHERE active = 1"
    params: tuple[Any, ...] = ()
    if subject_ref:
        clause += " AND (subject_ref = ? OR subject_ref = '')"
        params = (subject_ref,)
    rows = repo._conn.execute(
        f"SELECT * FROM standing_questions {clause} ORDER BY created_at",  # noqa: S608
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def run_standing_questions(
    repo: Any, subject_ref: str, *, model: str, thread_id: str = "", **kwargs: Any
) -> list[dict[str, Any]]:
    """Run every standing question against one subject and keep the answers."""
    out: list[dict[str, Any]] = []
    for entry in standing_questions(repo, subject_ref):
        out.append(
            read(
                repo,
                str(entry["question"]),
                subject_ref,
                model=model,
                thread_id=thread_id or f"standing:{subject_ref}",
                **kwargs,
            )
        )
    return out


def as_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)
