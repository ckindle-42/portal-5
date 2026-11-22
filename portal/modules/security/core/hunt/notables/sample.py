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
from ..executor import (
    REQUEST_BUDGET_EXHAUSTED,
    HuntBudgetExceededError,
    HuntExecutor,
    plan_within_requests,
)

SAMPLE_WINDOWS = 3  # effort budget: raw reads spread across each source's own time range
SAMPLE_LINES = 40  # effort budget: events read per window for a source card
SAMPLE_SOURCES = 2  # effort budget: indexed sources sampled for one source card
SAMPLE_FILES = 6  # effort budget: indexed files one source card sample draws from
SAMPLE_FILE_LINES = 20  # effort budget: events read per file in a spread card sample
ALERT_PROBE_LINES = 400  # effort budget: events read per window to detect an alert-bearing part
ALERT_TERM = 'event_type="alert"'  # the search term that selects a JSON detection event
BEHAVIOUR_SOURCES = 8  # effort budget: indexed sources one pooled read covers
READ_FILES_MAX = 32  # effort budget: indexed files one behaviour read covers
DENSITY_PROBE_MAX = 4  # effort budget: density probes one source read spends on its largest files
FILE_READ_MIN_WINDOWS = 3  # a file is sampled at several points, never only its tail
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
SPLUNK_TIME_EPSILON = 1.0  # an exclusive Splunk latest needs a whole second to hold the last event
RENAME_DISCOVERY_QUERY = "| rest splunk_server=local /servicesNS/-/-/configs/conf-props | search rename=* | table title rename"


def inclusive_end(last: float) -> float:
    """A Splunk `latest` bound that still contains an event stamped `last`."""
    return last + SPLUNK_TIME_EPSILON


@dataclass(frozen=True)
class IndexFile:
    """One indexed source path under a sourcetype: its volume, hosts and own time range."""

    path: str
    events: int
    hosts: tuple[str, ...] = ()
    first: float = 0.0
    last: float = 0.0


@dataclass(frozen=True)
class FileRead:
    """One (indexed file, window) read, or why the file was not read at all."""

    path: str
    host: str
    events_available: int
    window_start: float
    window_end: float
    rows: int
    reason: str = ""
    hosts: tuple[str, ...] = ()


EMPTY_WINDOW = "empty_window"  # the window was read and returned nothing


def file_omitted(item: FileRead) -> bool:
    """An omitted file was declined unread; an empty window was issued and returned nothing."""
    return bool(item.reason) and item.reason != EMPTY_WINDOW


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
    files: tuple[IndexFile, ...] = ()
    search_sourcetype: str = ""


def file_span(facts: SourceFacts, item: IndexFile) -> tuple[float, float]:
    """A file's own range, or its source's when the run recorded none (0.0 ⇒ unknown)."""
    return (item.first, item.last) if item.last > 0.0 else (facts.first, facts.last)


def search_sourcetype_of(facts: SourceFacts) -> str:
    """The name a raw `search` must use: the search-time rename, else the indexed name."""
    return facts.search_sourcetype or facts.sourcetype


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
    files: list[FileRead] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": len(self.rows),
            "windows": self.windows,
            "route": self.route,
            "read_mode": self.read_mode,
            "rung": self.rung,
            "events_scanned": self.events_scanned,
            "coverage": self.coverage,
            "files_read": len({item.path for item in self.files if not file_omitted(item)}),
            "files_omitted": len({item.path for item in self.files if file_omitted(item)}),
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
class ScanCache:
    """One index aggregate per (index, width): fetched over `span` once, sliced per source."""

    span: tuple[float, float]
    rows: list[dict[str, Any]] | None = None


