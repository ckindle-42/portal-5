"""Hunt engine v1 -- surface host-hours where several weak, generic signals come together.

Nothing here names a technique, an event code, a field, a sourcetype or a format. Every signal
is a statistic of the environment against its own prior history, computed in Splunk where
possible (the search tier does the volume; this process does the reasoning):

1. Template novelty. Splunk's indexed ``punct`` (the event's punctuation skeleton) is a
   format-agnostic template. A template never seen before on a host/source is novel; its weight
   grows with how much prior history said it was absent (no history -> no surprise).
2. Concentration. Novelty seen on every host at once is an environment event (boot, sensor
   start), not an intrusion; a host-hour's novelty is divided by the hosts novel that hour.
3. Value burst. Tokens from the host-hour's events are scored by how far this hour's count
   sits above that value's own prior hours (robust z on log counts).
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
_TIME_OF_DAY = re.compile(r"\d{1,2}:\d{2}:\d{2}")
_TERM_UNSAFE = re.compile(r"[\"\\=\[\]()|,;]")


class Search(Protocol):
    def iter_post(self, search: str, start: float, end: float) -> Iterable[Mapping[str, Any]]: ...


@dataclass
class Burst:
    token: str
    this_hour: int
    prior_median: float
    prior_hours_active: int
    z: float
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

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["hour_utc"] = time.strftime("%Y-%m-%d %H:00", time.gmtime(self.hour))
        return out


def _hour(value: Any) -> int:
    return int(float(value)) // HOUR * HOUR


def template_rows(search: Search, index: str, start: float, end: float) -> list[dict[str, Any]]:
    q = f"| tstats count where index={index} by host source punct _time span=1h"
    return [dict(r) for r in search.iter_post(q, start, end)]


def host_hour_novelty(
    rows: list[dict[str, Any]],
) -> dict[tuple[int, str], tuple[float, list[tuple[str, str, int]]]]:
    """Prior-only template novelty per host-hour, before the concentration discount."""
    by_stream: dict[tuple[str, str], dict[int, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in rows:
        by_stream[(r["host"], r["source"])][_hour(r["_time"])].append(
            (r.get("punct", ""), int(r["count"]))
        )
    out: dict[tuple[int, str], tuple[float, list[tuple[str, str, int]]]] = {}
    for (host, source), hours in by_stream.items():
        seen: set[str] = set()
        for n_prior, hour in enumerate(sorted(hours)):
            novel = [(p, c) for p, c in hours[hour] if p not in seen]
            seen.update(p for p, _ in hours[hour])
            if not novel or n_prior == 0:
                continue
            weight = math.log1p(n_prior) * len(novel)
            score, items = out.get((hour, host), (0.0, []))
            items = items + [(source, p, c) for p, c in novel]
            out[(hour, host)] = (score + weight, items)
    return out


def _is_time_token(token: str) -> bool:
    return bool(_TIME_OF_DAY.search(token))


def _token_series(
    search: Search, index: str, token: str, start: float, end: float
) -> dict[int, int]:
    q = f'| tstats count where index={index} TERM("{token}") by _time span=1h'
    return {_hour(r["_time"]): int(r["count"]) for r in search.iter_post(q, start, end)}


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
    events = list(search.iter_post(q, lead.hour, lead.hour + HOUR))
    tokens = Counter(
        t
        for e in events
        for t in set(_TOKEN.findall(str(e.get("_raw", ""))))
        if not _is_time_token(t) and not _TERM_UNSAFE.search(t)
    )
    chosen = [t for t, _ in tokens.most_common(top)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        series = list(pool.map(lambda t: _token_series(search, index, t, start, end), chosen))
    bursts = [b for t, s in zip(chosen, series, strict=True) if (b := _burst(t, lead.hour, s))]
    return sorted(bursts, key=lambda b: -b.z)


def link(search: Search, index: str, burst: Burst, hour: int) -> list[tuple[str, str, int]]:
    q = f'| tstats count where index={index} TERM("{burst.token}") by host source'
    rows = search.iter_post(q, hour - HOUR, hour + 2 * HOUR)
    return sorted(((r["host"], r["source"], int(r["count"])) for r in rows), key=lambda x: -x[2])


def hunt(
    search: Search,
    index: str,
    start: float,
    end: float,
    *,
    candidates: int = 40,
    sample: int = 2000,
    tokens: int = 60,
    bursts_kept: int = 5,
) -> list[Lead]:
    """Rank host-hours by template novelty x concentration, then value burst x linkage."""
    novelty = host_hour_novelty(template_rows(search, index, start, end))
    hosts_novel = Counter(hour for hour, _ in novelty)
    leads = [
        Lead(hour, host, round(score / hosts_novel[hour], 2), hosts_novel[hour], items[:20])
        for (hour, host), (score, items) in novelty.items()
    ]
    leads.sort(key=lambda lead: -lead.novelty)
    pool = leads[:candidates]
    for lead in pool:
        lead.bursts = value_bursts(search, index, lead, start, end, sample=sample, top=tokens)[
            :bursts_kept
        ]
        for b in lead.bursts:
            b.links = link(search, index, b, lead.hour)
    rank_coherence(pool)
    for lead in leads[candidates:]:
        lead.score = 0.0
    return sorted(leads, key=lambda lead: -lead.score)


def _percentiles(values: list[float]) -> list[float]:
    order = sorted(values)
    return [(order.index(v) + 1) / len(order) for v in values]


def rank_coherence(pool: list[Lead]) -> None:
    """Score = product of each signal's percentile among candidates: a lead must be unusual on
    every independent signal at once, not extreme on one ("this AND that came together")."""
    if not pool:
        return
    nov = _percentiles([lead.novelty for lead in pool])
    bur = _percentiles([max((b.z for b in lead.bursts), default=0.0) for lead in pool])
    for lead, a, b in zip(pool, nov, bur, strict=True):
        lead.score = round(a * b, 4)


def epoch(day_hour: str) -> int:
    return calendar.timegm(time.strptime(day_hour, "%Y-%m-%d %H"))
