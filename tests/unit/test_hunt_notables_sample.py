from __future__ import annotations

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.sample import (
    SourceFacts,
    read_windows,
    route_filter,
    sample_windows,
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
