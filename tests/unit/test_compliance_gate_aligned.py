"""Workstream C — the aligned gate (IMPLEMENTATION_BRIEF §4/§5).

Pure unit tests: no model calls. They pin the packet arithmetic, the
authoritative governing text (R2.4 must never collapse to "or delegate."), the
lead-in actor, and the single-constraint scalar rule.
"""

from __future__ import annotations

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.determination import (
    AlignmentRecord,
    AlignmentResult,
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    ConstraintBinding,
    CorpusSnapshot,
    GoverningBundle,
    SourceSlice,
)
from portal.modules.compliance.core.gate import compare_aligned, run_aligned_gate

PART_TEXT = (
    "Each Responsible Entity shall implement each of the following Parts: "
    "Part 2.4: For every mitigation plan created or revised under Part 2.3, "
    "SMEs shall implement the plan within its specified timeframe. A revision "
    "to such a plan or an extension of its timeframe is permitted only when "
    "approved by the CIP Senior Manager or delegate."
)
LEAD_IN = "Each Responsible Entity shall implement each of the following Parts:"
GOV_SLICE = SourceSlice(
    slice_id="gov-1",
    ref="register:Part2.4",
    document_id="reg",
    revision_hash="h",
    chunk_id="reg-2.4",
    text="SMEs shall implement the plan within 35 calendar days.",
    role="governing",
)


def _candidate(candidate_id: str, text: str) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        document_id="proc",
        chunk_id=f"ch-{candidate_id}",
        text=text,
        source_slice=SourceSlice(
            slice_id=candidate_id,
            ref=f"proc#{candidate_id}",
            document_id="proc",
            revision_hash="h",
            chunk_id=f"ch-{candidate_id}",
            text=text,
            role="candidate",
        ),
    )


def _binding(link_id: str, value: int = 35, kind: str = "max_interval") -> ConstraintBinding:
    quantity = {"value": value, "unit": "day", "qualifier": "calendar"}
    return ConstraintBinding(
        binding_id=f"{link_id}:b0",
        link_id=link_id,
        governing_slice_id="gov-1",
        candidate_slice_id=link_id,
        value=value,
        unit="day",
        qualifier="calendar",
        constraint_kind=kind,
        direction=kind,
        governing_quantity=quantity,
        internal_quantity=quantity,
    )


def _link(
    link_id: str,
    relation: str = "SAME",
    overlap: str = "OVERLAPPING",
    source_function: str = "OPERATIVE_COMMITMENT",
    bindings: list[ConstraintBinding] | None = None,
) -> AlignmentRecord:
    return AlignmentRecord(
        link_id=link_id,
        governing_ref="CIP-007-6 R2 Part 2.4",
        governing_slice_ids=["gov-1"],
        candidate_ref=link_id,
        candidate_slice_ids=[link_id],
        relation=relation,
        population_overlap=overlap,
        source_function=source_function,
        constraint_bindings=bindings or [],
    )


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2",
        scope=AssetScope(
            impact_present={"high", "medium"},
            associated_present={"bcs", "pacs"},
            declared_by="operator:test",
        ),
        governing=GoverningBundle(
            ref="CIP-007-6 R2 Part 2.4",
            part_text=PART_TEXT,
            lead_in=LEAD_IN,
            source_slices=[GOV_SLICE],
            fingerprint="govfp",
            meta=[{"applicable_systems": "High Impact BES Cyber Systems"}],
        ),
        snapshot=CorpusSnapshot(snapshot_id="snap", kb_id="kb", completeness="COMPLETE"),
        candidate_set=CandidateSet(
            records=[
                _candidate("cand-a", "SMEs implement the mitigation plan within its timeframe."),
                _candidate("cand-b", "The supplier list is retained for three years."),
                _candidate("cand-c", "Contents: mitigation plan; implementation timeframe."),
            ]
        ),
    )


# ── compare_aligned ─────────────────────────────────────────────────────────


