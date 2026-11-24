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
from ..executor import REQUEST_BUDGET_EXHAUSTED, HuntExecutor
from .cards import SourceCard, card_consumers
from .parse import parse_row
from .receipt import read_json, write_json
from .sample import (
    BEHAVIOUR_SOURCES,
    EMPTY_WINDOW,
    LOCALISE_WINDOWS,
    AccelSummary,
    Localisation,
    LocalWindow,
    RowSet,
    ScanCache,
    SourceFacts,
    accel_summaries,
    file_omitted,
    inclusive_end,
    localise,
    localise_width,
    read_files,
    read_mode,
    read_windows,
    route_filter,
    source_windows,
)
from .sample import (
    window_bounds as window_bounds,
)

BEHAVIOUR_WINDOWS = 12  # effort budget: time slices read per activity source
BEHAVIOUR_BURST_WINDOWS = 4  # peak four-hour slices reserved inside BEHAVIOUR_WINDOWS
BEHAVIOUR_SUB_WINDOWS = 2  # each uniform slice read at midpoint and tail when no bursts planned
BEHAVIOUR_UNIFORM_SUB_WINDOWS_WITH_BURSTS = (
    1  # 8*1 uniform + 4*4 burst keeps the exact 24-request ceiling per source
)
BEHAVIOUR_BURST_SUB_WINDOWS = (
    4  # hourly slices inside each peak four-hour burst window (same 24-req cap)
)
BEHAVIOUR_BURST_SPAN_SECONDS = 4 * 3600  # four-hour burst bucket width matching deviation
BEHAVIOUR_BURST_SERIES_ROWS = 40_000  # effort budget: per-period tstats rows for burst planning
BEHAVIOUR_EVENTS_PER_WINDOW = 2500  # effort budget: events read from one slice
SPLUNK_MAX_RESULT_ROWS = 10_000  # Splunk maxresultrows: one search silently caps here
_WHOLE_WINDOW_CEILING = SPLUNK_MAX_RESULT_ROWS
_WHOLE_BISECT_MAX_DEPTH = 12  # effort budget: adaptive whole-read bisection stops at this depth
_WHOLE_BISECT_MIN_WIDTH = 1.0  # a whole-read window narrower than one second is not split
_WHOLE_READ_REQUEST_CAP = 256  # effort budget: adaptive whole-read queries for one source
BEHAVIOUR_TOTAL_EVENTS = 400_000  # effort budget: parsed events across the whole stage
BEHAVIOUR_ANCHOR_MERGE_SECONDS = 300  # value spans closer than this are one anchor window
STRUCTURED_FORMATS = frozenset({"json", "xml", "kv", "delimited"})
UNSTRUCTURED_RAW_CHARS = 400  # effort budget: raw prefix kept for an unstructured event
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
BEHAVIOURS_CHECKPOINT_FILE = "behaviours_checkpoint.json"


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
    keep = EXAMPLE_CHARS if card.fmt in STRUCTURED_FORMATS else UNSTRUCTURED_RAW_CHARS
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
                str(row.get("_raw") or "")[:keep],
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
    return max(1, share // BEHAVIOUR_WINDOWS)


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
    read_mode: str = "sampled",
) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "source_id": card.source_id,
        "part": {"field": card.part_field, "value": card.part_value} if card.part_field else None,
        "kind": card.kind,
        "read_mode": read_mode,
        "events_available": facts.events,
        "events_read": len(read.rows),
        "events_scanned": read.events_scanned,
        "events_parsed": events,
        "events_keyed": keyed,
        "events_keyless": max(0, events - keyed),
        "events_out_of_structure": unparsed,
        "unparsed_share": round(unparsed / len(read.rows), 6) if read.rows else None,
        "windows": read.windows,
        "per_window": per_window,
        "selection": read.selection,
        "route": read.route,
        "rung": read.rung,
        "coverage": read.coverage,
        "accel_window": list(read.accel_window) if read.accel_window else None,
        "files_indexed": len(facts.files),
        "files_routed": len({item.path for item in read.files if not file_omitted(item)}),
        "files_omitted": len({item.path for item in read.files if file_omitted(item)}),
        "share_of_source": round(len(read.rows) / facts.events, 6) if facts.events else None,
        "read_fraction": round(len(read.rows) / facts.events, 6) if facts.events else None,
        "seconds": round(seconds, 3),
        "notes": read.notes,
    }


