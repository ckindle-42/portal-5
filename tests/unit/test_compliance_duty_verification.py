"""END_TO_END Phase 9 — the duty-level judgment's deterministic verification.

The required minimal-pair / adversary battery (slice §6), hermetic at the
verify layer: same-duty quantitative direction (35→40 weaker, 30 stricter),
copied-text and ToC adversaries, stale-revision demotion, internal conflict
retention, and the boundary case. Nothing here weakens an expected outcome
after seeing output — every expectation below is the slice spec's own
definition of the case.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import reading
from portal.modules.compliance.core.determination import (
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    GoverningBundle,
    SourceSlice,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _request(candidates: list[dict]) -> AssessmentRequest:
    gov_slice = SourceSlice(
        slice_id="GOV",
        ref="CIP-007-6 R2 Part 2.2",
        document_id="cip-007-6.pdf",
        revision_hash="govhash",
        chunk_id="GOV",
        locator="R2 Part 2.2",
        text=(
            "At least once every 35 calendar days, evaluate security patches "
            "for applicability that have been released since the last evaluation."
        ),
        char_start=0,
        char_end=140,
        role="governing",
    )
    bundle = GoverningBundle(
        ref="CIP-007-6 R2 Part 2.2",
        part_text=gov_slice.text,
        lead_in="Each Responsible Entity shall implement one or more documented processes.",
        definitions=[],
        references=[],
        meta=[],
        source_slices=[gov_slice],
    )
    records = []
    for cand in candidates:
        sl = SourceSlice(
            slice_id=cand["id"],
            ref=cand["id"],
            document_id=cand.get("document", "proc.pdf"),
            revision_hash=cand["id"].lower() + "hash",
            chunk_id=cand["id"],
            locator=cand.get("locator", "3.3"),
            text=cand["text"],
            char_start=0,
            char_end=len(cand["text"]),
            role="candidate",
        )
        records.append(
            CandidateRecord(
                candidate_id=cand["id"],
                document_id=cand.get("document", "proc.pdf"),
                chunk_id=cand["id"],
                text=cand["text"],
                locator=sl.locator,
                source_slice=sl,
            )
        )
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2 Part 2.2",
        governing=bundle,
        candidate_set=CandidateSet(records=records),
    )


def _packet_functions(candidates: list[dict]) -> dict[str, dict]:
    return {
        c["id"]: {
            "operative": c.get("operative", True),
            "source_function": c.get("source_function", "OPERATIVE_PROCEDURE"),
            "revision_current": c.get("revision_current", True),
        }
        for c in candidates
    }


def _judge(
    duties: list[dict],
    candidates: list[dict],
    *,
    coverage: str = "FULL",
    gaps: list[dict] | None = None,
):
    request = _request(candidates)
    packet = {"candidates": [_candidate_packet(c) for c in candidates]}
    obj = {
        "documentary_coverage": coverage,
        "duties": duties,
        "gaps": gaps or [],
        "rationale": "fixture",
        "uncertainties": [],
    }
    return reading.verify_judgment(obj, request, packet=packet)


def _candidate_packet(cand: dict) -> dict:
    return {
        "candidate_id": cand["id"],
        "document_id": cand.get("document", "proc.pdf"),
        "text": cand["text"],
        "source_function": cand.get("source_function", "OPERATIVE_PROCEDURE"),
        "operative": cand.get("operative", True),
        "revision_current": cand.get("revision_current", True),
    }


def _duty(
    duty_id: str,
    *,
    finding: str = "COVERED",
    gov_operand: str = "at least once every 35 calendar days",
    cand_operand: str = "",
    cand_ids: list[str] | None = None,
) -> dict:
    return {
        "duty_id": duty_id,
        "statement": "evaluate released security patches for applicability",
        "finding": finding,
        "governing_slice_ids": ["GOV"],
        "candidate_slice_ids": cand_ids if cand_ids is not None else ["A22"],
        "governing_operand": gov_operand,
        "candidate_operand": cand_operand,
        "rationale": "",
    }


# ── A/B: positive + minimal counterexamples on the same duty ────────────────


class TestSameDutyQuantity:
    def test_40_days_is_the_same_duty_weaker(self):
        """35→40: same duty, weaker cadence — LESS_RESTRICTIVE direction, the
        duty lands PARTIAL, never a different-duty escape."""
        candidates = [
            {
                "id": "A40",
                "text": "SMEs shall complete the patch-applicability evaluation "
                "once every 40 calendar days.",
            }
        ]
        judgment = _judge(
            [_duty("d1", cand_operand="once every 40 calendar days", cand_ids=["A40"])],
            candidates,
        )
        duty = judgment.duties[0]
        assert duty.quantity_direction == "LESS_RESTRICTIVE"
        assert judgment.outcomes["duties"][0]["outcome"] == "PARTIAL"

    def test_30_days_is_stricter_with_unused_flexibility(self):
        """30 against a required 35 is MORE_RESTRICTIVE: a satisfied duty whose
        unused regulatory flexibility is reported, never a gap."""
        candidates = [
            {
                "id": "A30",
                "text": "The analyst shall evaluate applicable security patches "
                "once every 30 calendar days.",
            }
        ]
        judgment = _judge(
            [_duty("d1", cand_operand="once every 30 calendar days", cand_ids=["A30"])],
            candidates,
        )
        duty = judgment.duties[0]
        assert duty.quantity_direction == "MORE_RESTRICTIVE"
        outcomes = judgment.outcomes["duties"][0]
        assert outcomes["outcome"] == "STRICTER"
        assert judgment.outcomes["unused_flexibility"] == ["d1"]

    def test_no_operands_means_no_direction_claim(self):
        judgment = _judge([_duty("d1", gov_operand="", cand_operand="")], [])
        assert judgment.duties[0].quantity_direction == ""


# ── C: copied-text / non-operative adversaries ──────────────────────────────


class TestSourceFunctionAdversaries:
    def test_copied_traceability_row_cannot_cover_the_duty(self):
        candidates = [
            {
                "id": "TR",
                "text": "R2 Part 2.2 At least once every 35 calendar days, "
                "evaluate security patches. | Section 3.3",
                "operative": False,
                "source_function": "TRACEABILITY_ASSERTION",
            }
        ]
        judgment = _judge(
            [_duty("d1", cand_ids=["TR"])],
            candidates,
        )
        duty = judgment.duties[0]
        assert duty.verified_support is False
        assert "TR" in duty.non_operative_citations
        assert judgment.outcomes["duties"][0]["outcome"] == "EVIDENCE_ONLY"

    def test_toc_and_control_text_cannot_cover_the_duty(self):
        candidates = [
            {
                "id": "TOC22",
                "text": "3.3 Discovery and Evaluation ......... 8",
                "operative": False,
                "source_function": "TABLE_OF_CONTENTS",
            }
        ]
        judgment = _judge([_duty("d1", cand_ids=["TOC22"])], candidates)
        assert judgment.duties[0].verified_support is False

    def test_operative_neighbor_still_supports_beside_a_decoy(self):
        """The top semantic hit is a decoy; the operative clause still supports
        the duty — mixed citations keep the finding grounded."""
        candidates = [
            {
                "id": "DECOY",
                "text": "Evaluation of vendor risk factors occurs annually.",
                "operative": False,
                "source_function": "TRACEABILITY_ASSERTION",
            },
            {
                "id": "A22",
                "text": "The analyst shall evaluate applicable security patches "
                "at least once every 35 calendar days from the identified sources.",
            },
        ]
        judgment = _judge(
            [_duty("d1", cand_operand="every 35 calendar days", cand_ids=["DECOY", "A22"])],
            candidates,
        )
        duty = judgment.duties[0]
        assert duty.verified_support is True
        assert "DECOY" in duty.non_operative_citations
        assert duty.quantity_direction == "EQUIVALENT"


# ── D: stale revision ───────────────────────────────────────────────────────


class TestStaleRevision:
    def test_superseded_revision_is_demoted(self):
        candidates = [
            {
                "id": "OLD",
                "text": "Evaluate applicable security patches once every 35 calendar days.",
                "revision_current": False,
            }
        ]
        judgment = _judge([_duty("d1", cand_ids=["OLD"])], candidates)
        duty = judgment.duties[0]
        assert "OLD" in duty.stale_citations
        assert duty.verified_support is False


# ── internal conflict + boundary ────────────────────────────────────────────


class TestConflictAndBoundary:
    def test_internal_conflict_is_retained_and_flagged(self):
        """Two current documents disagree: neither side is dropped, the gap is
        kept, and the judgment-level conflict flag is set."""
        candidates = [
            {
                "id": "A22",
                "text": "The analyst shall evaluate applicable security patches "
                "at least once every 35 calendar days.",
            },
            {
                "id": "CONF",
                "text": "The OT manager may defer patch applicability evaluation "
                "to the annual review without any interim evaluation.",
            },
        ]
        gaps = [
            {
                "gap_id": "g1",
                "duty_id": "d1",
                "kind": "CONTRADICTION",
                "missing_commitment": "mandatory 35-day evaluation",
                "governing_slice_ids": ["GOV"],
                "internal_counterevidence_slice_ids": ["CONF"],
            }
        ]
        judgment = _judge(
            [_duty("d1", cand_operand="every 35 calendar days", cand_ids=["A22"])],
            candidates,
            coverage="PARTIAL",
            gaps=gaps,
        )
        assert len(judgment.gaps) == 1 and judgment.gaps[0].kind == "CONTRADICTION"
        assert judgment.outcomes["conflict"] is True
        assert judgment.outcomes["conflict_gap_ids"] == ["g1"]
        assert len(judgment.duties) == 1  # the duty survives beside the conflict

    def test_absence_without_boundary_is_downgraded(self):
        """A MISSING duty with no completed boundary receipt cannot ground a
        NONE verdict — U04 downgrade (acceptance case 13's verify-layer twin)."""
        candidates = []
        judgment = _judge(
            [_duty("d1", finding="MISSING", cand_ids=[])],
            candidates,
            coverage="NONE",
            gaps=[
                {
                    "gap_id": "g9",
                    "kind": "OMISSION",
                    "missing_commitment": "the 35-day evaluation",
                    "governing_slice_ids": ["GOV"],
                    "internal_counterevidence_slice_ids": [],
                    "boundary_proof_id": "fabricated-receipt",
                }
            ],
        )
        assert judgment.documentary_coverage == "UNRESOLVED"
        assert judgment.downgraded_from == "NONE"
        assert "boundary" in judgment.failure
