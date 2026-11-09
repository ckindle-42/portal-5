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
_TERM_UNSAFE = re.compile(r"[\"\\=\[\]()|,;']")


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

    @property
    def pivot_tokens(self) -> set[str]:
        return {p.token for p in self.pivots}

    def summary(self) -> dict[str, Any]:
        hosts = Counter(e["host"] for e in self.events.values())
        hours = sorted({int(e["time"]) // HOUR * HOUR for e in self.events.values()})
        return {
            "seed": self.seed,
            "merged_from": self.merged_from,
            "events": len(self.events),
            "hosts": dict(hosts.most_common()),
            "sources": len({(e["host"], e["source"]) for e in self.events.values()}),
            "span_hours": (hours[-1] - hours[0]) // HOUR + 1 if hours else 0,
            "pivots": [p.__dict__ for p in self.pivots],
        }


def _tokens(raw: str) -> set[str]:
    return {t for t in _TOKEN.findall(raw) if not _is_time_token(t) and not _TERM_UNSAFE.search(t)}


class Investigator:
    def __init__(self, search: Search, index: str, start: float, end: float) -> None:
        self.search, self.index, self.start, self.end = search, index, start, end
        rows = list(search.iter_post(f"| tstats count where index={index}", start, end))
        self.total = int(rows[0]["count"]) if rows else 1
        self._footprints: dict[str, tuple[int, int, int]] = {}

    def footprint(self, token: str) -> tuple[int, int, int]:
        """(index-wide count, distinct hosts, distinct sources) for one value."""
        if token not in self._footprints:
            q = f'| tstats count where index={self.index} TERM("{token}") by host source'
            rows = list(self.search.iter_post(q, self.start, self.end))
            self._footprints[token] = (
                sum(int(r["count"]) for r in rows),
                len({r["host"] for r in rows}),
                len({(r["host"], r["source"]) for r in rows}),
            )
        return self._footprints[token]

    def pivot_weight(self, token: str) -> float:
        """Specific (rare in the environment) and recurring in at least two places.

        Recurrence is the condition (a value seen in one place leads nowhere); rarity is the
        rank. Rewarding spread would favour background words that are everywhere."""
        count, _hosts, sources = self.footprint(token)
        if count < 2 or sources < 2:
            return 0.0
        return math.log(self.total / count)

    def kinds(self, token: str, per_kind: int = 2) -> list[dict[str, Any]]:
        """Every distinct kind of event the value appears in, a couple of examples of each."""
        q = (
            f'search index={self.index} TERM("{token}") '
            f"| dedup {per_kind} host source punct | table _time host source _raw"
        )
        return [dict(r) for r in self.search.iter_post(q, self.start, self.end)]

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
            rows = self.search.iter_post(q, lead.hour, lead.hour + HOUR)
            events.extend(dict(r) for r in rows if r.get("punct", "") == punct)
            if len(events) > 400:
                break
        candidates = Counter(t for e in events[:400] for t in _tokens(str(e.get("_raw", ""))))
        scored = self.score_candidates(t for t, _ in candidates.most_common(examine))
        seeds += [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0]
        return list(dict.fromkeys(seeds))

    def investigate(
        self, lead: Lead, *, depth: int = 3, breadth: int = 6, examine: int = 40
    ) -> Case:
        case = Case(seed=f"{lead.host}@{lead.hour}", seed_hour=lead.hour)
        frontier = self.seed_tokens(lead, examine)[:breadth]
        visited: set[str] = set()
        for level in range(depth):
            seen_here: Counter[str] = Counter()
            for token in frontier:
                if token in visited:
                    continue
                visited.add(token)
                count, hosts, sources = self.footprint(token)
                case.pivots.append(
                    Pivot(token, count, hosts, sources, level, round(self.pivot_weight(token), 2))
                )
                for e in self.kinds(token):
                    key = f"{e['host']}|{e['source']}|{e['_raw']}"
                    case.events.setdefault(
                        key,
                        {
                            "host": e["host"],
                            "source": e["source"],
                            "time": float(e["_time"]),
                            "raw": e["_raw"],
                            "via": token,
                        },
                    )
                    seen_here.update(_tokens(str(e["_raw"])) - visited)
            scored = self.score_candidates(t for t, _ in seen_here.most_common(examine))
            frontier = [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0][
                :breadth
            ]
            if not frontier:
                break
        return case


def merge_cases(cases: list[Case]) -> list[Case]:
    """Cases that pivoted through the same value are one story."""
    merged: list[Case] = []
    for case in cases:
        home = next((m for m in merged if m.pivot_tokens & case.pivot_tokens), None)
        if home is None:
            case.merged_from = [case.seed]
            merged.append(case)
            continue
        home.merged_from.append(case.seed)
        known = home.pivot_tokens
        home.pivots += [p for p in case.pivots if p.token not in known]
        for key, ev in case.events.items():
            home.events.setdefault(key, ev)
    return merged
