"""Index facts and deterministic raw samples: understanding reads a small fixed slice."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from ..engine import _search_literal
from ..executor import HuntBudgetExceededError, HuntExecutor

SAMPLE_WINDOWS = 3  # effort budget: raw reads spread across each source's own time range
SAMPLE_LINES = 40  # effort budget: events read per window for a source card
SAMPLE_SOURCES = 2  # effort budget: indexed sources sampled for one source card
ALERT_PROBE_LINES = 400  # effort budget: events read per window to detect an alert-bearing part
ALERT_TERM = 'event_type="alert"'  # the search term that selects a JSON detection event
BEHAVIOUR_SOURCES = 8  # effort budget: indexed sources one behaviour read covers
MAX_HOST_NAMES = 24  # effort budget: host names listed on one source's facts
# The results endpoint returns at most 50,000 rows per request; caps stay below it.
METADATA_ROWS = 40_000  # effort budget: sourcetype/source/host aggregate rows read
CADENCE_ROWS = 40_000  # effort budget: per-period sourcetype counts read for cadence
EMPTY_SAMPLE_WINDOWS = (
    48  # effort budget: fixed windows per source when its own time range is unknown
)


@dataclass(frozen=True)
class SourceFacts:
    """Cheap index facts about one sourcetype: volume, time range, hosts and sources."""

    index: str
    sourcetype: str
    events: int
    first: float
    last: float
    hosts: tuple[str, ...]
    host_count: int
    sources: tuple[str, ...]
    source_count: int
    active_periods: int = 0
    periods: int = 0
    count_cv: float = 0.0
    shared_sources: tuple[str, ...] = ()


@dataclass
class RowSet:
    """Rows read across a set of windows, with how the slice was chosen and cut."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    windows: int = 0
    route: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"rows": len(self.rows), "windows": self.windows, "route": self.route}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count(value: Any) -> int:
    number = _number(value)
    return int(number) if number is not None else 0


def _quoted(value: str) -> str:
    return _search_literal(value)


def window_bounds(first: float, last: float, count: int) -> list[tuple[float, float]]:
    """`count` equal slices of a source's own time range, earliest first."""
    if count <= 0:
        return []
    if last <= first:
        return [(first, first + 3600.0)]
    width = (last - first) / count
    return [(first + index * width, first + (index + 1) * width) for index in range(count)]


