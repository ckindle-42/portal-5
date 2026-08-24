"""K.3 -- starvation as a first-class signal (TASK_BULLY_SCORER_FEED_V1).

Seeded: F.4's real stage profile (records_received 63, stream total
359,757) must fail `starvation_check`; a healthy profile must pass."""

from __future__ import annotations

from portal.modules.security.core.bully.full_pipeline import (
    STAGE_DEGRADED,
    STAGE_OK,
    PipelineReport,
    StageResult,
    starvation_check,
)

_ANALYTICAL_STAGES = (
    "infer_field_roles",
    "classify_telemetry",
    "infer_universal_behaviors",
    "build_artifact_graph",
    "resolve_entities_and_timelines",
    "fit_baseline",
    "discover_and_cluster",
    "series_and_level",
    "level_match",
    "grade_to_loop_contract",
    "resolve_unit_outcomes",
    "raise_and_verdict_concerns",
)


def _report_with(records_received: int) -> PipelineReport:
    report = PipelineReport()
    report.stages = [
        StageResult(
            name=name,
            module="m",
            status=STAGE_OK,
            seconds=0.0,
            records_received=records_received,
        )
        for name in _ANALYTICAL_STAGES
    ]
    return report


def test_f4_stage_profile_fails_starvation_check_permanent_regression():
    """F.4's real numbers: every analytical stage received 63 records while
    the stream covered 359,757. Must always FAIL."""
    report = _report_with(63)
    result = starvation_check(report, stream_total=359_757, analytical_stages=_ANALYTICAL_STAGES)
    assert result["verdict"] == "FAIL", result
    assert len(result["findings"]) == len(_ANALYTICAL_STAGES)
    assert all(f["stage"] in _ANALYTICAL_STAGES for f in result["findings"])


def test_healthy_profile_passes_starvation_check():
    """A stratified-sample-fed run: analytical stages receive ~65k of
    359,757 (18%), well above the 1% floor."""
    report = _report_with(64_863)
    result = starvation_check(report, stream_total=359_757, analytical_stages=_ANALYTICAL_STAGES)
    assert result["verdict"] == "PASS", result
    assert result["findings"] == []


def test_degraded_stage_is_not_flagged_by_starvation_check():
    """A stage that failed outright is already visible via `status`;
    starvation_check should not double-report it."""
    report = PipelineReport()
    report.stages = [
        StageResult(
            name="classify_telemetry",
            module="telemetry_behavior",
            status=STAGE_DEGRADED,
            seconds=0.0,
            records_received=0,
            error="boom",
        )
    ]
    result = starvation_check(
        report, stream_total=359_757, analytical_stages=("classify_telemetry",)
    )
    assert result["verdict"] == "PASS"
    assert result["findings"] == []


def test_stage_missing_from_report_is_not_flagged():
    """A stage the report never ran (e.g. an earlier required-stage abort)
    must not be reported as starved -- that is a different failure mode,
    already visible as a missing entry."""
    report = PipelineReport()
    report.stages = []
    result = starvation_check(
        report, stream_total=359_757, analytical_stages=("classify_telemetry",)
    )
    assert result["verdict"] == "PASS"
    assert result["findings"] == []
