"""Hunt engine v1 -- surface host-hours where several weak, generic signals come together.

Nothing here names a technique, an event code, a field, a sourcetype or a format. Every signal
is a statistic of the environment against its own prior history, computed in Splunk where
possible (the search tier does the volume; this process does the reasoning):

1. Template novelty. Splunk's indexed ``punct`` (the event's punctuation skeleton) is a
   format-agnostic template. A template never seen before on a host/source is novel; its weight
   grows with how long a prior history said it was absent (no history -> no surprise).
2. Concentration. Novelty seen on every host at once is an environment event (boot, sensor
   start), not an intrusion; a bucket's novelty is divided by the most hosts any zoom level
   saw novel around it.
3. Value burst. Tokens from the host-hour's events are scored by how far this hour's count
   sits above that value's own prior hours and above the values holding the same slot in the
   same shape of event on that host (robust z on log counts, then peer-relative).
4. Linkage. A bursting value is pivoted across the whole environment: how many other hosts and
   sources it touches in the same span -- the "this and that came together" step.

A lead is one host-hour with its evidence: the novel templates, the bursting values and the
places they link to. Labels are never read here; scoring is a separate scorer-plane script.
"""

from __future__ import annotations

import calendar
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .ranking import (
    census_query,
    note_ranking,
    peer_history_query,
    rollup_series,
    slot_query,
    z_upper,
)

HOUR = 3600
_TOKEN = re.compile(r"[A-Za-z0-9_.:/@%\-]{4,}")
# A value has at least one letter or digit; a run of punctuation ("........") is formatting.
# Found live on BOTS v1: such a pivot became a full-index plain search (>20 min).
_HAS_VALUE = re.compile(r"[A-Za-z0-9]")
_TIME_OF_DAY = re.compile(r"\d{1,2}:\d{2}:\d{2}")
_TERM_UNSAFE = re.compile(r"[\"\\=\[\]()|,;]")
PEERS = 12  # effort budget: distinct peer values compared for one burst
PEER_SAMPLE = 200  # effort budget: events read to locate a value's slot and its peers
PEER_SHAPES = 4  # effort budget: event shapes read per burst when looking for peers


class Search(Protocol):
    def iter_post(self, search: str, start: float, end: float) -> Iterable[Mapping[str, Any]]: ...


class SearchBudgetExceededError(RuntimeError):
    """A shared hunt effort budget ran out inside one search call."""


class SearchCoverageCensoredError(RuntimeError):
    """A search stopped early; its rows are not an exact count."""


@dataclass
class Burst:
    token: str
    this_hour: int
    prior_median: float
    prior_hours_active: int
    z: float
    peer_z: float = 0.0
    peers: int = 0
    peer_median_z: float = 0.0
    links: list[tuple[str, str, int]] = field(default_factory=list)


@dataclass
class Lead:
    hour: int
    host: str
    novelty: float
    hosts_novel_that_hour: int
    novel_templates: list[tuple[str, str, int]]
    bursts: list[Burst] = field(default_factory=list)
    score: float = 0.0
    span: int = HOUR  # the zoom level this lead was seen at; `hour` is the bucket start

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["hour_utc"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(self.hour))
        return out


# Zoom ladder: the clock resolutions an analyst flips between. A level is used only when the
# data spans enough of it to have history; it is a set of views, not a tuned threshold.
LADDER = (60, 600, HOUR, 86400)


def _hour(value: Any, span: int = HOUR) -> int:
    return int(float(value)) // span * span


def ladder(search: Search, index: str, start: float, end: float) -> list[int]:
    rows = list(
        search.iter_post(
            f"| tstats min(_time) as lo max(_time) as hi where index={_search_literal(index)}",
            start,
            end,
        )
    )
    if not rows or rows[0].get("lo") is None:
        return [HOUR]
    data_span = float(rows[0]["hi"]) - float(rows[0]["lo"])
    return [s for s in LADDER if data_span >= 2 * s] or [LADDER[0]]


TEMPLATE_HOST_GROUP = 64  # effort budget: indexed hosts per novelty partition job
TEMPLATE_PARTITION_PARALLEL = 8  # effort budget: concurrent novelty partition jobs


