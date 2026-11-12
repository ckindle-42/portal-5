"""Schema-free entity graph: values, co-occurrence edges, deviations, accumulation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from portal.modules.security.core.hunt.baselines import peer_proportion
from portal.modules.security.core.hunt.engine import HOUR, _burst
from portal.modules.security.core.hunt.observations import Observation

Cell = tuple[str, str, int]
Pair = tuple[str, str]

# Effort budget: distinct values read from one event.
MAX_VALUES_PER_EVENT = 64
# Effort budget: co-occurrence edges linked from one event.
MAX_EDGES_PER_EVENT = 512

# Splunk Enterprise 9.4 segmenters.conf [default] MAJOR, spec version 9.4.0.
# https://docs.splunk.com/Documentation/Splunk/9.4.1/Admin/Segmentersconf
_MAJOR_SPEC = r"""[ ] < > ( ) { } | ! ; , ' " * \n \r \s \t & ? + %21 %26 %2526 %3B %7C %20 %2B %3D -- %2520 %5D %5B %3A %0A %2C %28 %29"""
_ESCAPES = {"\\n": "\n", "\\r": "\r", "\\s": " ", "\\t": "\t"}
_MAJOR_BREAKERS = tuple(_ESCAPES.get(token, token) for token in _MAJOR_SPEC.split())
_BREAKER = re.compile(
    "|".join(re.escape(item) for item in sorted(_MAJOR_BREAKERS, key=len, reverse=True))
)


def values(raw: str) -> list[str]:
    """The major segments of `raw`, in appearance order. Repeats are kept."""
    return [piece for piece in _BREAKER.split(raw) if piece]


@dataclass(frozen=True)
class EventRef:
    host: str
    source: str
    time: float

    def as_dict(self) -> dict[str, Any]:
        return {"host": self.host, "source": self.source, "time": self.time}


@dataclass
class Node:
    value: str
    hours: dict[int, int] = field(default_factory=dict)
    hosts: dict[str, int] = field(default_factory=dict)
    degree: dict[int, int] = field(default_factory=dict)
    events: dict[int, list[EventRef]] = field(default_factory=dict)


@dataclass
class Edge:
    left: str
    right: str
    hours: dict[int, int] = field(default_factory=dict)
    hosts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Truncation:
    kind: str
    events: int
    dropped: int

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "events": self.events, "dropped": self.dropped}


@dataclass
class Graph:
    nodes: dict[str, Node]
    edges: dict[Pair, Edge]
    adjacency: dict[str, set[str]]
    truncations: dict[str, Truncation]

    def neighbours(self, value: str) -> set[str]:
        return set(self.adjacency.get(value, ()))

    def edge_weight(self, value: str, other: str) -> int:
        return sum(_edge(self.edges, value, other).hours.values())


def _edge(edges: Mapping[Pair, Edge], left: str, right: str) -> Edge:
    return edges[(left, right) if left < right else (right, left)]


def _time(event: Mapping[str, Any], hour: int) -> float:
    try:
        return float(event.get("_time", hour))
    except (TypeError, ValueError):
        return float(hour)


def _bump(truncations: dict[str, list[int]], kind: str, dropped: int) -> None:
    slot = truncations.setdefault(kind, [0, 0])
    slot[0] += 1
    slot[1] += dropped


def _distinct(raw: str) -> list[str]:
    seen: set[str] = set()
    found: list[str] = []
    for value in values(raw):
        if value not in seen:
            seen.add(value)
            found.append(value)
    return found


def _link(
    nodes: dict[str, Node],
    edges: dict[Pair, Edge],
    adjacency: dict[str, set[str]],
    pair: Pair,
    hour: int,
    host: str,
) -> None:
    key = (pair[0], pair[1]) if pair[0] < pair[1] else (pair[1], pair[0])
    edge = edges.setdefault(key, Edge(key[0], key[1]))
    edge.hours[hour] = edge.hours.get(hour, 0) + 1
    edge.hosts[host] = edge.hosts.get(host, 0) + 1
    adjacency.setdefault(key[0], set()).add(key[1])
    adjacency.setdefault(key[1], set()).add(key[0])


