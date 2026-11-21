"""Index-wide value lists for low-cardinality card fields, enumerated before sampling."""

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
INVENTORY_MAX_SAMPLE_DISTINCT = 32  # effort budget: card fields above this are not enumerated
INVENTORY_MAX_VALUES = 64  # effort budget: aggregation rows; more is not low-cardinality
INVENTORY_MAX_FIELD_SEARCHES = 32  # effort budget: one search per selected field
INVENTORY_MAX_JOINT_SEARCHES = 16  # effort budget: joint first-seen searches after the field lists
INVENTORY_CANDIDATES_PER_SOURCE = 8  # effort budget: unseen value rows handed to the generators
INVENTORY_CANDIDATE_TOTAL = 32  # effort budget: unseen value rows across the index
FLOW_MAX_SOURCES = 12  # effort budget: a value in more sources is ambient, not one entity
_ROLE_ORDER = {"action": 0, "actor": 1, "object": 2}
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_LITERAL_ROLES = (
    ("actor", "actor_field", "actor", "actor_mode"),
    ("action", "action_field", "action", "action_mode"),
    ("object", "object_field", "object", "object_mode"),
)


@dataclass(frozen=True)
class FieldChoice:
    source_id: str
    sourcetype: str
    field: str
    role: str
    distinct: int


def _field_token(name: str) -> str:
    return name if _FIELD_NAME.fullmatch(name) else _search_literal(name)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _empty_document(index: str) -> dict[str, Any]:
    return {
        "index": index,
        "searches": 0,
        "seconds": 0.0,
        "fields": [],
        "joints": [],
        "flows": [],
        "notes": [],
    }


def load_inventory(path: Any) -> dict[str, Any]:
    """The stored value lists, or an empty document when this run has none."""
    from .receipt import read_json

    stored = read_json(path)
    document = _empty_document(str(stored.get("index") or ""))
    for key in ("searches", "seconds", "fields", "joints", "flows", "notes"):
        if key in stored:
            document[key] = stored[key]
    return document


def _stat_rejected(stat: FieldStat) -> bool:
    return (
        stat.variety == "free" or stat.distinct > INVENTORY_MAX_SAMPLE_DISTINCT or stat.distinct < 1
    )


def select_fields(cards: Sequence[SourceCard]) -> list[FieldChoice]:
    """Low-cardinality role fields, smallest sample variety first, inside the search budget."""
    banned: set[tuple[str, str]] = set()
    chosen: dict[tuple[str, str], FieldChoice] = {}
    for card in cards:
        if not card.understood:
            continue
        stats = {stat.name: stat for stat in card.fields}
        for role in _ROLE_ORDER:
            for name in card.roles.get(role, ()):
                stat = stats.get(name)
                key = (card.source_id, name)
                if stat is None or _stat_rejected(stat):
                    banned.add(key)
                    chosen.pop(key, None)
                    continue
                if key in banned:
                    continue
                current = chosen.get(key)
                distinct = (
                    stat.distinct if current is None else max(current.distinct, stat.distinct)
                )
                if current is None or _ROLE_ORDER[role] < _ROLE_ORDER[current.role]:
                    chosen[key] = FieldChoice(card.source_id, card.sourcetype, name, role, distinct)
                elif current is not None:
                    chosen[key] = replace(current, distinct=distinct)
    ordered = sorted(
        chosen.values(),
        key=lambda item: (item.distinct, _ROLE_ORDER[item.role], item.source_id, item.field),
    )
    return ordered[:INVENTORY_MAX_FIELD_SEARCHES]


def _value_query(index: str, sourcetype: str, fields: Sequence[str]) -> str:
    by = ", ".join(_field_token(name) for name in fields)
    return (
        "| tstats count min(_time) as first max(_time) as last "
        f"where index={_search_literal(index)} sourcetype={_search_literal(sourcetype)} by {by}"
    )


def _read_values(
    executor: HuntExecutor, query: str, start: float, end: float
) -> tuple[list[dict[str, Any]], str]:
    try:
        result = executor.read(
            query, start, end, kind="discovery", row_cap=INVENTORY_MAX_VALUES + 1
        )
    except Exception as exc:  # noqa: BLE001 -- one failed aggregate is coverage, not a crash
        return [], f"failed:{type(exc).__name__}"
    if result.reason and not result.rows:
        return [], f"failed:{result.reason}"
    return [dict(row) for row in result.rows], ""


def _cell(row: Mapping[str, Any], field: str) -> str:
    if field in row:
        return str(row.get(field) or "")
    folded = field.casefold()
    for key, value in row.items():
        if str(key).casefold() == folded:
            return str(value or "")
    return ""


def _complete(
    rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> tuple[str, list[dict[str, Any]]]:
    if len(rows) > INVENTORY_MAX_VALUES:
        return "capped", []
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
            }
        )
    return ("empty" if not values else "complete"), values


def _field_record(
    choice: FieldChoice, status: str, values: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "source_id": choice.source_id,
        "sourcetype": choice.sourcetype,
        "field": choice.field,
        "role": choice.role,
        "sample_distinct": choice.distinct,
        "status": status,
        "values": [
            {
                "value": str(item["values"][choice.field]),
                "events": item["events"],
                "first_seen": item["first_seen"],
                "last_seen": item["last_seen"],
            }
            for item in values
        ],
    }


