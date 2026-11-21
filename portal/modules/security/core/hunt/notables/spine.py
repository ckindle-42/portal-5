"""Entity spine and episodes: the join key over a run's stored events.

python -m portal.modules.security.core.hunt.notables.spine --out <run dir> \
    --family kyoushi --keys <keys.jsonl> --logs <gather dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .parse import parse_row
from .receipt import read_json, utc_now, write_json

SPINE_FILE = "entities.duckdb"
SPINE_RECEIPT = "spine.json"
STORE_FILE = "behaviours.duckdb"
PROGRESS_FILE = "progress.json"
EPISODE_MIN_GAP_SECONDS = 5 * 60.0  # a sub-five-minute gap never splits an episode
EPISODE_GAP_MULTIPLIER = 4.0  # an entity's own cadence: split beyond four median gaps
EPISODE_MAX_GAP_SECONDS = 4 * 3600.0  # accept-all effort budget: no episode spans more than 4h
NEIGHBOUR_WINDOW_SECONDS = 4 * 3600.0  # adjacency window for episodes on one host
EPISODE_OBJECTS = 100  # effort budget: distinct objects kept on one episode
ENTITY_VALUE_CHARS = 512  # effort budget: longest value a spine row keeps
USER_VALUE_BUDGET = 5000  # effort budget: a recurring field above this is not a user field
USER_RECURRENCE = 2.0  # a user field's values recur across the read slice

ADDRESS = "address"
HOSTNAME = "hostname"
USER = "user"
FILE = "file"
PROCESS = "process"
HASH = "hash"
REGISTRY = "registry"
DOMAIN = "domain"

_PROCESS_FIELDS = frozenset(
    {
        "image",
        "parent_image",
        "parentimage",
        "parent",
        "cmdline",
        "command_line",
        "command",
        "exe",
        "executable",
        "new_process_name",
        "process_name",
        "process",
        "program",
    }
)
_FILE_FIELDS = frozenset(
    {
        "path",
        "file",
        "filename",
        "file_name",
        "target",
        "cwd",
        "dir",
        "directory",
        "mount_point",
        "src_file",
        "dst_file",
        "attachment",
        "attach_filename",
    }
)
_USER_FIELDS = frozenset(
    {"user", "username", "account", "acct", "src_user", "dest_user", "account_name", "user_name"}
)
_HOST_FIELDS = frozenset(
    {"host", "hostname", "host_name", "src_host", "dest_host", "computer", "computer_name"}
)
_DOMAIN_FIELDS = frozenset({"query", "dns_query", "qname", "domain", "fqdn"})
_URL_FIELDS = frozenset({"url", "uri", "uri_path", "request", "referrer"})

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_IPV6 = re.compile(r"^(?=[0-9A-Fa-f:]*:)(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}$")
_HEX = re.compile(r"^(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$")
_HOSTNAME = re.compile(
    r"^(?=.{4,253}$)(?:[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.)+[A-Za-z]{2,24}\.?$"
)
_REGISTRY = re.compile(r"^[A-Za-z0-9_.-]+(?:\\[A-Za-z0-9_. -]+){2,}$")
_KEY_VALUE = re.compile(r"""([A-Za-z_][\w.:-]*)=("[^"]*"|'[^']*'|[^\s,;]+)""")
_TOKEN = re.compile(r"""[^\s,;()\[\]{}"']+""")
_USER_SHAPE = re.compile(r"^[A-Za-z0-9_.@-]+$")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class SpineEvent:
    """One read event, already parsed into the fields its card found."""

    event_id: str
    source_id: str
    part: str
    host: str
    ts: float
    raw: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class EntityHit:
    kind: str
    value: str
    class_token: str


@dataclass(frozen=True)
class Episode:
    episode_id: str
    kind: str
    value: str
    source_id: str
    part: str
    host: str
    start: float
    end: float
    event_ids: tuple[str, ...]
    objects: tuple[str, ...]


def event_id(source_id: str, host: str, ts: float, raw: str) -> str:
    """A content hash, stable across rebuilds and independent of store row order."""
    digest = hashlib.sha1(
        "\x1f".join((source_id, host, repr(float(ts)), raw)).encode("utf-8", "replace")
    )
    return digest.hexdigest()[:16]


