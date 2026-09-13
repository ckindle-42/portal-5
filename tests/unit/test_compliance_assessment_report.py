"""Workstream C — the bounded source-linked explanation (IMPLEMENTATION_BRIEF §4/§5).

The report makes exactly one call with its own system prompt, preserves the
council decision and cannot overturn it, and rejects off-packet or
model-reconstructed evidence. All calls are injected fakes.
"""

from __future__ import annotations

import json
from typing import Any

from portal.modules.compliance.core.assessment_report import explain
from portal.modules.compliance.core.council import _SEAT_SYSTEM
from portal.modules.compliance.core.determination import (
    AlignmentRecord,
    AlignmentResult,
    AssessmentContext,
    AssessmentRequest,
    CorpusSnapshot,
    GoverningBundle,
    SourceSlice,
)

SEATS = [
    {"id": "s1", "label": "a", "model": "m1"},
    {"id": "s2", "label": "b", "model": "m2"},
    {"id": "s3", "label": "c", "model": "m3"},
]

GOV = SourceSlice(
    slice_id="gov-1",
    ref="register:Part2.2",
    document_id="reg",
    revision_hash="h",
    chunk_id="reg-2.2",
    text="Evaluate patches at least once every 35 calendar days.",
    role="governing",
)
CATALOG: dict[str, dict[str, Any]] = {
    "gov-1": {"text": GOV.text, "role": "governing"},
    "cand-a": {"text": "SMEs evaluate patches every 35 calendar days.", "role": "candidate"},
    "cand-b": {"text": "The patch-source inventory is retained for 3 years.", "role": "candidate"},
}


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2",
        governing=GoverningBundle(
            ref="CIP-007-6 R2 Part 2.2",
            part_text="Each Responsible Entity shall evaluate patches.",
            lead_in="Each Responsible Entity shall implement:",
            source_slices=[GOV],
        ),
        snapshot=CorpusSnapshot(snapshot_id="snap", kb_id="kb", completeness="UNKNOWN"),
    )


def _alignment() -> AlignmentResult:
    return AlignmentResult(
        part_ref="CIP-007-6 R2 Part 2.2",
        records=[
            AlignmentRecord(
                link_id="cand-a",
                governing_ref="CIP-007-6 R2 Part 2.2",
                governing_slice_ids=["gov-1"],
                candidate_ref="cand-a",
                candidate_slice_ids=["cand-a"],
                relation="SAME",
            ),
            AlignmentRecord(
                link_id="cand-b",
                governing_ref="CIP-007-6 R2 Part 2.2",
                governing_slice_ids=["gov-1"],
                candidate_ref="cand-b",
                candidate_slice_ids=["cand-b"],
                relation="SAME",
            ),
        ],
        valid=True,
    )


def _council(decision: str = "PARTIAL") -> dict[str, Any]:
    return {
        "determination": decision,
        "dissent": ["s2"],
        "opinions": [
            {"seat_id": "s1", "valid": True, "determination": decision, "cited_refs": ["cand-a"]},
            {
                "seat_id": "s2",
                "valid": True,
                "determination": "SUPPORTED",
                "cited_refs": ["cand-a"],
            },
            {"seat_id": "s3", "valid": True, "determination": decision, "cited_refs": ["cand-a"]},
        ],
        "citations": ["cand-a"],
    }


def _covered(internal: str = "cand-a", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "commitment": "evaluate patches for applicability",
        "governing_slice_ids": ["gov-1"],
        "internal_slice_ids": [internal],
    }
    entry.update(extra or {})
    return entry


def _gap(**overrides: Any) -> dict[str, Any]:
    entry = {
        "gap_id": "gap-1",
        "kind": "WEAKER_COMMITMENT",
        "missing_commitment": "35-day cadence",
        "governing_slice_ids": ["gov-1"],
        "internal_counterevidence_slice_ids": ["cand-a"],
    }
    entry.update(overrides)
    return entry


