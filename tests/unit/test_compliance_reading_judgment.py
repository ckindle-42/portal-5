"""The reading judgment: duties drive the verdict, verification never vetoes it.

No model calls — a fake transport returns a fixed judgment so every rule is
pinned deterministically.

The architecture under test replaces three decomposed, mutually-gating questions
with one reading pass. Acceptance case 10 is why: asked "is L22 the SAME duty as
Part 2.2?", two of three live seats answered DIFFERENT while emitting a correct
35/40 binding — a sane answer to a malformed question, since L22 is a cadence
fragment and not a duty. Quorum then struck L22 from the citable set and the
reporter's gap, which necessarily cites L22, was rejected as off-packet: the
Part returned UNRESOLVED with empty covered and gaps, discarding a council
determination of PARTIAL/GAP that was already correct.
"""

from __future__ import annotations

from typing import Any

from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    GoverningBundle,
    SourceSlice,
)
from portal.modules.compliance.core.reading import (
    build_reading_packet,
    read_and_judge,
)

GOV_TEXT = (
    "At least once every 35 calendar days, evaluate security patches for "
    "applicability that have been released since the last evaluation from the "
    "source or sources identified in Part 2.1."
)
A22_TEXT = (
    "SMEs shall evaluate for applicability all security patches released since the "
    "previous evaluation by every source identified in our Part 2.1 inventory."
)
L22_TEXT = (
    "SMEs shall complete that patch-applicability evaluation once every 40 calendar "
    "days; this is the only required evaluation cadence."
)


def _slice(sid: str, text: str, role: str, ref: str = "r") -> SourceSlice:
    return SourceSlice(
        slice_id=sid,
        ref=ref,
        document_id="doc",
        revision_hash="h",
        chunk_id=sid,
        text=text,
        role=role,
    )


def _candidate(cid: str, text: str) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=cid,
        document_id="proc",
        chunk_id=cid,
        text=text,
        source_slice=_slice(f"cand-{cid}", text, "candidate"),
    )


def _request(*candidates: CandidateRecord) -> AssessmentRequest:
    governing = GoverningBundle(
        ref="CIP-007-6 R2 Part 2.2",
        part_text=GOV_TEXT,
        lead_in="Each Responsible Entity shall implement each applicable requirement part.",
        references=[{"ref": "CIP-007-6 R2 Part 2.1", "text": "A patch management process ..."}],
        source_slices=[
            _slice("gov-1", GOV_TEXT, "governing", "CIP-007-6 R2 Part 2.2"),
            _slice(
                "gov-ref", "A patch management process ...", "reference", "CIP-007-6 R2 Part 2.1"
            ),
        ],
    )
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2",
        governing=governing,
        candidate_set=CandidateSet(records=list(candidates)),
    )


def _context() -> AssessmentContext:
    return AssessmentContext(seats=[{"id": "s1", "label": "a", "model": "m1"}])


def _transport(payload: dict[str, Any]):
    import json

    def fn(model: str, system: str, user: str) -> str:
        return json.dumps(payload)

    return fn


def _judge(payload: dict[str, Any], *candidates: CandidateRecord):
    cands = candidates or (_candidate("A22", A22_TEXT), _candidate("L22", L22_TEXT))
    return read_and_judge(_request(*cands), _context(), transport=_transport(payload))


# ── the packet ──────────────────────────────────────────────────────────────


def test_packet_gives_both_sides_in_full():
    packet = build_reading_packet(
        _request(_candidate("A22", A22_TEXT), _candidate("L22", L22_TEXT))
    )
    assert packet["governing"]["part_text"] == GOV_TEXT
    texts = [c["text"] for c in packet["candidates"]]
    assert A22_TEXT in texts and L22_TEXT in texts


def test_a_reference_is_context_and_never_selectable_as_a_duty():
    """The granite trigger, closed structurally.

    Single-factor ablation on the live case-10 packet: with Part 2.1 present
    among the governing slices and in selectable_slice_ids, granite anchored the
    candidate against it and read DIFFERENT; removing it, the same model read
    SAME. Part 2.1 is a *different duty*, so it must reach the reader as context
    for resolving a term and never as selectable governing evidence.
    """
    packet = build_reading_packet(_request(_candidate("A22", A22_TEXT)))
    assert "gov-ref" not in packet["governing"]["selectable_slice_ids"]
    assert all(s["slice_id"] != "gov-ref" for s in packet["governing"]["source_slices"])
    # still supplied, but as labelled context
    assert packet["governing"]["references_for_term_resolution_only"]
    assert "not a duty" in packet["governing"]["references_for_term_resolution_only"][0]["note"]


def test_applicability_is_not_a_decision_surface_in_the_packet():
    """The mistral trigger, closed structurally: the scope block flipped it."""
    packet = build_reading_packet(_request(_candidate("A22", A22_TEXT)))
    assert "scope" not in packet
    assert "do not re-decide" in packet["scope_note"]


# ── duties drive the verdict ────────────────────────────────────────────────


def test_case_10_shape_resolves_to_partial_with_the_gap_citing_l22():
    """The case the old architecture could not express."""
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "rationale": "the cadence duty is weaker than required",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patch applicability at least once every 35 calendar days",
                    "finding": "PARTIAL",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-A22", "cand-L22"],
                    "governing_operand": "35 calendar days",
                    "candidate_operand": "40 calendar days",
                }
            ],
            "gaps": [
                {
                    "duty_id": "d1",
                    "kind": "WEAKER_COMMITMENT",
                    "missing_commitment": "40-day cadence exceeds the 35-day maximum",
                    "governing_slice_ids": ["gov-1"],
                    "internal_counterevidence_slice_ids": ["cand-L22"],
                }
            ],
        }
    )
    assert judgment.documentary_coverage == "PARTIAL"
    assert judgment.valid
    assert [g.kind for g in judgment.gaps] == ["WEAKER_COMMITMENT"]
    # the counterevidence survives: nothing strikes L22 for not being a "duty"
    assert judgment.gaps[0].internal_counterevidence_slice_ids == ["cand-L22"]
    assert judgment.covered and "cand-A22" in judgment.covered[0].internal_slice_ids


