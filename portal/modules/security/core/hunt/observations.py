"""One tstats grid per observation kind, scored with hunt novelty and burst statistics."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
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
    _search_literal,
    host_hour_novelty,
)
from portal.modules.security.core.hunt.executor import (
    DEFAULT_BUDGETS,
    QUERY_BOUND,
    HuntBudget,
    HuntExecutor,
    executor_for,
    per_sample_cap,
)
from portal.modules.security.core.hunt.jobs import BudgetedSearch
from portal.modules.security.core.hunt.ranking import where_literal

KEY_SLICES = 4  # effort budget: time slices read while learning keys
KEY_SLICE_SAMPLE = 200  # effort budget: md5-ordered events read from one slice
KEY_BUDGET = 8  # effort budget: PREFIX grids; keys beyond this stay uncovered
GRID_SPLITS = 8  # effort budget: hour-partitions of one grid that did not finish in one query
_KEY = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=(?=[^\s"=])""")
_PAIR = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=([^\s"=]*)""")
_QUOTED = r'"((?:\\.|[^"])*)"'
_HOST_CONSTRAINT = re.compile(rf"host={_QUOTED}")
_WHERE_CONSTRAINT = re.compile(rf"where\s+([A-Za-z_][\w.]*)={_QUOTED}")
_TERM_CONSTRAINT = re.compile(rf"TERM\({_QUOTED}\)")


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


def literal_query(kind: str, index: str, host: str, entity: str) -> str:
    """Put a learned value back as a where-literal, never as a search wildcard."""
    index_lit = _search_literal(index)
    host_lit = _search_literal(host)
    if kind == "volume":
        return f"search index={index_lit} host={host_lit}"
    if kind == "source":
        source, sourcetype = entity.split("\t", 1)
        return (
            f"search index={index_lit} host={host_lit} "
            f"| where source={where_literal(source)} "
            f"| where sourcetype={where_literal(sourcetype)}"
        )
    if kind == "shape":
        return f"search index={index_lit} host={host_lit} | where punct={where_literal(entity)}"
    if kind == "stream":
        sourcetype, punct = entity.split("\t", 1)
        return (
            f"search index={index_lit} host={host_lit} "
            f"| where sourcetype={where_literal(sourcetype)} "
            f"| where punct={where_literal(punct)}"
        )
    # A learned value is one indexed term; a field comparison is not what the grid counted.
    return f"search index={index_lit} host={host_lit} TERM({_search_literal(entity)})"


def _unescape(inner: str) -> str:
    return re.sub(r"\\(.)", r"\1", inner)


def _term_matches(raw: str, term: str) -> bool:
    """The key=value a value literal encodes, as the PREFIX grid grouped it."""
    key, sep, value = term.partition("=")
    return bool(sep) and learned_pairs(raw).get(key) == value


def literal_matches(event: Mapping[str, Any], query: str) -> bool:
    """Exact field or indexed-term match for a literal_query; a `*` matches only a star."""
    constraints: list[tuple[str, str]] = []
    host = _HOST_CONSTRAINT.search(query)
    if host:
        constraints.append(("host", _unescape(host.group(1))))
    constraints.extend(
        (match.group(1), _unescape(match.group(2))) for match in _WHERE_CONSTRAINT.finditer(query)
    )
    terms = [_unescape(match.group(1)) for match in _TERM_CONSTRAINT.finditer(query)]
    if not constraints and not terms:
        return False
    fields: dict[str, str] = {
        "host": str(event.get("host", "")),
        "source": str(event.get("source", "")),
        "sourcetype": str(event.get("sourcetype", "")),
        "punct": str(event.get("punct", "")),
    }
    fields.update(learned_pairs(str(event.get("_raw", ""))))
    raw = str(event.get("_raw", ""))
    return all(fields.get(name) == value for name, value in constraints) and all(
        _term_matches(raw, term) for term in terms
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
    read = executor.read(query, start, end, kind=kind, row_cap=per_sample_cap(query))
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
    """Contiguous hour slices of [start, end). One slice when the window is a single hour."""
    if end <= start or pieces <= 1:
        return [(start, end)]
    first = int(start // HOUR)
    last = int((end - 1e-9) // HOUR)
    hours = last - first + 1
    if hours <= 1:
        return [(start, end)]
    count = min(pieces, hours)
    base, extra = divmod(hours, count)
    parts: list[tuple[float, float]] = []
    cursor = first
    for index in range(count):
        take = base + (1 if index < extra else 0)
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


def _load_grid(
    executor: HuntExecutor,
    index: str,
    by: str,
    start: float,
    end: float,
    kind: str,
    suffix: str = "",
    *,
    allow_split: bool = True,
) -> tuple[list[dict[str, Any]], str | None]:
    """One grid. A query the executor cut by its own time bound is re-read in hour partitions."""
    rows, reason = _load_once(executor, index, by, start, end, kind, suffix)
    if reason != QUERY_BOUND or not allow_split:
        return rows, reason
    parts = _hour_partitions(start, end, GRID_SPLITS)
    if len(parts) <= 1:
        return [], reason
    merged: list[dict[str, Any]] = []
    for lo, hi in parts:
        part, part_reason = _load_grid(executor, index, by, lo, hi, kind, suffix, allow_split=False)
        if part_reason:
            return [], part_reason
        merged.extend(part)
    return merged, None


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


def _observe_one(
    executor: HuntExecutor,
    index: str,
    kind: str,
    by: str,
    start: float,
    end: float,
    coverage: dict[str, dict[str, Any]],
) -> tuple[list[Observation], list[dict[str, Any]] | None]:
    rows, reason = _load_grid(executor, index, by, start, end, kind)
    if reason:
        coverage[kind] = _coverage(reason)
        return [], None
    try:
        scored, score_reason = _score_loaded(kind, rows, index)
    except (KeyError, TypeError, ValueError):
        coverage[kind] = _coverage("censored")
        return [], rows
    coverage[kind] = _coverage(score_reason)
    return (scored, rows) if score_reason is None else ([], rows)


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
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]]]:
    found: list[Observation] = []
    grids: dict[str, list[dict[str, Any]]] = {}
    for kind, by in _STRUCTURAL:
        scored, rows = _observe_one(executor, index, kind, by, start, end, coverage)
        found.extend(scored)
        if rows is not None:
            grids[kind] = rows
    return found, grids


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
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]]]:
    found: list[Observation] = []
    grids: dict[str, list[dict[str, Any]]] = {}
    for key, _count in queried:
        by = f"by host PREFIX({key}=) _time span=1h"
        rows, reason = _load_grid(
            executor, index, by, start, end, f"value:{key}", suffix=f' | rename "{key}=" as v'
        )
        if reason:
            reasons.append(reason)
            continue
        grids[f"value:{key}"] = rows
        try:
            scored, score_reason = _from_values(key, rows, index)
        except (KeyError, TypeError, ValueError):
            reasons.append("censored")
            continue
        if score_reason:
            reasons.append(score_reason)
            continue
        found.extend(scored)
    return found, grids