def _report(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "documentary_coverage": "PARTIAL",
        "covered": [_covered()],
        "gaps": [_gap()],
        "uncertainties": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _context(payload: str, calls: list[tuple[str, str, str]]) -> AssessmentContext:
    def transport(model: str, system: str, user: str) -> str:
        calls.append((model, system, user))
        return payload

    return AssessmentContext(
        seats=SEATS, quorum=0.66, seat_fn=transport, report_model="report-model"
    )


def test_consistent_partial_explanation_makes_one_separate_call():
    calls: list[tuple[str, str, str]] = []
    explanation = explain(
        _request(), _council("PARTIAL"), _alignment(), CATALOG, _context(_report(), calls)
    )
    assert explanation.valid
    assert explanation.documentary_coverage == "PARTIAL"
    assert explanation.covered and explanation.gaps
    assert len(calls) == 1
    assert calls[0][0] == "report-model"
    assert calls[0][1] != _SEAT_SYSTEM
    assert "reporting analyst" in calls[0][1]


def test_report_cannot_overturn_the_council_decision_to_full():
    calls: list[tuple[str, str, str]] = []
    explanation = explain(
        _request(),
        _council("PARTIAL"),
        _alignment(),
        CATALOG,
        _context(_report(documentary_coverage="FULL"), calls),
    )
    assert explanation.documentary_coverage == "UNRESOLVED"
    assert explanation.valid is False
    assert explanation.raw["council_decision"] == "PARTIAL"


def test_partial_requires_covered_and_grounded_gaps():
    calls: list[tuple[str, str, str]] = []
    explanation = explain(
        _request(),
        _council("PARTIAL"),
        _alignment(),
        CATALOG,
        _context(_report(covered=[]), calls),
    )
    assert explanation.valid is False
    assert explanation.documentary_coverage == "UNRESOLVED"


def test_none_with_absence_boundary_proof_is_valid():
    calls: list[tuple[str, str, str]] = []
    payload = _report(
        documentary_coverage="NONE",
        covered=[],
        gaps=[
            _gap(kind="OMISSION", boundary_proof_id="bp-1", internal_counterevidence_slice_ids=[])
        ],
    )
    explanation = explain(
        _request(), _council("ABSENT"), _alignment(), CATALOG, _context(payload, calls)
    )
    assert explanation.valid
    assert explanation.documentary_coverage == "NONE"


def test_none_without_a_boundary_basis_is_unresolved():
    calls: list[tuple[str, str, str]] = []
    payload = _report(
        documentary_coverage="NONE",
        covered=[],
        gaps=[_gap(kind="OMISSION", internal_counterevidence_slice_ids=[])],
    )
    explanation = explain(
        _request(), _council("ABSENT"), _alignment(), CATALOG, _context(payload, calls)
    )
    assert explanation.valid is False
    assert explanation.documentary_coverage == "UNRESOLVED"


def test_excluded_source_cannot_supply_the_support_witness():
    # cand-b has a SAME link, but no decision-agreeing opinion cites it — it is
    # not part of the consensus operative set and cannot be rehabilitated.
    calls: list[tuple[str, str, str]] = []
    explanation = explain(
        _request(),
        _council("PARTIAL"),
        _alignment(),
        CATALOG,
        _context(_report(covered=[_covered("cand-b")]), calls),
    )
    assert explanation.valid is False


def test_model_reconstructed_quote_is_rejected():
    calls: list[tuple[str, str, str]] = []
    forged = _covered(extra={"text": "a quote the model wrote itself"})
    explanation = explain(
        _request(),
        _council("PARTIAL"),
        _alignment(),
        CATALOG,
        _context(_report(covered=[forged]), calls),
    )
    assert explanation.valid is False
    assert explanation.documentary_coverage == "UNRESOLVED"


def test_missing_report_shape_is_unresolved():
    calls: list[tuple[str, str, str]] = []
    explanation = explain(
        _request(), _council("PARTIAL"), _alignment(), CATALOG, _context("not json", calls)
    )
    assert explanation.valid is False
    assert explanation.documentary_coverage == "UNRESOLVED"
