"""Candidate links between requirements and operator sections (BILATERAL_CORPUS_V1 P7).

Deterministic and **generative-model-free**. A link proposed here is the output
of retrieval plus a cross-encoder rerank over the projected section population,
recorded as a ``relationship_assertions`` row with ``status='proposed'``,
``derivation='projection_rerank'`` and its score. It is a candidate, and it says
so everywhere it appears.

**Absence is recorded, not inferred.** A requirement whose best candidate falls
below the calibrated threshold gets an explicit "no candidate" row plus the
boundary receipt for the population searched. Because that population is the
whole projected corpus — every section, not a top-k window — the claim is
defensible in a way "we searched and found nothing" never was.

The other producer is the conversation: when a reading says *this section is what
implements that*, with citations, that becomes a separate proposed edge with
``derivation='reading'`` carrying the answer it came from. Proposed, labelled,
contestable — the model's reading is evidence for a link, never the link itself.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any

DERIVATION_RERANK = "projection_rerank"
DERIVATION_READING = "reading"

#: Rerank score below which a candidate is not proposed. Calibrated in P7.4
#: against a hand-checked set on CIP-007-6 R2 — see the report. Never assume
#: this number; re-calibrate when the embedder or the reranker changes.
DEFAULT_THRESHOLD = 0.5

#: How many candidates to rerank per requirement. Wider than the number kept:
#: the dense arm's ordering is not the rerank's ordering, and a candidate the
#: dense arm ranked twelfth is exactly the one a narrow window loses.
RERANK_POOL = 40


@dataclass
class Candidate:
    section_id: str
    score: float
    text: str
    headings: str
    document: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "score": round(self.score, 4),
            "headings": self.headings,
            "document": self.document,
            "excerpt": self.text[:240],
        }


@dataclass
class RequirementLinks:
    ref: str
    query: str
    proposed: list[Candidate] = field(default_factory=list)
    rejected: list[Candidate] = field(default_factory=list)
    threshold: float = DEFAULT_THRESHOLD

    @property
    def has_link(self) -> bool:
        return bool(self.proposed)


def requirement_queries(repo: Any, standard: str) -> dict[str, str]:
    """``requirement ref -> the duty's own words``, from the captured sections.

    The query is the standard's own text, never a paraphrase and never a
    hand-written search string: a query nobody can trace to the requirement is
    a query nobody can audit.
    """
    from portal.modules.compliance.core.reading_assembly import assemble, parse_ref

    parsed = parse_ref(standard)
    if parsed is None:
        return {}
    rows = repo._conn.execute(
        """SELECT s.section_id FROM source_sections s
           JOIN document_revisions r ON r.revision_id = s.revision_id
           WHERE r.logical_id = ? AND s.unit_kind = 'table_row' AND s.char_start >= 0
           ORDER BY s.ordinal""",
        (parsed.logical_id,),
    ).fetchall()
    out: dict[str, str] = {}
    for row in rows:
        cells = repo.table_cells(str(row[0]))
        by_column = {str(c["column_name"]): str(c["text"]) for c in cells}
        part = by_column.get("Part", "").strip()
        duty = by_column.get("Requirements", "").strip()
        if not part or not duty or "." not in part:
            continue
        requirement = part.split(".", 1)[0]
        out[f"{parsed.standard} R{requirement} Part {part}"] = duty
    if out:
        return out
    # a prose standard: fall back to the requirement lead-ins the capture holds
    assembly = assemble(repo, standard, include=["requirement"])
    for component in assembly.get("components", []):
        for section in component.get("sections", []):
            text = str(section.get("text", "")).strip()
            if text.startswith("R"):
                ref = f"{parsed.standard} {text.split('.', 1)[0]}"
                out.setdefault(ref, text)
    return out


async def _rank(query: str, kb_id: str, pool: int) -> list[tuple[str, float, str, str, str]]:
    """``(section_id, score, text, headings, document)`` best first.

    The dense arm and the BM25 sparse arm both feed the pool, and the
    cross-encoder reranks it — the same stages the search surface uses, so a
    proposed link and a search hit agree about what is relevant.
    """
    from portal.modules.compliance.core.section_index import parent_section_id
    from portal.modules.compliance.tools.compliance_retrieval import search as _search

    body = await _search(kb_id, query, pool)
    out: list[tuple[str, float, str, str, str]] = []
    seen: set[str] = set()
    for hit in body.get("results", []):
        section_id = parent_section_id(str(hit.get("chunk_id", "")))
        if not section_id or section_id in seen:
            continue
        seen.add(section_id)
        out.append(
            (
                section_id,
                float(hit.get("rerank_score") or hit.get("fused_score") or 0.0),
                str(hit.get("text", "")),
                str(hit.get("headings", "")),
                str(hit.get("source_file", "")),
            )
        )
    return out


def build_links(
    repo: Any,
    standard: str,
    *,
    kb_id: str = "operator_corpus",
    threshold: float = DEFAULT_THRESHOLD,
    pool: int = RERANK_POOL,
    keep: int = 5,
) -> list[RequirementLinks]:
    """Candidate edges for every requirement Part of one standard."""
    out: list[RequirementLinks] = []
    for ref, query in requirement_queries(repo, standard).items():
        ranked = asyncio.run(_rank(query, kb_id, pool))
        links = RequirementLinks(ref=ref, query=query, threshold=threshold)
        for section_id, score, text, headings, document in ranked:
            candidate = Candidate(section_id, score, text, headings, document)
            if score >= threshold and len(links.proposed) < keep:
                links.proposed.append(candidate)
            else:
                links.rejected.append(candidate)
        out.append(links)
    return out


def record_links(
    repo: Any,
    links: list[RequirementLinks],
    *,
    boundary_receipt: dict[str, Any] | None = None,
    org_id: str = "default",
) -> dict[str, Any]:
    """Persist proposed edges, and record absence where there is none.

    A prior ``projection_rerank`` proposal for the same requirement is replaced,
    so a re-run after a re-projection never leaves stale candidates beside fresh
    ones. Edges from any other derivation — an approved mapping, a reading's
    assertion — are untouched.
    """
    from portal.modules.compliance.core.temporal import now_iso

    recorded, absent = 0, []
    stamp = now_iso()
    receipt_id = ""
    if boundary_receipt:
        receipt_id = (
            "boundary-"
            + hashlib.sha256(
                repr(sorted(boundary_receipt.get("eligible_sections", []))).encode()
            ).hexdigest()[:20]
        )
    with repo._lock, repo._conn:
        for entry in links:
            repo._conn.execute(
                "DELETE FROM relationship_assertions WHERE src_ref = ? AND derivation = ?",
                (entry.ref, DERIVATION_RERANK),
            )
            for candidate in entry.proposed:
                assertion_id = (
                    "rel-"
                    + hashlib.sha256(
                        f"{entry.ref}|{candidate.section_id}|{DERIVATION_RERANK}".encode()
                    ).hexdigest()[:20]
                )
                repo._conn.execute(
                    """INSERT INTO relationship_assertions(assertion_id, relation_type,
                           src_ref, src_revision_id, dst_ref, dst_revision_id, scope,
                           citations, status, review_state, recorded_from, rationale,
                           confidence, derivation, org_id, version)
                       VALUES (?,?,?,NULL,?,NULL,'',?,'proposed','proposed',?,?,?,?,?,1)
                       ON CONFLICT(assertion_id) DO UPDATE SET
                           confidence = excluded.confidence,
                           rationale = excluded.rationale""",
                    (
                        assertion_id,
                        "IMPLEMENTS",
                        entry.ref,
                        candidate.section_id,
                        "[]",
                        stamp,
                        (
                            f"retrieval + cross-encoder rerank over the projected section "
                            f"population, score {candidate.score:.4f} "
                            f"(threshold {entry.threshold})"
                        ),
                        candidate.score,
                        DERIVATION_RERANK,
                        org_id,
                    ),
                )
                recorded += 1
            if not entry.proposed:
                best = max((c.score for c in entry.rejected), default=0.0)
                absent.append(
                    {
                        "ref": entry.ref,
                        "best_score": round(best, 4),
                        "threshold": entry.threshold,
                        "population_searched": len(
                            (boundary_receipt or {}).get("examined_sections", [])
                        ),
                        "boundary_proof_id": receipt_id,
                        "claim": (
                            "no operator section in the searched population scores above the "
                            "calibrated threshold for this requirement"
                        ),
                    }
                )
    return {
        "edges_recorded": recorded,
        "requirements": len(links),
        "requirements_with_no_candidate": absent,
        "derivation": DERIVATION_RERANK,
        "boundary_proof_id": receipt_id,
    }


def record_reading_link(
    repo: Any,
    *,
    src_ref: str,
    dst_section_id: str,
    answer_id: str,
    rationale: str = "",
    org_id: str = "default",
) -> str:
    """A link a reading asserted, recorded as its own kind of proposal.

    The model reading both sides and saying *this section is what implements
    that* is evidence for a link. It is recorded as ``derivation='reading'``
    carrying the answer it came from, so an analyst can follow it back to the
    argument and disagree with it.
    """
    from portal.modules.compliance.core.temporal import now_iso

    assertion_id = (
        "rel-"
        + hashlib.sha256(
            f"{src_ref}|{dst_section_id}|{DERIVATION_READING}|{answer_id}".encode()
        ).hexdigest()[:20]
    )
    with repo._lock, repo._conn:
        repo._conn.execute(
            """INSERT INTO relationship_assertions(assertion_id, relation_type, src_ref,
                   src_revision_id, dst_ref, dst_revision_id, scope, citations, status,
                   review_state, recorded_from, rationale, confidence, derivation, org_id,
                   version)
               VALUES (?,?,?,NULL,?,NULL,'',?,'proposed','proposed',?,?,0.0,?,?,1)
               ON CONFLICT(assertion_id) DO NOTHING""",
            (
                assertion_id,
                "IMPLEMENTS",
                src_ref,
                dst_section_id,
                f'[{{"answer_id": "{answer_id}"}}]',
                now_iso(),
                rationale or f"asserted while reading, in answer {answer_id}",
                DERIVATION_READING,
                org_id,
            ),
        )
    return assertion_id


def links_from_answer(repo: Any, answer_id: str, src_ref: str = "") -> list[str]:
    """Every operator section a stored answer cited becomes a reading-derived
    proposal for the requirement the answer was about.

    Only the OPERATOR side: the answer citing the standard it was asked about is
    not a claim that the standard implements itself.
    """
    row = repo._conn.execute(
        "SELECT subject_ref FROM conversation_answers WHERE answer_id = ?", (answer_id,)
    ).fetchone()
    if row is None:
        return []
    subject = src_ref or str(row[0])
    citations = repo._conn.execute(
        """SELECT cited_ref, jurisdiction FROM answer_citations
           WHERE answer_id = ? AND resolved = 1 AND jurisdiction = 'internal'""",
        (answer_id,),
    ).fetchall()
    return [
        record_reading_link(repo, src_ref=subject, dst_section_id=str(c[0]), answer_id=answer_id)
        for c in citations
    ]
