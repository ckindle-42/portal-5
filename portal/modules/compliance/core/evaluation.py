"""The approved mappings ARE the evaluation set (SUBSTRATE_PROPERTIES_V1 P5).

``mapping_store`` has said since T3 Phase 4 that every approved or corrected
mapping is a labelled example — a machine judgment a human settled, the most
informative label the module can own. Nothing used them that way. A reading
could not be scored, so the seat was chosen by hand-reading transcripts, so it
has been "provisional" since it was chosen. This module is the fix, and it is
deliberately small:

* :func:`labelled_examples` exports the settled ``requirement → section``
  mappings as labelled examples — plus the explicitly REJECTED mappings, which
  are labelled negatives and the sharpest error signal available;
* :func:`as_eval_set` emits the shape a WFE suite consumes, so file C binds it
  without a translation layer;
* :func:`score_reading` measures a reading's CITATION behaviour against the
  labelled set — never prose quality. A rubric that could capture "did it
  understand the material" would make the reading model unnecessary; the only
  thing that can be scored mechanically is what the reading cited.

Two disciplines, both mandatory (P5.3):

* **The scorer is an offline instrument.** Nothing in the product path imports
  it — a test in ``tests/unit/test_compliance_evaluation.py`` walks ``portal/``
  and asserts no importer outside this module. It never adjudicates a live
  answer.
* **No ground truth is not a bad reading.** An empty mapping set returns
  ``honest-BLOCKED`` naming the shortfall — never a score of 0, which is how a
  green board gets manufactured.
"""

from __future__ import annotations

import re
from typing import Any

#: relation types that are requirement→document mappings (mapping_store's own
#: list — a typed edge of another kind is not a coverage mapping).
_MAPPING_RELATION_TYPES = ("IMPLEMENTS", "EVIDENCES", "REFERENCES")
_SEP = "::"

_CITATION_KEYS = ("cited_ref", "section_id", "citation")
_REF_RE = re.compile(r"c?[a-z]*section-[0-9a-f]{8,}|isection-[0-9a-f]{8,}")


def _section_of_dst(dst_ref: str) -> str:
    """``doc::section`` carries the section after the separator; a bare value is
    already a section id."""
    _doc, sep, section = str(dst_ref).partition(_SEP)
    return section if sep else str(dst_ref)