def test_full_requires_every_duty_covered():
    """§5's actual FULL rule, checkable for the first time — the false-FULL family."""
    judgment = _judge(
        {
            "documentary_coverage": "FULL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "COVERED",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-A22"],
                },
                {
                    "duty_id": "d2",
                    "statement": "do it every 35 days",
                    "finding": "MISSING",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": [],
                },
            ],
            "gaps": [
                {
                    "duty_id": "d2",
                    "kind": "OMISSION",
                    "missing_commitment": "no cadence stated",
                    "governing_slice_ids": ["gov-1"],
                    "internal_counterevidence_slice_ids": [],
                }
            ],
        }
    )
    assert judgment.documentary_coverage == "PARTIAL"
    assert judgment.downgraded_from == "FULL"


def test_full_stands_when_every_duty_is_covered_and_cited():
    judgment = _judge(
        {
            "documentary_coverage": "FULL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "COVERED",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-A22"],
                }
            ],
            "gaps": [],
        }
    )
    assert judgment.documentary_coverage == "FULL"
    assert judgment.downgraded_from == ""


# ── verification names failures, it does not veto ───────────────────────────


def test_an_unresolvable_citation_is_named_and_does_not_void_the_verdict():
    """Exactly mistral's live failure: a slice id one digit short.

    The old layer's instinct here was to void the whole assessment. The verdict
    is backed by another citation that did verify, so it stands and the bad id
    is reported.
    """
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "PARTIAL",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-A22", "cand-A2"],
                }
            ],
            "gaps": [],
        }
    )
    assert judgment.documentary_coverage == "PARTIAL"
    assert judgment.valid
    assert judgment.duties[0].unverified_citations == ["cand-A2"]
    reasons = " ".join(u.reason for u in judgment.uncertainties)
    assert "cand-A2" in reasons
    codes = {u.code for u in judgment.uncertainties}
    assert "READING_CITATION_UNVERIFIED" in codes
    # the unverified id is dropped from the emitted citation, the verified one kept
    assert judgment.covered[0].internal_slice_ids == ["cand-A22"]


def test_a_fabricated_quantity_drops_the_operand_and_keeps_the_finding():
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "PARTIAL",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-L22"],
                    "governing_operand": "35 calendar days",
                    "candidate_operand": "99 calendar days",
                }
            ],
            "gaps": [],
        }
    )
    assert judgment.documentary_coverage == "PARTIAL"
    assert judgment.duties[0].finding == "PARTIAL"
    assert judgment.duties[0].unverified_operands
    assert "99" in judgment.duties[0].unverified_operands[0]
    assert "READING_OPERAND_UNVERIFIED" in {u.code for u in judgment.uncertainties}


def test_a_real_quantity_verifies_even_with_surrounding_paraphrase():
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "PARTIAL",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-L22"],
                    "governing_operand": "at least once every 35 calendar days",
                    "candidate_operand": "a 40-day cycle",
                }
            ],
            "gaps": [],
        }
    )
    assert judgment.duties[0].unverified_operands == []


def test_a_verdict_resting_only_on_unverified_citations_is_unresolved():
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "COVERED",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-nope"],
                }
            ],
            "gaps": [],
        }
    )
    assert judgment.documentary_coverage == "UNRESOLVED"
    assert not judgment.valid


def test_no_enumerated_duty_is_unresolved_and_says_so():
    judgment = _judge({"documentary_coverage": "FULL", "duties": [], "gaps": []})
    assert judgment.documentary_coverage == "UNRESOLVED"
    assert "no duty" in judgment.failure


def test_a_gap_against_a_covered_duty_is_reported_not_silently_kept():
    judgment = _judge(
        {
            "documentary_coverage": "PARTIAL",
            "duties": [
                {
                    "duty_id": "d1",
                    "statement": "evaluate patches",
                    "finding": "COVERED",
                    "governing_slice_ids": ["gov-1"],
                    "candidate_slice_ids": ["cand-A22"],
                }
            ],
            "gaps": [
                {
                    "duty_id": "d1",
                    "kind": "OMISSION",
                    "missing_commitment": "contradicts its own duty finding",
                    "governing_slice_ids": ["gov-1"],
                    "internal_counterevidence_slice_ids": [],
                }
            ],
        }
    )
    assert "READING_GAP_INCONSISTENT" in {u.code for u in judgment.uncertainties}


def test_a_transport_failure_is_unresolved_not_a_crash():
    def boom(model: str, system: str, user: str) -> str:
        raise RuntimeError("ollama down")

    judgment = read_and_judge(_request(_candidate("A22", A22_TEXT)), _context(), transport=boom)
    assert judgment.documentary_coverage == "UNRESOLVED"
    assert "ollama down" in judgment.failure


def test_non_json_is_unresolved_not_a_crash():
    def prose(model: str, system: str, user: str) -> str:
        return "I think this is probably fine."

    judgment = read_and_judge(_request(_candidate("A22", A22_TEXT)), _context(), transport=prose)
    assert judgment.documentary_coverage == "UNRESOLVED"
    assert "no JSON object" in judgment.failure
