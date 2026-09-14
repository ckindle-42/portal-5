"""Source-grounded duty identity and operand selection before arithmetic.

Categorical quorum determines SAME/DIFFERENT; no lexical fallback or prior
judgment enters the reader. Invalid selections remain explicit uncertainty.
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
    "Read duty identity, never satisfaction or confidence. Use the full Part, lead-in, "
    "definitions, references, scope and candidate context.\n"
    "SAME: the clause implements the governing activity/object for an overlapping "
    "population and compatible triggering event. Missing conditions, weaker wording "
    "or changed deadlines remain SAME. DIFFERENT: the text establishes another duty, "
    "disjoint population or non-operative material. Otherwise UNKNOWN with missing facts.\n"
    "Distinguish the event creating a duty from its frequency/completion deadline. "
    "A changed or missing interval does not create a different duty. Resolve 'that "
    "evaluation' from the other candidate clauses; a cadence clause can implement "
    "an activity stated elsewhere. Select each candidate's own source slice.\n"
    "Use source meaning, never keyword overlap, filenames, folders or numeric equality. "
    "Select supplied slice IDs, never reconstructed quotes or character offsets.\n"
    "For clause_alignment, emit exactly one record per candidate using response_contract. "
    "Bind every matched quantity for a SAME duty to the governing and candidate slices "
    "that actually contain its literal digit, unit and qualifier. A reference supplying "
    "context need not contain the numeric operand. Missing/ambiguous operands mean UNKNOWN. "
    "Use empty constraint_bindings only without a quantity for the matched duty.\n"
    "max_interval bounds delay between recurrences or time to finish an action. "
    "min_retention bounds how long records/material must be kept. 'At least once every' "
    "is max_interval. Direction must equal constraint_kind.\n"
    "For internal_pair_identity, compare only LEFT and RIGHT, returning relation, "
    "rationale and missing_facts instead of candidate records."
)


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _quantity_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "value": {"type": "integer"},
            "unit": {"type": "string", "enum": list(_UNITS)},
            "qualifier": {"type": ["string", "null"], "enum": ["calendar", "business", None]},
        }
    )


def _response_contract(task: str = "clause_alignment") -> dict[str, Any]:
    strings: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    relation = {"type": "string", "enum": list(ALIGNMENT_RELATIONS)}
    if task == "internal_pair_identity":
        return _object_schema(
            {"relation": relation, "rationale": {"type": "string"}, "missing_facts": strings}
        )
    binding: dict[str, Any] = {
        "governing_slice_id": {"type": "string"},
        "candidate_slice_id": {"type": "string"},
        "constraint_kind": {"type": "string", "enum": list(CONSTRAINT_KINDS)},
        "direction": {"type": "string", "enum": list(CONSTRAINT_KINDS)},
        "governing_quantity": _quantity_schema(),
        "internal_quantity": _quantity_schema(),
        "rationale": {"type": "string"},
    }
    record: dict[str, Any] = {
        key: {"type": "string"}
        for key in ("candidate_id", "activity", "object", "trigger", "population", "rationale")
    }
    record.update(
        relation=relation,
        population_overlap={"type": "string", "enum": list(POPULATION_OVERLAPS)},
        source_function={"type": "string", "enum": list(SOURCE_FUNCTIONS)},
        missing_facts=strings,
        governing_slice_ids=strings,
        candidate_slice_ids=strings,
        constraint_bindings={"type": "array", "items": _object_schema(binding)},
    )
    return _object_schema({"records": {"type": "array", "items": _object_schema(record)}})


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
        "response_contract": _response_contract(),
        "governing": {
            "ref": governing.ref if governing else request.requirement_id,
            "part_text": governing.part_text if governing else "",
            "lead_in": governing.lead_in if governing else "",
            "definitions": governing.definitions if governing else [],
            "references": governing.references if governing else [],
            "selectable_slice_ids": _governing_slice_ids(governing),
            "source_slices": [
                {"slice_id": s.slice_id, "ref": s.ref, "role": s.role, "text": s.text}
                for s in (governing.source_slices if governing else [])
            ],
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
        valid, reason = _validate_vote(record, cand_allowed, gov_allowed)
        if valid and record["relation"] == "SAME":
            for raw in record["constraint_bindings"]:
                if (
                    _validate_binding(
                        cand.candidate_id, "", raw, gov_by_id, cand_allowed, cand.text
                    )
                    is None
                ):
                    valid, reason = False, f"seat {seat_id}: invalid numeric binding"
                    break
        if not valid:
            record["missing_facts"] = [*record["missing_facts"], reason]
        votes.append((seat_id, record, valid))

    same = [v for v in votes if v[2] and v[1]["relation"] == "SAME"]
    diff = [v for v in votes if v[2] and v[1]["relation"] == "DIFFERENT"]
    if len(same) >= required and len(same) > len(diff):
        return _decided_record(governing_ref, cand, "SAME", same, gov_by_id, cand_allowed, required)
    if len(diff) >= required and len(diff) > len(same):
        return _decided_record(
            governing_ref, cand, "DIFFERENT", diff, gov_by_id, cand_allowed, required
        )
    return _unknown_record(governing_ref, cand, votes, same, diff, required)


def _decided_record(
    governing_ref: str,
    cand: CandidateRecord,
    relation: str,
    winning: list[tuple[str, dict[str, Any], bool]],
    gov_by_id: dict[str, SourceSlice],
    cand_allowed: set[str],
    required: int,
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
    link_id = _link_id(cand)
    cand_text = cand.source_slice.text if cand.source_slice is not None else cand.text
    missing_facts = _dedupe(template["missing_facts"])
    try:
        bindings = _bindings_from_winning(
            link_id, winning, gov_by_id, cand_allowed, cand_text, required
        )
    except ValueError as exc:
        relation = "UNKNOWN"
        bindings = []
        missing_facts.append(str(exc))
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
        missing_facts=missing_facts,
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
    for _, record, _ in votes:
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
    if record["relation"] == "SAME" and record["population_overlap"] != "OVERLAPPING":
        return False, "SAME requires source-grounded overlapping populations"
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
    required: int = 1,
) -> list[ConstraintBinding]:
    bindings: dict[str, ConstraintBinding] = {}
    supporters: dict[str, set[str]] = {}
    for seat_id, record, _ in winning:
        for raw in record["constraint_bindings"]:
            binding = _validate_binding(link_id, "", raw, gov_by_id, cand_allowed, cand_text)
            if binding is None:
                raise ValueError(f"seat {seat_id}: invalid numeric binding for {link_id}")
            identity = {
                k: raw.get(k)
                for k in (
                    "governing_slice_id",
                    "candidate_slice_id",
                    "governing_quantity",
                    "internal_quantity",
                    "constraint_kind",
                    "direction",
                )
            }
            key = json.dumps(identity, sort_keys=True)
            bindings[key] = binding
            supporters.setdefault(key, set()).add(seat_id)
    accepted = [binding for key, binding in bindings.items() if len(supporters[key]) >= required]
    if bindings and not accepted:
        raise ValueError("no quorum on source-grounded numeric operands and constraint kind")
    for index, binding in enumerate(accepted):
        binding.binding_id = f"{link_id}:b{index}"
    return accepted


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
    if direction != kind:
        return None
    governing_q = _quantity_dict(raw.get("governing_quantity"))
    internal_q = _quantity_dict(raw.get("internal_quantity"))
    if governing_q is None or internal_q is None:
        return None
    gov_text = gov_by_id[gov_id].text
    if not _text_has_quantity(gov_text, governing_q.value, governing_q.unit, governing_q.qualifier):
        return None
    # The internal operand must also be literally present in the candidate text;
    # the model selects operands, deterministic validation checks their literals.
    if cand_text and not _text_has_quantity(
        cand_text, internal_q.value, internal_q.unit, internal_q.qualifier
    ):
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


def _text_has_quantity(text: str, value: int, unit: str, qualifier: str | None = None) -> bool:
    pattern = rf"(?<![\d.]){value}(?![\d.])\)?\s+(?:(calendar|business)\s+)?{re.escape(unit)}s?\b"
    return any((match.group(1) or None) == qualifier for match in re.finditer(pattern, text, re.I))


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

    packet = json.loads(user)
    count = len(packet.get("candidates", []))
    # One record per supplied source, with bindings and exact ids. The real
    # corpus can supply fifteen records; a council-sized cap truncates them.
    output_budget = min(8192, max(4096, 512 * count))
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": _response_contract(packet.get("task", "clause_alignment")),
        "think": False,
        "options": {"temperature": 0.0, "num_predict": output_budget},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:  # noqa: S310 - fixed localhost
        return (json.load(response).get("message") or {}).get("content", "") or ""