@dataclass
class Localisation:
    """Where a read's windows came from: a summary, the index aggregate, or neither."""

    windows: list[LocalWindow] = field(default_factory=list)
    mechanism: str = ""  # accelerated | accelerated_partial | indexed | ""
    model: str = ""
    accel_window: tuple[float, float] | None = None
    covered_window: tuple[float, float] | None = None
    scanned_window: list[tuple[float, float]] = field(default_factory=list)
    coverage: str = "scan"  # accelerated | accelerated_partial | scan
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
    """Exact containment accelerates; any smaller overlap is a declared partial, never a miss."""
    if not accel_window:
        return "scan"
    first, last = float(accel_window[0]), float(accel_window[1])
    if first <= start and end <= last:
        return "accelerated"
    if first < end and start < last:
        return "accelerated_partial"
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
    return (min(firsts), inclusive_end(max(lasts)))


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
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    *,
    width: float | None = None,
    summaries: Sequence[AccelSummary] | None = None,
    scan_cache: ScanCache | None = None,
) -> Localisation:
    """Rung 1 over a covering summary, else rung 2's index aggregate: one source's own span."""
    chosen = width or localise_width(end - start)
    if summaries is None:
        probed, notes = accel_summaries(executor, index)
    else:
        probed, notes = list(summaries), []
    covered = [item for item in probed if coverage_label(item.window, start, end) == "accelerated"]
    for summary in covered:
        windows = _summary_windows(executor, index, summary.model, start, end, chosen, notes)
        if windows:
            return Localisation(
                windows=windows,
                mechanism="accelerated",
                model=summary.model,
                accel_window=summary.window,
                coverage="accelerated",
                notes=notes,
            )
        notes.append(f"accel:no_windows:{summary.model}")
    partial = _partial_summary(probed, start, end)
    if partial is not None:
        found = _partial_localisation(executor, index, partial, start, end, chosen, notes)
        if found is not None:
            return found
    scanned_rows = _scan_windows(executor, index, start, end, chosen, notes, scan_cache)
    return Localisation(
        windows=scanned_rows,
        mechanism="indexed",
        model="",
        accel_window=covered[0].window if covered else (probed[0].window if probed else None),
        coverage="scan",
        notes=notes,
    )


def _summary_windows(
    executor: HuntExecutor,
    index: str,
    model: str,
    start: float,
    end: float,
    width: float,
    notes: list[str],
) -> list[LocalWindow]:
    """The peak buckets one model's summary answers for a sub-range."""
    rows, reason = _read_range(
        executor,
        accel_localise_query(model, index, width),
        start,
        end,
        kind="localise",
        row_cap=LOCALISE_ROWS,
    )
    if reason:
        notes.append(f"accel:{model}:{reason}")
        return []
    return select_local_windows(rows, width)


def _scan_windows(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    width: float,
    notes: list[str],
    scan_cache: ScanCache | None = None,
) -> list[LocalWindow]:
    """The peak buckets the index aggregate answers for a sub-range no summary holds.

    With a cache, the aggregate is fetched once over the shared span and sliced per source.
    """
    if scan_cache is not None and scan_cache.rows is not None:
        return select_local_windows(_rows_within(scan_cache.rows, start, end), width)
    fetch_start, fetch_end = scan_cache.span if scan_cache is not None else (start, end)
    rows, reason = _read_range(
        executor,
        localise_query(index, width),
        fetch_start,
        fetch_end,
        kind="localise",
        row_cap=LOCALISE_ROWS,
    )
    if reason:
        notes.append(f"localise:{reason}")
        return select_local_windows(rows, width)
    if scan_cache is not None:
        scan_cache.rows = rows
        rows = _rows_within(rows, start, end)
    return select_local_windows(rows, width)


