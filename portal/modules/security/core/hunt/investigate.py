"""Investigation -- dig from a lead the way an analyst does, until the picture assembles.

An analyst does not know the vector up front. From something odd they pivot on its values,
look at every *kind* of event each value shows up in (not every event), notice the new odd
values those events carry, and keep pulling. Cases that turn out to share values are one story.

Generic only: a value is a token from the raw event; a "kind" of event is (host, source, punct);
a good pivot is rare in the environment yet recurs across several places (a value seen once is
a dead end, a value seen everywhere is background). Depth and breadth are effort budgets, not
decision thresholds -- they bound how long the analyst digs, never what counts as suspicious.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .engine import HOUR, Lead, Search, _is_time_token

_TOKEN = re.compile(r"[A-Za-z0-9_.:/@%\-]{4,}")
# A value has at least one letter or digit; a run of punctuation ("........") is formatting.
# Found live on BOTS v1: such a pivot became a full-index plain search (>20 min).
_HAS_VALUE = re.compile(r"[A-Za-z0-9]")
_TERM_UNSAFE = re.compile(r"[\"\\=\[\]()|,;']")
CORE_EVENTS = 200  # effort budget: how many events the focused case core may hold
PER_KIND = 3  # effort budget: examples of any one kind of event shown in the core
TIMELINE_DAYS = 5  # effort budget: how many other days of a value's timeline are read
_TOP_DECILE = 0.1  # a level's own top decile -- a relative band, not a suspicion threshold


@dataclass
class Pivot:
    token: str
    count: int
    hosts: int
    sources: int
    depth: int
    weight: float


@dataclass
class Case:
    seed: str
    seed_hour: int
    pivots: list[Pivot] = field(default_factory=list)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    merged_from: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    # the seed leads' own windows: (host, bucket start, bucket end)
    seed_windows: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def pivot_tokens(self) -> set[str]:
        return {p.token for p in self.pivots}

    def summary(self) -> dict[str, Any]:
        hosts = Counter(e["host"] for e in self.events.values())
        hours = sorted({int(e["time"]) // HOUR * HOUR for e in self.events.values()})
        core = self.core()
        return {
            "seed": self.seed,
            "merged_from": self.merged_from,
            "events": len(self.events),
            "core_events": len(core),
            "core_hosts": len({e["host"] for e in core}),
            "hosts": dict(hosts.most_common()),
            "sources": len({(e["host"], e["source"]) for e in self.events.values()}),
            "span_hours": (hours[-1] - hours[0]) // HOUR + 1 if hours else 0,
            "pivot_depths": dict(sorted(Counter(p.depth for p in self.pivots).items())),
            "degraded": self.degraded,
            "pivots": [p.__dict__ for p in self.pivots],
            "core": core,
            "picture": self.picture(),
        }

    def core(self, cap: int = CORE_EVENTS) -> list[dict[str, Any]]:
        """The case read outward from its seed leads, diversified by kind, in time order."""
        events = list(self.events.values())
        if not events:
            return []
        depth = {p.token: p.depth for p in self.pivots}

        def in_seed(e: dict[str, Any]) -> bool:
            return any(h == e["host"] and lo <= e["time"] < hi for h, lo, hi in self.seed_windows)

        def order(e: dict[str, Any]) -> tuple[int, int, int, float]:
            token = str(e.get("via", "")).split(":", 1)[-1]
            # outward from the lead, as an analyst reads a case: what happened in the lead's own
            # window on its host first, then the closest pivots, then rarer kinds and specificity
            return (
                0 if in_seed(e) else 1,
                depth.get(token, 99),
                int(e.get("kind_count") or 1),
                -float(e.get("weight", 0.0)),
            )

        taken: Counter[str] = Counter()
        focused: list[dict[str, Any]] = []
        for e in sorted(events, key=order):
            # an event with no recorded kind is its own kind (never collapsed with others)
            kind = e.get("kind") or f"{e['host']}|{e['source']}|{e['raw']}"
            if taken[kind] >= PER_KIND:
                continue
            taken[kind] += 1
            focused.append(e)
            if len(focused) >= cap:
                break
        return sorted(focused, key=lambda e: e["time"])

    def picture(self, n: int = 25) -> list[dict[str, Any]]:
        """The analyst's view: the core's most specific events, in time order."""
        focused = sorted(
            ((float(e.get("weight", 0.0)), e) for e in self.core()), key=lambda we: -we[0]
        )
        return [e for _w, e in sorted(focused[:n], key=lambda we: we[1]["time"])]


_PART = re.compile(r"[:/=@]+")


def _tokens(raw: str) -> set[str]:
    """Whole tokens plus their parts: `www-data:msperl` is also `www-data` and `msperl`."""
    out: set[str] = set()
    for t in _TOKEN.findall(raw):
        for piece in (t, *_PART.split(t)):
            if (
                len(piece) >= 4
                and _HAS_VALUE.search(piece)
                and not _is_time_token(piece)
                and not _TERM_UNSAFE.search(piece)
            ):
                out.add(piece)
    return out


def _recurring_least_common(counts: Counter[str], n: int) -> list[str]:
    """Candidates an analyst would look at: values that recur in the evidence, least common
    first (frequent-in-evidence values are mostly background)."""
    return [t for t, c in sorted(counts.items(), key=lambda kv: (kv[1], kv[0])) if c >= 2][:n]


def _top_decile_cut(values: list[int]) -> int | None:
    """A zoom level's environment-wide band: the rarest value band holding at most a tenth of
    the level. A level with spread but no clean decile still has its maximum as that band."""
    if not values:
        return None
    counts = Counter(values)
    at_or_above = 0
    cut: int | None = None
    for value in sorted(counts, reverse=True):
        at_or_above += counts[value]
        if at_or_above / len(values) > _TOP_DECILE:
            break
        cut = value
    if cut is None and len(counts) > 1:
        return max(counts)
    return cut


class Investigator:
    def __init__(self, search: Search, index: str, start: float, end: float) -> None:
        self.search, self.index, self.start, self.end = search, index, start, end
        rows = list(search.iter_post(f"| tstats count where index={index}", start, end))
        self.total = int(rows[0]["count"]) if rows else 1
        # Populated hours, not min..max span: a handful of events stamped with their ingest time
        # (no timestamp in their file) stretched Kyoushi's span from 6 days to ~5 years, shrank
        # this scale to ~550 and capped nearly every pivot to one identical weight (found live, P2).
        populated = list(
            search.iter_post(
                f"| tstats count where index={index} by _time span=1h | stats count", start, end
            )
        )
        hours = max(1.0, float(populated[0]["count"])) if populated else 1.0
        # A value seen more often than an average populated hour of this environment is
        # background-scale; exact counting stops there (its weight is already low).
        self.background_scale = max(2, int(self.total / hours))
        self.degraded: list[str] = []
        self._footprints: dict[tuple[str, bool], tuple[int, int, int]] = {}
        q = f"| tstats count where index={index} by host source punct"
        self.template_count = {
            (r["host"], r["source"], r.get("punct", "")): int(r["count"])
            for r in self._rows(q, start, end)
        }

    def _rows(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        """Splunk returns multivalue fields as lists (found live on BOTS v1: the investigation
        crashed with `unhashable type: list`); a row is flattened to its first value per field."""
        return [
            {k: (v[0] if isinstance(v, list) and v else v) for k, v in r.items()}
            for r in self.search.iter_post(q, start, end)
        ]

    def _footprint_rows(self, token: str, exact: bool) -> list[dict[str, Any]]:
        if not exact:
            q = f'| tstats count where index={self.index} TERM("{token}") by host source'
            rows = list(self._rows(q, self.start, self.end))
            if rows:
                return rows
        q = (
            f'search index={self.index} "{token}" | head {self.background_scale} '
            "| stats count by host source"
        )
        return list(self._rows(q, self.start, self.end))

    def footprint(self, token: str, *, exact: bool = False) -> tuple[int, int, int]:
        """(index-wide count, distinct hosts, distinct sources) for one value.

        Ranking candidates uses TERM() (fast, index-only, but blind to a value inside a compound
        such as `192.42.0.255:41607`). A value chosen as a pivot gets the exact plain-search
        footprint -- measured live: TERM found 179 of the attacker address's 455 events."""
        key = (token, exact)
        if key not in self._footprints:
            try:
                rows = self._footprint_rows(token, exact)
            except Exception as exc:  # noqa: BLE001 -- one failed lookup degrades one pivot
                self.degraded.append(f"{token}: {type(exc).__name__}")
                rows = []
            self._footprints[key] = (
                sum(int(r["count"]) for r in rows),
                len({r["host"] for r in rows}),
                len({(r["host"], r["source"]) for r in rows}),
            )
        return self._footprints[key]

    def pivot_weight(self, token: str, *, exact: bool = False) -> float:
        """Specific (rare in the environment) and recurring in at least two places.

        Recurrence is the condition (a value seen in one place leads nowhere); rarity is the
        rank. Rewarding spread would favour background words that are everywhere."""
        count, _hosts, sources = self.footprint(token, exact=exact)
        if count < 2 or sources < 2:
            return 0.0
        return math.log(self.total / count)

    def kinds(self, token: str, per_kind: int = 2) -> list[dict[str, Any]]:
        """Every distinct kind of event the value appears in, a couple of examples of each."""
        q = (
            f'search index={self.index} "{token}" '
            f"| dedup {per_kind} host source punct | table _time host source punct _raw"
        )
        try:
            return [dict(r) for r in self._rows(q, self.start, self.end)]
        except Exception as exc:  # noqa: BLE001 -- one failed lookup degrades one pivot
            self.degraded.append(f"kinds {token}: {type(exc).__name__}")
            return []

    def timeline(
        self, token: str, *, seed_day: int, days: int = TIMELINE_DAYS
    ) -> list[dict[str, Any]]:
        """The kinds of event a value appears in on days other than the seed's -- the link a
        value pivot alone never reaches, because the seed day's examples fill the per-kind cap."""
        q = (
            f'search index={self.index} "{token}" | head {self.background_scale} '
            "| bin _time span=1h | stats count by _time host source"
        )
        try:
            rows = self._rows(q, self.start, self.end)
        except Exception as exc:  # noqa: BLE001 -- one failed lookup degrades one pivot
            self.degraded.append(f"timeline {token}: {type(exc).__name__}")
            return []
        per_hour: Counter[int] = Counter()
        for r in rows:
            t = int(float(r["_time"]))
            if t // 86400 != seed_day:
                per_hour[t // HOUR * HOUR] += int(r["count"])
        blocks: list[tuple[int, int, int]] = []
        for hour in sorted(per_hour):
            if blocks and blocks[-1][1] == hour:
                lo, _hi, count = blocks[-1]
                blocks[-1] = (lo, hour + HOUR, count + per_hour[hour])
            else:
                blocks.append((hour, hour + HOUR, per_hour[hour]))
        out: list[dict[str, Any]] = []
        for lo, hi, _count in sorted(blocks, key=lambda b: -b[2])[:days]:
            self._timeline_kinds(token, lo, hi, out)
        return out

    def _timeline_kinds(self, token: str, lo: int, hi: int, out: list[dict[str, Any]]) -> None:
        q = (
            f'search index={self.index} "{token}" '
            "| dedup 2 host source punct | table _time host source punct _raw"
        )
        try:
            out.extend(dict(r) for r in self._rows(q, lo, hi))
        except Exception as exc:  # noqa: BLE001 -- one failed block degrades, not fails
            self.degraded.append(f"timeline kinds {token}: {type(exc).__name__}")

    def neighborhood(
        self, event: dict[str, Any], *, minutes: int, kinds: int
    ) -> list[dict[str, Any]]:
        """What else happened on this host around this moment -- rarest kinds of event first.

        `minutes` is how far the analyst looks around, not a judgement of what is odd."""
        t = float(event["time"])
        q = (
            f'search index={self.index} host="{event["host"]}" '
            "| dedup 2 source punct | table _time host source punct _raw"
        )
        try:
            rows = [dict(r) for r in self._rows(q, t - 60 * minutes, t + 60 * minutes)]
        except Exception as exc:  # noqa: BLE001 -- one failed look-around degrades, not fails
            self.degraded.append(f"near {event['host']}@{t:.0f}: {type(exc).__name__}")
            return []
        rows.sort(
            key=lambda r: self.template_count.get((r["host"], r["source"], r.get("punct", "")), 0)
        )
        return rows[:kinds]

    def score_candidates(self, tokens: Iterable[str]) -> dict[str, float]:
        chosen = list(tokens)
        with ThreadPoolExecutor(max_workers=8) as pool:
            weights = list(pool.map(self.pivot_weight, chosen))
        return dict(zip(chosen, weights, strict=True))

    def seed_tokens(self, lead: Lead, examine: int) -> list[str]:
        """The lead's bursting values plus values from its never-before-seen kinds of event."""
        seeds = [b.token for b in lead.bursts if b.z > 0]
        events: list[dict[str, Any]] = []
        for source, punct, _ in lead.novel_templates[:10]:
            q = f'search index={self.index} host="{lead.host}" source="{source}" | table _raw punct'
            rows = self._rows(q, lead.hour, lead.hour + lead.span)
            events.extend(dict(r) for r in rows if r.get("punct", "") == punct)
            if len(events) > 400:
                break
        candidates = Counter(t for e in events[:400] for t in _tokens(str(e.get("_raw", ""))))
        scored = self.score_candidates(t for t, _ in candidates.most_common(examine))
        seeds += [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0]
        return list(dict.fromkeys(seeds))

    def investigate(
        self,
        lead: Lead,
        *,
        depth: int = 3,
        breadth: int = 6,
        examine: int = 120,
        minutes: int = 15,
    ) -> Case:
        case = Case(
            seed=f"{lead.host}@{lead.hour}",
            seed_hour=lead.hour,
            seed_windows=[(lead.host, lead.hour, lead.hour + lead.span)],
        )
        mark = len(self.degraded)
        frontier = self.seed_tokens(lead, examine)[:breadth]
        visited: set[str] = set()
        looked_around: set[tuple[str, float]] = set()
        for level in range(depth):
            seen_here: Counter[str] = Counter()
            reached: list[tuple[float, dict[str, Any]]] = []
            for token in frontier:
                if token in visited:
                    continue
                visited.add(token)
                count, hosts, sources = self.footprint(token, exact=True)
                weight = round(self.pivot_weight(token, exact=True), 2)
                case.pivots.append(Pivot(token, count, hosts, sources, level, weight))
                for e in self.kinds(token):
                    ev = self._add(case, e, via=token, weight=weight)
                    reached.append((weight, ev))
                    seen_here.update(_tokens(str(e["_raw"])) - visited)
                if weight > 0:
                    for e in self.timeline(token, seed_day=lead.hour // 86400):
                        self._add(case, e, via=f"timeline:{token}", weight=weight)
            # time/place pivot: around the most specific events this round, on their host
            for weight, ev in sorted(reached, key=lambda we: -we[0])[:breadth]:
                spot = (ev["host"], float(ev["time"]) // 60)
                if spot in looked_around:
                    continue
                looked_around.add(spot)
                for e in self.neighborhood(ev, minutes=minutes, kinds=breadth):
                    self._add(case, e, via=f"near:{ev['via']}", weight=weight)
                    seen_here.update(_tokens(str(e["_raw"])) - visited)
            scored = self.score_candidates(_recurring_least_common(seen_here, examine))
            frontier = [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0][
                :breadth
            ]
            if not frontier:
                break
        case.degraded = self.degraded[mark:]
        return case

    def investigate_all(self, leads: list[Lead], *, dig: int) -> list[Case]:
        """Dig the top `dig` leads that are not their zoom level's environment-wide band."""
        values: dict[int, list[int]] = {}
        for lead in leads:
            values.setdefault(lead.span, []).append(lead.hosts_novel_that_hour)
        cuts = {span: _top_decile_cut(v) for span, v in values.items()}
        chosen = [
            lead
            for lead in leads
            if (cut := cuts[lead.span]) is None or lead.hosts_novel_that_hour < cut
        ]
        return merge_cases([self.investigate(lead) for lead in chosen[:dig]])

    def _add(self, case: Case, e: dict[str, Any], *, via: str, weight: float) -> dict[str, Any]:
        key = f"{e['host']}|{e['source']}|{e['_raw']}"
        kind = (e["host"], e["source"], e.get("punct", ""))
        return case.events.setdefault(
            key,
            {
                "host": e["host"],
                "source": e["source"],
                "time": float(e["_time"]),
                "raw": e["_raw"],
                "via": via,
                "weight": weight,
                "kind": "|".join(kind),
                # how common this kind of event is in the environment (0 = unknown)
                "kind_count": self.template_count.get(kind, 0),
            },
        )


def _shared_pivots(a: Case, b: Case) -> set[str]:
    """A value worth merging two cases on: no more common than the less-specific case's median
    pivot count (relative, not a constant), and reached near a seed in at least one of them."""

    def median_count(case: Case) -> float:
        counts = sorted(p.count for p in case.pivots)
        return counts[len(counts) // 2] if counts else 0.0

    bar = min(median_count(a), median_count(b))
    pa = {p.token: p for p in a.pivots}
    pb = {p.token: p for p in b.pivots}
    return {
        token
        for token in pa.keys() & pb.keys()
        if min(pa[token].count, pb[token].count) <= bar
        and min(pa[token].depth, pb[token].depth) <= 1
    }


def merge_cases(cases: list[Case]) -> list[Case]:
    """Cases that pivoted through the same specific value are one story."""
    merged: list[Case] = []
    for case in cases:
        home = next((m for m in merged if _shared_pivots(m, case)), None)
        if home is None:
            case.merged_from = [case.seed]
            merged.append(case)
            continue
        home.merged_from.append(case.seed)
        home.degraded.extend(case.degraded)
        home.seed_windows.extend(case.seed_windows)
        known = home.pivot_tokens
        home.pivots += [p for p in case.pivots if p.token not in known]
        for key, ev in case.events.items():
            home.events.setdefault(key, ev)
    return merged