def _value_coverage(
    reasons: list[str], skipped: list[str], slices: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "complete": not reasons,
        "reasons": _unique(reasons),
        "unqueried_keys": skipped,
        "slices": slices,
    }


def _observe_values(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    volume_rows: list[dict[str, Any]] | None,
) -> tuple[list[Observation], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if volume_rows is None:
        return [], {}, _value_coverage(["volume_incomplete"], [], [])
    sample, reasons, slices = _read_slices(executor, index, volume_rows)
    ranked = _learned_keys(sample)
    queried = ranked[:KEY_BUDGET]
    skipped = [key for key, _count in ranked[KEY_BUDGET:]]
    if skipped:
        reasons.append("key_budget")
    found, grids = _query_keys(executor, index, queried, start, end, reasons)
    return found, grids, _value_coverage(reasons, skipped, slices)


def _split_grid(name: str) -> tuple[str, str]:
    if name.startswith("value:"):
        return "value", name.split(":", 1)[1]
    return name, ""


def _score_present(grids: dict[str, list[dict[str, Any]]], index: str) -> list[Observation]:
    found: list[Observation] = []
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


def _finish(
    found: list[Observation],
    grids: dict[str, list[dict[str, Any]]],
    coverage: dict[str, dict[str, Any]],
    stats: dict[str, dict[str, Any]],
    baseline: str,
) -> ObservationRun:
    view = _baseline_view(grids)
    chosen = [_select(_with_baselines(obs, view), baseline) for obs in found]
    chosen.sort(key=_sort_key)
    return ObservationRun(chosen, stats, coverage, grids, baseline)


def observe(
    search: Search, index: str, start: float, end: float, baseline: str = "current"
) -> ObservationRun:
    """Exact entity-hour scores over full grids. A short or censored grid is incomplete."""
    _check_baseline(baseline)
    executor = executor_for(search)
    before = executor.stats()
    coverage: dict[str, dict[str, Any]] = {}
    found, grids = _observe_structural(executor, index, start, end, coverage)
    volume_slot = coverage.get("volume", {})
    volume_rows = grids.get("volume") if volume_slot.get("complete") else None
    values, value_grids, value_coverage = _observe_values(executor, index, start, end, volume_rows)
    grids.update(value_grids)
    coverage["value"] = value_coverage
    found.extend(values)
    return _finish(found, grids, coverage, executor.delta(before), baseline)


def rescore(
    grids: dict[str, list[dict[str, Any]]],
    coverage: dict[str, dict[str, Any]],
    index: str,
    baseline: str = "current",
    request_kinds: dict[str, dict[str, Any]] | None = None,
) -> ObservationRun:
    """Score saved grids. The baseline flag selects which side-by-side number is primary."""
    _check_baseline(baseline)
    found = _score_present(grids, index)
    return _finish(found, grids, coverage, request_kinds or {}, baseline)


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
    return ObservationRun(chosen, dict(request_kinds or {}), dict(coverage or {}), {}, baseline)


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
