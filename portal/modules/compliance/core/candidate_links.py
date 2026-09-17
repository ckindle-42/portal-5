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
import json
import re
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

    The dense arm and the BM25 sparse arm build the pool; the **cross-encoder
    scores it**. The rerank pass is explicit here rather than taken from the
    search response because the compliance composition runs the shared
    ``text_gate`` fusion, which reranks only page images and leaves every text
    chunk at ``reranker_prob: None``. Its ``fused_score`` is a reciprocal-rank
    constant — measured live, every candidate for every CIP-007-6 Part came back
    at 0.0167, 0.0164, 0.0161 … in rank order, identical across requirements.

    That matters because P7 records ABSENCE below a threshold. A threshold on a
    rank constant says "not in the top N", which is true of most of any corpus
    and calibrates to nothing. A threshold on a cross-encoder probability is a
    statement about this requirement and this section.
    """
    from portal.modules.compliance.core.section_index import parent_section_id
    from portal.modules.compliance.tools.compliance_retrieval import search as _search
    from portal.platform.retrieval import embedding as _embedding

    body = await _search(kb_id, query, pool)
    candidates: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for hit in body.get("results", []):
        section_id = parent_section_id(str(hit.get("chunk_id", "")))
        text = str(hit.get("text", ""))
        if not section_id or section_id in seen or not text.strip():
            continue
        seen.add(section_id)
        candidates.append(
            (section_id, text, str(hit.get("headings", "")), str(hit.get("source_file", "")))
        )
    if not candidates:
        return []
    order = await _embedding.vl_rerank(query, [{"text": c[1]} for c in candidates], len(candidates))
    return [
        (
            candidates[int(entry["index"])][0],
            float(entry["score"]),
            candidates[int(entry["index"])][1],
            candidates[int(entry["index"])][2],
            candidates[int(entry["index"])][3],
        )
        for entry in order
    ]


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
                           citations_json, status, review_state, recorded_from, rationale,
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


#: Relations a reading may propose. A reading never proposes anything else, and
#: never proposes without naming which of these it means.
READING_RELATIONS = ("IMPLEMENTS", "EVIDENCES")

#: A sentence positively asserting that the operator's section implements the
#: duty. Required — a citation on its own asserts nothing.
_ASSERTS_IMPLEMENTS = re.compile(
    r"\b(?:implement(?:s|ed|ing)?|satisf(?:ies|y|ied)|meets?|fulfil(?:s|ls|led)?|"
    r"address(?:es|ed)?|covers?|complies\s+with|discharg(?:es|ed))\b",
    re.I,
)

#: A sentence offering the section as EVIDENCE of the duty rather than as the
#: control itself. A different relation, and the store already has a name for it.
_ASSERTS_EVIDENCES = re.compile(
    r"\b(?:evidence(?:s|d)?|demonstrat(?:es|ed|ing)|records?|logs?|attests?)\b", re.I
)

#: Anything that makes the sentence something OTHER than a positive assertion:
#: a negation, a shortfall, a contradiction, a contrast, or a bare mention. When
#: one of these is present the link is withheld with the reason, and the
#: citation stays what it already was — evidence, in ``answer_citations``.
_WITHHOLDS = re.compile(
    r"\b(?:not|no|never|without|fails?|failed|lacks?|absent|missing|silent|"
    r"conflicts?|contradicts?|inconsistent|diverges?|unlike|whereas|however|"
    r"but|although|though|stricter|shorter|longer|exceeds?|unclear|cannot|"
    r"does\s+not|would\s+need|insufficient)\b",
    re.I,
)


def classify_assertion(sentence: str) -> tuple[str, str]:
    """What a citing sentence actually ASSERTS about the section it cites.

    Every resolved internal citation used to become an ``IMPLEMENTS`` proposal.
    That reads a citation as a claim, and a reading cites for many reasons: to
    show a shortfall, to name a contradiction, to quote the very section that
    does NOT satisfy the duty. Those proposals then travel into the review queue
    and, once approved, into the labelled evaluation set — so counterevidence
    ends up recorded as the implementation of the thing it contradicts.

    Returns ``(relation, reason)``; an empty relation means withheld, and the
    reason says why. Conservative by construction: a sentence must positively
    assert, and must carry no withholding marker, to yield an edge at all.
    """
    text = str(sentence or "")
    if not text.strip():
        return "", "no sentence around the citation to read an assertion from"
    if _WITHHOLDS.search(text):
        return "", "the citing sentence negates, contrasts or qualifies — not an assertion"
    if _ASSERTS_IMPLEMENTS.search(text):
        return "IMPLEMENTS", "the citing sentence asserts implementation"
    if _ASSERTS_EVIDENCES.search(text):
        return "EVIDENCES", "the citing sentence offers the section as evidence"
    return "", "the citing sentence discusses the section without asserting a relation"


def record_reading_link(
    repo: Any,
    *,
    src_ref: str,
    dst_section_id: str,
    answer_id: str,
    relation: str,
    rationale: str = "",
    org_id: str = "default",
) -> str:
    """A link a reading asserted, recorded as its own kind of proposal.

    ``relation`` is explicit and required: the caller says which of
    :data:`READING_RELATIONS` it means, because the reading is what carries that
    information and a citation does not.

    Recorded as ``derivation='reading'`` carrying the answer it came from, so an
    analyst can follow it back to the argument and disagree with it.
    """
    from portal.modules.compliance.core.temporal import now_iso

    if relation not in READING_RELATIONS:
        raise ValueError(f"relation must be one of {READING_RELATIONS}, not {relation!r}")
    assertion_id = (
        "rel-" + hashlib.sha256(f"{src_ref}|{dst_section_id}|{relation}".encode()).hexdigest()[:20]
    )
    detail = rationale or f"asserted while reading, in answer {answer_id}"
    with repo._lock, repo._conn:
        existing = repo._conn.execute(
            """SELECT assertion_id, derivation, rationale, citations_json
               FROM relationship_assertions
               WHERE relation_type = ? AND src_ref = ? AND dst_ref = ?
                 AND status = 'proposed'""",
            (relation, src_ref, dst_section_id),
        ).fetchone()
        if existing is not None:
            current = [part for part in str(existing[1] or "").split("|") if part]
            if DERIVATION_READING not in current:
                current.append(DERIVATION_READING)
            citations = json.loads(existing[3] or "[]")
            citations.append({"answer_id": answer_id, "section_id": dst_section_id})
            repo._conn.execute(
                """UPDATE relationship_assertions
                   SET derivation = ?, rationale = ?, citations_json = ?
                   WHERE assertion_id = ?""",
                (
                    "|".join(dict.fromkeys(current)),
                    f"{existing[2] or ''}\n{detail}".strip(),
                    json.dumps(citations),
                    existing[0],
                ),
            )
            return str(existing[0])
        repo._conn.execute(
            """INSERT INTO relationship_assertions(assertion_id, relation_type, src_ref,
                   src_revision_id, dst_ref, dst_revision_id, scope, citations_json, status,
                   review_state, recorded_from, rationale, confidence, derivation, org_id,
                   version)
               VALUES (?,?,?,NULL,?,NULL,'',?,'proposed','proposed',?,?,0.0,?,?,1)
               ON CONFLICT(assertion_id) DO NOTHING""",
            (
                assertion_id,
                relation,
                src_ref,
                dst_section_id,
                json.dumps([{"answer_id": answer_id, "section_id": dst_section_id}]),
                now_iso(),
                detail,
                DERIVATION_READING,
                org_id,
            ),
        )
    return assertion_id


def links_from_answer(repo: Any, answer_id: str, src_ref: str = "") -> dict[str, Any]:
    """The links a stored answer ASSERTED, and the citations it did not.

    Every resolved internal citation used to become an ``IMPLEMENTS`` proposal.
    A reading cites for many reasons — to show a shortfall, to name a
    contradiction, to quote the section that does NOT satisfy the duty — and
    those proposals travel into the review queue and, once approved, into the
    labelled evaluation set, so counterevidence was being recorded as the
    implementation of the thing it contradicts.

    A citation is now evidence and stays evidence, in ``answer_citations``. It
    becomes a proposed edge only where the citing sentence positively asserts a
    relation and carries no negation, contrast or qualification; everything else
    is returned under ``withheld`` with the reason, visible rather than dropped.

    Only the OPERATOR side: the answer citing the standard it was asked about is
    not a claim that the standard implements itself.
    """
    empty: dict[str, Any] = {"proposed": [], "withheld": []}
    row = repo._conn.execute(
        "SELECT subject_ref, question, answer FROM conversation_answers WHERE answer_id = ?",
        (answer_id,),
    ).fetchone()
    if row is None:
        return empty
    subject = src_ref or str(row[0])
    if not re.match(r"^CIP-\d{3}-[\w.]+\s+R\d+", subject, re.I):
        return empty
    if re.search(r"\b(?:hypothetical|scenario|suppose|if we)\b", str(row[1] or ""), re.I):
        return empty
    citations = repo._conn.execute(
        """SELECT cited_ref, jurisdiction, detail FROM answer_citations
           WHERE answer_id = ? AND resolved = 1 AND jurisdiction = 'internal'""",
        (answer_id,),
    ).fetchall()
    from portal.modules.compliance.core.section_index import parent_section_id

    answer = str(row[2] or "")
    proposed: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for citation, _jurisdiction, detail in citations:
        position = answer.find(str(citation))
        start = max(answer.rfind(".", 0, position), answer.rfind("\n", 0, position)) + 1
        end = answer.find(".", position)
        sentence = answer[start : (end + 1 if end >= 0 else len(answer))].strip()
        relation, reason = classify_assertion(sentence)
        entry = {
            "section_id": parent_section_id(str(citation)),
            "cited_ref": str(citation),
            "sentence": sentence or detail,
            "reason": reason,
        }
        if not relation:
            withheld.append(entry)
            continue
        proposed.append(
            {
                **entry,
                "relation": relation,
                "assertion_id": record_reading_link(
                    repo,
                    src_ref=subject,
                    dst_section_id=entry["section_id"],
                    answer_id=answer_id,
                    relation=relation,
                    rationale=(
                        f"answer {answer_id}; {reason}; cited sentence: "
                        f"{sentence or detail or str(citation)}"
                    ),
                ),
            }
        )
    return {
        "proposed": proposed,
        "withheld": withheld,
        "note": (
            "a citation is evidence, not an assertion: an edge is proposed only where the "
            "citing sentence positively asserts a relation"
        ),
    }
