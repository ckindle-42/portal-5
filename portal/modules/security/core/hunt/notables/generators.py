"""Independent notable generators: existing alerts, peer-rare behaviours, deviations."""

from __future__ import annotations

import hashlib
import math
import statistics
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from ..engine import _literal_term_segments
from ..executor import HuntExecutor
from .behaviours import Behaviour, BehaviourIdentity, behaviour_identity
from .cards import SourceCard, card_consumers
from .parse import parse_row
from .sample import BEHAVIOUR_SOURCES, SourceFacts, read_windows, route_filter, source_windows

NOTABLE_BUDGET = 300  # effort budget: notables kept per generator
ALERT_WINDOWS = 8  # effort budget: time slices read per alert stream
ALERT_EVENTS_PER_WINDOW = 1000  # effort budget: alert events read from one slice
DEVIATION_SOURCE_BUDGET = 100  # effort budget: source-level deviations kept per ordering
DEVIATION_BEHAVIOUR_BUDGET = 100  # effort budget: behaviour-level deviations considered
DEVIATION_BURST_ALLOWANCE = 2  # LOFO-selected: behaviour bursts admitted above the source baseline
MIN_SERIES_PERIODS = 3  # a deviation needs at least this many observed buckets
SERIES_ROWS = 40_000  # effort budget: per-period source-count rows (below the 50k result cap)
SERIES_SPAN_SECONDS = 4 * 3600  # effort budget: deviation bucket width
MAX_ENTITIES = 8  # effort budget: entities attached to one notable
EVIDENCE_CHARS = 400  # effort budget: raw characters kept on one notable evidence line
EXACT_COUNT_BUDGET = 300  # effort budget: whole-index counts for kept peer-rare notables
EXACT_TERMS = 3  # effort budget: identity terms in one exact count

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
    nearest_known: tuple[Mapping[str, Any], ...] = ()
    generator_reliability: float | None = None

    @property
    def notable_id(self) -> str:
        return hashlib.sha1(self.content_key.encode()).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        result = {
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
        if self.nearest_known:
            result["nearest_known"] = [dict(item) for item in self.nearest_known]
        if self.generator_reliability is not None:
            result["generator_reliability"] = self.generator_reliability
        return result


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
    nearest_known: Sequence[Mapping[str, Any]] = (),
    generator_reliability: float | None = None,
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
        tuple(dict(item) for item in nearest_known),
        generator_reliability,
    )


def _first_present(fields: Mapping[str, str], names: Sequence[str]) -> str:
    for name in names:
        value = (fields.get(name) or "").strip()
        if value:
            return value
    return ""


def _term(value: str) -> str:
    return " ".join(_quote(segment) for segment in _literal_term_segments(value))


def _alert_query(facts: SourceFacts, action: str, entity: str) -> str:
    route, _ = route_filter(facts, BEHAVIOUR_SOURCES)
    term_groups = [_term(value) for value in (action, entity) if value]
    terms = " ".join(term for term in term_groups if term)
    tail = f" {terms}"
    return f"search index={_quote(facts.index)} {route}{tail} | head 5"


