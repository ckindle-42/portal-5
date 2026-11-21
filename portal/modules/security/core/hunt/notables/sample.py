"""Index facts and deterministic raw samples: understanding reads a small fixed slice."""

from __future__ import annotations

import math
import statistics
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
WHOLE_READ_MAX_EVENTS = 10_000_000  # a wider source is localised before it is read
LOCALISE_MIN_WIDTH = 300  # effort budget: finest tstats span the localiser considers
LOCALISE_MAX_WIDTH = 3600  # effort budget: coarsest span that still separates a short burst
LOCALISE_BUCKETS = 288  # effort budget: time buckets one localiser aggregates a range into
LOCALISE_ROWS = 40_000  # effort budget: host/time bucket rows read by one localiser
LOCALISE_WINDOWS = 4  # effort budget: peak windows one anchored read narrows to
LOCALISE_Z = 2.0  # a bucket is a peak this many robust deviations above the source baseline
# The CIM models the hunt setup app accelerates (runbook stage 3); a summary read is only
# preferred over the index aggregate when one of these covers the whole searched range.
ACCEL_MODELS = (
    "Authentication",
    "Endpoint",
    "Intrusion_Detection",
    "Network_Resolution",
    "Network_Traffic",
    "Web",
)
ACCEL_PROBE_ROWS = 100  # effort budget: window rows one accelerated-model probe reads


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
    selection: str = "newest events of each equal time slice"
    query: str = ""
    read_mode: str = ""  # whole | anchored | sampled
    rung: str = ""  # whole | indexed_aggregate | narrowed_scan | equal_slice
    events_scanned: int = 0
    coverage: str = ""  # whole | accelerated | scan (never "empty")
    accel_window: tuple[float, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": len(self.rows),
            "windows": self.windows,
            "route": self.route,
            "read_mode": self.read_mode,
            "rung": self.rung,
            "events_scanned": self.events_scanned,
            "coverage": self.coverage,
        }


@dataclass(frozen=True)
class LocalWindow:
    """One host/time bucket the indexed aggregate says carries the events: where and when."""

    host: str
    start: float
    end: float
    events: int


@dataclass(frozen=True)
class AccelSummary:
    """One accelerated model's summary coverage for an index: the range it can answer."""

    model: str
    window: tuple[float, float]


@dataclass
class Localisation:
    """Where a read's windows came from: a summary, the index aggregate, or neither."""

    windows: list[LocalWindow] = field(default_factory=list)
    mechanism: str = ""  # accelerated | indexed | ""
    model: str = ""
    accel_window: tuple[float, float] | None = None
    coverage: str = "scan"  # accelerated | scan
    notes: list[str] = field(default_factory=list)


def read_mode(events: int, *, whole_budget: int = WHOLE_READ_MAX_EVENTS) -> str:
    """A whole-range read is allowed only for a source small enough to finish in one pass."""
    return "whole" if events <= whole_budget else "anchored"


def localise_width(span: float) -> float:
    """The finest span that keeps a source's range inside the localiser's bucket budget."""
    if span <= 0:
        return float(LOCALISE_MIN_WIDTH)
    width = round(span / LOCALISE_BUCKETS)
    return float(min(LOCALISE_MAX_WIDTH, max(LOCALISE_MIN_WIDTH, width)))


def coverage_label(accel_window: Sequence[float] | None, start: float, end: float) -> str:
    """`accelerated` only inside a model's window; everything else is a scan, never a miss."""
    if accel_window and float(accel_window[0]) <= start and end <= float(accel_window[1]):
        return "accelerated"
    return "scan"


def localise_query(index: str, width: float) -> str:
    """Rung 2: the default indexed fields say where and when, never who."""
    return f"| tstats count where index={_quoted(index)} by host _time span={int(width)}s"


def select_local_windows(
    rows: Iterable[Mapping[str, Any]], width: float, *, limit: int = LOCALISE_WINDOWS
) -> list[LocalWindow]:
    """Peak buckets of one host/time series, coalesced: every other bucket is a baseline."""
    grouped: dict[tuple[str, float], int] = {}
    for row in rows:
        host = str(row.get("host") or "")
        stamp = _number(row.get("_time"))
        count = _count(row.get("count"))
        if not host or stamp is None or count <= 0:
            continue
        key = (host, stamp)
        grouped[key] = grouped.get(key, 0) + count
    if not grouped:
        return []
    logs = [math.log1p(count) for count in grouped.values()]
    middle = statistics.median(logs)
    spread = statistics.median(abs(value - middle) for value in logs)
    scored = [
        ((math.log1p(count) - middle) / (spread + 0.5), stamp, host, count)
        for (host, stamp), count in grouped.items()
    ]
    peaks = sorted(
        (item for item in scored if item[0] >= LOCALISE_Z), key=lambda item: (-item[0], item[1])
    )[:limit]
    windows = sorted(
        (LocalWindow(host, stamp, stamp + width, count) for _score, stamp, host, count in peaks),
        key=lambda window: (window.host, window.start),
    )
    return _coalesce(windows, width)


