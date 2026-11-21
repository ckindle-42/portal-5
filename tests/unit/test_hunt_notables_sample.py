from __future__ import annotations

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.sample import (
    LocalWindow,
    SourceFacts,
    localise,
    read_anchors,
    read_mode,
    read_windows,
    route_filter,
    sample_windows,
    select_local_windows,
    window_bounds,
)


class _NewestExecutor:
    """Splunk-like: newest events first inside the queried time bound, capped at row_cap."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[float, float, int | None]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, kind
        self.calls.append((start, end, row_cap))
        inside = [row for row in self.rows if start <= float(row["_time"]) < end]
        inside.sort(key=lambda row: float(row["_time"]), reverse=True)
        return Read([dict(row) for row in inside[: row_cap or len(inside)]], False, None)


def _facts() -> SourceFacts:
    return SourceFacts("ix", "st", 9, 0.0, 100.0, ("h1",), 1, ("s1",), 1)


def _rows() -> list[dict[str, object]]:
    return [{"_raw": f"event {t}", "_time": float(t), "host": "h1"} for t in range(10, 100, 10)]


def test_one_sub_window_reads_the_newest_of_the_whole_slice():
    executor = _NewestExecutor(_rows())
    read = read_windows(
        executor, _facts(), window_bounds(0.0, 100.0, 1), per_window=4, kind="behavior_events"
    )
    assert [float(row["_time"]) for row in read.rows] == [60.0, 70.0, 80.0, 90.0]
    assert executor.calls == [(0.0, 100.0, 4)]


def test_sub_windows_sample_each_part_of_the_slice_not_only_its_tail():
    executor = _NewestExecutor(_rows())
    read = read_windows(
        executor,
        _facts(),
        window_bounds(0.0, 100.0, 1),
        per_window=4,
        kind="behavior_events",
        sub_windows=2,
    )
    times = {float(row["_time"]) for row in read.rows}
    # the newest two of each half: first half contributes 40/30, second half 90/80
    assert times == {30.0, 40.0, 80.0, 90.0}
    assert executor.calls == [(0.0, 50.0, 2), (50.0, 100.0, 2)]
    assert read.windows == 1


def test_sub_windows_keep_the_total_event_budget():
    rows = [{"_raw": f"e{t}", "_time": float(t), "host": "h1"} for t in range(0, 4800, 1)]
    executor = _NewestExecutor(rows)
    read = read_windows(
        executor,
        SourceFacts("ix", "st", len(rows), 0.0, 4800.0, ("h1",), 1, ("s1",), 1),
        window_bounds(0.0, 4800.0, 12),
        per_window=392,
        kind="behavior_events",
        sub_windows=2,
    )
    assert len(read.rows) <= 392 * 12
    assert len(executor.calls) == 24


def test_shared_indexed_sources_remain_scoped_to_card_sourcetype():
    facts = SourceFacts(
        "ix",
        "mysql:database",
        10,
        0,
        100,
        (),
        0,
        ("gacrux", "jabbah"),
        2,
        shared_sources=("gacrux",),
    )
    route, _ = route_filter(facts)
    assert route == 'sourcetype="mysql:database" (source="gacrux" OR source="jabbah")'


def test_card_can_read_a_historical_source_with_one_timestamp():
    stamp = 1503726179.0
    facts = SourceFacts("ix", "st", 1, stamp, stamp, (), 0, (), 0)
    assert any(start <= stamp < end for start, end in sample_windows(facts))


def test_small_source_read_includes_events_clustered_in_one_slice():
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    facts = SourceFacts("ix", "stream:ftp", 1490, 0, 1500, (), 0, ("ftp",), 1)
    rows = [{"_time": 0.0}] + [{"_time": 1500.0}] * 1489
    executor = _NewestExecutor(rows)
    read = read_behaviour_source(executor, facts, per_window=383)
    assert len(read.rows) == facts.events
    assert read.windows == len(executor.calls) == 1
    assert read.read_mode == "whole"


def test_read_mode_reads_whole_only_below_the_wide_source_ceiling():
    assert read_mode(47_000) == "whole"
    assert read_mode(55_000_000) == "anchored"


def _burst_series(
    width: float, buckets: int, baseline: int, burst: int, burst_buckets: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"_time": index * width, "host": "h1", "count": str(baseline)} for index in range(buckets)
    ]
    for index in range(2, 2 + burst_buckets):
        rows[index]["count"] = str(burst)
    return rows


def test_twenty_minute_burst_is_selected_by_five_minutes_and_missed_by_four_hours():
    narrow = select_local_windows(_burst_series(300, 288, 21, 121, 4), 300)
    wide = select_local_windows(_burst_series(14400, 24, 1008, 1408, 1), 14400)
    assert len(narrow) == 1
    assert narrow[0].end - narrow[0].start == 1200
    assert narrow[0].events == 484
    assert wide == []


class _SummaryExecutor:
    """A Splunk-like fake: one model's summaries cover a window, and the index aggregate answers."""

    def __init__(
        self, window: tuple[float, float] | None, buckets: list[dict[str, object]]
    ) -> None:
        self.window = window
        self.buckets = buckets
        self.queries: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del start, end, kind, row_cap
        self.queries.append(query)
        if "summariesonly=true count min(_time)" in query:
            model = query.split("from datamodel=", 1)[1].split(" ", 1)[0]
            if model == "Authentication" and self.window:
                row = {"count": "100", "first": self.window[0], "last": self.window[1]}
                return Read([row], False, None)
            return Read([], False, None)
        return Read([dict(row) for row in self.buckets], False, None)


