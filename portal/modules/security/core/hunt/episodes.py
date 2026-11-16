"""Group seed observations into episodes. No searches and no score cut-off.

A host's seeds form a run while each next hour is the same bucket or the next one.
Hosts that share one learned key=value in the same hour join one episode. Order is
distinct kinds, then distinct hosts, then the strongest seed's place in the
observation total order, then start hour and host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from portal.modules.security.core.hunt.engine import HOUR, Burst, Lead
from portal.modules.security.core.hunt.observations import Observation, _sort_key

_UNSAFE = re.compile(r"[\"\\=\[\]()|,;']")


@dataclass(frozen=True)
class Episode:
    hosts: tuple[str, ...]
    start: int
    end: int
    observations: tuple[Observation, ...]


def _ident(obs: Observation) -> tuple[str, str, str, int, str]:
    return (obs.kind, obs.host, obs.entity, obs.hour, str(obs.evidence.get("signal", "")))


def _runs(rows: list[Observation]) -> list[list[Observation]]:
    ordered = sorted(rows, key=lambda obs: (obs.hour, obs.kind, obs.entity))
    runs: list[list[Observation]] = []
    current: list[Observation] = []
    last: int | None = None
    for obs in ordered:
        if last is not None and obs.hour > last + HOUR:
            runs.append(current)
            current = []
        current.append(obs)
        last = obs.hour
    if current:
        runs.append(current)
    return runs


def _contiguous(seeds: list[Observation]) -> list[list[Observation]]:
    by_host: dict[str, list[Observation]] = {}
    for obs in seeds:
        by_host.setdefault(obs.host, []).append(obs)
    groups: list[list[Observation]] = []
    for host in sorted(by_host):
        groups.extend(_runs(by_host[host]))
    return groups


def _hour_index(groups: list[list[Observation]]) -> dict[tuple[str, int], int]:
    found: dict[tuple[str, int], int] = {}
    for index, group in enumerate(groups):
        for obs in group:
            found.setdefault((obs.host, obs.hour), index)
    return found


def _value_hosts(observations: list[Observation]) -> dict[tuple[str, int], list[str]]:
    found: dict[tuple[str, int], list[str]] = {}
    for obs in observations:
        if obs.kind != "value":
            continue
        hosts = found.setdefault((obs.entity, obs.hour), [])
        if obs.host not in hosts:
            hosts.append(obs.host)
    return found


def _at_hour(observations: list[Observation], host: str, hour: int) -> list[Observation]:
    return [obs for obs in observations if obs.host == host and obs.hour == hour]


def _seeded_values(groups: list[list[Observation]]) -> set[tuple[str, int]]:
    return {(obs.entity, obs.hour) for group in groups for obs in group if obs.kind == "value"}


def _link(
    groups: list[list[Observation]], observations: list[Observation]
) -> list[tuple[int, int]]:
    """Union hosts that share a seed's key=value in one hour. Other hosts join at that hour."""
    index = _hour_index(groups)
    seeded = _seeded_values(groups)
    pairs: list[tuple[int, int]] = []
    for (entity, hour), hosts in _value_hosts(observations).items():
        if (entity, hour) not in seeded or len(hosts) < 2:
            continue
        ids = [_group_for(groups, index, observations, host, hour) for host in sorted(hosts)]
        pairs.extend((ids[0], other) for other in ids[1:])
    return pairs


def _group_for(
    groups: list[list[Observation]],
    index: dict[tuple[str, int], int],
    observations: list[Observation],
    host: str,
    hour: int,
) -> int:
    found = index.get((host, hour))
    if found is not None:
        return found
    groups.append(_at_hour(observations, host, hour))
    index[(host, hour)] = len(groups) - 1
    return len(groups) - 1