def _read_range(
    executor: HuntExecutor,
    query: str,
    start: float,
    end: float,
    *,
    kind: str,
    row_cap: int,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        result = executor.read(query, start, end, kind=kind, row_cap=row_cap)
    except HuntBudgetExceededError as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001 -- a failed read is recorded coverage, not a crash
        return [], f"read_failed:{type(exc).__name__}"
    return [dict(row) for row in result.rows], result.reason


def _meta_rows(
    executor: HuntExecutor, index: str, by: str, start: float, end: float
) -> tuple[list[dict[str, Any]], str | None]:
    query = f"| tstats count where index={_quoted(index)} {by}"
    return _read_range(executor, query, start, end, kind="discovery", row_cap=METADATA_ROWS)


def cadence_facts(
    executor: HuntExecutor, index: str, start: float, end: float
) -> tuple[dict[str, tuple[int, int, float]], list[str]]:
    """Per sourcetype: active days, days spanned and the variation of daily counts."""
    rows, reason = _read_range(
        executor,
        f"| tstats count where index={_quoted(index)} by sourcetype _time span=1d",
        start,
        end,
        kind="discovery",
        row_cap=CADENCE_ROWS,
    )
    notes = [f"cadence:{reason}"] if reason else []
    grouped: dict[str, list[tuple[float, int]]] = {}
    for row in rows:
        name = str(row.get("sourcetype") or "")
        if not name:
            continue
        stamp = _number(row.get("_time")) or 0.0
        grouped.setdefault(name, []).append((stamp, _count(row.get("count"))))
    found: dict[str, tuple[int, int, float]] = {}
    for name, series in grouped.items():
        series.sort()
        counts = [count for _stamp, count in series]
        active = sum(1 for count in counts if count > 0)
        span = max(1, int(round((series[-1][0] - series[0][0]) / 86400.0)) + 1)
        mean = sum(counts) / len(counts)
        if len(counts) < 2 or mean <= 0:
            cv = 0.0
        else:
            variance = sum((count - mean) ** 2 for count in counts) / len(counts)
            cv = (variance**0.5) / mean
        found[name] = (active, span, round(cv, 4))
    return found, notes


def _group_meta(
    rows: Iterable[Mapping[str, Any]], key: str, value: str
) -> dict[str, list[tuple[str, int]]]:
    grouped: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        owner = str(row.get(key) or "")
        name = str(row.get(value) or "")
        if not owner or not name:
            continue
        grouped.setdefault(owner, []).append((name, _count(row.get("count"))))
    return grouped


def index_facts(
    executor: HuntExecutor, index: str, start: float, end: float
) -> tuple[list[SourceFacts], list[str]]:
    """Volume, time range, hosts and indexed sources for every sourcetype in the index."""
    notes: list[str] = []
    volume, reason = _read_range(
        executor,
        f"| tstats count min(_time) as first max(_time) as last"
        f" where index={_quoted(index)} by sourcetype",
        start,
        end,
        kind="discovery",
        row_cap=METADATA_ROWS,
    )
    if reason:
        notes.append(f"volume_metadata:{reason}")
    if not volume:
        return [], notes + ["index_metadata_empty"]
    sources, source_reason = _meta_rows(executor, index, "by sourcetype source", start, end)
    hosts, host_reason = _meta_rows(executor, index, "by sourcetype host", start, end)
    cadence, cadence_notes = cadence_facts(executor, index, start, end)
    notes.extend(cadence_notes)
    for label, cause in (("source", source_reason), ("host", host_reason)):
        if cause:
            notes.append(f"{label}_metadata:{cause}")
    by_source = _group_meta(sources, "sourcetype", "source")
    by_host = _group_meta(hosts, "sourcetype", "host")
    owners: dict[str, set[str]] = {}
    for owner, names in by_source.items():
        for name, _ in names:
            owners.setdefault(name.casefold(), set()).add(owner)
    facts: list[SourceFacts] = []
    for row in sorted(volume, key=lambda item: str(item.get("sourcetype") or "")):
        name = str(row.get("sourcetype") or "")
        if not name:
            continue
        ranked_sources = sorted(by_source.get(name, []), key=lambda item: (-item[1], item[0]))
        ranked_hosts = sorted(by_host.get(name, []), key=lambda item: (-item[1], item[0]))
        active, span, cv = cadence.get(name, (0, 0, 0.0))
        facts.append(
            SourceFacts(
                index=index,
                sourcetype=name,
                events=_count(row.get("count")),
                first=_number(row.get("first")) or start,
                last=_number(row.get("last")) or end,
                hosts=tuple(host for host, _ in ranked_hosts[:MAX_HOST_NAMES]),
                host_count=len(ranked_hosts),
                sources=tuple(source for source, _ in ranked_sources),
                source_count=len(ranked_sources),
                active_periods=active,
                periods=span,
                count_cv=cv,
                shared_sources=tuple(
                    src for src, _ in ranked_sources if len(owners[src.casefold()]) > 1
                ),
            )
        )
    return facts, notes


def route_filter(facts: SourceFacts, max_sources: int = SAMPLE_SOURCES) -> tuple[str, str]:
    """Filter that selects this source's events: indexed sources where known, else the name."""
    selected = facts.sources[:max_sources]
    if selected:
        predicates = " OR ".join(f"source={_quoted(name)}" for name in selected)
        route = f"({predicates})"
        if set(selected).intersection(facts.shared_sources):
            route = f"sourcetype={_quoted(facts.sourcetype)} {route}"
        return route, "source"
    return f"sourcetype={_quoted(facts.sourcetype)}", "sourcetype"


def read_windows(
    executor: HuntExecutor,
    facts: SourceFacts,
    windows: Sequence[tuple[float, float]],
    *,
    per_window: int,
    kind: str,
    max_sources: int = SAMPLE_SOURCES,
    sub_windows: int = 1,
) -> RowSet:
    """Read the newest `per_window` events of each equal time slice, concurrently.

    The slice is the declared, deterministic sample: the source's own range cut into
    equal windows, newest events first inside each. Nothing is extrapolated beyond it.
    `sub_windows` > 1 splits each slice and reads the newest share of every part, so a
    high-volume source is sampled at several points in the slice instead of only its tail.
    """
    route, route_name = route_filter(facts, max_sources)
    readable = [bounds for bounds in windows if bounds[1] > bounds[0]]
    parts = max(1, sub_windows)
    slice_bounds: list[tuple[float, float]] = []
    for start, end in readable:
        slice_bounds.extend(window_bounds(start, end, parts))
    per_part = max(1, per_window // parts)
    query = f"search index={_quoted(facts.index)} {route} | head {per_part}"
    found = RowSet(windows=len(readable), route=route_name)
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(slice_bounds) or 1, concurrency)) as pool:
        futures = [
            pool.submit(_read_range, executor, query, start, end, kind=kind, row_cap=per_part)
            for start, end in slice_bounds
        ]
        for future in futures:
            rows, reason = future.result()
            found.rows.extend(rows)
            if reason:
                found.notes.append(reason)
    found.rows.sort(
        key=lambda row: (
            _number(row.get("_time")) or 0.0,
            str(row.get("host") or ""),
            str(row.get("_raw") or ""),
        )
    )
    return found


def sample_windows(facts: SourceFacts) -> list[tuple[float, float]]:
    """The windows a source card samples: its own range, or a fixed recent span."""
    if facts.last > facts.first:
        return window_bounds(facts.first, facts.last, SAMPLE_WINDOWS)
    now = time.time()
    return window_bounds(now - EMPTY_SAMPLE_WINDOWS * 3600.0, now, SAMPLE_WINDOWS)


def read_alert_rows(
    executor: HuntExecutor, facts: SourceFacts, *, per_window: int = ALERT_PROBE_LINES
) -> RowSet:
    """Read a source's detection events directly by the marker that makes them detections."""
    route, route_name = route_filter(facts, SAMPLE_SOURCES)
    query = f"search index={_quoted(facts.index)} {route} {ALERT_TERM} | head {per_window}"
    rows, reason = _read_range(
        executor, query, facts.first, facts.last, kind="alert_probe", row_cap=per_window
    )
    return RowSet([dict(row) for row in rows], 1, route_name, [reason] if reason else [])


__all__ = [
    "ALERT_TERM",
    "RowSet",
    "SourceFacts",
    "cadence_facts",
    "index_facts",
    "read_alert_rows",
    "read_windows",
    "route_filter",
    "sample_windows",
    "window_bounds",
]