def _coalesce(windows: Sequence[LocalWindow], width: float) -> list[LocalWindow]:
    """Adjacent peak buckets of one host are one readable window."""
    merged: list[LocalWindow] = []
    for window in windows:
        last = merged[-1] if merged else None
        if last is not None and last.host == window.host and last.end == window.start:
            merged[-1] = LocalWindow(
                last.host, last.start, window.start + width, last.events + window.events
            )
            continue
        merged.append(window)
    return merged


def accel_probe_query(model: str, index: str) -> str:
    """Rung 1's guard: the window a model's summaries hold for this index."""
    return (
        f"| tstats summariesonly=true count min(_time) as first max(_time) as last"
        f" from datamodel={model} where index={_quoted(index)}"
    )


def accel_localise_query(model: str, index: str, width: float) -> str:
    """Rung 1: the summary's own host/time buckets; a summary read scans no events."""
    return (
        f"| tstats summariesonly=true count from datamodel={model}"
        f" where index={_quoted(index)} by host _time span={int(width)}s"
    )


def summary_window(rows: Iterable[Mapping[str, Any]]) -> tuple[float, float] | None:
    """The earliest and latest summarized event the probe returned; None when it holds none."""
    firsts: list[float] = []
    lasts: list[float] = []
    for row in rows:
        if _count(row.get("count")) <= 0:
            continue
        first = _number(row.get("first"))
        last = _number(row.get("last")) or first
        if first is None or last is None:
            continue
        firsts.append(first)
        lasts.append(last)
    if not firsts:
        return None
    return (min(firsts), max(lasts) + 0.000001)


def accel_summaries(executor: HuntExecutor, index: str) -> tuple[list[AccelSummary], list[str]]:
    """One summariesonly probe per accelerated model: which cover this index, over what window."""
    found: list[AccelSummary] = []
    notes: list[str] = []
    end = time.time() + 1.0
    for model in ACCEL_MODELS:
        rows, reason = _read_range(
            executor,
            accel_probe_query(model, index),
            0.0,
            end,
            kind="localise_accel",
            row_cap=ACCEL_PROBE_ROWS,
        )
        if reason:
            notes.append(f"accel:{model}:{reason}")
            continue
        window = summary_window(rows)
        if window:
            found.append(AccelSummary(model, window))
    return found, notes


def localise(
    executor: HuntExecutor, index: str, start: float, end: float, *, width: float | None = None
) -> Localisation:
    """Rung 1 over a covering summary, else rung 2's index aggregate: where and when, never who."""
    chosen = width or localise_width(end - start)
    summaries, notes = accel_summaries(executor, index)
    covered = [
        item for item in summaries if coverage_label(item.window, start, end) == "accelerated"
    ]
    accel_window = covered[0].window if covered else (summaries[0].window if summaries else None)
    for summary in covered:
        rows, reason = _read_range(
            executor,
            accel_localise_query(summary.model, index, chosen),
            start,
            end,
            kind="localise",
            row_cap=LOCALISE_ROWS,
        )
        if reason:
            notes.append(f"accel:{summary.model}:{reason}")
            continue
        windows = select_local_windows(rows, chosen)
        if windows:
            return Localisation(
                windows, "accelerated", summary.model, summary.window, "accelerated", notes
            )
        notes.append(f"accel:no_windows:{summary.model}")
    rows, reason = _read_range(
        executor,
        localise_query(index, chosen),
        start,
        end,
        kind="localise",
        row_cap=LOCALISE_ROWS,
    )
    if reason:
        notes.append(f"localise:{reason}")
    return Localisation(
        select_local_windows(rows, chosen), "indexed", "", accel_window, "scan", notes
    )


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


def source_windows(facts: SourceFacts, count: int) -> list[tuple[float, float]]:
    """Include max(_time) in the last half-open search at the transport's microsecond precision."""
    if facts.last < facts.first or count <= 0:
        return []
    end = facts.last + 0.000001
    if facts.last == facts.first:
        return [(facts.first, end)]
    bounds = window_bounds(facts.first, facts.last, count)
    bounds[-1] = (bounds[-1][0], end)
    return bounds