def _clean(value: str) -> str:
    token = value.strip().strip("\"'").rstrip(".,;:")
    return token[:ENTITY_VALUE_CHARS]


def _is_ipv4(token: str) -> bool:
    return bool(_IPV4.match(token)) and all(int(part) <= 255 for part in token.split("."))


def _is_ipv6(token: str) -> bool:
    if not _IPV6.match(token):
        return False
    return (
        any(char.isalpha() for char in token)
        or len(token.split(":")) >= 4
        or token.startswith("::")
    )


def _is_address(token: str) -> bool:
    return _is_ipv4(token) or _is_ipv6(token)


def _hostname_shape(token: str) -> bool:
    return bool(_HOSTNAME.match(token)) and not _is_address(token)


def _multi_label_hostname(token: str) -> bool:
    """Three or more labels, the second-to-last not numeric: a dotted name, not a file basename."""
    labels = token.rstrip(".").split(".")
    if len(labels) < 3 or not all(re.fullmatch(r"[A-Za-z0-9_-]{1,63}", label) for label in labels):
        return False
    return not labels[-2].isdigit() and 2 <= len(labels[-1]) <= 24


def _file_shape(token: str) -> bool:
    path = token.split("?", 1)[0].split("#", 1)[0].rstrip("/\\")
    if not path:
        return False
    base = re.split(r"[/\\]", path)[-1]
    stem, dot, ext = base.rpartition(".")
    return bool(dot and stem and ext.isalpha() and 1 <= len(ext) <= 8)


def _registry_shape(token: str) -> bool:
    return bool(_REGISTRY.match(token)) and not _DRIVE.match(token) and not _file_shape(token)


def class_token(kind: str, value: str) -> str:
    """A derived class: file extension, URL/path shape or process basename; never a dictionary."""
    if kind == FILE:
        base = re.split(r"[/\\]", value.split("?", 1)[0].rstrip("/\\"))[-1]
        stem, dot, ext = base.rpartition(".")
        return f".{ext.casefold()}" if dot and stem and ext.isalpha() and len(ext) <= 8 else ""
    if kind == PROCESS:
        return re.split(r"[/\\]", value)[-1].casefold()
    return ""


def _field_kind(name: str) -> str | None:
    key = name.casefold().replace("-", "_")
    if key in _PROCESS_FIELDS:
        return PROCESS
    if key in _FILE_FIELDS:
        return FILE
    if key in _USER_FIELDS:
        return USER
    if key in _DOMAIN_FIELDS:
        return DOMAIN
    if key in _HOST_FIELDS:
        return HOSTNAME
    if key in _URL_FIELDS:
        return FILE
    return None


def _shape_kind(token: str) -> str | None:
    if _HEX.match(token):
        return HASH
    if _is_address(token):
        return ADDRESS
    if _registry_shape(token):
        return REGISTRY
    if _multi_label_hostname(token):
        return HOSTNAME
    if _file_shape(token):
        return FILE
    if _hostname_shape(token):
        return HOSTNAME
    return None


def _strip_port(token: str) -> str:
    """A host:port token carries its host; a bare name:value pair does not."""
    head, separator, port = token.partition(":")
    if not separator or not port.isdigit():
        return token
    return head if _is_address(head) or _hostname_shape(head) else token


def classify(name: str, value: str) -> EntityHit | None:
    """The entity a field value carries, by shape first and by the field's structural kind."""
    token = _strip_port(_clean(value))
    if token.count("@") == 1:
        token = token.split("@")[-1]
    if len(token) < 2 or any(char.isspace() for char in token):
        return None
    field_kind = _field_kind(name)
    kind = HASH if _HEX.match(token) else ADDRESS if _is_address(token) else None
    if kind is None and field_kind in (PROCESS, FILE, USER):
        kind = field_kind
    if kind is None:
        kind = _shape_kind(token)
    if kind == HOSTNAME and field_kind == DOMAIN:
        kind = DOMAIN
    if kind is None and field_kind in (DOMAIN, HOSTNAME):
        kind = field_kind
    if kind is None:
        return None
    return EntityHit(kind, token, class_token(kind, token))


