"""Resolve ranked source anomalies into observed actor/action activity inside their window."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote

from ..executor import HuntExecutor
from .behaviours import BEHAVIOUR_EVENTS_PER_WINDOW, _extract, per_window_events
from .cards import SourceCard, card_consumers
from .generators import Notable, _make
from .sample import BEHAVIOUR_SOURCES, SourceFacts, read_windows

REVIEW_HEAD = 50  # effort budget: resolve source anomalies in the ranked review head
WINDOW_SUB_WINDOWS = 4  # read across the whole four-hour anomaly, not only its tail
BURST_SLICE_SECONDS = 300.0  # five-minute slices to find the densest burst inside a window
_PCT_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")
Group = tuple[str, str, str, str, str]
Observation = tuple[float, str, str]


def _role(fields: Mapping[str, str], names: Sequence[str]) -> tuple[str, str]:
    return next(((name, fields[name]) for name in names if fields.get(name)), ("", ""))


def _readable(value: str) -> str:
    return unquote(value) if _PCT_ENCODED.search(value) else value


def _object_fields(card: SourceCard) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*card.role_fields("object"), *card.role_fields("to"))))


def _groups(
    cards: Sequence[SourceCard], rows: Sequence[Mapping[str, Any]], window: tuple[float, float]
) -> dict[Group, dict[int, Observation]]:
    found: dict[Group, dict[int, Observation]] = defaultdict(dict)
    for card in cards:
        events, matched, _ = _extract(card, rows, [window])
        actor_fields = (*card.role_fields("actor"), *card.role_fields("from"))
        action_fields = card.role_fields("action")
        obj_fields = _object_fields(card)
        for index, event in zip(sorted(matched), events, strict=True):
            if not window[0] <= event.ts < window[1]:
                continue
            actor_field, actor = _role(event.fields, actor_fields)
            action_field, action = _role(event.fields, action_fields)
            if not actor and not obj_fields:
                continue
            for name in obj_fields:
                if value := event.fields.get(name):
                    found[actor_field, actor, action_field, action, name][index] = (
                        event.ts,
                        value,
                        event.raw,
                    )
    return found


def _representative_observations(observations: Sequence[Observation]) -> list[Observation]:
    """Earliest, latest, densest five-minute burst slice, and most frequent object."""
    first, last = min(observations), max(observations)
    by_slice: dict[int, list[Observation]] = defaultdict(list)
    val_counts: dict[str, int] = defaultdict(int)
    val_first: dict[str, Observation] = {}
    for obs in observations:
        by_slice[int(obs[0] // BURST_SLICE_SECONDS)].append(obs)
        val_counts[obs[1]] += 1
        if obs[1] not in val_first or obs[0] < val_first[obs[1]][0]:
            val_first[obs[1]] = obs
    densest = max(by_slice.values(), key=lambda group: (len(group), -group[0][0]))
    peak_obs = min(densest)
    top_val = max(val_counts, key=lambda val: (val_counts[val], val))
    chosen = [first, last]
    seen_raws = {first[2], last[2]}
    for candidate in (peak_obs, val_first[top_val]):
        if candidate[2] not in seen_raws:
            chosen.append(candidate)
            seen_raws.add(candidate[2])
    return chosen


def window_activity(
    seed: Notable, cards: Sequence[SourceCard], rows: Sequence[Mapping[str, Any]], query: str
) -> Notable:
    groups = _groups(cards, rows, (seed.first_seen, seed.last_seen))
    if not groups:
        return seed
    counts = {
        key: len({item[1] for item in observations.values()})
        for key, observations in groups.items()
    }
    key = min(groups, key=lambda k: (-counts[k], -len(groups[k]), k))
    if counts[key] < 2:
        return seed
    actor_field, actor, action_field, action, name = key
    observations = list(groups[key].values())
    ev_items = _representative_observations(observations)
    first, last = ev_items[0], ev_items[1]
    actor_desc = f"{actor_field}={_readable(actor)}" if actor else "unnamed actor"
    action_desc = f" and {action_field}={_readable(action)}" if action else ""
    entities: list[tuple[str, str]] = []
    if actor:
        entities.append(("actor", actor))
    if action:
        entities.append(("action", action))
    for _stamp, val, _raw in ev_items:
        entities.append(("object", val))
    return _make(
        generator=seed.generator,
        basis=f"{seed.basis}_activity",
        what=f"{len(observations)} sampled events with {actor_desc}{action_desc} involved {counts[key]} "
        f"distinct {name} values in the sampled window (first {_readable(first[1])}, last {_readable(last[1])})",
        entities=tuple(entities),
        source_id=seed.source_id,
        first_seen=seed.first_seen,
        last_seen=seed.last_seen,
        counts={
            **seed.counts,
            "sample_rows": len(rows),
            "group_rows": len(observations),
            "distinct_objects": counts[key],
        },
        measure_name=seed.measure_name,
        measure_value=seed.measure_value,
        why=f"{seed.what}. This activity had the most distinct observed objects in the sample.",
        evidence=[
            {
                "line": raw,
                "query": query,
                "earliest": seed.first_seen,
                "latest": seed.last_seen,
                "time": stamp,
            }
            for stamp, _, raw in ev_items
        ]
        + list(seed.evidence),
    )


def resolve_source_windows(
    ranked: list[Notable],
    executor: HuntExecutor,
    cards: Sequence[SourceCard],
    facts: Mapping[str, SourceFacts],
) -> dict[str, Any]:
    sources: dict[str, list[SourceCard]] = defaultdict(list)
    for card in cards:
        if "behaviours" in card_consumers(card):
            sources[card.source_id].append(card)
    cap = min(per_window_events(len(sources)), BEHAVIOUR_EVENTS_PER_WINDOW)
    reads = []
    for position, seed in enumerate(ranked[:REVIEW_HEAD]):
        if seed.basis not in {"source_first_seen", "source_burst"} or seed.source_id not in sources:
            continue
        source = facts[seed.source_id]
        read = read_windows(
            executor,
            source,
            [(seed.first_seen, seed.last_seen)],
            per_window=cap,
            kind="deviation_window",
            max_sources=BEHAVIOUR_SOURCES,
            sub_windows=WINDOW_SUB_WINDOWS,
        )
        ranked[position] = window_activity(seed, sources[seed.source_id], read.rows, read.query)
        reads.append(
            {
                "rank": position + 1,
                "source_id": seed.source_id,
                "rows": len(read.rows),
                "notes": read.notes,
                "resolved": ranked[position] is not seed,
            }
        )
    return {"row_cap": cap, "windows": reads}