def _file_rows(source_id: str, read: RowSet) -> list[dict[str, Any]]:
    """One receipt line per (source, file, window), or per unread file with its reason."""
    return [
        {
            "source_id": source_id,
            "path": item.path,
            "host": item.host,
            "hosts": list(item.hosts),
            "events_available": item.events_available,
            "window_start": item.window_start,
            "window_end": item.window_end,
            "rows": item.rows,
            "reason": item.reason,
        }
        for item in read.files
    ]


def _is_complete_source(facts: SourceFacts, per_window: int) -> bool:
    """Whole-range read only when the source fits the row budget and the wide-source ceiling."""
    return (
        0 < facts.events <= per_window * BEHAVIOUR_WINDOWS
        and facts.source_count <= min(len(facts.sources), BEHAVIOUR_SOURCES)
        and read_mode(facts.events) == "whole"
    )


def _whole_window_count(events: int) -> int:
    """Time slices sized so no single whole-read query hits Splunk's maxresultrows ceiling."""
    return max(1, math.ceil(events / _WHOLE_WINDOW_CEILING))


def _whole_request_cap(executor: HuntExecutor) -> int:
    """Per-source fan-out bound, also cut by the shared request ceiling when one exists."""
    counter = getattr(getattr(executor, "budget", None), "remaining_requests", None)
    if not callable(counter):
        return _WHOLE_READ_REQUEST_CAP
    return max(0, min(_WHOLE_READ_REQUEST_CAP, int(counter())))


def _whole_blocked(read: RowSet) -> bool:
    """A failed or budget-stopped page is kept; splitting it would spend another search."""
    return any(
        note == REQUEST_BUDGET_EXHAUSTED or note.startswith("read_failed:") for note in read.notes
    )


def _whole_splits(read: RowSet, start: float, end: float, depth: int, slots: int) -> bool:
    """A full page is worth two halves only while width, depth and request slots allow it."""
    if len(read.rows) < _WHOLE_WINDOW_CEILING or slots < 2 or _whole_blocked(read):
        return False
    if depth >= _WHOLE_BISECT_MAX_DEPTH or (end - start) < _WHOLE_BISECT_MIN_WIDTH:
        return False
    mid = start + (end - start) / 2.0
    return start < mid < end


def _absorb_whole(found: RowSet, part: RowSet) -> None:
    found.rows.extend(part.rows)
    found.files.extend(part.files)
    found.notes.extend(part.notes)
    if not part.query:
        return
    found.windows += 1
    if not found.query:
        found.query = part.query
        found.route = part.route


def _read_whole_span(
    executor: HuntExecutor,
    facts: SourceFacts,
    start: float,
    end: float,
    depth: int,
    slots: int,
) -> tuple[list[RowSet], int]:
    """One half-open window; replace a ceiling-sized page with its two halves."""
    if slots <= 0 or end <= start:
        missed = RowSet()
        missed.notes.append("capped")
        return [missed], slots
    read = read_windows(
        executor,
        facts,
        [(start, end)],
        per_window=_WHOLE_WINDOW_CEILING,
        kind="behavior_events",
        max_sources=BEHAVIOUR_SOURCES,
    )
    slots -= 1
    if _whole_splits(read, start, end, depth, slots):
        mid = start + (end - start) / 2.0
        left, slots = _read_whole_span(executor, facts, start, mid, depth + 1, slots - 1)
        right, slots = _read_whole_span(executor, facts, mid, end, depth + 1, slots + 1)
        return [*left, *right], slots
    if len(read.rows) >= _WHOLE_WINDOW_CEILING:
        read.notes.append("capped")
    return [read], slots


def _read_whole_source(executor: HuntExecutor, facts: SourceFacts) -> RowSet:
    """Equal slices first; any slice that comes back full is bisected until it is not."""
    found = RowSet()
    slots = _whole_request_cap(executor)
    for start, end in source_windows(facts, _whole_window_count(facts.events)):
        parts, slots = _read_whole_span(executor, facts, start, end, 0, slots)
        for part in parts:
            _absorb_whole(found, part)
    found.rows.sort(
        key=lambda row: (_row_time(row), str(row.get("host") or ""), str(row.get("_raw") or ""))
    )
    return found


