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
from typing import Any, Protocol

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
            f"| tstats min(_time) as lo max(_time) as hi where index={index}", start, end
        )
    )
    if not rows or rows[0].get("lo") is None:
        return [HOUR]
    data_span = float(rows[0]["hi"]) - float(rows[0]["lo"])
    return [s for s in LADDER if data_span >= 2 * s] or [LADDER[0]]


def template_rows(
    search: Search, index: str, start: float, end: float, span: int = HOUR
) -> list[dict[str, Any]]:
    q = f"| tstats count where index={index} by host source punct _time span={span}s"
    return [dict(r) for r in search.iter_post(q, start, end)]


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
            novel = [(p, c) for p, c in hours[hour] if p not in seen]
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
    return bool(_TIME_OF_DAY.search(token))


def _pivotable(token: str) -> bool:
    return (
        bool(_HAS_VALUE.search(token))
        and not _is_time_token(token)
        and not _TERM_UNSAFE.search(token)
    )


def _token_series(
    search: Search, index: str, token: str, start: float, end: float, span: int = HOUR
) -> dict[int, int]:
    q = f'| tstats count where index={index} TERM("{token}") by _time span={span}s'
    return {_hour(r["_time"], span): int(r["count"]) for r in search.iter_post(q, start, end)}


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


def value_bursts(
    search: Search, index: str, lead: Lead, start: float, end: float, *, sample: int, top: int
) -> list[Burst]:
    q = (
        f'search index={index} host="{lead.host}" | eval r=random() % 1000 '
        f"| sort r | head {sample} | table _raw"
    )
    events = list(search.iter_post(q, lead.hour, lead.hour + lead.span))
    tokens = Counter(
        t for e in events for t in set(_TOKEN.findall(str(e.get("_raw", "")))) if _pivotable(t)
    )
    chosen = [t for t, _ in tokens.most_common(top)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        series = list(
            pool.map(lambda t: _token_series(search, index, t, start, end, lead.span), chosen)
        )
    bursts = [b for t, s in zip(chosen, series, strict=True) if (b := _burst(t, lead.hour, s))]
    return sorted(bursts, key=lambda b: -b.z)


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
) -> list[str]:
    """Values in the burst token's slot of the same event shape on the lead's host, from history."""
    q = (
        f'search index={index} host="{lead.host}" TERM("{burst.token}") '
        f"| head {sample} | table _raw punct"
    )
    shapes = _slots(search.iter_post(q, lead.hour, lead.hour + lead.span), burst.token)
    peers: list[str] = []
    for punct, slot in list(shapes.items())[:PEER_SHAPES]:
        prior = (
            f'search index={index} host="{lead.host}" punct={_search_literal(punct)} '
            f"| head {sample} | table _raw"
        )
        for row in search.iter_post(prior, start, lead.hour):
            tokens = _TOKEN.findall(str(row.get("_raw", "")))
            candidate = tokens[slot] if slot < len(tokens) else ""
            if (
                candidate
                and candidate != burst.token
                and _pivotable(candidate)
                and candidate not in peers
            ):
                peers.append(candidate)
            if len(peers) >= PEERS:
                return peers
    return peers


def peer_bursts(search: Search, index: str, lead: Lead, start: float, end: float) -> None:
    """Rank each kept burst against the same-slot values instead of only its own history."""
    found = [peer_tokens(search, index, lead, burst, start) for burst in lead.bursts]
    flat = [token for peers in found for token in peers]

    def series(token: str) -> dict[int, int]:
        return _token_series(search, index, token, start, end, lead.span)

    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(series, flat))
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
    q = f'| tstats count where index={index} TERM("{burst.token}") by host source'
    rows = search.iter_post(q, hour - span, hour + 2 * span)
    return sorted(((r["host"], r["source"], int(r["count"])) for r in rows), key=lambda x: -x[2])


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
    levels = [
        (span, host_hour_novelty(template_rows(search, index, start, end, span), span))
        for span in ladder(search, index, start, end)
    ]
    maps = {span: Counter(bucket for bucket, _ in nov) for span, nov in levels}
    for i, (span, novelty) in enumerate(levels):
        coarse = [(s, maps[s]) for s, _ in levels[i + 1 :]]
        level: list[Lead] = []
        for (bucket, host), (score, items) in novelty.items():
            spread = max(maps[span][bucket], _enclosing_hosts(bucket, coarse))
            level.append(
                Lead(bucket, host, round(score / spread, 2), spread, items[:20], span=span)
            )
        level.sort(key=lambda lead: -lead.novelty)
        leads += level
        pool += level[:candidates]
    for lead in pool:
        lead.bursts = value_bursts(search, index, lead, start, end, sample=sample, top=tokens)[
            :bursts_kept
        ]
        for b in lead.bursts:
            b.links = link(search, index, b, lead.hour, lead.span)
        peer_bursts(search, index, lead, start, end)
    rank_coherence(pool)
    for lead in leads:
        if lead not in pool:
            lead.score = 0.0
    return fold_shared_values(fold_overlaps(sorted(leads, key=lambda lead: -lead.score)))


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
