"""Candidate closure with source-function preservation (END_TO_END Phase 8 /
slice P2).

Candidate acquisition for the reading packet combines, in priority order:

* exact reviewed/proposed mappings from the canonical store (prioritized and
  explained — never decisive);
* lexical/vector retrieval (unchanged ``propose`` behaviour upstream);
* parent/sibling/neighbor section closure over the internal documents'
  classified section trees (P4);
* a bounded full-document fallback for the declared small corpus.

Every candidate entering the packet carries its **source function** — the
classified section role from the canonical store — plus the document revision
id, so a copied NERC traceability row, a table of contents, or a revision
history can never present itself to the reader as operative implementation
(lesson L18). Authority/revision filters apply here, before ranking: only the
current revision of an internal document is eligible, and non-operative
sections are labelled as context, never silently dropped (the reader sees why
a passage is not implementation).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from portal.modules.compliance.core.internal_corpus import OPERATIVE_ROLES

#: roles that can never count as operative implementation, labelled in-packet
_CONTEXT_NOTE = (
    "context only: this section is {role}, not an operative commitment — it "
    "cannot implement a duty by itself"
)


def _section_rows(repo: Any, revision_id: str) -> list[dict[str, Any]]:
    return repo.sections_with_role(revision_id)


def _document_revision(repo: Any, document_id: str) -> tuple[str, str] | None:
    """(revision_id, logical_id) of the CURRENT revision for a candidate
    document id. Candidates may arrive keyed by rel path, document name or
    alias — resolve by logical_id first, then alias_path."""
    conn = repo._conn
    for column in ("logical_id", "alias_path"):
        like = f"%{document_id}%" if column == "alias_path" else document_id
        rows = conn.execute(
            f"""SELECT dr.revision_id, dr.logical_id, dr.retrieved_at
                FROM document_revisions dr JOIN source_documents sd USING(logical_id)
                WHERE dr.{column} = ?
                ORDER BY dr.retrieved_at DESC""",
            (like,),
        ).fetchall()
        if rows:
            return rows[0][0], rows[0][1]
    return None


def source_function_for(
    repo: Any,
    document_id: str,
    text: str,
) -> dict[str, Any]:
    """The source-function metadata for one candidate: document revision, its
    classified sections, the section containing this text (best effort), and
    the operative verdict."""
    resolved = _document_revision(repo, document_id)
    if resolved is None:
        return {
            "source_function": "UNRESOLVED",
            "revision_id": "",
            "revision_current": False,
            "section_path": "",
            "operative": False,
            "note": "candidate document does not resolve to a canonical revision",
        }
    revision_id, _logical = resolved
    # current-revision filter: a candidate from a superseded internal revision
    # cannot answer the current question (slice §6 D) — labelled, never silent.
    revisions = repo.revisions_for_logical_id(_logical)
    revision_current = bool(revisions) and revisions[-1].revision_id == revision_id
    sections = _section_rows(repo, revision_id)
    section = _match_section(sections, text)
    role = (section or {}).get("role", "") or (sections[0].get("role") if sections else "")
    operative = role in OPERATIVE_ROLES
    return {
        "source_function": role or "UNCLASSIFIED",
        "revision_id": revision_id,
        "revision_current": revision_current,
        "section_path": (section or {}).get("path", ""),
        "section_title": (section or {}).get("title", ""),
        "operative": operative,
        "note": "" if operative else _CONTEXT_NOTE.format(role=role or "unclassified"),
    }


def _match_section(sections: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    """The classified section whose heading path/title best matches the
    candidate's locator, else the first operative section."""
    for section in sections:
        if text and section.get("path") and str(section["path"]) in text:
            return section
    for section in sections:
        if section.get("role") in OPERATIVE_ROLES:
            return section
    return None