def _labelled_rows(repo: Any, statuses: tuple[str, ...], standard: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in repo.list_relationship_assertions(statuses=statuses):
        if rel.relation_type not in _MAPPING_RELATION_TYPES:
            continue
        if standard and standard.lower() not in str(rel.src_ref).lower():
            continue
        rows.append(
            {
                "requirement_id": str(rel.src_ref),
                "section_id": _section_of_dst(rel.dst_ref),
                "status": str(rel.status),
                "review_state": str(rel.review_state),
                "approved_by": str(rel.decided_by or ""),
                "approved_date": str(rel.decided_at or "")[:10],
                "assertion_id": str(rel.assertion_id),
            }
        )
    return rows


def labelled_examples(
    repo: Any, *, standard: str = "", min_status: str = "approved"
) -> list[dict[str, Any]]:
    """The settled ``requirement → section`` mappings, as labelled examples.

    One example per mapping row: the requirement ref, the internal section id
    that implements it, who approved it, when, and whether it was a CORRECTION
    of a proposal — a correction is the most informative label in the store,
    because it records a machine judgment a human overturned.

    ``min_status`` widens the export downward: ``"approved"`` (default) is the
    settled set and the scoring ground truth; ``"proposed"`` also emits
    machine-proposed mappings, labelled as such — useful for coverage review,
    never for scoring. Explicitly REJECTED/REVOKED rows travel alongside as
    ``rejected_sections`` per requirement: labelled negatives, scored
    separately, never silently mixed into the positives.
    """
    if min_status not in ("approved", "proposed"):
        raise ValueError(f"min_status must be 'approved' or 'proposed', not {min_status!r}")
    statuses = ("approved", "proposed") if min_status == "proposed" else ("approved",)
    approved = _labelled_rows(repo, statuses, standard)
    rejected = _labelled_rows(repo, ("rejected", "revoked"), standard)
    rejected_by_req: dict[str, list[str]] = {}
    for row in rejected:
        rejected_by_req.setdefault(row["requirement_id"], []).append(row["section_id"])

    by_requirement: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in approved:
        req = row["requirement_id"]
        if req not in by_requirement:
            by_requirement[req] = {
                "requirement_id": req,
                "settled_sections": [],
                "rejected_sections": sorted(set(rejected_by_req.get(req, ()))),
                "approved_by": "",
                "approved_date": "",
                "correction": False,
                "label_source": "mapping_store",
            }
            order.append(req)
        example = by_requirement[req]
        example["settled_sections"].append(row["section_id"])
        if row["approved_by"]:
            example["approved_by"] = row["approved_by"]
            example["approved_date"] = row["approved_date"]
        if row["review_state"] == "CORRECTED":
            example["correction"] = True
    examples = [by_requirement[req] for req in order]
    for req, sections in rejected_by_req.items():
        if req not in by_requirement:
            examples.append(
                {
                    "requirement_id": req,
                    "settled_sections": [],
                    "rejected_sections": sorted(set(sections)),
                    "approved_by": "",
                    "approved_date": "",
                    "correction": False,
                    "label_source": "mapping_store",
                }
            )
    return examples


def as_eval_set(examples: list[dict[str, Any]]) -> dict[str, Any]:
    """The shape the WFE suite consumes (file C binds this, not the store).

    Every example carries its expected citations and its labelled negatives;
    ``label_source`` says where each label came from, so a consumer can tell a
    human-settled mapping from any future label source without a schema change.
    """
    return {
        "eval_set": "compliance_requirement_sections",
        "version": 1,
        "label_source": "mapping_store",
        "n_examples": len(examples),
        "examples": [
            {
                "requirement_id": e["requirement_id"],
                "expected_sections": sorted(set(e["settled_sections"])),
                "rejected_sections": sorted(set(e.get("rejected_sections", ()))),
                "approved_by": e.get("approved_by", ""),
                "approved_date": e.get("approved_date", ""),
                "correction": bool(e.get("correction")),
                "label_source": e.get("label_source", "mapping_store"),
            }
            for e in examples
        ],
    }


def _cited_sections(answer_payload: dict[str, Any]) -> list[str]:
    """The internal section ids a reading cited, in order, deduplicated.

    Reads the stored-answer payload's ``verification.citations`` (the reader's
    own shape), falling back to a bare ``citations`` list. Only strings that
    look like section ids count — an address like ``CIP-007-6 R2 Part 2.2`` is
    the requirement, not a citation of the operator's material.
    """
    out: list[str] = []
    verification = answer_payload.get("verification") or {}
    entries = verification.get("citations") or answer_payload.get("citations") or []
    for entry in entries:
        ref = ""
        if isinstance(entry, dict):
            for key in _CITATION_KEYS:
                if entry.get(key):
                    ref = str(entry[key])
                    break
        else:
            ref = str(entry)
        if not ref:
            continue
        if (
            _REF_RE.fullmatch(ref.strip()) or ref.strip().startswith(("csection-", "isection-"))
        ) and ref not in out:
            out.append(ref)
    return out


def _blocked(reason: str, requirement_id: str = "") -> dict[str, Any]:
    return {
        "verdict": "honest-BLOCKED",
        "reason": reason,
        "requirement_id": requirement_id,
        "citation_recall": None,
        "citation_precision": None,
        "unlabelled": [],
        "rejected_mapping_avoidance": None,
        "rejected_cited": [],
        "closure_honesty": None,
    }


def score_reading(
    answer_payload: dict[str, Any], examples: list[dict[str, Any]]
) -> dict[str, Any]:
    """Score one reading's citation behaviour against the labelled set.

    OFFLINE ONLY. The measures, in the order they can fail:

    * **citation recall** — of the sections a settled mapping says implement
      this requirement, how many did the reading cite;
    * **citation precision** — of the labelled sections cited, how many are in
      the settled mapping. A cited section the mapping does not mention is
      ``unlabelled``, never wrong: the mapping set is incomplete by
      construction, and scoring an unlabelled citation as a miss punishes a
      reading for finding something true;
    * **rejected-mapping avoidance** — a mapping explicitly rejected by a human
      is a labelled negative; citing one is flagged, separately and by name;
    * **closure honesty** — carried from the reading's own receipt when the
      payload has one (file B); absent, the field is ``None``, never 0.

    No labelled example for this requirement, or no labelled sections in it, is
    ``honest-BLOCKED`` naming the shortfall — no ground truth is not the same
    as a bad reading, and conflating them is how a green board gets
    manufactured.
    """
    if not examples:
        return _blocked("the labelled set is empty — no settled requirement→document "
                        "mappings exist to score against")
    requirement_id = str(
        answer_payload.get("ref")
        or answer_payload.get("requirement_id")
        or answer_payload.get("requirement")
        or ""
    )
    example = next(
        (e for e in examples if e.get("requirement_id") == requirement_id), None
    )
    if example is None:
        return _blocked(
            f"no labelled example for requirement {requirement_id!r} — "
            f"{len(examples)} labelled requirement(s) exist for other refs",
            requirement_id,
        )
    settled = sorted(set(example.get("settled_sections") or ()))
    if not settled:
        return _blocked(
            f"requirement {requirement_id!r} carries no settled section mapping — "
            "nothing to recall against",
            requirement_id,
        )
    cited = _cited_sections(answer_payload)
    cited_set = set(cited)
    rejected = set(example.get("rejected_sections") or ())
    hits = sorted(cited_set & set(settled))
    rejected_cited = sorted(cited_set & rejected)
    unlabelled = sorted(cited_set - set(settled) - rejected)
    labelled_cited = cited_set & (set(settled) | rejected)
    closure = answer_payload.get("closure_receipt") or answer_payload.get("closure")
    return {
        "verdict": "scored",
        "requirement_id": requirement_id,
        "citation_recall": (len(hits) / len(settled)) if settled else None,
        "citation_precision": (len(hits) / len(labelled_cited)) if labelled_cited else None,
        "cited": cited,
        "settled_sections": settled,
        "hits": hits,
        "misses": sorted(set(settled) - cited_set),
        "unlabelled": unlabelled,
        "rejected_mapping_avoidance": (not rejected_cited) if cited else None,
        "rejected_cited": rejected_cited,
        "closure_honesty": closure if closure is not None else None,
    }