def test_a_model_covering_the_range_localises_from_its_summary_not_a_scan():
    executor = _SummaryExecutor((0.0, 7200.0), _burst_series(300, 24, 21, 121, 4))
    found = localise(executor, "ix", 0.0, 7200.0)

    assert found.mechanism == "accelerated"
    assert found.model == "Authentication"
    assert found.coverage == "accelerated"
    assert found.accel_window == (0.0, 7200.000001)
    assert len(found.windows) == 1 and found.windows[0].events == 484
    assert not any(query.startswith("| tstats count where") for query in executor.queries)


def test_a_range_outside_the_acceleration_window_is_localised_by_a_scan_not_empty():
    executor = _SummaryExecutor((0.0, 500.0), _burst_series(300, 24, 21, 121, 4))
    found = localise(executor, "ix", 600.0, 7200.0)

    assert found.mechanism == "indexed"
    assert found.coverage == "scan"
    assert found.accel_window == (0.0, 500.000001)
    assert len(found.windows) == 1
    assert any(query.startswith("| tstats count where") for query in executor.queries)


class _QueryExecutor:
    """Answers each read with the rows its own host and time bounds select."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind
        self.queries.append(query)
        inside = [
            row
            for row in self.rows
            if start <= float(row["_time"]) < end and f'host="{row["host"]}"' in query
        ]
        return Read([dict(row) for row in inside[: row_cap or len(inside)]], False, None)


def test_narrowed_scan_reads_one_host_window_and_reports_events_scanned():
    rows = [
        {"_time": 350.0, "host": "h1", "count": 1},
        {"_time": 350.0, "host": "h2", "count": 1},
    ]
    executor = _QueryExecutor(rows)
    facts = SourceFacts("ix", "st", 55_000_000, 0.0, 600.0, ("h1", "h2"), 2, ("s1",), 1)
    read = read_anchors(
        executor, facts, [LocalWindow("h1", 300.0, 600.0, 1000)], per_window=10, kind="x"
    )
    assert [row["host"] for row in read.rows] == ["h1"]
    assert read.events_scanned == 1000
    assert read.read_mode == "anchored"
    assert read.rung == "narrowed_scan"
    assert 'host="h1"' in executor.queries[0]
