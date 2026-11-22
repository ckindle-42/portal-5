"""Hunt engine: host-hours are the seeds, episodes are the leads.

One pass scores volume, source, shape, stream, and learned values with the current
baseline. Host-hours in the final order, bounded by the candidates effort budget,
supply the positive-scored observations that become episodes. Observations outside
that budget stay listed. Nothing here names a technique, a field, or a format.
"""

from __future__ import annotations

import calendar
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Protocol

from portal.modules.security.core.hunt.judge import JudgeClient

HOUR = 3600
_TIME_OF_DAY = re.compile(r"\d{1,2}:\d{2}:\d{2}")
# Splunk default segmenters.conf breakers: https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/9.2/configuration-file-reference/9.2.5-configuration-file-reference/segmenters.conf
_MAJOR_BREAKERS = (
    "%2526",
    "%2520",
    "%21",
    "%26",
    "%3B",
    "%7C",
    "%20",
    "%2B",
    "%3D",
    "%5D",
    "%5B",
    "%3A",
    "%0A",
    "%2C",
    "%28",
    "%29",
    "--",
    "[",
    "]",
    "<",
    ">",
    "(",
    ")",
    "{",
    "}",
    "|",
    "!",
    ";",
    ",",
    "'",
    '"',
    "*",
    "&",
    "?",
    "+",
)
_MINOR_BREAKERS = frozenset("/:=@.-$#%\\_")
_MAJOR_BREAKER_RE = re.compile(r"\s+|" + "|".join(re.escape(item) for item in _MAJOR_BREAKERS))


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
    risk: float = 0.0  # accumulated risk of this lead's best host-hour
    acc_rank: int = 0  # that host-hour's place in the accumulated order
    p_yes: float | None = None  # judge mass for that host-hour; null when unjudged

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["hour_utc"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(self.hour))
        return out


def _hour(value: Any, span: int = HOUR) -> int:
    return int(float(value)) // span * span


@lru_cache(maxsize=4096)
def _log1p(value: float) -> float:
    """log(1 + value) rounded in software: glibc and Apple libm differ by one ULP."""
    if value == 0.0:
        return 0.0
    return float((Decimal(1) + Decimal(value)).ln())


def _expm1(value: float) -> float:
    """exp(value) - 1 rounded once in software, so a receipt is byte-identical everywhere."""
    return float(Decimal(value).exp() - 1)


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
            weight = _log1p(prior_hours) * len(novel)
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
    logs = [_log1p(v) for v in prior if v]
    med = statistics.median(logs)
    mad = statistics.median(abs(x - med) for x in logs)
    z = (_log1p(now) - med) / (mad + 0.5)
    return Burst(token, now, round(_expm1(med), 1), active, round(z, 2))


def _search_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _literal_term_segments(value: str) -> tuple[str, ...]:
    """Return at most two longest whole Splunk terms from one value."""
    candidates = []
    start = 0
    unsafe_left = False
    for breaker in _MAJOR_BREAKER_RE.finditer(value + " "):
        segment = value[start : breaker.start()]
        if segment and all(char.isalnum() or char in _MINOR_BREAKERS for char in segment):
            pieces = []
            piece_start = None
            for offset, char in enumerate(segment):
                if char.isalnum():
                    if piece_start is None:
                        piece_start = offset
                elif piece_start is not None:
                    pieces.append((piece_start, offset))
                    piece_start = None
            if piece_start is not None:
                pieces.append((piece_start, len(segment)))
            # Splunk's wildcard breakers do not make their directly touching fragments searchable.
            if unsafe_left and pieces and pieces[0][0] == 0:
                pieces = pieces[1:]
            if breaker.group() in ("*", "?") and pieces and pieces[-1][1] == len(segment):
                pieces = pieces[:-1]
            if pieces:
                candidates.append(segment[pieces[0][0] : pieces[-1][1]])
                candidates.extend(segment[left:right] for left, right in pieces)
        start = breaker.end()
        unsafe_left = breaker.group() in ("*", "?")
    return tuple(
        sorted(dict.fromkeys(term for term in candidates if len(term) >= 4), key=len, reverse=True)[
            :2
        ]
    )