def indexed_hosts(search: Search, index: str, start: float, end: float) -> list[str]:
    """The indexed host inventory, learned from the environment's own metadata."""
    q = f"| tstats count where index={_search_literal(index)} by host"
    return sorted({str(r["host"]) for r in search.iter_post(q, start, end)})


def _template_query(index: str, span: int, hosts: list[str]) -> str:
    clause = ""
    if hosts:
        clause = "(" + " OR ".join(f"host={_search_literal(h)}" for h in hosts) + ") "
    return (
        f"| tstats count where index={_search_literal(index)} {clause}"
        f"by host source punct _time span={span}s "
        "| dedup host source punct sortby +_time"
    )


def template_rows(
    search: Search,
    index: str,
    start: float,
    end: float,
    span: int = HOUR,
    hosts: list[str] | None = None,
) -> list[dict[str, Any]]:
    # First occurrence per (host, source, template), reduced on the server: novelty weighs a
    # template only at its first bucket, so later rows cannot change the score (found live:
    # the unreduced by-hour grid streamed 1.84M rows for one index). High-cardinality indexes
    # are partitioned by discovered host inventory, each host wholly in one group, so the
    # first-occurrence rows and counts stay exactly equivalent at every zoom span.
    if hosts is None:
        hosts = indexed_hosts(search, index, start, end)
    if not hosts or len(hosts) <= TEMPLATE_HOST_GROUP:
        query = _template_query(index, span, hosts)
        return [dict(r) for r in search.iter_post(query, start, end)]
    groups = [hosts[i : i + TEMPLATE_HOST_GROUP] for i in range(0, len(hosts), TEMPLATE_HOST_GROUP)]
    with ThreadPoolExecutor(max_workers=min(TEMPLATE_PARTITION_PARALLEL, len(groups))) as pool:
        pages = list(
            pool.map(
                lambda group: list(
                    search.iter_post(_template_query(index, span, group), start, end)
                ),
                groups,
            )
        )
    return [dict(r) for page in pages for r in page]