def _rows_within(
    rows: Sequence[Mapping[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    """The aggregate's buckets whose own stamp falls inside one source's span."""
    kept = []
    for row in rows:
        stamp = _number(row.get("_time"))
        if stamp is not None and start <= stamp < end:
            kept.append(dict(row))
    return kept


def _partial_summary(
    summaries: Sequence[AccelSummary], start: float, end: float
) -> AccelSummary | None:
    """The summary window with the largest overlap of a span it does not contain."""
    best: tuple[float, AccelSummary] | None = None
    for item in summaries:
        if coverage_label(item.window, start, end) != "accelerated_partial":
            continue
        overlap = min(end, float(item.window[1])) - max(start, float(item.window[0]))
        if best is None or overlap > best[0]:
            best = (overlap, item)
    return best[1] if best else None


def _partial_localisation(
    executor: HuntExecutor,
    index: str,
    summary: AccelSummary,
    start: float,
    end: float,
    width: float,
    notes: list[str],
) -> Localisation | None:
    """The covered sub-range is localised from the summary, each remainder from the index."""
    first, last = float(summary.window[0]), float(summary.window[1])
    covered = (max(start, first), min(end, last))
    scanned = [piece for piece in ((start, first), (last, end)) if piece[0] < piece[1]]
    windows = _summary_windows(executor, index, summary.model, *covered, width, notes)
    for piece in scanned:
        windows.extend(_scan_windows(executor, index, *piece, width, notes))
    if not windows:
        notes.append(f"accel_partial:no_windows:{summary.model}")
        return None
    peaks = sorted(windows, key=lambda window: -window.events)[:LOCALISE_WINDOWS]
    peaks.sort(key=lambda window: (window.host, window.start))
    return Localisation(
        windows=peaks,
        mechanism="accelerated_partial",
        model=summary.model,
        accel_window=summary.window,
        covered_window=covered,
        scanned_window=scanned,
        coverage="accelerated_partial",
        notes=notes,
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


def _span_windows(first: float, last: float, count: int) -> list[tuple[float, float]]:
    """`count` equal slices of a range, its last slice ending after an event at `last`."""
    if last < first or count <= 0:
        return []
    end = inclusive_end(last)
    if last == first:
        return [(first, end)]
    bounds = window_bounds(first, last, count)
    bounds[-1] = (bounds[-1][0], end)
    return bounds


def source_windows(facts: SourceFacts, count: int) -> list[tuple[float, float]]:
    """Include max(_time) in the last half-open search at the transport's microsecond precision."""
    return _span_windows(facts.first, facts.last, count)


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
    executor: HuntExecutor, index: str, by: str, start: float, end: float, *, span: bool = False
) -> tuple[list[dict[str, Any]], str | None]:
    counted = "count min(_time) as first max(_time) as last" if span else "count"
    query = f"| tstats {counted} where index={_quoted(index)} {by}"
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


def sourcetype_renames(executor: HuntExecutor) -> tuple[dict[str, str], list[str]]:
    """The instance's live `props.conf` renames, case-folded: indexed name -> search name."""
    rows, reason = _read_range(
        executor,
        RENAME_DISCOVERY_QUERY,
        0.0,
        time.time() + SPLUNK_TIME_EPSILON,
        kind="discovery",
        row_cap=METADATA_ROWS,
    )
    if reason:
        return {}, [f"sourcetype_renames:{reason}"]
    found: dict[str, str] = {}
    for row in rows:
        title = str(row.get("title") or "").strip()
        rename = str(row.get("rename") or "").strip()
        if title and rename and title.casefold() != rename.casefold():
            found[title.casefold()] = rename
    return found, []


def index_facts(
    executor: HuntExecutor, index: str, start: float, end: float
) -> tuple[list[SourceFacts], list[str]]:
    """Volume, time range, hosts and indexed files for every sourcetype in the index."""
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
    renames, rename_notes = sourcetype_renames(executor)
    notes.extend(rename_notes)
    sources, source_reason = _meta_rows(
        executor, index, "by sourcetype source host", start, end, span=True
    )
    hosts, host_reason = _meta_rows(executor, index, "by sourcetype host", start, end)
    cadence, cadence_notes = cadence_facts(executor, index, start, end)
    notes.extend(cadence_notes)
    for label, cause in (("source", source_reason), ("host", host_reason)):
        if cause:
            notes.append(f"{label}_metadata:{cause}")
    by_source = _group_meta(sources, "sourcetype", "source")
    by_host = _group_meta(hosts, "sourcetype", "host")
    by_file = _group_files(sources)
    shared = shared_source_names({k: [s for s, _ in v] for k, v in by_source.items()})
    facts: list[SourceFacts] = []
    for row in sorted(volume, key=lambda item: str(item.get("sourcetype") or "")):
        name = str(row.get("sourcetype") or "")
        if not name:
            continue
        ranked_sources = sorted(by_source.get(name, []), key=lambda item: (-item[1], item[0]))
        ranked_hosts = sorted(by_host.get(name, []), key=lambda item: (-item[1], item[0]))
        events = _count(row.get("count"))
        files = _files_of(by_file.get(name), events)
        if not files and by_file.get(name):
            notes.append(f"files_incomplete:{name}")
        active, span, cv = cadence.get(name, (0, 0, 0.0))
        facts.append(
            SourceFacts(
                index=index,
                sourcetype=name,
                events=events,
                first=_number(row.get("first")) or start,
                last=_number(row.get("last")) or end,
                hosts=tuple(host for host, _ in ranked_hosts[:MAX_HOST_NAMES]),
                host_count=len(ranked_hosts),
                sources=tuple(file.path for file in files)
                or tuple(source for source, _ in ranked_sources),
                source_count=len(ranked_sources),
                active_periods=active,
                periods=span,
                count_cv=cv,
                shared_sources=tuple(src for src, _ in ranked_sources if src.casefold() in shared),
                files=files,
                search_sourcetype=renames.get(name.casefold(), ""),
            )
        )
    return facts, notes


@dataclass(frozen=True)
class _FileRow:
    """One host's slice of one indexed file: the events it holds and the span they cover."""

    host: str
    count: int
    first: float = 0.0
    last: float = 0.0


def _group_files(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, list[_FileRow]]]:
    """Per sourcetype: each indexed source path with its host rows, counts and own span."""
    grouped: dict[str, dict[str, list[_FileRow]]] = {}
    for row in rows:
        owner = str(row.get("sourcetype") or "")
        path = str(row.get("source") or "")
        if not owner or not path:
            continue
        grouped.setdefault(owner, {}).setdefault(path, []).append(
            _FileRow(
                str(row.get("host") or ""),
                _count(row.get("count")),
                _number(row.get("first")) or 0.0,
                _number(row.get("last")) or 0.0,
            )
        )
    return grouped


def _files_of(
    entries: Mapping[str, Sequence[_FileRow]] | None, events: int
) -> tuple[IndexFile, ...]:
    """Ranked files, or none when the file rows do not account for every event of the source."""
    if not entries:
        return ()
    total = sum(row.count for rows in entries.values() for row in rows)
    if total != events:
        return ()
    files: list[IndexFile] = []
    for path, rows in entries.items():
        if not rows:
            continue
        first, last = _rows_span(rows)
        events_here = sum(row.count for row in rows)
        files.append(IndexFile(path, events_here, _file_hosts(rows), first, last))
    return tuple(sorted(files, key=lambda item: (-item.events, item.path)))


def _rows_span(rows: Sequence[_FileRow]) -> tuple[float, float]:
    """The file's own range across its host rows, or 0/0 when the rows carried no time."""
    spans = [(row.first, row.last) for row in rows if row.last > 0.0]
    if not spans:
        return 0.0, 0.0
    return min(first for first, _last in spans), max(last for _first, last in spans)


def _file_hosts(rows: Sequence[_FileRow]) -> tuple[str, ...]:
    """The hosts a file appears on, or none when they are too many to be worth naming."""
    ranked = [
        row.host for row in sorted(rows, key=lambda item: (-item.count, item.host)) if row.host
    ]
    if len(ranked) > MAX_HOST_NAMES:
        return ()
    return tuple(sorted(ranked))


def route_filter(facts: SourceFacts, max_sources: int = SAMPLE_SOURCES) -> tuple[str, str]:
    """This source's raw-search filter: indexed sources where known, else its search-time name."""
    return source_route(
        search_sourcetype_of(facts), facts.sources[:max_sources], facts.shared_sources
    )


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
    host: str = "",
) -> RowSet:
    """Read the newest `per_window` events of each equal time slice, concurrently.

    The slice is the declared, deterministic sample: the source's own range cut into
    equal windows, newest events first inside each. Nothing is extrapolated beyond it.
    `sub_windows` > 1 splits each slice and reads the newest share of every part, so a
    high-volume source is sampled at several points in the slice instead of only its tail.
    """
    route, route_name = route_filter(facts, max_sources)
    if host:
        route = f"{route} host={_quoted(host)}"
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


def sample_files(facts: SourceFacts, cap: int = SAMPLE_FILES) -> tuple[IndexFile, ...]:
    """Ranked files round-robin by lead host, so every host contributes before one host repeats."""
    groups: dict[str, list[IndexFile]] = {}
    for item in facts.files:
        groups.setdefault(item.hosts[0] if item.hosts else "", []).append(item)
    queues = [
        sorted(files, key=lambda item: (-item.events, item.path))
        for _host, files in sorted(groups.items())
    ]
    picked: list[IndexFile] = []
    while len(picked) < cap and any(queues):
        for queue in queues:
            if queue and len(picked) < cap:
                picked.append(queue.pop(0))
    return tuple(picked)


def _file_window(
    facts: SourceFacts, item: IndexFile, windows: Sequence[tuple[float, float]]
) -> tuple[float, float]:
    """The source window holding the file's own last event, else the first window."""
    last = file_span(facts, item)[1]
    for bounds in windows:
        if bounds[0] <= last < bounds[1]:
            return bounds
    return windows[0]


def read_card_sample(executor: HuntExecutor, facts: SourceFacts, *, kind: str) -> RowSet:
    """The card's sample: per-file heads across hosts — a pooled `head` is arrival order."""
    files = sample_files(facts)
    windows = [bounds for bounds in sample_windows(facts) if bounds[1] > bounds[0]]
    if len(files) <= 1 or not windows:
        return read_windows(
            executor, facts, sample_windows(facts), per_window=SAMPLE_LINES, kind=kind
        )
    source_id = f"{facts.index}:{facts.sourcetype}"
    found = RowSet(
        windows=len(windows),
        route="source",
        selection="newest lines of each indexed file, hosts round-robin, at each file's own window",
    )
    requests = [(item, _file_window(facts, item, windows)) for item in files]
    found.query = (
        f"search index={_quoted(facts.index)} {file_route(facts, files[0].path)}"
        f" | sort - _time | head {SAMPLE_FILE_LINES}"
    )
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(requests), concurrency)) as pool:
        futures = [
            pool.submit(
                _read_range,
                executor,
                f"search index={_quoted(facts.index)} {file_route(facts, item.path)}"
                f" | sort - _time | head {SAMPLE_FILE_LINES}",
                bounds[0],
                bounds[1],
                kind=kind,
                row_cap=SAMPLE_FILE_LINES,
                source_id=source_id,
            )
            for item, bounds in requests
        ]
        for (item, bounds), future in zip(requests, futures, strict=True):
            rows, reason = future.result()
            found.rows.extend(rows)
            if reason:
                found.notes.append(reason)
            found.files.append(
                FileRead(
                    item.path,
                    "",
                    item.events,
                    bounds[0],
                    bounds[1],
                    len(rows),
                    reason or (EMPTY_WINDOW if not rows else ""),
                    item.hosts,
                )
            )
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


