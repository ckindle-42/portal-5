"""Bully field_roles timestamp parsing — py3.13 strptime deprecation (2026-11-07).

Year-bearing formats must keep their exact pre-fix behaviour; the year-less
syslog format must not go through strptime's deprecated 1900 default (it
emitted ~45k DeprecationWarnings across this suite, cpython gh-70647).
"""

from __future__ import annotations

import datetime as _dt
import warnings

from portal.modules.security.core.bully.field_roles import _parse_time


def test_year_bearing_iso_z_is_utc() -> None:
    # Corrected 2026-11-07: this test previously asserted the defect, that the
    # literal Z yields a naive datetime read at the reader's local offset. Live
    # collection proved that wrong -- Zulu means UTC, and reading it as local put
    # every event six hours out on a Central host.
    expected = _dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=_dt.UTC).timestamp()
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


def test_zone_bearing_stamps_are_read_as_utc_not_local() -> None:
    """Live 2026-11-07: a trailing literal `Z` is a character to strptime, not a
    zone, so every Zulu stamp was read at the reader's own offset -- six hours on
    a Central host. A `" UTC"` suffix had the same defect. Both mean UTC."""
    want = _dt.datetime(2026, 11, 7, 20, 12, 6, tzinfo=_dt.UTC).timestamp()
    for text in (
        "2026-11-07T20:12:06Z",
        "2026-11-07 20:12:06 UTC",
        "2026-11-07T20:12:06+00:00",
        "2026-11-07T14:12:06-06:00",
    ):
        assert _parse_time(text) == want, text


def test_fractional_zulu_keeps_microseconds_and_utc() -> None:
    want = _dt.datetime(2017, 8, 3, 18, 22, 56, 701252, tzinfo=_dt.UTC).timestamp()
    assert _parse_time("2017-08-03T18:22:56.701252Z") == want


def test_a_stamp_with_no_zone_is_still_local() -> None:
    """Unchanged: without zone information, local is the only honest reading."""
    naive = _dt.datetime(2026, 11, 7, 20, 12, 6)
    assert _parse_time("2026-11-07 20:12:06") == naive.timestamp()
