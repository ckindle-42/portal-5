"""H.4 -- claims from the hunt, not from a pre-stream stage
(TASK_BULLY_HUNT_SWEEP_V1). Seeded to fail against a naive/no-op
implementation: K.4's shape (`investigate_anchors` at 0 records) cannot
publish a Bully number; comprehension is computed over sampled, not
streamed."""

from __future__ import annotations

from portal.modules.security.core.bully.full_pipeline import (
    STAGE_OK,
    ClaimEvidence,
    PipelineReport,
    StageResult,
    zero_record_claim_guard,
)


def _report_with(name: str, records_received: int) -> PipelineReport:
    report = PipelineReport()
    report.stages = [
        StageResult(
            name=name,
            module="investigation_pivot",
            status=STAGE_OK,
            seconds=0.1,
            records_received=records_received,
        )
    ]
    return report


def test_k4_shape_investigate_anchors_at_zero_records_is_disqualified():
    report = _report_with("investigate_anchors", records_received=0)
    guard = zero_record_claim_guard(report, ("investigate_anchors", "infer_universal_behaviors"))
    assert guard["disqualified_stages"] == ["investigate_anchors"]
    assert guard["guard_active"] is True


def test_healthy_stage_with_records_is_not_disqualified():
    report = _report_with("investigate_anchors", records_received=359_757)
    guard = zero_record_claim_guard(report, ("investigate_anchors", "infer_universal_behaviors"))
    assert guard["disqualified_stages"] == []


def test_missing_stage_is_not_treated_as_disqualified():
    # a stage that never ran (e.g. required stage failed earlier) has no
    # StageResult at all -- absence is a different finding from "ran at 0
    # records" and must not silently disqualify a claim that never had the
    # chance to be sourced from it.
    report = PipelineReport()
    guard = zero_record_claim_guard(report, ("investigate_anchors",))
    assert guard["disqualified_stages"] == []


def test_disqualified_stage_nulls_the_bully_claim_not_fabricates_zero():
    """A disqualified stage's claim fields must publish as None, never a
    fabricated 0 or a stale prior-run number."""
    evidence = ClaimEvidence(
        crogl_sourcetypes_reviewed=0,
        crogl_identity_coverage=None,
        bully_chain_reach_recall=None,
        bully_max_pivot_distance=None,
        corpus_records_processed=0,
        corpus_records_available=0,
        generator_cousin_recall_at_distance={},
        bully_entries_located=None,
        bully_entries_attempted=None,
        bully_cousins_planted=None,
        bully_cousins_recovered=None,
    )
    d = evidence.to_dict()
    assert d["bully"]["entries_located"] is None
    assert d["bully"]["floor_recall"] is None


def test_crogl_comprehension_uses_sampled_denominator_not_stream_exposure():
    """K.4's own numbers: 5 schemas behaviourally profiled of 245 sourcetypes
    the SCORER sampled -- comprehension 0.020. The stream touched 325
    sourcetypes (exposure); comprehension must NOT be computed against that
    number."""
    evidence = ClaimEvidence(
        crogl_sourcetypes_reviewed=325,  # exposure -- stream touched 325 sourcetypes
        crogl_identity_coverage=None,
        bully_chain_reach_recall=None,
        bully_max_pivot_distance=None,
        corpus_records_processed=359_757,
        corpus_records_available=281_069_416,
        generator_cousin_recall_at_distance={},
        crogl_sources_profiled=5,
        crogl_sources_sampled=245,  # comprehension denominator -- what the scorer sampled
    )
    d = evidence.to_dict()
    assert d["crogl"]["sourcetypes_reviewed"] == 325
    assert d["crogl"]["comprehension_fraction"] == 0.0204
    assert d["crogl"]["sources_profiled"] == 5
    assert d["crogl"]["sources_sampled"] == 245


def test_bully_reported_from_sweep_counts_not_single_found_entry():
    evidence = ClaimEvidence(
        crogl_sourcetypes_reviewed=0,
        crogl_identity_coverage=None,
        bully_chain_reach_recall=None,
        bully_max_pivot_distance=None,
        corpus_records_processed=0,
        corpus_records_available=0,
        generator_cousin_recall_at_distance={},
        bully_entries_located=8,
        bully_entries_attempted=27,
        bully_cousins_planted=8,
        bully_cousins_recovered=3,
    )
    d = evidence.to_dict()
    assert d["bully"]["entries_located"] == 8
    assert d["bully"]["entries_attempted"] == 27
    assert d["bully"]["floor_recall"] == round(8 / 27, 4)
    assert d["bully"]["cousin_recall"] == round(3 / 8, 4)