def _pairs(text: str, depth: int = 0) -> Iterable[tuple[str, str]]:
    """Key=value pairs, including the pairs nested inside a quoted value, bounded by depth."""
    for name, value in _KEY_VALUE.findall(text):
        yield name, value
        if depth < 2 and "=" in value:
            yield from _pairs(value, depth + 1)


def _scan_tokens(raw: str) -> Iterable[tuple[str, str]]:
    """Field pairs and bare tokens a raw line exposes, for lines no card field captured."""
    yield from _pairs(raw)
    for token in _TOKEN.findall(raw):
        if "=" in token:
            continue
        yield "", token.split("@")[-1] if token.count("@") == 1 else token


def entities_for(
    event: SpineEvent, field_kinds: Mapping[tuple[str, str], str] | None = None
) -> list[EntityHit]:
    """Every entity one event carries, deduplicated in first-seen order."""
    found: dict[tuple[str, str], EntityHit] = {}
    overrides = field_kinds or {}
    for name, value in event.fields.items():
        kind = overrides.get((event.source_id, name))
        hit = EntityHit(kind, _clean(value), class_token(kind, _clean(value))) if kind else None
        if hit is None:
            hit = classify(name, value)
            for _nested_name, nested in _pairs(value):
                nested_hit = classify(_nested_name, nested)
                if nested_hit is not None:
                    found.setdefault((nested_hit.kind, nested_hit.value), nested_hit)
        if hit is not None:
            found.setdefault((hit.kind, hit.value), hit)
    for name, value in _scan_tokens(event.raw):
        hit = classify(name, value)
        if hit is not None:
            found.setdefault((hit.kind, hit.value), hit)
    return list(found.values())


def field_kinds(
    events: Sequence[SpineEvent],
    roles: Mapping[tuple[str, str], str] | None = None,
) -> dict[tuple[str, str], str]:
    """Fields whose values recur and are not addresses or shapes behave like user fields."""
    values: dict[tuple[str, str], set[str]] = defaultdict(set)
    presence: dict[tuple[str, str], int] = defaultdict(int)
    for event in events:
        for name, value in event.fields.items():
            key = (event.source_id, name)
            presence[key] += 1
            if len(values[key]) <= USER_VALUE_BUDGET:
                values[key].add(_clean(value))
    chosen: dict[tuple[str, str], str] = {}
    for key, seen in values.items():
        if not _may_hold_a_user(key, roles):
            continue
        distinct = len(seen)
        if not 2 <= distinct <= USER_VALUE_BUDGET:
            continue
        if presence[key] / distinct < USER_RECURRENCE:
            continue
        bare = sum(1 for value in seen if _user_shaped(value))
        if bare / distinct < 0.9:
            continue
        chosen[key] = USER
    return chosen


def _may_hold_a_user(key: tuple[str, str], roles: Mapping[tuple[str, str], str] | None) -> bool:
    if _field_kind(key[1]) is not None:
        return False
    if roles is None:
        return True
    return roles.get(key) in ("actor", "to", "object")


def _user_shaped(value: str) -> bool:
    return bool(_USER_SHAPE.match(value)) and any(char.isalpha() for char in value)


def segments(times: Sequence[float]) -> list[tuple[int, int]]:
    """Split an entity's ordered events where its own gap exceeds max(5m, 4 x median), or 4h."""
    if not times:
        return []
    gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    median = statistics.median(gaps) if gaps else 0.0
    threshold = min(
        EPISODE_MAX_GAP_SECONDS, max(EPISODE_MIN_GAP_SECONDS, EPISODE_GAP_MULTIPLIER * median)
    )
    bounds: list[tuple[int, int]] = []
    start = 0
    for index, gap in enumerate(gaps, 1):
        if gap > threshold:
            bounds.append((start, index))
            start = index
    bounds.append((start, len(times)))
    return bounds


def _episode_objects(
    event_ids: Sequence[str], hits: Mapping[str, Sequence[EntityHit]], kind: str, value: str
) -> tuple[str, ...]:
    objects: dict[str, None] = {}
    for identifier in event_ids:
        for hit in hits.get(identifier, ()):
            if (hit.kind, hit.value) != (kind, value):
                objects.setdefault(f"{hit.kind}:{hit.value}", None)
            if len(objects) >= EPISODE_OBJECTS:
                return tuple(objects)
    return tuple(objects)


