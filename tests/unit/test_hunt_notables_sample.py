from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from portal.modules.security.core.hunt.executor import (
    REQUEST_BUDGET_EXHAUSTED,
    HuntBudget,
    HuntExecutor,
    Read,
)
from portal.modules.security.core.hunt.notables.behaviours import _file_rows
from portal.modules.security.core.hunt.notables.cards import _facts as card_facts
from portal.modules.security.core.hunt.notables.run import _fact_dict, card_from_dict
from portal.modules.security.core.hunt.notables.sample import (
    DENSITY_PROBE_MAX,
    IndexFile,
    Localisation,
    LocalWindow,
    SourceFacts,
    file_route,
    file_span,
    index_facts,
    localise,
    read_alert_rows,
    read_anchors,
    read_card_sample,
    read_files,
    read_mode,
    read_windows,
    route_filter,
    sample_files,
    sample_windows,
    search_sourcetype_of,
    select_local_windows,
    source_route,
    sourcetype_renames,
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
    assert found.accel_window == (0.0, 7201.0)
    assert len(found.windows) == 1 and found.windows[0].events == 484
    assert not any(query.startswith("| tstats count where") for query in executor.queries)


def test_a_range_outside_the_acceleration_window_is_localised_by_a_scan_not_empty():
    executor = _SummaryExecutor((0.0, 500.0), _burst_series(300, 24, 21, 121, 4))
    found = localise(executor, "ix", 600.0, 7200.0)

    assert found.mechanism == "indexed"
    assert found.coverage == "scan"
    assert found.accel_window == (0.0, 501.0)
    assert len(found.windows) == 1
    assert any(query.startswith("| tstats count where") for query in executor.queries)


def test_a_partially_covered_source_declares_the_covered_and_scanned_ranges():
    executor = _SummaryExecutor((3000.0, 6000.0), _burst_series(300, 24, 21, 121, 4))
    found = localise(executor, "ix", 0.0, 7200.0)

    assert found.mechanism == "accelerated_partial"
    assert found.model == "Authentication"
    assert found.coverage == "accelerated_partial"
    assert found.covered_window == (3000.0, 6001.0)
    assert found.scanned_window == [(0.0, 3000.0), (6001.0, 7200.0)]
    assert found.windows
    # the summary read covers the covered sub-range, the scan reads the two remainders
    assert (3000.0, 6001.0) in executor.bounds
    assert (0.0, 3000.0) in executor.bounds
    assert (6001.0, 7200.0) in executor.bounds


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
        if query.startswith("| tstats"):
            return Read([{"count": str(len(inside))}], False, None)
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
    # each file is capped per read by what its own window holds, not by its share of the source
    assert len(read.rows) <= 100 * 2 * len(files)
    assert sum(item.rows for item in read.files if item.path == "a00") == 200
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


def _wide_file_facts() -> SourceFacts:
    return SourceFacts(
        "ix", "st", 500, 0.0, 1_000.0, ("h1",), 1, ("a",), 1, files=(IndexFile("a", 500, ("h1",)),)
    )


def _card_sample_facts() -> tuple[SourceFacts, dict[str, list[dict[str, object]]]]:
    """26 files on 4 hosts, kyoushi-shaped: the graded intranet file holds no newest events."""
    files: dict[str, list[dict[str, object]]] = {}
    stamp = 0.0
    for index in range(26):
        kind, host = (
            ("intranet", "intranet_server"),
            ("horde", "acme_mail"),
            ("mail", "webserver"),
            ("cloud", "cloud_share"),
        )[index % 4]
        path = f"/apache2/{kind}.company.log.{index // 4}"
        if path in files:
            path = f"/apache2/{kind}.company.log"
        files.setdefault(
            path, _rows_of(path, host, [stamp + number for number in range(0, 1_000, 20)])
        )
        stamp += 0.1
    ranked = sorted(files, key=lambda path: (-len(files[path]), path))
    facts = SourceFacts(
        "ix",
        "access_combined",
        sum(len(rows) for rows in files.values()),
        0.0,
        1_000.0,
        ("intranet_server", "acme_mail", "webserver", "cloud_share"),
        4,
        tuple(ranked),
        26,
        files=tuple(
            IndexFile(path, len(files[path]), (files[path][0]["host"],)) for path in ranked
        ),
    )
    return facts, files


def test_a_card_sample_spreads_across_files_and_hosts():
    facts, files = _card_sample_facts()
    windows = window_bounds(0.0, 1_000.0, 3)
    pooled_executor = _FileExecutor(files)
    pooled = read_windows(pooled_executor, facts, windows, per_window=40, kind="source_sample")
    collapse = {str(row["host"]) for row in pooled.rows}
    # today: a pooled head only reaches the route's top-2 files, so most hosts go unsampled
    assert "intranet_server" not in collapse
    assert len(collapse) <= 2

    executor = _FileExecutor(files)
    read = read_card_sample(executor, facts, kind="source_sample")

    read_hosts = {str(row["host"]) for row in read.rows}
    assert {"intranet_server", "acme_mail", "webserver", "cloud_share"} <= read_hosts
    files_read = {item.path for item in read.files if item.rows}
    assert len(files_read) > 2
    assert any("intranet" in path for path in files_read)
    assert len(executor.queries) == 6
    spread = sample_files(facts)
    assert spread == sample_files(facts)
    assert [item.path for item in read.files] == [item.path for item in spread]


def test_a_single_file_source_still_samples_through_the_pooled_read():
    facts = SourceFacts("ix", "st", 90, 0.0, 100.0, ("h1",), 1, ("s1",), 1)
    executor = _NewestExecutor(_rows())
    read = read_card_sample(executor, facts, kind="source_sample")
    assert read.rows
    assert len(executor.calls) == 3  # the three pooled windows, not one request per file


def test_a_zero_row_file_read_declares_an_empty_window() -> None:
    read = read_files(
        _NewestExecutor(_rows()),
        _wide_file_facts(),
        [(2_000.0, 3_000.0)],
        per_window=100,
        kind="x",
    )

    assert read.files
    assert all(item.rows == 0 for item in read.files)
    assert {item.reason for item in read.files} == {"empty_window"}


class _RefusingSearch:
    """A transport that never answers: the shared request ceiling refuses before it can."""

    executor: HuntExecutor | None = None

    def iter_post_bounded(
        self,
        query: str,
        start: float,
        end: float,
        *,
        timeout_seconds: float = 0,
        max_results: int | None = None,
    ) -> list[dict[str, object]]:
        del query, start, end, timeout_seconds, max_results
        return []


def test_a_budget_refused_read_writes_a_ledger_row(tmp_path: Path) -> None:
    from portal.modules.security.core.hunt.notables.run import configure_ledger

    search = _RefusingSearch()
    budget = HuntBudget(
        {"query_seconds": 30.0, "job_seconds": 60.0, "requests": 0, "cells": 10, "events": 10}
    )
    search.executor = HuntExecutor(search, budget)
    executor = configure_ledger(search, tmp_path, "behaviours")

    read = read_files(executor, _wide_file_facts(), [(0.0, 1_000.0)], per_window=100, kind="x")

    assert {item.reason for item in read.files} == {"request_budget_exhausted"}
    ledger = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    # the refused window read is declared, and its density probe is priced away before it
    # can spend: no tstats request is issued the ceiling cannot pay for
    assert [row["reason"] for row in ledger] == ["request_budget_exhausted"]
    assert not any(row["query"].startswith("| tstats") for row in ledger)


def test_a_read_from_a_covering_summary_reports_accelerated_coverage() -> None:
    from portal.modules.security.core.hunt.notables.behaviours import read_behaviour_source

    located = Localisation(
        windows=[LocalWindow("h1", 300.0, 600.0, 1_000)],
        mechanism="accelerated",
        model="Web",
        accel_window=(0.0, 600.000001),
        coverage="accelerated",
    )
    facts = SourceFacts("ix", "st", 55_000_000, 0.0, 600.0, ("h1",), 1, ("s1",), 1)
    executor = _QueryExecutor([{"_time": 350.0, "host": "h1", "count": 1}])

    merged = read_behaviour_source(
        executor,
        facts,
        per_window=10,
        anchors=located.windows,
        accel_window=located.accel_window,
        coverage=located.coverage,
    )
    direct = read_anchors(
        executor,
        facts,
        located.windows,
        per_window=10,
        kind="x",
        accel_window=located.accel_window,
        coverage=located.coverage,
    )

    assert merged.coverage == "accelerated"
    assert merged.accel_window == located.accel_window
    assert direct.coverage == "accelerated"


class _DensityExecutor:
    """Splunk-like: honour source/host/time filters, answer `tstats count`, head newest-first."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, float, float, int | None]] = []
        self.skipped: list[tuple[str, str]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind
        self.calls.append((query, start, end, row_cap))
        inside = [row for row in self.rows if start <= float(row["_time"]) < end]
        for path in re.findall(r'source="([^"]+)"', query):
            inside = [row for row in inside if row["source"] == path]
        for host in re.findall(r'host="([^"]+)"', query):
            inside = [row for row in inside if row["host"] == host]
        if query.startswith("| tstats"):
            return Read([{"count": str(len(inside))}], False, None)
        inside.sort(key=lambda row: float(row["_time"]), reverse=True)
        return Read([dict(row) for row in inside[: row_cap or len(inside)]], False, None)

    def row_reads(self) -> list[tuple[str, float, float, int | None]]:
        return [call for call in self.calls if not call[0].startswith("| tstats")]

    def record_skipped_read(
        self, query: str, start: float, end: float, *, source_id=None, part=None, reason: str
    ) -> None:
        del start, end, source_id, part
        self.skipped.append((query, reason))


def _rows_of(path: str, host: str, times: list[float]) -> list[dict[str, object]]:
    return [
        {"_raw": f"{path} {stamp}", "_time": stamp, "host": host, "source": path} for stamp in times
    ]


def test_a_files_windows_land_on_the_files_own_burst_not_the_sources():
    burst = [3400.0 + number * 1.0 for number in range(60)]
    facts = SourceFacts(
        "ix",
        "st",
        13_000,
        0.0,
        5_000.0,
        ("web1",),
        1,
        ("/a", "/b"),
        2,
        files=(
            IndexFile("/a", 9_000, ("web1",), 3000.0, 4000.0),
            IndexFile("/b", 4_000, ("web1",), 0.0, 5000.0),
        ),
    )
    executor = _DensityExecutor(
        _rows_of("/a", "web1", burst)
        + _rows_of("/b", "web1", [float(n) for n in range(0, 5000, 5)])
    )
    read_files(executor, facts, window_bounds(0.0, 5_000.0, 3), per_window=2_500, kind="x")

    planned = [call for call in executor.row_reads() if 'source="/a"' in call[0]]
    assert planned
    assert min(start for _query, start, _end, _cap in planned) == 3000.0
    assert all(start >= 3000.0 and end <= 4001.0 for _query, start, end, _cap in planned)
    assert any(start <= 3400.0 and end > 3459.0 for _query, start, end, _cap in planned)


def test_a_file_is_never_read_with_a_host_it_is_not_on():
    facts = SourceFacts(
        "ix",
        "st",
        1_200,
        0.0,
        1_000.0,
        ("web1", "web2"),
        2,
        ("/a", "/b", "/c"),
        3,
        files=(
            IndexFile("/a", 500, ("web1",), 0.0, 1000.0),
            IndexFile("/b", 500, ("web2",), 0.0, 1000.0),
            IndexFile("/c", 200, (), 0.0, 1000.0),
        ),
    )
    executor = _DensityExecutor(
        _rows_of("/a", "web1", [float(n) for n in range(500)])
        + _rows_of("/b", "web2", [float(n) for n in range(500)])
        + _rows_of("/c", "web1", [float(n) for n in range(200)])
    )
    read = read_files(
        executor, facts, window_bounds(0.0, 1_000.0, 2), per_window=2_500, kind="x", host="web1"
    )

    issued = executor.row_reads()
    assert issued
    assert all('host="web1"' in query for query, _start, _end, _cap in issued if "/a" in query)
    assert not any('source="/b"' in query for query, _start, _end, _cap in issued)
    receipts = {item.path: item for item in read.files}
    assert receipts["/a"].host == "web1"
    assert (receipts["/b"].host, receipts["/b"].reason) == ("", "host_mismatch")
    assert (receipts["/c"].host, receipts["/c"].reason) == ("", "")
    assert any('source="/c"' in query and "host=" not in query for query, _s, _e, _c in issued)
    assert "host_mismatch" in {reason for _query, reason in executor.skipped}


def test_a_files_head_reflects_the_windows_density_not_its_source_share():
    stamped = [2500.0 + number * 0.1 for number in range(2_600)]
    facts = SourceFacts(
        "ix",
        "st",
        1_000_000,
        0.0,
        3000.0,
        ("h1",),
        1,
        ("/a", "/huge"),
        2,
        files=(
            IndexFile("/a", 6_000, ("h1",), 0.0, 3000.0),
            IndexFile("/huge", 994_000, ("h1",), 0.0, 3000.0),
        ),
    )
    executor = _DensityExecutor(_rows_of("/a", "h1", stamped))
    read = read_files(
        executor, facts, window_bounds(0.0, 3000.0, 2), per_window=2_500, kind="x", sub_windows=2
    )

    heads = [cap for query, _start, _end, cap in executor.row_reads() if 'source="/a"' in query]
    assert max(head or 0 for head in heads) == 2_500  # the window's own count, not a 0.6% share
    rows = sum(item.rows for item in read.files if item.path == "/a")
    assert rows == 2_500 >= min(6_000, 2_500)


def test_the_last_slice_of_a_file_is_always_planned():
    facts = SourceFacts(
        "ix",
        "st",
        9_000,
        0.0,
        4_000.0,
        ("h1",),
        1,
        ("/a", "/b"),
        2,
        files=(
            IndexFile("/a", 5_000, ("h1",), 1000.0, 4000.0),
            IndexFile("/b", 4_000, ("h1",)),
        ),
    )
    executor = _DensityExecutor(_rows_of("/a", "h1", [float(n) for n in range(1000, 1100)]))
    read_files(executor, facts, window_bounds(0.0, 4_000.0, 6), per_window=2_500, kind="x")

    planned = [
        (start, end) for query, start, end, _cap in executor.row_reads() if 'source="/a"' in query
    ]
    assert (3000.0, 4001.0) in planned  # the file's own tail slice, last event included
    assert any(start <= 4000.0 < end for start, end in planned)

    fallback = [
        (start, end) for query, start, end, _cap in executor.row_reads() if 'source="/b"' in query
    ]
    assert window_bounds(0.0, 4_000.0, 6)[-1][0] in {start for start, _end in fallback}


def _ceiling(remaining: int | None = None, concurrency: int = 4) -> SimpleNamespace:
    """A budget stub: the request ceiling a plan is priced against, and the read slots."""
    budget = SimpleNamespace(concurrency=concurrency)
    if remaining is not None:
        budget.remaining_requests = lambda: remaining
    return budget


def test_windows_dropped_by_the_request_ceiling_issue_no_density_probe() -> None:
    """The (file, window) plan is priced before any probe: a dropped window spends nothing."""
    rows = _rows_of("/a", "h1", [float(n) for n in range(500)]) + _rows_of(
        "/b", "h1", [float(n) for n in range(400)]
    )
    facts = SourceFacts(
        "ix",
        "st",
        900,
        0.0,
        1_000.0,
        ("h1",),
        1,
        ("/a", "/b"),
        2,
        files=(
            IndexFile("/a", 500, ("h1",), 0.0, 1_000.0),
            IndexFile("/b", 400, ("h1",), 0.0, 1_000.0),
        ),
    )
    executor = _DensityExecutor(rows)
    executor.budget = _ceiling(remaining=4)  # pays for two probed reads, never six

    read = read_files(executor, facts, window_bounds(0.0, 1_000.0, 3), per_window=100, kind="x")

    probes = [call for call in executor.calls if call[0].startswith("| tstats")]
    assert len(probes) == 2  # the two newest /a windows kept: one probe each, none for /b
    assert all('source="/a"' in query for query, _s, _e, _c in probes)
    dropped = [item for item in read.files if item.reason == REQUEST_BUDGET_EXHAUSTED]
    assert len(dropped) == 4  # /a's oldest window and every /b window
    assert {item.path for item in dropped} == {"/a", "/b"}
    assert not any('source="/b"' in call[0] for call in executor.calls)
    assert len(executor.skipped) == 4  # every dropped window declared through the ledger


class _ConcurrentDensity(_DensityExecutor):
    """Counts overlapping tstats probes: a batch, not a serial queue."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__(rows)
        self.budget = _ceiling()
        self._lock = threading.Lock()
        self._in_flight = 0
        self.probe_peak = 0

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        if query.startswith("| tstats"):
            with self._lock:
                self._in_flight += 1
                self.probe_peak = max(self.probe_peak, self._in_flight)
            time.sleep(0.05)
            with self._lock:
                self._in_flight -= 1
        return super().read(query, start, end, kind=kind, row_cap=row_cap)


def test_density_probes_batch_concurrently_instead_of_queueing_serially() -> None:
    """Kept windows probe together: 181 files never issue 543 one-at-a-time counts."""
    rows = _rows_of("/a", "h1", [float(n) for n in range(500)])
    facts = SourceFacts(
        "ix",
        "st",
        500,
        0.0,
        1_000.0,
        ("h1",),
        1,
        ("/a",),
        1,
        files=(IndexFile("/a", 500, ("h1",), 0.0, 1_000.0),),
    )
    executor = _ConcurrentDensity(rows)

    read = read_files(executor, facts, window_bounds(0.0, 1_000.0, 3), per_window=100, kind="x")

    assert executor.probe_peak >= 2  # three probed windows overlapped: batched, not serial
    assert read.files


def test_a_small_file_issues_no_density_probe() -> None:
    """A file within one window's ceiling is read whole: its density is already known."""
    rows = _rows_of("/small", "h1", [float(n) for n in range(50)]) + _rows_of(
        "/big", "h1", [float(n) for n in range(500)]
    )
    facts = SourceFacts(
        "ix",
        "st",
        550,
        0.0,
        1_000.0,
        ("h1",),
        1,
        ("/small", "/big"),
        2,
        files=(
            IndexFile("/small", 50, ("h1",), 0.0, 1_000.0),
            IndexFile("/big", 500, ("h1",), 0.0, 1_000.0),
        ),
    )
    executor = _DensityExecutor(rows)
    executor.budget = _ceiling()

    read = read_files(executor, facts, window_bounds(0.0, 1_000.0, 2), per_window=100, kind="x")

    probes = [call for call in executor.calls if call[0].startswith("| tstats")]
    assert probes  # the large file's windows are still probed
    assert all('source="/big"' in query for query, _s, _e, _c in probes)
    assert not any('source="/small"' in query for query, _s, _e, _c in probes)
    assert any('source="/small"' in query for query, _s, _e, _c in executor.row_reads())
    assert {item.path for item in read.files} == {"/small", "/big"}


def test_a_wide_estate_caps_its_density_probes() -> None:
    """Only the largest files' windows probe; every window still reads at its planned cap."""
    files = tuple(
        IndexFile(f"/f{number}", 500 + number, ("h1",), 0.0, 1_000.0) for number in range(8)
    )
    facts = SourceFacts(
        "ix",
        "st",
        sum(item.events for item in files),
        0.0,
        1_000.0,
        ("h1",),
        1,
        tuple(item.path for item in files),
        len(files),
        files=files,
    )
    executor = _DensityExecutor(
        sum((_rows_of(item.path, "h1", [float(n) for n in range(1_000)]) for item in files), [])
    )
    executor.budget = _ceiling()

    read = read_files(executor, facts, window_bounds(0.0, 1_000.0, 3), per_window=100, kind="x")

    probes = [call for call in executor.calls if call[0].startswith("| tstats")]
    assert len(probes) == DENSITY_PROBE_MAX  # capped, not one per window of 24
    assert all('source="/f7"' in query or 'source="/f6"' in query for query, _s, _e, _c in probes)
    assert len(read.files) == 8 * 3  # every planned window still read, heads at planned caps
    assert not any(item.reason for item in read.files)


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
        if "| rest" in query:
            return Read([], False, None)
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


class _RenamedSplunk:
    """A Splunk that renames at search time: tstats answers one name, raw search the other."""

    def __init__(
        self,
        volume: list[dict[str, object]],
        renames: list[dict[str, object]] | None = None,
        rows: list[dict[str, object]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.volume = volume
        self.renames = renames or []
        self.rows = rows or []
        self.error = error
        self.queries: list[str] = []
        self.bounds: list[tuple[float, float]] = []

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del kind
        self.queries.append(query)
        self.bounds.append((start, end))
        if "| rest" in query:
            if self.error is not None:
                raise self.error
            return Read([dict(row) for row in self.renames], False, None)
        if "by sourcetype source host" in query or "by sourcetype host" in query:
            return Read([], False, None)
        if "span=1d" in query:
            return Read([], False, None)
        if "min(_time) as first max(_time) as last" in query:
            return Read([dict(row) for row in self.volume], False, None)
        inside = [row for row in self.rows if start <= float(row["_time"]) < end]
        if query.startswith("| tstats"):
            for name in re.findall(r'sourcetype="([^"]+)"', query):
                inside = [row for row in inside if row.get("indexed_sourcetype") == name]
            for path in re.findall(r'source="([^"]+)"', query):
                inside = [row for row in inside if row.get("source") == path]
            return Read([{"count": str(len(inside))}], False, None)
        for name in re.findall(r'sourcetype="([^"]+)"', query):
            inside = [row for row in inside if row.get("sourcetype") == name]
        for path in re.findall(r'source="([^"]+)"', query):
            inside = [row for row in inside if row.get("source") == path]
        inside.sort(key=lambda row: float(row["_time"]), reverse=True)
        return Read([dict(row) for row in inside[: row_cap or len(inside)]], False, None)


_RENAMES = [
    {"title": "WinEventLog:Security", "rename": "WinEventLog"},
    {"title": "fgt_traffic", "rename": "fortigate_traffic"},
    {"title": "identical", "rename": "identical"},  # a stanza renaming to itself: not a rename
    {"title": "", "rename": "blank_title"},  # blank stanzas carry no usable name
    {"title": "blank_rename", "rename": ""},
]


def _renamed_volume() -> list[dict[str, object]]:
    return [
        {"sourcetype": "WinEventLog:Security", "count": "9", "first": 0.0, "last": 100.0},
        {"sourcetype": "wineventlog:security", "count": "3", "first": 0.0, "last": 100.0},
        {"sourcetype": "fgt_traffic", "count": "5", "first": 0.0, "last": 100.0},
    ]


def _renamed_rows(source: str = "/sec") -> list[dict[str, object]]:
    return [
        {
            "_time": 10.0 + number,
            "host": "h1",
            "source": source,
            "sourcetype": "WinEventLog",
            "indexed_sourcetype": "WinEventLog:Security",
            "_raw": f"event {number}",
        }
        for number in range(5)
    ]


def test_props_renames_are_discovered_live_and_matched_caselessly():
    executor = _RenamedSplunk(_renamed_volume(), _RENAMES, _renamed_rows())
    facts, notes = index_facts(executor, "ix", 0.0, 100.0)

    assert notes == []
    by_name = {item.sourcetype: item for item in facts}
    assert by_name["WinEventLog:Security"].search_sourcetype == "WinEventLog"
    assert by_name["wineventlog:security"].search_sourcetype == "WinEventLog"
    assert by_name["fgt_traffic"].search_sourcetype == "fortigate_traffic"
    assert by_name["fgt_traffic"].sourcetype == "fgt_traffic"  # the indexed name is untouched
    discovery = [query for query in executor.queries if "| rest" in query]
    assert discovery == [
        "| rest splunk_server=local /servicesNS/-/-/configs/conf-props"
        " | search rename=* | table title rename"
    ]


def test_sourcetype_renames_returns_the_folded_map_without_blank_or_identical_stanzas():
    found, notes = sourcetype_renames(_RenamedSplunk(_renamed_volume(), _RENAMES, _renamed_rows()))

    assert notes == []
    assert found == {
        "wineventlog:security": "WinEventLog",
        "fgt_traffic": "fortigate_traffic",
    }


def test_a_denied_rename_discovery_never_fails_the_estate_map():
    executor = _RenamedSplunk(
        _renamed_volume(), _RENAMES, _renamed_rows(), error=RuntimeError("denied")
    )
    found, notes = sourcetype_renames(executor)

    assert found == {}
    assert notes == ["sourcetype_renames:read_failed:RuntimeError"]

    facts, notes = index_facts(executor, "ix", 0.0, 100.0)
    assert facts
    assert all(item.search_sourcetype == "" for item in facts)
    assert "sourcetype_renames:read_failed:RuntimeError" in notes


def test_route_builders_emit_the_search_time_name_for_raw_search():
    facts = SourceFacts(
        "ix",
        "WinEventLog:Security",
        4,
        0.0,
        100.0,
        ("h1",),
        1,
        ("/sec", "/sec2"),
        2,
        shared_sources=("/sec", "/sec2"),
        search_sourcetype="WinEventLog",
    )

    route, name = route_filter(facts)
    assert route == 'sourcetype="WinEventLog" (source="/sec" OR source="/sec2")'
    assert name == "source"
    indexed_route, _ = source_route(facts.sourcetype, [], ())
    assert indexed_route == 'sourcetype="WinEventLog:Security"'
    assert file_route(facts, "/sec") == 'sourcetype="WinEventLog" source="/sec"'
    scoped = file_route(facts, "/sec", indexed=True)
    assert scoped == 'sourcetype="WinEventLog:Security" source="/sec"'
    assert search_sourcetype_of(facts) == "WinEventLog"
    unrenamed = SourceFacts("ix", "st", 1, 0.0, 1.0, (), 0, (), 0)
    assert search_sourcetype_of(unrenamed) == "st"


def test_raw_reads_use_the_search_time_name_and_tstats_keeps_the_indexed_name():
    facts = SourceFacts(
        "ix",
        "WinEventLog:Security",
        5_000,
        0.0,
        100.0,
        ("h1",),
        1,
        ("/big",),
        1,
        shared_sources=("/big",),
        files=(IndexFile("/big", 5_000, ("h1",), 0.0, 100.0),),
        search_sourcetype="WinEventLog",
    )
    executor = _RenamedSplunk(_renamed_volume(), _RENAMES, _renamed_rows("/big"))

    windows = window_bounds(0.0, 100.0, 3)
    pooled = read_windows(executor, facts, windows, per_window=100, kind="x")
    assert pooled.rows
    pooled_reads = [query for query in executor.queries if query.startswith("search")]
    assert all('sourcetype="WinEventLog"' in query for query in pooled_reads)

    card = read_card_sample(executor, facts, kind="x")
    assert card.rows

    spread = read_files(executor, facts, windows, per_window=100, kind="x")
    assert spread.rows
    probes = [query for query in executor.queries if query.startswith("| tstats")]
    assert probes
    assert all('sourcetype="WinEventLog:Security"' in query for query in probes)
    assert not any('sourcetype="WinEventLog"' in query for query in probes)
    raw_reads = [query for query in executor.queries if query.startswith("search")]
    assert all('sourcetype="WinEventLog"' in query for query in raw_reads)
    assert not any("WinEventLog:Security" in query for query in raw_reads)


def test_a_single_second_source_spans_a_whole_second_in_splunk_bounds():
    stamp = 1_643_118_128.0
    facts = SourceFacts("ix", "st", 5, stamp, stamp, (), 0, (), 0)
    windows = sample_windows(facts)
    assert windows == [(stamp, stamp + 1.0)]

    executor = _NewestExecutor([{"_time": stamp, "_raw": "one", "host": "h1"}])
    read = read_alert_rows(executor, facts)
    assert executor.calls == [(stamp, stamp + 1.0, 400)]
    assert read.notes == []


def test_card_facts_carry_the_search_time_name_only_when_it_differs():
    renamed = SourceFacts(
        "ix",
        "WinEventLog:Security",
        4,
        0.0,
        100.0,
        ("h1",),
        1,
        ("/sec",),
        1,
        search_sourcetype="WinEventLog",
    )
    raw = card_facts(renamed)
    assert raw["search_sourcetype"] == "WinEventLog"
    restored = _fact_dict(
        card_from_dict({"index": "ix", "sourcetype": "WinEventLog:Security", "facts": raw})
    )
    assert search_sourcetype_of(restored) == "WinEventLog"

    plain = card_facts(SourceFacts("ix", "st", 1, 0.0, 1.0, (), 0, (), 0))
    assert "search_sourcetype" not in plain