def anchor_windows(
    inventory: Mapping[str, Any], source_id: str, limit: int = BEHAVIOUR_WINDOWS
) -> list[tuple[float, float]]:
    """The source's own value spans from its stored lists, merged and capped by activity."""
    spans: list[tuple[float, float, int]] = []
    for record in inventory.get("fields") or ():
        if not isinstance(record, Mapping) or str(record.get("source_id")) != source_id:
            continue
        if str(record.get("status")) not in ("complete", "capped"):
            continue
        for value in record.get("values") or ():
            if not isinstance(value, Mapping):
                continue
            first = _time_value(value.get("first_seen"))
            last = _time_value(value.get("last_seen")) or first
            if last >= first:
                spans.append((first, inclusive_end(last), int(value.get("events") or 0)))
    if not spans:
        return []
    spans.sort()
    merged: list[tuple[float, float, int]] = []
    for first, last, events in spans:
        if merged and first <= merged[-1][1] + BEHAVIOUR_ANCHOR_MERGE_SECONDS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last), merged[-1][2] + events)
        else:
            merged.append((first, last, events))
    merged.sort(key=lambda span: (-span[2], span[0]))
    return [(first, last) for first, last, _events in sorted(merged[:limit])]


def _time_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def read_mode_of(facts: SourceFacts, per_window: int, anchors: Sequence[object]) -> str:
    """whole when the budget covered the source, anchored on any anchor windows, else sampled."""
    if _is_complete_source(facts, per_window):
        return "whole"
    return "anchored" if anchors else "sampled"


def _select_source_bursts(
    per_source_z: Mapping[str, Sequence[tuple[float, float]]],
    bucket_shift: Mapping[float, float],
    limit: int,
) -> dict[str, list[tuple[float, float]]]:
    """Top residual-z four-hour bursts per source, filled with remaining raw-z peaks."""
    half = max(1, limit // 2)
    selected: dict[str, list[tuple[float, float]]] = {}
    for sourcetype, scored in per_source_z.items():
        res_top = sorted(scored, key=lambda item: (-(item[0] - bucket_shift[item[1]]), item[1]))
        raw_top = sorted(scored, key=lambda item: (-item[0], item[1]))
        chosen: list[float] = []
        for z_val, stamp in res_top:
            if z_val - bucket_shift[stamp] > 0 and stamp not in chosen:
                chosen.append(stamp)
                if len(chosen) >= half:
                    break
        for z_val, stamp in raw_top:
            if z_val > 0 and stamp not in chosen:
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
    end = inclusive_end(max(facts.last for facts in sampled))
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


def _merge_row_sets(
    uniform: RowSet, burst: RowSet, burst_windows: Sequence[tuple[float, float]]
) -> RowSet:
    """Combine uniform and burst rows without double-counting overlapping windows or dropping ties."""
    covered = [
        (lo, hi) for lo, hi in burst_windows if any(lo <= _row_time(row) < hi for row in burst.rows)
    ]
    rows = [row for row in uniform.rows if not any(lo <= _row_time(row) < hi for lo, hi in covered)]
    rows.extend(burst.rows)
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
        files=[*uniform.files, *burst.files],
    )


def _merge_anchored(
    uniform: RowSet,
    anchored: RowSet,
    anchors: Sequence[LocalWindow],
    *,
    coverage: str = "scan",
    accel_window: tuple[float, float] | None = None,
) -> RowSet:
    """Uniform baseline plus rung-3 reads; a row an anchor already read is not counted twice."""
    rows = [
        row
        for row in uniform.rows
        if not any(
            anchor.host == str(row.get("host") or "")
            and anchor.start <= _row_time(row) < anchor.end
            for anchor in anchors
        )
    ]
    kept_uniform = len(rows)
    rows.extend(anchored.rows)
    rows.sort(
        key=lambda row: (_row_time(row), str(row.get("host") or ""), str(row.get("_raw") or ""))
    )
    found = RowSet(
        rows=rows,
        windows=uniform.windows + anchored.windows,
        route=uniform.route,
        notes=[*uniform.notes, *anchored.notes],
        selection="uniform baseline plus localised host/time windows",
        query=uniform.query,
        files=[*uniform.files, *anchored.files],
    )
    found.read_mode = "anchored"
    found.rung = "narrowed_scan"
    found.events_scanned = anchored.events_scanned + kept_uniform
    found.coverage = coverage
    found.accel_window = accel_window
    return found


