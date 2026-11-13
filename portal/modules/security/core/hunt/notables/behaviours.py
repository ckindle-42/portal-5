"""Distinct behaviours — who did what to what — counted on DuckDB over a declared slice."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..executor import HuntExecutor
from .cards import SourceCard
from .parse import parse_row
from .sample import BEHAVIOUR_SOURCES, SourceFacts, read_windows, route_filter, window_bounds

BEHAVIOUR_WINDOWS = 12  # effort budget: time slices read per activity source
BEHAVIOUR_EVENTS_PER_WINDOW = 2500  # effort budget: events read from one slice
BEHAVIOUR_TOTAL_EVENTS = 400_000  # effort budget: parsed events across the whole stage
IDENTITY_RECURRENCE = 2.0  # an identity is seen at least twice on average
IDENTITY_BUCKET_SECONDS = 3600  # identities recur across hours, not inside one burst
IDENTITY_BUCKET_SHARE = 0.5  # most occurrences of an identity recur in separate hours
IDENTITY_VALUE_BUDGET = 2000  # effort budget: an identity field keys values up to this many
MAX_BEHAVIOURS = 200_000  # effort budget: rows kept in the behaviour table
EXAMPLE_CHARS = 400  # effort budget: raw characters kept on one behaviour
MAX_TERMS = 3  # effort budget: literal role values used to reproduce one behaviour


@dataclass(frozen=True)
class ExampleEvent:
    source_id: str
    host: str
    ts: float
    raw: str
    fields: Mapping[str, str]
    earliest: float
    latest: float


@dataclass(frozen=True)
class Behaviour:
    """One behaviour row in the order the DuckDB table returns it."""

    source_id: str
    actor_field: str
    actor: str
    action_field: str
    action: str
    object_field: str
    object: str
    actor_mode: str
    action_mode: str
    object_mode: str
    events: int
    first_seen: float
    last_seen: float
    hosts: int
    actors: int
    example_time: float
    example_query: str
    example_raw: str
    example_earliest: float
    example_latest: float


@dataclass(frozen=True)
class FieldIdentity:
    """What a field's values do across events and time, per source."""

    name: str
    present: int
    distinct: int
    recurrence: float
    bucket_share: float
    identity: bool


@dataclass(frozen=True)
class IdentityPlan:
    """Which fields key a behaviour and which are generalised, decided from the data."""

    actor_field: str
    actor_mode: str
    action_field: str
    action_mode: str
    objects: tuple[tuple[str, str], ...]
    overrides: tuple[Mapping[str, Any], ...]
    stats: Mapping[str, FieldIdentity]

    @property
    def object_field(self) -> str:
        return " ".join(name for name, _mode in self.objects) or "slots"

    @property
    def object_mode(self) -> str:
        return "shape" if any(mode == "shape" for _name, mode in self.objects) else "literal"


_COLUMNS = (
    "source_id VARCHAR, host VARCHAR, ts DOUBLE, actor_field VARCHAR, actor VARCHAR, "
    "action_field VARCHAR, action VARCHAR, object_field VARCHAR, object VARCHAR, "
    "actor_mode VARCHAR, action_mode VARCHAR, object_mode VARCHAR, "
    "raw VARCHAR, query VARCHAR, earliest DOUBLE, latest DOUBLE"
)
_INSERT = "INSERT INTO events VALUES (" + ",".join("?" for _ in range(16)) + ")"


def _value(fields: Mapping[str, str], name: str, mode: str) -> str:
    """A literal identity, or a wildcard for a generalised value (it must not key a behaviour)."""
    value = (fields.get(name) or "").strip()
    if not value or not mode:
        return ""
    return value if mode == "literal" else "*"


