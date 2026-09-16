"""Operator notes as first-class sources (BILATERAL_CORPUS_V1 P5).

An operator's decision, intent or rationale — *"we chose 30 days rather than 35
because our change window is monthly"* — is not metadata about the corpus. It is
part of it, and it is the part an auditor asks for first. So a note is stored
the way every other source is stored: a ``source_documents`` row, an immutable
``document_revisions`` row keyed on the note's own bytes, and a
``source_sections`` row with a span into a captured coordinate space.

Consequences that fall out of that choice rather than being built separately:

* a note is **citeable** by ``section_id``, like a requirement Part or an
  operator procedure section;
* a note is **resolvable** through ``section_index.resolve_sections``, so a
  reader that cites one gets back verbatim text with provenance;
* a note is **projectable** into the retrieval index by the same path as
  everything else, so it is findable by search from the next question onward;
* a note is **immutable and dated**. A changed mind is a new note, and both
  remain.

A note always outranks a stored answer: an answer is one reader's notes pinned
to the revisions it read, while a note is the operator telling you what they
decided.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

NOTE_JURISDICTION = "operator_note"
NOTE_SOURCE_KIND = "operator_note"
EXTRACTOR = "operator_note"
EXTRACTOR_VERSION = "1"

#: the corpus operator notes project into — beside the two document corpora,
#: under the same table prefix, so ``search_all`` spans all three.
NOTE_CORPUS = "operator_notes"

#: what a note is. Free text, not a controlled vocabulary: the kinds people
#: actually write are not knowable in advance, and forcing one is the
#: prescriptive move this whole task exists to stop.
DEFAULT_KIND = "note"


def _note_id(subject_ref: str, body: str, created_at: str) -> str:
    return "note-" + hashlib.sha256(f"{subject_ref}|{body}|{created_at}".encode()).hexdigest()[:20]


def write_note(
    repo: Any,
    *,
    subject_ref: str,
    body: str,
    kind: str = DEFAULT_KIND,
    author: str = "",
    org_id: str = "default",
) -> dict[str, Any]:
    """Record one note. Immutable: the same subject, body and second produce the
    same id and the same revision, so a double submit is a no-op rather than a
    duplicate."""
    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.temporal import now_iso

    body = body.strip()
    if not body:
        raise ValueError("a note needs a body")
    if not subject_ref.strip():
        raise ValueError("a note needs a subject_ref — what it is about")

    created_at = now_iso()
    note_id = _note_id(subject_ref, body, created_at)
    logical_id = f"note/{note_id}"
    heading = f"{kind} on {subject_ref}"
    text = f"{heading}\n{body}\n"

    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=heading,
            issuer=author or "operator",
            source_kind=NOTE_SOURCE_KIND,
            jurisdiction=NOTE_JURISDICTION,
            org_id=org_id,
        )
    )
    revision = repo.add_document_revision(
        logical_id,
        logical_id,
        text.encode(),
        binding_effect="internally_mandatory",
        authored_date=created_at[:10],
        owner=author,
    )
    captured = CapturedDocument(
        path=Path(logical_id),
        page_count=1,
        full_text=text,
        units=[
            CapturedUnit(
                ordinal=0,
                unit_kind="prose",
                heading_path=heading,
                title=kind,
                page_start=1,
                page_end=1,
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
        extractor=EXTRACTOR,
        extractor_version=EXTRACTOR_VERSION,
        reader_strings=(body,),
    )
    store_capture(repo, revision.revision_id, captured, org_id=org_id)
    section_id = repo._conn.execute(
        "SELECT section_id FROM source_sections WHERE revision_id = ? AND extractor = ?",
        (revision.revision_id, EXTRACTOR),
    ).fetchone()[0]

    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO operator_notes(note_id, subject_ref, kind, author, created_at,
                   section_id, revision_id, org_id)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(note_id) DO NOTHING""",
            (
                note_id,
                subject_ref.strip(),
                kind,
                author,
                created_at,
                section_id,
                revision.revision_id,
                org_id,
            ),
        )
    return {
        "note_id": note_id,
        "subject_ref": subject_ref.strip(),
        "kind": kind,
        "author": author,
        "created_at": created_at,
        "section_id": str(section_id),
        "revision_id": revision.revision_id,
        "text": text,
    }


def notes_for(repo: Any, subject_ref: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
    """Notes about one subject (or every note), newest first, with their text."""
    from portal.modules.compliance.core.section_index import resolve_sections

    if subject_ref:
        rows = repo._conn.execute(
            """SELECT * FROM operator_notes WHERE subject_ref = ?
               ORDER BY created_at DESC LIMIT ?""",
            (subject_ref.strip(), limit),
        ).fetchall()
    else:
        rows = repo._conn.execute(
            "SELECT * FROM operator_notes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    entries = [dict(r) for r in rows]
    resolved = resolve_sections(repo, [str(e["section_id"]) for e in entries])
    for entry in entries:
        section = resolved.get(str(entry["section_id"]), {})
        entry["text"] = section.get("text", "")
        entry["outranks"] = "a stored answer — a note is the operator's own decision"
    return entries
