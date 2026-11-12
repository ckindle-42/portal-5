"""Independent notable generators: existing alerts, peer-rare behaviours, deviations."""

from __future__ import annotations

import hashlib
import math
import statistics
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..executor import HuntExecutor
from .behaviours import Behaviour
from .cards import SourceCard
from .parse import parse_row
from .sample import SourceFacts, read_windows, route_filter, window_bounds

NOTABLE_BUDGET = 300  # effort budget: notables kept per generator
ALERT_WINDOWS = 8  # effort budget: time slices read per alert stream
ALERT_EVENTS_PER_WINDOW = 1000  # effort budget: alert events read from one slice
DEVIATION_SOURCE_BUDGET = 100  # effort budget: source-level deviations kept per ordering
DEVIATION_BEHAVIOUR_BUDGET = 100  # effort budget: behaviour-level deviations considered
MIN_SERIES_HOURS = 3  # a deviation needs at least this many observed hours
SERIES_ROWS = 200_000  # effort budget: hourly source-count rows read
MAX_ENTITIES = 8  # effort budget: entities attached to one notable
EVIDENCE_CHARS = 400  # effort budget: raw characters kept on one notable evidence line

GENERATORS = ("alerts", "peer_rare", "deviation")


@dataclass(frozen=True)
class Notable:
    generator: str
    basis: str
    what: str
    entities: tuple[tuple[str, str], ...]
    source_id: str
    first_seen: float
    last_seen: float
    counts: Mapping[str, Any]
    measure_name: str
    measure_value: float
    why: str
    evidence: tuple[Mapping[str, Any], ...]
    content_key: str

    @property
    def notable_id(self) -> str:
        return hashlib.sha1(self.content_key.encode()).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        return {
            "notable_id": self.notable_id,
            "generator": self.generator,
            "basis": self.basis,
            "what": self.what,
            "entities": [{"role": role, "value": value} for role, value in self.entities],
            "source_id": self.source_id,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "counts": dict(self.counts),
            "measure": {"name": self.measure_name, "value": self.measure_value},
            "why": self.why,
            "evidence": [dict(item) for item in self.evidence],
            "content_key": self.content_key,
        }


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _content_key(
    generator: str, what: str, entities: Sequence[tuple[str, str]], source_id: str
) -> str:
    return f"{generator}|{source_id}|{what}|" + "|".join(
        f"{role}={value}" for role, value in entities
    )


def _make(
    *,
    generator: str,
    basis: str,
    what: str,
    entities: Sequence[tuple[str, str]],
    source_id: str,
    first_seen: float,
    last_seen: float,
    counts: Mapping[str, Any],
    measure_name: str,
    measure_value: float,
    why: str,
    evidence: Sequence[Mapping[str, Any]],
) -> Notable:
    shaped = tuple((role, value) for role, value in entities if value)[:MAX_ENTITIES]
    return Notable(
        generator,
        basis,
        what,
        shaped,
        source_id,
        first_seen,
        last_seen,
        counts,
        measure_name,
        measure_value,
        why,
        tuple(evidence),
        _content_key(generator, what, shaped, source_id),
    )


def _first_present(fields: Mapping[str, str], names: Sequence[str]) -> str:
    for name in names:
        value = (fields.get(name) or "").strip()
        if value:
            return value
    return ""


def _term(value: str) -> str:
    return f"TERM({_quote(value)})"


def _alert_query(facts: SourceFacts, action: str, entity: str) -> str:
    route, _ = route_filter(facts)
    terms = " ".join(_term(value) for value in (action, entity) if value)
    tail = f" {terms}" if terms else ""
    return f"search index={_quote(facts.index)} {route}{tail} | head 5"


