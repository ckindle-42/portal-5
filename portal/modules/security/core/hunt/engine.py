"""Hunt engine: layer-1 observations are the seeds, episodes are the leads.

One pass scores volume, source, shape, stream, and learned values with the current
baseline. The top of that total order, bounded by the candidates effort budget, is
grouped into episodes and handed to investigation as leads. Observations outside
that budget stay listed. Nothing here names a technique, a field, or a format.
"""

from __future__ import annotations

import calendar
import math
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol

HOUR = 3600
_TIME_OF_DAY = re.compile(r"\d{1,2}:\d{2}:\d{2}")


class Search(Protocol):
    def iter_post(self, search: str, start: float, end: float) -> Iterable[Mapping[str, Any]]: ...


class SearchBudgetExceededError(RuntimeError):
    """A shared hunt effort budget ran out inside one search call."""


class SearchCoverageCensoredError(RuntimeError):
    """A search stopped early; its rows are not an exact count."""


class SearchQueryBoundError(SearchCoverageCensoredError):
    """One search exceeded its own query time bound."""


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
    span: int = HOUR  # episode window; `hour` is the first hour of the episode
    observations: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["hour_utc"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(self.hour))
        return out


def _hour(value: Any, span: int = HOUR) -> int:
    return int(float(value)) // span * span


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


def _search_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _copy_kinds(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        kind: {"requests": int(slot["requests"]), "seconds": round(float(slot["seconds"]), 3)}
        for kind, slot in stats.items()
    }


def _record(search: Search, run: Any, investigated: set[tuple[str, str, str, int]]) -> None:
    """Keep observation timings and the uninvestigated list on the shared budget."""
    budget = getattr(search, "budget", None)
    if budget is None:
        return
    notes = getattr(budget, "ranking_notes", None)
    if isinstance(notes, set):
        for name, slot in run.coverage.items():
            for reason in slot.get("reasons", []):
                notes.add(f"{name}:{reason}")
    kinds = _copy_kinds(run.request_kinds)
    listed = []
    for obs in run.observations:
        row = {
            "kind": obs.kind,
            "host": obs.host,
            "entity": obs.entity,
            "hour": obs.hour,
            "score": obs.score,
            "signal": obs.evidence.get("signal"),
            "now": obs.evidence.get("now"),
            "literal": obs.evidence.get("literal"),
            "investigated": (obs.kind, obs.host, obs.entity, obs.hour) in investigated,
        }
        listed.append(row)
    budget.observation_request_kinds = kinds
    budget.listed_observations = listed
    stats = getattr(budget, "kind_stats", None)
    if isinstance(stats, dict):
        stats.clear()


def _budget_stopped(run: Any) -> bool:
    return any("budget" in slot.get("reasons", []) for slot in run.coverage.values())


def hunt(
    search: Search,
    index: str,
    start: float,
    end: float,
    *,
    candidates: int = 15,
) -> list[Lead]:
    """Seeds are the top of the observation order. `candidates` bounds how many are investigated."""
    from portal.modules.security.core.hunt.episodes import accumulate, to_lead
    from portal.modules.security.core.hunt.observations import observe

    run = observe(search, index, start, end, baseline="current")
    ordered = list(run.observations)
    seeds = ordered[: max(0, candidates)]
    place = {
        (obs.kind, obs.host, obs.entity, obs.hour, str(obs.evidence.get("signal", ""))): index
        for index, obs in enumerate(ordered)
    }
    episodes = accumulate(seeds, ordered, place)
    leads = [to_lead(episode, place) for episode in episodes]
    investigated = {
        (row["kind"], row["host"], row["entity"], row["hour"])
        for lead in leads
        for row in lead.observations
    }
    _record(search, run, investigated)
    if _budget_stopped(run):
        raise SearchBudgetExceededError("observation_budget_exhausted")
    return leads


def epoch(day_hour: str) -> int:
    return calendar.timegm(time.strptime(day_hour, "%Y-%m-%d %H"))