def _pairs(found: list[str], limit: int) -> Iterable[Pair]:
    kept = 0
    for left in range(len(found)):
        for right in range(left + 1, len(found)):
            if kept >= limit:
                return
            kept += 1
            yield found[left], found[right]


def _record_event(
    nodes: dict[str, Node],
    edges: dict[Pair, Edge],
    adjacency: dict[str, set[str]],
    truncations: dict[str, list[int]],
    cell: Cell,
    event: Mapping[str, Any],
) -> None:
    host, source, hour = cell
    found = _distinct(str(event.get("_raw", "")))
    if len(found) > MAX_VALUES_PER_EVENT:
        _bump(truncations, "values", len(found) - MAX_VALUES_PER_EVENT)
        found = found[:MAX_VALUES_PER_EVENT]
    ref = EventRef(host, source, _time(event, hour))
    for value in found:
        node = nodes.setdefault(value, Node(value))
        node.hours[hour] = node.hours.get(hour, 0) + 1
        node.hosts[host] = node.hosts.get(host, 0) + 1
        node.events.setdefault(hour, []).append(ref)
    possible = len(found) * (len(found) - 1) // 2
    if possible > MAX_EDGES_PER_EVENT:
        _bump(truncations, "edges", possible - MAX_EDGES_PER_EVENT)
    for pair in _pairs(found, MAX_EDGES_PER_EVENT):
        _link(nodes, edges, adjacency, pair, hour, host)


def _degree(nodes: Mapping[str, Node], edges: Mapping[Pair, Edge]) -> None:
    for (left, right), edge in edges.items():
        for hour in edge.hours:
            for value in (left, right):
                nodes[value].degree[hour] = nodes[value].degree.get(hour, 0) + 1


def build(cells: Mapping[Cell, Iterable[Mapping[str, Any]]]) -> Graph:
    """Build the graph from bounded event samples; a cell owns its host, source and hour."""
    nodes: dict[str, Node] = {}
    edges: dict[Pair, Edge] = {}
    adjacency: dict[str, set[str]] = {}
    truncations: dict[str, list[int]] = {}
    for host, source, hour in sorted(cells):
        for event in cells[(host, source, hour)]:
            _record_event(nodes, edges, adjacency, truncations, (host, source, hour), event)
    _degree(nodes, edges)
    recorded = {kind: Truncation(kind, slot[0], slot[1]) for kind, slot in truncations.items()}
    return Graph(nodes, edges, adjacency, recorded)


@dataclass(frozen=True)
class Deviation:
    entity: str
    hour: int
    first_seen: bool
    volume: int
    volume_z: float | None
    prior_volume_median: float | None
    prior_hours_active: int
    degree: int
    degree_z: float | None
    new_edges: tuple[str, ...]
    peer_volume: float | None
    peer_degree: float | None
    hosts: tuple[tuple[str, int], ...]
    cells: tuple[Pair, ...]

    @property
    def signals(self) -> tuple[str, ...]:
        found: list[str] = []
        if self.volume_z is not None and self.volume_z > 0:
            found.append("volume")
        if self.degree_z is not None and self.degree_z > 0:
            found.append("degree")
        if self.new_edges:
            found.append("new_edge")
        return tuple(found)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "hour": self.hour,
            "first_seen": self.first_seen,
            "volume": self.volume,
            "volume_z": self.volume_z,
            "prior_volume_median": self.prior_volume_median,
            "prior_hours_active": self.prior_hours_active,
            "degree": self.degree,
            "degree_z": self.degree_z,
            "new_edges": list(self.new_edges),
            "peer_volume": self.peer_volume,
            "peer_degree": self.peer_degree,
            "hosts": [{"host": host, "count": count} for host, count in self.hosts],
            "cells": [{"host": host, "source": source} for host, source in self.cells],
            "signals": list(self.signals),
        }


def _peers(graph: Graph, value: str) -> set[str]:
    found: set[str] = set()
    for neighbour in graph.adjacency.get(value, ()):
        found.update(graph.adjacency.get(neighbour, ()))
    found.discard(value)
    return found


