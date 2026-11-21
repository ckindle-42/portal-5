from __future__ import annotations

import re

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import _file_rows
from portal.modules.security.core.hunt.notables.cards import _facts as card_facts
from portal.modules.security.core.hunt.notables.run import _fact_dict, card_from_dict
from portal.modules.security.core.hunt.notables.sample import (
    IndexFile,
    LocalWindow,
    SourceFacts,
    file_span,
    index_facts,
    localise,
    read_anchors,
    read_files,
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
        self.bounds: list[tuple[float, float]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind, row_cap
        self.queries.append(query)
        self.bounds.append((start, end))
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


def test_a_partially_covered_source_declares_the_covered_and_scanned_ranges():
    executor = _SummaryExecutor((3000.0, 6000.0), _burst_series(300, 24, 21, 121, 4))
    found = localise(executor, "ix", 0.0, 7200.0)

    assert found.mechanism == "accelerated_partial"
    assert found.model == "Authentication"
    assert found.coverage == "accelerated_partial"
    assert found.covered_window == (3000.0, 6000.000001)
    assert found.scanned_window == [(0.0, 3000.0), (6000.000001, 7200.0)]
    assert found.windows
    # the summary read covers the covered sub-range, the scan reads the two remainders
    assert (3000.0, 6000.000001) in executor.bounds
    assert (0.0, 3000.0) in executor.bounds
    assert (6000.000001, 7200.0) in executor.bounds


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


class _FileExecutor:
    """Splunk-like: `head` is arrival order, so a pooled route never reaches every file."""

    def __init__(self, files: dict[str, list[dict[str, object]]]) -> None:
        self.files = files
        self.queries: list[str] = []
        self.skipped: list[tuple[str, str]] = []

    def rows_for(self, query: str) -> list[dict[str, object]]:
        named = set(re.findall(r'source="([^"]+)"', query))
        paths = [path for path in self.files if not named or path in named]
        rows = [row for path in paths for row in self.files[path]]
        return sorted(rows, key=lambda row: float(row["_time"]), reverse=True)

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind
        self.queries.append(query)
        inside = [row for row in self.rows_for(query) if start <= float(row["_time"]) < end]
        return Read(inside[: row_cap or len(inside)], False, None)

    def record_skipped_read(
        self, query: str, start: float, end: float, *, source_id=None, part=None, reason: str
    ) -> None:
        del start, end, source_id, part
        self.skipped.append((query, reason))


def _file_facts() -> tuple[SourceFacts, dict[str, list[dict[str, object]]]]:
    """21 files ranked by volume; the labelled one is 14th, so a pooled route never sees it."""
    files = {
        f"a{index:02d}": [
            {
                "_raw": f"a{index:02d} {number}",
                "_time": float(number),
                "host": "h1",
                "source": f"a{index:02d}",
            }
            for number in range(1_000 - index * 10)
        ]
        for index in range(21)
    }
    ranked = sorted(files, key=lambda path: (-len(files[path]), path))
    facts = SourceFacts(
        "ix",
        "st",
        sum(len(rows) for rows in files.values()),
        0.0,
        1_000.0,
        ("h1",),
        1,
        tuple(ranked),
        21,
        files=tuple(IndexFile(path, len(files[path]), ("h1",)) for path in ranked),
    )
    return facts, files


def test_every_indexed_file_is_read_with_its_own_head_not_by_arrival_order():
    facts, files = _file_facts()
    executor = _FileExecutor(files)
    labelled = "a13"
    pooled = read_windows(executor, facts, window_bounds(0.0, 1_000.0, 2), per_window=100, kind="x")
    assert not [row for row in pooled.rows if row["source"] == labelled]

    read = read_files(executor, facts, window_bounds(0.0, 1_000.0, 2), per_window=100, kind="x")

    assert {item.path for item in read.files} == set(files)
    assert all(item.rows > 0 for item in read.files)
    assert sum(item.rows for item in read.files if item.path == labelled) > 0
    assert any(f'source="{labelled}"' in query for query in executor.queries)
    assert len(read.rows) <= 100 * 2 + len(files) * 2  # today's row budget plus per-read rounding
    lines = _file_rows("ix:st", read)
    assert {line["path"] for line in lines} == set(files)
    assert all(line["events_available"] > 0 for line in lines)


def test_a_capped_read_declares_every_unread_file_with_its_reason():
    facts, files = _file_facts()
    executor = _FileExecutor(files)
    read = read_files(
        executor, facts, window_bounds(0.0, 1_000.0, 1), per_window=100, kind="x", max_files=3
    )

    omitted = [item for item in read.files if item.reason]
    assert len(omitted) == 18
    assert {item.reason for item in omitted} == {"read_files_cap"}
    assert len(executor.skipped) == 18
    assert all(reason == "read_files_cap" for _query, reason in executor.skipped)


class _EstateExecutor:
    """Answers the estate map's own tstats queries: volume, per-file rows, hosts, cadence."""

    def __init__(
        self,
        volume: list[dict[str, object]],
        sources: list[dict[str, object]],
        hosts: list[dict[str, object]],
    ) -> None:
        self.volume = volume
        self.sources = sources
        self.hosts = hosts
        self.queries: list[str] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del start, end, kind, row_cap
        self.queries.append(query)
        if "span=1d" in query:
            return Read([], False, None)
        if "by sourcetype source host" in query:
            return Read([dict(row) for row in self.sources], False, None)
        if "by sourcetype host" in query:
            return Read([dict(row) for row in self.hosts], False, None)
        return Read([dict(row) for row in self.volume], False, None)


def _file_row(path: str, host: str, count: int, first: float, last: float) -> dict[str, object]:
    return {
        "sourcetype": "stream:http",
        "source": path,
        "host": host,
        "count": str(count),
        "first": first,
        "last": last,
    }


def _estate_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    volume = [{"sourcetype": "stream:http", "count": "35", "first": 0.0, "last": 5000.0}]
    sources = [
        _file_row("/a/access.log", "web1", 20, 1000.0, 2199.0),
        _file_row("/a/access.log", "web2", 5, 3000.0, 4000.0),
        _file_row("/a/old.log", "web1", 10, 200.0, 900.0),
    ]
    return volume, sources


def test_estate_map_carries_each_files_own_time_range():
    volume, sources = _estate_rows()
    executor = _EstateExecutor(volume, sources, [{"sourcetype": "stream:http", "host": "web1"}])
    facts, _notes = index_facts(executor, "ix", 0.0, 5000.0)

    graded = {item.path: item for item in facts[0].files}["/a/access.log"]
    assert (graded.events, graded.first, graded.last) == (25, 1000.0, 4000.0)
    assert (graded.first, graded.last) != (facts[0].first, facts[0].last)

    source_queries = [query for query in executor.queries if "by sourcetype source host" in query]
    assert len(source_queries) == 1
    assert "min(_time) as first max(_time) as last" in source_queries[0]

    raw = card_facts(facts[0])
    assert {item["path"]: item for item in raw["files"]}["/a/access.log"]["first"] == 1000.0
    restored = _fact_dict(
        card_from_dict({"index": "ix", "sourcetype": "stream:http", "facts": raw})
    )
    back = {item.path: item for item in restored.files}["/a/access.log"]
    assert (back.first, back.last) == (1000.0, 4000.0)


def test_a_file_without_a_time_range_falls_back_to_its_source_span():
    facts = SourceFacts(
        "ix",
        "st",
        15,
        100.0,
        900.0,
        ("h1",),
        1,
        ("/a.log", "/b.log"),
        2,
        files=(IndexFile("/a.log", 10, ("h1",)), IndexFile("/b.log", 5, ("h1",), 700.0, 800.0)),
    )
    assert file_span(facts, facts.files[0]) == (facts.first, facts.last)
    assert file_span(facts, facts.files[1]) == (700.0, 800.0)


def test_the_estate_map_still_declares_no_files_when_the_counts_do_not_add_up():
    volume, sources = _estate_rows()
    volume[0]["count"] = "36"
    executor = _EstateExecutor(volume, sources, [])
    facts, notes = index_facts(executor, "ix", 0.0, 5000.0)

    assert facts[0].files == ()
    assert "files_incomplete:stream:http" in notes