def file_route(
    facts: SourceFacts,
    path: str,
    host: str = "",
    shared: Sequence[str] = (),
    *,
    indexed: bool = False,
) -> str:
    """One indexed file's own route; a shared path stays scoped (`indexed=True`: TSIDX name)."""
    name = facts.sourcetype if indexed else search_sourcetype_of(facts)
    route = f"source={_quoted(path)}"
    if path.casefold() in {src.casefold() for src in (shared or facts.shared_sources)}:
        route = f"sourcetype={_quoted(name)} {route}"
    return f"{route} host={_quoted(host)}" if host else route


def read_files(
    executor: HuntExecutor,
    facts: SourceFacts,
    windows: Sequence[tuple[float, float]],
    *,
    per_window: int,
    kind: str,
    host: str = "",
    sub_windows: int = 1,
    max_files: int = READ_FILES_MAX,
) -> RowSet:
    """One read per indexed file with its own `head`: a pooled `head` returns arrival order."""
    if not facts.files:
        return read_windows(
            executor,
            facts,
            windows,
            per_window=per_window,
            kind=kind,
            max_sources=BEHAVIOUR_SOURCES,
            sub_windows=sub_windows,
            host=host,
        )
    readable = [bounds for bounds in windows if bounds[1] > bounds[0]]
    parts = max(1, sub_windows)
    source_bounds: list[tuple[float, float]] = []
    for start, end in readable:
        source_bounds.extend(window_bounds(start, end, parts))
    per_read = max(1, per_window // parts)
    source_id = f"{facts.index}:{facts.sourcetype}"
    found = RowSet(
        windows=len(readable),
        route="source",
        selection="newest events of each indexed file's own windows",
    )
    planned, skipped = _plan_files(
        executor, facts, source_bounds, per_window, per_read, host, max_files, source_id
    )
    found.files.extend(skipped)
    counts: dict[tuple[str, float, float], int] = {}
    planned_reads = [
        (item, file_host, start, end, cap, probed)
        for item, file_host, reads in planned
        for start, end, cap, probed in reads
    ]
    _cap_density_probes(planned_reads)
    kept, dropped = plan_within_requests(
        planned_reads,
        _remaining_requests(executor),
        priority=lambda request: (-request[0].events, request[0].path, -request[2]),
        cost=lambda request: 2 if request[5] else 1,
    )
    for item, file_host, start, end, cap, _probed in dropped:
        _omit_window(
            executor, facts, item, file_host, start, end, cap, source_id, REQUEST_BUDGET_EXHAUSTED
        )
        found.files.append(
            FileRead(
                item.path,
                file_host,
                item.events,
                start,
                end,
                0,
                REQUEST_BUDGET_EXHAUSTED,
                item.hosts,
            )
        )
    _density_counts(executor, facts, kept, counts)
    requests = _headed_requests(kept, counts)
    if requests:
        item, file_host, _start, _end, head = requests[0]
        found.query = (
            f"search index={_quoted(facts.index)} {file_route(facts, item.path, file_host)}"
            f" | sort - _time | head {head}"
        )
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(requests) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                _read_range,
                executor,
                f"search index={_quoted(facts.index)} {file_route(facts, item.path, file_host)}"
                f" | sort - _time | head {head}",
                start,
                end,
                kind=kind,
                row_cap=head,
                source_id=source_id,
            )
            for item, file_host, start, end, head in requests
        ]
        for (item, file_host, start, end, _head), future in zip(requests, futures, strict=True):
            rows, reason = future.result()
            found.rows.extend(rows)
            if reason:
                found.notes.append(reason)
            found.files.append(
                FileRead(
                    item.path,
                    file_host,
                    item.events,
                    start,
                    end,
                    len(rows),
                    reason or (EMPTY_WINDOW if not rows else ""),
                    item.hosts,
                )
            )
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