def _behaviour_read_windows(
    facts: SourceFacts,
    per_window: int,
    burst_windows: Sequence[tuple[float, float]],
    anchors: Sequence[LocalWindow] = (),
    value_spans: Sequence[tuple[float, float]] = (),
) -> list[tuple[float, float]]:
    if _is_complete_source(facts, per_window):
        return source_windows(facts, 1)
    if anchors:
        localised = anchors[:LOCALISE_WINDOWS]
        return [
            *_anchored_uniform_windows(facts, len(localised)),
            *((anchor.start, anchor.end) for anchor in localised),
        ]
    if value_spans:
        return list(value_spans)
    if not burst_windows:
        return source_windows(facts, BEHAVIOUR_WINDOWS)
    peaks = list(burst_windows[:BEHAVIOUR_BURST_WINDOWS])
    uniform_count = max(1, BEHAVIOUR_WINDOWS - len(peaks))
    return [*source_windows(facts, uniform_count), *peaks]


def _anchored_uniform_windows(facts: SourceFacts, peaks: int) -> list[tuple[float, float]]:
    """Baseline slices that leave the per-source request ceiling to the anchored windows."""
    budget = BEHAVIOUR_WINDOWS * BEHAVIOUR_SUB_WINDOWS - peaks
    count = max(1, budget // BEHAVIOUR_SUB_WINDOWS)
    return source_windows(facts, count)


def read_behaviour_source(
    executor: HuntExecutor,
    facts: SourceFacts,
    per_window: int,
    *,
    burst_windows: Sequence[tuple[float, float]] = (),
    anchors: Sequence[LocalWindow] = (),
    value_spans: Sequence[tuple[float, float]] = (),
    accel_window: tuple[float, float] | None = None,
    coverage: str = "scan",
) -> RowSet:
    """Whole when it fits, else rung-2 windows, the source's value spans, bursts, uniform."""
    complete = _is_complete_source(facts, per_window)
    if complete:
        read = _read_whole_source(executor, facts)
        read.selection = "full source range within allocated row budget"
        read.read_mode = "whole"
        read.rung = "whole"
        read.events_scanned = facts.events
        read.coverage = "whole"
        if len(read.rows) != facts.events:
            read.notes.append(f"source_count_mismatch:{len(read.rows)}/{facts.events}")
        return read
    # sampled slices keep the per-read ceiling; only the whole read spends the full share
    per_window = min(per_window, BEHAVIOUR_EVENTS_PER_WINDOW)
    if anchors:
        return _read_anchored_source(executor, facts, per_window, anchors, accel_window, coverage)
    if value_spans:
        return _read_value_span_source(executor, facts, per_window, value_spans)
    if burst_windows:
        return _read_burst_source(executor, facts, per_window, burst_windows)
    read = read_files(
        executor,
        facts,
        source_windows(facts, BEHAVIOUR_WINDOWS),
        per_window=per_window,
        kind="behavior_events",
        sub_windows=BEHAVIOUR_SUB_WINDOWS,
    )
    return read


def _read_anchored_source(
    executor: HuntExecutor,
    facts: SourceFacts,
    per_window: int,
    anchors: Sequence[LocalWindow],
    accel_window: tuple[float, float] | None = None,
    coverage: str = "scan",
) -> RowSet:
    """Uniform baseline plus the host/time windows rung 2 selected."""
    peaks = list(anchors[:LOCALISE_WINDOWS])
    uniform_read = read_files(
        executor,
        facts,
        _anchored_uniform_windows(facts, len(peaks)),
        per_window=per_window,
        kind="behavior_events",
        sub_windows=BEHAVIOUR_SUB_WINDOWS,
    )
    anchored_read = _read_anchor_files(executor, facts, peaks, per_window)
    return _merge_anchored(
        uniform_read, anchored_read, peaks, coverage=coverage, accel_window=accel_window
    )


def _read_anchor_files(
    executor: HuntExecutor, facts: SourceFacts, anchors: Sequence[LocalWindow], per_window: int
) -> RowSet:
    """Rung 3 read of each localised host/time window, one file at a time."""
    found = RowSet(
        windows=len(anchors),
        route="source",
        selection="localised host/time windows from the indexed aggregate",
        query=f"search index=<index> source=<file> host=<localised host> | head {per_window}",
    )
    found.read_mode = "anchored"
    found.rung = "narrowed_scan"
    found.events_scanned = sum(anchor.events for anchor in anchors)
    found.coverage = "scan"
    for anchor in anchors:
        read = read_files(
            executor,
            facts,
            [(anchor.start, anchor.end)],
            per_window=per_window,
            kind="behavior_events",
            host=anchor.host,
        )
        found.rows.extend(read.rows)
        found.files.extend(read.files)
        found.notes.extend(read.notes)
    found.rows.sort(
        key=lambda row: (
            _row_time(row),
            str(row.get("host") or ""),
            str(row.get("_raw") or ""),
        )
    )
    return found


def _read_burst_source(
    executor: HuntExecutor,
    facts: SourceFacts,
    per_window: int,
    burst_windows: Sequence[tuple[float, float]],
) -> RowSet:
    """Uniform baseline plus peak four-hour slices when no rung-2 windows were produced."""
    peaks = list(burst_windows[:BEHAVIOUR_BURST_WINDOWS])
    uniform_count = max(1, BEHAVIOUR_WINDOWS - len(peaks))
    uniform_read = read_files(
        executor,
        facts,
        source_windows(facts, uniform_count),
        per_window=per_window,
        kind="behavior_events",
        sub_windows=BEHAVIOUR_UNIFORM_SUB_WINDOWS_WITH_BURSTS,
    )
    burst_read = read_files(
        executor,
        facts,
        peaks,
        per_window=per_window,
        kind="behavior_events",
        sub_windows=BEHAVIOUR_BURST_SUB_WINDOWS,
    )
    found = _merge_row_sets(uniform_read, burst_read, peaks)
    found.read_mode = "sampled"
    found.rung = "indexed_aggregate"
    found.events_scanned = len(found.rows)
    found.coverage = "scan"
    return found


def _read_value_span_source(
    executor: HuntExecutor,
    facts: SourceFacts,
    per_window: int,
    value_spans: Sequence[tuple[float, float]],
) -> RowSet:
    """S2's anchored read: the source's own inventory value spans, one read each."""
    read = read_files(
        executor,
        facts,
        value_spans,
        per_window=per_window,
        kind="behavior_events",
    )
    read.selection = "inventory value spans"
    read.read_mode = "anchored"
    read.rung = "value_spans"
    return read


def _key_source(
    con: duckdb.DuckDBPyConnection,
    group: Sequence[SourceCard],
    facts: SourceFacts,
    per_window: int,
    executor: HuntExecutor,
    started: float,
    read: RowSet | None = None,
    burst_windows: Sequence[tuple[float, float]] = (),
    anchors: Sequence[LocalWindow] = (),
    value_spans: Sequence[tuple[float, float]] = (),
) -> tuple[
    list[dict[str, Any]],
    int,
    dict[str, dict[str, Any]],
    list[MisfitShape],
    dict[str, int],
    list[dict[str, Any]],
]:
    """Read one source once, key each structure's events, and keep its out-of-structure lines."""
    windows = _behaviour_read_windows(facts, per_window, burst_windows, anchors, value_spans)
    if read is None:
        read = read_behaviour_source(
            executor,
            facts,
            per_window,
            burst_windows=burst_windows,
            anchors=anchors,
            value_spans=value_spans,
        )
    mode = read_mode_of(facts, per_window, anchors or value_spans)
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
            read_mode=mode,
        )
        receipt["identity"] = summary
        receipts.append(receipt)
    misfits, misfit_stats = collect_misfits(source_id, read.rows, windows, claimed)
    return receipts, total, overrides, misfits, misfit_stats, _file_rows(source_id, read)


