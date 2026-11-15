"""One tstats grid per observation kind, scored with hunt novelty and burst statistics."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from portal.modules.security.core.hunt.baselines import (
    BASELINES,
    active_hosts,
    counts_by_hour,
    cycle_seconds,
    episodes,
    index_entities,
    index_volume,
    peer_proportion,
    phase_burst,
)
from portal.modules.security.core.hunt.engine import (
    HOUR,
    Search,
    _burst,
    _literal_term_segments,
    _search_literal,
    host_hour_novelty,
)
from portal.modules.security.core.hunt.executor import (
    DEFAULT_BUDGETS,
    QUERY_BOUND,
    HuntBudget,
    HuntBudgetExceededError,
    HuntExecutor,
    executor_for,
    per_sample_cap,
)
from portal.modules.security.core.hunt.identity import (
    HostAliases,
    build_host_aliases,
    fold_host_rows,
    host_filter,
    identity_only,
)
from portal.modules.security.core.hunt.jobs import BudgetedSearch
from portal.modules.security.core.hunt.ranking import where_literal

KEY_SLICES = 4  # effort budget: time slices read while learning keys
KEY_SLICE_SAMPLE = 200  # effort budget: md5-ordered events read from one slice
KEY_BUDGET = 8  # effort budget: PREFIX grids; keys beyond this stay uncovered
GRID_SPLITS = 8  # effort budget: initial partitions after a query bound
_KEY = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=(?=[^\s"=])""")
_PAIR = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=([^\s"=]*)""")
_QUOTED = r'"((?:\\.|[^"])*)"'
_HOST_CONSTRAINT = re.compile(rf"host={_QUOTED}")
_WHERE_CONSTRAINT = re.compile(rf"where\s+([A-Za-z_][\w.]*)={_QUOTED}")
_TERM_CONSTRAINT = re.compile(rf"TERM\({_QUOTED}\)")
_PLAIN_TERM_CONSTRAINT = re.compile(rf"(?<![=\\\w]){_QUOTED}")


@dataclass(frozen=True)
class Observation:
    kind: str
    host: str
    entity: str
    hour: int
    score: float | None
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "host": self.host,
            "entity": self.entity,
            "hour": self.hour,
            "score": self.score,
            "evidence": self.evidence,
        }


@dataclass
class ObservationRun:
    observations: list[Observation]
    request_kinds: dict[str, dict[str, Any]]
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    grids: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    baseline: str = "current"
    host_name_count: int = 0
    host_machine_count: int = 0

    @property
    def coverage_complete(self) -> bool:
        return all(bool(slot.get("complete")) for slot in self.coverage.values())


def budgeted_search(search: Search) -> BudgetedSearch:
    """The runner's search: existing shared budgets, discovery phase, bounded transport."""
    return BudgetedSearch(search, HuntBudget(dict(DEFAULT_BUDGETS)))


def learned_pairs(raw: str) -> dict[str, str]:
    """First exact key=value for each key. `*` and quotes stay characters, not wildcards."""
    found: dict[str, str] = {}
    for key, value in _PAIR.findall(raw):
        found.setdefault(key, value)
    return found


def literal_query(
    kind: str,
    index: str,
    host: str,
    entity: str,
    *,
    host_aliases: Sequence[str] | None = None,
) -> str:
    """Build the search expression that rechecks a learned observation."""
    index_lit = _search_literal(index)
    host_lit = host_filter(host, host_aliases, _search_literal)
    if kind == "volume":
        return f"search index={index_lit} {host_lit}"
    if kind == "source":
        source, sourcetype = entity.split("\t", 1)
        return (
            f"search index={index_lit} {host_lit} "
            f"| where source={where_literal(source)} "
            f"| where sourcetype={where_literal(sourcetype)}"
        )
    if kind == "shape":
        return f"search index={index_lit} {host_lit} | where punct={where_literal(entity)}"
    if kind == "stream":
        sourcetype, punct = entity.split("\t", 1)
        return (
            f"search index={index_lit} {host_lit} "
            f"| where sourcetype={where_literal(sourcetype)} "
            f"| where punct={where_literal(punct)}"
        )
    if kind == "value":
        terms = _literal_term_segments(entity)
        if not terms:
            return ""
        return f"search index={index_lit} {host_lit} " + " ".join(
            _search_literal(term) for term in terms
        )
    return f"search index={index_lit} {host_lit} {_search_literal(entity)}"


def _unescape(inner: str) -> str:
    return re.sub(r"\\(.)", r"\1", inner)


def _term_matches(raw: str, term: str) -> bool:
    return term in raw


def literal_matches(event: Mapping[str, Any], query: str) -> bool:
    """Exact field or indexed-term match for a literal_query; a `*` matches only a star."""
    hosts = [_unescape(match.group(1)) for match in _HOST_CONSTRAINT.finditer(query)]
    constraints: list[tuple[str, str]] = []
    constraints.extend(
        (match.group(1), _unescape(match.group(2))) for match in _WHERE_CONSTRAINT.finditer(query)
    )
    terms = [_unescape(match.group(1)) for match in _TERM_CONSTRAINT.finditer(query)]
    if "| where" not in query:
        terms.extend(_unescape(match.group(1)) for match in _PLAIN_TERM_CONSTRAINT.finditer(query))
    if not hosts and not constraints and not terms:
        return False
    fields: dict[str, str] = {
        "host": str(event.get("host", "")),
        "source": str(event.get("source", "")),
        "sourcetype": str(event.get("sourcetype", "")),
        "punct": str(event.get("punct", "")),
    }
    fields.update(learned_pairs(str(event.get("_raw", ""))))
    raw = str(event.get("_raw", ""))
    return (
        (not hosts or fields["host"] in hosts)
        and all(fields.get(name) == value for name, value in constraints)
        and all(_term_matches(raw, term) for term in terms)
    )


