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
BEHAVIOUR_FIELD_VALUES = 2000  # effort budget: a field stays literal in keys up to this many values
MAX_BEHAVIOURS = 200_000  # effort budget: rows kept in the behaviour table
SHAPE_CHARS = 64  # effort budget: characters that describe a generalised value
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


_COLUMNS = (
    "source_id VARCHAR, host VARCHAR, ts DOUBLE, actor_field VARCHAR, actor VARCHAR, "
    "action_field VARCHAR, action VARCHAR, object_field VARCHAR, object VARCHAR, "
    "raw VARCHAR, query VARCHAR, earliest DOUBLE, latest DOUBLE"
)
_INSERT = "INSERT INTO events VALUES (" + ",".join("?" for _ in range(13)) + ")"


def value_shape(value: str) -> str:
    """A value's character classes: digits become 9, letters a, punctuation is kept."""
    shaped = "".join(
        "9" if char.isdigit() else "a" if char.isalpha() else char for char in value[:SHAPE_CHARS]
    )
    return shaped or value[:SHAPE_CHARS]


def field_modes(fields: Sequence[str], events: Sequence[ExampleEvent]) -> dict[str, str]:
    """Literal values for fields whose catalogue fits the effort budget, shapes otherwise."""
    distinct: dict[str, set[str]] = {}
    for event in events:
        for name in fields:
            value = (event.fields.get(name) or "").strip()
            if value:
                distinct.setdefault(name, set()).add(value)
    return {
        name: "literal" if len(distinct.get(name, ())) <= BEHAVIOUR_FIELD_VALUES else "shape"
        for name in fields
    }


def _first_value(
    fields: Mapping[str, str], names: Sequence[str], modes: Mapping[str, str]
) -> tuple[str, str]:
    for name in names:
        value = (fields.get(name) or "").strip()
        if value:
            return name, value if modes.get(name) == "literal" else value_shape(value)
    return "", ""


def behaviour_key(
    card: SourceCard, fields: Mapping[str, str], modes: Mapping[str, str]
) -> tuple[str, str, str, str, str, str]:
    """(actor_field, actor, action_field, action, object_field, object) for one event."""
    if card.fmt == "template":
        actor = (fields.get("program") or "").strip()
        action = (fields.get("template") or "").strip()
        slots = [
            value if modes.get(name, "literal") == "literal" else value_shape(value)
            for name in card.role_fields("object")
            if (value := (fields.get(name) or "").strip())
        ]
        return ("program", actor, "template", action, "slots", " ".join(slots))
    return (
        *_first_value(fields, card.role_fields("actor"), modes),
        *_first_value(fields, card.role_fields("action"), modes),
        *_first_value(fields, card.role_fields("object"), modes),
    )


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
    card: SourceCard, facts: SourceFacts, events: Sequence[ExampleEvent]
) -> list[tuple[Any, ...]]:
    """One row per event: the behaviour key, the reproducing query and the event's window."""
    modes = field_modes(role_fields(card), events)
    rows: list[tuple[Any, ...]] = []
    for event in events:
        actor_field, actor, action_field, action, object_field, object_value = behaviour_key(
            card, event.fields, modes
        )
        if not actor and not object_value:
            continue
        if card.fmt == "template":
            terms = [actor] + [
                value
                for name in card.role_fields("object")
                if (value := (event.fields.get(name) or "").strip())
                and modes.get(name) == "literal"
            ]
        else:
            terms = [
                value
                for _field, value, mode in (
                    (actor_field, actor, modes.get(actor_field, "shape")),
                    (action_field, action, modes.get(action_field, "shape")),
                    (object_field, object_value, modes.get(object_field, "shape")),
                )
                if mode == "literal"
            ]
        query = reproduction_query(facts, terms)
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
        " action, object_field, object, count(*) AS events, min(ts) AS first_seen,"
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
) -> tuple[list[dict[str, Any]], int]:
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
    total = 0
    for card in usable:
        events = _extract(card, read.rows, windows)
        rows = keyed_rows(card, facts, events)
        if rows:
            con.executemany(_INSERT, rows)
        total += len(rows)
        receipts.append(
            _source_receipt(
                card,
                facts,
                read,
                len(events),
                len(rows),
                time.monotonic() - started,
                per_window,
            )
        )
    return receipts, total


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
            found, count = _key_source(con, usable, facts, per_window, executor, started)
            receipts.extend(found)
            total += count
        behaviours, existed = aggregate_events(con)
    finally:
        con.close()
    counts: dict[str, int] = {}
    for behaviour in behaviours:
        counts[behaviour.source_id] = counts.get(behaviour.source_id, 0) + 1
    for item in receipts:
        item["behaviours"] = counts.get(str(item.get("source_id")), 0)
    return behaviours, {
        "receipts": receipts,
        "skipped": skipped,
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
