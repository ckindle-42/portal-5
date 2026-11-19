"""Distinct behaviours — who did what to what — counted on DuckDB over a declared slice."""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..engine import _literal_term_segments
from ..executor import HuntExecutor
from .cards import SourceCard, card_consumers
from .parse import parse_row
from .sample import (
    BEHAVIOUR_SOURCES,
    RowSet,
    SourceFacts,
    read_windows,
    route_filter,
    source_windows,
)
from .sample import (
    window_bounds as window_bounds,
)

BEHAVIOUR_WINDOWS = 12  # effort budget: time slices read per activity source
BEHAVIOUR_BURST_WINDOWS = 4  # peak four-hour slices reserved inside BEHAVIOUR_WINDOWS
BEHAVIOUR_SUB_WINDOWS = 2  # each uniform slice read at its midpoint and tail
BEHAVIOUR_BURST_SUB_WINDOWS = (
    2  # each peak four-hour slice read at midpoint and tail (same req cap)
)
BEHAVIOUR_BURST_SPAN_SECONDS = 4 * 3600  # four-hour burst bucket width matching deviation
BEHAVIOUR_BURST_SERIES_ROWS = 40_000  # effort budget: per-period tstats rows for burst planning
BEHAVIOUR_EVENTS_PER_WINDOW = 2500  # effort budget: events read from one slice
BEHAVIOUR_TOTAL_EVENTS = 400_000  # effort budget: parsed events across the whole stage
IDENTITY_RECURRENCE = 2.0  # an identity is seen at least twice on average
IDENTITY_BUCKET_SECONDS = 3600  # identities recur across hours, not inside one burst
IDENTITY_MIN_BUCKETS = 12  # a short sample is cut into at least this many time buckets
IDENTITY_BUCKET_SHARE = 0.5  # most occurrences of an identity recur in separate hours
IDENTITY_VALUE_BUDGET = 2000  # effort budget: an identity field keys values up to this many
MAX_BEHAVIOURS = 200_000  # effort budget: rows kept in the behaviour table
EXAMPLE_CHARS = 2400  # effort budget: raw characters kept on one behaviour (fits JSON/XML bodies)
MAX_TERMS = 3  # effort budget: literal role values used to reproduce one behaviour
MISFIT_EXAMPLES = 3  # effort budget: sampled lines kept for one misfit shape
MISFIT_SHAPE_CAP = 4_000  # effort budget: distinct misfit shapes tracked per source
MISFIT_SHAPES_PER_SOURCE = 500  # effort budget: rarest misfit shapes stored per source
SHAPE_TOKENS = 40  # effort budget: tokens one misfit shape describes
SHAPE_CHARS = 200  # effort budget: characters kept on one misfit shape


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


BehaviourIdentity = tuple[str, ...]
_BEHAVIOUR_IDENTITY_COLUMNS = (
    "source_id",
    "actor_field",
    "actor",
    "action_field",
    "action",
    "object_field",
    "object",
    "actor_mode",
    "action_mode",
    "object_mode",
)


def behaviour_identity(behaviour: Behaviour) -> BehaviourIdentity:
    return tuple(str(getattr(behaviour, name)) for name in _BEHAVIOUR_IDENTITY_COLUMNS)


@dataclass(frozen=True)
class MisfitShape:
    """One distinct out-of-structure line shape seen in one source's read slice."""

    source_id: str
    shape: str
    events: int
    hosts: int
    first_seen: float
    last_seen: float
    examples: tuple[Mapping[str, Any], ...]


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
_MISFIT_COLUMNS = (
    "source_id VARCHAR, shape VARCHAR, events INTEGER, hosts INTEGER, "
    "first_seen DOUBLE, last_seen DOUBLE, examples VARCHAR"
)
_MISFIT_INSERT = "INSERT INTO misfits VALUES (" + ",".join("?" for _ in range(7)) + ")"
_MISFIT_STATS_COLUMNS = (
    "source_id VARCHAR, lines_read INTEGER, misfit_lines INTEGER, "
    "shapes INTEGER, shapes_kept INTEGER, shapes_dropped INTEGER"
)
_MISFIT_STATS_INSERT = "INSERT INTO misfit_stats VALUES (" + ",".join("?" for _ in range(6)) + ")"