def _alert_rows(
    executor: HuntExecutor, cards: Sequence[SourceCard], facts_by_source: Mapping[str, SourceFacts]
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Distinct (action, entity) in each alert stream, over a declared slice."""
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    receipts: list[dict[str, Any]] = []
    notes: list[str] = []
    alert_cards = [card for card in cards if card.understood and card.kind == "alert"]
    for card in alert_cards:
        facts = facts_by_source.get(card.source_id)
        if facts is None:
            receipts.append({"source_id": card.source_id, "reason": "no_index_facts"})
            continue
        started = time.monotonic()
        windows = window_bounds(facts.first, facts.last, ALERT_WINDOWS)
        read = read_windows(
            executor, facts, windows, per_window=ALERT_EVENTS_PER_WINDOW, kind="alert_events"
        )
        missing = 0
        for row in read.rows:
            parsed_raw = str(row.get("_raw") or "")
            fields = _alert_fields(card, parsed_raw)
            action = _first_present(fields, card.role_fields("action")) or _first_present(
                fields, card.role_fields("object")
            )
            entity = _first_present(fields, card.role_fields("actor")) or _first_present(
                fields, card.role_fields("to")
            )
            entity = (
                entity
                or _first_present(fields, card.role_fields("from"))
                or str(row.get("host") or "")
            )
            if not action:
                missing += 1
                continue
            key = (card.source_id, action, entity)
            slot = grouped.setdefault(
                key,
                {
                    "count": 0,
                    "first": float("inf"),
                    "last": 0.0,
                    "hosts": set(),
                    "raw": parsed_raw[:EVIDENCE_CHARS],
                    "earliest": None,
                    "latest": None,
                },
            )
            slot["count"] += 1
            try:
                ts = float(row.get("_time") or 0.0)
            except (TypeError, ValueError):
                ts = 0.0
            slot["first"] = min(float(slot["first"]), ts)
            slot["last"] = max(float(slot["last"]), ts)
            slot["hosts"].add(str(row.get("host") or ""))
            hour = ts - ts % 3600.0
            slot["earliest"], slot["latest"] = hour, hour + 3600.0
        receipts.append(
            {
                "source_id": card.source_id,
                "events_available": facts.events,
                "events_read": len(read.rows),
                "events_without_action": missing,
                "windows": read.windows,
                "share_of_source": round(len(read.rows) / facts.events, 6)
                if facts.events
                else None,
                "seconds": round(time.monotonic() - started, 3),
            }
        )
        notes.extend(read.notes)
    return grouped, receipts, notes


def _alert_fields(card: SourceCard, raw: str) -> Mapping[str, str]:
    return parse_row(raw, card.fmt, card.columns).fields


def alerts(
    executor: HuntExecutor, cards: Sequence[SourceCard], facts_by_source: Mapping[str, SourceFacts]
) -> tuple[list[Notable], dict[str, Any]]:
    grouped, receipts, notes = _alert_rows(executor, cards, facts_by_source)
    ordered = sorted(grouped.items(), key=lambda item: (-item[1]["count"], item[0]))
    notables: list[Notable] = []
    for (source_id, action, entity), slot in ordered[:NOTABLE_BUDGET]:
        card_facts = facts_by_source.get(source_id)
        query = _alert_query(card_facts, action, entity) if card_facts else ""
        notables.append(
            _make(
                generator="alerts",
                basis="alert_on_entity",
                what=f"alert {action} on {entity or 'an unnamed entity'}",
                entities=(
                    ("alert", action),
                    ("entity", entity),
                ),
                source_id=source_id,
                first_seen=float(slot["first"]) if slot["first"] != float("inf") else 0.0,
                last_seen=float(slot["last"]),
                counts={
                    "occurrences": slot["count"],
                    "hosts": len(slot["hosts"]),
                },
                measure_name="occurrences",
                measure_value=float(slot["count"]),
                why=f"{slot['count']} occurrences on {len(slot['hosts'])} hosts in the covered slice",
                evidence=(
                    {
                        "line": slot["raw"],
                        "query": query,
                        "earliest": slot["earliest"],
                        "latest": slot["latest"],
                    },
                ),
            )
        )
    return notables, {
        "existed": len(grouped),
        "kept": len(notables),
        "sources": receipts,
        "notes": notes,
    }


def peer_rare(
    behaviours: Sequence[Behaviour], source_stats: Mapping[str, Mapping[str, Any]]
) -> tuple[list[Notable], dict[str, Any]]:
    """Behaviours shared by few hosts and actors, relative to how many could share them."""
    ranked: list[tuple[float, int, str, Behaviour]] = []
    for behaviour in behaviours:
        stats = source_stats.get(behaviour.source_id, {})
        hosts_possible = int(stats.get("hosts_possible") or 0)
        actors_possible = int(stats.get("actors_possible") or 0)
        host_share = behaviour.hosts / hosts_possible if hosts_possible else 1.0
        actor_share = behaviour.actors / actors_possible if actors_possible else 1.0
        measure = round(host_share * actor_share, 10)
        ranked.append((measure, -behaviour.events, behaviour.source_id, behaviour))
    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3].actor, item[3].action))
    notables: list[Notable] = []
    for measure, _events, source_id, behaviour in ranked[:NOTABLE_BUDGET]:
        stats = source_stats.get(source_id, {})
        what = _behaviour_words(behaviour)
        notables.append(
            _make(
                generator="peer_rare",
                basis="behaviour_share",
                what=what,
                entities=(
                    ("actor", behaviour.actor),
                    ("action", behaviour.action),
                    ("object", behaviour.object),
                ),
                source_id=source_id,
                first_seen=behaviour.first_seen,
                last_seen=behaviour.last_seen,
                counts={
                    "events": behaviour.events,
                    "hosts": behaviour.hosts,
                    "actors": behaviour.actors,
                },
                measure_name="host_share_x_actor_share",
                measure_value=measure,
                why=(
                    f"on {behaviour.hosts}/{int(stats.get('hosts_possible') or 0)} hosts and "
                    f"{behaviour.actors}/{int(stats.get('actors_possible') or 0)} actors"
                ),
                evidence=(
                    {
                        "line": behaviour.example_raw,
                        "query": behaviour.example_query,
                        "earliest": behaviour.example_earliest,
                        "latest": behaviour.example_latest,
                    },
                ),
            )
        )
    return notables, {"existed": len(ranked), "kept": len(notables)}


def _behaviour_words(behaviour: Behaviour) -> str:
    parts = []
    if behaviour.actor:
        parts.append(f"actor {behaviour.actor}")
    if behaviour.action:
        parts.append(f"did {behaviour.action}")
    if behaviour.object:
        parts.append(f"to {behaviour.object}")
    return " ".join(parts) or "an unnamed behaviour"


def _robust_z(counts: Sequence[int]) -> tuple[float, int]:
    """The hour most unlike this source's own history, by median/MAD over log counts."""
    logs = [math.log1p(float(value)) for value in counts]
    median = statistics.median(logs)
    mad = statistics.median(abs(value - median) for value in logs)
    scores = [(value - median) / (mad + 0.5) for value in logs]
    peak = max(range(len(scores)), key=lambda index: (scores[index], -index))
    return round(scores[peak], 3), peak


def hourly_series(
    executor: HuntExecutor, index: str, start: float, end: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-source event counts by hour, read from indexed terms only."""
    began = time.monotonic()
    query = f"| tstats count where index={_quote(index)} by sourcetype _time span=1h"
    try:
        result = executor.read(query, start, end, kind="deviation_series", row_cap=SERIES_ROWS)
    except Exception as exc:  # noqa: BLE001 -- a failed series read is declared coverage
        return [], {"error": f"{type(exc).__name__}", "seconds": round(time.monotonic() - began, 3)}
    return [dict(row) for row in result.rows], {
        "requests": 1,
        "rows": len(result.rows),
        "censored": result.reason,
        "seconds": round(time.monotonic() - began, 3),
    }


def _hour(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _series_by_source(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[float, int]]]:
    grouped: dict[str, list[tuple[float, int]]] = {}
    for row in rows:
        name = str(row.get("sourcetype") or "")
        if not name:
            continue
        try:
            count = int(float(row.get("count") or 0))
        except (TypeError, ValueError):
            count = 0
        grouped.setdefault(name, []).append((_hour(row.get("_time")), count))
    for series in grouped.values():
        series.sort()
    return grouped


def _source_deviations(
    grouped: Mapping[str, Sequence[tuple[float, int]]], index: str, index_start: float
) -> tuple[list[Notable], list[Notable], dict[str, Any]]:
    bursts: list[tuple[float, str, float, int]] = []
    firsts: list[tuple[float, str, float]] = []
    for name, series in grouped.items():
        if len(series) >= MIN_SERIES_HOURS:
            z, peak = _robust_z([count for _hour_value, count in series])
            bursts.append((z, name, series[peak][0], series[peak][1]))
        firsts.append((series[0][0] - index_start, name, series[0][0]))
    bursts.sort(key=lambda item: (-item[0], item[1]))
    firsts.sort(key=lambda item: (-item[0], item[1]))
    burst_notables = [
        _make(
            generator="deviation",
            basis="source_burst",
            what=f"source {name} burst to {count} events in one hour",
            entities=(("source", name),),
            source_id=f"{index}:{name}",
            first_seen=hour,
            last_seen=hour + 3600.0,
            counts={"events": count},
            measure_name="robust_z",
            measure_value=value,
            why=f"log count {value} robust deviations above its own hourly median",
            evidence=(
                {
                    "line": f"sourcetype={name} hour={hour:.0f} count={count} z={value}",
                    "query": "",
                    "earliest": hour,
                    "latest": hour + 3600.0,
                },
            ),
        )
        for value, name, hour, count in bursts[:DEVIATION_SOURCE_BUDGET]
    ]
    first_notables = [
        _make(
            generator="deviation",
            basis="source_first_seen",
            what=f"source {name} first appeared {late / 86400.0:.1f} days into the index",
            entities=(("source", name),),
            source_id=f"{index}:{name}",
            first_seen=hour,
            last_seen=hour + 3600.0,
            counts={},
            measure_name="seconds_after_index_start",
            measure_value=round(late, 3),
            why="first hour this source was observed, relative to the index start",
            evidence=(
                {
                    "line": f"sourcetype={name} first_hour={hour:.0f}",
                    "query": "",
                    "earliest": hour,
                    "latest": hour + 3600.0,
                },
            ),
        )
        for late, name, hour in firsts[:DEVIATION_SOURCE_BUDGET]
    ]
    return (
        burst_notables,
        first_notables,
        {
            "sources": len(grouped),
            "bursts": len(bursts),
            "first_seen": len(firsts),
        },
    )


def _behaviour_deviations(
    behaviours: Sequence[Behaviour], index_start: float
) -> tuple[list[Notable], dict[str, Any]]:
    ordered = sorted(
        behaviours,
        key=lambda item: (-item.first_seen, item.source_id, item.actor, item.action, item.object),
    )
    found: list[Notable] = []
    for behaviour in ordered[:DEVIATION_BEHAVIOUR_BUDGET]:
        late = behaviour.first_seen - index_start
        found.append(
            _make(
                generator="deviation",
                basis="behaviour_first_seen",
                what=_behaviour_words(behaviour) + f" first appeared {late / 86400.0:.1f} days in",
                entities=(
                    ("actor", behaviour.actor),
                    ("action", behaviour.action),
                    ("object", behaviour.object),
                ),
                source_id=behaviour.source_id,
                first_seen=behaviour.first_seen,
                last_seen=behaviour.last_seen,
                counts={"events": behaviour.events},
                measure_name="seconds_after_index_start",
                measure_value=round(late, 3),
                why="first hour this behaviour was observed, relative to the index start",
                evidence=(
                    {
                        "line": behaviour.example_raw,
                        "query": behaviour.example_query,
                        "earliest": behaviour.example_earliest,
                        "latest": behaviour.example_latest,
                    },
                ),
            )
        )
    return found, {"existed": len(behaviours), "kept": len(found)}


def _interleave(groups: Sequence[Sequence[Notable]], limit: int) -> list[Notable]:
    kept: list[Notable] = []
    index = 0
    while len(kept) < limit and any(index < len(group) for group in groups):
        for group in groups:
            if index < len(group) and len(kept) < limit:
                kept.append(group[index])
        index += 1
    return kept


def generate(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    cards: Sequence[SourceCard],
    facts_by_source: Mapping[str, SourceFacts],
    behaviours: Sequence[Behaviour],
    source_stats: Mapping[str, Mapping[str, Any]],
    enabled: Sequence[str],
) -> tuple[list[Notable], dict[str, Any]]:
    """Run each enabled generator on its own and keep a bounded, ordered slice of each."""
    began = time.monotonic()
    notables: list[Notable] = []
    receipt: dict[str, Any] = {"enabled": list(enabled), "seconds": {}}
    if "alerts" in enabled:
        started = time.monotonic()
        found, detail = alerts(executor, cards, facts_by_source)
        notables.extend(found)
        receipt["alerts"] = detail
        receipt["seconds"]["alerts"] = round(time.monotonic() - started, 3)
    if "peer_rare" in enabled:
        found, detail = peer_rare(behaviours, source_stats)
        notables.extend(found)
        receipt["peer_rare"] = detail
    if "deviation" in enabled:
        started = time.monotonic()
        rows, series_receipt = hourly_series(executor, index, start, end)
        grouped = _series_by_source(rows)
        bursts, firsts, detail = _source_deviations(grouped, index, start)
        behaviour_firsts, behaviour_detail = _behaviour_deviations(behaviours, start)
        found = _interleave([bursts, firsts, behaviour_firsts], NOTABLE_BUDGET)
        notables.extend(found)
        receipt["deviation"] = {
            **detail,
            **behaviour_detail,
            "series": series_receipt,
            "kept": len(found),
            "existed": detail["bursts"] + detail["first_seen"] + behaviour_detail["existed"],
        }
        receipt["seconds"]["deviation"] = round(time.monotonic() - started, 3)
    receipt["total"] = len(notables)
    receipt["seconds"]["total"] = round(time.monotonic() - began, 3)
    return notables, receipt