def _read_range(
    executor: HuntExecutor,
    query: str,
    start: float,
    end: float,
    *,
    kind: str,
    row_cap: int,
    source_id: str | None = None,
    part: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        options: dict[str, Any] = {"kind": kind, "row_cap": row_cap}
        if isinstance(executor, HuntExecutor):
            options.update(source_id=source_id, part=part)
        result = executor.read(query, start, end, **options)
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


def shared_source_names(by_type: Mapping[str, Iterable[str]]) -> set[str]:
    owners: dict[str, set[str]] = {}
    for owner, names in by_type.items():
        for name in names:
            owners.setdefault(name.casefold(), set()).add(owner)
    return {name for name, types in owners.items() if len(types) > 1}


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
    shared = shared_source_names({k: [s for s, _ in v] for k, v in by_source.items()})
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
                shared_sources=tuple(src for src, _ in ranked_sources if src.casefold() in shared),
            )
        )
    return facts, notes


def route_filter(facts: SourceFacts, max_sources: int = SAMPLE_SOURCES) -> tuple[str, str]:
    """Filter that selects this source's events: indexed sources where known, else the name."""
    return source_route(facts.sourcetype, facts.sources[:max_sources], facts.shared_sources)


def source_route(
    sourcetype: str, selected: Sequence[str], shared_sources: Sequence[str]
) -> tuple[str, str]:
    if selected:
        predicates = " OR ".join(f"source={_quoted(name)}" for name in selected)
        route = f"({predicates})"
        if set(selected).intersection(shared_sources):
            route = f"sourcetype={_quoted(sourcetype)} {route}"
        return route, "source"
    return f"sourcetype={_quoted(sourcetype)}", "sourcetype"


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
    found = RowSet(windows=len(readable), route=route_name, query=query)
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(slice_bounds) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                _read_range,
                executor,
                query,
                start,
                end,
                kind=kind,
                row_cap=per_part,
                source_id=f"{facts.index}:{facts.sourcetype}",
            )
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
    found.read_mode = "sampled"
    found.rung = "equal_slice"
    found.events_scanned = len(found.rows)
    found.coverage = "scan"
    return found


def read_anchors(
    executor: HuntExecutor,
    facts: SourceFacts,
    anchors: Sequence[LocalWindow],
    *,
    per_window: int,
    kind: str,
    max_sources: int = SAMPLE_SOURCES,
    accel_window: tuple[float, float] | None = None,
) -> RowSet:
    """Rung 3: read only the host/time windows rung 2 produced, capped per window."""
    route, route_name = route_filter(facts, max_sources)
    readable = [anchor for anchor in anchors if anchor.end > anchor.start]
    found = RowSet(
        windows=len(readable),
        route=route_name,
        selection="localised host/time windows from the indexed aggregate",
        query=f"search index={_quoted(facts.index)} {route} host=<localised host> | head {per_window}",
    )
    found.read_mode = "anchored"
    found.rung = "narrowed_scan"
    found.events_scanned = sum(anchor.events for anchor in readable)
    found.coverage = "scan"
    found.accel_window = accel_window
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(readable) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                _read_range,
                executor,
                f"search index={_quoted(facts.index)} {route} host={_quoted(anchor.host)}"
                f" | head {per_window}",
                anchor.start,
                anchor.end,
                kind=kind,
                row_cap=per_window,
                source_id=f"{facts.index}:{facts.sourcetype}",
            )
            for anchor in readable
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
    if facts.last >= facts.first and (facts.last or facts.events):
        return source_windows(facts, SAMPLE_WINDOWS)
    now = time.time()
    return window_bounds(now - EMPTY_SAMPLE_WINDOWS * 3600.0, now, SAMPLE_WINDOWS)


def read_alert_rows(
    executor: HuntExecutor, facts: SourceFacts, *, per_window: int = ALERT_PROBE_LINES
) -> RowSet:
    """Read a source's detection events directly by the marker that makes them detections."""
    route, route_name = route_filter(facts, SAMPLE_SOURCES)
    query = f"search index={_quoted(facts.index)} {route} {ALERT_TERM} | head {per_window}"
    rows, reason = _read_range(
        executor,
        query,
        facts.first,
        facts.last + 0.000001,
        kind="alert_probe",
        row_cap=per_window,
        source_id=f"{facts.index}:{facts.sourcetype}",
    )
    found = RowSet([dict(row) for row in rows], 1, route_name, [reason] if reason else [])
    found.read_mode = "sampled"
    found.events_scanned = len(found.rows)
    found.coverage = "scan"
    return found


__all__ = [
    "ACCEL_MODELS",
    "ALERT_TERM",
    "AccelSummary",
    "Localisation",
    "LocalWindow",
    "RowSet",
    "SourceFacts",
    "accel_localise_query",
    "accel_probe_query",
    "accel_summaries",
    "cadence_facts",
    "coverage_label",
    "index_facts",
    "localise",
    "localise_query",
    "localise_width",
    "read_alert_rows",
    "read_anchors",
    "read_mode",
    "read_windows",
    "route_filter",
    "sample_windows",
    "select_local_windows",
    "summary_window",
    "window_bounds",
]