def _localise_sources(
    executor: HuntExecutor,
    scheduled: Sequence[tuple[str, list[SourceCard], SourceFacts, float]],
    per_window: int,
) -> tuple[dict[str, Localisation], dict[str, Any]]:
    """Rung 1/2 once per wide source, over that source's own span: the windows it is narrowed to."""
    sampled = [
        (source_id, facts)
        for source_id, _grp, facts, _st in scheduled
        if not _is_complete_source(facts, per_window)
    ]
    if not sampled:
        return {}, {"windows": 0, "events": 0, "indexes": [], "notes": []}
    by_index: dict[str, list[tuple[str, SourceFacts]]] = {}
    for source_id, facts in sampled:
        by_index.setdefault(facts.index, []).append((source_id, facts))
    anchors: dict[str, Localisation] = {}
    indexes: list[dict[str, Any]] = []
    notes: list[str] = []
    for index, sources in sorted(by_index.items()):
        summaries, probe_notes = accel_summaries(executor, index)
        notes.extend(probe_notes)
        widths = {
            source_id: localise_width(facts.last - facts.first) for source_id, facts in sources
        }
        by_width: dict[float, list[SourceFacts]] = {}
        for source_id, facts in sources:
            by_width.setdefault(widths[source_id], []).append(facts)
        caches = {
            width: ScanCache(
                (
                    min(facts.first for facts in group),
                    inclusive_end(max(facts.last for facts in group)),
                )
            )
            for width, group in by_width.items()
        }
        for source_id, facts in sources:
            located = _localise_one(executor, index, facts, summaries, caches[widths[source_id]])
            notes.extend(located.notes)
            if located.windows:
                anchors[source_id] = located
            indexes.append(_localisation_entry(source_id, facts, located))
    return anchors, {
        "windows": sum(item["windows"] for item in indexes),
        "events": sum(item["events"] for item in indexes),
        "indexes": indexes,
        "notes": notes,
    }