def _plan_files(
    executor: HuntExecutor,
    facts: SourceFacts,
    source_bounds: Sequence[tuple[float, float]],
    per_window: int,
    per_read: int,
    host: str,
    max_files: int,
    source_id: str,
) -> tuple[list[tuple[IndexFile, str, list[tuple[float, float, int, bool]]]], list[FileRead]]:
    """One read plan per file; every file not read is a receipt with its reason."""
    planned: list[tuple[IndexFile, str, list[tuple[float, float, int, bool]]]] = []
    skipped: list[FileRead] = []
    reading = 0
    for item in facts.files:
        if host and item.hosts and host not in item.hosts:
            _omit_file(executor, facts, item, "", per_read, source_id, "host_mismatch")
            skipped.append(
                FileRead(item.path, "", item.events, 0.0, 0.0, 0, "host_mismatch", item.hosts)
            )
            continue
        file_host = host if host and host in item.hosts else ""
        reading += 1
        if reading > max_files:
            _omit_file(executor, facts, item, file_host, per_read, source_id, "read_files_cap")
            skipped.append(
                FileRead(
                    item.path, file_host, item.events, 0.0, 0.0, 0, "read_files_cap", item.hosts
                )
            )
            continue
        planned.append(
            (item, file_host, _file_reads(facts, item, source_bounds, per_window, per_read))
        )
    return planned, skipped