def _episodes_for_group(
    key: tuple[str, str, str, str],
    points: Sequence[tuple[float, str]],
    hits: Mapping[str, Sequence[EntityHit]],
) -> list[Episode]:
    kind, value, source_id, part = key
    ordered = sorted(points)
    times = [ts for ts, _identifier in ordered]
    found: list[Episode] = []
    for index, (start, end) in enumerate(segments(times)):
        ids = tuple(identifier for _ts, identifier in ordered[start:end])
        objects = _episode_objects(ids, hits, kind, value)
        identifier = hashlib.sha1(
            "\x1f".join((kind, value, source_id, part, repr(times[start]))).encode(
                "utf-8", "replace"
            )
        ).hexdigest()[:16]
        found.append(
            Episode(
                f"{identifier}-{index}",
                kind,
                value,
                source_id,
                part,
                "",
                times[start],
                times[end - 1],
                ids,
                objects,
            )
        )
    return found


def _with_hosts(episodes: Sequence[Episode], hosts: Mapping[str, str]) -> list[Episode]:
    return [
        Episode(
            item.episode_id,
            item.kind,
            item.value,
            item.source_id,
            item.part,
            hosts.get(item.episode_id, ""),
            item.start,
            item.end,
            item.event_ids,
            item.objects,
        )
        for item in episodes
    ]


def neighbours(
    episodes: Sequence[Episode],
) -> dict[str, tuple[str, str, float, str, str, float]]:
    """Per episode: the nearest earlier and later episode of another source on its host in 4h."""
    by_host: dict[str, list[Episode]] = defaultdict(list)
    for item in episodes:
        if item.host:
            by_host[item.host].append(item)
    found: dict[str, tuple[str, str, float, str, str, float]] = {}
    for _host, group in by_host.items():
        ordered = sorted(group, key=lambda item: (item.start, item.episode_id))
        for index, item in enumerate(ordered):
            before = next(
                (
                    other
                    for other in reversed(ordered[:index])
                    if other.source_id != item.source_id
                    and item.start - other.start <= NEIGHBOUR_WINDOW_SECONDS
                ),
                None,
            )
            after = next(
                (
                    other
                    for other in ordered[index + 1 :]
                    if other.source_id != item.source_id
                    and other.start - item.start <= NEIGHBOUR_WINDOW_SECONDS
                ),
                None,
            )
            found[item.episode_id] = (
                before.episode_id if before else "",
                before.source_id if before else "",
                round(item.start - before.start, 3) if before else 0.0,
                after.episode_id if after else "",
                after.source_id if after else "",
                round(after.start - item.start, 3) if after else 0.0,
            )
    return found


def _write_rows(
    con: duckdb.DuckDBPyConnection, statement: str, rows: Sequence[tuple[Any, ...]]
) -> None:
    for start in range(0, len(rows), 5000):
        con.executemany(statement, rows[start : start + 5000])


def _create_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        "CREATE TABLE entities (entity_kind VARCHAR, value VARCHAR, source_id VARCHAR,"
        " part VARCHAR, events INTEGER, first_seen DOUBLE, last_seen DOUBLE, hosts INTEGER,"
        " sources INTEGER, class_token VARCHAR)"
    )
    con.execute(
        "CREATE TABLE episodes (episode_id VARCHAR, entity_kind VARCHAR, value VARCHAR,"
        " source_id VARCHAR, part VARCHAR, host VARCHAR, start_time DOUBLE, end_time DOUBLE,"
        " events INTEGER, event_ids VARCHAR, objects VARCHAR, prev_source VARCHAR,"
        " next_source VARCHAR, delta DOUBLE)"
    )
    con.execute(
        "CREATE TABLE episode_links (episode_id VARCHAR, neighbour_id VARCHAR, host VARCHAR,"
        " delta DOUBLE)"
    )
    con.execute("CREATE TABLE event_index (event_id VARCHAR, entity_kind VARCHAR, value VARCHAR)")