def test_compare_aligned_equivalent_and_stricter():
    link = _link("cand-a", bindings=[])
    assert compare_aligned(_binding("cand-a", 35), link)[0] == "EQUIVALENT"

    stricter = ConstraintBinding(
        binding_id="cand-a:b0",
        link_id="cand-a",
        governing_slice_id="gov-1",
        candidate_slice_id="cand-a",
        value=30,
        unit="day",
        qualifier="calendar",
        constraint_kind="max_interval",
        direction="max_interval",
        governing_quantity={"value": 35, "unit": "day", "qualifier": "calendar"},
        internal_quantity={"value": 30, "unit": "day", "qualifier": "calendar"},
    )
    assert compare_aligned(stricter, link)[0] == "MORE_RESTRICTIVE"


def test_compare_aligned_rejects_non_same():
    binding = _binding("cand-a")
    assert compare_aligned(binding, _link("cand-a", relation="DIFFERENT"))[0] == "INCOMPARABLE"
    assert compare_aligned(binding, _link("cand-a", relation="UNKNOWN"))[0] == "INCOMPARABLE"


def test_compare_aligned_rejects_disjoint_population():
    binding = _binding("cand-a")
    result, reason = compare_aligned(binding, _link("cand-a", overlap="DISJOINT"))
    assert result == "INCOMPARABLE"
    assert "disjoint" in reason.lower()


def test_compare_aligned_rejects_operand_not_cited_by_the_link():
    binding = _binding("cand-a")
    link = _link("cand-a")
    link.candidate_slice_ids = ["some-other-slice"]
    assert compare_aligned(binding, link)[0] == "INCOMPARABLE"


# ── run_aligned_gate ────────────────────────────────────────────────────────


def test_packet_uses_full_governing_text_and_lead_in_actor():
    alignment = AlignmentResult(
        part_ref="CIP-007-6 R2 Part 2.4",
        records=[
            _link("cand-a", bindings=[_binding("cand-a")]),
            _link("cand-b", relation="DIFFERENT", source_function="OTHER"),
            _link("cand-c", source_function="CONTENTS"),
        ],
        valid=True,
    )
    gate = run_aligned_gate(_request(), alignment, AssessmentContext())
    packet = gate.to_council_packet()
    unit = packet["governing_unit"]

    assert gate.applicability == "APPLIES"
    assert not gate.gated_out
    assert unit["verbatim_text"] == PART_TEXT
    assert unit["constraint"]["text"] == PART_TEXT
    assert unit["constraint"]["text"] != "or delegate."
    assert "Part 2.3" in unit["verbatim_text"]
    assert unit["subject"]["text"] == "Responsible Entity"
    assert "delegate" not in unit["subject"]["text"].lower()

    candidate_ids = {c["commitment_id"] for c in packet["candidates"]}
    # commitment_id carries the document name plus the stable candidate id
    assert len(candidate_ids) == 1 and "cand-a" in next(iter(candidate_ids))
    excluded_refs = {entry["candidate_ref"] for entry in gate.excluded}
    assert "cand-b" in excluded_refs and "cand-c" in excluded_refs
    assert gate.governing_fingerprint == "govfp"
    assert gate.acquisition_completeness == "COMPLETE"


def test_single_aligned_constraint_populates_the_scalar():
    alignment = AlignmentResult(
        part_ref="CIP-007-6 R2 Part 2.4",
        records=[_link("cand-a", bindings=[_binding("cand-a")])],
        valid=True,
    )
    gate = run_aligned_gate(_request(), alignment, AssessmentContext())
    packet = gate.to_council_packet()
    assert packet["candidates"][0]["quantity_outcome"] == "EQUIVALENT"
    assert len(gate.binding_outcomes) == 1


def test_multiple_constraints_leave_the_scalar_empty():
    alignment = AlignmentResult(
        part_ref="CIP-007-6 R2 Part 2.4",
        records=[
            _link("cand-a", bindings=[_binding("cand-a")]),
            _link("cand-b", bindings=[_binding("cand-b", value=40)]),
        ],
        valid=True,
    )
    # cand-b is SAME here because both records are operative commitments.
    gate = run_aligned_gate(_request(), alignment, AssessmentContext())
    packet = gate.to_council_packet()
    assert all(c["quantity_outcome"] == "" for c in packet["candidates"])
    assert len(gate.binding_outcomes) == 2
