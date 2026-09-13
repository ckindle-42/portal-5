"""Workstream C — the narrow semantic alignment reader (IMPLEMENTATION_BRIEF §4).

All model calls are injected fakes returning deterministic JSON, so the suite
is network-free. The reader is sealed: no prior determination, gold label or
approved verdict ever reaches a seat.
"""

from __future__ import annotations

import json
from typing import Any

from portal.modules.compliance.core.council import _SEAT_SYSTEM
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    GoverningBundle,
    SourceSlice,
)
from portal.modules.compliance.core.obligation_alignment import align_part

SEATS = [
    {"id": "s1", "label": "a", "model": "m1"},
    {"id": "s2", "label": "b", "model": "m2"},
    {"id": "s3", "label": "c", "model": "m3"},
]

GOV_TEXT = "Evaluate security patches for applicability at least once every 35 calendar days."
CAND_TEXT = "SMEs shall evaluate patch applicability once every 35 calendar days."


def _governing() -> GoverningBundle:
    return GoverningBundle(
        ref="CIP-007-6 R2 Part 2.2",
        part_text="Each Responsible Entity shall evaluate security patches for applicability.",
        lead_in="Each Responsible Entity shall implement each of the following Parts:",
        source_slices=[
            SourceSlice(
                slice_id="gov-1",
                ref="register:Part2.2",
                document_id="reg",
                revision_hash="h",
                chunk_id="reg-2.2",
                text=GOV_TEXT,
                role="governing",
            )
        ],
        fingerprint="govfp",
    )


def _candidate(candidate_id: str, text: str) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        document_id="proc",
        chunk_id=f"chunk-{candidate_id}",
        text=text,
        source_slice=SourceSlice(
            slice_id=f"cand-{candidate_id}",
            ref=f"proc#{candidate_id}",
            document_id="proc",
            revision_hash="h",
            chunk_id=f"chunk-{candidate_id}",
            text=text,
            role="candidate",
        ),
    )


def _request(*candidates: CandidateRecord) -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2",
        governing=_governing(),
        snapshot=None,
        candidate_set=CandidateSet(records=list(candidates)),
    )


def _record(candidate_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "relation": entry["relation"],
        "governing_slice_ids": entry.get("gov", ["gov-1"]),
        "candidate_slice_ids": entry.get("cand", [f"cand-{candidate_id}"]),
        "activity": entry.get("activity", "evaluate patches"),
        "object": entry.get("object", "security patches"),
        "trigger": entry.get("trigger", ""),
        "population": entry.get("population", ""),
        "population_overlap": entry.get("overlap", "OVERLAPPING"),
        "source_function": entry.get("source_function", "OPERATIVE_COMMITMENT"),
        "rationale": entry.get("rationale", ""),
        "missing_facts": entry.get("missing_facts", []),
        "constraint_bindings": entry.get("bindings", []),
    }


def _seat_response(spec: dict[str, dict[str, Any]]) -> str:
    return json.dumps({"records": [_record(cid, entry) for cid, entry in spec.items()]})


def _context(responses: dict[str, str], calls: list[tuple[str, str]]) -> AssessmentContext:
    def fn(model: str, system: str, user: str) -> str:
        calls.append((system, user))
        return responses[model]

    return AssessmentContext(seats=SEATS, quorum=0.66, seat_fn=fn)


def test_alignment_preserves_every_candidate():
    request = _request(
        _candidate("a", CAND_TEXT),
        _candidate("b", "The supplier list is retained for three years."),
        _candidate("c", "Review the supply-chain plan every 15 calendar months."),
    )
    calls: list[tuple[str, str]] = []
    responses = {
        "m1": _seat_response(
            {
                "a": {"relation": "SAME"},
                "b": {"relation": "DIFFERENT"},
                "c": {"relation": "DIFFERENT"},
            }
        ),
        "m2": _seat_response(
            {
                "a": {"relation": "SAME"},
                "b": {"relation": "DIFFERENT"},
                "c": {"relation": "DIFFERENT"},
            }
        ),
        "m3": _seat_response(
            {
                "a": {"relation": "SAME"},
                "b": {"relation": "DIFFERENT"},
                "c": {"relation": "DIFFERENT"},
            }
        ),
    }
    result = align_part(request, _context(responses, calls))
    assert result.valid
    assert {r.candidate_ref for r in result.records} == {"a", "b", "c"}
    assert [r.relation for r in result.records] == ["SAME", "DIFFERENT", "DIFFERENT"]


