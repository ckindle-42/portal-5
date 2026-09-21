"""Property 4, finally satisfiable (PROVE_THEN_SCALE_V1 P6).

The module's founding docstring said settled mappings are *human-owned and
double as the evaluation set*. With a machine determining mappings at scale
that is circular: a scorer that measured machine determinations against
machine determinations would report a system's agreement with itself, which is
worse than ``honest-BLOCKED``. The split this module now enforces:

* **Operational mappings** — ``machine_determined`` rows, at scale,
  provenance-carrying. They build populations. They are never called approved,
  and they are **never** the scoring ground truth — not even after a human
  approves one in the ordinary review path, because approval of a row is not
  induction of that row into the evaluation set. Sample membership lives in
  the ``evaluation_sample`` table and nowhere else.
* **The evaluation set** — :func:`select_sample`'s small, stratified,
  human-confirmed sample (P5.3). :func:`labelled_examples` returns the sample
  and nothing else; :func:`score_reading` measures against it and only it.
  :func:`agreement` reports the machine's agreement with the sample — the
  first honest mapping-accuracy number this module has had.

Two disciplines survive unchanged from the founding contract:

* **The scorer is an offline instrument.** Nothing in the product path imports
  it — a test in ``tests/unit/test_compliance_evaluation.py`` walks ``portal/``
  and asserts no importer outside this module.
* **No ground truth is not a bad reading.** An empty or undecided sample
  returns ``honest-BLOCKED`` naming the shortfall — never a score of 0, which
  is how a green board gets manufactured.
"""

from __future__ import annotations

import random
import re
from typing import Any

from portal.modules.compliance.core.answer_contract import _SECTION_TOKEN

#: relation types that are requirement→document mappings (mapping_store's own
#: list — a typed edge of another kind is not a coverage mapping).
_MAPPING_RELATION_TYPES = ("IMPLEMENTS", "EVIDENCES", "REFERENCES")
_SEP = "::"
_SAMPLE = "evaluation_sample"

_CITATION_KEYS = ("cited_ref", "section_id", "citation")

#: The decisions a sample reviewer can record. CONFIRMED agrees with the
#: machine; CORRECTED keeps the pair and replaces the relation; REJECTED is a
#: labelled negative.
SAMPLE_DECISIONS = ("CONFIRMED", "CORRECTED", "REJECTED")


def _section_of_dst(dst_ref: str) -> str:
    """``doc::section`` carries the section after the separator; a bare value is
    already a section id."""
    _doc, sep, section = str(dst_ref).partition(_SEP)
    return section if sep else str(dst_ref)


def _standard_of(requirement_id: str) -> str:
    match = re.match(r"(CIP-\d{3})", str(requirement_id))
    return match.group(1) if match else str(requirement_id).split(" ")[0]


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"