def _copy_kinds(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        kind: {
            "requests": int(slot["requests"]),
            "seconds": round(float(slot["seconds"]), 3),
            "censored": int(slot.get("censored", 0)),
        }
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


# effort budget: positive-scored observations of one host-hour passed to episode grouping
SEEDS_PER_HOST_HOUR = 12


def _judge_stopped(search: Search) -> bool:
    budget = getattr(search, "budget", None)
    remaining = getattr(budget, "remaining", None)
    if not callable(remaining):
        return False
    return bool(remaining() <= 0)


def _publish_order(search: Search, rows: list[dict[str, Any]], block: dict[str, Any]) -> None:
    budget = getattr(search, "budget", None)
    if budget is None:
        return
    from portal.modules.security.core.hunt.order import host_hour_record

    budget.host_hours = [host_hour_record(row) for row in rows]
    budget.judge_block = dict(block)
    budget.judge_requests = int(block.get("requests", 0))
    budget.judge_seconds = float(block.get("seconds", 0.0))


def _host_hour_rows(
    search: Search,
    index: str,
    start: float,
    end: float,
    ordered: list[Any],
    judge: JudgeClient | None,
    judge_model: str | None,
    renames: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Final host-hour order. Unconfigured and stopped judges say so and do not score."""
    from portal.modules.security.core.hunt.evidence import (
        JUDGE_CELLS,
        MAX_EVENT_CHARACTERS,
    )
    from portal.modules.security.core.hunt.order import accumulated_rows, rank_from_observations

    if judge is None or not judge_model:
        return accumulated_rows(ordered, "judge_not_configured"), {"configured": False}
    if _judge_stopped(search):
        return accumulated_rows(ordered, "job_deadline_exceeded"), {
            "configured": True,
            "requests": 0,
            "seconds": 0.0,
            "order": "fused",
        }
    executor = getattr(search, "executor", None)
    if executor is None:
        return accumulated_rows(ordered, "no_budgeted_executor"), {
            "configured": True,
            "reason": "no_budgeted_executor",
        }
    ranked = rank_from_observations(
        ordered,
        executor,
        index,
        start,
        end,
        judge,
        judge_model,
        budget_order="accumulated",
        judge_cells=JUDGE_CELLS,
        order_mode="fused",
        evidence_mode="rarest",
        event_chars=MAX_EVENT_CHARACTERS,
        stop=lambda: _judge_stopped(search),
        renames=renames,
    )
    cost = ranked["judge_cost"]
    return ranked["leads"], {
        "configured": True,
        "requests": cost["requests"],
        "seconds": cost["seconds"],
        "served": sorted(ranked["served_models"]),
        "order": "fused",
    }


def _episode_hours(episode: Any) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for obs in episode.observations:
        key = (obs.host, obs.hour)
        if key not in seen:
            seen.add(key)
            found.append(key)
    return found


def _order_leads(episodes: list[Any], leads: list[Lead], rows: list[dict[str, Any]]) -> list[Lead]:
    """Best host-hour position first. Equal positions keep the episode order."""
    from portal.modules.security.core.hunt.order import best_host_hour, order_group_indexes

    groups = [_episode_hours(episode) for episode in episodes]
    info = {(str(row["host"]), int(row["hour"])): row for row in rows}
    ordered: list[Lead] = []
    for index in order_group_indexes(groups, rows):
        lead = leads[index]
        key = best_host_hour(groups[index], rows)
        row = None if key is None else info.get(key)
        if row is not None:
            lead.risk = float(row["risk"])
            lead.acc_rank = int(row["acc_rank"])
            lead.p_yes = None if row["p_yes"] is None else float(row["p_yes"])
        ordered.append(lead)
    return ordered


def _discover_renames(search: Search) -> dict[str, str]:
    """Live props.conf renames; a failed read or a bare test double degrades to none."""
    from portal.modules.security.core.hunt.executor import executor_for
    from portal.modules.security.core.hunt.notables.sample import sourcetype_renames

    try:
        found, _notes = sourcetype_renames(executor_for(search))
    except Exception:
        return {}
    return found


def hunt(
    search: Search,
    index: str,
    start: float,
    end: float,
    *,
    candidates: int = 15,
    judge: JudgeClient | None = None,
    judge_model: str | None = None,
    renames: Mapping[str, str] | None = None,
) -> list[Lead]:
    """Seeds are host-hours. `candidates` bounds how many host-hours are investigated."""
    from portal.modules.security.core.hunt.episodes import accumulate, to_lead
    from portal.modules.security.core.hunt.observations import observe
    from portal.modules.security.core.hunt.order import positive_seeds

    resolved_renames = renames if renames is not None else _discover_renames(search)
    run = observe(search, index, start, end, baseline="current", renames=resolved_renames)
    ordered = list(run.observations)
    rows, block = _host_hour_rows(
        search, index, start, end, ordered, judge, judge_model, resolved_renames
    )
    seeds = positive_seeds(ordered, rows, candidates, SEEDS_PER_HOST_HOUR)
    place = {
        (obs.kind, obs.host, obs.entity, obs.hour, str(obs.evidence.get("signal", ""))): index
        for index, obs in enumerate(ordered)
    }
    episodes = accumulate(seeds, ordered, place)
    leads = _order_leads(episodes, [to_lead(episode, place) for episode in episodes], rows)
    investigated = {
        (row["kind"], row["host"], row["entity"], row["hour"])
        for lead in leads
        for row in lead.observations
    }
    _record(search, run, investigated)
    _publish_order(search, rows, block)
    if _budget_stopped(run):
        raise SearchBudgetExceededError("observation_budget_exhausted")
    return leads


def epoch(day_hour: str) -> int:
    return calendar.timegm(time.strptime(day_hour, "%Y-%m-%d %H"))
