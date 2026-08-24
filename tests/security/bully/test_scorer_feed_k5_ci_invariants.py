"""K.5 -- CI invariants for the scorer feed (TASK_BULLY_SCORER_FEED_V1).
Each check seeds a violation and confirms the guard rejects it, then
confirms a clean input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_scorer_feed_stratified_sample_never_single_batch",
    "bully_scorer_feed_verdict_published_and_starved_fails",
    "bully_scorer_feed_records_received_published_per_stage",
    "bully_scorer_feed_f4_profile_permanent_starved_regression",
    "bully_scorer_feed_head_or_tail_slice_fails_stratification",
    "bully_scorer_feed_handoff_doc_exists_with_head_pin",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_six_invariants_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_scorer_feed_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        verdict, detail, _findings = _run(slug)
        assert verdict == "PASS", f"{slug} should PASS on the clean repo but got: {detail}"


def test_f4_permanent_regression_guard_is_itself_verified_true():
    """K5's permanent regression: the real starvation_check against F.4's
    exact published profile (63 records, 359,757-record stream) must FAIL,
    proving the guard would have caught the original defect."""
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
        starvation_check,
    )

    stages = (
        "classify_telemetry",
        "infer_universal_behaviors",
        "resolve_entities_and_timelines",
        "raise_and_verdict_concerns",
    )
    report = PipelineReport()
    report.stages = [
        StageResult(name=n, module="m", status=STAGE_OK, seconds=0.0, records_received=63)
        for n in stages
    ]
    result = starvation_check(report, stream_total=359_757, analytical_stages=stages)
    assert result["verdict"] == "FAIL"
    assert len(result["findings"]) == len(stages)