def select_sample(
    repo: Any,
    *,
    n: int = 36,
    seed: str = "prove-then-scale-v1",
    org_id: str = "default",
) -> dict[str, Any]:
    """Pick the stratified sample the operator will confirm or correct.

    Stratified across standards, relation types and confidence bands (P5.3) —
    a sample that drifted to one standard or one relation would measure the
    easy cells. Deterministic on ``seed``: re-running the selection grows the
    sample without reshuffling it, and two runs with the same seed and store
    pick the same rows. Rows already sampled are never sampled twice.

    The quota per stratum is ``n`` spread evenly, redistributed round-robin
    across strata with surplus when a stratum is short — recorded with the
    selection, because a sample whose shape nobody can state is a sample
    nobody can trust.
    """
    from portal.modules.compliance.core.temporal import now_iso

    rows = [
        {
            "assertion_id": rel.assertion_id,
            "requirement_id": rel.src_ref,
            "section_id": _section_of_dst(rel.dst_ref),
            "relation_type": rel.relation_type,
            "confidence": float(getattr(rel, "confidence", 0.0) or 0.0),
        }
        for rel in repo.list_relationship_assertions(statuses=("machine_determined",))
        if rel.relation_type in _MAPPING_RELATION_TYPES
    ]
    already = {
        str(r[0])
        for r in repo._conn.execute("SELECT assertion_id FROM evaluation_sample").fetchall()
    }
    fresh = [r for r in rows if r["assertion_id"] not in already]

    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in fresh:
        key = (
            _standard_of(row["requirement_id"]),
            row["relation_type"],
            _confidence_band(row["confidence"]),
        )
        strata.setdefault(key, []).append(row)
    for key in strata:
        strata[key].sort(key=lambda r: r["assertion_id"])
        random.Random(f"{seed}|{key}").shuffle(strata[key])

    keys = sorted(strata)
    quota = {key: (n // len(keys) if keys else 0) for key in keys}
    remaining = n - sum(quota.values())
    round_robin = keys[:]
    random.Random(f"{seed}|roundrobin").shuffle(round_robin)
    idx = 0
    while remaining > 0 and round_robin:
        key = round_robin[idx % len(round_robin)]
        if quota[key] < len(strata[key]):
            quota[key] += 1
            remaining -= 1
        idx += 1
        if idx > 100 * max(1, len(keys)):
            break

    picked: list[dict[str, Any]] = []
    short: list[tuple[str, str, str]] = []
    for key in keys:
        take = strata[key][: min(quota[key], len(strata[key]))]
        picked.extend(take)
        if len(take) < quota[key]:
            short.append(key)

    selected_at = now_iso()
    sample_ids = []
    with repo._lock, repo._conn:
        for row in picked:
            sample_id = "sample-" + str(abs(hash((seed, row["assertion_id"]))) % (10**12)).zfill(12)
            repo._conn.execute(
                """INSERT INTO evaluation_sample(sample_id, assertion_id, requirement_id,
                       section_id, relation_type, machine_relation, confidence,
                       confidence_band, stratum_standard, stratum_relation, selected_at, org_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(sample_id) DO NOTHING""",
                (
                    sample_id,
                    row["assertion_id"],
                    row["requirement_id"],
                    row["section_id"],
                    row["relation_type"],
                    row["relation_type"],
                    row["confidence"],
                    _confidence_band(row["confidence"]),
                    _standard_of(row["requirement_id"]),
                    row["relation_type"],
                    selected_at,
                    org_id,
                ),
            )
            sample_ids.append(sample_id)
    return {
        "requested": n,
        "selected": len(picked),
        "strata": {f"{k[0]}|{k[1]}|{k[2]}": quota[k] for k in keys},
        "strata_short": short,
        "n_determined_rows": len(rows),
        "already_sampled": len(already),
        "sample_ids": sample_ids,
        "seed": seed,
        "note": (
            "measurement only: confirming or correcting these rows is what makes the "
            "evaluation set, and it is the only thing the scorer will ever measure against"
        ),
    }


def record_sample_decision(
    repo: Any,
    sample_id: str,
    decision: str,
    *,
    human_relation: str = "",
    decided_by: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """The operator's word on one sampled row — the label being made."""
    from portal.modules.compliance.core.temporal import now_iso

    decision = decision.upper()
    if decision not in SAMPLE_DECISIONS:
        raise ValueError(f"decision must be one of {SAMPLE_DECISIONS}, not {decision!r}")
    if decision == "CORRECTED" and not human_relation:
        raise ValueError("CORRECTED requires human_relation — the relation the human settled on")
    with repo._lock, repo._conn:
        cur = repo._conn.execute(
            """UPDATE evaluation_sample
               SET decision = ?, human_relation = ?, decided_by = ?, decided_at = ?, notes = ?
               WHERE sample_id = ?""",
            (
                decision,
                human_relation.upper(),
                decided_by,
                now_iso(),
                notes,
                sample_id,
            ),
        )
        if cur.rowcount == 0:
            raise KeyError(sample_id)
    return {"sample_id": sample_id, "decision": decision}


def sample_rows(repo: Any, *, decided_only: bool = False) -> list[dict[str, Any]]:
    """The sample table, decoded. ``decided_only`` narrows to labelled rows."""
    clause = "WHERE decision <> ''" if decided_only else ""
    rows = repo._conn.execute(
        f"SELECT * FROM evaluation_sample {clause} ORDER BY stratum_standard, requirement_id, section_id",  # noqa: S608
    ).fetchall()
    return [dict(r) for r in rows]


def agreement(repo: Any) -> dict[str, Any]:
    """The machine's agreement with the human-confirmed sample.

    This number — decided rows where the human CONFIRMED the machine's
    relation, over all decided rows — is the system's mapping accuracy, and
    the first honest one this module has had. CORRECTED and REJECTED count as
    disagreements: a corrected relation means the machine named the wrong one;
    a rejection means the machine paired at all where the human said no. An
    undecided sample reports ``None`` and says so — never a rate over an empty
    numerator dressed as zero.
    """
    rows = sample_rows(repo, decided_only=True)
    if not rows:
        return {
            "verdict": "honest-BLOCKED",
            "reason": "no decided sample rows — the evaluation set has no labels yet (P5.3)",
            "n_decided": 0,
            "agreement_rate": None,
        }
    confirmed = sum(1 for r in rows if r["decision"] == "CONFIRMED")
    corrected = sum(1 for r in rows if r["decision"] == "CORRECTED")
    rejected = sum(1 for r in rows if r["decision"] == "REJECTED")
    by_relation: dict[str, dict[str, Any]] = {}
    for r in rows:
        slot = by_relation.setdefault(r["machine_relation"], {"n": 0, "confirmed": 0})
        slot["n"] += 1
        slot["confirmed"] += 1 if r["decision"] == "CONFIRMED" else 0
    return {
        "verdict": "scored",
        "n_decided": len(rows),
        "n_confirmed": confirmed,
        "n_corrected": corrected,
        "n_rejected": rejected,
        "agreement_rate": round(confirmed / len(rows), 4),
        "by_machine_relation": {
            k: {**v, "agreement": round(v["confirmed"] / v["n"], 4) if v["n"] else None}
            for k, v in sorted(by_relation.items())
        },
        "note": "machine determinations versus the human-confirmed sample — the mapping accuracy",
    }


def _decided_rows(repo: Any, standard: str) -> list[dict[str, Any]]:
    rows = sample_rows(repo, decided_only=True)
    if standard:
        rows = [r for r in rows if standard.lower() in str(r["requirement_id"]).lower()]
    return rows


def labelled_examples(
    repo: Any, *, standard: str = "", min_status: str = "approved"
) -> list[dict[str, Any]]:
    """The human-confirmed sample, as labelled examples — the ONLY scoring
    ground truth this module exposes.

    One example per requirement in the sample: the sections a human CONFIRMED
    or CORRECTED as ``settled_sections``, the REJECTED ones as
    ``rejected_sections`` (labelled negatives), who decided and when.
    ``label_source`` says where every label came from, so a consumer can tell
    the sample from any future source without a schema change.

    ``min_status='proposed'`` widens the export to UNDECIDED sample rows —
    selections awaiting their reviewer — emitted with empty
    ``settled_sections`` and ``label_source='evaluation_sample:pending'``.
    Useful for review bookkeeping, never for scoring: a scorer fed a pending
    row gets an ``honest-BLOCKED`` for that requirement, which is the honest
    answer. The operational ``machine_determined`` set is NOT exported here at
    any setting — that is the circularity this module exists to prevent.
    """
    if min_status not in ("approved", "proposed"):
        raise ValueError(f"min_status must be 'approved' or 'proposed', not {min_status!r}")
    by_requirement: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def _slot(requirement_id: str, label_source: str) -> dict[str, Any]:
        if requirement_id not in by_requirement:
            by_requirement[requirement_id] = {
                "requirement_id": requirement_id,
                "settled_sections": [],
                "rejected_sections": [],
                "approved_by": "",
                "approved_date": "",
                "correction": False,
                "label_source": label_source,
            }
            order.append(requirement_id)
        return by_requirement[requirement_id]

    for row in _decided_rows(repo, standard):
        example = _slot(str(row["requirement_id"]), _SAMPLE)
        if row["decision"] == "REJECTED":
            example["rejected_sections"] = sorted(
                set(example["rejected_sections"]) | {str(row["section_id"])}
            )
        else:
            example["settled_sections"] = sorted(
                set(example["settled_sections"]) | {str(row["section_id"])}
            )
        if row["decided_by"]:
            example["approved_by"] = str(row["decided_by"])
            example["approved_date"] = str(row["decided_at"] or "")[:10]
        if row["decision"] == "CORRECTED":
            example["correction"] = True
    if min_status == "proposed":
        for row in sample_rows(repo):
            if row["decision"]:
                continue
            if standard and standard.lower() not in str(row["requirement_id"]).lower():
                continue
            _slot(str(row["requirement_id"]), "evaluation_sample:pending")
    return [by_requirement[req] for req in order]


def as_eval_set(examples: list[dict[str, Any]]) -> dict[str, Any]:
    """The shape the WFE suite consumes (file C binds this, not the store).

    Every example carries its expected citations and its labelled negatives;
    ``label_source`` says where each label came from, so a consumer can tell a
    human-settled sample row from any future label source without a schema
    change.
    """
    return {
        "eval_set": "compliance_requirement_sections",
        "version": 2,
        "label_source": _SAMPLE,
        "n_examples": len(examples),
        "examples": [
            {
                "requirement_id": e["requirement_id"],
                "expected_sections": sorted(set(e["settled_sections"])),
                "rejected_sections": sorted(set(e.get("rejected_sections", ()))),
                "approved_by": e.get("approved_by", ""),
                "approved_date": e.get("approved_date", ""),
                "correction": bool(e.get("correction")),
                "label_source": e.get("label_source", _SAMPLE),
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
        stripped = ref.strip()
        # Permissive on shape, same as the contract's own extraction: a
        # malformed id is still a citation attempt and belongs in the score
        # as unlabelled, not silently dropped for failing a stricter regex.
        looks_like_a_section = _SECTION_TOKEN.fullmatch(stripped) or stripped.startswith(
            ("csection-", "isection-")
        )
        if looks_like_a_section and ref not in out:
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


def score_reading(answer_payload: dict[str, Any], examples: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one reading's citation behaviour against the labelled set.

    OFFLINE ONLY. The measures, in the order they can fail:

    * **citation recall** — of the sections the sample CONFIRMED for this
      requirement, how many did the reading cite;
    * **citation precision** — of the sample's sections cited, how many are
      confirmed. A cited section the sample does not mention is
      ``unlabelled``, never wrong: the sample is small by construction, and
      scoring an unlabelled citation as a miss punishes a reading for finding
      something true;
    * **rejected-mapping avoidance** — a section the human REJECTED in the
      sample is a labelled negative; citing one is flagged, separately and by
      name;
    * **closure honesty** — carried from the reading's own receipt when the
      payload has one (file B); absent, the field is ``None``, never 0.

    No labelled example for this requirement, or no confirmed sections in it,
    is ``honest-BLOCKED`` naming the shortfall — no ground truth is not the
    same as a bad reading, and conflating them is how a green board gets
    manufactured.
    """
    if not examples:
        return _blocked(
            "the labelled set is empty — no human-confirmed sample rows exist to score against"
        )
    requirement_id = str(
        answer_payload.get("ref")
        or answer_payload.get("requirement_id")
        or answer_payload.get("requirement")
        or ""
    )
    example = next((e for e in examples if e.get("requirement_id") == requirement_id), None)
    if example is None:
        return _blocked(
            f"no labelled example for requirement {requirement_id!r} — "
            f"{len(examples)} labelled requirement(s) exist for other refs",
            requirement_id,
        )
    settled = sorted(set(example.get("settled_sections") or ()))
    if not settled:
        return _blocked(
            f"requirement {requirement_id!r} carries no confirmed section mapping — "
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