def _host_cells(
    refs: Iterable[EventRef],
) -> tuple[tuple[tuple[str, int], ...], tuple[Pair, ...]]:
    hosts: dict[str, int] = {}
    cells: set[Pair] = set()
    for ref in refs:
        hosts[ref.host] = hosts.get(ref.host, 0) + 1
        cells.add((ref.host, ref.source))
    ordered = tuple(sorted(hosts.items(), key=lambda item: (-item[1], item[0])))
    return ordered, tuple(sorted(cells))


def _new_edges(graph: Graph, value: str, hour: int) -> tuple[str, ...]:
    found: list[str] = []
    for other in graph.adjacency.get(value, ()):
        edge = _edge(graph.edges, value, other)
        if edge.hours.get(hour, 0) and min(edge.hours) == hour:
            found.append(other)
    return tuple(sorted(found))


def _deviation(
    graph: Graph,
    node: Node,
    hour: int,
    first_seen: bool,
    peers: set[str],
    active: set[str],
    volumes: Mapping[str, int],
    degrees: Mapping[str, int],
) -> Deviation:
    volume = node.hours[hour]
    degree = node.degree.get(hour, 0)
    volume_burst = None if first_seen else _burst(node.value, hour, node.hours)
    degree_burst = None if first_seen else _burst(node.value, hour, node.degree)
    shared = peers & active
    hosts, cells = _host_cells(node.events.get(hour, ()))
    return Deviation(
        entity=node.value,
        hour=hour,
        first_seen=first_seen,
        volume=volume,
        volume_z=None if volume_burst is None else volume_burst.z,
        prior_volume_median=None if volume_burst is None else volume_burst.prior_median,
        prior_hours_active=0 if volume_burst is None else volume_burst.prior_hours_active,
        degree=degree,
        degree_z=None if degree_burst is None else degree_burst.z,
        new_edges=() if first_seen else _new_edges(graph, node.value, hour),
        peer_volume=peer_proportion(volume, node.value, volumes, shared),
        peer_degree=peer_proportion(degree, node.value, degrees, shared),
        hosts=hosts,
        cells=cells,
    )


def _entity_deviations(
    graph: Graph,
    node: Node,
    active: Mapping[int, set[str]],
    volumes: Mapping[int, Mapping[str, int]],
    degrees: Mapping[int, Mapping[str, int]],
) -> list[Deviation]:
    origin = min(node.hours)
    peers = _peers(graph, node.value)
    return [
        _deviation(
            graph, node, hour, hour == origin, peers, active[hour], volumes[hour], degrees[hour]
        )
        for hour in sorted(node.hours)
    ]


def _hour_counts(
    graph: Graph,
) -> tuple[dict[int, set[str]], dict[int, dict[str, int]], dict[int, dict[str, int]]]:
    active: dict[int, set[str]] = {}
    volumes: dict[int, dict[str, int]] = {}
    degrees: dict[int, dict[str, int]] = {}
    for value, node in graph.nodes.items():
        for hour, count in node.hours.items():
            active.setdefault(hour, set()).add(value)
            volumes.setdefault(hour, {})[value] = count
            degrees.setdefault(hour, {})[value] = node.degree.get(hour, 0)
    return active, volumes, degrees


def deviations(graph: Graph) -> list[Deviation]:
    """One record per entity-hour, ordered by (entity, hour); first-seen hours are flagged."""
    active, volumes, degrees = _hour_counts(graph)
    found: list[Deviation] = []
    for value in sorted(graph.nodes):
        found.extend(_entity_deviations(graph, graph.nodes[value], active, volumes, degrees))
    return found