def _localise_one(
    executor: HuntExecutor,
    index: str,
    facts: SourceFacts,
    summaries: Sequence[AccelSummary],
    scan_cache: ScanCache | None = None,
) -> Localisation:
    """A source's own `[first, last]` is the operand; the summary probe is shared per index."""
    width = localise_width(facts.last - facts.first)
    return localise(
        executor,
        index,
        facts.first,
        inclusive_end(facts.last),
        width=width,
        summaries=summaries,
        scan_cache=scan_cache,
    )


def _localisation_entry(
    source_id: str, facts: SourceFacts, located: Localisation
) -> dict[str, Any]:
    """One receipt row per wide source: a window here is that source's, never its index's."""
    return {
        "source": source_id,
        "sourcetype": facts.sourcetype,
        "index": facts.index,
        "width": localise_width(facts.last - facts.first),
        "hosts": len({window.host for window in located.windows}),
        "windows": len(located.windows),
        "events": sum(window.events for window in located.windows),
        "mechanism": located.mechanism,
        "model": located.model,
        "coverage": located.coverage,
        "accel_window": list(located.accel_window) if located.accel_window else None,
        "covered_window": list(located.covered_window) if located.covered_window else None,
        "scanned_window": [list(piece) for piece in located.scanned_window],
        "notes": located.notes,
    }


def _localisation_of(anchors: Mapping[str, Localisation], source_id: str) -> Localisation:
    """A missing source has no windows; it is never an error."""
    return anchors.get(source_id) or Localisation()


def _read_priority(
    item: tuple[str, list[SourceCard], SourceFacts, float],
) -> tuple[float, int, str, str]:
    """Peaked then wide sources are planned first, so the file plan inside them is paid first."""
    facts = item[2]
    size = sum(file.events for file in facts.files) or facts.events
    return (-facts.count_cv, -size, facts.index, facts.sourcetype)


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
    localisation: Mapping[str, Any] | None = None,
    file_rows: Sequence[Mapping[str, Any]] = (),
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
        "localisation": dict(localisation or {}),
        "files": [dict(item) for item in file_rows],
        "files_indexed": _files_counted(file_rows, "path"),
        "files_omitted": _files_omitted(file_rows),
        "events_scanned": sum(int(item.get("events_scanned") or 0) for item in receipts),
        "read_modes": {
            mode: sum(1 for item in receipts if item.get("read_mode") == mode)
            for mode in ("whole", "anchored", "sampled")
        },
        "store": str(store_path),
        "seconds": round(time.monotonic() - began, 3),
    }


def _files_counted(rows: Sequence[Mapping[str, Any]], key: str) -> int:
    """Distinct (source, file) pairs, or only those whose `key` is set."""
    return len(
        {(str(item.get("source_id")), str(item.get("path"))) for item in rows if item.get(key)}
    )


def _files_omitted(rows: Sequence[Mapping[str, Any]]) -> int:
    """Distinct (source, file) pairs the read policy declined; an empty window was still read."""
    return len(
        {
            (str(item.get("source_id")), str(item.get("path")))
            for item in rows
            if item.get("reason") and item.get("reason") != EMPTY_WINDOW
        }
    )


def _read_behaviour_batch(
    executor: HuntExecutor,
    scheduled: Sequence[tuple[str, list[SourceCard], SourceFacts, float]],
    per_window: int,
    value_spans: Mapping[str, Sequence[tuple[float, float]]],
) -> tuple[
    dict[str, Localisation], dict[str, Any], dict[str, list[tuple[float, float]]], list[RowSet]
]:
    anchors, localisation = _localise_sources(executor, scheduled, per_window)
    burst_plan = {} if anchors else _burst_windows_by_source(executor, scheduled, per_window)
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(scheduled) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                read_behaviour_source,
                executor,
                facts,
                per_window,
                burst_windows=burst_plan.get(facts.sourcetype, ()),
                anchors=_localisation_of(anchors, source_id).windows,
                accel_window=_localisation_of(anchors, source_id).accel_window,
                coverage=_localisation_of(anchors, source_id).coverage,
                value_spans=value_spans.get(source_id, ()),
            )
            for source_id, _group, facts, _started in scheduled
        ]
        reads = [future.result() for future in futures]
    return anchors, localisation, burst_plan, reads