def _file_reads(
    facts: SourceFacts,
    item: IndexFile,
    source_bounds: Sequence[tuple[float, float]],
    per_window: int,
    per_read: int,
) -> list[tuple[float, float, int, bool]]:
    """One file's (window, cap) plan: its own range sliced, else the source schedule.

    The cap is the head ceiling the window's density probe may cut; a small file is read
    whole at its own event count, with no probe ahead of it.
    """
    if item.events <= per_window:
        bounds = _file_windows(item, 1) or [(facts.first, inclusive_end(facts.last))]
        return [(bounds[0][0], bounds[-1][1], max(1, item.events), False)]
    own = _file_windows(item, _file_window_count(item.events, per_window, per_window))
    bounds = own or _spread_windows(
        source_bounds, _file_window_count(item.events, per_window, per_read)
    )
    return [(start, end, per_window if own else per_read, True) for start, end in bounds]


def _cap_density_probes(
    requests: list[tuple[IndexFile, str, float, float, int, bool]],
) -> None:
    """Beyond `DENSITY_PROBE_MAX`, the largest files keep probes and the rest read at cap."""
    probed = [order for order, item in enumerate(requests) if item[5]]
    for order in sorted(
        probed,
        key=lambda order: (
            -requests[order][0].events,
            requests[order][0].path,
            -requests[order][2],
        ),
    )[DENSITY_PROBE_MAX:]:
        item = requests[order]
        requests[order] = (item[0], item[1], item[2], item[3], item[4], False)