def line_shape(raw: str) -> str:
    """A line's token-class shape: letters and digits generalised, punctuation kept."""
    tokens = []
    for token in raw.split()[:SHAPE_TOKENS]:
        tokens.append(
            "".join("a" if char.isalpha() else "9" if char.isdigit() else char for char in token)
        )
    return " ".join(tokens)[:SHAPE_CHARS]


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
    span = max((event.ts for event in events), default=0.0) - min(
        (event.ts for event in events), default=0.0
    )
    width = min(IDENTITY_BUCKET_SECONDS, max(60.0, span / IDENTITY_MIN_BUCKETS))
    for event in events:
        bucket = int(event.ts // width)
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


def _is_burst_identity(stat: FieldIdentity) -> bool:
    return (
        stat.identity
        or stat.distinct == 1
        or (stat.recurrence >= IDENTITY_RECURRENCE and stat.distinct <= IDENTITY_VALUE_BUDGET)
    )


def _choose(
    names: Sequence[str], stats: Mapping[str, FieldIdentity], role: str
) -> tuple[str, str, dict[str, Any] | None]:
    """The first field whose values behave like an identity, else the first present, generalised."""
    present = [name for name in names if name in stats and stats[name].present]
    if not present:
        return "", "", None
    qualifying = [name for name in present if stats[name].identity] or [
        name for name in present if _is_burst_identity(stats[name])
    ]
    chosen = qualifying[0] if qualifying else present[0]
    safe = _is_burst_identity(stats[chosen])
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


def _choose_with_fallback(
    primary: Sequence[str],
    fallback: Sequence[str],
    stats: Mapping[str, FieldIdentity],
    role: str,
    *,
    prefer_richer_fallback: bool = False,
) -> tuple[str, str, dict[str, Any] | None]:
    field_name, mode, override = _choose(primary, stats, role)
    if not field_name and fallback:
        return _choose(fallback, stats, role)
    if prefer_richer_fallback and field_name and stats[field_name].distinct <= 2 and fallback:
        fb_field, fb_mode, fb_override = _choose(fallback, stats, role)
        if fb_field and stats[fb_field].distinct > stats[field_name].distinct:
            return fb_field, fb_mode, fb_override
    return field_name, mode, override


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
        actor_field, actor_mode, actor_override = _choose_with_fallback(
            card.role_fields("actor"), card.role_fields("from"), stats, "actor"
        )
        action_field, action_mode, action_override = _choose(
            card.role_fields("action"), stats, "action"
        )
        object_field, object_mode, object_override = _choose_with_fallback(
            card.role_fields("object"),
            card.role_fields("to"),
            stats,
            "object",
            prefer_richer_fallback=True,
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
    selected = [value for value in terms if value][:MAX_TERMS]
    picked = [segment for value in selected for segment in _literal_term_segments(value)]
    tail = " " + " ".join(_quote(value) for value in picked) if picked else ""
    return f"search index={_quote(facts.index)} {route}{tail} | head 5"


def _window_for(ts: float, windows: Sequence[tuple[float, float]]) -> tuple[float, float]:
    for start, end in windows:
        if start <= ts < end:
            return start, end
    return windows[0] if windows else (ts, ts + 3600.0)


def _extract(
    card: SourceCard, rows: Sequence[Mapping[str, Any]], windows: Sequence[tuple[float, float]]
) -> tuple[list[ExampleEvent], set[int], int]:
    """Parsed in-part events, the row indexes this card claims, and rows its structure missed."""
    found: list[ExampleEvent] = []
    matched: set[int] = set()
    unparsed = 0
    for index, row in enumerate(rows):
        parsed = parse_row(str(row.get("_raw") or ""), card.fmt, card.columns, card.template_model)
        if not parsed.fields:
            unparsed += 1
            continue
        if not card.in_part(parsed.fields):
            continue
        matched.add(index)
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
    return found, matched, unparsed


def _row_time(row: Mapping[str, Any]) -> float:
    try:
        return float(row.get("_time") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def collect_misfits(
    source_id: str,
    rows: Sequence[Mapping[str, Any]],
    windows: Sequence[tuple[float, float]],
    claimed: set[int],
) -> tuple[list[MisfitShape], dict[str, int]]:
    """Group the rows no card of the source claimed by shape, rarest shapes kept."""
    shapes: dict[str, dict[str, Any]] = {}
    lines = 0
    dropped = 0
    for index, row in enumerate(rows):
        if index in claimed:
            continue
        raw = str(row.get("_raw") or "")
        if not raw.strip():
            continue
        lines += 1
        shape = line_shape(raw)
        ts = _row_time(row)
        slot = shapes.get(shape)
        if slot is None:
            if len(shapes) >= MISFIT_SHAPE_CAP:
                dropped += 1
                continue
            slot = shapes[shape] = {
                "events": 0,
                "hosts": set(),
                "first": ts,
                "last": ts,
                "examples": [],
            }
        slot["events"] += 1
        host = str(row.get("host") or "")
        if host:
            slot["hosts"].add(host)
        slot["first"] = min(float(slot["first"]), ts)
        slot["last"] = max(float(slot["last"]), ts)
        if len(slot["examples"]) < MISFIT_EXAMPLES:
            earliest, latest = _window_for(ts, windows)
            slot["examples"].append(
                {
                    "time": ts,
                    "host": host,
                    "raw": raw[:EXAMPLE_CHARS],
                    "earliest": earliest,
                    "latest": latest,
                }
            )
    ordered = sorted(shapes.items(), key=lambda item: (item[1]["events"], item[0]))
    kept = ordered[:MISFIT_SHAPES_PER_SOURCE]
    found = [
        MisfitShape(
            source_id,
            shape,
            int(slot["events"]),
            len(slot["hosts"]),
            float(slot["first"]),
            float(slot["last"]),
            tuple(slot["examples"]),
        )
        for shape, slot in kept
    ]
    stats = {
        "lines_read": len(rows),
        "misfit_lines": lines,
        "shapes": len(shapes),
        "shapes_kept": len(kept),
        "shapes_dropped": dropped + max(0, len(shapes) - len(kept)),
    }
    return found, stats


def role_fields(card: SourceCard) -> list[str]:
    return sorted(
        {
            *card.role_fields("actor"),
            *card.role_fields("action"),
            *card.role_fields("object"),
            *card.role_fields("from"),
            *card.role_fields("to"),
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


def create_misfits(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE TABLE misfits ({_MISFIT_COLUMNS})")
    con.execute(f"CREATE TABLE misfit_stats ({_MISFIT_STATS_COLUMNS})")


def _insert_misfits(
    con: duckdb.DuckDBPyConnection,
    source_id: str,
    shapes: Sequence[MisfitShape],
    stats: Mapping[str, int],
) -> None:
    if shapes:
        con.executemany(
            _MISFIT_INSERT,
            [
                (
                    item.source_id,
                    item.shape,
                    item.events,
                    item.hosts,
                    item.first_seen,
                    item.last_seen,
                    json.dumps([dict(example) for example in item.examples], sort_keys=True),
                )
                for item in shapes
            ],
        )
    con.execute(
        _MISFIT_STATS_INSERT,
        (
            source_id,
            int(stats.get("lines_read") or 0),
            int(stats.get("misfit_lines") or 0),
            int(stats.get("shapes") or 0),
            int(stats.get("shapes_kept") or 0),
            int(stats.get("shapes_dropped") or 0),
        ),
    )


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
    unparsed: int = 0,
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
        "events_out_of_structure": unparsed,
        "unparsed_share": round(unparsed / len(read.rows), 6) if read.rows else None,
        "windows": read.windows,
        "per_window": per_window,
        "selection": read.selection,
        "route": read.route,
        "share_of_source": round(len(read.rows) / facts.events, 6) if facts.events else None,
        "seconds": round(seconds, 3),
        "notes": read.notes,
    }


def _is_complete_source(facts: SourceFacts, per_window: int) -> bool:
    return 0 < facts.events <= per_window * BEHAVIOUR_WINDOWS and facts.source_count <= min(
        len(facts.sources), BEHAVIOUR_SOURCES
    )


def _select_source_bursts(
    per_source_z: Mapping[str, Sequence[tuple[float, float]]],
    bucket_shift: Mapping[float, float],
    limit: int,
) -> dict[str, list[tuple[float, float]]]:
    """Top raw-z and common-mode-residual-z four-hour burst buckets per source."""
    half = max(1, limit // 2)
    selected: dict[str, list[tuple[float, float]]] = {}
    for sourcetype, scored in per_source_z.items():
        raw_top = sorted(scored, key=lambda item: (-item[0], item[1]))
        res_top = sorted(scored, key=lambda item: (-(item[0] - bucket_shift[item[1]]), item[1]))
        chosen: list[float] = []
        for z_val, stamp in raw_top:
            if z_val > 0 and stamp not in chosen:
                chosen.append(stamp)
                if len(chosen) >= half:
                    break
        for z_val, stamp in res_top:
            if z_val - bucket_shift[stamp] > 0 and stamp not in chosen:
                chosen.append(stamp)
                if len(chosen) >= limit:
                    break
        if chosen:
            selected[sourcetype] = [
                (stamp, stamp + BEHAVIOUR_BURST_SPAN_SECONDS) for stamp in sorted(chosen)
            ]
    return selected


def _burst_windows_by_source(
    executor: HuntExecutor,
    scheduled: Sequence[tuple[str, list[SourceCard], SourceFacts, float]],
    per_window: int,
) -> dict[str, list[tuple[float, float]]]:
    """One four-hour tstats query to locate each sampled source's peak burst windows."""
    sampled = [
        facts for _sid, _grp, facts, _st in scheduled if not _is_complete_source(facts, per_window)
    ]
    if not sampled:
        return {}
    index = sampled[0].index
    start = min(facts.first for facts in sampled)
    end = max(facts.last for facts in sampled) + 0.000001
    query = f"| tstats count where index={_quote(index)} by sourcetype _time span=4h"
    try:
        result = executor.read(
            query, start, end, kind="behaviour_burst_plan", row_cap=BEHAVIOUR_BURST_SERIES_ROWS
        )
    except Exception:  # noqa: BLE001 -- burst planning is optional; fall back to uniform reads
        return {}
    by_source: dict[str, list[tuple[float, int]]] = {}
    for row in result.rows:
        name = str(row.get("sourcetype") or "")
        if not name:
            continue
        try:
            stamp = float(row.get("_time") or 0.0)
            count = int(float(row.get("count") or 0))
        except (TypeError, ValueError):
            continue
        by_source.setdefault(name, []).append((stamp, count))
    per_source_z: dict[str, list[tuple[float, float]]] = {}
    bucket_zs: dict[float, list[float]] = {}
    for name, series in by_source.items():
        if len(series) < 3:
            continue
        logs = [math.log1p(float(count)) for _stamp, count in series]
        med = statistics.median(logs)
        mad = statistics.median(abs(val - med) for val in logs)
        scored = [
            ((math.log1p(float(count)) - med) / (mad + 0.5), stamp) for stamp, count in series
        ]
        per_source_z[name] = scored
        for z_val, stamp in scored:
            bucket_zs.setdefault(stamp, []).append(z_val)
    bucket_shift = {
        stamp: max(0.0, statistics.median(vals)) if len(vals) >= 3 else 0.0
        for stamp, vals in bucket_zs.items()
    }
    return _select_source_bursts(per_source_z, bucket_shift, BEHAVIOUR_BURST_WINDOWS)


def _merge_row_sets(uniform: RowSet, burst: RowSet) -> RowSet:
    seen: set[tuple[float, str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in (*uniform.rows, *burst.rows):
        key = (_row_time(row), str(row.get("host") or ""), str(row.get("_raw") or ""))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    rows.sort(
        key=lambda row: (_row_time(row), str(row.get("host") or ""), str(row.get("_raw") or ""))
    )
    return RowSet(
        rows=rows,
        windows=uniform.windows + burst.windows,
        route=uniform.route,
        notes=[*uniform.notes, *burst.notes],
        selection="uniform baseline plus peak four-hour burst windows",
        query=uniform.query,
    )


def read_behaviour_source(
    executor: HuntExecutor,
    facts: SourceFacts,
    per_window: int,
    *,
    burst_windows: Sequence[tuple[float, float]] = (),
) -> RowSet:
    """Read a source whole when it fits, else mix uniform baseline and peak burst windows."""
    complete = _is_complete_source(facts, per_window)
    if complete or not burst_windows:
        read = read_windows(
            executor,
            facts,
            source_windows(facts, 1 if complete else BEHAVIOUR_WINDOWS),
            per_window=facts.events if complete else per_window,
            kind="behavior_events",
            max_sources=BEHAVIOUR_SOURCES,
            sub_windows=1 if complete else BEHAVIOUR_SUB_WINDOWS,
        )
        if complete:
            read.selection = "full source range within allocated row budget"
            if len(read.rows) != facts.events:
                read.notes.append(f"source_count_mismatch:{len(read.rows)}/{facts.events}")
        return read
    peaks = list(burst_windows[:BEHAVIOUR_BURST_WINDOWS])
    uniform_count = max(1, BEHAVIOUR_WINDOWS - len(peaks))
    uniform_read = read_windows(
        executor,
        facts,
        source_windows(facts, uniform_count),
        per_window=per_window,
        kind="behavior_events",
        max_sources=BEHAVIOUR_SOURCES,
        sub_windows=BEHAVIOUR_SUB_WINDOWS,
    )
    burst_read = read_windows(
        executor,
        facts,
        peaks,
        per_window=per_window,
        kind="behavior_events",
        max_sources=BEHAVIOUR_SOURCES,
        sub_windows=BEHAVIOUR_BURST_SUB_WINDOWS,
    )
    return _merge_row_sets(uniform_read, burst_read)


def _key_source(
    con: duckdb.DuckDBPyConnection,
    group: Sequence[SourceCard],
    facts: SourceFacts,
    per_window: int,
    executor: HuntExecutor,
    started: float,
    read: RowSet | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, dict[str, Any]], list[MisfitShape], dict[str, int]]:
    """Read one source once, key each structure's events, and keep its out-of-structure lines."""
    windows = source_windows(facts, BEHAVIOUR_WINDOWS)
    if read is None:
        read = read_behaviour_source(executor, facts, per_window)
    receipts: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, Any]] = {}
    total = 0
    claimed: set[int] = set()
    source_id = f"{facts.index}:{facts.sourcetype}"
    for card in group:
        events, matched, unparsed = _extract(card, read.rows, windows)
        claimed |= matched
        if "behaviours" not in card_consumers(card):
            continue
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
            unparsed,
        )
        receipt["identity"] = summary
        receipts.append(receipt)
    misfits, misfit_stats = collect_misfits(source_id, read.rows, windows, claimed)
    return receipts, total, overrides, misfits, misfit_stats


def _schedule_sources(
    grouped: Mapping[str, list[SourceCard]],
    facts_by_source: Mapping[str, SourceFacts],
    skipped: list[dict[str, Any]],
) -> list[tuple[str, list[SourceCard], SourceFacts, float]]:
    """The sources the stage will read, with every unreadable card's reason declared."""
    scheduled: list[tuple[str, list[SourceCard], SourceFacts, float]] = []
    for source_id, group in grouped.items():
        usable = [card for card in group if "behaviours" in card_consumers(card)]
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
        scheduled.append((source_id, group, facts, time.monotonic()))
    return scheduled


def _behaviour_receipt(
    behaviours: Sequence[Behaviour],
    receipts: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
    total: int,
    per_window: int,
    existed: int,
    misfit_receipts: list[dict[str, Any]],
    store_path: Path,
    began: float,
) -> dict[str, Any]:
    """Build the behaviour-stage receipt from its stored results."""
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
    return {
        "receipts": receipts,
        "skipped": skipped,
        "identity_overrides": overrides,
        "singletons": sum(singletons.values()),
        "events_read": total,
        "per_window": per_window,
        "behaviours_existed": existed,
        "behaviours_kept": len(behaviours),
        "misfits": misfit_receipts,
        "misfit_lines": sum(int(item.get("misfit_lines") or 0) for item in misfit_receipts),
        "misfit_shapes": sum(int(item.get("shapes_kept") or 0) for item in misfit_receipts),
        "misfit_sources": sum(1 for item in misfit_receipts if int(item.get("misfit_lines") or 0)),
        "store": str(store_path),
        "seconds": round(time.monotonic() - began, 3),
    }


def collect_behaviours(
    executor: HuntExecutor,
    cards: Sequence[SourceCard],
    facts_by_source: Mapping[str, SourceFacts],
    store_path: Path,
) -> tuple[list[Behaviour], dict[str, Any]]:
    """Read each activity source once, key each structure's events, and count on DuckDB."""
    began = time.monotonic()
    grouped = _source_groups(cards)
    usable_sources = sum(
        1
        for group in grouped.values()
        if any("behaviours" in card_consumers(card) for card in group)
    )
    skipped: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, Any]] = {}
    per_window = per_window_events(usable_sources)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.unlink(missing_ok=True)
    con = duckdb.connect(str(store_path))
    total = 0
    misfit_receipts: list[dict[str, Any]] = []
    try:
        create_events(con)
        create_misfits(con)
        scheduled = _schedule_sources(grouped, facts_by_source, skipped)
        burst_plan = _burst_windows_by_source(executor, scheduled, per_window)
        concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
        with ThreadPoolExecutor(max_workers=min(len(scheduled) or 1, concurrency)) as pool:
            futures = [
                pool.submit(
                    read_behaviour_source,
                    executor,
                    facts,
                    per_window,
                    burst_windows=burst_plan.get(facts.sourcetype, ()),
                )
                for _source_id, _group, facts, _started in scheduled
            ]
            reads = [future.result() for future in futures]
        for (source_id, group, facts, started), read in zip(scheduled, reads, strict=True):
            found, count, found_overrides, misfits, misfit_stats = _key_source(
                con, group, facts, per_window, executor, started, read
            )
            receipts.extend(found)
            overrides.update(found_overrides)
            total += count
            _insert_misfits(con, source_id, misfits, misfit_stats)
            misfit_receipts.append({"source_id": source_id, **misfit_stats})
        behaviours, existed = aggregate_events(con)
    finally:
        con.close()
    receipt = _behaviour_receipt(
        behaviours,
        receipts,
        skipped,
        overrides,
        total,
        per_window,
        existed,
        misfit_receipts,
        store_path,
        began,
    )
    return behaviours, receipt


def load_behaviours(path: Path) -> list[Behaviour]:
    """Read back the stored behaviour table for a later stage."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute("SELECT * FROM behaviours").fetchall()
    finally:
        con.close()
    return [Behaviour(*row) for row in rows]


def load_behaviour_peaks(path: Path, bucket_seconds: float) -> dict[BehaviourIdentity, int]:
    """Largest event bucket for every kept behaviour in the stored read slice."""
    key = list(_BEHAVIOUR_IDENTITY_COLUMNS)
    selected = ",".join(f"b.{name}" for name in key)
    joined = " AND ".join(f"e.{name}=b.{name}" for name in key)
    event_key = ",".join(f"e.{name}" for name in key)
    output_key = ",".join(key)
    query = f"""
    WITH eligible AS (SELECT {selected} FROM behaviours b),
    counts AS (
      SELECT {event_key}, floor(e.ts / ?) AS bucket, count(*) AS n
      FROM events e JOIN eligible b ON {joined}
      GROUP BY ALL
    ), peaks AS (
      SELECT {output_key}, max(n) AS peak FROM counts GROUP BY ALL
    )
    SELECT {output_key}, peak FROM peaks
    """
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute(query, [bucket_seconds]).fetchall()
    finally:
        con.close()
    return {tuple(str(value) for value in row[:-1]): int(row[-1]) for row in rows}


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


def load_misfits(path: Path) -> tuple[list[MisfitShape], dict[str, dict[str, Any]], list[str]]:
    """Stored out-of-structure shapes and per-source counts; a store without them declares it."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        tables = {str(row[0]) for row in con.execute("SHOW TABLES").fetchall()}
        if "misfits" not in tables or "misfit_stats" not in tables:
            return [], {}, ["no_misfit_table"]
        rows = con.execute(
            "SELECT source_id, shape, events, hosts, first_seen, last_seen, examples FROM misfits"
        ).fetchall()
        stat_rows = con.execute("SELECT * FROM misfit_stats").fetchall()
    finally:
        con.close()
    misfits = [
        MisfitShape(
            str(row[0]),
            str(row[1]),
            int(row[2]),
            int(row[3]),
            float(row[4]),
            float(row[5]),
            tuple(
                example
                for example in json.loads(str(row[6] or "[]"))
                if isinstance(example, Mapping)
            ),
        )
        for row in rows
    ]
    stats = {
        str(row[0]): {
            "lines_read": int(row[1]),
            "misfit_lines": int(row[2]),
            "shapes": int(row[3]),
            "shapes_kept": int(row[4]),
            "shapes_dropped": int(row[5]),
        }
        for row in stat_rows
    }
    return misfits, stats, []
