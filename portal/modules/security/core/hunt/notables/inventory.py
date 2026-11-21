"""Index-wide value lists for reviewable fields, enumerated before sampling on a probed path."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..engine import _search_literal
from ..executor import HuntExecutor
from .behaviours import Behaviour, reproduction_query
from .cards import SourceCard
from .parse import FieldStat
from .sample import SourceFacts

INVENTORY_FILE = "inventory.json"
INVENTORY_MAX_VALUES = 5_000  # effort budget (LIST_MAX): a longer list is capped, never exhaustive
INVENTORY_MAX_FIELD_SEARCHES = 32  # effort budget: one value query per selected field
INVENTORY_FIELDS_PER_SOURCE = 8  # effort budget: one source cannot fill the field budget
INVENTORY_MAX_SCAN_EVENTS = 2_000_000  # effort budget: a stats list above this is localised first
INVENTORY_MAX_JOINT_VALUES = 256  # effort budget: rows one two-field joint may aggregate
INVENTORY_MAX_JOINT_SEARCHES = 16  # effort budget: joint first-seen searches after the field lists
INVENTORY_CANDIDATES_PER_SOURCE = 8  # effort budget: unseen value rows handed to the generators
INVENTORY_CANDIDATE_TOTAL = 32  # effort budget: unseen value rows across the index
INVENTORY_MAX_MODEL_PROBES = 8  # effort budget: accelerated models tried for one list
INVENTORY_ACCEL_MIN_EVENTS = 250_000  # effort budget: below this a scan beats an acceleration probe
FLOW_MAX_SOURCES = 12  # effort budget: a value in more sources is ambient, not one entity
# The documented output of setup stage 3: one row per model, with the window its summary covers.
ACCEL_QUERY = (
    "| rest /services/admin/summarization by_tstats=1 "
    "| fields datamodel_name summary.earliest_time summary.latest_time summary.complete"
)
_ROLE_ORDER = {"actor": 0, "action": 1, "object": 2, "from": 3, "to": 4, "outcome": 5}
_CORE_ROLES = ("actor", "action", "object")
# Structural field names can carry an artefact; no value, extension or source is named here.
_STRUCTURAL_FIELDS = frozenset(
    {
        "path",
        "file",
        "file_name",
        "filename",
        "image",
        "process",
        "process_name",
        "parent",
        "parent_image",
        "cmdline",
        "command_line",
        "user",
        "username",
        "account",
        "src",
        "dest",
        "src_ip",
        "dest_ip",
        "source_ip",
        "destination_ip",
        "query",
        "url",
        "uri",
        "registry",
        "key",
        "exe",
        "comm",
        "uid",
        "acct",
        "addr",
    }
)
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_LITERAL_ROLES = (
    ("actor", "actor_field", "actor", "actor_mode"),
    ("action", "action_field", "action", "action_mode"),
    ("object", "object_field", "object", "object_mode"),
)


@dataclass(frozen=True)
class FieldChoice:
    source_id: str
    card_id: str
    sourcetype: str
    field: str
    role: str
    distinct: int
    part_field: str = ""
    part_value: str = ""


@dataclass(frozen=True)
class SourcePaths:
    """Which access path accepts which name for one source; both probed, never assumed."""

    tstats_name: str
    search_name: str
    tstats_events: int
    observed: tuple[str, ...]
    failed: bool = False

    @property
    def two_names(self) -> bool:
        """True when the tsidx path and the raw path answer to different names."""
        return bool(self.tstats_name and self.search_name and self.tstats_name != self.search_name)


@dataclass(frozen=True)
class AcceleratedModel:
    """One model whose summaries are complete, and the window those summaries cover."""

    name: str
    earliest: float
    latest: float


def _field_token(name: str) -> str:
    return name if _FIELD_NAME.fullmatch(name) else _search_literal(name)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _summary_complete(value: Any) -> bool:
    """`summary.complete` is a fraction; only a fully built summary may claim a complete list."""
    if isinstance(value, bool):
        return value
    try:
        return float(value) >= 1.0
    except (TypeError, ValueError):
        return str(value).casefold() == "true"


def _empty_document(index: str) -> dict[str, Any]:
    return {
        "index": index,
        "searches": 0,
        "probe_queries": 0,
        "probe_failures": [],
        "seconds": 0.0,
        "fields": [],
        "joints": [],
        "flows": [],
        "names": [],
        "notes": [],
        "accelerated": [],
        "model_probes": 0,
    }


def load_inventory(path: Any) -> dict[str, Any]:
    """The stored value lists, or an empty document when this run has none."""
    from .receipt import read_json

    stored = read_json(path)
    document = _empty_document(str(stored.get("index") or ""))
    for key in (
        "searches",
        "probe_queries",
        "probe_failures",
        "seconds",
        "fields",
        "joints",
        "flows",
        "names",
        "notes",
        "accelerated",
        "model_probes",
    ):
        if key in stored:
            document[key] = stored[key]
    return document


def _selectable(stat: FieldStat) -> bool:
    """A reviewable field: present, and small enough that one aggregation decides completeness."""
    return 1 <= stat.distinct <= INVENTORY_MAX_VALUES


def _candidates(card: SourceCard) -> list[tuple[str, str, FieldStat]]:
    """Role fields first, then structural fields, each name once per card."""
    stats = {stat.name: stat for stat in card.fields}
    found: dict[str, tuple[str, str, FieldStat]] = {}
    for role in _ROLE_ORDER:
        for name in card.roles.get(role, ()):
            stat = stats.get(name)
            if stat is not None and _selectable(stat) and name not in found:
                found[name] = (role, name, stat)
    for name in sorted(stats):
        stat = stats[name]
        if name.casefold() in _STRUCTURAL_FIELDS and _selectable(stat) and name not in found:
            found[name] = ("object", name, stat)
    return list(found.values())


def select_fields(cards: Sequence[SourceCard]) -> list[FieldChoice]:
    """Role first then smallest list within a source; every source's best list before any second.

    The round-robin is what lets a wide source be enumerated at all: a global "smallest list
    wins" cut spends the whole budget on narrow cards and a wide card's list never runs.
    """
    ranked_cards: list[list[FieldChoice]] = []
    for card in cards:
        if not card.understood:
            continue
        over_budget = int(_number(card.facts.get("events"))) > INVENTORY_MAX_SCAN_EVENTS
        ranked = sorted(
            _candidates(card),
            key=lambda item: (_ROLE_ORDER[item[0]], over_budget, item[2].distinct, item[1]),
        )[:INVENTORY_FIELDS_PER_SOURCE]
        if ranked:
            ranked_cards.append(
                [
                    FieldChoice(
                        card.source_id,
                        card.card_id,
                        card.sourcetype,
                        name,
                        role,
                        stat.distinct,
                        card.part_field,
                        card.part_value,
                    )
                    for role, name, stat in ranked
                ]
            )
    chosen: list[FieldChoice] = []
    depth = 0
    while len(chosen) < INVENTORY_MAX_FIELD_SEARCHES:
        added = False
        for group in ranked_cards:
            if len(chosen) >= INVENTORY_MAX_FIELD_SEARCHES:
                break
            if depth < len(group):
                chosen.append(group[depth])
                added = True
        if not added:
            break
        depth += 1
    ordered = sorted(
        chosen, key=lambda item: (_ROLE_ORDER[item.role], item.distinct, item.card_id, item.field)
    )
    return ordered[:INVENTORY_MAX_FIELD_SEARCHES]


class _Prober:
    """Name and field probes cached per source and per field: one query per question."""

    def __init__(self, executor: HuntExecutor, index: str, start: float, end: float) -> None:
        self.executor = executor
        self.index = index
        self.start = start
        self.end = end
        self.queries = 0
        self.probe_queries = 0
        self.model_probes = 0
        self.failures: list[str] = []
        self._sources: dict[tuple[str, str], SourcePaths] = {}
        self._fields: dict[tuple[str, str, str], bool] = {}
        self._accelerated: tuple[AcceleratedModel, ...] | None = None

    def _name_route(self, name: str) -> str:
        """The route a name probe asks about: a partition predicate belongs to the read, not the name."""
        return f"index={_search_literal(self.index)} sourcetype={_search_literal(name)}"

    def _route(self, name: str, card: SourceCard | None = None) -> str:
        route = f"index={_search_literal(self.index)} sourcetype={_search_literal(name)}"
        if card is not None and card.part_field:
            route += f" {_field_token(card.part_field)}={_search_literal(card.part_value)}"
        return route

    def read(
        self,
        query: str,
        row_cap: int | None = None,
        *,
        source_id: str | None = None,
        part: str | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """One read; a transport failure is a recorded reason, not an empty answer."""
        self.queries += 1
        try:
            result = self.executor.read(
                query,
                self.start,
                self.end,
                kind="discovery",
                row_cap=row_cap,
                source_id=source_id,
                part=part,
            )
        except Exception as exc:  # noqa: BLE001 -- one failed aggregate is coverage, not a crash
            return [], f"read_failed:{type(exc).__name__}"
        rows = [dict(row) for row in result.rows]
        # A censored aggregate's rows are partial: the reason travels with them.
        return rows, (str(result.reason) if result.reason else "")

    def _probe(
        self,
        query: str,
        row_cap: int | None = None,
        *,
        source_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        self.probe_queries += 1
        return self.read(query, row_cap, source_id=source_id)

    def source(self, card: SourceCard) -> SourcePaths:
        key = (card.index, card.sourcetype)
        found = self._sources.get(key)
        if found is None:
            found = self._probe_source(card)
            self._sources[key] = found
        return found

    def _probe_source(self, card: SourceCard) -> SourcePaths:
        observed = tuple(
            str(name) for name in (card.sample.get("search_sourcetypes") or ()) if str(name)
        )
        names = tuple(dict.fromkeys((card.sourcetype, *observed)))
        tstats_name, tstats_events = "", 0
        failed = False
        for name in names:
            rows, problem = self._probe(
                f"| tstats count where {self._name_route(name)}", source_id=card.source_id
            )
            if problem:
                failed = True
                self.failures.append(f"name:tstats:{problem}")
                continue
            events = int(_number(rows[0].get("count"))) if rows else 0
            if events > 0:
                tstats_name, tstats_events = name, events
                break
        search_name = ""
        for name in names:
            rows, problem = self._probe(
                f"search {self._name_route(name)} | head 1", source_id=card.source_id
            )
            if problem:
                failed = True
                self.failures.append(f"name:search:{problem}")
                continue
            if rows:
                search_name = name
                break
        return SourcePaths(tstats_name, search_name, tstats_events, observed, failed)

    def field_indexed(self, card: SourceCard, name: str, field: str) -> bool:
        """One field per probe: a multi-field by-list cannot attribute a failed field."""
        key = (card.index, name, field)
        found = self._fields.get(key)
        if found is None:
            rows, problem = self._probe(
                f"| tstats count where {self._route(name)} by {_field_token(field)}",
                source_id=card.source_id,
            )
            if problem:
                self.failures.append(f"field:{field}:{problem}")
            found = bool(rows)
            self._fields[key] = found
        return found

    def accelerated(self) -> tuple[AcceleratedModel, ...]:
        """Models with a complete summary and the window it covers, probed once per run."""
        if self._accelerated is None:
            rows, problem = self._probe(ACCEL_QUERY)
            if problem:
                self.failures.append(f"accelerated:{problem}")
                rows = []
            found: list[AcceleratedModel] = []
            for row in rows:
                name = str(row.get("datamodel_name") or "")
                if not name or not _summary_complete(row.get("summary.complete")):
                    continue
                found.append(
                    AcceleratedModel(
                        name,
                        _number(row.get("summary.earliest_time")),
                        _number(row.get("summary.latest_time")),
                    )
                )
            self._accelerated = tuple(
                sorted(found, key=lambda item: item.name)[:INVENTORY_MAX_MODEL_PROBES]
            )
        return self._accelerated


def _mechanism(prober: _Prober, card: SourceCard, fields: Sequence[str]) -> tuple[str, str, str]:
    """(mechanism, name_used, reason): the cheapest proven path, or why there is none."""
    paths = prober.source(card)
    if paths.tstats_name:
        part_ok = not card.part_field or prober.field_indexed(
            card, paths.tstats_name, card.part_field
        )
        if part_ok and all(prober.field_indexed(card, paths.tstats_name, f) for f in fields):
            return "tstats", paths.tstats_name, ""
    if paths.search_name:
        return "stats", paths.search_name, ""
    # The search path is the only route for a search-time field, so a rejected name is the cause.
    return "", "", "mechanism" if paths.failed else "name"


def _value_query(
    index: str,
    name: str,
    mechanism: str,
    fields: Sequence[str],
    card: SourceCard,
) -> str:
    route = f"index={_search_literal(index)} sourcetype={_search_literal(name)}"
    if card.part_field:
        route += f" {_field_token(card.part_field)}={_search_literal(card.part_value)}"
    by = ", ".join(_field_token(field) for field in fields)
    if mechanism == "tstats":
        return f"| tstats count min(_time) as first max(_time) as last where {route} by {by}"
    return (
        f"search {route} | stats count min(_time) as first max(_time) as last "
        f"dc(host) as hosts by {by}"
    )


def _read_values(
    prober: _Prober, query: str, row_cap: int | None, card: SourceCard
) -> tuple[list[dict[str, Any]], str, float]:
    part = f"{card.part_field}={card.part_value}" if card.part_field else None
    began = time.monotonic()
    rows, problem = prober.read(query, row_cap, source_id=card.source_id, part=part)
    return rows, problem, round(time.monotonic() - began, 3)


def _model_query(index: str, name: str, model: str, fields: Sequence[str], card: SourceCard) -> str:
    """One summary aggregate; the source predicate keeps the list attributable to its card."""
    route = f"index={_search_literal(index)} sourcetype={_search_literal(name)}"
    if card.part_field:
        route += f" {_field_token(card.part_field)}={_search_literal(card.part_value)}"
    # Model name == root dataset for Authentication/Web; another root's zero rows fall through.
    by = ", ".join(f"{model}.{_field_token(field)}" for field in fields)
    return (
        f"| tstats summariesonly=true count min(_time) as first max(_time) as last "
        f"from datamodel={model} where {route} by {by}"
    )


def _datamodel_values(
    prober: _Prober,
    index: str,
    card: SourceCard,
    fields: Sequence[str],
) -> tuple[AcceleratedModel | None, str, list[dict[str, Any]], str, float]:
    """The first accelerated model that answers this source; the aggregate is its own probe."""
    paths = prober.source(card)
    if not paths.tstats_name:
        return None, "", [], "", 0.0
    for model in prober.accelerated():
        name = paths.tstats_name
        prober.model_probes += 1
        rows, problem, seconds = _read_values(
            prober,
            _model_query(index, name, model.name, fields, card),
            INVENTORY_MAX_VALUES + 1,
            card,
        )
        if rows:
            return model, name, rows, problem, seconds
    return None, "", [], "", 0.0


def _cell(row: Mapping[str, Any], field: str) -> str:
    if field in row:
        return str(row.get(field) or "")
    folded = field.casefold()
    for key, value in row.items():
        if str(key).casefold() == folded:
            return str(value or "")
    return ""


def _has_column(row: Mapping[str, Any], field: str) -> bool:
    if field in row:
        return True
    folded = field.casefold()
    return any(str(key).casefold() == folded for key in row)


def _values(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    mechanism: str,
    problem: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """complete | capped | unavailable:<mechanism>; only a proven mechanism may report empty."""
    if len(rows) > INVENTORY_MAX_VALUES:
        return "capped", []
    if problem:
        return f"failed:{problem}", []
    if rows and not all(_has_column(row, field) for row in rows for field in fields):
        return f"unavailable:{mechanism}", []
    values: list[dict[str, Any]] = []
    for row in rows:
        mapped = {field: _cell(row, field) for field in fields}
        if not all(mapped.values()):
            continue
        first = _number(row.get("first"))
        last = _number(row.get("last")) or first
        values.append(
            {
                "values": mapped,
                "events": int(_number(row.get("count"))),
                "first_seen": first,
                "last_seen": last,
                "hosts": int(_number(row.get("hosts"))),
            }
        )
    return ("empty" if not values else "complete"), values


def _scanned(mechanism: str, rows: Sequence[Mapping[str, Any]], available: int) -> int:
    if mechanism == "stats":
        return available or int(sum(_number(row.get("count")) for row in rows))
    return int(sum(_number(row.get("count")) for row in rows))


def _field_record(
    choice: FieldChoice,
    status: str,
    values: Sequence[Mapping[str, Any]],
    *,
    mechanism: str = "",
    name_used: str = "",
    events_scanned: int = 0,
    seconds: float = 0.0,
    value_field: str = "",
    accel_window: Sequence[float] | None = None,
    searched_window: Sequence[float] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": choice.source_id,
        "card_id": choice.card_id,
        "sourcetype": choice.sourcetype,
        "part": (
            {"field": choice.part_field, "value": choice.part_value} if choice.part_field else None
        ),
        "field": choice.field,
        "role": choice.role,
        "sample_distinct": choice.distinct,
        "status": status,
        "mechanism": mechanism,
        "name_used": name_used,
        "events_scanned": events_scanned,
        "events_scope": (
            "source"
            if mechanism == "stats"
            else ("summary" if mechanism == "datamodel" else ("aggregate" if mechanism else ""))
        ),
        "accel_window": list(accel_window) if accel_window else None,
        "searched_window": list(searched_window) if searched_window else None,
        "seconds": seconds,
        "values": [
            {
                "value": str(item["values"][value_field or choice.field]),
                "events": item["events"],
                "first_seen": item["first_seen"],
                "last_seen": item["last_seen"],
                "hosts": item["hosts"],
            }
            for item in values
        ],
    }


def _enumerate_fields(
    prober: _Prober,
    index: str,
    choices: Sequence[FieldChoice],
    cards_by_id: Mapping[str, SourceCard],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for choice in choices:
        card = cards_by_id[choice.card_id]
        mechanism, name, reason = _mechanism(prober, card, (choice.field,))
        available = int(_number(card.facts.get("events")))
        if mechanism != "tstats" and available >= INVENTORY_ACCEL_MIN_EVENTS:
            model, route_name, rows, problem, seconds = _datamodel_values(
                prober, index, card, (choice.field,)
            )
            if model is not None:
                value_field = f"{model.name}.{choice.field}"
                status, values = _values(rows, (value_field,), "datamodel", problem)
                records.append(
                    _field_record(
                        choice,
                        status,
                        values,
                        mechanism="datamodel",
                        name_used=f"{model.name}:{route_name}",
                        events_scanned=_scanned("datamodel", rows, available),
                        seconds=seconds,
                        value_field=value_field,
                        accel_window=(model.earliest, model.latest) if model.latest > 0 else None,
                        searched_window=(prober.start, prober.end),
                    )
                )
                continue
        if not mechanism:
            records.append(
                _field_record(
                    choice,
                    f"unavailable:{reason or 'mechanism'}",
                    (),
                    searched_window=(prober.start, prober.end),
                )
            )
            continue
        if mechanism == "stats" and available > INVENTORY_MAX_SCAN_EVENTS:
            record = _field_record(choice, "unavailable:mechanism", ())
            record["reason"] = "events_budget"
            record["events_available"] = available
            record["searched_window"] = [prober.start, prober.end]
            records.append(record)
            continue
        rows, problem, seconds = _read_values(
            prober,
            _value_query(index, name, mechanism, (choice.field,), card),
            INVENTORY_MAX_VALUES + 1,
            card,
        )
        status, values = _values(rows, (choice.field,), mechanism, problem)
        records.append(
            _field_record(
                choice,
                status,
                values,
                mechanism=mechanism,
                name_used=name,
                events_scanned=_scanned(mechanism, rows, available),
                seconds=seconds,
                searched_window=(prober.start, prober.end),
            )
        )
    return records


def _joint_plan(
    records: Sequence[Mapping[str, Any]], cards_by_id: Mapping[str, SourceCard]
) -> list[tuple[SourceCard, list[Mapping[str, Any]]]]:
    by_card: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") == "complete" and record.get("values"):
            by_card[str(record["card_id"])].append(record)
    planned: list[tuple[SourceCard, list[Mapping[str, Any]]]] = []
    for card_id, group in sorted(by_card.items()):
        per_role: dict[str, Mapping[str, Any]] = {}
        for record in sorted(group, key=lambda item: (len(item["values"]), str(item["field"]))):
            if str(record["role"]) in _CORE_ROLES:
                per_role.setdefault(str(record["role"]), record)
        picked = [per_role[role] for role in _CORE_ROLES if role in per_role]
        product = 1
        for record in picked:
            product *= len(record["values"])
        card = cards_by_id.get(card_id)
        if card is not None and len(picked) >= 2 and product <= INVENTORY_MAX_JOINT_VALUES:
            planned.append((card, picked))
    return planned[:INVENTORY_MAX_JOINT_SEARCHES]


def _joint_record(
    card: SourceCard,
    picked: Sequence[Mapping[str, Any]],
    status: str,
    mechanism: str,
    name_used: str,
    events_scanned: int,
    seconds: float,
    rows: Sequence[Mapping[str, Any]],
    searched_window: Sequence[float] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": card.source_id,
        "card_id": card.card_id,
        "sourcetype": card.sourcetype,
        "part": {"field": card.part_field, "value": card.part_value} if card.part_field else None,
        "fields": [{"role": record["role"], "field": record["field"]} for record in picked],
        "status": status,
        "reason": mechanism,
        "mechanism": mechanism,
        "name_used": name_used,
        "events_scanned": events_scanned,
        "events_scope": "source" if mechanism == "stats" else ("aggregate" if mechanism else ""),
        "accel_window": None,
        "searched_window": list(searched_window) if searched_window else None,
        "seconds": seconds,
        "rows": rows,
    }


def _enumerate_joints(
    prober: _Prober,
    index: str,
    planned: Sequence[tuple[SourceCard, list[Mapping[str, Any]]]],
) -> list[dict[str, Any]]:
    joints: list[dict[str, Any]] = []
    window = (prober.start, prober.end)
    for card, picked in planned:
        names = [str(record["field"]) for record in picked]
        mechanism, name, reason = _mechanism(prober, card, names)
        if not mechanism:
            joints.append(
                _joint_record(card, picked, f"unavailable:{reason}", "", "", 0, 0.0, (), window)
            )
            continue
        available = int(_number(card.facts.get("events")))
        if mechanism == "stats" and available > INVENTORY_MAX_SCAN_EVENTS:
            record = _joint_record(
                card, picked, "unavailable:mechanism", "", "", 0, 0.0, (), window
            )
            record["reason"] = "events_budget"
            record["events_available"] = available
            joints.append(record)
            continue
        rows, problem, seconds = _read_values(
            prober,
            _value_query(index, name, mechanism, names, card),
            INVENTORY_MAX_VALUES + 1,
            card,
        )
        status, values = _values(rows, names, mechanism, problem)
        joints.append(
            _joint_record(
                card,
                picked,
                status,
                mechanism,
                name,
                _scanned(mechanism, rows, available),
                seconds,
                values,
                window,
            )
        )
    return joints


def _entity_token(value: str) -> bool:
    if len(value) < 4:
        return False
    return bool(_IPV4.fullmatch(value) or any(char.isalpha() for char in value))


def _flow_keep(value: str, sources: int) -> bool:
    return 2 <= sources <= FLOW_MAX_SOURCES and _entity_token(value)


def _flows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for record in records:
        if record.get("status") != "complete":
            continue
        for item in record.get("values") or ():
            if not isinstance(item, Mapping):
                continue
            raw = str(item.get("value") or "")
            key = raw.casefold()
            labels.setdefault(key, raw)
            grouped[key].append(
                {
                    "source_id": record["source_id"],
                    "field": record["field"],
                    "events": item.get("events"),
                    "first_seen": item.get("first_seen"),
                    "last_seen": item.get("last_seen"),
                }
            )
    flows: list[dict[str, Any]] = []
    for key, steps in grouped.items():
        ordered = sorted(
            steps, key=lambda step: (_number(step.get("first_seen")), str(step["source_id"]))
        )
        sources = {str(step["source_id"]) for step in ordered}
        if not _flow_keep(labels[key], len(sources)):
            continue
        flows.append(
            {
                "value": labels[key],
                "ingress": ordered[0]["source_id"],
                "later": ordered[-1]["source_id"],
                "steps": ordered,
            }
        )
    flows.sort(key=lambda item: (str(item["value"]).casefold(), str(item["ingress"])))
    return flows


def _single_field_joints(
    records: Sequence[Mapping[str, Any]], jointed: set[str]
) -> list[dict[str, Any]]:
    """A complete one-field list is the joint when no two-field aggregate was run."""
    by_card: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") == "complete" and record.get("values"):
            by_card[str(record["card_id"])].append(record)
    joints: list[dict[str, Any]] = []
    for card_id, group in sorted(by_card.items()):
        if card_id in jointed:
            continue
        record = min(group, key=lambda item: (len(item["values"]), str(item["field"])))
        field = str(record["field"])
        joints.append(
            {
                "source_id": record["source_id"],
                "card_id": card_id,
                "sourcetype": record["sourcetype"],
                "part": record.get("part"),
                "fields": [{"role": record["role"], "field": field}],
                "status": "complete",
                "reason": "field_list",
                "mechanism": record.get("mechanism"),
                "name_used": record.get("name_used"),
                "events_scanned": record.get("events_scanned"),
                "accel_window": record.get("accel_window"),
                "searched_window": record.get("searched_window"),
                "seconds": record.get("seconds"),
                "rows": [
                    {
                        "values": {field: item["value"]},
                        "events": item["events"],
                        "first_seen": item["first_seen"],
                        "last_seen": item["last_seen"],
                        "hosts": item.get("hosts"),
                    }
                    for item in record["values"]
                    if isinstance(item, Mapping)
                ],
            }
        )
    return joints


def _name_documents(
    choices: Sequence[FieldChoice], cards_by_id: Mapping[str, SourceCard], prober: _Prober
) -> list[dict[str, Any]]:
    """One receipt row per probed source: both names, and whether they differ."""
    found: dict[str, dict[str, Any]] = {}
    for choice in choices:
        if choice.source_id in found:
            continue
        card = cards_by_id[choice.card_id]
        paths = prober.source(card)
        found[choice.source_id] = {
            "source_id": choice.source_id,
            "card_name": card.sourcetype,
            "tstats_name": paths.tstats_name,
            "search_name": paths.search_name,
            "two_names": paths.two_names,
            "failed": paths.failed,
            "observed": list(paths.observed),
            "tstats_events": paths.tstats_events,
        }
    return list(found.values())


def collect_inventory(
    executor: HuntExecutor,
    cards: Sequence[SourceCard],
    index: str,
    start: float,
    end: float,
) -> dict[str, Any]:
    """Enumerate selected fields over the whole index and store value lists plus joints."""
    began = time.monotonic()
    choices = select_fields(cards)
    cards_by_id = {card.card_id: card for card in cards}
    prober = _Prober(executor, index, start, end)
    fields = _enumerate_fields(prober, index, choices, cards_by_id)
    planned = _joint_plan(fields, cards_by_id)
    joints = _enumerate_joints(prober, index, planned)
    jointed = {str(item["card_id"]) for item in joints if item.get("status") == "complete"}
    joints.extend(_single_field_joints(fields, jointed))
    accelerated = prober.accelerated()
    document = _empty_document(index)
    document.update(
        {
            "searches": len(choices) + len(planned),
            "probe_queries": prober.probe_queries,
            "model_probes": prober.model_probes,
            "probe_failures": prober.failures[:16],
            "seconds": round(time.monotonic() - began, 3),
            "fields_selected": len(choices),
            "fields": fields,
            "joints": joints,
            "flows": _flows(fields),
            "names": _name_documents(choices, cards_by_id, prober),
            "accelerated": [
                {"model": model.name, "earliest": model.earliest, "latest": model.latest}
                for model in accelerated
            ],
        }
    )
    return document


def inventory_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    """Counts for the behaviour receipt. The value lists stay in inventory.json."""
    fields = [item for item in document.get("fields") or () if isinstance(item, Mapping)]
    by_status: dict[str, int] = defaultdict(int)
    mechanisms: dict[str, int] = defaultdict(int)
    values = 0
    scanned = 0
    for item in fields:
        by_status[str(item.get("status") or "")] += 1
        values += len(item.get("values") or ())
        if item.get("mechanism"):
            mechanisms[str(item["mechanism"])] += 1
        scanned += int(_number(item.get("events_scanned")))
    names = [item for item in document.get("names") or () if isinstance(item, Mapping)]
    return {
        "searches": int(document.get("searches") or 0),
        "probe_queries": int(document.get("probe_queries") or 0),
        "model_probes": int(document.get("model_probes") or 0),
        "probe_failures": list(document.get("probe_failures") or ()),
        "seconds": document.get("seconds"),
        "fields_selected": int(document.get("fields_selected") or len(fields)),
        "fields": dict(sorted(by_status.items())),
        "mechanisms": dict(sorted(mechanisms.items())),
        "two_names": sum(1 for item in names if item.get("two_names")),
        "events_scanned": scanned,
        "values": values,
        "joints": len(document.get("joints") or ()),
        "flows": len(document.get("flows") or ()),
        "accelerated": [
            str(item.get("model") or "")
            for item in document.get("accelerated") or ()
            if isinstance(item, Mapping)
        ],
        "lists": [
            {
                "card_id": item.get("card_id"),
                "part": item.get("part"),
                "field": item.get("field"),
                "status": item.get("status"),
                "mechanism": item.get("mechanism"),
                "name_used": item.get("name_used"),
                "events_scanned": int(_number(item.get("events_scanned"))),
                "accel_window": item.get("accel_window"),
                "seconds": item.get("seconds"),
                "values": len(item.get("values") or ()),
            }
            for item in fields
        ],
    }


def _literal_pairs(behaviour: Behaviour) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for _role, field_name, value_name, mode_name in _LITERAL_ROLES:
        if getattr(behaviour, mode_name) != "literal":
            continue
        field = str(getattr(behaviour, field_name) or "")
        value = str(getattr(behaviour, value_name) or "")
        if field and value:
            pairs.append((field, value))
    return tuple(pairs)


def _joint_key(
    fields: Sequence[Mapping[str, Any]], mapped: Mapping[str, str]
) -> tuple[tuple[str, str], ...]:
    return tuple((str(item["field"]), str(mapped[str(item["field"])])) for item in fields)


def _joint_index(
    joints: Sequence[Mapping[str, Any]],
) -> dict[str, dict[tuple[tuple[str, str], ...], tuple[float, float, int]]]:
    """Joint rows per source, min/max across parts; the value lists stay per part."""
    found: dict[str, dict[tuple[tuple[str, str], ...], tuple[float, float, int]]] = {}
    for joint in joints:
        if joint.get("status") != "complete":
            continue
        source_id = str(joint.get("source_id") or "")
        spec = [item for item in joint.get("fields") or () if isinstance(item, Mapping)]
        table = found.setdefault(source_id, {})
        for row in joint.get("rows") or ():
            if not isinstance(row, Mapping):
                continue
            mapped = row.get("values")
            if not isinstance(mapped, Mapping):
                continue
            mapped_text = {str(key): str(value) for key, value in mapped.items()}
            key = tuple(sorted(_joint_key(spec, mapped_text)))
            first = _number(row.get("first_seen"))
            last = _number(row.get("last_seen"))
            events = int(_number(row.get("events")))
            old_first, old_last, old_events = table.get(key, (first, last, 0))
            table[key] = (min(first, old_first), max(last, old_last), old_events + events)
    return found


def _facts_for(source_id: str, facts: Mapping[str, SourceFacts]) -> SourceFacts:
    found = facts.get(source_id)
    if found is not None:
        return found
    index, _sep, sourcetype = source_id.partition(":")
    return SourceFacts(index, sourcetype, 0, 0.0, 0.0, (), 0, (), 0)


def _candidate_ok(mapped: Mapping[str, str]) -> bool:
    return any(_entity_token(value) for value in mapped.values())


def _candidate_behaviour(
    source_id: str,
    spec: Sequence[Mapping[str, Any]],
    mapped: Mapping[str, str],
    first: float,
    last: float,
    events: int,
    facts: SourceFacts,
) -> Behaviour:
    by_role = {str(item["role"]): str(item["field"]) for item in spec}
    actor_field = by_role.get("actor", "")
    action_field = by_role.get("action", "")
    object_field = by_role.get("object", "")
    actor = mapped.get(actor_field, "") if actor_field else ""
    action = mapped.get(action_field, "") if action_field else ""
    obj = mapped.get(object_field, "") if object_field else ""
    terms = [value for value in (actor, action, obj) if value]
    return Behaviour(
        source_id,
        actor_field,
        actor,
        action_field,
        action,
        object_field or "slots",
        obj,
        "literal" if actor else "",
        "literal" if action else "",
        "literal" if obj else "shape",
        events,
        first,
        last or first,
        0,
        0,
        first,
        reproduction_query(facts, terms),
        "",
        first,
        last or first,
    )


def _seen_keys(behaviours: Sequence[Behaviour]) -> dict[str, set[tuple[tuple[str, str], ...]]]:
    found: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)
    for behaviour in behaviours:
        pairs = _literal_pairs(behaviour)
        if not pairs:
            continue
        found[behaviour.source_id].add(tuple(sorted(pairs)))
        for pair in pairs:
            found[behaviour.source_id].add((pair,))
    return found


def apply_inventory(
    behaviours: Sequence[Behaviour],
    document: Mapping[str, Any],
    facts: Mapping[str, SourceFacts],
) -> tuple[list[Behaviour], dict[str, Any]]:
    """Replace sample first-seen from joint aggregates and add unseen rows as candidates."""
    tables = _joint_index(
        [item for item in document.get("joints") or () if isinstance(item, Mapping)]
    )
    corrected: list[Behaviour] = []
    replaced = 0
    seen = _seen_keys(behaviours)
    for behaviour in behaviours:
        pairs = tuple(sorted(_literal_pairs(behaviour)))
        table = tables.get(behaviour.source_id) or {}
        hit = table.get(pairs) if pairs else None
        if hit is None or hit[0] <= 0:
            corrected.append(behaviour)
            continue
        replaced += 1
        corrected.append(replace(behaviour, first_seen=hit[0], last_seen=max(hit[1], hit[0])))
    candidates = _unseen_candidates(document, seen, facts)
    summary = inventory_summary(document)
    return [*corrected, *candidates], {
        "first_seen_replaced": replaced,
        "candidates": len(candidates),
        "flows": summary["flows"],
        "fields": summary["fields"],
        "mechanisms": summary["mechanisms"],
        "values": summary["values"],
        "events_scanned": summary["events_scanned"],
        "two_names": summary["two_names"],
        "accelerated": summary["accelerated"],
    }


def _unseen_candidates(
    document: Mapping[str, Any],
    seen: Mapping[str, set[tuple[tuple[str, str], ...]]],
    facts: Mapping[str, SourceFacts],
) -> list[Behaviour]:
    per_source: dict[str, list[Behaviour]] = defaultdict(list)
    for joint in document.get("joints") or ():
        if not isinstance(joint, Mapping) or joint.get("status") != "complete":
            continue
        source_id = str(joint.get("source_id") or "")
        spec = [item for item in joint.get("fields") or () if isinstance(item, Mapping)]
        known = seen.get(source_id) or set()
        for row in joint.get("rows") or ():
            if not isinstance(row, Mapping) or not isinstance(row.get("values"), Mapping):
                continue
            mapped = {str(key): str(value) for key, value in row["values"].items()}
            key = tuple(sorted(_joint_key(spec, mapped)))
            if key in known or not _candidate_ok(mapped):
                continue
            first = _number(row.get("first_seen"))
            if first <= 0:
                continue
            per_source[source_id].append(
                _candidate_behaviour(
                    source_id,
                    spec,
                    mapped,
                    first,
                    _number(row.get("last_seen")),
                    int(_number(row.get("events"))),
                    _facts_for(source_id, facts),
                )
            )
    chosen: list[Behaviour] = []
    for source_id in sorted(per_source):
        ordered = sorted(
            per_source[source_id], key=lambda item: (-item.first_seen, item.actor, item.action)
        )
        chosen.extend(ordered[:INVENTORY_CANDIDATES_PER_SOURCE])
    chosen.sort(key=lambda item: (-item.first_seen, item.source_id, item.actor, item.action))
    return chosen[:INVENTORY_CANDIDATE_TOTAL]
