"""Workstream C — semantic duty alignment (IMPLEMENTATION_BRIEF §4).

This is the narrow reading pass that runs *before* any arithmetic or council
judgment. It does not decide FULL/PARTIAL/NONE. For one Part it reads the
complete candidate set against the complete governing duty (full Part text,
verified lead-in, cited definitions/references and the scope context) and
returns one :class:`AlignmentRecord` per candidate:

  - ``SAME``      the clause prescribes or implements the governing
                  activity/object for an overlapping population with a
                  compatible trigger (different deadlines / weaker wording /
                  incomplete satisfaction stay SAME);
  - ``DIFFERENT`` the wording positively establishes another duty or
                  non-operative material;
  - ``UNKNOWN``   the supplied text establishes neither; the precise missing
                  fact is recorded and no arithmetic may use the record.

Agreement is categorical and reaches a relation only by the same quorum rule
``council.run_council`` uses; confidence is never a vote and there is no
keyword/lexical fallback. Every candidate ID must appear exactly once in every
seat's response — an omission, an invalid response, or duplicate inconsistent
IDs fail the whole alignment (``valid=False``) rather than being retried for a
more favorable answer.

The reader is deliberately sealed from the later stages: it never receives a
prior determination, a gold label, an approved verdict or a coverage decision.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from portal.modules.compliance.core.constraints import CONSTRAINT_KINDS, Quantity
from portal.modules.compliance.core.determination import (
    ALIGNMENT_RELATIONS,
    POPULATION_OVERLAPS,
    SOURCE_FUNCTIONS,
    AlignmentRecord,
    AlignmentResult,
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    ConstraintBinding,
    GoverningBundle,
    SourceSlice,
)

__all__ = ["align_part"]

_UNITS = ("hour", "day", "week", "month", "year")
_OPERATIVE = "OPERATIVE_COMMITMENT"

_ALIGNMENT_SYSTEM = (
    "You are a narrow clause-alignment reader. You compare source clauses and "
    "return categorical duty identities. You never decide whether a requirement "
    "is met, and you never output a confidence score.\n"
    "Given one governing duty (its full Part text, the verified lead-in, cited "
    "definitions and references, and the scope context) and a list of candidate "
    "source clauses, classify each candidate clause's relation to the duty:\n"
    "- SAME: the clause prescribes or implements the governing activity/object "
    "for an overlapping population with a compatible trigger. Different "
    "deadlines, weaker wording, omitted conditions or incomplete wording stay "
    "SAME.\n"
    "- DIFFERENT: the wording positively establishes another activity, another "
    "triggering duty, a disjoint population, or non-operative reference "
    "material.\n"
    "- UNKNOWN: the supplied text does not establish either; state the precise "
    "missing fact.\n"
    "RULES:\n"
    "- Read the source semantically. Do not use keyword overlap, folder names, "
    "file names or numeric equality to decide the relation.\n"
    "- Select only slice ids that appear in the supplied selectable slices. "
    "Never write a quoted string, an ellipsis, or a character offset.\n"
    '- Every candidate_id must appear exactly once in "records".\n'
    "- A chunk that mixes topics returns separate records.\n"
    "- constraint_bindings capture numeric constraints: pick the exact governing "
    "and candidate operand slice ids, the literal digit as written (for example "
    '35 in "thirty-five (35) calendar days"), the unit, the qualifier and the '
    "constraint kind and direction.\n"
    'Return ONE JSON object: {"records":[{...}]}.'
)


def align_part(request: AssessmentRequest, context: AssessmentContext) -> AlignmentResult:
    """Read the full candidate set of one Part against its governing duty.

    Seats are injected through ``context.seat_fn``; the configured roster and
    quorum come from ``context``. Never raises for a malformed model response:
    an unusable reader contract is an ``AlignmentResult(valid=False)``.
    """
    governing = request.governing
    candidate_set = request.candidate_set
    part_ref = (governing.ref if governing else "") or request.requirement_id
    if governing is None or candidate_set is None:
        return AlignmentResult(
            part_ref=part_ref,
            valid=False,
            failure="alignment requires a governing bundle and a pinned candidate set",
        )
    seats = list(context.seats or [])
    if not seats:
        return AlignmentResult(part_ref=part_ref, valid=False, failure="no configured seats")

    fn = context.seat_fn
    if fn is None:
        fn = _default_seat_fn()

    candidate_ids = [c.candidate_id for c in candidate_set.records]
    if not candidate_ids:
        # No supplied candidate needs reading; absence is judged by the council
        # over the governing unit, not by a model asked to align nothing.
        return AlignmentResult(part_ref=part_ref, records=[], valid=True, raw={"seats": []})
    user = json.dumps(_build_user_packet(request), indent=2, ensure_ascii=False, default=str)
    responses: list[dict[str, Any]] = []
    seat_records: dict[str, dict[str, dict[str, Any]]] = {}
    seat_order: list[str] = []
    for seat in seats:
        seat_id = str(seat.get("id", ""))
        model = str(seat.get("model", ""))
        try:
            raw = fn(model, _ALIGNMENT_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001 - a failed reader seat fails the reading
            return AlignmentResult(
                part_ref=part_ref,
                valid=False,
                failure=f"seat {seat_id} error: {exc}",
                raw={"seats": responses},
            )
        parsed, err = _parse_seat(raw, candidate_ids)
        responses.append({"seat_id": seat_id, "model": model, "raw": raw})
        if parsed is None:
            return AlignmentResult(
                part_ref=part_ref,
                valid=False,
                failure=f"seat {seat_id}: {err}",
                raw={"seats": responses},
            )
        seat_records[seat_id] = parsed
        seat_order.append(seat_id)

    required = _quorum(context.quorum, len(seats))
    gov_by_id = {s.slice_id: s for s in governing.source_slices}
    records = [
        _aggregate(cand, governing.ref, seat_order, seat_records, required, gov_by_id)
        for cand in candidate_set.records
    ]

    pairs = request.metadata.get("internal_pairs") if request.metadata else None
    if pairs:
        records.extend(_align_pairs(request, records, pairs, seats, fn, required, gov_by_id))

    return AlignmentResult(part_ref=part_ref, records=records, valid=True, raw={"seats": responses})


# ── seat protocol ───────────────────────────────────────────────────────────


def _build_user_packet(request: AssessmentRequest) -> dict[str, Any]:
    governing = request.governing
    candidate_set = request.candidate_set
    return {
        "task": "clause_alignment",
        "governing": {
            "ref": governing.ref if governing else request.requirement_id,
            "part_text": governing.part_text if governing else "",
            "lead_in": governing.lead_in if governing else "",
            "definitions": governing.definitions if governing else [],
            "references": governing.references if governing else [],
            "selectable_slice_ids": _governing_slice_ids(governing),
        },
        "scope": _scope_dict(request.scope),
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "text": c.text,
                "locator": c.locator,
                "selectable_slice_ids": _candidate_slice_ids(c),
            }
            for c in (candidate_set.records if candidate_set else [])
        ],
    }


def _parse_seat(raw: str, candidate_ids: list[str]) -> tuple[dict[str, dict[str, Any]] | None, str]:
    obj = _json_object(raw)
    if obj is None:
        return None, "response was not a JSON object"
    items = obj.get("records")
    if not isinstance(items, list):
        return None, "response is missing the 'records' list"
    known = set(candidate_ids)
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            return None, "a record is not a JSON object"
        cid = str(item.get("candidate_id", ""))
        if cid not in known:
            return None, f"unknown candidate_id {cid!r}"
        try:
            norm = _normalize_record(item)
        except ValueError as exc:
            return None, f"candidate {cid}: {exc}"
        if cid in by_id and by_id[cid] != norm:
            return None, f"duplicate inconsistent records for {cid!r}"
        by_id[cid] = norm
    missing = [cid for cid in candidate_ids if cid not in by_id]
    if missing:
        return None, f"omitted candidate ids: {missing}"
    return by_id, ""


def _normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    relation = str(raw.get("relation", "")).upper()
    if relation not in ALIGNMENT_RELATIONS:
        raise ValueError(f"invalid relation {relation!r}")
    overlap = str(raw.get("population_overlap", "UNKNOWN")).upper()
    if overlap not in POPULATION_OVERLAPS:
        overlap = "UNKNOWN"
    source_function = str(raw.get("source_function", "OTHER")).upper()
    if source_function not in SOURCE_FUNCTIONS:
        source_function = "OTHER"
    bindings = raw.get("constraint_bindings") or []
    if not isinstance(bindings, list):
        raise ValueError("constraint_bindings must be a list")
    return {
        "relation": relation,
        "population_overlap": overlap,
        "source_function": source_function,
        "activity": str(raw.get("activity", "")),
        "object": str(raw.get("object", "")),
        "trigger": str(raw.get("trigger", "")),
        "population": str(raw.get("population", "")),
        "rationale": str(raw.get("rationale", "")),
        "governing_slice_ids": _str_list(raw.get("governing_slice_ids")),
        "candidate_slice_ids": _str_list(raw.get("candidate_slice_ids")),
        "missing_facts": _str_list(raw.get("missing_facts")),
        "constraint_bindings": [b for b in bindings if isinstance(b, dict)],
    }


# ── aggregation ─────────────────────────────────────────────────────────────


def _aggregate(
    cand: CandidateRecord,
    governing_ref: str,
    seat_order: list[str],
    seat_records: dict[str, dict[str, dict[str, Any]]],
    required: int,
    gov_by_id: dict[str, SourceSlice],
) -> AlignmentRecord:
    cand_allowed = set(_candidate_slice_ids(cand))
    gov_allowed = set(gov_by_id)
    gov_default = next(iter(gov_by_id), "")
    votes: list[tuple[str, dict[str, Any], bool]] = []
    for seat_id in seat_order:
        record = seat_records[seat_id][cand.candidate_id]
        record = _resolve_slices(record, cand, gov_default, cand_allowed, gov_allowed)
        valid, _ = _validate_vote(record, cand_allowed, gov_allowed)
        votes.append((seat_id, record, valid))

    same = [v for v in votes if v[2] and v[1]["relation"] == "SAME"]
    diff = [v for v in votes if v[2] and v[1]["relation"] == "DIFFERENT"]
    if len(same) >= required and len(same) > len(diff):
        return _decided_record(governing_ref, cand, "SAME", same, gov_by_id, cand_allowed)
    if len(diff) >= required and len(diff) > len(same):
        return _decided_record(governing_ref, cand, "DIFFERENT", diff, gov_by_id, cand_allowed)
    return _unknown_record(governing_ref, cand, votes, same, diff, required)


def _decided_record(
    governing_ref: str,
    cand: CandidateRecord,
    relation: str,
    winning: list[tuple[str, dict[str, Any], bool]],
    gov_by_id: dict[str, SourceSlice],
    cand_allowed: set[str],
) -> AlignmentRecord:
    template = winning[0][1]
    gov_ids = _dedupe(
        [i for _, r, _ in winning for i in r["governing_slice_ids"] if i in gov_by_id]
    )
    cand_ids = _dedupe(
        [i for _, r, _ in winning for i in r["candidate_slice_ids"] if i in cand_allowed]
    )
    if not cand_ids and cand.source_slice is not None:
        cand_ids = [cand.source_slice.slice_id]
    # The link id carries the human-readable document id ahead of the opaque
    # candidate id, so a seat's citation of the document name resolves in the
    # council allowlist (and in the report's consensus match) without changing
    # council internals. The candidate id remains the stable key for lookup.
    link_id = _link_id(cand)
    cand_text = cand.source_slice.text if cand.source_slice is not None else cand.text
    bindings = _bindings_from_winning(link_id, winning, gov_by_id, cand_allowed, cand_text)
    return AlignmentRecord(
        link_id=link_id,
        governing_ref=governing_ref,
        governing_slice_ids=gov_ids,
        candidate_ref=cand.candidate_id,
        document_id=cand.document_id,
        candidate_slice_ids=cand_ids,
        relation=relation,
        activity=template["activity"],
        object=template["object"],
        trigger=template["trigger"],
        population=template["population"],
        population_overlap=template["population_overlap"],
        source_function=template["source_function"],
        rationale=template["rationale"],
        missing_facts=_dedupe(template["missing_facts"]),
        constraint_bindings=bindings,
    )


def _unknown_record(
    governing_ref: str,
    cand: CandidateRecord,
    votes: list[tuple[str, dict[str, Any], bool]],
    same: list[tuple[str, dict[str, Any], bool]],
    diff: list[tuple[str, dict[str, Any], bool]],
    required: int,
) -> AlignmentRecord:
    abstentions = [v for v in votes if v[2] and v[1]["relation"] == "UNKNOWN"]
    template = abstentions[0][1] if abstentions else None
    facts: list[str] = []
    for _, record, valid in votes:
        if valid:
            facts.extend(record["missing_facts"])
    if not (len(same) >= required or len(diff) >= required):
        facts.append(
            f"no categorical quorum: SAME={len(same)} DIFFERENT={len(diff)} required={required}"
        )
    own = [cand.source_slice.slice_id] if cand.source_slice is not None else []
    return AlignmentRecord(
        link_id=_link_id(cand),
        governing_ref=governing_ref,
        governing_slice_ids=[],
        candidate_ref=cand.candidate_id,
        document_id=cand.document_id,
        candidate_slice_ids=own,
        relation="UNKNOWN",
        activity=template["activity"] if template else "",
        object=template["object"] if template else "",
        trigger=template["trigger"] if template else "",
        population=template["population"] if template else "",
        population_overlap="UNKNOWN",
        source_function=template["source_function"] if template else "OTHER",
        rationale=template["rationale"] if template else "no categorical alignment established",
        missing_facts=_dedupe(facts),
        constraint_bindings=[],
    )


def _resolve_slices(
    record: dict[str, Any],
    cand: CandidateRecord,
    gov_default: str,
    cand_allowed: set[str],
    gov_allowed: set[str],
) -> dict[str, Any]:
    """Fill omitted slice ids with the system-owned candidate slice and the
    primary governing slice. A model that returns the correct relation but omits
    the single unambiguous selectable id must not have its vote voided; a model
    that cites an off-packet id is still rejected by ``_validate_vote``."""
    resolved = dict(record)
    if not resolved["candidate_slice_ids"] and cand_allowed:
        own = cand.source_slice.slice_id if cand.source_slice is not None else None
        if own in cand_allowed:
            resolved["candidate_slice_ids"] = [own]
    if not resolved["governing_slice_ids"] and gov_default:
        resolved["governing_slice_ids"] = [gov_default]
    if resolved["constraint_bindings"]:
        cand_ids = resolved["candidate_slice_ids"]
        gov_ids = resolved["governing_slice_ids"]
        bindings = []
        for binding in resolved["constraint_bindings"]:
            filled = dict(binding)
            if not filled.get("candidate_slice_id") and cand_ids:
                filled["candidate_slice_id"] = cand_ids[0]
            if not filled.get("governing_slice_id") and gov_ids:
                filled["governing_slice_id"] = gov_ids[0]
            bindings.append(filled)
        resolved["constraint_bindings"] = bindings
    return resolved


def _validate_vote(
    record: dict[str, Any], cand_allowed: set[str], gov_allowed: set[str]
) -> tuple[bool, str]:
    if record["relation"] == "UNKNOWN":
        return True, ""
    if not record["candidate_slice_ids"]:
        return False, "no candidate source slice selected"
    if not record["governing_slice_ids"]:
        return False, "no governing source slice selected"
    if any(i not in cand_allowed for i in record["candidate_slice_ids"]):
        return False, "off-packet candidate slice"
    if any(i not in gov_allowed for i in record["governing_slice_ids"]):
        return False, "off-packet governing slice"
    return True, ""


# ── constraint bindings ─────────────────────────────────────────────────────


def _bindings_from_winning(
    link_id: str,
    winning: list[tuple[str, dict[str, Any], bool]],
    gov_by_id: dict[str, SourceSlice],
    cand_allowed: set[str],
    cand_text: str = "",
) -> list[ConstraintBinding]:
    out: list[ConstraintBinding] = []
    seen: set[tuple[Any, ...]] = set()
    for _, record, _ in winning:
        for raw in record["constraint_bindings"]:
            binding = _validate_binding(
                link_id, f"{link_id}:b{len(out)}", raw, gov_by_id, cand_allowed, cand_text
            )
            if binding is None:
                continue
            key = (
                binding.governing_slice_id,
                binding.candidate_slice_id,
                binding.value,
                binding.unit,
                binding.constraint_kind,
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(binding)
    return out


def _validate_binding(
    link_id: str,
    binding_id: str,
    raw: dict[str, Any],
    gov_by_id: dict[str, SourceSlice],
    cand_allowed: set[str],
    cand_text: str = "",
) -> ConstraintBinding | None:
    gov_id = str(raw.get("governing_slice_id", ""))
    cand_id = str(raw.get("candidate_slice_id", ""))
    if gov_id not in gov_by_id or cand_id not in cand_allowed:
        return None
    kind = str(raw.get("constraint_kind", ""))
    if kind not in CONSTRAINT_KINDS:
        return None
    direction = str(raw.get("direction", ""))
    if not direction:
        return None
    governing_q = _quantity_dict(raw.get("governing_quantity"))
    internal_q = _quantity_dict(raw.get("internal_quantity"))
    if governing_q is None or internal_q is None:
        return None
    gov_text = gov_by_id[gov_id].text
    if not _text_has_quantity(gov_text, governing_q.value, governing_q.unit):
        return None
    # The internal operand must also be literally present in the candidate text;
    # the model selects operands, deterministic validation checks their literals.
    if cand_text and not _text_has_quantity(cand_text, internal_q.value, internal_q.unit):
        return None
    return ConstraintBinding(
        binding_id=binding_id,
        link_id=link_id,
        governing_slice_id=gov_id,
        candidate_slice_id=cand_id,
        value=internal_q.value,
        unit=internal_q.unit,
        qualifier=internal_q.qualifier,
        constraint_kind=kind,
        direction=direction,
        governing_quantity=_quantity_as_dict(governing_q),
        internal_quantity=_quantity_as_dict(internal_q),
        rationale=str(raw.get("rationale", "")),
    )


def _quantity_dict(value: Any) -> Quantity | None:
    if not isinstance(value, dict):
        return None
    raw_number = value.get("value")
    if raw_number is None:
        return None
    try:
        number = int(raw_number)
    except (TypeError, ValueError):
        return None
    unit = str(value.get("unit", "")).lower().rstrip("s")
    if unit not in _UNITS:
        return None
    qualifier = value.get("qualifier")
    norm = str(qualifier).lower() if qualifier else None
    if norm not in (None, "calendar", "business"):
        norm = None
    return Quantity(number, unit, norm)


def _quantity_as_dict(quantity: Quantity) -> dict[str, Any]:
    return {"value": quantity.value, "unit": quantity.unit, "qualifier": quantity.qualifier}


def _text_has_quantity(text: str, value: int, unit: str) -> bool:
    if not text:
        return False
    if not re.search(rf"(?<!\d){value}(?!\d)", text):
        return False
    return bool(re.search(rf"\b{re.escape(unit)}s?\b", text, re.I))


# ── internal-pair identity batch ────────────────────────────────────────────


def _align_pairs(
    request: AssessmentRequest,
    records: list[AlignmentRecord],
    pairs: list[Any],
    seats: list[dict[str, str]],
    fn: Any,
    required: int,
    gov_by_id: dict[str, SourceSlice],
) -> list[AlignmentRecord]:
    """Direct LEFT/RIGHT identity decisions for clauses already tied to the
    same governing duty. LEFT is always the pair's own left operand — the
    target governing text is never substituted for it."""
    same_by_id = {r.candidate_ref: r for r in records if r.relation == "SAME"}
    candidate_set = request.candidate_set
    out: list[AlignmentRecord] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        left_id = str(pair.get("left_id", ""))
        right_id = str(pair.get("right_id", ""))
        left, right = same_by_id.get(left_id), same_by_id.get(right_id)
        if left is None or right is None:
            # Only clauses already tied to the same duty get a direct decision.
            continue
        packet = _build_pair_packet(request, pair, left_id, right_id, candidate_set)
        user = json.dumps(packet, indent=2, ensure_ascii=False, default=str)
        same_votes = diff_votes = 0
        rationales: list[str] = []
        facts: list[str] = []
        for seat in seats:
            try:
                raw = fn(str(seat.get("model", "")), _ALIGNMENT_SYSTEM, user)
            except Exception:  # noqa: BLE001 - a malformed pair vote is not a crash
                continue
            relation, rationale, missing = _parse_pair(raw)
            if relation == "SAME":
                same_votes += 1
            elif relation == "DIFFERENT":
                diff_votes += 1
            if rationale:
                rationales.append(rationale)
            facts.extend(missing)
        relation = _pair_relation(same_votes, diff_votes, required)
        link_id = str(pair.get("pair_id", "")) or f"pair:{left_id}|{right_id}"
        out.append(
            AlignmentRecord(
                link_id=link_id,
                governing_ref=request.governing.ref if request.governing else "",
                governing_slice_ids=_dedupe(left.governing_slice_ids),
                candidate_ref=right_id,
                candidate_slice_ids=list(right.candidate_slice_ids),
                relation=relation,
                population_overlap="UNKNOWN" if relation == "UNKNOWN" else "OVERLAPPING",
                source_function=_OPERATIVE,
                rationale=rationales[0] if rationales else "",
                missing_facts=_dedupe(facts),
            )
        )
    return out


def _build_pair_packet(
    request: AssessmentRequest,
    pair: dict[str, Any],
    left_id: str,
    right_id: str,
    candidate_set: Any,
) -> dict[str, Any]:
    def operand(cid: str) -> dict[str, Any]:
        rec = candidate_set.by_id(cid) if candidate_set else None
        return {
            "candidate_id": cid,
            "text": rec.text if rec else "",
            "selectable_slice_ids": _candidate_slice_ids(rec) if rec else [],
        }

    return {
        "task": "internal_pair_identity",
        "requirement_id": request.requirement_id,
        "question": (
            "Do LEFT and RIGHT prescribe the same duty (SAME) or different duties "
            "(DIFFERENT)? Return one relation for the pair."
        ),
        "left": operand(left_id),
        "right": operand(right_id),
        "pair_note": pair.get("note", ""),
    }


def _parse_pair(raw: str) -> tuple[str, str, list[str]]:
    obj = _json_object(raw)
    if obj is None:
        return "UNKNOWN", "", ["pair response was not JSON"]
    inner = obj.get("pair")
    payload = inner if isinstance(inner, dict) else obj
    relation = str(payload.get("relation", "")).upper()
    if relation not in ALIGNMENT_RELATIONS:
        relation = "UNKNOWN"
    rationale = str(payload.get("rationale", ""))
    missing = _str_list(payload.get("missing_facts"))
    return relation, rationale, missing


def _pair_relation(same_votes: int, diff_votes: int, required: int) -> str:
    if same_votes >= required and same_votes > diff_votes:
        return "SAME"
    if diff_votes >= required and diff_votes > same_votes:
        return "DIFFERENT"
    return "UNKNOWN"


# ── small shared utilities ──────────────────────────────────────────────────


def _quorum(quorum: float, roster: int) -> int:
    # same rule as council.run_council — categorical agreement, no confidence
    return math.ceil((quorum * roster) - 1e-9)


def _governing_slice_ids(governing: GoverningBundle | None) -> list[str]:
    if governing is None:
        return []
    return [s.slice_id for s in governing.source_slices]


def _candidate_slice_ids(cand: CandidateRecord | None) -> list[str]:
    if cand is None or cand.source_slice is None:
        return []
    return [cand.source_slice.slice_id]


def _scope_dict(scope: Any) -> dict[str, Any]:
    if scope is None:
        return {}
    return {
        "impact_present": sorted(getattr(scope, "impact_present", set()) or set()),
        "associated_present": sorted(getattr(scope, "associated_present", set()) or set()),
        "has_erc": getattr(scope, "has_erc", None),
        "has_control_center": getattr(scope, "has_control_center", None),
        "declared": bool(getattr(scope, "is_declared", False)),
        "confirmed": bool(getattr(scope, "is_confirmed", False)),
        "conflicted": bool(getattr(scope, "conflicted", False)),
    }


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _link_id(cand: CandidateRecord) -> str:
    """The stable link key — the candidate id. The human-readable document name
    travels on the record's ``document_id`` and is what the council allowlist
    exposes as the citable ref (see ``gate._build_aligned_candidate``)."""
    return cand.candidate_id


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(stripped.splitlines()[1:])
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(stripped[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _default_seat_fn() -> Any:
    return _ollama_alignment_seat


def _ollama_alignment_seat(model: str, system: str, user: str) -> str:
    """The alignment transport: one JSON object per candidate plus bindings, so
    it needs far more output budget than a single council verdict. Mirrors the
    council's Ollama transport (think suppressed, temperature 0, JSON format)
    with a larger ``num_predict``; the council's own transport is untouched."""
    import urllib.request

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 4096},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:  # noqa: S310 - fixed localhost
        return (json.load(response).get("message") or {}).get("content", "") or ""