def _enumerate_fields(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    choices: Sequence[FieldChoice],
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    for choice in choices:
        rows, reason = _read_values(
            executor, _value_query(index, choice.sourcetype, (choice.field,)), start, end
        )
        if reason:
            records.append(_field_record(choice, "failed", ()))
            records[-1]["reason"] = reason
            continue
        status, values = _complete(rows, (choice.field,))
        records.append(_field_record(choice, status, values))
    return records, len(choices)


def _joint_plan(
    records: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str, list[Mapping[str, Any]]]]:
    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") == "complete" and record.get("values"):
            by_source[str(record["source_id"])].append(record)
    planned: list[tuple[str, str, list[Mapping[str, Any]]]] = []
    for source_id, group in sorted(by_source.items()):
        per_role: dict[str, Mapping[str, Any]] = {}
        for record in sorted(group, key=lambda item: (len(item["values"]), str(item["field"]))):
            per_role.setdefault(str(record["role"]), record)
        picked = [per_role[role] for role in _ROLE_ORDER if role in per_role]
        product = 1
        for record in picked:
            product *= len(record["values"])
        if len(picked) >= 2 and product <= INVENTORY_MAX_VALUES:
            planned.append((source_id, str(picked[0]["sourcetype"]), picked))
    return planned[:INVENTORY_MAX_JOINT_SEARCHES]


def _enumerate_joints(
    executor: HuntExecutor,
    index: str,
    start: float,
    end: float,
    planned: Sequence[tuple[str, str, list[Mapping[str, Any]]]],
) -> list[dict[str, Any]]:
    joints: list[dict[str, Any]] = []
    for source_id, sourcetype, picked in planned:
        names = [str(record["field"]) for record in picked]
        rows, reason = _read_values(executor, _value_query(index, sourcetype, names), start, end)
        status, values = ("failed", []) if reason else _complete(rows, names)
        joints.append(
            {
                "source_id": source_id,
                "sourcetype": sourcetype,
                "fields": [{"role": record["role"], "field": record["field"]} for record in picked],
                "status": status,
                "reason": reason,
                "rows": values,
            }
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
    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") == "complete" and record.get("values"):
            by_source[str(record["source_id"])].append(record)
    joints: list[dict[str, Any]] = []
    for source_id, group in sorted(by_source.items()):
        if source_id in jointed:
            continue
        record = min(group, key=lambda item: (len(item["values"]), str(item["field"])))
        field = str(record["field"])
        joints.append(
            {
                "source_id": source_id,
                "sourcetype": record["sourcetype"],
                "fields": [{"role": record["role"], "field": field}],
                "status": "complete",
                "reason": "field_list",
                "rows": [
                    {
                        "values": {field: item["value"]},
                        "events": item["events"],
                        "first_seen": item["first_seen"],
                        "last_seen": item["last_seen"],
                    }
                    for item in record["values"]
                    if isinstance(item, Mapping)
                ],
            }
        )
    return joints


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
    fields, searches = _enumerate_fields(executor, index, start, end, choices)
    planned = _joint_plan(fields)
    joints = _enumerate_joints(executor, index, start, end, planned)
    network_searches = searches + len(joints)
    jointed = {str(item["source_id"]) for item in joints if item.get("status") == "complete"}
    joints.extend(_single_field_joints(fields, jointed))
    document = _empty_document(index)
    document.update(
        {
            "searches": network_searches,
            "seconds": round(time.monotonic() - began, 3),
            "fields_selected": len(choices),
            "fields": fields,
            "joints": joints,
            "flows": _flows(fields),
        }
    )
    return document


def inventory_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    """Counts for the behaviour receipt. The value lists stay in inventory.json."""
    fields = [item for item in document.get("fields") or () if isinstance(item, Mapping)]
    by_status: dict[str, int] = defaultdict(int)
    values = 0
    for item in fields:
        by_status[str(item.get("status") or "")] += 1
        values += len(item.get("values") or ())
    return {
        "searches": int(document.get("searches") or 0),
        "seconds": document.get("seconds"),
        "fields_selected": int(document.get("fields_selected") or len(fields)),
        "fields": dict(sorted(by_status.items())),
        "values": values,
        "joints": len(document.get("joints") or ()),
        "flows": len(document.get("flows") or ()),
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
            table[tuple(sorted(_joint_key(spec, mapped_text)))] = (
                _number(row.get("first_seen")),
                _number(row.get("last_seen")),
                int(_number(row.get("events"))),
            )
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
        hit = (tables.get(behaviour.source_id) or {}).get(pairs) if pairs else None
        if hit is None or hit[0] <= 0:
            corrected.append(behaviour)
            continue
        replaced += 1
        corrected.append(replace(behaviour, first_seen=hit[0], last_seen=max(hit[1], hit[0])))
    candidates = _unseen_candidates(document, seen, facts)
    return [*corrected, *candidates], {
        "first_seen_replaced": replaced,
        "candidates": len(candidates),
        "flows": len(document.get("flows") or ()),
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