def _write_spine(
    con: duckdb.DuckDBPyConnection,
    entities: Mapping[tuple[str, str, str, str], dict[str, Any]],
    episodes: Sequence[Episode],
    hits: Mapping[str, Sequence[EntityHit]],
    links: Mapping[str, tuple[str, str, float, str, str, float]],
) -> None:
    _create_tables(con)
    source_counts: dict[tuple[str, str], set[str]] = defaultdict(set)
    for kind, value, source_id, _part in entities:
        source_counts[(kind, value)].add(source_id)
    _write_rows(
        con,
        "INSERT INTO entities VALUES (" + ",".join("?" for _ in range(10)) + ")",
        [
            (
                kind,
                value,
                source_id,
                part,
                stats["events"],
                stats["first"],
                stats["last"],
                len(stats["hosts"]),
                len(source_counts[(kind, value)]),
                stats["class_token"],
            )
            for (kind, value, source_id, part), stats in entities.items()
        ],
    )
    empty_link: tuple[str, str, float, str, str, float] = ("", "", 0.0, "", "", 0.0)
    episode_rows = []
    for item in episodes:
        before_id, before, before_delta, after_id, after, after_delta = links.get(
            item.episode_id, empty_link
        )
        episode_rows.append(
            (
                item.episode_id,
                item.kind,
                item.value,
                item.source_id,
                item.part,
                item.host,
                item.start,
                item.end,
                len(item.event_ids),
                json.dumps(list(item.event_ids)),
                json.dumps(list(item.objects)),
                before,
                after,
                after_delta or before_delta,
            )
        )
    _write_rows(
        con,
        "INSERT INTO episodes VALUES (" + ",".join("?" for _ in range(14)) + ")",
        episode_rows,
    )
    by_id = {item.episode_id: item for item in episodes}
    link_rows: list[tuple[Any, ...]] = []
    for identifier in sorted(links):
        item = by_id[identifier]
        before_id, _before, before_delta, after_id, _after, after_delta = links[identifier]
        if before_id:
            link_rows.append((identifier, before_id, item.host, before_delta))
        if after_id:
            link_rows.append((identifier, after_id, item.host, after_delta))
    _write_rows(
        con,
        "INSERT INTO episode_links VALUES (" + ",".join("?" for _ in range(4)) + ")",
        link_rows,
    )
    _write_rows(
        con,
        "INSERT INTO event_index VALUES (" + ",".join("?" for _ in range(3)) + ")",
        [(identifier, hit.kind, hit.value) for identifier, items in hits.items() for hit in items],
    )


def build_spine(
    events: Sequence[SpineEvent],
    out_path: Path,
    roles: Mapping[tuple[str, str], str] | None = None,
) -> dict[str, Any]:
    """Write entities.duckdb from read events: entity rows, episodes and neighbour links."""
    began = time.monotonic()
    overrides = field_kinds(events, roles)
    hits: dict[str, list[EntityHit]] = {}
    host_of_event: dict[str, str] = {event.event_id: event.host for event in events}
    groups: dict[tuple[str, str, str, str], list[tuple[float, str]]] = defaultdict(list)
    entities: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    per_source: dict[str, dict[str, int]] = defaultdict(
        lambda: {"events": 0, "events_without_entity": 0, "entities": 0, "episodes": 0}
    )
    without_entity = 0
    for event in events:
        found = entities_for(event, overrides)
        hits[event.event_id] = found
        per_source[event.source_id]["events"] += 1
        if not found:
            without_entity += 1
            per_source[event.source_id]["events_without_entity"] += 1
        for hit in found:
            key = (hit.kind, hit.value, event.source_id, event.part)
            groups[key].append((event.ts, event.event_id))
            per_source[event.source_id]["entities"] += 1
            stats = entities.setdefault(
                key,
                {
                    "events": 0,
                    "first": event.ts,
                    "last": event.ts,
                    "hosts": set(),
                    "class_token": hit.class_token,
                },
            )
            stats["events"] += 1
            stats["first"] = min(stats["first"], event.ts)
            stats["last"] = max(stats["last"], event.ts)
            if event.host:
                stats["hosts"].add(event.host)
    episodes: list[Episode] = []
    host_of: dict[str, str] = {}
    for (kind, value, source_id, part), points in groups.items():
        for item in _episodes_for_group((kind, value, source_id, part), points, hits):
            episodes.append(item)
            per_source[source_id]["episodes"] += 1
            hosts = [host_of_event.get(identifier) for identifier in item.event_ids]
            present = [host for host in hosts if host]
            host_of[item.episode_id] = (
                sorted(present, key=lambda host: (-present.count(host), host))[0] if present else ""
            )
    episodes = _with_hosts(episodes, host_of)
    links = neighbours(episodes)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    con = duckdb.connect(str(out_path))
    try:
        _write_spine(con, entities, episodes, hits, links)
    finally:
        con.close()
    kinds: dict[str, int] = defaultdict(int)
    for kind, _value, _source_id, _part in entities:
        kinds[kind] += 1
    return {
        "file": str(out_path),
        "generated": utc_now(),
        "events": len(events),
        "events_without_entity": without_entity,
        "entities": len(entities),
        "episodes": len(episodes),
        "links": sum(
            1
            for before, _b, _bd, after, _a, _ad in links.values()
            for present in (before, after)
            if present
        ),
        "kinds": dict(sorted(kinds.items())),
        "fields_typed": len(overrides),
        "sources": {source: dict(stats) for source, stats in sorted(per_source.items())},
        "seconds": round(time.monotonic() - began, 3),
        "segmentation": {
            "min_gap_seconds": EPISODE_MIN_GAP_SECONDS,
            "gap_multiplier": EPISODE_GAP_MULTIPLIER,
            "max_gap_seconds": EPISODE_MAX_GAP_SECONDS,
            "neighbour_window_seconds": NEIGHBOUR_WINDOW_SECONDS,
        },
    }


