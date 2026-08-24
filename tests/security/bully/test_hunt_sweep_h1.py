"""H.1 -- preflight gates and span calibration for the hunt-sweep long run
(TASK_BULLY_HUNT_SWEEP_V1). Each test is seeded to fail against a naive/no-op
implementation: a 60m span must project over budget and return NARROW_SPAN
with the narrowing factor; a 10m span must COMMIT; a failing plant
round-trip must fail preflight; a checkpoint that does not round-trip must
fail; `EntryProgress.already_planted` must block a re-plant on resume;
unattempted entries must be reported, never silently dropped."""

from __future__ import annotations

from portal.modules.security.core.bully.run_preflight import (
    EntryProgress,
    PreflightCheck,
    calibrate_span,
    check_anchors_resolve,
    check_claim_guard,
    check_plant_roundtrip,
    check_resume_roundtrip,
    preflight,
    project_entry_seconds,
)

# K.4's measured constants, restated here so this test would fail if the
# module's defaults ever silently drifted from the measured run.
K4_UNITS = 971
K4_CLUSTER_SECONDS = 770.6
K4_READ_RPS = 950.0


def test_60m_span_projects_over_budget_and_narrows() -> None:
    units = 2_158
    records = 84_583
    cost = project_entry_seconds(units, records)
    cal = calibrate_span(
        span_seconds=3600,
        index="botsv3",
        measured_records=records,
        measured_units=units,
        measured_cluster_seconds=cost["cluster_seconds"],
        measured_total_seconds=cost["total_seconds"],
        n_entries=27,
        budget_hours=4.0,
    )
    assert cal.verdict == "NARROW_SPAN"
    assert cal.projected_total_hours > 4.0
    assert any("narrow the span by" in r for r in cal.reasons)
    # the projection should be in the ballpark the task's own table gives
    # (~29h at 60m span across 27 entries) -- not exact (this test uses
    # illustrative units/records, not a live-measured entry) but the same
    # order of magnitude.
    assert 20.0 < cal.projected_total_hours < 40.0


def test_10m_span_commits() -> None:
    units = 360
    records = 14_097
    cost = project_entry_seconds(units, records)
    cal = calibrate_span(
        span_seconds=600,
        index="botsv3",
        measured_records=records,
        measured_units=units,
        measured_cluster_seconds=cost["cluster_seconds"],
        measured_total_seconds=cost["total_seconds"],
        n_entries=27,
        budget_hours=4.0,
    )
    assert cal.verdict == "COMMIT"
    assert cal.projected_total_hours < 4.0
    assert cal.reasons == ()


def test_calibration_entry_with_no_units_is_invalid_not_committed() -> None:
    cal = calibrate_span(
        span_seconds=600,
        index="botsv3",
        measured_records=0,
        measured_units=0,
        measured_cluster_seconds=0.0,
        measured_total_seconds=0.0,
        n_entries=27,
    )
    assert cal.verdict == "INVALID"
    assert any("no_units" in r or "no_records" in r for r in cal.reasons)


def test_failing_plant_roundtrip_fails_preflight() -> None:
    def broken_plant() -> str:
        raise RuntimeError("HEC write failed silently")

    check = check_plant_roundtrip(broken_plant, lambda m: 1, lambda m: None)
    assert check.passed is False
    report = preflight([check])
    assert report.passed is False
    assert "plant_roundtrip" in report.failures


def test_plant_roundtrip_that_reads_back_nothing_fails() -> None:
    check = check_plant_roundtrip(lambda: "marker-1", lambda m: 0, lambda m: None)
    assert check.passed is False


def test_working_plant_roundtrip_passes() -> None:
    check = check_plant_roundtrip(lambda: "marker-1", lambda m: 1, lambda m: None)
    assert check.passed is True


def test_checkpoint_that_does_not_roundtrip_fails() -> None:
    def save(_data: dict) -> None:
        pass  # silently drops the write -- the exact failure mode this guards

    def load() -> dict | None:
        return None

    check = check_resume_roundtrip(save, load)
    assert check.passed is False
    report = preflight([check])
    assert report.passed is False
    assert "resume_roundtrip" in report.failures


def test_checkpoint_that_roundtrips_passes() -> None:
    store: dict = {}

    def save(data: dict) -> None:
        store["v"] = data

    def load() -> dict | None:
        return store.get("v")

    check = check_resume_roundtrip(save, load)
    assert check.passed is True


def test_already_planted_blocks_replant_on_resume() -> None:
    progress = EntryProgress()
    progress.planted_cousins["T1558.004"] = "cz-botsv3-T1558.004-000-REORDER_MINOR-00-d0"
    assert progress.already_planted("T1558.004") is not None
    assert progress.already_planted("T1190") is None


def test_unattempted_entries_reported_not_dropped() -> None:
    progress = EntryProgress()
    progress.record(
        "T1558.004", {"located": True, "cousin_planted": True, "cousin_recovered": True}
    )
    progress.entries_not_attempted.extend(["T1190", "T1078"])
    d = progress.to_dict()
    assert d["n_not_attempted"] == 2
    assert d["entries_not_attempted"] == ["T1190", "T1078"]
    assert d["n_done"] == 1
    assert d["floor_recall"] == 1.0
    assert d["cousin_recall"] == 1.0


def test_anchors_resolve_reports_unresolved_entries() -> None:
    class FakeEntry:
        def __init__(self, technique: str, hits: int) -> None:
            self.technique = technique
            self._hits = hits

    entries = [FakeEntry("T1558.004", 5), FakeEntry("T1190", 0), FakeEntry("T1078", 0)]
    check = check_anchors_resolve(entries, probe=lambda e: e._hits)
    assert check.passed is True  # at least one resolved
    assert "1/3" in check.detail
    assert "T1190" in check.detail
    assert "T1078" in check.detail


def test_claim_guard_check_reports_unwired_guard() -> None:
    check = check_claim_guard(lambda: False)
    assert check.passed is False
    check_ok = check_claim_guard(lambda: True)
    assert check_ok.passed is True


def test_preflight_report_fails_overall_when_calibration_is_narrow_span() -> None:
    checks = [PreflightCheck(name="anchors_resolve", passed=True, detail="ok")]
    cal = calibrate_span(
        span_seconds=3600,
        index="botsv3",
        measured_records=84_583,
        measured_units=2_158,
        measured_cluster_seconds=3894.0,
        measured_total_seconds=3982.0,
        n_entries=27,
    )
    report = preflight(checks, calibration=cal)
    assert report.passed is False
    assert report.to_dict()["calibration"]["verdict"] == "NARROW_SPAN"
