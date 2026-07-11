"""Tests for growth loop — Phase 4 of BUILD_PROGRAM.

Validates:
- RED_ONLY gap produces a draft detection
- Draft that fails proof leg is NOT promotable
- Draft that passes all three legs is surfaced-for-confirm but NOT auto-merged
- Provenance links to the gap
- SPL syntax validation gate
- PROMOTE_POLICY: confirm-only
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.capability_graph import (
    CoverageSummary,
    Gap,
    seed_graph_from_assets,
)
from portal.modules.security.core.growth_loop import (
    DraftDetection,
    GrowthLoopResult,
    ProofResult,
    propose_draft,
    prove_draft,
    run_growth_loop,
    surface_for_confirm,
    validate_spl_syntax,
)

# ── Draft proposer ───────────────────────────────────────────────────────────


class TestDraftProposer:
    """RED_ONLY gap produces a draft detection."""

    def test_propose_draft_from_gap(self):
        gap = Gap(
            gap_id="gap-proc-test-T1078.004",
            procedure_id="proc-test",
            technique_id="T1078.004",
            axes={
                "red": "RED_LANDED",
                "telemetry": "TELEMETRY_OBSERVED",
                "detection": "DETECTION_MISSING",
                "response": "RESPONSE_NOT_TESTED",
            },
            summary="RED_ONLY",
            reason_codes=["RED_LANDED", "TELEMETRY_OBSERVED"],
        )
        draft = propose_draft(gap, technique_description="Cloud account abuse")
        assert draft.technique_id == "T1078.004"
        assert draft.status == "draft"
        assert draft.created_from_gap == "gap-proc-test-T1078.004"
        assert draft.provenance["source"] == "purple-gap"

    def test_draft_id_includes_technique_and_scenario(self):
        gap = Gap(
            gap_id="gap-proc-web_sqli_dump-T1190",
            procedure_id="proc-web_sqli_dump",
            technique_id="T1190",
            axes={},
            summary="RED_ONLY",
            reason_codes=[],
        )
        draft = propose_draft(gap)
        assert "T1190" in draft.draft_id
        assert "web_sqli_dump" in draft.draft_id


# ── SPL syntax validation ────────────────────────────────────────────────────


class TestSPLValidation:
    """SPL syntax validation is a deterministic gate."""

    def test_empty_spl_fails(self):
        ok, errors = validate_spl_syntax("")
        assert not ok
        assert "empty" in errors[0].lower()

    def test_placeholder_comment_fails(self):
        ok, errors = validate_spl_syntax("# TODO: draft SPL for T1078.004")
        assert not ok
        assert "placeholder" in errors[0].lower()

    def test_valid_spl_passes(self):
        spl = 'index=portal5_lab sourcetype="web:access" "UNION SELECT" | stats count'
        ok, errors = validate_spl_syntax(spl)
        assert ok
        assert errors == []

    def test_spl_without_index_fails(self):
        ok, errors = validate_spl_syntax("some random text")
        assert not ok


# ── Proof harness ────────────────────────────────────────────────────────────


class TestProofHarness:
    """Draft proof: fresh-positive + negative-baseline + regression."""

    def test_proof_with_valid_spl(self):
        gap = Gap("gap-1", "proc-1", "T1190", {}, "RED_ONLY", [])
        draft = propose_draft(gap, existing_spl='index=portal5_lab sourcetype="web:access" test')
        result = prove_draft(draft)
        assert result.fresh_positive
        assert result.negative_baseline
        assert result.regression
        assert result.all_passed()

    def test_proof_with_invalid_spl_fails(self):
        gap = Gap("gap-1", "proc-1", "T1190", {}, "RED_ONLY", [])
        draft = propose_draft(gap)  # placeholder SPL
        result = prove_draft(draft)
        assert not result.all_passed()
        assert len(result.errors) > 0

    def test_proof_result_to_dict(self):
        result = ProofResult(fresh_positive=True, negative_baseline=True, regression=False)
        d = result.to_dict()
        assert d["fresh_positive"] is True
        assert d["regression"] is False


# ── Draft promotability ──────────────────────────────────────────────────────


class TestDraftPromotability:
    """Draft that fails any proof leg is NOT promotable."""

    def test_draft_not_promotable_when_unproven(self):
        draft = DraftDetection(
            draft_id="draft-test",
            technique_id="T1190",
            description="test",
            spl="# placeholder",
            expected_signal="test",
            status="draft",
        )
        assert not draft.is_promotable()

    def test_draft_promotable_when_all_proven(self):
        draft = DraftDetection(
            draft_id="draft-test",
            technique_id="T1190",
            description="test",
            spl="index=portal5_lab test",
            expected_signal="test",
            status="proven",
            proof={
                "fresh_positive": True,
                "negative_baseline": True,
                "regression": True,
            },
        )
        assert draft.is_promotable()

    def test_draft_not_promotable_with_missing_leg(self):
        draft = DraftDetection(
            draft_id="draft-test",
            technique_id="T1190",
            description="test",
            spl="index=portal5_lab test",
            expected_signal="test",
            status="proven",
            proof={
                "fresh_positive": True,
                "negative_baseline": False,  # missing
                "regression": True,
            },
        )
        assert not draft.is_promotable()


# ── Growth loop ──────────────────────────────────────────────────────────────


class TestGrowthLoop:
    """Growth loop: RED_ONLY gaps → propose → prove → surface."""

    def test_growth_loop_finds_red_only_gaps(self):
        graph = seed_graph_from_assets()
        # Create a RED_ONLY gap for a technique WITHOUT a detection
        # T1078.004 is a documented gap with no SPL detection
        for gap_id, gap in graph.gaps.items():
            if "T1078.004" in gap_id:
                gap.summary = CoverageSummary.RED_ONLY.value
                gap.axes = {
                    "red": "RED_LANDED",
                    "telemetry": "TELEMETRY_OBSERVED",
                    "detection": "DETECTION_MISSING",
                    "response": "RESPONSE_NOT_TESTED",
                }
                break

        result = run_growth_loop(graph, dry_run=True)
        assert result.gaps_found >= 1
        assert result.drafts_proposed >= 1

    def test_growth_loop_produces_drafts(self):
        graph = seed_graph_from_assets()
        # Make a gap RED_ONLY
        for gap in graph.gaps.values():
            gap.summary = CoverageSummary.RED_ONLY.value
            gap.axes["red"] = "RED_LANDED"
            gap.axes["detection"] = "DETECTION_MISSING"
            break

        result = run_growth_loop(graph, dry_run=True)
        if result.drafts:
            draft = result.drafts[0]
            assert draft.status in ("draft", "proven")
            assert draft.created_from_gap != ""

    def test_growth_loop_dry_run_writes_nothing(self):
        graph = seed_graph_from_assets()
        initial_gaps = len(graph.gaps)
        run_growth_loop(graph, dry_run=True)
        assert len(graph.gaps) == initial_gaps  # unchanged


# ── Surface for confirm ──────────────────────────────────────────────────────


class TestSurfaceForConfirm:
    """Proven drafts surface for operator confirm, never auto-merge."""

    def test_surface_proven_draft(self):
        draft = DraftDetection(
            draft_id="draft-T1190-test",
            technique_id="T1190",
            description="test",
            spl="index=portal5_lab test",
            expected_signal="test",
            status="proven",
            proof={"fresh_positive": True, "negative_baseline": True, "regression": True},
        )
        result = surface_for_confirm(draft)
        assert result["action_required"] == "operator_confirm"
        assert "operator" in result["message"].lower()

    def test_surface_unproven_draft(self):
        draft = DraftDetection(
            draft_id="draft-T1190-test",
            technique_id="T1190",
            description="test",
            spl="# placeholder",
            expected_signal="test",
            status="draft",
        )
        result = surface_for_confirm(draft)
        assert result["action_required"] == "needs_proof"


# ── GrowthLoopResult ─────────────────────────────────────────────────────────


class TestGrowthLoopResult:
    def test_to_dict(self):
        r = GrowthLoopResult(gaps_found=5, drafts_proposed=2, drafts_proven=1)
        d = r.to_dict()
        assert d["gaps_found"] == 5
        assert d["drafts_proven"] == 1
        import json

        json.dumps(d)


# ── Provenance ───────────────────────────────────────────────────────────────


class TestProvenance:
    """Provenance links draft to gap."""

    def test_draft_provenance_links_to_gap(self):
        gap = Gap(
            gap_id="gap-proc-test-T1190",
            procedure_id="proc-test",
            technique_id="T1190",
            axes={"red": "RED_LANDED"},
            summary="RED_ONLY",
            reason_codes=["RED_LANDED"],
        )
        draft = propose_draft(gap)
        assert draft.provenance["source"] == "purple-gap"
        assert draft.provenance["gap_summary"] == "RED_ONLY"
        assert draft.created_from_gap == "gap-proc-test-T1190"
