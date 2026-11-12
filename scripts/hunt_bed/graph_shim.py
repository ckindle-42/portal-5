"""Stand-in graph and executor for the graph runner: replaced when those two lanes are merged."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from portal.modules.security.core.hunt.engine import (
    HOUR,
    SearchBudgetExceededError,
    SearchCoverageCensoredError,
    SearchQueryBoundError,
)
from portal.modules.security.core.hunt.jobs import HuntSearchFailedError
from portal.modules.security.core.hunt.observations import budgeted_search
from portal.modules.security.core.review.window import SplunkWindowSource

# Placeholder value notion: the repository's token pattern, with `key=` structure dropped.
_VALUE = re.compile(r"[A-Za-z0-9_.:/@%\-]{4,}(?!=)")


def values(raw: str) -> list[str]:
    """Entity values in one raw event, first-occurrence order, no repeats."""
    return list(dict.fromkeys(_VALUE.findall(raw)))


@dataclass
class Graph:
    links: dict[str, set[str]]
    cells: dict[str, dict[tuple[str, str, int], int]]


def build(samples: Mapping[tuple[str, str, int], list[dict[str, Any]]]) -> Graph:
    """Link values that share an event; count each value per (host, source, hour)."""
    links: dict[str, set[str]] = {}
    cells: dict[str, dict[tuple[str, str, int], int]] = {}
    for (host, source, hour), events in samples.items():
        for event in events:
            found = values(str(event.get("_raw", "")))
            for value in found:
                seen = cells.setdefault(value, {})
                seen[(host, source, hour)] = seen.get((host, source, hour), 0) + 1
                links.setdefault(value, set()).update(other for other in found if other != value)
    return Graph(links, cells)


@dataclass
class Notable:
    entity: str
    score: float
    observations: list[dict[str, Any]] = field(default_factory=list)
    hosts: dict[str, int] = field(default_factory=dict)
    first: int = 0
    last: int = 0
    neighbours: list[str] = field(default_factory=list)
    cells: dict[str, int] = field(default_factory=dict)

    def as_lead(self) -> dict[str, Any]:
        host = min(self.hosts, key=lambda name: (-self.hosts[name], name))
        return {
            "host": host,
            "hour": self.first,
            "span": max(HOUR, self.last - self.first + HOUR),
            "score": round(self.score, 4),
            "entity": self.entity,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.as_lead(),
            "observations": self.observations,
            "hosts": dict(sorted(self.hosts.items())),
            "neighbours": self.neighbours,
            "cells": self.cells,
        }


def _named(obs: Any) -> list[str]:
    if obs.kind == "volume":
        return [obs.host]
    if obs.kind == "value":
        return [obs.entity.split("=", 1)[-1]]
    return [part for part in obs.entity.split("\t") if part]


def _notable(name: str, slot: dict[str, Any], graph: Graph) -> Notable:
    # The lead window is the observed deviation window: baseline cells never stretch it.
    hours = [int(row["hour"]) for row in slot["observations"]]
    cells = {
        f"{host}|{source}|{hour}": count
        for (host, source, hour), count in graph.cells.get(name, {}).items()
    }
    return Notable(
        entity=name,
        score=float(slot["score"]),
        observations=list(slot["observations"]),
        hosts=dict(slot["hosts"]),
        first=min(hours),
        last=max(hours),
        neighbours=sorted(graph.links.get(name, ())),
        cells=cells,
    )


def notables(graph: Graph, observations: list[Any]) -> list[Notable]:
    """Entities a deviation was observed on, ranked by accumulated deviation, no cut-off."""
    found: dict[str, dict[str, Any]] = {}
    for obs in observations:
        for name in _named(obs):
            slot = found.setdefault(name, {"score": 0.0, "hosts": {}, "observations": []})
            slot["score"] += float(obs.score or 0.0)
            slot["hosts"][obs.host] = slot["hosts"].get(obs.host, 0) + 1
            slot["observations"].append(
                {
                    "kind": obs.kind,
                    "host": obs.host,
                    "entity": obs.entity,
                    "hour": obs.hour,
                    "score": obs.score,
                    "signal": obs.evidence.get("signal"),
                }
            )
    rows = [_notable(name, slot, graph) for name, slot in found.items()]
    rows.sort(key=lambda row: (-row.score, -len(row.observations), -len(row.hosts), row.entity))
    return rows


@dataclass
class Read:
    rows: list[dict[str, Any]]
    censored: bool
    reason: str | None


_SEARCH: Any = None


def _budgeted() -> Any:
    global _SEARCH
    if _SEARCH is None:
        window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
        _SEARCH = budgeted_search(window)
        _SEARCH.budget.phase = "investigating"  # a raw evidence read is the events budget kind
    return _SEARCH


def read(query: str, start: float, end: float, *, kind: str, row_cap: int) -> Read:
    """One bounded raw read; a stopped, failed or over-cap read is censored, never trusted."""
    rows: list[dict[str, Any]] = []
    search = _budgeted()
    try:
        for row in search.iter_post(query, start, end):
            rows.append({k: (v[0] if isinstance(v, list) and v else v) for k, v in row.items()})
            if len(rows) >= row_cap:
                return Read(rows, True, "row_cap")
    except SearchQueryBoundError:
        return Read(rows, True, "query_bound")
    except SearchCoverageCensoredError:
        return Read(rows, True, "censored")
    except SearchBudgetExceededError as exc:
        return Read(rows, True, str(exc) or "budget")
    except HuntSearchFailedError:
        return Read(rows, True, "search_failed")
    return Read(rows, False, None)