def identity_stats(
    fields: Sequence[str], events: Sequence[ExampleEvent]
) -> dict[str, FieldIdentity]:
    """Per field: recurrence and the share of occurrences seen in more than one hour."""
    occurrences: dict[str, dict[str, int]] = {}
    buckets: dict[str, dict[str, set[int]]] = {}
    for event in events:
        bucket = int(event.ts // IDENTITY_BUCKET_SECONDS)
        for name in fields:
            value = (event.fields.get(name) or "").strip()
            if not value:
                continue
            per_value = occurrences.setdefault(name, {})
            per_value[value] = per_value.get(value, 0) + 1
            buckets.setdefault(name, {}).setdefault(value, set()).add(bucket)
    stats: dict[str, FieldIdentity] = {}
    for name in fields:
        per_value = occurrences.get(name, {})
        present = sum(per_value.values())
        distinct = len(per_value)
        recurrence = present / distinct if distinct else 0.0
        recurring = sum(
            count for value, count in per_value.items() if len(buckets[name][value]) >= 2
        )
        bucket_share = recurring / present if present else 0.0
        identity = (
            distinct >= 2
            and recurrence >= IDENTITY_RECURRENCE
            and bucket_share >= IDENTITY_BUCKET_SHARE
            and distinct <= IDENTITY_VALUE_BUDGET
        )
        stats[name] = FieldIdentity(
            name, present, distinct, round(recurrence, 3), round(bucket_share, 3), identity
        )
    return stats


def _choose(
    names: Sequence[str], stats: Mapping[str, FieldIdentity], role: str
) -> tuple[str, str, dict[str, Any] | None]:
    """The first field whose values behave like an identity, else the first present, generalised."""
    present = [name for name in names if name in stats and stats[name].present]
    if not present:
        return "", "", None
    qualifying = [name for name in present if stats[name].identity]
    chosen = qualifying[0] if qualifying else present[0]
    safe = stats[chosen].identity or stats[chosen].distinct == 1
    mode = "literal" if safe else "shape"
    if chosen == present[0] and mode == "literal":
        return chosen, mode, None
    return (
        chosen,
        mode,
        {
            "role": role,
            "chosen": chosen,
            "first_present": present[0],
            "identity": stats[chosen].identity,
            "recurrence": stats[chosen].recurrence,
            "bucket_share": stats[chosen].bucket_share,
            "mode": mode,
        },
    )


def identity_plan(card: SourceCard, events: Sequence[ExampleEvent]) -> IdentityPlan:
    """Decide actor, action and object fields from recurrence across events and time."""
    stats = identity_stats(role_fields(card), events)
    overrides: list[Mapping[str, Any]] = []
    if card.fmt == "template":
        if "program" in stats and stats["program"].present:
            actor_field, actor_mode = "program", "literal"
        else:
            candidates = [
                name for name in card.role_fields("object") if name in stats and stats[name].present
            ]
            qualifying = [name for name in candidates if stats[name].identity]
            actor_field = qualifying[0] if qualifying else ""
            actor_mode = "literal" if qualifying else ""
            if actor_field:
                overrides.append(
                    {"role": "actor", "chosen": actor_field, "reason": "first_identity_slot"}
                )
        action_field, action_mode = "template", "literal"
        objects = tuple(
            (
                name,
                "literal" if stats[name].identity or stats[name].distinct == 1 else "shape",
            )
            for name in card.role_fields("object")
            if name in stats and stats[name].present and name != actor_field
        )
    else:
        actor_field, actor_mode, actor_override = _choose(card.role_fields("actor"), stats, "actor")
        action_field, action_mode, action_override = _choose(
            card.role_fields("action"), stats, "action"
        )
        object_field, object_mode, object_override = _choose(
            card.role_fields("object"), stats, "object"
        )
        overrides.extend(
            item for item in (actor_override, action_override, object_override) if item
        )
        objects = ((object_field, object_mode),) if object_field else ()
    return IdentityPlan(
        actor_field,
        actor_mode,
        action_field,
        action_mode,
        objects,
        tuple(overrides),
        stats,
    )


def _query_terms(plan: IdentityPlan, fields: Mapping[str, str]) -> list[str]:
    values = [_value(fields, plan.actor_field, plan.actor_mode)] if plan.actor_field else []
    if plan.action_field and plan.action_field != "template":
        values.append(_value(fields, plan.action_field, plan.action_mode))
    values.extend(_value(fields, name, mode) for name, mode in plan.objects if mode == "literal")
    return [value for value in values if value][:MAX_TERMS]


def behaviour_key(
    card: SourceCard, fields: Mapping[str, str], plan: IdentityPlan
) -> tuple[str, str, str, str, str, str]:
    """(actor_field, actor, action_field, action, object_field, object) for one event."""
    if card.fmt == "template":
        actor = _value(fields, plan.actor_field, plan.actor_mode)
        action = (fields.get("template") or "").strip()
        parts = [value for name, mode in plan.objects if (value := _value(fields, name, mode))]
        return (plan.actor_field, actor, "template", action, "slots", " ".join(parts))
    object_value = _value(fields, plan.objects[0][0], plan.objects[0][1]) if plan.objects else ""
    return (
        plan.actor_field,
        _value(fields, plan.actor_field, plan.actor_mode),
        plan.action_field,
        _value(fields, plan.action_field, plan.action_mode),
        plan.object_field,
        object_value,
    )


def plan_summary(plan: IdentityPlan) -> dict[str, Any]:
    """Recorded form of one source's keying decision, written back onto its card."""
    return {
        "actor": {"field": plan.actor_field, "mode": plan.actor_mode},
        "action": {"field": plan.action_field, "mode": plan.action_mode},
        "objects": [{"field": name, "mode": mode} for name, mode in plan.objects],
        "overrides": [dict(item) for item in plan.overrides],
        "fields": {
            name: {
                "present": stat.present,
                "distinct": stat.distinct,
                "recurrence": stat.recurrence,
                "bucket_share": stat.bucket_share,
                "identity": stat.identity,
            }
            for name, stat in sorted(plan.stats.items())
        },
    }


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def reproduction_query(facts: SourceFacts, terms: Sequence[str]) -> str:
    """Every literal role value together, so the query selects this behaviour, not a common word."""
    route, _ = route_filter(facts, BEHAVIOUR_SOURCES)
    picked = [value for value in terms if value][:MAX_TERMS]
    tail = " " + " ".join(f"TERM({_quote(value)})" for value in picked) if picked else ""
    return f"search index={_quote(facts.index)} {route}{tail} | head 5"


def _window_for(ts: float, windows: Sequence[tuple[float, float]]) -> tuple[float, float]:
    for start, end in windows:
        if start <= ts < end:
            return start, end
    return windows[0] if windows else (ts, ts + 3600.0)


def _extract(
    card: SourceCard, rows: Sequence[Mapping[str, Any]], windows: Sequence[tuple[float, float]]
) -> list[ExampleEvent]:
    found: list[ExampleEvent] = []
    for row in rows:
        parsed = parse_row(str(row.get("_raw") or ""), card.fmt, card.columns, card.template_model)
        if not parsed.fields or not card.in_part(parsed.fields):
            continue
        try:
            ts = float(row.get("_time") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        earliest, latest = _window_for(ts, windows)
        found.append(
            ExampleEvent(
                card.source_id,
                str(row.get("host") or ""),
                ts,
                str(row.get("_raw") or "")[:EXAMPLE_CHARS],
                parsed.fields,
                earliest,
                latest,
            )
        )
    return found


def role_fields(card: SourceCard) -> list[str]:
    return sorted(
        {
            *card.role_fields("actor"),
            *card.role_fields("action"),
            *card.role_fields("object"),
        }
    )


def keyed_rows(
    card: SourceCard,
    facts: SourceFacts,
    events: Sequence[ExampleEvent],
    plan: IdentityPlan | None = None,
) -> list[tuple[Any, ...]]:
    """One row per event: the behaviour key, the reproducing query and the event's window."""
    plan = plan or identity_plan(card, events)
    rows: list[tuple[Any, ...]] = []
    for event in events:
        actor_field, actor, action_field, action, object_field, object_value = behaviour_key(
            card, event.fields, plan
        )
        if not actor and not object_value:
            continue
        query = reproduction_query(facts, _query_terms(plan, event.fields))
        rows.append(
            (
                event.source_id,
                event.host,
                event.ts,
                actor_field,
                actor,
                action_field,
                action,
                object_field,
                object_value,
                plan.actor_mode,
                plan.action_mode,
                plan.object_mode,
                event.raw,
                query,
                event.earliest,
                event.latest,
            )
        )
    return rows


def per_window_events(sources: int) -> int:
    """Each source's share of the total event budget, expressed per time slice."""
    share = max(1, BEHAVIOUR_TOTAL_EVENTS // max(1, sources))
    return max(1, min(BEHAVIOUR_EVENTS_PER_WINDOW, share // BEHAVIOUR_WINDOWS))


def create_events(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE TABLE events ({_COLUMNS})")


def aggregate_events(con: duckdb.DuckDBPyConnection) -> tuple[list[Behaviour], int]:
    """Group keyed events into behaviours and source statistics; return the kept table."""
    con.execute(
        "CREATE TABLE behaviour_all AS SELECT source_id, actor_field, actor, action_field,"
        " action, object_field, object, actor_mode, action_mode, object_mode,"
        " count(*) AS events, min(ts) AS first_seen,"
        " max(ts) AS last_seen, count(DISTINCT NULLIF(host, '')) AS hosts,"
        " count(DISTINCT NULLIF(actor, '')) AS actors, arg_min(ts, ts) AS example_time,"
        " arg_min(query, ts) AS example_query, arg_min(raw, ts) AS example_raw,"
        " min(ts) AS example_earliest, max(ts) AS example_latest"
        " FROM events GROUP BY ALL"
    )
    row = con.execute("SELECT count(*) FROM behaviour_all").fetchone()
    existed = int(row[0]) if row else 0
    con.execute(
        "CREATE TABLE behaviours AS SELECT * FROM behaviour_all"
        f" ORDER BY events DESC, source_id, actor, action, object LIMIT {MAX_BEHAVIOURS}"
    )
    con.execute(
        "CREATE TABLE source_stats AS SELECT source_id, count(*) AS events,"
        " count(DISTINCT NULLIF(host, '')) AS hosts_possible,"
        " count(DISTINCT NULLIF(actor, '')) AS actors_possible FROM events GROUP BY source_id"
    )
    return [Behaviour(*row) for row in con.execute("SELECT * FROM behaviours").fetchall()], existed


def _source_groups(cards: Sequence[SourceCard]) -> dict[str, list[SourceCard]]:
    grouped: dict[str, list[SourceCard]] = {}
    for card in cards:
        grouped.setdefault(card.source_id, []).append(card)
    return grouped


def _skip_reason(card: SourceCard) -> str:
    return card.reason or ("no_roles" if card.kind == "activity" else f"kind:{card.kind}")


def _source_receipt(
    card: SourceCard,
    facts: SourceFacts,
    read: Any,
    events: int,
    keyed: int,
    seconds: float,
    per_window: int,
) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "source_id": card.source_id,
        "part": {"field": card.part_field, "value": card.part_value} if card.part_field else None,
        "kind": card.kind,
        "events_available": facts.events,
        "events_read": len(read.rows),
        "events_parsed": events,
        "events_keyed": keyed,
        "events_keyless": max(0, events - keyed),
        "windows": read.windows,
        "per_window": per_window,
        "selection": "newest events of each equal time slice",
        "route": read.route,
        "share_of_source": round(len(read.rows) / facts.events, 6) if facts.events else None,
        "seconds": round(seconds, 3),
        "notes": read.notes,
    }


def _key_source(
    con: duckdb.DuckDBPyConnection,
    usable: Sequence[SourceCard],
    facts: SourceFacts,
    per_window: int,
    executor: HuntExecutor,
    started: float,
) -> tuple[list[dict[str, Any]], int, dict[str, dict[str, Any]]]:
    """Read one source once and key each of its structures' events into the store."""
    windows = window_bounds(facts.first, facts.last, BEHAVIOUR_WINDOWS)
    read = read_windows(
        executor,
        facts,
        windows,
        per_window=per_window,
        kind="behavior_events",
        max_sources=BEHAVIOUR_SOURCES,
    )
    receipts: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, Any]] = {}
    total = 0
    for card in usable:
        events = _extract(card, read.rows, windows)
        plan = identity_plan(card, events)
        rows = keyed_rows(card, facts, events, plan)
        if rows:
            con.executemany(_INSERT, rows)
        total += len(rows)
        summary = plan_summary(plan)
        overrides[card.card_id] = summary
        receipt = _source_receipt(
            card,
            facts,
            read,
            len(events),
            len(rows),
            time.monotonic() - started,
            per_window,
        )
        receipt["identity"] = summary
        receipts.append(receipt)
    return receipts, total, overrides


def collect_behaviours(
    executor: HuntExecutor,
    cards: Sequence[SourceCard],
    facts_by_source: Mapping[str, SourceFacts],
    store_path: Path,
) -> tuple[list[Behaviour], dict[str, Any]]:
    """Read each activity source once, key each structure's events, and count on DuckDB."""
    began = time.monotonic()
    grouped = _source_groups(cards)
    usable_sources = sum(1 for group in grouped.values() if any(card.usable for card in group))
    skipped: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, Any]] = {}
    per_window = per_window_events(usable_sources)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.unlink(missing_ok=True)
    con = duckdb.connect(str(store_path))
    total = 0
    try:
        create_events(con)
        for source_id, group in grouped.items():
            usable = [card for card in group if card.usable]
            if not usable:
                skipped.extend(
                    {
                        "card_id": card.card_id,
                        "source_id": card.source_id,
                        "reason": _skip_reason(card),
                        "behaviours": 0,
                    }
                    for card in group
                )
                continue
            facts = facts_by_source.get(source_id)
            if facts is None:
                skipped.extend(
                    {
                        "card_id": card.card_id,
                        "source_id": card.source_id,
                        "reason": "no_index_facts",
                        "behaviours": 0,
                    }
                    for card in usable
                )
                continue
            started = time.monotonic()
            found, count, found_overrides = _key_source(
                con, usable, facts, per_window, executor, started
            )
            receipts.extend(found)
            overrides.update(found_overrides)
            total += count
        behaviours, existed = aggregate_events(con)
    finally:
        con.close()
    counts: dict[str, int] = {}
    singletons: dict[str, int] = {}
    for behaviour in behaviours:
        counts[behaviour.source_id] = counts.get(behaviour.source_id, 0) + 1
        if behaviour.events == 1:
            singletons[behaviour.source_id] = singletons.get(behaviour.source_id, 0) + 1
    for item in receipts:
        source = str(item.get("source_id"))
        distinct = counts.get(source, 0)
        once = singletons.get(source, 0)
        item["behaviours"] = distinct
        item["singletons"] = once
        item["singleton_share"] = round(once / distinct, 3) if distinct else None
    return behaviours, {
        "receipts": receipts,
        "skipped": skipped,
        "identity_overrides": overrides,
        "singletons": sum(singletons.values()),
        "events_read": total,
        "per_window": per_window,
        "behaviours_existed": existed,
        "behaviours_kept": len(behaviours),
        "store": str(store_path),
        "seconds": round(time.monotonic() - began, 3),
    }


def load_behaviours(path: Path) -> list[Behaviour]:
    """Read back the stored behaviour table for a later stage."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute("SELECT * FROM behaviours").fetchall()
    finally:
        con.close()
    return [Behaviour(*row) for row in rows]


def load_source_stats(path: Path) -> dict[str, dict[str, Any]]:
    """Hosts and actors that could share a behaviour, per source, from the stored table."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute(
            "SELECT source_id, hosts_possible, actors_possible FROM source_stats"
        ).fetchall()
    finally:
        con.close()
    return {
        str(source_id): {
            "hosts_possible": int(hosts),
            "actors_possible": int(actors),
        }
        for source_id, hosts, actors in rows
    }
