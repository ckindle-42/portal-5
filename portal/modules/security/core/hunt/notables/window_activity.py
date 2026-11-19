"""Resolve ranked source anomalies into observed actor/action activity inside their window."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from ..executor import HuntExecutor
from .behaviours import _extract, per_window_events
from .cards import SourceCard, card_consumers
from .generators import Notable, _make
from .sample import BEHAVIOUR_SOURCES, SourceFacts, read_windows

REVIEW_HEAD = 50  # effort budget: resolve source anomalies in the ranked review head
Group = tuple[str, str, str, str, str]
Observation = tuple[float, str, str]


def _role(fields: Mapping[str, str], names: Sequence[str]) -> tuple[str, str]:
    return next(((name, fields[name]) for name in names if fields.get(name)), ("", ""))


def _groups(
    cards: Sequence[SourceCard], rows: Sequence[Mapping[str, Any]], window: tuple[float, float]
) -> dict[Group, dict[int, Observation]]:
    found: dict[Group, dict[int, Observation]] = defaultdict(dict)
    for card in cards:
        events, matched, _ = _extract(card, rows, [window])
        for index, event in zip(sorted(matched), events, strict=True):
            actor_field, actor = _role(event.fields, card.role_fields("actor"))
            action_field, action = _role(event.fields, card.role_fields("action"))
            if not actor or not action or not window[0] <= event.ts < window[1]:
                continue
            for name in card.role_fields("object"):
                if value := event.fields.get(name):
                    found[actor_field, actor, action_field, action, name][index] = (
                        event.ts,
                        value,
                        event.raw,
                    )
    return found


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
    observations = groups[key].values()
    first, last = min(observations), max(observations)
    return _make(
        generator=seed.generator,
        basis=f"{seed.basis}_activity",
        what=f"{len(observations)} sampled events with {actor_field}={actor} and {action_field}={action} involved {counts[key]} "
        f"distinct {name} values in the sampled window (first {first[1]}, last {last[1]})",
        entities=(("actor", actor), ("action", action), ("object", first[1]), ("object", last[1])),
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
        why=f"{seed.what}. This actor and action had the most distinct observed objects in the sample.",
        evidence=[
            {
                "line": raw,
                "query": query,
                "earliest": seed.first_seen,
                "latest": seed.last_seen,
                "time": stamp,
            }
            for stamp, _, raw in (first, last)
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
    cap = per_window_events(len(sources))
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
