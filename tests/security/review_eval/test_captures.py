"""Recorded capture certification uses source-shaped event times and can fail its own checks."""

from __future__ import annotations

from datetime import UTC, datetime

from portal.modules.security.core.review_eval.captures import (
    _known_answer_fixture,
    event_time,
    event_time_bounds,
    run_known_answer_selftest,
    validate_capture,
)


def test_capture_validator_known_answer_selftest_covers_all_four_outcomes() -> None:
    result = run_known_answer_selftest()
    assert result["passed"]
    assert result["cases"] == {
        "signal_present": True,
        "signal_removed": True,
        "events_shifted_outside_interval": True,
        "empty_capture": True,
    }


def test_event_time_reads_record_prefixes_but_not_dates_inside_payloads() -> None:
    expected = datetime(2026, 10, 9, 12, 30, 0, tzinfo=UTC).timestamp()
    assert event_time("2026-10-09T12:30:00Z client request") == expected
    assert event_time("request body includes 2026-10-09T12:30:00Z") is None


def test_linux_syslog_prefix_uses_the_recorded_interval_to_resolve_the_year() -> None:
    start = datetime(2026, 1, 2, 2, 59, 0, tzinfo=UTC).timestamp()
    end = datetime(2026, 1, 2, 3, 1, 0, tzinfo=UTC).timestamp()
    expected = datetime(2026, 1, 2, 3, 0, 0, tzinfo=UTC).timestamp()
    assert (
        event_time(
            "Jan  2 03:00:00 host daemon: event", source="linux:syslog", interval=(start, end)
        )
        == expected
    )
    assert (
        event_time("Jan  2 03:00:00 host daemon: event", source="web:access", interval=(start, end))
        is None
    )


def test_date_only_source_time_is_kept_as_a_day_wide_uncertainty_interval() -> None:
    start = datetime(2026, 10, 9, 12, 30, 0, tzinfo=UTC).timestamp()
    end = start + 60
    bounds = event_time_bounds("EventCode=4769 TimeCreated=2026-10-09", source="windows:security")
    assert bounds == (
        datetime(2026, 10, 9, 0, 0, 0, tzinfo=UTC).timestamp(),
        datetime(2026, 10, 10, 0, 0, 0, tzinfo=UTC).timestamp() - 0.000001,
    )
    capture, source = _known_answer_fixture()
    signal = capture["telemetry"][source][0].rsplit(" TimeCreated=", maxsplit=1)[0]
    capture["telemetry"] = {source: [f"{signal} TimeCreated=2026-10-09"]}
    capture["collected_since_epoch"] = start
    capture["captured_at"] = end
    result = validate_capture(capture)
    assert not result.valid
    assert result.timed_in_interval == 0 and result.time_unscoped_count == 1
    assert "SIGNAL_EVENT_TIME_PRECISION_EXCEEDS_INTERVAL" in next(
        iter(result.technique_reasons.values())
    )


def test_signal_without_a_source_timestamp_is_reported_as_unscoped() -> None:
    capture, source = _known_answer_fixture()
    line = capture["telemetry"][source][0].rsplit(" TimeCreated=", maxsplit=1)[0]
    capture["telemetry"] = {source: [line]}
    result = validate_capture(capture)
    assert not result.valid
    assert "SIGNAL_PRESENT_WITHOUT_EVENT_TIMESTAMP" in next(iter(result.technique_reasons.values()))


def test_out_of_interval_context_does_not_reject_an_in_interval_signal() -> None:
    capture, source = _known_answer_fixture()
    signal_line = capture["telemetry"][source][0]
    capture["telemetry"][source].append("2020-01-01T00:00:00Z unrelated context")
    result = validate_capture(capture)
    assert result.valid
    assert result.timed_in_interval == 1 and result.timed_outside_interval == 1
    assert signal_line in capture["telemetry"][source]