def test_tie_is_unknown_with_no_arithmetic():
    request = _request(_candidate("a", CAND_TEXT))
    calls: list[tuple[str, str]] = []
    responses = {
        "m1": _seat_response({"a": {"relation": "SAME"}}),
        "m2": _seat_response({"a": {"relation": "DIFFERENT"}}),
        "m3": _seat_response({"a": {"relation": "UNKNOWN", "missing_facts": ["ambiguous actor"]}}),
    }
    result = align_part(request, _context(responses, calls))
    assert result.valid
    assert len(result.records) == 1
    record = result.records[0]
    assert record.relation == "UNKNOWN"
    assert not record.constraint_bindings
    assert any("quorum" in fact for fact in record.missing_facts)


def test_same_and_different_separate_unrelated_duties():
    request = _request(
        _candidate("patch", CAND_TEXT),
        _candidate("va", "Vulnerability assessments shall be performed every 15 months."),
    )
    calls: list[tuple[str, str]] = []
    spec = {"patch": {"relation": "SAME"}, "va": {"relation": "DIFFERENT"}}
    responses = {m: _seat_response(spec) for m in ("m1", "m2", "m3")}
    result = align_part(request, _context(responses, calls))
    by_ref = {r.candidate_ref: r for r in result.records}
    assert by_ref["patch"].relation == "SAME"
    assert by_ref["patch"].governing_slice_ids == ["gov-1"]
    assert by_ref["patch"].candidate_slice_ids == ["cand-patch"]
    assert by_ref["va"].relation == "DIFFERENT"


def _binding(value: int, unit: str = "day", qualifier: str = "calendar") -> dict[str, Any]:
    quantity = {"value": value, "unit": unit, "qualifier": qualifier}
    return {
        "governing_slice_id": "gov-1",
        "candidate_slice_id": "cand-a",
        "value": value,
        "unit": unit,
        "qualifier": qualifier,
        "constraint_kind": "max_interval",
        "direction": "max_interval",
        "governing_quantity": quantity,
        "internal_quantity": quantity,
        "rationale": "same 35-day cadence",
    }


def test_binding_uses_the_literal_digit_in_parentheses():
    text = "Complete the evaluation at least once every thirty-five (35) calendar days."
    request = _request(_candidate("a", text))
    calls: list[tuple[str, str]] = []
    spec = {"a": {"relation": "SAME", "bindings": [_binding(35)]}}
    responses = {m: _seat_response(spec) for m in ("m1", "m2", "m3")}
    result = align_part(request, _context(responses, calls))
    bindings = result.records[0].constraint_bindings
    assert len(bindings) == 1
    assert bindings[0].value == 35
    assert bindings[0].unit == "day"
    assert bindings[0].qualifier == "calendar"


def test_binding_with_absent_literal_is_dropped_not_retried():
    text = "Complete the evaluation at least once every thirty-five (35) calendar days."
    request = _request(_candidate("a", text))
    calls: list[tuple[str, str]] = []
    spec = {"a": {"relation": "SAME", "bindings": [_binding(40)]}}
    responses = {m: _seat_response(spec) for m in ("m1", "m2", "m3")}
    result = align_part(request, _context(responses, calls))
    record = result.records[0]
    assert record.relation == "SAME"
    assert record.constraint_bindings == []


def test_reader_never_receives_a_prior_or_gold_or_approved_verdict():
    request = _request(_candidate("a", CAND_TEXT))
    calls: list[tuple[str, str]] = []
    spec = {"a": {"relation": "SAME"}}
    responses = {m: _seat_response(spec) for m in ("m1", "m2", "m3")}
    align_part(request, _context(responses, calls))
    banned = ("prior_determination", "gold", "approved", "verdict", "supported", "coverage")
    for system, user in calls:
        assert system != _SEAT_SYSTEM
        blob = f"{system}\n{user}".lower()
        for token in banned:
            assert token not in blob, f"reader saw forbidden token {token!r}"


def test_invalid_json_fails_the_alignment():
    request = _request(_candidate("a", CAND_TEXT))
    calls: list[tuple[str, str]] = []
    responses = dict.fromkeys(("m1", "m2", "m3"), "not a json object")
    result = align_part(request, _context(responses, calls))
    assert result.valid is False
    assert "JSON" in result.failure


def test_omitted_candidate_fails_the_alignment():
    request = _request(_candidate("a", CAND_TEXT), _candidate("b", "unrelated"))
    calls: list[tuple[str, str]] = []
    partial = json.dumps({"records": [_record("a", {"relation": "SAME"})]})
    responses = dict.fromkeys(("m1", "m2", "m3"), partial)
    result = align_part(request, _context(responses, calls))
    assert result.valid is False
    assert "omitted" in result.failure
