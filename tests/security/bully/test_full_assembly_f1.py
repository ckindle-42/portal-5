"""F.1 -- the assembly harness admits no new capability and fixes in place.

Each test is seeded to fail against a naive harness: a stage naming a module
outside the sixteen must raise at registration time (not silently run), a
failing non-required stage must not stop the run, a failing required stage
must stop it, and the historical I.6/R.6 figures must remain a permanent
`PARTIAL_ASSEMBLY` regression -- if a future change ever makes them grade
`ASSEMBLED`, that change broke the grader, not the history.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully.full_pipeline import (
    BUILT_MODULES,
    STAGE_DEGRADED,
    STAGE_OK,
    ClaimEvidence,
    RunContext,
    Stage,
    assembly_verdict,
    run_pipeline,
)

CORPUS_AVAILABLE = 281_069_416


def test_stage_naming_unbuilt_module_raises() -> None:
    with pytest.raises(ValueError, match="not one of the"):
        Stage(name="bogus", module="window_survey", run=lambda ctx: None)


def test_every_built_module_name_is_registrable() -> None:
    for module in BUILT_MODULES:
        Stage(name=f"stage-{module}", module=module, run=lambda ctx: None)


def test_failing_non_required_stage_is_degraded_and_run_continues() -> None:
    calls: list[str] = []

    def ok_stage(ctx: RunContext) -> str:
        calls.append("first")
        return "first-ok"

    def failing_stage(ctx: RunContext) -> None:
        calls.append("second")
        raise RuntimeError("infer_roles blew up")

    def after_stage(ctx: RunContext) -> str:
        calls.append("third")
        return "third-ok"

    stages = [
        Stage(name="first", module="field_roles", run=ok_stage),
        Stage(name="second", module="behavior_inference", run=failing_stage),
        Stage(name="third", module="discovery", run=after_stage),
    ]

    _ctx, report = run_pipeline(stages, fix_in_place=True)

    assert calls == ["first", "second", "third"]
    assert len(report.stages) == 3
    assert report.stages[1].status == STAGE_DEGRADED
    assert "infer_roles blew up" in (report.stages[1].error or "")
    assert report.stages[0].status == STAGE_OK
    assert report.stages[2].status == STAGE_OK
    assert report.degraded == ("second",)


def test_failing_required_stage_stops_the_run() -> None:
    calls: list[str] = []

    def failing_required(ctx: RunContext) -> None:
        calls.append("first")
        raise RuntimeError("no corpus connection")

    def never_runs(ctx: RunContext) -> None:
        calls.append("second")

    stages = [
        Stage(name="first", module="corpus_bed", run=failing_required, required=True),
        Stage(name="second", module="discovery", run=never_runs),
    ]

    _ctx, report = run_pipeline(stages, fix_in_place=True)

    assert calls == ["first"]
    assert len(report.stages) == 1
    assert report.stages[0].status == STAGE_DEGRADED


def test_integration_fraction_counts_only_ok_stages() -> None:
    def ok(ctx: RunContext) -> None:
        return None

    def fails(ctx: RunContext) -> None:
        raise RuntimeError("boom")

    stages = [
        Stage(name="a", module="field_roles", run=ok),
        Stage(name="b", module="correlation", run=ok),
        Stage(name="c", module="discovery", run=fails),
    ]
    _ctx, report = run_pipeline(stages, fix_in_place=True)

    assert report.modules_exercised == ("correlation", "field_roles")
    assert report.integration_fraction == pytest.approx(2 / 16)


def _real_run_evidence(records_processed: int) -> ClaimEvidence:
    return ClaimEvidence(
        crogl_sourcetypes_reviewed=0,
        crogl_identity_coverage=None,
        bully_chain_reach_recall=None,
        bully_max_pivot_distance=None,
        corpus_records_processed=records_processed,
        corpus_records_available=CORPUS_AVAILABLE,
        generator_cousin_recall_at_distance={},
    )


def _report_for_modules(modules: tuple[str, ...]) -> object:
    def ok(ctx: RunContext) -> None:
        return None

    stages = [Stage(name=f"s{i}", module=m, run=ok) for i, m in enumerate(modules)]
    _ctx, report = run_pipeline(stages, fix_in_place=True)
    return report


def test_i6_actual_figures_are_a_permanent_partial_assembly_regression() -> None:
    # I.6 (bully_investigation_run_i6.py) actually exercises 5/16 modules:
    # behavior_inference, investigation_pivot, telemetry_behavior,
    # corpus_bed, inject_plane -- 213,311 of 281,069,416 records (0.076%).
    i6_modules = (
        "behavior_inference",
        "investigation_pivot",
        "telemetry_behavior",
        "corpus_bed",
        "inject_plane",
    )
    report = _report_for_modules(i6_modules)
    evidence = _real_run_evidence(213_311)

    verdict = assembly_verdict(report, evidence)

    assert verdict["verdict"] == "PARTIAL_ASSEMBLY"
    assert verdict["integration_fraction"] < 0.80
    assert verdict["corpus_fraction"] < 0.10


def test_r6_actual_figures_are_a_permanent_partial_assembly_regression() -> None:
    # R.6 (bully_loop_milestone_run.py) actually exercises 7/16 modules:
    # field_roles, correlation, discovery, series_cousin, pyramid,
    # loop_grader, inject_plane -- 2,000 of 281,069,416 records.
    r6_modules = (
        "field_roles",
        "correlation",
        "discovery",
        "series_cousin",
        "pyramid",
        "loop_grader",
        "inject_plane",
    )
    report = _report_for_modules(r6_modules)
    evidence = _real_run_evidence(2_000)

    verdict = assembly_verdict(report, evidence)

    assert verdict["verdict"] == "PARTIAL_ASSEMBLY"
    assert verdict["integration_fraction"] == pytest.approx(7 / 16)
    assert verdict["corpus_fraction"] < 0.10


def test_genuine_assembled_run_grades_assembled() -> None:
    def ok(ctx: RunContext) -> None:
        return None

    stages = [Stage(name=f"s{i}", module=m, run=ok) for i, m in enumerate(BUILT_MODULES)]
    _ctx, report = run_pipeline(stages, fix_in_place=True)
    evidence = _real_run_evidence(40_000_000)

    verdict = assembly_verdict(report, evidence)

    assert verdict["verdict"] == "ASSEMBLED"
    assert verdict["integration_fraction"] == 1.0
    assert verdict["corpus_fraction"] > 0.10
    assert verdict["reasons"] == []
