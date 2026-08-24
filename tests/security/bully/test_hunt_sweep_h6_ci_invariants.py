"""H.6 -- CI invariants for the hunt sweep (TASK_BULLY_HUNT_SWEEP_V1). Each
check seeds a violation and confirms the guard rejects it, then confirms a
clean input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_hunt_sweep_every_entry_attempted_or_reported",
    "bully_hunt_sweep_sampled_window_raises",
    "bully_hunt_sweep_narrow_span_blocks_the_sweep",
    "bully_hunt_sweep_incremental_checkpoint_and_publication",
    "bully_hunt_sweep_resumed_run_never_replants",
    "bully_hunt_sweep_no_claim_from_zero_record_stage",
    "bully_hunt_sweep_crogl_reported_as_comprehension_not_exposure",
    "bully_hunt_sweep_k4_one_entry_shape_permanent_regression",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_eight_invariants_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_hunt_sweep_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        verdict, detail, _findings = _run(slug)
        assert verdict == "PASS", f"{slug} should PASS on the clean repo but got: {detail}"


def test_k4_permanent_regression_guard_is_itself_verified_true():
    """H.6's permanent regression: the real zero_record_claim_guard against
    K.4's exact published shape (investigate_anchors at records_received: 0,
    the single-entry proof) must disqualify the Bully claim, proving the
    guard would have caught K.4's own defect."""
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
        zero_record_claim_guard,
    )

    report = PipelineReport()
    report.stages = [
        StageResult(
            name="investigate_anchors",
            module="investigation_pivot",
            status=STAGE_OK,
            seconds=0.0,
            records_received=0,
        )
    ]
    guard = zero_record_claim_guard(report, ("investigate_anchors", "infer_universal_behaviors"))
    assert guard["disqualified_stages"] == ["investigate_anchors"]