def _density_counts(
    executor: HuntExecutor,
    facts: SourceFacts,
    requests: Sequence[tuple[IndexFile, str, float, float, int, bool]],
    cache: dict[tuple[str, float, float], int],
) -> None:
    """Every kept window's own count, probed concurrently: one tstats request each."""
    probed = [item for item in requests if item[5]]
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(probed) or 1, concurrency)) as pool:
        futures = [
            pool.submit(_window_events, executor, facts, item[0].path, item[2], item[3], cache)
            for item in probed
        ]
        for future in futures:
            future.result()


def _headed_requests(
    requests: Sequence[tuple[IndexFile, str, float, float, int, bool]],
    counts: Mapping[tuple[str, float, float], int],
) -> list[tuple[IndexFile, str, float, float, int]]:
    """Final heads: the window's own density, or the planned cap when no count came back."""
    return [
        (
            item,
            file_host,
            start,
            end,
            cap if not probed else _file_head(counts.get((item.path, start, end), -1), cap),
        )
        for item, file_host, start, end, cap, probed in requests
    ]


def _file_windows(item: IndexFile, count: int) -> list[tuple[float, float]]:
    """A file's own range sliced like a source's, or none when the map recorded no time."""
    return _span_windows(item.first, item.last, count) if item.last > 0.0 else []