def _sort_key(obs: Observation) -> tuple[bool, float, str, str, str, str, int]:
    # Total order: scored rows by descending score, then kind, host, entity, signal, hour.
    signal = str(obs.evidence.get("signal", ""))
    if obs.score is None:
        return (True, 0.0, obs.kind, obs.host, obs.entity, signal, obs.hour)
    return (False, -obs.score, obs.kind, obs.host, obs.entity, signal, obs.hour)


def _issue(
    executor: HuntExecutor,
    query: str,
    start: float,
    end: float,
    kind: str,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        read = executor.read(query, start, end, kind=kind, row_cap=per_sample_cap(query))
    except HuntBudgetExceededError:
        return [], executor.budget.exhausted or "request_budget_exhausted"
    return read.rows, read.reason


def _as_int(rows: list[dict[str, Any]], field: str) -> int | None:
    if len(rows) != 1 or field not in rows[0]:
        return None
    try:
        return int(float(rows[0][field]))
    except (TypeError, ValueError):
        return None


def _cell_count(row: Mapping[str, Any]) -> int:
    return int(float(row["count"]))


def _epoch_hour(value: Any) -> int:
    return int(float(value)) // HOUR * HOUR


def _tstats(index: str, by: str) -> str:
    return f"| tstats count where index={_search_literal(index)} {by}"


def _hour_partitions(start: float, end: float, pieces: int) -> list[tuple[float, float]]:
    if end <= start or pieces <= 1:
        return [(start, end)]
    first = int(start // HOUR)
    last = int(math.nextafter(end, -math.inf) // HOUR)
    hours = last - first + 1
    if hours <= 1:
        return [(start, end)]
    count = min(pieces, hours)
    base, extra = divmod(hours, count)
    parts: list[tuple[float, float]] = []
    cursor = first
    for _ in range(count):
        take = base + (1 if len(parts) < extra else 0)
        lo = start if cursor == first else float(cursor * HOUR)
        hi_hour = cursor + take - 1
        hi = end if hi_hour == last else float((hi_hour + 1) * HOUR)
        parts.append((float(lo), float(hi)))
        cursor += take
    return parts


def _load_once(
    executor: HuntExecutor,
    index: str,
    by: str,
    start: float,
    end: float,
    kind: str,
    suffix: str,
) -> tuple[list[dict[str, Any]], str | None]:
    counted, reason = _issue(
        executor, f"{_tstats(index, by)} | stats count as groups", start, end, kind
    )
    if reason:
        return [], reason
    expected = _as_int(counted, "groups")
    if expected is None:
        return [], "censored"
    fetched, reason = _issue(executor, f"{_tstats(index, by)}{suffix}", start, end, kind)
    if reason:
        return [], reason
    if len(fetched) != expected:
        return [], "truncated"
    return fetched, None


@dataclass
class _GridLoad:
    rows: list[dict[str, Any]] = field(default_factory=list)
    pieces: int = 0
    loaded_pieces: int = 0
    reasons: list[str] = field(default_factory=list)
    unread_ranges: list[dict[str, Any]] = field(default_factory=list)
    stopped: bool = False


def _weighted_hour_groups(
    totals: Mapping[int, int], hours: list[int], pieces: int
) -> list[list[int]]:
    count = min(max(1, pieces), len(hours))
    groups: list[list[int]] = []
    offset = 0
    remaining = sum(totals[hour] for hour in hours)
    while count > 1:
        target = remaining / count
        max_stop = len(hours) - (count - 1)
        stop = offset + 1
        weight = 0
        while stop <= max_stop:
            weight += totals[hours[stop - 1]]
            if weight >= target:
                previous = weight - totals[hours[stop - 1]]
                if stop > offset + 1 and abs(previous - target) < abs(weight - target):
                    weight = previous
                    stop -= 1
                break
            stop += 1
        group = hours[offset:stop]
        groups.append(group)
        remaining -= sum(totals[hour] for hour in group)
        offset = stop
        count -= 1
    groups.append(hours[offset:])
    return [group for group in groups if group]


def _data_partitions(
    totals: Mapping[int, int], start: float, end: float, pieces: int
) -> list[tuple[float, float, list[int]]]:
    hours = [
        hour
        for hour, count in sorted(totals.items())
        if count > 0 and hour < end and hour + HOUR > start
    ]
    groups = _weighted_hour_groups(totals, hours, pieces) if hours else []
    return [
        (max(start, float(group[0])), min(end, float(group[-1] + HOUR)), group) for group in groups
    ]


def _mark_unread(
    state: _GridLoad,
    totals: Mapping[int, int] | None,
    start: float,
    end: float,
    reason: str,
) -> None:
    if reason not in state.reasons:
        state.reasons.append(reason)
    hours = [hour for hour in (totals or {}) if hour < end and hour + HOUR > start]
    events = sum((totals or {})[hour] for hour in hours)
    total_events = sum((totals or {}).values())
    state.unread_ranges.append(
        {
            "start": start,
            "end": end,
            "data_hours": len(hours) if totals is not None else None,
            "events": events if totals is not None else None,
            "event_share": events / total_events if totals is not None and total_events else None,
            "reason": reason,
        }
    )
    if "budget_exhausted" in reason or reason == "job_deadline_exceeded":
        state.stopped = True


def _read_piece(
    executor: HuntExecutor,
    index: str,
    by: str,
    kind: str,
    suffix: str,
    start: float,
    end: float,
    hours: list[int],
    totals: Mapping[int, int],
    state: _GridLoad,
) -> None:
    if state.stopped:
        _mark_unread(state, totals, start, end, executor.budget.exhausted or "budget_exhausted")
        return
    state.pieces += 1
    rows, reason = _load_once(executor, index, by, start, end, kind, suffix)
    if reason is None:
        state.rows.extend(rows)
        state.loaded_pieces += 1
        return
    if reason == QUERY_BOUND and len(hours) > 1:
        parts = _data_partitions(totals, start, end, 2)
        if len(parts) > 1:
            for lo, hi, group in parts:
                _read_piece(executor, index, by, kind, suffix, lo, hi, group, totals, state)
            return
    _mark_unread(state, totals, start, end, reason)


def _read_time_piece(
    executor: HuntExecutor,
    index: str,
    by: str,
    kind: str,
    suffix: str,
    start: float,
    end: float,
    state: _GridLoad,
) -> None:
    if state.stopped:
        _mark_unread(state, None, start, end, executor.budget.exhausted or "budget_exhausted")
        return
    state.pieces += 1
    rows, reason = _load_once(executor, index, by, start, end, kind, suffix)
    if reason is None:
        state.rows.extend(rows)
        state.loaded_pieces += 1
        return
    parts = _hour_partitions(start, end, 2) if reason == QUERY_BOUND else []
    if len(parts) > 1:
        for lo, hi in parts:
            _read_time_piece(executor, index, by, kind, suffix, lo, hi, state)
        return
    _mark_unread(state, None, start, end, reason)


def _load_grid(
    executor: HuntExecutor,
    index: str,
    by: str,
    start: float,
    end: float,
    kind: str,
    suffix: str = "",
    totals: Mapping[int, int] | None = None,
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    """Load one grid, splitting a bounded read over the populated hour buckets."""
    rows, reason = _load_once(executor, index, by, start, end, kind, suffix)
    state = _GridLoad(rows=list(rows), pieces=1, loaded_pieces=int(reason is None))
    if reason:
        if reason == QUERY_BOUND and kind == "volume" and totals is None:
            for lo, hi in _hour_partitions(start, end, GRID_SPLITS):
                _read_time_piece(executor, index, by, kind, suffix, lo, hi, state)
        elif reason != QUERY_BOUND or totals is None:
            _mark_unread(state, totals, start, end, reason)
        else:
            parts = _data_partitions(totals, start, end, GRID_SPLITS)
            narrowed = len(parts) > 1 or bool(parts and (parts[0][0] > start or parts[0][1] < end))
            if narrowed:
                for lo, hi, hours in parts:
                    _read_piece(executor, index, by, kind, suffix, lo, hi, hours, totals, state)
            else:
                _mark_unread(state, totals, start, end, reason)
    total_events = sum(totals.values(), 0) if totals is not None else 0
    unread_event_count = (
        None
        if any(item["events"] is None for item in state.unread_ranges)
        else sum(int(item["events"] or 0) for item in state.unread_ranges)
    )
    stats = {
        "pieces": state.pieces,
        "loaded_pieces": state.loaded_pieces,
        "rows": len(state.rows),
        "reasons": state.reasons,
        "unread_ranges": state.unread_ranges,
        "unread_event_count": unread_event_count,
        "unread_event_share": (
            unread_event_count / total_events
            if unread_event_count is not None and total_events
            else None
        ),
    }
    return state.rows, state.reasons[0] if state.reasons else None, stats


def _coverage(reason: str | None, **extra: Any) -> dict[str, Any]:
    reasons = [reason] if reason else []
    slot: dict[str, Any] = {"complete": not reasons, "reasons": reasons}
    slot.update(extra)
    return slot


def _novelty(origin: int, hour: int) -> float:
    """First-seen weight from host_hour_novelty. No prior history is no surprise."""
    if hour <= origin:
        return 0.0
    rows = [
        {"host": "h", "source": "s", "punct": "a", "_time": origin, "count": 1},
        {"host": "h", "source": "s", "punct": "b", "_time": hour, "count": 1},
    ]
    scored = host_hour_novelty(rows, span=HOUR)
    return float(scored.get((hour, "h"), (0.0, []))[0])


def _prior_rows(series: dict[int, int], hour: int) -> list[dict[str, int]]:
    return [{"hour": stamp, "count": series[stamp]} for stamp in sorted(series) if stamp < hour]


def _literal(kind: str, index: str, host: str, entity: str) -> str:
    return literal_query(kind, index, host, entity)


def _emit(
    kind: str,
    host: str,
    entity: str,
    hour: int,
    score: float,
    evidence: dict[str, Any],
    index: str,
) -> Observation:
    evidence = dict(evidence)
    evidence["literal"] = _literal(kind, index, host, entity)
    return Observation(kind, host, entity, hour, score, evidence)


def _score_series(
    kind: str,
    host: str,
    entity: str,
    series: dict[int, int],
    origin: int,
    index: str,
) -> tuple[list[Observation], str | None]:
    """One record per observed hour: first hour is novelty, later hours are burst z."""
    hours = sorted(stamp for stamp, count in series.items() if count > 0)
    if not hours:
        return [], None
    found: list[Observation] = []
    first = hours[0]
    for hour in hours:
        now = series[hour]
        if hour == first:
            found.append(
                _emit(
                    kind,
                    host,
                    entity,
                    hour,
                    _novelty(origin, hour),
                    {
                        "signal": "novelty",
                        "now": now,
                        "origin_hour": origin,
                        "prior": _prior_rows(series, hour),
                        "prior_median": None,
                        "prior_hours_active": None,
                    },
                    index,
                )
            )
            continue
        burst = _burst(entity, hour, series)
        if burst is None:
            return [], "unscored"
        found.append(
            _emit(
                kind,
                host,
                entity,
                hour,
                burst.z,
                {
                    "signal": "burst",
                    "now": burst.this_hour,
                    "origin_hour": origin,
                    "prior": _prior_rows(series, hour),
                    "prior_median": burst.prior_median,
                    "prior_hours_active": burst.prior_hours_active,
                },
                index,
            )
        )
    return found, None


def _add_hour(grouped: dict[str, dict[int, int]], host: str, hour: int, count: int) -> None:
    bucket = grouped.setdefault(host, {})
    bucket[hour] = bucket.get(hour, 0) + count


def _volume_series(rows: list[dict[str, Any]]) -> dict[str, dict[int, int]]:
    grouped: dict[str, dict[int, int]] = {}
    for row in rows:
        _add_hour(grouped, str(row["host"]), _epoch_hour(row["_time"]), _cell_count(row))
    return grouped


def _pair_series(
    rows: list[dict[str, Any]], left: str, right: str
) -> dict[tuple[str, str, str], dict[int, int]]:
    grouped: dict[tuple[str, str, str], dict[int, int]] = {}
    for row in rows:
        ident = (str(row["host"]), str(row[left]), str(row[right]))
        hour = _epoch_hour(row["_time"])
        bucket = grouped.setdefault(ident, {})
        bucket[hour] = bucket.get(hour, 0) + _cell_count(row)
    return grouped


def _prefix_value(row: Mapping[str, Any], key: str) -> str:
    for name in ("v", f"{key}=", f"PREFIX({key}=)"):
        cell = row.get(name)
        if cell not in (None, ""):
            return str(cell)
    raise KeyError(key)


def _value_series(rows: list[dict[str, Any]], key: str) -> dict[tuple[str, str], dict[int, int]]:
    grouped: dict[tuple[str, str], dict[int, int]] = {}
    for row in rows:
        ident = (str(row["host"]), _prefix_value(row, key))
        hour = _epoch_hour(row["_time"])
        bucket = grouped.setdefault(ident, {})
        bucket[hour] = bucket.get(hour, 0) + _cell_count(row)
    return grouped


def _episode_bounds(series: Mapping[int, int]) -> list[tuple[int, int]]:
    return [(group[0], group[-1]) for group in episodes(series)]


def _primary_start(series: Mapping[int, int]) -> int | None:
    groups = episodes(series)
    if not groups:
        return None
    return max(groups, key=lambda group: (len(group), -group[0]))[0]


def _clip(series: Mapping[int, int], start: int, stop: int) -> dict[int, int]:
    return {hour: count for hour, count in series.items() if start <= hour <= stop and count > 0}


def _host_windows(
    host_hours: Mapping[str, Mapping[int, int]],
) -> dict[str, tuple[int, list[tuple[int, int]]]]:
    windows: dict[str, tuple[int, list[tuple[int, int]]]] = {}
    for host, series in host_hours.items():
        start = _primary_start(series)
        if start is None:
            continue
        windows[host] = (start, _episode_bounds(series))
    return windows


def _score_pieces(
    kind: str,
    host: str,
    entity: str,
    series: Mapping[int, int],
    bounds: list[tuple[int, int]],
    primary_start: int,
    primary_origin: int,
    index: str,
) -> tuple[list[Observation], str | None]:
    found: list[Observation] = []
    for start, stop in bounds:
        piece = _clip(series, start, stop)
        if not piece:
            continue
        origin = primary_origin if start == primary_start else start
        scored, reason = _score_series(kind, host, entity, piece, origin, index)
        if reason:
            return [], reason
        found.extend(scored)
    return found, None


def _from_volume(rows: list[dict[str, Any]], index: str) -> tuple[list[Observation], str | None]:
    grouped = _volume_series(rows)
    if not grouped:
        return [], None
    windows = _host_windows(grouped)
    origin = min(start for start, _bounds in windows.values())
    found: list[Observation] = []
    for host in sorted(grouped):
        start, bounds = windows[host]
        scored, reason = _score_pieces(
            "volume", host, "", grouped[host], bounds, start, origin, index
        )
        if reason:
            return [], reason
        found.extend(scored)
    return found, None


def _from_pairs(
    kind: str,
    rows: list[dict[str, Any]],
    index: str,
    left: str,
    right: str,
) -> tuple[list[Observation], str | None]:
    grouped = _pair_series(rows, left, right)
    host_hours: dict[str, dict[int, int]] = {}
    for (host, _left, _right), series in grouped.items():
        for hour, count in series.items():
            _add_hour(host_hours, host, hour, count)
    windows = _host_windows(host_hours)
    found: list[Observation] = []
    for host, left_value, right_value in sorted(grouped):
        entity = right_value if kind == "shape" else f"{left_value}\t{right_value}"
        start, bounds = windows[host]
        scored, reason = _score_pieces(
            kind,
            host,
            entity,
            grouped[(host, left_value, right_value)],
            bounds,
            start,
            start,
            index,
        )
        if reason:
            return [], reason
        found.extend(scored)
    return found, None


def _slice_query(index: str) -> str:
    literal = _search_literal(index)
    return (
        f"search index={literal} | eval _k=md5(_raw) | sort {KEY_SLICE_SAMPLE} _k _time _raw "
        f"| head {KEY_SLICE_SAMPLE} | table _raw"
    )


def _slice_hours(hours: list[int]) -> list[int]:
    ordered = sorted(set(hours))
    if len(ordered) <= KEY_SLICES:
        return ordered
    if KEY_SLICES <= 1:
        return ordered[:1]
    last = len(ordered) - 1
    picked: list[int] = []
    for step in range(KEY_SLICES):
        hour = ordered[round(step * last / (KEY_SLICES - 1))]
        if not picked or picked[-1] != hour:
            picked.append(hour)
    return picked


def _hour_volume(rows: list[dict[str, Any]]) -> dict[int, int]:
    totals: dict[int, int] = {}
    for row in rows:
        hour = _epoch_hour(row["_time"])
        totals[hour] = totals.get(hour, 0) + _cell_count(row)
    return totals


def _learned_keys(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        for key in set(_KEY.findall(str(row.get("_raw", "")))):
            counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _earliest_value(
    grouped: dict[tuple[str, str], dict[int, int]],
) -> dict[str, tuple[int, int]]:
    """Earliest hour of each value and that hour's count. Ties break by host name."""
    best: dict[str, tuple[int, str, int]] = {}
    for (host, value), series in grouped.items():
        first = min(series)
        current = best.get(value)
        if current is None or (first, host) < (current[0], current[1]):
            best[value] = (first, host, series[first])
    return {value: (hour, count) for value, (hour, _host, count) in best.items()}


def _new_host_records(
    key: str,
    grouped: dict[tuple[str, str], dict[int, int]],
    index: str,
) -> list[Observation]:
    earliest = _earliest_value(grouped)
    found: list[Observation] = []
    for (host, value), series in sorted(grouped.items()):
        first = min(series)
        origin, origin_count = earliest[value]
        score = _novelty(origin, first)
        if score == 0.0:
            continue
        found.append(
            _emit(
                "value",
                host,
                f"{key}={value}",
                first,
                score,
                {
                    "signal": "new_host",
                    "now": series[first],
                    "origin_hour": origin,
                    "prior": [{"hour": origin, "count": origin_count}],
                    "prior_median": None,
                    "prior_hours_active": None,
                },
                index,
            )
        )
    return found


def _primary_values(
    grouped: dict[tuple[str, str], dict[int, int]],
    windows: Mapping[str, tuple[int, list[tuple[int, int]]]],
) -> dict[tuple[str, str], dict[int, int]]:
    kept: dict[tuple[str, str], dict[int, int]] = {}
    for (host, value), series in grouped.items():
        start, bounds = windows[host]
        for begin, end in bounds:
            if begin != start:
                continue
            piece = _clip(series, begin, end)
            if piece:
                kept[(host, value)] = piece
    return kept


def _from_values(
    key: str, rows: list[dict[str, Any]], index: str
) -> tuple[list[Observation], str | None]:
    grouped = _value_series(rows, key)
    host_hours: dict[str, dict[int, int]] = {}
    for (host, _value), series in grouped.items():
        for hour, count in series.items():
            _add_hour(host_hours, host, hour, count)
    windows = _host_windows(host_hours)
    found: list[Observation] = []
    for host, value in sorted(grouped):
        start, bounds = windows[host]
        scored, reason = _score_pieces(
            "value", host, f"{key}={value}", grouped[(host, value)], bounds, start, start, index
        )
        if reason:
            return [], reason
        found.extend(scored)
    found.extend(_new_host_records(key, _primary_values(grouped, windows), index))
    return found, None


def _score_loaded(
    kind: str, rows: list[dict[str, Any]], index: str
) -> tuple[list[Observation], str | None]:
    if kind == "volume":
        return _from_volume(rows, index)
    if kind == "source":
        return _from_pairs("source", rows, index, "source", "sourcetype")
    if kind == "shape":
        return _from_pairs("shape", rows, index, "punct", "punct")
    if kind == "stream":
        return _from_pairs("stream", rows, index, "sourcetype", "punct")
    raise KeyError(kind)


def _folded_volume(
    volume_rows: list[dict[str, Any]] | None, host_aliases: HostAliases | None
) -> list[dict[str, Any]] | None:
    if volume_rows is None or host_aliases is None:
        return volume_rows
    return fold_host_rows(volume_rows, host_aliases)


def _safe_partial_observations(
    found: list[Observation],
    volume_rows: list[dict[str, Any]] | None,
    unread_ranges: list[dict[str, Any]],
) -> tuple[list[Observation], int]:
    if not unread_ranges or volume_rows is None:
        return found, 0
    missed: dict[str, int] = {}
    for row in volume_rows:
        hour = _epoch_hour(row["_time"])
        if any(part["start"] < hour + HOUR and hour < part["end"] for part in unread_ranges):
            host = str(row["host"])
            missed[host] = min(hour, missed.get(host, hour))
    kept: list[Observation] = []
    for obs in found:
        history_missing = obs.hour >= missed.get(obs.host, float("inf"))
        value_origin_missing = obs.evidence.get("signal") == "new_host" and any(
            part["start"] < obs.hour + HOUR for part in unread_ranges
        )
        if not history_missing and not value_origin_missing:
            kept.append(obs)
    return kept, len(found) - len(kept)


def _observe_one(
    executor: HuntExecutor,
    index: str,
    kind: str,
    by: str,
    start: float,
    end: float,
    coverage: dict[str, dict[str, Any]],
    host_aliases: HostAliases | None = None,
    totals: Mapping[int, int] | None = None,
    volume_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[Observation], list[dict[str, Any]] | None, HostAliases | None]:
    rows, reason, stats = _load_grid(executor, index, by, start, end, kind, totals=totals)
    if reason and not rows:
        coverage[kind] = _coverage(reason, **stats)
        return [], None, host_aliases
    try:
        if kind == "volume":
            host_aliases = build_host_aliases(rows)
        scoring_rows = fold_host_rows(rows, host_aliases) if host_aliases is not None else rows
        scored, score_reason = _score_loaded(kind, scoring_rows, index)
    except (KeyError, TypeError, ValueError):
        coverage[kind] = {
            "complete": False,
            **stats,
            "reasons": _unique([*stats["reasons"], "censored"]),
        }
        return [], rows, host_aliases
    history = _folded_volume(volume_rows, host_aliases)
    scored, suppressed = _safe_partial_observations(scored, history, stats["unread_ranges"])
    reasons = _unique([*stats["reasons"], *[item for item in (reason, score_reason) if item]])
    coverage[kind] = {"complete": not reasons, "reasons": reasons, **stats}
    if suppressed:
        coverage[kind]["unscored_observations"] = suppressed
        coverage[kind]["unscored_reason"] = "unread host history is withheld"
    return (scored, rows, host_aliases) if score_reason is None else ([], rows, host_aliases)


_STRUCTURAL = (
    ("volume", "by host _time span=1h"),
    ("source", "by host source sourcetype _time span=1h"),
    ("shape", "by host punct _time span=1h"),
    ("stream", "by host sourcetype punct _time span=1h"),
)


def _observe_structural(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    coverage: dict[str, dict[str, Any]],
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]], HostAliases | None]:
    found: list[Observation] = []
    grids: dict[str, list[dict[str, Any]]] = {}
    host_aliases: HostAliases | None = None
    for kind, by in _STRUCTURAL:
        volume_rows = grids.get("volume") if coverage.get("volume", {}).get("complete") else None
        totals = _hour_volume(volume_rows) if volume_rows is not None else None
        scored, rows, host_aliases = _observe_one(
            executor, index, kind, by, start, end, coverage, host_aliases, totals, volume_rows
        )
        found.extend(scored)
        if rows is not None:
            grids[kind] = rows
    return found, grids, host_aliases


def _unique(reasons: list[str]) -> list[str]:
    found: list[str] = []
    for reason in reasons:
        if reason not in found:
            found.append(reason)
    return found


def _read_slices(
    executor: HuntExecutor,
    index: str,
    volume_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    totals = _hour_volume(volume_rows)
    chosen = _slice_hours(list(totals))
    reasons: list[str] = []
    if len(totals) > len(chosen):
        reasons.append("slice_budget")
    rows: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    for hour in chosen:
        got, reason = _issue(executor, _slice_query(index), hour, hour + HOUR, "key_sample")
        entry: dict[str, Any] = {
            "hour": hour,
            "returned": 0 if reason else len(got),
            "volume": totals[hour],
        }
        if reason:
            entry["reason"] = reason
            reasons.append(reason)
        else:
            if len(got) < totals[hour]:
                reasons.append("sample_budget")
            rows.extend(got)
        slices.append(entry)
    return rows, reasons, slices


def _query_keys(
    executor: HuntExecutor,
    index: str,
    queried: list[tuple[str, int]],
    start: float,
    end: float,
    reasons: list[str],
    host_aliases: HostAliases | None,
    totals: Mapping[int, int],
    volume_rows: list[dict[str, Any]],
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    found: list[Observation] = []
    grids: dict[str, list[dict[str, Any]]] = {}
    details: dict[str, dict[str, Any]] = {}
    for key, _count in queried:
        by = f"by host PREFIX({key}=) _time span=1h"
        rows, reason, stats = _load_grid(
            executor,
            index,
            by,
            start,
            end,
            f"value:{key}",
            suffix=f' | rename "{key}=" as v',
            totals=totals,
        )
        reasons.extend(stats["reasons"])
        details[key] = {
            "complete": reason is None,
            "reasons": _unique([*stats["reasons"], *([reason] if reason else [])]),
            "unscored_observations": 0,
            **stats,
        }
        if reason and not rows:
            continue
        grids[f"value:{key}"] = rows
        try:
            scoring_rows = fold_host_rows(rows, host_aliases) if host_aliases is not None else rows
            scored, score_reason = _from_values(key, scoring_rows, index)
        except (KeyError, TypeError, ValueError):
            reasons.append("censored")
            details[key]["complete"] = False
            details[key]["reasons"] = _unique([*details[key]["reasons"], "censored"])
            continue
        if score_reason:
            reasons.append(score_reason)
            details[key]["complete"] = False
            details[key]["reasons"] = _unique([*details[key]["reasons"], score_reason])
            continue
        scored, suppressed = _safe_partial_observations(scored, volume_rows, stats["unread_ranges"])
        details[key]["unscored_observations"] = suppressed
        if suppressed:
            details[key]["unscored_reason"] = "unread host history is withheld"
        found.extend(scored)
    return found, grids, details


def _value_coverage(
    reasons: list[str],
    skipped: list[str],
    slices: list[dict[str, Any]],
    grid_coverage: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    grids = grid_coverage or {}
    return {
        "complete": not reasons,
        "reasons": _unique(reasons),
        "unqueried_keys": skipped,
        "slices": slices,
        "grid_coverage": grids,
        "pieces": sum(int(slot["pieces"]) for slot in grids.values()),
        "loaded_pieces": sum(int(slot["loaded_pieces"]) for slot in grids.values()),
        "rows": sum(int(slot["rows"]) for slot in grids.values()),
        "unscored_observations": sum(int(slot["unscored_observations"]) for slot in grids.values()),
    }


def _observe_values(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    volume_rows: list[dict[str, Any]] | None,
    host_aliases: HostAliases | None,
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if volume_rows is None:
        return [], {}, _value_coverage(["volume_incomplete"], [], [])
    sample, reasons, slices = _read_slices(executor, index, volume_rows)
    ranked = _learned_keys(sample)
    queried = ranked[:KEY_BUDGET]
    skipped = [key for key, _count in ranked[KEY_BUDGET:]]
    if skipped:
        reasons.append("key_budget")
    found, grids, grid_coverage = _query_keys(
        executor,
        index,
        queried,
        start,
        end,
        reasons,
        host_aliases,
        _hour_volume(volume_rows),
        _folded_volume(volume_rows, host_aliases) or [],
    )
    return found, grids, _value_coverage(reasons, skipped, slices, grid_coverage)


def _split_grid(name: str) -> tuple[str, str]:
    if name.startswith("value:"):
        return "value", name.split(":", 1)[1]
    return name, ""


def _score_present(
    grids: dict[str, list[dict[str, Any]]],
    index: str,
    coverage: dict[str, dict[str, Any]] | None = None,
) -> list[Observation]:
    found: list[Observation] = []
    volume_rows = (
        grids.get("volume") if (coverage or {}).get("volume", {}).get("complete") else None
    )
    for name in sorted(grids):
        kind, key = _split_grid(name)
        try:
            if kind == "value":
                scored, reason = _from_values(key, grids[name], index)
            else:
                scored, reason = _score_loaded(kind, grids[name], index)
        except (KeyError, TypeError, ValueError):
            continue
        if reason is None:
            detail = (coverage or {}).get(kind, {})
            if kind == "value":
                detail = detail.get("grid_coverage", {}).get(key, {})
            scored, _suppressed = _safe_partial_observations(
                scored, volume_rows, detail.get("unread_ranges", [])
            )
            found.extend(scored)
    return found


@dataclass
class _View:
    cycles: dict[str, int | None]
    host_first: dict[str, int]
    bounds: dict[str, list[tuple[int, int]]]
    active: dict[int, set[str]]
    series: dict[str, dict[tuple[str, str], dict[int, int]]]
    by_hour: dict[str, dict[tuple[str, int], dict[str, int]]]


def _baseline_view(grids: dict[str, list[dict[str, Any]]]) -> _View:
    volume = index_volume(grids.get("volume", []))
    cycles = {host: cycle_seconds(series) for host, series in volume.items()}
    host_first = {
        host: start
        for host, series in volume.items()
        if (start := _primary_start(series)) is not None
    }
    bounds = {host: _episode_bounds(series) for host, series in volume.items()}
    series: dict[str, dict[tuple[str, str], dict[int, int]]] = {}
    by_hour: dict[str, dict[tuple[str, int], dict[str, int]]] = {}
    for name, rows in grids.items():
        kind, key = _split_grid(name)
        grouped = index_entities(kind, rows, key)
        series[name] = grouped
        by_hour[name] = counts_by_hour(grouped)
    return _View(cycles, host_first, bounds, active_hosts(volume), series, by_hour)


def _clip_to_episode(
    series: Mapping[int, int], hour: int, bounds: list[tuple[int, int]]
) -> dict[int, int]:
    for start, stop in bounds:
        if start <= hour <= stop:
            return _clip(series, start, stop)
    return dict(series)


def _grid_key(obs: Observation) -> str:
    if obs.kind == "value":
        return "value:" + obs.entity.split("=", 1)[0]
    return obs.kind


def _current(obs: Observation) -> float:
    if obs.score is None:
        raise ValueError("current score")
    return obs.score


def _seasonal_score(
    obs: Observation, series: dict[int, int], measured: int | None, has_volume: bool
) -> tuple[float | None, str | None]:
    if not has_volume:
        return None, "no_volume"
    if measured is None:
        return None, "no_cycle"
    positive = sorted(hour for hour, count in series.items() if count > 0)
    if obs.evidence["signal"] in {"novelty", "new_host"} or obs.hour == positive[0]:
        return _current(obs), None
    score = phase_burst(obs.entity, obs.hour, series, measured)
    if score is None:
        return None, "no_phase_history"
    return score, None


def _left_score(
    obs: Observation, series: dict[int, int], view: _View
) -> tuple[float | None, bool, str | None, int | None, str]:
    if obs.host not in view.host_first:
        return _current(obs), False, None, None, "no_volume"
    measured = view.cycles.get(obs.host)
    period = HOUR if measured is None else measured
    source = "one_bucket" if measured is None else "cycle"
    first = min(hour for hour, count in series.items() if count > 0)
    host_first = _episode_start(view, obs.host, obs.hour)
    censored = first < host_first + period
    withheld = censored and obs.evidence["signal"] in {"novelty", "new_host"} and obs.hour == first
    if withheld:
        return None, True, "first-seen at retention start", period, source
    return _current(obs), False, None, period, source


def _episode_start(view: _View, host: str, hour: int) -> int:
    for start, stop in view.bounds.get(host, ()):
        if start <= hour <= stop:
            return start
    return view.host_first[host]


def _with_baselines(obs: Observation, view: _View) -> Observation:
    raw = view.series[_grid_key(obs)][(obs.host, obs.entity)]
    series = _clip_to_episode(raw, obs.hour, view.bounds.get(obs.host, []))
    measured = view.cycles.get(obs.host)
    seasonal, seasonal_fallback = _seasonal_score(
        obs, series, measured, obs.host in view.host_first
    )
    counts = view.by_hour[_grid_key(obs)].get((obs.entity, obs.hour), {})
    peer = peer_proportion(
        int(obs.evidence["now"]), obs.host, counts, view.active.get(obs.hour, ())
    )
    left_score, censored, mark, left_period, left_source = _left_score(obs, series, view)
    evidence = dict(obs.evidence)
    evidence["scores"] = {
        "current": _current(obs),
        "seasonal": seasonal,
        "peer": peer,
        "left": left_score,
    }
    evidence["seasonal_period"] = measured
    evidence["seasonal_fallback"] = seasonal_fallback
    evidence["peer_fallback"] = None if peer is not None else "no_peers"
    evidence["left_censored"] = censored
    evidence["left_period"] = left_period
    evidence["left_period_source"] = left_source
    if mark:
        evidence["mark"] = mark
    return Observation(obs.kind, obs.host, obs.entity, obs.hour, obs.score, evidence)


def _select(obs: Observation, baseline: str) -> Observation:
    scores = obs.evidence["scores"]
    if baseline == "left":
        score = scores["left"]
    elif baseline == "seasonal" and scores["seasonal"] is not None:
        score = scores["seasonal"]
    elif baseline == "peer" and scores["peer"] is not None:
        score = scores["peer"]
    else:
        score = scores["current"]
    if score == obs.score:
        return obs
    return Observation(obs.kind, obs.host, obs.entity, obs.hour, score, obs.evidence)


def _check_baseline(baseline: str) -> None:
    if baseline not in BASELINES:
        raise ValueError(baseline)


def _host_aliases_for_grids(grids: Mapping[str, list[dict[str, Any]]]) -> HostAliases:
    volume = grids.get("volume")
    if volume:
        return build_host_aliases(volume)
    names = {str(row["host"]) for rows in grids.values() for row in rows}
    return identity_only(names)


def _with_host_aliases(
    observations: Iterable[Observation], index: str, aliases: HostAliases
) -> list[Observation]:
    found: list[Observation] = []
    for observation in observations:
        host = aliases.display(observation.host)
        spellings = aliases.spellings(host)
        evidence = dict(observation.evidence)
        evidence["literal"] = literal_query(
            observation.kind, index, host, observation.entity, host_aliases=spellings
        )
        if len(spellings) > 1:
            evidence["host_aliases"] = list(spellings)
        else:
            evidence.pop("host_aliases", None)
        found.append(
            Observation(
                observation.kind,
                host,
                observation.entity,
                observation.hour,
                observation.score,
                evidence,
            )
        )
    return found


def _finish(
    found: list[Observation],
    grids: dict[str, list[dict[str, Any]]],
    coverage: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, Any]],
    baseline: str,
    index: str,
    aliases: HostAliases | None = None,
) -> ObservationRun:
    aliases = aliases or _host_aliases_for_grids(grids)
    folded_grids = {name: fold_host_rows(rows, aliases) for name, rows in grids.items()}
    view = _baseline_view(folded_grids)
    aliased = _with_host_aliases(found, index, aliases)
    chosen = [_select(_with_baselines(obs, view), baseline) for obs in aliased]
    chosen.sort(key=_sort_key)
    return ObservationRun(
        chosen,
        stats,
        coverage,
        grids,
        baseline,
        aliases.name_count,
        aliases.machine_count,
    )


def _attach_cost(
    coverage: dict[str, dict[str, Any]], request_kinds: dict[str, dict[str, Any]]
) -> None:
    for kind, slot in coverage.items():
        matching = (
            {name: stats for name, stats in request_kinds.items() if name.startswith("value:")}
            if kind == "value"
            else ({kind: request_kinds[kind]} if kind in request_kinds else {})
        )
        slot["requests"] = sum(int(stats["requests"]) for stats in matching.values())
        slot["seconds"] = round(sum(float(stats["seconds"]) for stats in matching.values()), 3)
        if kind == "value":
            for key, detail in slot.get("grid_coverage", {}).items():
                stats = request_kinds.get(f"value:{key}", {})
                detail["requests"] = int(stats.get("requests", 0))
                detail["seconds"] = round(float(stats.get("seconds", 0.0)), 3)


def observe(
    search: Search, index: str, start: float, end: float, baseline: str = "current"
) -> ObservationRun:
    """Exact entity-hour scores over full grids. A short or censored grid is incomplete."""
    _check_baseline(baseline)
    executor = executor_for(search)
    before = executor.stats()
    coverage: dict[str, dict[str, Any]] = {}
    found, grids, aliases = _observe_structural(executor, index, start, end, coverage)
    volume_slot = coverage.get("volume", {})
    volume_rows = grids.get("volume") if volume_slot.get("complete") else None
    values, value_grids, value_coverage = _observe_values(
        executor, index, start, end, volume_rows, aliases
    )
    grids.update(value_grids)
    coverage["value"] = value_coverage
    found.extend(values)
    request_kinds = executor.delta(before)
    _attach_cost(coverage, request_kinds)
    return _finish(found, grids, coverage, request_kinds, baseline, index, aliases)


def rescore(
    grids: dict[str, list[dict[str, Any]]],
    coverage: dict[str, dict[str, Any]],
    index: str,
    baseline: str = "current",
    request_kinds: dict[str, dict[str, Any]] | None = None,
) -> ObservationRun:
    """Score saved grids. The baseline flag selects which side-by-side number is primary."""
    _check_baseline(baseline)
    aliases = _host_aliases_for_grids(grids)
    folded_grids = {name: fold_host_rows(rows, aliases) for name, rows in grids.items()}
    found = _score_present(folded_grids, index, coverage)
    return _finish(found, grids, coverage, request_kinds or {}, baseline, index, aliases)


def _observation_from_dict(row: Mapping[str, Any]) -> Observation:
    score = row["score"]
    return Observation(
        str(row["kind"]),
        str(row["host"]),
        str(row["entity"]),
        int(row["hour"]),
        None if score is None else float(score),
        dict(row["evidence"]),
    )


def load_observations(directory: Path) -> list[Observation]:
    text = (directory / "observations.jsonl").read_text().splitlines()
    return [_observation_from_dict(json.loads(line)) for line in text if line]


def reorder(
    observations: list[Observation],
    baseline: str,
    coverage: dict[str, dict[str, Any]] | None = None,
    request_kinds: dict[str, dict[str, Any]] | None = None,
) -> ObservationRun:
    """Select one stored score and sort. Does not read grids or remeasure a cycle."""
    _check_baseline(baseline)
    chosen = [_select(obs, baseline) for obs in observations]
    chosen.sort(key=_sort_key)
    names = {
        str(name)
        for observation in chosen
        for name in observation.evidence.get("host_aliases", [observation.host])
    }
    aliases = identity_only(names)
    return ObservationRun(
        chosen,
        dict(request_kinds or {}),
        dict(coverage or {}),
        {},
        baseline,
        aliases.name_count,
        aliases.machine_count,
    )


def _grid_rel(name: str) -> Path:
    if name.startswith("value:"):
        key = name.split(":", 1)[1]
        if not key or "/" in key or key in {".", ".."}:
            raise ValueError(name)
        return Path("grids") / "value" / f"{key}.jsonl"
    if "/" in name:
        raise ValueError(name)
    return Path("grids") / f"{name}.jsonl"


def write_receipts(directory: Path, run: ObservationRun, progress: dict[str, Any]) -> None:
    """Write observations, the raw grids, and coverage so a later run can rescore offline."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(obs.as_dict(), sort_keys=True) for obs in run.observations]
    (directory / "observations.jsonl").write_text(("\n".join(lines) + "\n") if lines else "")
    grid_paths: dict[str, str] = {}
    for name, rows in sorted(run.grids.items()):
        rel = _grid_rel(name)
        path = directory / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        grid_paths[name] = rel.as_posix()
    body = dict(progress)
    body["baseline"] = run.baseline
    body["coverage_complete"] = run.coverage_complete
    body["coverage"] = run.coverage
    body["request_kinds"] = run.request_kinds
    body["observation_count"] = len(run.observations)
    body["host_name_count"] = run.host_name_count
    body["host_machine_count"] = run.host_machine_count
    body["order"] = "(-score, kind, host, entity, signal, hour); missing scores sort last"
    body["grids"] = grid_paths
    (directory / "progress.json").write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")


def load_receipts(directory: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    progress = json.loads((directory / "progress.json").read_text())
    grids: dict[str, list[dict[str, Any]]] = {}
    for name, rel in progress.get("grids", {}).items():
        text = (directory / str(rel)).read_text().splitlines()
        grids[str(name)] = [json.loads(line) for line in text if line]
    return grids, progress