@dataclass(frozen=True)
class Notable:
    entity: str
    deviations: tuple[Deviation, ...]
    host_hours: tuple[tuple[str, int, int], ...]
    events: tuple[dict[str, Any], ...]
    observations: tuple[dict[str, Any], ...]
    neighbours: tuple[tuple[str, int], ...]
    cells: int
    hosts: int
    hours: int
    signals: tuple[str, ...]
    new_edges: int
    strength: float

    def as_lead(self) -> dict[str, Any]:
        """Strongest deviation's dominant host-hour, with the whole accumulation attached."""
        best = min(self.deviations, key=_best)
        return {
            "entity": self.entity,
            "host": best.hosts[0][0] if best.hosts else "",
            "hour": best.hour,
            "span": HOUR,
            "score": self.strength,
            "cells": self.cells,
            "hosts": self.hosts,
            "hours": self.hours,
            "signals": list(self.signals),
            "new_edges": self.new_edges,
            "host_hours": [
                {"host": host, "hour": hour, "span": span} for host, hour, span in self.host_hours
            ],
            "neighbours": [{"value": value, "count": count} for value, count in self.neighbours],
            "observations": [dict(row) for row in self.observations],
            "events": [dict(row) for row in self.events],
            "deviations": [dev.as_dict() for dev in self.deviations],
        }


def _best(dev: Deviation) -> tuple[float, float, int, int, str]:
    return (
        -(dev.volume_z or 0.0),
        -(dev.degree_z or 0.0),
        -len(dev.new_edges),
        dev.hour,
        dev.hosts[0][0] if dev.hosts else "",
    )


def _backs(obs: Observation, dev: Deviation) -> bool:
    return obs.hour == dev.hour and obs.host in {host for host, _count in dev.hosts}


def _backing(
    rows: list[Deviation], observations: Iterable[Observation]
) -> tuple[dict[str, Any], ...]:
    found: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
    for obs in observations:
        if not any(_backs(obs, dev) for dev in rows):
            continue
        ident = (obs.kind, obs.host, obs.entity, obs.hour, str(obs.evidence.get("signal", "")))
        found.setdefault(ident, obs.as_dict())
    ordered = sorted(
        found.values(),
        key=lambda row: (
            row["hour"],
            row["host"],
            row["kind"],
            row["entity"],
            str(row["evidence"].get("signal", "")),
        ),
    )
    return tuple(ordered)


def _neighbours(graph: Graph, entity: str) -> tuple[tuple[str, int], ...]:
    found = [(other, graph.edge_weight(entity, other)) for other in graph.adjacency.get(entity, ())]
    return tuple(sorted(found, key=lambda item: (-item[1], item[0])))


def _notable(
    graph: Graph, entity: str, rows: list[Deviation], observations: Iterable[Observation]
) -> Notable:
    host_hours = tuple((host, dev.hour, HOUR) for dev in rows for host, _count in dev.hosts)
    refs: dict[tuple[float, str, str], EventRef] = {}
    for dev in rows:
        for ref in graph.nodes[entity].events.get(dev.hour, ()):
            refs[(ref.time, ref.host, ref.source)] = ref
    cells = {(host, source) for dev in rows for host, source in dev.cells}
    strength = sum(max(dev.volume_z or 0.0, 0.0) + max(dev.degree_z or 0.0, 0.0) for dev in rows)
    return Notable(
        entity=entity,
        deviations=tuple(rows),
        host_hours=host_hours,
        events=tuple(refs[key].as_dict() for key in sorted(refs)),
        observations=_backing(rows, observations),
        neighbours=_neighbours(graph, entity),
        cells=len(cells),
        hosts=len({host for host, _hour, _span in host_hours}),
        hours=len({dev.hour for dev in rows}),
        signals=tuple(sorted({signal for dev in rows for signal in dev.signals})),
        new_edges=sum(len(dev.new_edges) for dev in rows),
        strength=round(strength, 9),
    )


def _rank(notable: Notable) -> tuple[int, int, int, int, int, float, str]:
    return (
        -notable.cells,
        -notable.hosts,
        -notable.hours,
        -len(notable.signals),
        -notable.new_edges,
        -notable.strength,
        notable.entity,
    )


def notables(graph: Graph, observations: Iterable[Observation]) -> list[Notable]:
    """Entities with a non-first-seen deviation, ranked by convergence: distinct (host,
    source) cells, then hosts, hours, signal kinds, new edges, positive burst z, entity."""
    obs = list(observations)
    grouped: dict[str, list[Deviation]] = {}
    for dev in deviations(graph):
        if not dev.first_seen and dev.signals:
            grouped.setdefault(dev.entity, []).append(dev)
    found = [_notable(graph, entity, rows, obs) for entity, rows in sorted(grouped.items())]
    return sorted(found, key=_rank)
