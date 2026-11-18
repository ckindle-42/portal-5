"""Layer-1 observations: repeatable, exact, constant-cost, and honest about truncation."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections import defaultdict
from typing import Any

from portal.modules.security.core.hunt.engine import HOUR, _expm1, _log1p
from portal.modules.security.core.hunt.jobs import DEFAULT_BUDGETS
from portal.modules.security.core.hunt.observations import (
    KEY_BUDGET,
    KEY_SLICE_SAMPLE,
    KEY_SLICES,
    ObservationRun,
    budgeted_search,
    literal_matches,
    literal_query,
    observe,
)

START = 1_700_000_000 // HOUR * HOUR

END = START + 4 * HOUR

INDEX = "idx"

_PAIR = re.compile(r"""(?<![\w.])([A-Za-z_][\w.]{1,30})=([^\s"=]*)""")

_PREFIX = re.compile(r"PREFIX\(([A-Za-z_][\w.]*)=\)")


def _hour(stamp: float) -> int:
    return int(stamp) // HOUR * HOUR


def _event(
    hour: int,
    host: str,
    raw: str,
    *,
    source: str = "svc",
    sourcetype: str = "a",
    punct: str = ".",
    n: int = 1,
) -> list[dict[str, Any]]:
    return [
        {
            "_time": float(hour),
            "host": host,
            "source": source,
            "sourcetype": sourcetype,
            "punct": punct,
            "_raw": raw,
        }
        for _ in range(n)
    ]


def _universe() -> list[dict[str, Any]]:
    t0, t1, t2 = START, START + HOUR, START + 2 * HOUR
    rows: list[dict[str, Any]] = []
    rows += _event(t0, "h1", "uid=one", n=2)
    rows += _event(t1, "h1", "uid=one", n=2)
    rows += _event(t2, "h1", "uid=one", n=9)
    rows += _event(t2, "h1", "uid=two msg=a*b", punct="a*b")
    rows += _event(t2, "h1", "uid=one note=say", punct='say "hi" *')
    rows += _event(t2, "h1", "uid=one", source="other", sourcetype="b")
    rows += _event(t2, "h2", "uid=one", n=4)
    rows += _event(t2, "h2", "msg=axxb", punct="axxb")
    return rows


def _keyed(n_events: int, keys: list[str], tokens: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(n_events):
        hour = START + (i % 5) * HOUR
        raw = " ".join(f"{key}=v{i % 3}" for key in keys)
        raw = f"{raw} " + " ".join(f"tok{j}{i}" for j in range(tokens))
        rows += _event(hour, "h", raw.strip())
    return rows


class GridSearch:
    """Miniature tstats over an event list. Truncation drops grid rows, not the group count."""

    def __init__(
        self,
        events: list[dict[str, Any]],
        *,
        truncate: str = "",
        censored: str = "",
    ) -> None:
        self.events = events
        self.truncate = truncate
        self.censored = censored
        self.calls: list[str] = []

    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        self.calls.append(query)
        if self.censored and self.censored in query:
            from portal.modules.security.core.hunt.engine import SearchCoverageCensoredError

            raise SearchCoverageCensoredError(self.censored)
        rows = self._rows(query, start, end)
        if self.truncate and self.truncate in query and "stats count as groups" not in query:
            rows = rows[:-1]
        return rows

    def _window(self, start: float, end: float) -> list[dict[str, Any]]:
        return [row for row in self.events if start <= float(row["_time"]) < end]

    def _rows(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        window = self._window(start, end)
        if "md5(_raw)" in query:
            ordered = sorted(
                window,
                key=lambda row: (
                    hashlib.md5(str(row["_raw"]).encode()).hexdigest(),
                    float(row["_time"]),
                    str(row["_raw"]),
                ),
            )
            head = re.search(r"head (\d+)", query)
            limit = int(head.group(1)) if head else len(ordered)
            return [{"_raw": row["_raw"]} for row in ordered[:limit]]
        if "stats count as groups" in query:
            return [{"groups": len(self._groups(query, window))}]
        if " by " not in query:
            return [{"count": len(window)}]
        return self._groups(query, window)

    def _groups(self, query: str, window: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[tuple[Any, ...], int] = defaultdict(int)
        prefix = _PREFIX.search(query)
        for row in window:
            hour = _hour(float(row["_time"]))
            if prefix:
                key = prefix.group(1)
                values = []
                seen: set[str] = set()
                for found, value in _PAIR.findall(str(row["_raw"])):
                    if found == key and value not in seen:
                        seen.add(value)
                        values.append(value)
                for value in values:
                    counts[(row["host"], value, hour)] += 1
                continue
            stream = "sourcetype punct" in query
            if stream:
                counts[(row["host"], row["sourcetype"], row["punct"], hour)] += 1
            elif "source sourcetype" in query:
                counts[(row["host"], row["source"], row["sourcetype"], hour)] += 1
            elif " punct " in query:
                counts[(row["host"], row["punct"], hour)] += 1
            else:
                counts[(row["host"], hour)] += 1
        return _emit_groups(
            counts,
            prefix is not None,
            "sourcetype punct" in query,
            "source sourcetype" in query,
            " punct " in query and "sourcetype punct" not in query,
        )


def _emit_groups(
    counts: dict[tuple[Any, ...], int],
    prefix: bool,
    stream: bool,
    source: bool,
    shape: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(counts):
        count = counts[key]
        if prefix:
            host, value, hour = key
            rows.append({"host": host, "v": value, "_time": hour, "count": count})
        elif stream:
            host, sourcetype, punct, hour = key
            rows.append(
                {
                    "host": host,
                    "sourcetype": sourcetype,
                    "punct": punct,
                    "_time": hour,
                    "count": count,
                }
            )
        elif source:
            host, src, sourcetype, hour = key
            rows.append(
                {
                    "host": host,
                    "source": src,
                    "sourcetype": sourcetype,
                    "_time": hour,
                    "count": count,
                }
            )
        elif shape:
            host, punct, hour = key
            rows.append({"host": host, "punct": punct, "_time": hour, "count": count})
        else:
            host, hour = key
            rows.append({"host": host, "_time": hour, "count": count})
    return rows


def _ref_novelty(origin: int, hour: int) -> float:
    if hour <= origin:
        return 0.0
    return _log1p((hour - origin) / HOUR)


def _ref_burst(series: dict[int, int], hour: int) -> tuple[float, float, int]:
    prior = [series[stamp] for stamp in sorted(series) if stamp < hour and series[stamp]]
    logs = [_log1p(count) for count in prior]
    med = statistics.median(logs)
    mad = statistics.median(abs(point - med) for point in logs)
    now = series[hour]
    z = round((_log1p(now) - med) / (mad + 0.5), 2)
    return z, round(_expm1(med), 1), len(prior)


def _score_ref(
    kind: str,
    host: str,
    entity: str,
    series: dict[int, int],
    origin: int,
) -> list[tuple[Any, ...]]:
    hours = sorted(stamp for stamp, count in series.items() if count)
    first = hours[0]
    out: list[tuple[Any, ...]] = []
    for hour in hours:
        if hour == first:
            out.append(
                (
                    kind,
                    host,
                    entity,
                    hour,
                    "novelty",
                    _ref_novelty(origin, hour),
                    series[hour],
                    origin,
                    None,
                    None,
                )
            )
            continue
        z, median, active = _ref_burst(series, hour)
        out.append((kind, host, entity, hour, "burst", z, series[hour], origin, median, active))
    return out


def _pairs(raw: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in _PAIR.findall(raw):
        if key in seen:
            continue
        seen.add(key)
        found.append((key, value))
    return found


def _slice_hours(hours: list[int]) -> list[int]:
    unique = sorted(set(hours))
    if len(unique) <= KEY_SLICES:
        return unique
    if KEY_SLICES <= 1:
        return unique[:1]
    last = len(unique) - 1
    picked: list[int] = []
    for step in range(KEY_SLICES):
        hour = unique[round(step * last / (KEY_SLICES - 1))]
        if not picked or picked[-1] != hour:
            picked.append(hour)
    return picked


def _learned(window: list[dict[str, Any]]) -> list[str]:
    by_hour: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in window:
        by_hour[_hour(float(row["_time"]))].append(row)
    sample: list[dict[str, Any]] = []
    for hour in _slice_hours(list(by_hour)):
        ordered = sorted(
            by_hour[hour],
            key=lambda row: (
                hashlib.md5(str(row["_raw"]).encode()).hexdigest(),
                float(row["_time"]),
                str(row["_raw"]),
            ),
        )
        sample.extend(ordered[:KEY_SLICE_SAMPLE])
    counts: dict[str, int] = defaultdict(int)
    for row in sample:
        for key, _value in _pairs(str(row["_raw"])):
            counts[key] += 1
    ranked = sorted(counts, key=lambda key: (-counts[key], key))
    return ranked[:KEY_BUDGET]


def _value_reference(
    window: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    values: dict[str, dict[tuple[str, str], dict[int, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for row in window:
        hour = _hour(float(row["_time"]))
        for key, value in _pairs(str(row["_raw"])):
            values[key][(str(row["host"]), value)][hour] += 1
    expected: list[tuple[Any, ...]] = []
    for key in _learned(window):
        grouped = values[key]
        host_origin: dict[str, int] = {}
        earliest: dict[str, tuple[int, str, int]] = {}
        for (host, value), series in grouped.items():
            host_origin[host] = min(host_origin.get(host, min(series)), min(series))
            first = min(series)
            current = earliest.get(value)
            if current is None or (first, host) < (current[0], current[1]):
                earliest[value] = (first, host, series[first])
        for host, value in sorted(grouped):
            entity = f"{key}={value}"
            series = dict(grouped[(host, value)])
            expected.extend(_score_ref("value", host, entity, series, host_origin[host]))
            origin, _origin_host, _count = earliest[value]
            score = _ref_novelty(origin, min(series))
            if score == 0.0:
                continue
            expected.append(
                (
                    "value",
                    host,
                    entity,
                    min(series),
                    "new_host",
                    score,
                    series[min(series)],
                    origin,
                    None,
                    None,
                )
            )
    return expected


def _reference(events: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    window = [row for row in events if START <= float(row["_time"]) < END]
    expected: list[tuple[Any, ...]] = []
    volume: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    source: dict[tuple[str, str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    shape: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in window:
        hour = _hour(float(row["_time"]))
        volume[str(row["host"])][hour] += 1
        source[(str(row["host"]), str(row["source"]), str(row["sourcetype"]))][hour] += 1
        shape[(str(row["host"]), str(row["punct"]))][hour] += 1
    index_origin = min(min(series) for series in volume.values())
    for host in sorted(volume):
        expected.extend(_score_ref("volume", host, "", dict(volume[host]), index_origin))
    host_source: dict[str, int] = {}
    for (host, _src, _st), series in source.items():
        host_source[host] = min(host_source.get(host, min(series)), min(series))
    for host, src, sourcetype in sorted(source):
        entity = f"{src}\t{sourcetype}"
        expected.extend(
            _score_ref(
                "source", host, entity, dict(source[(host, src, sourcetype)]), host_source[host]
            )
        )
    host_shape: dict[str, int] = {}
    for (host, _punct), series in shape.items():
        host_shape[host] = min(host_shape.get(host, min(series)), min(series))
    for host, punct in sorted(shape):
        expected.extend(
            _score_ref("shape", host, punct, dict(shape[(host, punct)]), host_shape[host])
        )
    stream: dict[tuple[str, str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in window:
        hour = _hour(float(row["_time"]))
        stream[(str(row["host"]), str(row["sourcetype"]), str(row["punct"]))][hour] += 1
    host_stream: dict[str, int] = {}
    for (host, _sourcetype, _punct), series in stream.items():
        host_stream[host] = min(host_stream.get(host, min(series)), min(series))
    for host, sourcetype, punct in sorted(stream):
        entity = f"{sourcetype}\t{punct}"
        expected.extend(
            _score_ref(
                "stream",
                host,
                entity,
                dict(stream[(host, sourcetype, punct)]),
                host_stream[host],
            )
        )
    expected.extend(_value_reference(window))
    return expected


def _seen(run: ObservationRun) -> list[tuple[Any, ...]]:
    return [
        (
            obs.kind,
            obs.host,
            obs.entity,
            obs.hour,
            obs.evidence["signal"],
            obs.score,
            obs.evidence["now"],
            obs.evidence["origin_hour"],
            obs.evidence["prior_median"],
            obs.evidence["prior_hours_active"],
        )
        for obs in run.observations
    ]


def test_tied_scores_order_by_kind_host_entity_signal_hour() -> None:
    events = _event(START, "b", "uid=one", n=1) + _event(START + HOUR, "b", "uid=one", n=5)
    events += _event(START, "a", "uid=one", n=1) + _event(START + HOUR, "a", "uid=one", n=5)
    run = observe(GridSearch(events), INDEX, float(START), float(END))
    bursts = [
        obs
        for obs in run.observations
        if obs.kind == "volume" and obs.evidence["signal"] == "burst"
    ]

    assert len(bursts) == 2
    assert bursts[0].score == bursts[1].score
    assert [obs.host for obs in bursts] == ["a", "b"]
    ordered = sorted(
        run.observations,
        key=lambda obs: (
            -obs.score,
            obs.kind,
            obs.host,
            obs.entity,
            str(obs.evidence["signal"]),
            obs.hour,
        ),
    )
    assert run.observations == ordered


def test_scores_match_a_brute_force_pass_over_the_events() -> None:
    events = _universe()
    run = observe(GridSearch(events), INDEX, float(START), float(END))

    def _order(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
        return sorted(
            rows, key=lambda row: (-float(row[5]), row[0], row[1], row[2], row[4], row[3])
        )

    assert _seen(run) == _order(_reference(events))
    assert run.coverage_complete is True
    assert {obs.evidence["signal"] for obs in run.observations} >= {"novelty", "burst", "new_host"}


def test_truncated_grid_is_incomplete_and_not_a_zero() -> None:
    events = _universe()
    run = observe(GridSearch(events, truncate="by host _time"), INDEX, float(START), float(END))
    volume = [obs for obs in run.observations if obs.kind == "volume"]

    assert run.coverage["volume"]["complete"] is False
    assert run.coverage["volume"]["reasons"] == ["truncated"]
    assert volume == []
    assert all(obs.evidence["now"] != 0 for obs in run.observations)
    assert any(obs.kind == "source" for obs in run.observations)
    assert run.coverage["source"]["complete"] is True


def test_censored_grid_is_incomplete_and_drops_the_kind() -> None:
    events = _universe()
    run = observe(GridSearch(events, censored=" punct "), INDEX, float(START), float(END))

    assert run.coverage["shape"]["reasons"] == ["censored"]
    assert [obs for obs in run.observations if obs.kind == "shape"] == []
    assert any(obs.kind == "volume" for obs in run.observations)


def test_learned_values_drop_starred_search_terms_but_keep_shapes() -> None:
    events = _universe()
    run = observe(GridSearch(events), INDEX, float(START), float(END))
    star = next(obs for obs in run.observations if obs.kind == "shape" and obs.entity == "a*b")
    quoted = next(obs for obs in run.observations if obs.entity == 'say "hi" *')
    value = next(obs for obs in run.observations if obs.entity == "msg=a*b")
    wild = next(row for row in events if row["punct"] == "axxb")
    star_row = next(row for row in events if row["punct"] == "a*b")
    quote_row = next(row for row in events if row["punct"] == 'say "hi" *')

    assert 'where punct="a*b"' in star.evidence["literal"]
    assert 'where punct="say \\"hi\\" *"' in quoted.evidence["literal"]
    assert value.evidence["literal"] == ""
    assert literal_matches(star_row, star.evidence["literal"])
    assert not literal_matches(wild, star.evidence["literal"])
    assert literal_matches(quote_row, quoted.evidence["literal"])
    assert not literal_matches(star_row, quoted.evidence["literal"])
    assert not literal_matches(star_row, value.evidence["literal"])
    assert not literal_matches(wild, value.evidence["literal"])
    assert not literal_matches({**wild, "host": "h1"}, value.evidence["literal"])


def test_value_query_drops_wildcard_with_no_long_literal_segment() -> None:
    assert literal_query("value", INDEX, "node-a", "***") == ""


def test_budgeted_search_keeps_the_shared_hunt_limits() -> None:
    class _Raw:
        def iter_post_bounded(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return []

    wrapped = budgeted_search(_Raw())

    assert wrapped.budget.limits == DEFAULT_BUDGETS
    assert wrapped.budget.phase == "ranking"


def test_single_host_observation_bytes_use_plain_search_terms() -> None:
    run = observe(GridSearch(_event(START, "solo", "uid=first")), INDEX, float(START), float(END))
    payload = json.dumps(
        [item.as_dict() for item in run.observations], sort_keys=True, separators=(",", ":")
    )

    assert hashlib.sha256(payload.encode()).hexdigest() == (
        "06cd550829c2cb2e04e370a96dad0d3ce0c4c691b91645d7b9bae5e82f4ecb2b"
    )


def test_literal_queries_match_each_spelling_in_an_alias_group() -> None:
    query = literal_query(
        "shape", INDEX, "NODE_core", "abc", host_aliases=("NODE_core", "node-core")
    )
    first = {"host": "NODE_core", "punct": "abc"}
    second = {"host": "node-core", "punct": "abc"}
    other = {"host": "node_core", "punct": "abc"}

    assert '(host="NODE_core" OR host="node-core")' in query
    assert literal_matches(first, query)
    assert literal_matches(second, query)
    assert not literal_matches(other, query)


def test_small_grid_observation_bytes_use_plain_search_terms() -> None:
    run = observe(GridSearch(_universe()), INDEX, float(START), float(END))
    encoded = "\n".join(json.dumps(row.as_dict(), sort_keys=True) for row in run.observations)

    assert len(run.observations) == 33
    assert hashlib.sha256(encoded.encode()).hexdigest() == (
        "45568d0383f8108b0dccba234dd288998ff1d4095ddd9bb740274a649f05e303"
    )
