"""Bully field_roles timestamp parsing — py3.13 strptime deprecation (2026-11-07).

Year-bearing formats must keep their exact pre-fix behaviour; the year-less
syslog format must not go through strptime's deprecated 1900 default (it
emitted ~45k DeprecationWarnings across this suite, cpython gh-70647).
"""

from __future__ import annotations

import datetime as _dt
import warnings

from portal.modules.security.core.bully.field_roles import _parse_time


def test_year_bearing_iso_z_unchanged() -> None:
    # The literal Z is matched but produces a naive datetime — local-time
    # epoch, the pre-fix behaviour (only the year-less path changed).
    expected = _dt.datetime(2026, 1, 2, 3, 4, 5).timestamp()
    assert _parse_time("2026-01-02T03:04:05Z") == expected


def test_year_bearing_space_format_unchanged() -> None:
    expected = _dt.datetime(2025, 6, 30, 12, 0, 0).timestamp()
    assert _parse_time("2025-06-30 12:00:00") == expected


def test_year_bearing_day_first_unchanged() -> None:
    expected = _dt.datetime(2024, 2, 29, 23, 59, 58).timestamp()
    assert _parse_time("02/29/2024 23:59:58") == expected


def test_yearless_syslog_uses_current_year_without_deprecation() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        stamp = _parse_time("Nov  7 12:34:56")
    assert stamp is not None
    parsed = _dt.datetime.fromtimestamp(stamp)
    assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (
        _dt.date.today().year,
        11,
        7,
        12,
        34,
    )


def test_yearless_with_utc_suffix_still_parses() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _parse_time("Nov  7 12:34:56 UTC") is not None


def test_garbage_returns_none() -> None:
    assert _parse_time("not a time") is None