def _add_alert(
    grouped: dict[tuple[str, str, str], dict[str, Any]],
    card: SourceCard,
    row: Mapping[str, Any],
    fields: Mapping[str, str],
) -> bool:
    action = _first_present(fields, card.role_fields("action")) or _first_present(
        fields, card.role_fields("object")
    )
    entity = _first_present(fields, card.role_fields("actor")) or _first_present(
        fields, card.role_fields("to")
    )
    entity = (
        entity or _first_present(fields, card.role_fields("from")) or str(row.get("host") or "")
    )
    if not action:
        return False
    key = (card.card_id, action, entity)
    slot = grouped.setdefault(
        key,
        {
            "source_id": card.source_id,
            "count": 0,
            "first": float("inf"),
            "last": 0.0,
            "hosts": set(),
            "raw": str(row.get("_raw") or "")[:EVIDENCE_CHARS],
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
    return True


def _alert_rows(
    executor: HuntExecutor, cards: Sequence[SourceCard], facts_by_source: Mapping[str, SourceFacts]
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Distinct (alert, entity) in each alert stream, over a declared slice."""
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    receipts: list[dict[str, Any]] = []
    notes: list[str] = []
    sources: dict[str, list[SourceCard]] = {}
    for card in cards:
        if "alerts" in card_consumers(card):
            sources.setdefault(card.source_id, []).append(card)
    scheduled: list[
        tuple[str, list[SourceCard], SourceFacts, float, list[tuple[float, float]]]
    ] = []
    for source_id, group in sources.items():
        facts = facts_by_source.get(source_id)
        if facts is None:
            receipts.extend({"card_id": card.card_id, "reason": "no_index_facts"} for card in group)
            continue
        started = time.monotonic()
        windows = source_windows(facts, ALERT_WINDOWS)
        scheduled.append((source_id, group, facts, started, windows))
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(scheduled) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                read_windows,
                executor,
                facts,
                windows,
                per_window=ALERT_EVENTS_PER_WINDOW,
                kind="alert_events",
                max_sources=BEHAVIOUR_SOURCES,
            )
            for _source_id, _group, facts, _started, windows in scheduled
        ]
        reads = [future.result() for future in futures]
    for (_source_id, group, facts, started, _windows), read in zip(scheduled, reads, strict=True):
        for card in group:
            missing = 0
            seen = 0
            for row in read.rows:
                fields = _alert_fields(card, str(row.get("_raw") or ""))
                if not card.in_part(fields):
                    continue
                seen += 1
                if not _add_alert(grouped, card, row, fields):
                    missing += 1
            receipts.append(
                {
                    "card_id": card.card_id,
                    "source_id": card.source_id,
                    "part": {"field": card.part_field, "value": card.part_value}
                    if card.part_field
                    else None,
                    "events_available": facts.events,
                    "events_read": seen,
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
    return parse_row(raw, card.fmt, card.columns, card.template_model).fields


def alerts(
    executor: HuntExecutor, cards: Sequence[SourceCard], facts_by_source: Mapping[str, SourceFacts]
) -> tuple[list[Notable], dict[str, Any]]:
    grouped, receipts, notes = _alert_rows(executor, cards, facts_by_source)
    ordered = sorted(grouped.items(), key=lambda item: (-item[1]["count"], item[0]))
    notables: list[Notable] = []
    for (_card_id, action, entity), slot in ordered[:NOTABLE_BUDGET]:
        source_id = str(slot["source_id"])
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


def rarity(behaviour: Behaviour, stats: Mapping[str, Any]) -> tuple[float, str]:
    """Rarity over the denominators that exist; a role the behaviour lacks is unknown, not rare."""
    hosts_possible = int(stats.get("hosts_possible") or 0)
    actors_possible = int(stats.get("actors_possible") or 0)
    factors: list[float] = []
    clauses: list[str] = []
    if hosts_possible and behaviour.hosts:
        factors.append(behaviour.hosts / hosts_possible)
        clauses.append(f"on {behaviour.hosts}/{hosts_possible} hosts")
    if not behaviour.hosts:
        clauses.append("host not present in this behaviour")
    if behaviour.actors and actors_possible:
        factors.append(behaviour.actors / actors_possible)
        clauses.append(f"{behaviour.actors}/{actors_possible} actors")
    if not behaviour.actors:
        clauses.append("actor not present in this behaviour")
    if not factors:
        return 1.0, "no host or actor denominator for this source"
    measure = 1.0
    for factor in factors:
        measure *= factor
    return round(measure, 10), " and ".join(clauses)


def _specificity(behaviour: Behaviour) -> int:
    """How many of actor, action and object the behaviour actually names."""
    return sum(1 for part in (behaviour.actor, behaviour.action, behaviour.object) if part)


def peer_rare(
    behaviours: Sequence[Behaviour], source_stats: Mapping[str, Mapping[str, Any]]
) -> tuple[list[Notable], dict[str, Any]]:
    """Behaviours shared by few hosts and actors, relative to how many could share them."""
    ranked: list[tuple[float, int, int, str, Behaviour, str]] = []
    for behaviour in behaviours:
        if not behaviour.actor and not behaviour.object:
            continue
        measure, why = rarity(behaviour, source_stats.get(behaviour.source_id, {}))
        ranked.append(
            (
                measure,
                -_specificity(behaviour),
                -behaviour.events,
                behaviour.source_id,
                behaviour,
                why,
            )
        )
    ranked.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3],
            item[4].actor,
            item[4].action,
            item[4].object,
        )
    )
    cut = ranked[NOTABLE_BUDGET - 1][0] if len(ranked) > NOTABLE_BUDGET else None
    tied_at_cut = sum(1 for item in ranked if item[0] == cut) if cut is not None else 0
    notables: list[Notable] = []
    for measure, _specificity_value, _events, source_id, behaviour, why in ranked[:NOTABLE_BUDGET]:
        notables.append(
            _make(
                generator="peer_rare",
                basis="behaviour_share",
                what=_behaviour_words(behaviour),
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
                why=why,
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
    return notables, {
        "existed": len(ranked),
        "kept": len(notables),
        "tied_at_cut": tied_at_cut,
        "tie_break": ["measure", "specificity", "events", "lexical"],
    }


def _index_terms(notable: Notable) -> list[str]:
    """Whole Splunk terms eligible for exact identity counts."""
    terms: list[str] = []
    for role, value in notable.entities:
        if role not in ("actor", "object"):
            continue
        text = value.strip()
        if not text or any(char.isspace() for char in text):
            continue
        terms.extend(_literal_term_segments(text))
    return terms[:EXACT_TERMS]


def _exact_count(
    executor: HuntExecutor, index: str, start: float, end: float, notable: Notable
) -> tuple[int | None, str | None]:
    """Whole-index event count for one notable's identity terms, or why it was not counted."""
    terms = _index_terms(notable)
    if not terms:
        return None, "no_index_terms"
    query = f"| tstats count where index={_quote(index)} " + " ".join(
        _quote(value) for value in terms
    )
    try:
        read = executor.read(query, start, end, kind="exact_count", row_cap=1)
    except Exception as exc:  # noqa: BLE001 -- an exact count that cannot run is declared
        return None, f"read_failed:{type(exc).__name__}"
    if not read.rows:
        return None, "no_count_row"
    value = read.rows[0].get("count")
    if value is None:
        return None, "bad_count"
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return None, "bad_count"
    sampled = int(notable.counts.get("events") or 0)
    if count == 0:
        return None, "no_index_match"
    if count < sampled:
        return None, "below_sample"
    return count, None


def exact_counts(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    notables: Sequence[Notable],
    *,
    budget: int = EXACT_COUNT_BUDGET,
) -> tuple[list[Notable], dict[str, Any]]:
    """Replace sampled events with exact whole-index counts where the identity terms allow it."""
    began = time.monotonic()
    chosen = list(notables[: max(0, budget)])
    updated = list(notables)
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(chosen) or 1, concurrency)) as pool:
        futures = [
            pool.submit(_exact_count, executor, index, start, end, notable) for notable in chosen
        ]
        results = [future.result() for future in futures]
    reasons: dict[str, int] = {}
    by_source: dict[str, int] = {}
    counted = 0
    for position, (count, reason) in enumerate(results):
        if count is None:
            key = reason or "unknown"
            reasons[key] = reasons.get(key, 0) + 1
            continue
        notable = chosen[position]
        counts = dict(notable.counts)
        counts["sampled_events"] = counts.get("events")
        counts["events"] = count
        counts["counted_from"] = "index_terms"
        updated[position] = replace(notable, counts=counts)
        counted += 1
        by_source[notable.source_id] = by_source.get(notable.source_id, 0) + 1
    return updated, {
        "candidates": len(notables),
        "budget": min(max(0, budget), len(notables)),
        "counted": counted,
        "queries": len(chosen),
        "reasons": reasons,
        "by_source": by_source,
        "seconds": round(time.monotonic() - began, 3),
    }


def behaviour_words(actor: str, action: str, object_value: str) -> str:
    return normalized_behaviour_words(actor, action, object_value)


def normalized_behaviour_words(
    actor: str,
    action: str,
    object_value: str,
    *,
    actor_field: str = "",
    action_field: str = "",
) -> str:
    """Format the shared run and manifest embedding statement for one behaviour."""
    parts = []
    if actor:
        role = "program" if actor_field.casefold() == "program" else "actor"
        parts.append(f"{role} {actor}")
    if action and action_field.casefold() != "template":
        parts.append(f"did {action}")
    if object_value:
        parts.append(f"to {object_value}")
    return " ".join(parts) or "an unnamed behaviour"


def _behaviour_words(behaviour: Behaviour) -> str:
    return normalized_behaviour_words(
        behaviour.actor,
        behaviour.action,
        behaviour.object,
        actor_field=behaviour.actor_field,
        action_field=behaviour.action_field,
    )


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
    query = f"| tstats count where index={_quote(index)} by sourcetype _time span=4h"
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
        if len(series) >= MIN_SERIES_PERIODS:
            z, peak = _robust_z([count for _hour_value, count in series])
            bursts.append((z, name, series[peak][0], series[peak][1]))
        firsts.append((series[0][0] - index_start, name, series[0][0]))
    bursts.sort(key=lambda item: (-item[0], item[1]))
    firsts.sort(key=lambda item: (-item[0], item[1]))
    series_query = f"| tstats count where index={_quote(index)} by sourcetype _time span=4h"
    burst_notables = [
        _make(
            generator="deviation",
            basis="source_burst",
            what=f"source {name} burst to {count} events in four hours",
            entities=(("source", name),),
            source_id=f"{index}:{name}",
            first_seen=hour,
            last_seen=hour + SERIES_SPAN_SECONDS,
            counts={"events": count},
            measure_name="robust_z",
            measure_value=value,
            why=f"log count {value} robust deviations above its own four-hour median",
            evidence=(
                {
                    "line": f"sourcetype={name} at={hour:.0f} count={count} z={value}",
                    "query": series_query,
                    "earliest": hour,
                    "latest": hour + SERIES_SPAN_SECONDS,
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
            last_seen=hour + SERIES_SPAN_SECONDS,
            counts={},
            measure_name="seconds_after_index_start",
            measure_value=round(late, 3),
            why="first four-hour bucket this source was observed in, relative to the index start",
            evidence=(
                {
                    "line": f"sourcetype={name} first_at={hour:.0f}",
                    "query": series_query,
                    "earliest": hour,
                    "latest": hour + SERIES_SPAN_SECONDS,
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


def _behaviour_bursts(
    behaviours: Sequence[Behaviour], peaks: Mapping[BehaviourIdentity, int]
) -> tuple[list[Notable], dict[str, Any]]:
    """Rank four-hour behaviour peaks against the other behaviours in their source."""
    by_source: dict[str, list[Behaviour]] = {}
    for behaviour in behaviours:
        by_source.setdefault(behaviour.source_id, []).append(behaviour)
    ranked: list[tuple[float, int, Behaviour, int]] = []
    for rows in by_source.values():
        values = [peaks.get(behaviour_identity(behaviour), 0) for behaviour in rows]
        logs = [math.log1p(value) for value in values]
        median = statistics.median(logs)
        mad = statistics.median(abs(value - median) for value in logs)
        source_events = sum(behaviour.events for behaviour in rows)
        for behaviour, peak in zip(rows, values, strict=True):
            score = (math.log1p(peak) - median) / (mad + 0.5)
            ranked.append((score, peak, behaviour, source_events))
    ranked.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2].source_id,
            item[2].actor,
            item[2].action,
            item[2].object,
        )
    )
    found = [
        _make(
            generator="deviation",
            basis="behaviour_burst",
            what=_behaviour_words(behaviour) + f" burst to {peak} events in one four-hour bucket",
            entities=(
                ("actor", behaviour.actor),
                ("action", behaviour.action),
                ("object", behaviour.object),
            ),
            source_id=behaviour.source_id,
            first_seen=behaviour.first_seen,
            last_seen=behaviour.last_seen,
            counts={
                "events": behaviour.events,
                "peak_bucket_events": peak,
                "source_events": source_events,
            },
            measure_name="robust_z",
            measure_value=score,
            why=f"{peak} of {behaviour.events} sampled events occurred in one four-hour bucket",
            evidence=(
                {
                    "line": behaviour.example_raw,
                    "query": behaviour.example_query,
                    "earliest": behaviour.example_earliest,
                    "latest": behaviour.example_latest,
                },
            ),
        )
        for score, peak, behaviour, _source_events in ranked[:DEVIATION_BEHAVIOUR_BUDGET]
    ]
    return found, {"existed": len(ranked), "kept": len(found)}


def _unified_bursts(
    source_bursts: Sequence[Notable], behaviour_bursts: Sequence[Notable]
) -> tuple[list[Notable], dict[str, Any]]:
    """Let exceptional behaviour peaks compete inside the source-burst allocation."""
    baseline = max((notable.measure_value for notable in source_bursts), default=0.0)
    admitted = [notable for notable in behaviour_bursts if notable.measure_value > baseline][
        :DEVIATION_BURST_ALLOWANCE
    ]
    unified = sorted(
        [*source_bursts, *admitted],
        key=lambda notable: (-notable.measure_value, notable.source_id, notable.what),
    )[: len(source_bursts)]
    return unified, {
        "candidates": len(behaviour_bursts),
        "admitted": len(admitted),
        "source_baseline": baseline,
    }


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
    behaviour_peaks: Mapping[BehaviourIdentity, int] | None = None,
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
        if found:
            found, detail["exact_counts"] = exact_counts(executor, index, start, end, found)
        notables.extend(found)
        receipt["peer_rare"] = detail
    if "deviation" in enabled:
        started = time.monotonic()
        rows, series_receipt = hourly_series(executor, index, start, end)
        grouped = _series_by_source(rows)
        origin = (
            start
            if start > 0
            else min((series[0][0] for series in grouped.values() if series), default=start)
        )
        bursts, firsts, detail = _source_deviations(grouped, index, origin)
        behaviour_bursts, burst_detail = _behaviour_bursts(behaviours, behaviour_peaks or {})
        bursts, unified_detail = _unified_bursts(bursts, behaviour_bursts)
        behaviour_firsts, behaviour_detail = _behaviour_deviations(behaviours, origin)
        found = _interleave([bursts, firsts, behaviour_firsts], NOTABLE_BUDGET)
        notables.extend(found)
        receipt["deviation"] = {
            **detail,
            **behaviour_detail,
            "behaviour_bursts": {**burst_detail, **unified_detail},
            "series": series_receipt,
            "kept": len(found),
            "existed": detail["bursts"]
            + detail["first_seen"]
            + behaviour_detail["existed"]
            + unified_detail["admitted"],
        }
        receipt["seconds"]["deviation"] = round(time.monotonic() - started, 3)
    receipt["total"] = len(notables)
    receipt["seconds"]["total"] = round(time.monotonic() - began, 3)
    return notables, receipt