def host_hour_novelty(
    rows: list[dict[str, Any]], span: int = HOUR
) -> dict[tuple[int, str], tuple[float, list[tuple[str, str, int]]]]:
    """Prior-only template novelty per host-bucket, weighted by prior history in hours."""
    by_stream: dict[tuple[str, str], dict[int, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in rows:
        by_stream[(r["host"], r["source"])][_hour(r["_time"], span)].append(
            (r.get("punct", ""), int(r["count"]))
        )
    out: dict[tuple[int, str], tuple[float, list[tuple[str, str, int]]]] = {}
    for (host, source), hours in by_stream.items():
        seen: set[str] = set()
        first = min(hours)
        for hour in sorted(hours):
            # punct order is the total order for a tied template list (items[:20] is a prefix)
            novel = sorted(
                ((p, c) for p, c in hours[hour] if p not in seen),
                key=lambda item: (item[0], item[1]),
            )
            seen.update(p for p, _ in hours[hour])
            prior_hours = (hour - first) / HOUR
            if not novel or prior_hours <= 0:
                continue
            weight = math.log1p(prior_hours) * len(novel)
            score, items = out.get((hour, host), (0.0, []))
            items = items + [(source, p, c) for p, c in novel]
            out[(hour, host)] = (score + weight, items)
    return out


def _is_time_token(token: str) -> bool:
    if _TIME_OF_DAY.search(token):
        return True
    try:
        datetime.fromisoformat(token.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _pivotable(token: str) -> bool:
    return (
        bool(_HAS_VALUE.search(token))
        and not _is_time_token(token)
        and not _TERM_UNSAFE.search(token)
    )


def _token_series(
    search: Search, index: str, token: str, start: float, end: float, span: int = HOUR
) -> dict[int, int]:
    q = (
        f"| tstats count where index={_search_literal(index)} "
        f"TERM({_search_literal(token)}) by _time span={span}s"
    )
    return {_hour(r["_time"], span): int(r["count"]) for r in search.iter_post(q, start, end)}


SERIES_BATCH = 8  # effort budget: token series packed into one parent search job
HOUR_BATCH = 32  # effort budget: narrow hour-count terms per parent; each child is one bucket
# Append children run serially inside a parent, so peak active jobs is one parent plus
# its one running child: 2 * PACK_PARENTS, inside the lab search concurrency allowance.
PACK_PARENTS = 8
LAB_SEARCH_CONCURRENCY = 20  # effort budget: lab Splunk search concurrency allowance


def _packed_series_query(index: str, tokens: list[str], span: int, subsearch_seconds: int) -> str:
    """One parent job carrying every token's series as a single packed row (term id, declared
    cell count, serialized cells), joined by append subsearches. maxtime stays longer than the
    enclosing job's allowance so a subsearch cannot finalize partial first; maxout is explicit."""
    parts = []
    for i, token in enumerate(tokens):
        parts.append(
            f"| tstats count where index={_search_literal(index)} "
            f"TERM({_search_literal(token)}) by _time span={span}s "
            '| eval _hc=printf("%d:%d",_time,count) '
            "| stats count as _hn values(_hc) as _hv "
            '| eval _hs=mvjoin(_hv,",") '
            f'| eval _ht="{i}" '
            "| fields _ht _hn _hs"
        )
    query = parts[0]
    for part in parts[1:]:
        query += f" | append maxtime={subsearch_seconds} maxout=2 [ {part} ]"
    return query


def _unpack_packed_row(row: Mapping[str, Any]) -> tuple[int, dict[int, int]] | None:
    """Decode one packed row exactly: the raw serialized cell list must match the declared
    count with no duplicate buckets and no negative counts -- never coerced to exact."""
    try:
        term = int(str(row.get("_ht", "")))
        declared = int(str(row.get("_hn", "")))
    except (TypeError, ValueError):
        return None
    raw_cells = str(row.get("_hs") or "").split(",") if row.get("_hs") else []
    parsed: dict[int, int] = {}
    for cell in raw_cells:
        try:
            bucket_s, count_s = cell.split(":")
            bucket, count = int(bucket_s), int(count_s)
        except ValueError:
            return None
        if count < 0 or bucket in parsed:
            return None
        parsed[bucket] = count
    if len(raw_cells) != len(parsed) or declared != len(parsed):
        return None
    return term, parsed


def _packed_series(
    search: Search, index: str, tokens: list[str], start: float, end: float, span: int
) -> dict[str, dict[int, int]] | None:
    """Run one packed batch job and unpack the exact series, or None when the job cannot be
    trusted as exact (missing/duplicated/malformed term records, declared cell count mismatch,
    truncated serialized cells, subsearch warnings). None never poisons the cache."""
    allowance = getattr(search, "query_allowance_seconds", None)
    maxtime = int(allowance) + 60 if allowance else 90
    try:
        rows = list(
            search.iter_post(_packed_series_query(index, tokens, span, maxtime), start, end)
        )
    except SearchBudgetExceededError:
        raise  # a spent budget must not fall through into more per-token scans
    except Exception:  # noqa: BLE001 -- a failed pack falls back to exact per-token scans
        return None
    series: dict[int, dict[int, int]] = {}
    for row in rows:
        unpacked = _unpack_packed_row(row)
        if unpacked is None:
            return None
        term, parsed = unpacked
        if term not in range(len(tokens)) or term in series:
            return None
        series[term] = parsed
    if len(series) != len(tokens):
        return None
    return {tokens[term]: cells for term, cells in series.items()}


def _remember_rollup(
    cache: dict[tuple[str, int], dict[int, int]], token: str, span: int
) -> dict[int, int] | None:
    """Reuse a finer full-window series. Narrow hour screens never enter ``cache``."""
    finer = [
        (fine, series)
        for (tok, fine), series in cache.items()
        if tok == token and 0 < fine < span and span % fine == 0
    ]
    if not finer:
        return None
    fine, series = min(finer)
    rolled = rollup_series(series, span)
    cache[(token, span)] = rolled
    return rolled


def _fill_series_cache(
    cache: dict[tuple[str, int], dict[int, int]],
    search: Search,
    index: str,
    tokens: list[str],
    start: float,
    end: float,
    span: int,
    *,
    batch: int = SERIES_BATCH,
) -> None:
    """Fill the run's series cache for pending tokens with bounded parallel parent packs
    (live-measured: 8 parents finish 32 tokens in 3.5s vs 6.5s at 2, peak 16 active
    parent+child jobs inside the lab's 20), then exact per-token scans for whatever a pack
    could not return exactly."""
    pending: list[str] = []
    for token in dict.fromkeys(tokens):
        if (token, span) in cache:
            continue
        if _remember_rollup(cache, token, span) is None:
            pending.append(token)
    while pending:
        wave, pending = pending[: batch * PACK_PARENTS], pending[batch * PACK_PARENTS :]
        batches = [wave[i : i + batch] for i in range(0, len(wave), batch)]
        if len(batches) == 1:
            packed = [(batches[0], _packed_series(search, index, batches[0], start, end, span))]
        else:
            with ThreadPoolExecutor(max_workers=min(PACK_PARENTS, len(batches))) as pool:
                packed = list(
                    pool.map(
                        lambda group: (
                            group,
                            _packed_series(search, index, group, start, end, span),
                        ),
                        batches,
                    )
                )
        for group, got in packed:
            if got is not None:
                cache.update({(token, span): cells for token, cells in got.items()})
                continue
            for token in group:  # exact per-token fallback: never cache a partial pack
                if (token, span) not in cache:
                    cache[(token, span)] = _token_series(search, index, token, start, end, span)


def _burst(token: str, hour: int, series: dict[int, int]) -> Burst | None:
    prior = [series.get(h, 0) for h in sorted(k for k in series if k < hour)]
    active = sum(1 for v in prior if v)
    if not active:
        return None
    now = series.get(hour, 0)
    # Compare against the hours this value is normally active, not against idle hours: a user
    # who works days is not "bursting" every morning against a median of nights.
    logs = [math.log1p(v) for v in prior if v]
    med = statistics.median(logs)
    mad = statistics.median(abs(x - med) for x in logs)
    z = (math.log1p(now) - med) / (mad + 0.5)
    return Burst(token, now, round(math.expm1(med), 1), active, round(z, 2))


def _burst_sort(bursts: list[Burst]) -> list[Burst]:
    """Total order: higher z first, then the token. Ties are not left to row order."""
    return sorted(bursts, key=lambda burst: (-burst.z, burst.token))


def _census_tokens(events: Iterable[Mapping[str, Any]]) -> Counter[str]:
    return Counter(
        token
        for event in events
        for token in set(_TOKEN.findall(str(event.get("_raw", ""))))
        if _pivotable(token)
    )


def _known_hour(
    cache: dict[tuple[str, int], dict[int, int]], token: str, bucket: int, span: int
) -> int | None:
    series = cache.get((token, span))
    if series is None:
        series = _remember_rollup(cache, token, span)
    if series is None:
        return None
    return int(series.get(bucket, 0))


def _screen_hours(
    search: Search,
    index: str,
    tokens: list[str],
    bucket: int,
    span: int,
    cache: dict[tuple[str, int], dict[int, int]],
    hours: dict[tuple[str, int, int], int],
) -> None:
    """Exact lead-bucket counts. A narrow tstats is not stored as a full-window series."""
    missing: list[str] = []
    for token in dict.fromkeys(tokens):
        key = (token, bucket, span)
        if key in hours:
            continue
        known = _known_hour(cache, token, bucket, span)
        if known is None:
            missing.append(token)
        else:
            hours[key] = known
    if not missing:
        return

    # Narrow one-bucket screens use standalone per-token scans: live-measured
    # ~0.37 s each versus ~15.2 s for a packed window parent. We do not feed
    # ``cache`` (full-window series are emitted later by ``_select_bursts``).
    def _safe_screen(token: str) -> tuple[str, dict[int, int]] | None:
        try:
            return (
                token,
                _token_series(search, index, token, float(bucket), float(bucket + span), span),
            )
        except SearchBudgetExceededError:
            return None

    with ThreadPoolExecutor(max_workers=min(LAB_SEARCH_CONCURRENCY, len(missing))) as pool:
        results = [r for r in pool.map(_safe_screen, missing) if r is not None]
    for token, series in results:
        hours[(token, bucket, span)] = int(series.get(bucket, 0))


def _select_bursts(
    search: Search,
    index: str,
    lead: Lead,
    tokens: list[str],
    start: float,
    end: float,
    cache: dict[tuple[str, int], dict[int, int]],
    hours: dict[tuple[str, int, int], int],
    keep: int,
) -> list[Burst]:
    """History series only for an hour-count group that can still enter the kept bursts."""
    bucket, span = lead.hour, lead.span
    pending = sorted(tokens, key=lambda token: (-hours.get((token, bucket, span), 0), token))
    found: list[Burst] = []
    while pending:
        now = hours.get((pending[0], bucket, span), 0)
        upper = z_upper(now)
        if len(found) >= keep and upper < _burst_sort(found)[keep - 1].z - 0.01:
            break
        group = [token for token in pending if hours.get((token, bucket, span), 0) == now]
        pending = pending[len(group) :]
        _fill_series_cache(cache, search, index, group, start, end, span)
        for token in group:
            burst = _burst(token, bucket, cache[(token, span)])
            if burst is not None:
                found.append(burst)
    return _burst_sort(found)[:keep]


def value_bursts(
    search: Search,
    index: str,
    lead: Lead,
    start: float,
    end: float,
    *,
    sample: int,
    top: int,
    cache: dict[tuple[str, int], dict[int, int]] | None = None,
    keep: int | None = None,
    hour_cache: dict[tuple[str, int, int], int] | None = None,
    census_cache: dict[tuple[int, str, int], list[Mapping[str, Any]]] | None = None,
) -> list[Burst]:
    events = list(
        search.iter_post(
            census_query(_search_literal(index), _search_literal(lead.host), sample),
            lead.hour,
            lead.hour + lead.span,
        )
    )
    if len(events) >= sample:
        note_ranking(search, "census_budget_exhausted")
    if census_cache is not None:
        census_cache[(lead.hour, lead.host, lead.span)] = events
    counts = _census_tokens(events)
    if cache is None:
        cache = {}
    if keep is None:
        # ``top`` is the legacy caller budget. Hunt passes ``keep`` and does not cut here.
        chosen = [
            token for token, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ][:top]
        _fill_series_cache(cache, search, index, chosen, start, end, lead.span)
        bursts = [
            burst
            for token in chosen
            if (burst := _burst(token, lead.hour, cache[(token, lead.span)]))
        ]
        return _burst_sort(bursts)
    hours = hour_cache if hour_cache is not None else {}
    _screen_hours(search, index, list(counts), lead.hour, lead.span, cache, hours)
    return _select_bursts(search, index, lead, list(counts), start, end, cache, hours, keep)


def _search_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _slots(rows: Iterable[Mapping[str, Any]], token: str) -> dict[str, int]:
    """Each event shape's slot for the token: its position among that shape's tokens."""
    out: dict[str, int] = {}
    for row in rows:
        punct = str(row.get("punct", ""))
        if punct not in out:
            found = _TOKEN.findall(str(row.get("_raw", "")))
            if token in found:
                out[punct] = found.index(token)
    return out


def peer_tokens(
    search: Search,
    index: str,
    lead: Lead,
    burst: Burst,
    start: float,
    *,
    sample: int = PEER_SAMPLE,
    rows: Iterable[Mapping[str, Any]] | None = None,
    history_cache: dict[tuple[Any, ...], list[Mapping[str, Any]]] | None = None,
) -> list[str]:
    """Values in the burst token's slot of the same event shape on the lead's host, from history.

    Shape order is the punct string. History rows are md5(_raw) order. ``where punct=`` is
    exact; a row whose punct field disagrees is dropped, never counted.
    """
    if rows is None:
        rows = search.iter_post(
            slot_query(
                _search_literal(index),
                _search_literal(lead.host),
                _search_literal(burst.token),
                sample,
            ),
            lead.hour,
            lead.hour + lead.span,
        )
    shapes = _slots(rows, burst.token)
    peers: list[str] = []
    seen: set[str] = set()
    index_literal, host_literal = _search_literal(index), _search_literal(lead.host)
    for punct, slot in sorted(shapes.items())[:PEER_SHAPES]:
        key = (index, lead.host, punct, float(start), lead.hour, sample)
        history = None if history_cache is None else history_cache.get(key)
        if history is None:
            history = list(
                search.iter_post(
                    peer_history_query(index_literal, host_literal, punct, sample),
                    start,
                    lead.hour,
                )
            )
            if history_cache is not None:
                history_cache[key] = history
        for row in history:
            if "punct" in row and str(row.get("punct")) != punct:
                continue
            tokens = _TOKEN.findall(str(row.get("_raw", "")))
            candidate = tokens[slot] if slot < len(tokens) else ""
            if (
                candidate
                and candidate != burst.token
                and _pivotable(candidate)
                and candidate not in seen
            ):
                seen.add(candidate)
                peers.append(candidate)
            if len(peers) >= PEERS:
                note_ranking(search, "peer_budget_exhausted")
                return peers
    return peers


def peer_bursts(
    search: Search,
    index: str,
    lead: Lead,
    start: float,
    end: float,
    cache: dict[tuple[str, int], dict[int, int]] | None = None,
    census_cache: dict[tuple[int, str, int], list[Mapping[str, Any]]] | None = None,
    history_cache: dict[tuple[Any, ...], list[Mapping[str, Any]]] | None = None,
) -> None:
    """Rank each kept burst against the same-slot values instead of only its own history."""
    census = None if census_cache is None else census_cache.get((lead.hour, lead.host, lead.span))
    found = [
        peer_tokens(search, index, lead, burst, start, rows=census, history_cache=history_cache)
        for burst in lead.bursts
    ]
    flat = [token for peers in found for token in peers]

    if cache is None:
        cache = {}
    _fill_series_cache(cache, search, index, flat, start, end, lead.span)
    values = [cache[(t, lead.span)] for t in flat]
    offset = 0
    for burst, peers in zip(lead.bursts, found, strict=True):
        rows = values[offset : offset + len(peers)]
        offset += len(peers)
        if len(peers) < 2:
            burst.peer_z = burst.z
            continue
        zs = [
            pb.z if (pb := _burst(t, lead.hour, s)) else 0.0
            for t, s in zip(peers, rows, strict=True)
        ]
        burst.peers = len(peers)
        burst.peer_median_z = round(statistics.median(zs), 2)
        # Peers bursting together discount the burst; quiet peers leave it as it is.
        burst.peer_z = round(burst.z - max(0.0, burst.peer_median_z), 2)


def link(
    search: Search, index: str, burst: Burst, hour: int, span: int = HOUR
) -> list[tuple[str, str, int]]:
    q = (
        f"| tstats count where index={_search_literal(index)} "
        f"TERM({_search_literal(burst.token)}) by host source"
    )
    rows = search.iter_post(q, hour - span, hour + 2 * span)
    return sorted(
        ((r["host"], r["source"], int(r["count"])) for r in rows),
        key=lambda item: (-item[2], item[0], item[1]),
    )


def _enclosing_hosts(bucket: int, coarse: list[tuple[int, Counter[int]]]) -> int:
    """Hosts novel in this bucket's enclosing slot at each coarser zoom level; widest wins."""
    return max((m.get(bucket // s * s, 0) for s, m in coarse), default=0)


def hunt(
    search: Search,
    index: str,
    start: float,
    end: float,
    *,
    candidates: int = 15,
    sample: int = 2000,
    tokens: int = 60,
    bursts_kept: int = 5,
) -> list[Lead]:
    """Rank host-buckets, at every zoom level, by template novelty x concentration, then
    value burst x linkage. `candidates` is the digging budget per zoom level."""
    leads: list[Lead] = []
    pool: list[Lead] = []
    series_cache: dict[tuple[str, int], dict[int, int]] = {}
    hour_cache: dict[tuple[str, int, int], int] = {}
    census_cache: dict[tuple[int, str, int], list[Mapping[str, Any]]] = {}
    history_cache: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    hosts = indexed_hosts(search, index, start, end)
    levels = [
        (span, host_hour_novelty(template_rows(search, index, start, end, span, hosts), span))
        for span in ladder(search, index, start, end)
    ]
    maps = {span: Counter(bucket for bucket, _ in nov) for span, nov in levels}
    for i, (span, novelty) in enumerate(levels):
        coarse = [(s, maps[s]) for s, _ in levels[i + 1 :]]
        level: list[Lead] = []
        for (bucket, host), (score, items) in novelty.items():
            spread = max(maps[span][bucket], _enclosing_hosts(bucket, coarse))
            # Total order for the displayed prefix: punct, then source, then count.
            shown = sorted(items, key=lambda item: (item[1], item[0], item[2]))[:20]
            level.append(Lead(bucket, host, round(score / spread, 2), spread, shown, span=span))
        level.sort(key=lambda lead: (-lead.novelty, lead.hour, lead.host, lead.span))
        leads += level
        pool += level[:candidates]
    for lead in pool:
        lead.bursts = value_bursts(
            search,
            index,
            lead,
            start,
            end,
            sample=sample,
            top=tokens,
            cache=series_cache,
            keep=bursts_kept,
            hour_cache=hour_cache,
            census_cache=census_cache,
        )
        for burst in lead.bursts:
            burst.links = link(search, index, burst, lead.hour, lead.span)
        peer_bursts(
            search,
            index,
            lead,
            start,
            end,
            cache=series_cache,
            census_cache=census_cache,
            history_cache=history_cache,
        )
    rank_coherence(pool)
    for lead in leads:
        if lead not in pool:
            lead.score = 0.0
    return fold_shared_values(
        fold_overlaps(
            sorted(leads, key=lambda lead: (-lead.score, lead.hour, lead.host, lead.span))
        )
    )


def fold_overlaps(ranked: list[Lead]) -> list[Lead]:
    """One incident seen at several zoom levels is one lead: a lead whose host matches and whose
    time bucket overlaps an already-ranked lead is folded into it (kept, but ranked after)."""
    kept: list[Lead] = []
    folded: list[Lead] = []
    spans: dict[str, list[tuple[int, int]]] = {}
    for lead in ranked:
        lo, hi = lead.hour, lead.hour + lead.span
        if lead.score > 0 and any(a < hi and lo < b for a, b in spans.get(lead.host, [])):
            folded.append(lead)
            continue
        kept.append(lead)
        if lead.score > 0:
            spans.setdefault(lead.host, []).append((lo, hi))
    return kept + folded


def _top_token(lead: Lead) -> str | None:
    return max(lead.bursts, key=lambda b: b.z).token if lead.bursts else None


def fold_shared_values(ranked: list[Lead]) -> list[Lead]:
    """One actor on several hosts is one lead: a lead whose top burst value already heads a kept
    lead on another host in an overlapping bucket is folded into it (kept, but ranked after)."""
    kept: list[Lead] = []
    folded: list[Lead] = []
    seen: list[tuple[str, int, int, str]] = []
    for lead in ranked:
        token = _top_token(lead)
        lo, hi = lead.hour, lead.hour + lead.span
        shared = token is not None and any(
            token == t and host != lead.host and a < hi and lo < b for t, a, b, host in seen
        )
        if lead.score > 0 and shared:
            folded.append(lead)
            continue
        kept.append(lead)
        if lead.score > 0 and token is not None:
            seen.append((token, lo, hi, lead.host))
    return kept + folded


def _percentiles(values: list[float]) -> list[float]:
    order = sorted(values)
    return [(order.index(v) + 1) / len(order) for v in values]


def rank_coherence(pool: list[Lead]) -> None:
    """Score = product of each signal's percentile among candidates: a lead must be unusual on
    every independent signal at once, not extreme on one ("this AND that came together")."""
    if not pool:
        return
    nov = _percentiles([lead.novelty for lead in pool])
    bur = _percentiles([max((b.peer_z for b in lead.bursts), default=0.0) for lead in pool])
    for lead, a, b in zip(pool, nov, bur, strict=True):
        lead.score = round(a * b, 4)


def epoch(day_hour: str) -> int:
    return calendar.timegm(time.strptime(day_hour, "%Y-%m-%d %H"))
