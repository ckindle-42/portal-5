"""One tstats grid per observation kind, scored with hunt novelty and burst statistics."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from portal.modules.security.core.hunt.engine import (
    HOUR,
    Search,
    SearchBudgetExceededError,
    SearchCoverageCensoredError,
    _burst,
    _search_literal,
    host_hour_novelty,
)
from portal.modules.security.core.hunt.jobs import DEFAULT_BUDGETS, BudgetedSearch, HuntBudget
from portal.modules.security.core.hunt.ranking import where_literal

KEY_SAMPLE = 3000  # effort budget: md5-ordered events read while learning keys
KEY_BUDGET = 8  # effort budget: PREFIX grids; keys beyond this stay uncovered
_KEY = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=(?=[^\s"=])""")
_PAIR = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=([^\s"=]*)""")
_QUOTED = r'"((?:\\.|[^"])*)"'
_HOST_CONSTRAINT = re.compile(rf"host={_QUOTED}")
_WHERE_CONSTRAINT = re.compile(rf"where\s+([A-Za-z_][\w.]*)={_QUOTED}")


@dataclass(frozen=True)
class Observation:
    kind: str
    host: str
    entity: str
    hour: int
    score: float
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
    key, _, value = entity.partition("=")
    return f"search index={index_lit} host={host_lit} | where {key}={where_literal(value)}"


def _unescape(inner: str) -> str:
    return re.sub(r"\\(.)", r"\1", inner)


def literal_matches(event: Mapping[str, Any], query: str) -> bool:
    """Exact field match for a literal_query. A `*` in the value matches only a star."""
    constraints: list[tuple[str, str]] = []
    host = _HOST_CONSTRAINT.search(query)
    if host:
        constraints.append(("host", _unescape(host.group(1))))
    constraints.extend(
        (match.group(1), _unescape(match.group(2))) for match in _WHERE_CONSTRAINT.finditer(query)
    )
    if not constraints:
        return False
    fields: dict[str, str] = {
        "host": str(event.get("host", "")),
        "source": str(event.get("source", "")),
        "sourcetype": str(event.get("sourcetype", "")),
        "punct": str(event.get("punct", "")),
    }
    fields.update(learned_pairs(str(event.get("_raw", ""))))
    return all(fields.get(name) == value for name, value in constraints)


def _sort_key(obs: Observation) -> tuple[float, str, str, str, str, int]:
    # Total order: higher score, then kind, host, entity, signal, hour.
    signal = str(obs.evidence.get("signal", ""))
    return (-obs.score, obs.kind, obs.host, obs.entity, signal, obs.hour)


def _note(stats: dict[str, dict[str, Any]], kind: str, started: float) -> None:
    slot = stats.setdefault(kind, {"requests": 0, "seconds": 0.0})
    slot["requests"] = int(slot["requests"]) + 1
    slot["seconds"] = round(float(slot["seconds"]) + time.monotonic() - started, 3)


def _issue(
    search: Search,
    query: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
    kind: str,
) -> tuple[list[dict[str, Any]], str | None]:
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    reason: str | None = None
    try:
        for row in search.iter_post(query, start, end):
            rows.append(dict(row))
    except SearchCoverageCensoredError:
        rows, reason = [], "censored"
    except SearchBudgetExceededError:
        rows, reason = [], "budget"
    finally:
        _note(stats, kind, started)
    return rows, reason


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


def _load_grid(
    search: Search,
    index: str,
    by: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
    kind: str,
    suffix: str = "",
) -> tuple[list[dict[str, Any]], str | None]:
    counted, reason = _issue(
        search, f"{_tstats(index, by)} | stats count as groups", start, end, stats, kind
    )
    if reason:
        return [], reason
    expected = _as_int(counted, "groups")
    if expected is None:
        return [], "censored"
    fetched, reason = _issue(search, f"{_tstats(index, by)}{suffix}", start, end, stats, kind)
    if reason:
        return [], reason
    if len(fetched) != expected:
        return [], "truncated"
    return fetched, None


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


def _host_first(grouped: dict[str, dict[int, int]]) -> dict[str, int]:
    return {host: min(hours) for host, hours in grouped.items() if hours}


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


def _from_volume(rows: list[dict[str, Any]], index: str) -> tuple[list[Observation], str | None]:
    grouped = _volume_series(rows)
    if not grouped:
        return [], None
    origin = min(_host_first(grouped).values())
    found: list[Observation] = []
    for host in sorted(grouped):
        scored, reason = _score_series("volume", host, "", grouped[host], origin, index)
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
    origins = _host_first(host_hours)
    found: list[Observation] = []
    for host, left_value, right_value in sorted(grouped):
        entity = right_value if kind == "shape" else f"{left_value}\t{right_value}"
        scored, reason = _score_series(
            kind, host, entity, grouped[(host, left_value, right_value)], origins[host], index
        )
        if reason:
            return [], reason
        found.extend(scored)
    return found, None


def _sample_query(index: str) -> str:
    literal = _search_literal(index)
    return (
        f"search index={literal} | eval _k=md5(_raw) | sort {KEY_SAMPLE} _k _time _raw "
        f"| head {KEY_SAMPLE} | table _raw"
    )


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


def _from_values(
    key: str, rows: list[dict[str, Any]], index: str
) -> tuple[list[Observation], str | None]:
    grouped = _value_series(rows, key)
    host_hours: dict[str, dict[int, int]] = {}
    for (host, _value), series in grouped.items():
        for hour, count in series.items():
            _add_hour(host_hours, host, hour, count)
    origins = _host_first(host_hours)
    found: list[Observation] = []
    for host, value in sorted(grouped):
        scored, reason = _score_series(
            "value",
            host,
            f"{key}={value}",
            grouped[(host, value)],
            origins[host],
            index,
        )
        if reason:
            return [], reason
        found.extend(scored)
    found.extend(_new_host_records(key, grouped, index))
    return found, None


def _score_loaded(
    kind: str, rows: list[dict[str, Any]], index: str
) -> tuple[list[Observation], str | None]:
    if kind == "volume":
        return _from_volume(rows, index)
    if kind == "source":
        return _from_pairs("source", rows, index, "source", "sourcetype")
    return _from_pairs("shape", rows, index, "punct", "punct")


def _observe_one(
    search: Search,
    index: str,
    kind: str,
    by: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
    coverage: dict[str, dict[str, Any]],
) -> list[Observation]:
    rows, reason = _load_grid(search, index, by, start, end, stats, kind)
    if reason:
        coverage[kind] = _coverage(reason)
        return []
    try:
        scored, score_reason = _score_loaded(kind, rows, index)
    except (KeyError, TypeError, ValueError):
        coverage[kind] = _coverage("censored")
        return []
    coverage[kind] = _coverage(score_reason)
    return scored if score_reason is None else []


def _observe_structural(
    search: Search,
    index: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
    coverage: dict[str, dict[str, Any]],
) -> list[Observation]:
    found: list[Observation] = []
    for kind, by in (
        ("volume", "by host _time span=1h"),
        ("source", "by host source sourcetype _time span=1h"),
        ("shape", "by host punct _time span=1h"),
    ):
        found.extend(_observe_one(search, index, kind, by, start, end, stats, coverage))
    return found


def _event_total(
    search: Search,
    index: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
) -> tuple[int | None, str | None]:
    rows, reason = _issue(search, _tstats(index, "").rstrip(), start, end, stats, "event_total")
    if reason:
        return None, reason
    return _as_int(rows, "count"), None if _as_int(rows, "count") is not None else "censored"


def _observe_values(
    search: Search,
    index: str,
    start: float,
    end: float,
    stats: dict[str, dict[str, Any]],
) -> tuple[list[Observation], dict[str, Any]]:
    total, total_reason = _event_total(search, index, start, end, stats)
    sample, sample_reason = _issue(search, _sample_query(index), start, end, stats, "key_sample")
    reasons: list[str] = []
    if total_reason or sample_reason:
        reasons.append(total_reason or sample_reason or "censored")
    if total is None and "censored" not in reasons and "budget" not in reasons:
        reasons.append("censored")
    if sample_reason is None and total is not None and total > len(sample):
        reasons.append("sample_budget")
    if sample_reason is not None:
        coverage = {"complete": False, "reasons": reasons, "unqueried_keys": []}
        return [], coverage
    ranked = _learned_keys(sample)
    queried = ranked[:KEY_BUDGET]
    skipped = [key for key, _count in ranked[KEY_BUDGET:]]
    if skipped:
        reasons.append("key_budget")
    found: list[Observation] = []
    for key, _count in queried:
        by = f"by host PREFIX({key}=) _time span=1h"
        rows, reason = _load_grid(
            search,
            index,
            by,
            start,
            end,
            stats,
            f"value:{key}",
            suffix=f' | rename "{key}=" as v',
        )
        if reason:
            reasons.append(reason)
            continue
        try:
            scored, score_reason = _from_values(key, rows, index)
        except (KeyError, TypeError, ValueError):
            reasons.append("censored")
            continue
        if score_reason:
            reasons.append(score_reason)
            continue
        found.extend(scored)
    coverage = {"complete": not reasons, "reasons": reasons, "unqueried_keys": skipped}
    return found, coverage


def observe(search: Search, index: str, start: float, end: float) -> ObservationRun:
    """Exact entity-hour scores over full grids. A short or censored grid is incomplete."""
    stats: dict[str, dict[str, Any]] = {}
    coverage: dict[str, dict[str, Any]] = {}
    found = _observe_structural(search, index, start, end, stats, coverage)
    values, value_coverage = _observe_values(search, index, start, end, stats)
    coverage["value"] = value_coverage
    found.extend(values)
    found.sort(key=_sort_key)
    return ObservationRun(found, stats, coverage)