def _source_incomplete(
    read: RowSet, receipts: Sequence[Mapping[str, Any]], files: Sequence[Mapping[str, Any]]
) -> bool:
    reasons = [*read.notes]
    reasons.extend(str(item.get("reason") or "") for item in files)
    for item in receipts:
        reasons.extend(str(reason) for reason in item.get("notes") or ())
    return any(
        reason == REQUEST_BUDGET_EXHAUSTED
        or reason == "capped"
        or reason.startswith("read_failed:")
        or "budget_exhausted" in reason
        or "deadline_exceeded" in reason
        for reason in reasons
    )


def _save_behaviour_checkpoint(
    path: Path,
    expected: Sequence[str],
    completed: set[str],
    results: Mapping[str, Mapping[str, Any]],
    localisation: Mapping[str, Any],
) -> dict[str, Any]:
    unfinished = sorted(set(expected) - completed)
    document = {
        "expected_sources": sorted(expected),
        "completed_sources": sorted(completed),
        "unfinished_sources": unfinished,
        "coverage_complete": not unfinished,
        "source_results": {source: dict(value) for source, value in results.items()},
        "localisation": dict(localisation),
    }
    write_json(path, document)
    return document


def _store_source_result(
    con: duckdb.DuckDBPyConnection,
    source_id: str,
    group: Sequence[SourceCard],
    facts: SourceFacts,
    per_window: int,
    executor: HuntExecutor,
    started: float,
    read: RowSet,
    burst_windows: Sequence[tuple[float, float]],
    anchors: Sequence[LocalWindow],
    value_spans: Sequence[tuple[float, float]],
) -> tuple[dict[str, Any], bool]:
    con.execute("DELETE FROM events WHERE source_id=?", [source_id])
    con.execute("DELETE FROM misfits WHERE source_id=?", [source_id])
    con.execute("DELETE FROM misfit_stats WHERE source_id=?", [source_id])
    found, total, overrides, misfits, stats, files = _key_source(
        con,
        group,
        facts,
        per_window,
        executor,
        started,
        read,
        burst_windows=burst_windows,
        anchors=anchors,
        value_spans=value_spans,
    )
    _insert_misfits(con, source_id, misfits, stats)
    con.commit()
    return {
        "receipts": found,
        "total": total,
        "overrides": overrides,
        "misfit_stats": stats,
        "files": files,
    }, _source_incomplete(read, found, files)


