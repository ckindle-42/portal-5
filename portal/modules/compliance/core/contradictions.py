"""The operator's review surfaces (PROVE_THEN_SCALE_V1 P5).

Not 1,427 rows. The operator checks the work by exception, and the exception
is generated:

* :func:`scan_contradictions` — every cross-reading disagreement the store
  already holds, found by machine: the same pair determined under different
  relation types by different readings, a determination on a pair a human
  REJECTED, and a determination that disagrees with an APPROVED edge. Each
  entry is a real question with both sides named — this is the review queue.
* :func:`drill_down` — an answer with its claims opened: every cited id and
  the verbatim text of both sides behind it, so an error in an answer is
  traceable to the citation that produced it, and correcting the answer
  corrects the edge behind it.
"""

from __future__ import annotations

import json

from typing import Any


def _pair_rows(repo: Any, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = repo.list_relationship_assertions(statuses=statuses)
    out = []
    for rel in rows:
        if rel.relation_type not in ("IMPLEMENTS", "EVIDENCES", "REFERENCES"):
            continue
        out.append(
            {
                "assertion_id": rel.assertion_id,
                "requirement_id": rel.src_ref,
                "section_id": rel.dst_ref,
                "relation_type": rel.relation_type,
                "status": rel.status,
                "derivation": str(getattr(rel, "derivation", "") or ""),
                "decided_by": rel.decided_by,
                "citations": list(rel.citations or []),
            }
        )
    return out


def scan_contradictions(repo: Any) -> dict[str, Any]:
    """Every cross-reading disagreement in the store, grouped by kind.

    * ``relation_conflicts`` — the same (requirement, section) pair carries
      different relation types from different readings. Both readings were of
      real text; the disagreement is the finding, and a human settles it once
      instead of re-reading the pair from scratch.
    * ``rejected_contradictions`` — a machine determination on a pair a human
      explicitly REJECTED. The strongest possible disagreement: labelled
      negative evidence versus a fresh reading.
    * ``approved_disagreements`` — a determination whose relation differs from
      an APPROVED edge on the same pair. Approved is a human's word; the
      disagreement is surfaced, never auto-resolved, and the approved edge
      stays authoritative.
    """
    determined = _pair_rows(repo, ("machine_determined",))
    decided = _pair_rows(repo, ("approved", "rejected"))
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in determined:
        by_pair.setdefault((row["requirement_id"], row["section_id"]), []).append(row)

    relation_conflicts: list[dict[str, Any]] = []
    for (requirement_id, section_id), rows in sorted(by_pair.items()):
        relations = sorted({r["relation_type"] for r in rows})
        if len(relations) > 1:
            relation_conflicts.append(
                {
                    "requirement_id": requirement_id,
                    "section_id": section_id,
                    "relations": [
                        {
                            "relation_type": r["relation_type"],
                            "assertion_id": r["assertion_id"],
                            "found_while_reading": [c.get("read_ref", "") for c in r["citations"]],
                        }
                        for r in rows
                    ],
                }
            )

    rejected_contradictions: list[dict[str, Any]] = []
    approved_disagreements: list[dict[str, Any]] = []
    decided_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in decided:
        decided_by_pair.setdefault((row["requirement_id"], row["section_id"]), []).append(row)
    for (requirement_id, section_id), rows in sorted(by_pair.items()):
        for decided_row in decided_by_pair.get((requirement_id, section_id), []):
            if decided_row["status"] == "rejected":
                rejected_contradictions.append(
                    {
                        "requirement_id": requirement_id,
                        "section_id": section_id,
                        "rejected_relation": decided_row["relation_type"],
                        "rejected_by": decided_row["decided_by"],
                        "now_determined": [
                            {
                                "relation_type": r["relation_type"],
                                "assertion_id": r["assertion_id"],
                            }
                            for r in rows
                        ],
                    }
                )
            else:  # approved
                for r in rows:
                    if r["relation_type"] != decided_row["relation_type"]:
                        approved_disagreements.append(
                            {
                                "requirement_id": requirement_id,
                                "section_id": section_id,
                                "approved_relation": decided_row["relation_type"],
                                "approved_by": decided_row["decided_by"],
                                "determined_relation": r["relation_type"],
                                "assertion_id": r["assertion_id"],
                            }
                        )
    return {
        "relation_conflicts": relation_conflicts,
        "rejected_contradictions": rejected_contradictions,
        "approved_disagreements": approved_disagreements,
        "n_items": (
            len(relation_conflicts) + len(rejected_contradictions) + len(approved_disagreements)
        ),
        "note": (
            "generated, small, every entry a real question: this is the review queue — "
            "not the full determination set"
        ),
    }


def drill_down(repo: Any, answer_id: str = "", *, run_id: str = "") -> dict[str, Any]:
    """One answer with every citation opened to verbatim text on both sides.

    The operator reads the ANSWER, not an edge. Each claim's id opens the
    section it cited — jurisdiction, standing, and the words — so an error is
    traceable to the citation that produced it, and correcting the answer
    corrects the edge behind it. A sweep's map reading stores no conversation
    answer, so its receipt's ``run_id`` opens the same surface from
    ``reading_runs``.
    """
    from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

    if run_id:
        row = repo._conn.execute(
            """SELECT question, answer, model, subject_ref, asked_at, verification_json
               FROM reading_runs WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return {"error": f"run {run_id!r} is not in the store"}
        citations = [
            {"cited_ref": c.get("cited_ref", ""), "resolved": c.get("resolved", False)}
            for c in (json.loads(row["verification_json"] or "{}").get("citations") or [])
        ]
    else:
        row = repo._conn.execute(
            """SELECT question, answer, model, subject_ref, asked_at FROM conversation_answers
               WHERE answer_id = ?""",
            (answer_id,),
        ).fetchone()
        if row is None:
            return {"error": f"answer {answer_id!r} is not in the store"}
        citations = [
            dict(c)
            for c in repo._conn.execute(
                """SELECT cited_ref, resolved, jurisdiction, source_kind FROM answer_citations
                   WHERE answer_id = ?""",
                (answer_id,),
            ).fetchall()
        ]
    ids = [str(c["cited_ref"]) for c in citations]
    resolved = resolve_sections(repo, [parent_section_id(s) for s in ids])
    opened: list[dict[str, Any]] = []
    for c in citations:
        section_id = parent_section_id(str(c["cited_ref"]))
        entry = resolved.get(section_id)
        opened.append(
            {
                "cited_ref": str(c["cited_ref"]),
                "resolved": bool(c.get("resolved")),
                "jurisdiction": str((entry or {}).get("jurisdiction", "")),
                "document": str((entry or {}).get("document_title") or ""),
                "headings": str((entry or {}).get("headings") or ""),
                "text": str((entry or {}).get("text", "")).strip(),
                "unresolved": entry is None,
            }
        )
    return {
        "answer_id": answer_id,
        "run_id": run_id,
        "question": str(row["question"]),
        "answer": str(row["answer"]),
        "model": str(row["model"]),
        "subject_ref": str(row["subject_ref"]),
        "asked_at": str(row["asked_at"]),
        "citations": opened,
    }


__all__ = ["drill_down", "scan_contradictions"]
