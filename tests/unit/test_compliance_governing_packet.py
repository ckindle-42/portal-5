"""The governing bundle's Measures / Technical Basis reach the reader as
labelled context — never as duties (foundation P3, program lesson L13).

These tests run against the real pinned CIP-007-6 revision and exercise the
packet contract plus the verifier's context-citation guard.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.determination import (
    AssessmentRequest,
    CandidateSet,
    CorpusSnapshot,
    GoverningBundle,
    SourceSlice,
)
from portal.modules.compliance.core.reading import build_reading_packet, verify_judgment

_SRC_PDF = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "portal/modules/compliance/data/cip_pdfs/cip-007-6.pdf"
)


def _governing() -> GoverningBundle:
    from portal.modules.compliance.core.assessment_source import resolve_governing_bundle

    return resolve_governing_bundle("CIP-007-6 R2 Part 2.3")


needs = pytest.mark.skipif(not _SRC_PDF.is_file(), reason="NERC CIP PDF corpus not fetched locally")


@needs
def test_bundle_carries_measures_and_technical_basis():
    g = _governing()
    assert g.readiness["ready"] is True
    assert len(g.measures) == 2
    assert all(m["role"] == "MEASURE" for m in g.measures)
    assert g.technical_basis
    assert all(t["role"] == "TECHNICAL_BASIS" for t in g.technical_basis)
    assert "High Impact BES Cyber Systems" in g.applicable_systems
    assert g.definitions_disposition == "external_glossary"


def _request(g: GoverningBundle) -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id=g.ref,
        governing=g,
        candidate_set=CandidateSet(),
        snapshot=CorpusSnapshot(snapshot_id="s", kb_id="kb"),
    )


@needs
def test_packet_carries_context_blocks_outside_selectable_slices():
    packet = build_reading_packet(_request(_governing()))
    gov = packet["governing"]
    assert gov["measures"], "Measures must reach the reader (was a dead '' placeholder)"
    assert gov["technical_basis"]
    for block, role in ((gov["measures"], "MEASURE"), (gov["technical_basis"], "TECHNICAL_BASIS")):
        for entry in block:
            assert entry["role"] == role
            assert "not selectable as duty evidence" in entry["note"]
    ctx_ids = {e["slice_id"] for e in gov["measures"] + gov["technical_basis"]}
    assert ctx_ids.isdisjoint(set(gov["selectable_slice_ids"]))
    # every measure names its non-duty status, so no model reads it as a duty
    assert all("not an additional duty" in m["note"] for m in gov["measures"])


def _forged_context_citation() -> tuple[GoverningBundle, dict]:
    g = _governing()
    measure_slice = next(s for s in g.source_slices if s.role == "measure")
    obj = {
        "documentary_coverage": "FULL",
        "rationale": "",
        "duties": [
            {
                "duty_id": "d1",
                "statement": "Apply applicable patches within 35 days",
                "finding": "COVERED",
                # the model cites the Measure as if it were the duty
                "governing_slice_ids": [measure_slice.slice_id],
                "candidate_slice_ids": [],
            }
        ],
        "gaps": [],
    }
    return g, obj


@needs
def test_verifier_rejects_context_slices_as_duty_evidence():
    g, obj = _forged_context_citation()
    judgment = verify_judgment(obj, _request(g))
    codes = [u.code for u in judgment.uncertainties]
    assert "READING_CONTEXT_CITED_AS_DUTY" in codes
    # the demoted citation carries no verified support
    assert not judgment.duties[0].verified_support
    # and the covered set built from it carries no governing anchors
    assert all(not c.governing_slice_ids for c in judgment.covered)


@needs
def test_genuine_governing_citation_still_verifies():
    g = _governing()
    duty_slice = next(s for s in g.source_slices if s.role == "governing" and g.ref in s.ref)
    internal = SourceSlice(
        slice_id="cand-internal-1",
        ref="patch-procedure V11 §4",
        document_id="patch-procedure",
        revision_hash="x",
        chunk_id="c1",
        text="Evaluate security patches at least once every 35 calendar days.",
        char_start=0,
        char_end=60,
        role="candidate",
    )
    request = _request(g)
    from portal.modules.compliance.core.determination import CandidateRecord

    request.candidate_set.records.append(
        CandidateRecord(
            candidate_id="c1",
            document_id="patch-procedure",
            chunk_id="c1",
            text=internal.text,
            source_slice=internal,
        )
    )
    obj = {
        "documentary_coverage": "FULL",
        "rationale": "",
        "duties": [
            {
                "duty_id": "d1",
                "statement": "evaluate patches every 35 days",
                "finding": "COVERED",
                "governing_slice_ids": [duty_slice.slice_id],
                "candidate_slice_ids": [internal.slice_id],
                "governing_operand": "35 calendar days",
                "candidate_operand": "35 calendar days",
            }
        ],
        "gaps": [],
    }
    judgment = verify_judgment(obj, request)
    assert judgment.documentary_coverage == "FULL"
    assert judgment.duties[0].verified_support
    assert judgment.covered and judgment.covered[0].governing_slice_ids == [duty_slice.slice_id]