def _window_events(
    executor: HuntExecutor,
    facts: SourceFacts,
    path: str,
    start: float,
    end: float,
    cache: dict[tuple[str, float, float], int],
) -> int:
    """The file's own count inside one window: one `tstats` request per file and window."""
    key = (path, start, end)
    if key not in cache:
        rows, reason = _read_range(
            executor,
            f"| tstats count where index={_quoted(facts.index)} "
            f"{file_route(facts, path, indexed=True)}",
            start,
            end,
            kind="discovery",
            row_cap=1,
        )
        counted = sum(_count(row.get("count")) for row in rows)
        cache[key] = counted if rows and not reason else -1
    return cache[key]


def _file_window_count(events: int, per_window: int, per_read: int) -> int:
    """Windows one file needs to expose the rows it can be read for, at several points."""
    return max(FILE_READ_MIN_WINDOWS, math.ceil(min(events, per_window) / max(1, per_read)))


def _file_head(events_in_window: int, per_read: int) -> int:
    """One read's cap: the events this window holds, never above a pooled read's."""
    return per_read if events_in_window < 0 else max(1, min(per_read, events_in_window))


def _spread_windows(bounds: Sequence[tuple[float, float]], take: int) -> list[tuple[float, float]]:
    """`take` windows spread evenly across the schedule, always keeping the tail."""
    if take >= len(bounds):
        return list(bounds)
    step = len(bounds) / take
    picks = {min(len(bounds) - 1, int(number * step)) for number in range(take)}
    picks.add(len(bounds) - 1)
    return [bounds[number] for number in sorted(picks)]


def _omit_window(
    executor: HuntExecutor,
    facts: SourceFacts,
    item: IndexFile,
    host: str,
    start: float,
    end: float,
    head: int,
    source_id: str,
    reason: str,
) -> None:
    """Declare an unread file window in the ledger through the same observer every read uses."""
    record = getattr(executor, "record_skipped_read", None)
    if not callable(record):
        return
    query = (
        f"search index={_quoted(facts.index)} {file_route(facts, item.path, host)} | head {head}"
    )
    record(query, start, end, source_id=source_id, reason=reason)


def _omit_file(
    executor: HuntExecutor,
    facts: SourceFacts,
    item: IndexFile,
    host: str,
    head: int,
    source_id: str,
    reason: str,
) -> None:
    """Declare a whole unread file in the ledger through the same observer every read uses."""
    _omit_window(executor, facts, item, host, facts.first, facts.last, head, source_id, reason)


def _remaining_requests(executor: HuntExecutor) -> int | None:
    """The unspent request ceiling, or None when the read path carries no shared budget."""
    counter = getattr(getattr(executor, "budget", None), "remaining_requests", None)
    return int(counter()) if callable(counter) else None


def read_anchors(
    executor: HuntExecutor,
    facts: SourceFacts,
    anchors: Sequence[LocalWindow],
    *,
    per_window: int,
    kind: str,
    max_sources: int = SAMPLE_SOURCES,
    accel_window: tuple[float, float] | None = None,
    coverage: str = "scan",
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
    found.coverage = coverage
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
        inclusive_end(facts.last),
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
    "EMPTY_WINDOW",
    "FileRead",
    "IndexFile",
    "Localisation",
    "LocalWindow",
    "RENAME_DISCOVERY_QUERY",
    "RowSet",
    "SPLUNK_TIME_EPSILON",
    "SourceFacts",
    "accel_localise_query",
    "accel_probe_query",
    "accel_summaries",
    "cadence_facts",
    "coverage_label",
    "file_omitted",
    "file_route",
    "inclusive_end",
    "index_facts",
    "localise",
    "localise_query",
    "localise_width",
    "read_alert_rows",
    "read_anchors",
    "read_card_sample",
    "read_files",
    "read_mode",
    "read_windows",
    "route_filter",
    "sample_files",
    "sample_windows",
    "search_sourcetype_of",
    "select_local_windows",
    "source_route",
    "sourcetype_renames",
    "summary_window",
    "window_bounds",
]