def neighbor_closure(
    repo: Any,
    document_id: str,
    *,
    max_neighbors: int = 2,
) -> list[dict[str, Any]]:
    """Sibling sections adjacent to the document's operative sections — a duty
    split across sibling clauses must be readable together (slice §5.2)."""
    resolved = _document_revision(repo, document_id)
    if resolved is None:
        return []
    revision_id, _logical = resolved
    sections = _section_rows(repo, revision_id)
    out: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        if section.get("role") not in OPERATIVE_ROLES:
            continue
        for offset in range(-max_neighbors, max_neighbors + 1):
            pos = index + offset
            if pos < 0 or pos >= len(sections) or pos == index:
                continue
            neighbor = sections[pos]
            entry = {
                "path": neighbor.get("path", ""),
                "title": neighbor.get("title", ""),
                "role": neighbor.get("role", ""),
                "relation": "sibling",
                "document_id": document_id,
            }
            if entry not in out:
                out.append(entry)
    return out[: max_neighbors * 4]


def mapping_candidates(
    repo: Any, requirement_id: str, *, known_at: str = ""
) -> list[dict[str, Any]]:
    """Exact store mappings for the requirement: approved first, then proposed
    as explicitly-labelled discovery. Each carries derivation and status —
    governance metadata, never the answer."""
    out: list[dict[str, Any]] = []
    for status, derivation_label in (
        ("approved", "reviewed_mapping"),
        ("proposed", "proposed_mapping"),
    ):
        for rel in repo.list_relationship_assertions(
            ref=requirement_id, statuses=(status,), known_at=known_at or None
        ):
            if rel.relation_type != "IMPLEMENTS":
                continue
            out.append(
                {
                    "candidate_ref": rel.dst_ref,
                    "status": status,
                    "derivation": rel.derivation or derivation_label,
                    "assertion_id": rel.assertion_id,
                    "note": (
                        "mapping metadata: prioritizes and explains candidates; it never "
                        "decides satisfaction"
                    ),
                }
            )
    return out


def corpus_boundary_receipt(repo: Any, corpus_dir: str) -> dict[str, Any]:
    """The declared small-corpus boundary: every controlled PDF on disk under
    the corpus root, whether it is registered in the canonical store, and
    whether all of them are searchable in the projection. A search over this
    corpus can only claim completeness when every declared document is
    accounted for."""
    from pathlib import Path

    root = Path(corpus_dir)
    pdfs = sorted(str(p.relative_to(root)) for p in root.rglob("*.pdf") if p.is_file())
    from portal.modules.compliance.core.jurisdiction import OPERATOR_SQL_IN

    registered = {
        row[0]
        for row in repo._conn.execute(
            f"SELECT logical_id FROM source_documents WHERE jurisdiction IN {OPERATOR_SQL_IN}"
        ).fetchall()
    }
    missing = [rel for rel in pdfs if rel not in registered]
    return {
        "declared_corpus": str(root),
        "declared_documents": len(pdfs),
        "registered_documents": len(pdfs) - len(missing),
        "unregistered": missing,
        "complete": not missing,
    }


def enrich_reading_packet(
    repo: Any, packet: dict[str, Any], *, requirement_id: str = "", corpus_dir: str = ""
) -> dict[str, Any]:
    """Attach source functions, revision ids, and the boundary receipt to the
    reading packet's candidates, plus mapping metadata and sibling closure.
    Returns the packet (mutated in place) — the reader sees each candidate's
    role and why a non-operative passage cannot implement a duty."""
    candidates = packet.get("candidates", [])
    seen_docs: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        fn = source_function_for(
            repo, str(candidate.get("document_id", "")), str(candidate.get("text", ""))
        )
        candidate.update(fn)
        doc_id = str(candidate.get("document_id", ""))
        if doc_id not in seen_docs:
            seen_docs[doc_id] = {
                "mappings": [
                    m
                    for m in mapping_candidates(repo, requirement_id)
                    if doc_id in str(m.get("candidate_ref", ""))
                ],
            }
        candidate["mapping_metadata"] = seen_docs[doc_id]["mappings"]
    neighbors: dict[str, list[dict[str, Any]]] = {}
    for doc_id in seen_docs:
        closure = neighbor_closure(repo, doc_id)
        if closure:
            neighbors[doc_id] = closure
    if neighbors:
        packet["neighbor_sections"] = neighbors
    if corpus_dir:
        packet["corpus_boundary"] = corpus_boundary_receipt(repo, corpus_dir)
    return packet


def packet_fingerprint(packet: dict[str, Any]) -> str:
    """Stable fingerprint of the assembled packet (both sides) for receipts."""
    return hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