def read_mode(receipt: Mapping[str, Any]) -> str:
    """whole when the allocated budget covered the source, anchored on a value span, else sampled."""
    stored = str(receipt.get("read_mode") or "")
    if stored in ("whole", "anchored", "sampled"):
        return stored
    selection = str(receipt.get("selection") or "")
    if selection.startswith("full source range"):
        return "whole"
    if selection.startswith("inventory"):
        return "anchored"
    return "sampled"


def _behaviour_receipts(
    out: Path, receipts: Sequence[Mapping[str, Any]] | None
) -> Sequence[Mapping[str, Any]]:
    if receipts is not None:
        return receipts
    stages = read_json(out / PROGRESS_FILE).get("stages") or {}
    return (stages.get("behaviours") or {}).get("receipts") or ()


def read_modes(
    out: Path, receipts: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, dict[str, str]]:
    """Per source: how its read was chosen, from a fresh or a stored behaviour receipt."""
    found: dict[str, dict[str, str]] = {}
    for item in _behaviour_receipts(out, receipts):
        source_id = str(item.get("source_id") or "")
        if not source_id or source_id in found:
            continue
        found[source_id] = {
            "read_mode": read_mode(item),
            "read_mode_source": "receipt" if item.get("read_mode") else "selection",
        }
    return found


def _card_for(cards: Sequence[Any], raw: str) -> tuple[Mapping[str, str], str]:
    for card in cards:
        parsed = parse_row(raw, card.fmt, card.columns, card.template_model)
        if parsed.fields and card.in_part(parsed.fields):
            return parsed.fields, str(card.part_value or "")
    return {}, ""


def _roles_of(cards: Iterable[Any]) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for card in cards:
        for role in ("actor", "to", "object"):
            for name in card.roles.get(role, ()):
                found.setdefault((card.source_id, name), role)
    return found


def events_from_store(out: Path, store: Path | None = None) -> list[SpineEvent]:
    """Re-read the behaviour store's events, parsing each back into its card's fields."""
    from .run import load_cards

    counted: dict[str, list[Any]] = defaultdict(list)
    for card in load_cards(out):
        counted[card.source_id].append(card)
    path = store or out / STORE_FILE
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute("SELECT source_id, host, ts, raw FROM events").fetchall()
    finally:
        con.close()
    events: list[SpineEvent] = []
    for source_id, host, ts, raw in rows:
        text = str(raw or "")
        fields, part = _card_for(counted.get(str(source_id), ()), text)
        events.append(
            SpineEvent(
                event_id(str(source_id), str(host or ""), float(ts or 0.0), text),
                str(source_id),
                part,
                str(host or ""),
                float(ts or 0.0),
                text,
                fields,
            )
        )
    return events