def _find(parent: list[int], item: int) -> int:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _merge(groups: list[list[Observation]], pairs: list[tuple[int, int]]) -> list[Episode]:
    parent = list(range(len(groups)))
    for left, right in pairs:
        root_left, root_right = _find(parent, left), _find(parent, right)
        if root_left != root_right:
            parent[root_right] = root_left
    buckets: dict[int, dict[tuple[str, str, str, int, str], Observation]] = {}
    for index, group in enumerate(groups):
        slot = buckets.setdefault(_find(parent, index), {})
        for obs in group:
            slot[_ident(obs)] = obs
    episodes: list[Episode] = []
    for slot in buckets.values():
        rows = tuple(sorted(slot.values(), key=_sort_key))
        hosts = tuple(sorted({obs.host for obs in rows}))
        hours = [obs.hour for obs in rows]
        episodes.append(Episode(hosts, min(hours), max(hours), rows))
    return episodes


def _rank(
    episode: Episode, place: dict[tuple[str, str, str, int, str], int]
) -> tuple[int, int, int, int, str]:
    """More kinds, then more hosts, then the strongest seed, then time and host."""
    kinds = len({obs.kind for obs in episode.observations})
    best = min(place.get(_ident(obs), len(place)) for obs in episode.observations)
    return (-kinds, -len(episode.hosts), best, episode.start, episode.hosts[0])


def accumulate(
    seeds: list[Observation],
    observations: list[Observation],
    place: dict[tuple[str, str, str, int, str], int],
) -> list[Episode]:
    """Ranked episodes for one seed list. `place` is the observation total order."""
    groups = _contiguous(seeds)
    if not groups:
        return []
    return sorted(_merge(groups, _link(groups, observations)), key=lambda ep: _rank(ep, place))


def _burst_token(entity: str, score: float | None) -> str | None:
    value = entity.split("=", 1)[-1]
    if score is None or score <= 0 or len(value) < 4 or _UNSAFE.search(value):
        return None
    return value


def _bursts(observations: tuple[Observation, ...] | list[Observation]) -> list[Burst]:
    found: list[Burst] = []
    seen: set[str] = set()
    for obs in observations:
        if obs.kind != "value":
            continue
        token = _burst_token(obs.entity, obs.score)
        if token is None or token in seen:
            continue
        seen.add(token)
        found.append(
            Burst(
                token,
                int(obs.evidence.get("now") or 0),
                float(obs.evidence.get("prior_median") or 0.0),
                int(obs.evidence.get("prior_hours_active") or 0),
                float(obs.score or 0.0),
            )
        )
    found.sort(key=lambda burst: (-burst.z, burst.token))
    return found


def _sources(observations: list[Observation], host: str, hour: int) -> list[str]:
    found: list[str] = []
    for obs in observations:
        if obs.kind != "source" or obs.host != host or obs.hour != hour:
            continue
        source = obs.entity.split("\t", 1)[0]
        if source and source not in found:
            found.append(source)
    return found


def _templates(observations: list[Observation], host: str) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for obs in observations:
        if obs.kind != "shape" or obs.host != host:
            continue
        count = int(obs.evidence.get("now") or 0)
        # Shape grids are host x punct, so a seed with no source is host + literal punct.
        sources = _sources(observations, host, obs.hour) or [""]
        for source in sources:
            found.append((source, obs.entity, count))
    return found


def _evidence(obs: Observation) -> dict[str, Any]:
    return {
        "kind": obs.kind,
        "host": obs.host,
        "entity": obs.entity,
        "hour": obs.hour,
        "score": obs.score,
        "signal": obs.evidence.get("signal"),
        "now": obs.evidence.get("now"),
        "literal": obs.evidence.get("literal"),
    }


def to_lead(episode: Episode, place: dict[tuple[str, str, str, int, str], int]) -> Lead:
    """One episode, one lead: the strongest seed's host, the run's own window."""
    rows = list(episode.observations)
    best = min(rows, key=lambda obs: (place.get(_ident(obs), len(place)), obs.host))
    score = float(best.score or 0.0)
    return Lead(
        episode.start,
        best.host,
        score,
        len(episode.hosts),
        _templates(rows, best.host),
        _bursts(rows),
        score,
        episode.end - episode.start + HOUR,
        [_evidence(obs) for obs in rows],
    )