def _restore_probe_results(
    results: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    receipts = [
        dict(item)
        for result in results.values()
        for item in result.get("receipts") or ()
        if isinstance(item, Mapping)
    ]
    overrides = {
        str(card_id): dict(value)
        for result in results.values()
        for card_id, value in (result.get("overrides") or {}).items()
        if isinstance(value, Mapping)
    }
    misfits = [
        {"source_id": source_id, **dict(result.get("misfit_stats") or {})}
        for source_id, result in sorted(results.items())
    ]
    total = sum(int(result.get("total") or 0) for result in results.values())
    return receipts, overrides, misfits, total


def _prepare_behaviour_store(path: Path, resume: bool) -> duckdb.DuckDBPyConnection:
    if not resume:
        path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute(f"CREATE TABLE IF NOT EXISTS events ({_COLUMNS})")
    con.execute(f"CREATE TABLE IF NOT EXISTS misfits ({_MISFIT_COLUMNS})")
    con.execute(f"CREATE TABLE IF NOT EXISTS misfit_stats ({_MISFIT_STATS_COLUMNS})")
    for table in ("behaviour_all", "behaviours", "source_stats"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    return con


def _merge_localisation(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    indexes: dict[str, dict[str, Any]] = {}
    for item in (*previous.get("indexes", ()), *current.get("indexes", ())):
        if isinstance(item, Mapping):
            indexes[str(item.get("source") or "")] = dict(item)
    values = list(indexes.values())
    return {
        "windows": sum(int(item.get("windows") or 0) for item in values),
        "events": sum(int(item.get("events") or 0) for item in values),
        "indexes": values,
        "notes": [*previous.get("notes", ()), *current.get("notes", ())],
    }


def _process_behaviour_sources(
    con: duckdb.DuckDBPyConnection,
    executor: HuntExecutor,
    scheduled: Sequence[tuple[str, list[SourceCard], SourceFacts, float]],
    per_window: int,
    value_spans: Mapping[str, Sequence[tuple[float, float]]],
    checkpoint_path: Path,
    expected: Sequence[str],
    completed: set[str],
    results: dict[str, dict[str, Any]],
    prior_localisation: Mapping[str, Any],
) -> dict[str, Any]:
    _save_behaviour_checkpoint(checkpoint_path, expected, completed, results, prior_localisation)
    anchors, current_localisation, burst_plan, reads = _read_behaviour_batch(
        executor, scheduled, per_window, value_spans
    )
    localisation = _merge_localisation(prior_localisation, current_localisation)
    _save_behaviour_checkpoint(checkpoint_path, expected, completed, results, localisation)
    for (source_id, group, facts, started), read in zip(scheduled, reads, strict=True):
        located = _localisation_of(anchors, source_id)
        result, incomplete = _store_source_result(
            con,
            source_id,
            group,
            facts,
            per_window,
            executor,
            started,
            read,
            burst_plan.get(facts.sourcetype, ()),
            located.windows,
            value_spans.get(source_id, ()),
        )
        results[source_id] = result
        if incomplete:
            completed.discard(source_id)
        else:
            completed.add(source_id)
        _save_behaviour_checkpoint(checkpoint_path, expected, completed, results, localisation)
    return localisation


def collect_behaviours(
    executor: HuntExecutor,
    cards: Sequence[SourceCard],
    facts_by_source: Mapping[str, SourceFacts],
    store_path: Path,
    inventory: Mapping[str, Any] | None = None,
    *,
    resume: bool = False,
) -> tuple[list[Behaviour], dict[str, Any]]:
    """Read each activity source once, key each structure's events, and count on DuckDB."""
    began = time.monotonic()
    grouped = _source_groups(cards)
    stored_lists = inventory or {}
    usable_sources = sum(
        1
        for group in grouped.values()
        if any("behaviours" in card_consumers(card) for card in group)
    )
    skipped: list[dict[str, Any]] = []
    per_window = per_window_events(usable_sources)
    scheduled_all = sorted(_schedule_sources(grouped, facts_by_source, skipped), key=_read_priority)
    expected = sorted(item[0] for item in scheduled_all)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = store_path.parent / BEHAVIOURS_CHECKPOINT_FILE
    checkpoint = read_json(checkpoint_path) if resume else {}
    if checkpoint and checkpoint.get("expected_sources") != expected:
        checkpoint = {}
    if not resume:
        checkpoint_path.unlink(missing_ok=True)
    source_results = {
        str(source): dict(result)
        for source, result in (checkpoint.get("source_results") or {}).items()
        if isinstance(result, Mapping)
    }
    completed = {str(source) for source in checkpoint.get("completed_sources") or ()}
    if not store_path.exists():
        completed.clear()
        source_results.clear()
        checkpoint = {}
    keep_store = resume and store_path.exists() and bool(checkpoint)
    con = _prepare_behaviour_store(store_path, keep_store)
    value_spans: dict[str, list[tuple[float, float]]] = {
        source_id: anchor_windows(stored_lists, source_id) for source_id in grouped
    }
    scheduled = [item for item in scheduled_all if item[0] not in completed]
    completed.intersection_update(expected)
    try:
        localisation = _process_behaviour_sources(
            con,
            executor,
            scheduled,
            per_window,
            value_spans,
            checkpoint_path,
            expected,
            completed,
            source_results,
            checkpoint.get("localisation") or {},
        )
        behaviours, existed = aggregate_events(con)
    finally:
        con.close()
    receipts, overrides, misfit_receipts, total = _restore_probe_results(source_results)
    file_rows = [
        dict(item)
        for result in source_results.values()
        for item in result.get("files") or ()
        if isinstance(item, Mapping)
    ]
    final_checkpoint = _save_behaviour_checkpoint(
        checkpoint_path, expected, completed, source_results, localisation
    )
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
        localisation,
        file_rows,
    )
    receipt["completed_sources"] = final_checkpoint["completed_sources"]
    receipt["unfinished_sources"] = final_checkpoint["unfinished_sources"]
    receipt["coverage_complete"] = final_checkpoint["coverage_complete"]
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