def spine_from_store(
    out: Path,
    store: Path | None = None,
    receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build entities.duckdb for one run directory and write its spine receipt."""
    from .run import load_cards

    events = events_from_store(out, store)
    roles = _roles_of(load_cards(out))
    receipt = build_spine(events, out / SPINE_FILE, roles)
    stored = _behaviour_receipts(out, receipts)
    modes = read_modes(out, stored)
    shares: dict[str, Any] = {}
    for item in stored:
        shares.setdefault(str(item.get("source_id") or ""), item.get("share_of_source"))
    for source_id, row in receipt["sources"].items():
        row["read_mode"] = modes.get(source_id, {}).get("read_mode", "")
        row["read_fraction"] = shares.get(source_id)
    receipt["read_modes"] = modes
    write_json(out / SPINE_RECEIPT, receipt)
    return receipt


def _labelled_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"keys not found: {path}")
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        stored = json.loads(raw)
        if "dataset" in stored:
            raise ValueError(f"{path} holds entity keys, not per-line keys")
        rows.append(stored)
    if not rows:
        raise ValueError(f"keys {path} hold no labelled line")
    return rows


def _stored_events(out: Path) -> dict[str, list[tuple[str, str, float]]]:
    con = duckdb.connect(str(out / STORE_FILE), read_only=True)
    try:
        rows = con.execute("SELECT source_id, host, ts, raw FROM events").fetchall()
    finally:
        con.close()
    found: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for source_id, host, ts, raw in rows:
        found[str(raw or "")].append((str(source_id), str(host or ""), float(ts or 0.0)))
    return found


def _event_index(out: Path) -> dict[str, set[tuple[str, str]]]:
    con = duckdb.connect(str(out / SPINE_FILE), read_only=True)
    try:
        rows = con.execute("SELECT event_id, entity_kind, value FROM event_index").fetchall()
    finally:
        con.close()
    found: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for identifier, kind, value in rows:
        found[str(identifier)].add((str(kind), str(value)))
    return found


def _episode_index(out: Path) -> dict[str, set[str]]:
    con = duckdb.connect(str(out / SPINE_FILE), read_only=True)
    try:
        rows = con.execute("SELECT entity_kind, value, event_ids FROM episodes").fetchall()
    finally:
        con.close()
    found: dict[str, set[str]] = defaultdict(set)
    for kind, value, event_ids in rows:
        for identifier in json.loads(str(event_ids or "[]")):
            found[str(identifier)].add(f"{kind}:{value}")
    return found


def verify_steps(
    out: Path, family: str, keys_path: Path, logs: Path | None = None
) -> dict[str, Any]:
    """Per graded step: its read labelled lines, carrier entities and episode containment."""
    from .knowledge import PROOF_INDEXES

    if family in PROOF_INDEXES:
        raise ValueError(f"{family!r} is a proof index; it is never verified here")
    keys = _labelled_lines(keys_path)
    store = _stored_events(out)
    episodes = _episode_index(out)
    carried = _event_index(out)
    wanted: dict[tuple[str, str], dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in keys:
        for label in row.get("labels") or ():
            wanted[(str(row["host"]), str(row["source"]))][int(row["line"])].append(str(label))
    steps: dict[str, dict[str, Any]] = {}
    for (host, source), lines in sorted(wanted.items()):
        path = (logs or logs_from_keys(keys_path)) / host / "logs" / source.lstrip("/")
        if not path.is_file():
            raise FileNotFoundError(f"keys name {host}{source} but {path} is not there")
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                labels = lines.get(number)
                if labels is None:
                    continue
                for label in labels:
                    step = steps.setdefault(label, _empty_step(label))
                    _score_line(step, raw.rstrip("\r\n"), store, episodes, carried)
    for step in steps.values():
        step["pass"] = bool(step["lines_read"]) and step["lines_with_episode"] == step["lines_read"]
        step["cause"] = _step_cause(step)
        step["carrier_entities"] = sorted(step.pop("_entities"))[:5]
    return {
        "family": family,
        "file": str(keys_path),
        "steps": len(steps),
        "steps_read": sum(1 for step in steps.values() if step["lines_read"]),
        "steps_pass": sum(1 for step in steps.values() if step["pass"]),
        "lines_read": sum(step["lines_read"] for step in steps.values()),
        "lines_with_episode": sum(step["lines_with_episode"] for step in steps.values()),
        "lines_without_entity": sum(step["lines_without_entity"] for step in steps.values()),
        "per_step": [steps[label] for label in sorted(steps)],
    }


def _empty_step(label: str) -> dict[str, Any]:
    return {
        "step": label,
        "lines": 0,
        "lines_read": 0,
        "lines_with_episode": 0,
        "lines_without_entity": 0,
        "_entities": set(),
    }


def _score_line(
    step: dict[str, Any],
    text: str,
    store: Mapping[str, list[tuple[str, str, float]]],
    episodes: Mapping[str, set[str]],
    carried: Mapping[str, set[tuple[str, str]]],
) -> None:
    step["lines"] += 1
    stored = store.get(text)
    if not stored:
        return
    step["lines_read"] += 1
    identifiers = [event_id(source_id, host, ts, text) for source_id, host, ts in stored]
    entities: set[tuple[str, str]] = set()
    for identifier in identifiers:
        entities.update(carried.get(identifier, set()))
    if not entities:
        step["lines_without_entity"] += 1
        return
    step["_entities"].update(f"{kind}:{value}" for kind, value in entities)
    named = {f"{kind}:{value}" for kind, value in entities}
    if any(identifier in episodes for identifier in identifiers):
        present = {entity for identifier in identifiers for entity in episodes.get(identifier, ())}
        if present & named:
            step["lines_with_episode"] += 1


def _step_cause(step: Mapping[str, Any]) -> str:
    if not step["lines_read"]:
        return "unreached"
    if step["lines_without_entity"] == step["lines_read"]:
        return "no_carrier_entity"
    if step["lines_with_episode"] < step["lines_read"]:
        return "episode_missing"
    return "covered"


def logs_from_keys(keys_path: Path) -> Path:
    parent = keys_path.resolve().parent
    if parent.name.endswith("_ingest"):
        candidate = parent.parent / parent.name[: -len("_ingest")] / "gather"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"cannot find the raw tree for {keys_path}; pass --logs")


def _print_receipt(receipt: Mapping[str, Any], verification: Mapping[str, Any] | None) -> None:
    print(
        f"spine: events={receipt['events']} entities={receipt['entities']} "
        f"episodes={receipt['episodes']} links={receipt['links']} "
        f"without_entity={receipt['events_without_entity']} kinds={receipt['kinds']} "
        f"-> {receipt['file']}"
    )
    modes: dict[str, int] = defaultdict(int)
    for item in (receipt.get("read_modes") or {}).values():
        modes[str(item.get("read_mode"))] += 1
    print(f"  read_mode per source: {dict(sorted(modes.items()))}")
    if verification is not None:
        print(
            f"  steps={verification['steps']} read={verification['steps_read']} "
            f"pass={verification['steps_pass']} lines_read={verification['lines_read']} "
            f"lines_with_episode={verification['lines_with_episode']} "
            f"lines_without_entity={verification['lines_without_entity']}"
        )
        for step in verification["per_step"]:
            print(
                f"  {step['step']}: lines={step['lines']} read={step['lines_read']} "
                f"covered={step['lines_with_episode']} pass={step['pass']} "
                f"cause={step['cause']} carriers={step['carrier_entities'][:3]}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="run directory")
    parser.add_argument(
        "--store", type=Path, help="behaviour store (default <out>/behaviours.duckdb)"
    )
    parser.add_argument("--family", help="family name, for --keys")
    parser.add_argument("--keys", type=Path, help="per-line keys.jsonl for step verification")
    parser.add_argument("--logs", type=Path, help="raw tree holding the labelled lines")
    args = parser.parse_args(argv)
    receipt = spine_from_store(args.out, args.store)
    verification = None
    if args.keys is not None:
        if not args.family:
            print("--keys needs --family", file=sys.stderr)
            return 2
        try:
            verification = verify_steps(args.out, args.family, args.keys, args.logs)
        except (FileNotFoundError, ValueError) as error:
            print(f"spine: {error}", file=sys.stderr)
            return 2
        write_json(args.out / "spine_steps.json", verification)
    _print_receipt(receipt, verification)
    return 0


if __name__ == "__main__":
    sys.exit(main())
