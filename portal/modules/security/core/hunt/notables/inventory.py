"""Index-wide value lists for reviewable fields, enumerated before sampling on a probed path."""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..engine import _search_literal
from ..executor import HuntExecutor, HuntSubBudgetExceededError
from .behaviours import Behaviour, reproduction_query
from .cards import ROLE_CONSUMERS, SourceCard, card_consumers
from .parse import FieldStat
from .sample import ACCEL_MODELS, SourceFacts
from .spine import is_sentinel_value

INVENTORY_FILE = "inventory.json"
INVENTORY_MAX_VALUES = 5_000  # effort budget (LIST_MAX): a longer list is capped, never exhaustive
# Effort budget: the rarest values a capped list keeps beside its volume head.
INVENTORY_MAX_TAIL = INVENTORY_MAX_VALUES // 10
INVENTORY_MAX_FIELD_SEARCHES = 40  # effort budget: three value queries per source
INVENTORY_FIELDS_PER_SOURCE = 8  # effort budget: one source cannot fill the field budget
INVENTORY_MAX_SCAN_EVENTS = 2_000_000  # effort budget: a stats list above this is localised first
INVENTORY_MAX_JOINT_VALUES = 256  # effort budget: rows one two-field joint may aggregate
INVENTORY_MAX_JOINT_SEARCHES = 16  # effort budget: joint first-seen searches after the field lists
INVENTORY_CANDIDATES_PER_SOURCE = 8  # effort budget: unseen value rows handed to the generators
INVENTORY_CANDIDATE_TOTAL = 32  # effort budget: unseen value rows across the index
INVENTORY_MAX_MODEL_PROBES = 8  # effort budget: accelerated models tried for one list
INVENTORY_PROBE_EVENTS = 1_000  # effort budget: events one source's vocabulary probe reads
INVENTORY_MAX_PROBE_FIELDS = 96  # effort budget: names one presence probe resolves
INVENTORY_MAX_PRESENCE_PROBES = 48  # effort budget: sources one run samples for a vocabulary
FLOW_MAX_SOURCES = 12  # effort budget: a value in more sources is ambient, not one entity
FLOW_MAX_GAP_SECONDS = 4 * 3600.0  # a later observation past the case link gap is another traverse
FLOW_MAX_FLOWS = 64  # effort budget: emitted flows per index
FLOW_MAX_PROBES = 16  # effort budget: host probes across every flow candidate
FLOW_HOST_ROWS = 64  # effort budget: hosts one probe may return
# The summarization endpoint keys an accelerator by `title`/`summary.id`, never `datamodel_name`;
# no `| fields` list, because one unknown name there empties the whole answer.
ACCEL_QUERY = "| rest /services/admin/summarization by_tstats=1"
# The estate's declaration of which names it indexes: the only ones tstats can ever answer.
VOCABULARY_QUERY = "| rest /servicesNS/-/-/configs/conf-fields | fields title INDEXED"
# The event's own metadata is present everywhere and names no entity.
_EVENT_METADATA = frozenset(
    {"host", "index", "source", "sourcetype", "punct", "linecount", "splunk_server"}
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
    parse_only: bool = False


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


def inventory_scope_matches(
    document: Mapping[str, Any], index: str, start: float, end: float
) -> bool:
    return (
        str(document.get("index") or "") == index
        and _number(document.get("start")) == start
        and _number(document.get("end")) == end
    )


def _summary_complete(value: Any) -> bool:
    """`summary.complete` is a fraction; only a fully built summary may claim a complete list."""
    if isinstance(value, bool):
        return value
    try:
        return float(value) >= 1.0
    except (TypeError, ValueError):
        return str(value).casefold() == "true"


def _declared_indexed(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """The estate's declared index-time names, minus the event's own metadata."""
    found: set[str] = set()
    for row in rows:
        name = str(row.get("title") or row.get("name") or "")
        if not name or str(row.get("INDEXED") or "").casefold() not in {"1", "true", "yes"}:
            continue
        if name in _EVENT_METADATA or name.startswith(("_", "date_")):
            continue
        if _FIELD_NAME.fullmatch(name):
            found.add(name)
    return tuple(sorted(found))


def _probe_names(card: SourceCard, vocabulary: Sequence[str]) -> tuple[str, ...]:
    """Every name worth one presence question: the card's own, then the estate's."""
    names = [name for role in card.roles.values() for name in role]
    names.extend(stat.name for stat in card.fields)
    names.extend(vocabulary)
    kept = (
        name
        for name in dict.fromkeys(names)
        if _FIELD_NAME.fullmatch(name) and name not in _EVENT_METADATA
    )
    return tuple(kept)[:INVENTORY_MAX_PROBE_FIELDS]


def _presence_query(route: str, names: Sequence[str]) -> str:
    """One bounded sample answers presence for every name at once."""
    counts = ", ".join(f"count({name}) as p{index}" for index, name in enumerate(names))
    return f"search {route} | head {INVENTORY_PROBE_EVENTS} | stats count as sampled, {counts}"


def _absent(known: frozenset[str] | None, name: str) -> bool:
    """Only a probe may declare a name absent: an unprobed source keeps its names."""
    return known is not None and name not in known


def _model_root(accelerator: str) -> str:
    """`tstats:DM_<app>_<Model>` -> `<Model>`: the name a `from datamodel=` search accepts."""
    text = accelerator.strip()
    if text.startswith("tstats:"):
        text = text[len("tstats:") :]
    for model in ACCEL_MODELS:
        if text == model or text.endswith(f"_{model}"):
            return model
    return ""


def _covers(window: tuple[float, float], span: tuple[float, float]) -> bool:
    """The endpoint reports whole seconds; a sub-second tail of the span is not a gap."""
    return window[0] <= span[0] and span[1] <= window[1] + 1.0


def _span(cards: Sequence[SourceCard], start: float, end: float) -> tuple[float, float]:
    """The event range the lists describe: the cards' own data, not the query's all-time bound."""
    firsts = [value for value in (_number(card.facts.get("first")) for card in cards) if value > 0]
    lasts = [value for value in (_number(card.facts.get("last")) for card in cards) if value > 0]
    if not firsts or not lasts:
        return start, end
    return min(firsts), max(lasts)


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
        "flow_skips": {},
        "names": [],
        "notes": [],
        "accelerated": [],
        "model_probes": 0,
        "vocabulary": 0,
    }


def load_inventory(path: Any) -> dict[str, Any]:
    """The stored value lists, or an empty document when this run has none."""
    from .receipt import read_json

    stored = read_json(path)
    document = _empty_document(str(stored.get("index") or ""))
    for key in (
        "start",
        "end",
        "searches",
        "probe_queries",
        "probe_failures",
        "seconds",
        "fields",
        "joints",
        "flows",
        "flow_skips",
        "names",
        "notes",
        "accelerated",
        "model_probes",
        "vocabulary",
        "vocabulary_names",
        "field_plan",
        "planning_complete",
        "unprobed_fields",
        "unprobed_joints",
        "coverage_complete",
        "budget_exhausted",
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


def select_fields(
    cards: Sequence[SourceCard],
    present: Mapping[str, frozenset[str] | None] | None = None,
    vocabulary: Sequence[str] = (),
) -> list[FieldChoice]:
    """Role first, then smallest list; only a name the estate carries may become a query."""
    known = present or {}
    usable: list[tuple[int, FieldChoice]] = []
    labelled: list[FieldChoice] = []
    for card in cards:
        if not card.understood:
            continue
        if present is not None and card.card_id not in known:
            continue  # no presence probe for this source: it contributes no list and no claim
        seen = known.get(card.card_id)
        candidates = _candidates(card)
        owned = {name for _role, name, _stat in candidates}
        if seen is not None:
            extra = [name for name in vocabulary if name in seen and name not in owned]
            candidates = [
                *candidates,
                *(("object", name, FieldStat(name, 0, 0, (), 0)) for name in extra),
            ]
        over_budget = int(_number(card.facts.get("events"))) > INVENTORY_MAX_SCAN_EVENTS
        ranked = sorted(
            candidates,
            key=lambda item: (
                _ROLE_ORDER[item[0]],
                over_budget,
                0 if item[1] in owned else 1,
                item[2].distinct,
                item[1],
            ),
        )
        picked = 0
        for role, name, stat in ranked:
            if _absent(seen, name):
                if name in owned:
                    labelled.append(_choice(card, role, name, stat.distinct, parse_only=True))
                continue
            if picked >= INVENTORY_FIELDS_PER_SOURCE:
                continue
            usable.append((picked, _choice(card, role, name, stat.distinct)))
            picked += 1
    ordered = sorted(
        usable,
        key=lambda item: (
            item[0],
            _ROLE_ORDER[item[1].role],
            item[1].distinct,
            item[1].card_id,
            item[1].field,
        ),
    )
    return [
        *(choice for _rank, choice in ordered[:INVENTORY_MAX_FIELD_SEARCHES]),
        *sorted(labelled, key=lambda item: (item.card_id, _ROLE_ORDER[item.role], item.field)),
    ]


def _probe_order(cards: Sequence[SourceCard]) -> list[SourceCard]:
    """Understood sources, the ones whose best card-owned candidate ranks first first."""
    ranked: list[tuple[tuple[int, int, str, str], SourceCard]] = []
    for card in cards:
        if not card.understood:
            continue
        candidates = sorted(
            _candidates(card), key=lambda item: (_ROLE_ORDER[item[0]], item[2].distinct, item[1])
        )
        if candidates:
            role, name, stat = candidates[0]
            key = (_ROLE_ORDER[role], stat.distinct, card.card_id, name)
        else:
            key = (len(_ROLE_ORDER), 0, card.card_id, "")
        ranked.append((key, card))
    return [card for _key, card in sorted(ranked, key=lambda item: item[0])]


def _choice(
    card: SourceCard, role: str, name: str, distinct: int, *, parse_only: bool = False
) -> FieldChoice:
    return FieldChoice(
        card.source_id,
        card.card_id,
        card.sourcetype,
        name,
        role,
        distinct,
        card.part_field,
        card.part_value,
        parse_only,
    )


def _choice_document(choice: FieldChoice) -> dict[str, Any]:
    return {
        "card_id": choice.card_id,
        "field": choice.field,
        "role": choice.role,
        "distinct": choice.distinct,
        "parse_only": choice.parse_only,
    }


def _restore_choices(
    specs: Sequence[Mapping[str, Any]], cards_by_id: Mapping[str, SourceCard]
) -> list[FieldChoice]:
    choices = []
    for spec in specs:
        card = cards_by_id.get(str(spec.get("card_id") or ""))
        if card is None:
            continue
        choices.append(
            _choice(
                card,
                str(spec.get("role") or "object"),
                str(spec.get("field") or ""),
                int(_number(spec.get("distinct"))),
                parse_only=bool(spec.get("parse_only")),
            )
        )
    return choices


def _pending_field(prober: _Prober, choice: FieldChoice) -> dict[str, Any]:
    record = _field_record(
        choice,
        "pending",
        (),
        searched_window=(prober.start, prober.end),
        parse_only=choice.parse_only,
    )
    record["reason"] = "inventory_budget_exhausted"
    return record


def _sub_budget_expired(prober: _Prober) -> bool:
    budget = getattr(prober.executor, "budget", None)
    expired = getattr(budget, "sub_budget_expired", None)
    return bool(callable(expired) and expired())


class _Prober:
    """Name and field probes cached per source and per field: one query per question."""

    def __init__(
        self,
        executor: HuntExecutor,
        index: str,
        start: float,
        end: float,
        span: tuple[float, float] | None = None,
    ) -> None:
        self.executor = executor
        self.index = index
        self.start = start
        self.end = end
        self.span = span or (start, end)
        self.queries = 0
        self.probe_queries = 0
        self.model_probes = 0
        self.failures: list[str] = []
        self._sources: dict[tuple[str, str], SourcePaths] = {}
        self._fields: dict[tuple[str, str, str], bool] = {}
        self._accelerated: tuple[AcceleratedModel, ...] | None = None
        self._vocabulary: tuple[str, ...] | None = None
        self._present: dict[tuple[str, str, str, str], frozenset[str] | None] = {}

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
        expired = getattr(getattr(self.executor, "budget", None), "sub_budget_expired", None)
        if callable(expired) and expired():
            return [], "inventory_budget_exhausted"
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
        except HuntSubBudgetExceededError:
            return [], "inventory_budget_exhausted"
        except Exception as exc:  # noqa: BLE001 -- one failed aggregate is coverage, not a crash
            return [], f"read_failed:{type(exc).__name__}"
        rows = [dict(row) for row in result.rows]
        # A censored aggregate's rows are partial: the reason travels with them.
        return rows, (str(result.reason) if result.reason else "")

    def probe(
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
            rows, problem = self.probe(
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
            rows, problem = self.probe(
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
            rows, problem = self.probe(
                f"| tstats count where {self._route(name)} by {_field_token(field)}",
                source_id=card.source_id,
            )
            if problem:
                self.failures.append(f"field:{field}:{problem}")
            found = bool(rows)
            self._fields[key] = found
        return found

    def accelerated(self) -> tuple[AcceleratedModel, ...]:
        """Complete models whose summary window covers the read: the only ones rung 1 may use."""
        if self._accelerated is None:
            rows, problem = self.probe(ACCEL_QUERY)
            if problem:
                self.failures.append(f"accelerated:{problem}")
                rows = []
            found: dict[str, AcceleratedModel] = {}
            for row in rows:
                name = _model_root(str(row.get("title") or row.get("summary.id") or ""))
                if not name or name in found or not _summary_complete(row.get("summary.complete")):
                    continue
                earliest = _number(row.get("summary.earliest_time"))
                latest = _number(row.get("summary.latest_time"))
                if not _covers((earliest, latest), self.span):
                    continue
                found[name] = AcceleratedModel(name, earliest, latest)
            self._accelerated = tuple(
                sorted(found.values(), key=lambda item: item.name)[:INVENTORY_MAX_MODEL_PROBES]
            )
        return self._accelerated

    def vocabulary(self) -> tuple[str, ...]:
        """The estate's declared index-time names, one config read per run."""
        if self._vocabulary is None:
            rows, problem = self.probe(VOCABULARY_QUERY, row_cap=INVENTORY_MAX_PROBE_FIELDS)
            if problem:
                self.failures.append(f"vocabulary:{problem}")
                rows = []
            self._vocabulary = _declared_indexed(rows)
        return self._vocabulary

    def present(self, card: SourceCard, vocabulary: Sequence[str]) -> frozenset[str] | None:
        """Names this source's own events carry; None when no probe can answer."""
        key = (card.index, card.sourcetype, card.part_field, card.part_value)
        if key in self._present:
            return self._present[key]
        paths = self.source(card)
        names = _probe_names(card, vocabulary)
        found: frozenset[str] | None = None
        if paths.search_name and names:
            rows, problem = self.probe(
                _presence_query(self._route(paths.search_name, card), names), row_cap=1
            )
            if problem:
                self.failures.append(f"presence:{problem}")
            elif rows:
                found = frozenset(
                    name
                    for index, name in enumerate(names)
                    if _number(rows[0].get(f"p{index}")) > 0
                )
        self._present[key] = found
        return found


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


def _bounded(aggregate: str, rarest: bool = False) -> str:
    """Bound the aggregate server-side: one end of the volume distribution, plus its own total."""
    if rarest:
        return f"{aggregate} | sort 0 count | head {INVENTORY_MAX_TAIL}"
    return (
        f"{aggregate} | eventstats count as inventory_distinct"
        f" | sort 0 -count | head {INVENTORY_MAX_VALUES + 1}"
    )


def _value_query(
    index: str,
    name: str,
    mechanism: str,
    fields: Sequence[str],
    card: SourceCard,
    rarest: bool = False,
) -> str:
    route = f"index={_search_literal(index)} sourcetype={_search_literal(name)}"
    if card.part_field:
        route += f" {_field_token(card.part_field)}={_search_literal(card.part_value)}"
    by = ", ".join(_field_token(field) for field in fields)
    if mechanism == "tstats":
        return _bounded(
            f"| tstats count min(_time) as first max(_time) as last where {route} by {by}", rarest
        )
    return _bounded(
        f"search {route} | stats count min(_time) as first max(_time) as last "
        f"dc(host) as hosts by {by}",
        rarest,
    )


def _read_values(
    prober: _Prober, query: str, row_cap: int | None, card: SourceCard
) -> tuple[list[dict[str, Any]], str, float]:
    part = f"{card.part_field}={card.part_value}" if card.part_field else None
    began = time.monotonic()
    rows, problem = prober.read(query, row_cap, source_id=card.source_id, part=part)
    return rows, problem, round(time.monotonic() - began, 3)


def _tail_values(
    prober: _Prober,
    index: str,
    card: SourceCard,
    choice: FieldChoice,
    mechanism: str,
    name: str,
    model: str = "",
) -> tuple[list[dict[str, Any]], float]:
    """The rarest end of a capped list: one ordered aggregate, bounded by the tail budget."""
    if mechanism == "accelerated":
        query = _model_query(index, name, model, (choice.field,), card, rarest=True)
    else:
        query = _value_query(index, name, mechanism, (choice.field,), card, rarest=True)
    rows, _problem, seconds = _read_values(prober, query, INVENTORY_MAX_TAIL, card)
    return rows, seconds


def _model_query(
    index: str,
    name: str,
    model: str,
    fields: Sequence[str],
    card: SourceCard,
    rarest: bool = False,
) -> str:
    """One summary aggregate; the source predicate keeps the list attributable to its card."""
    route = f"index={_search_literal(index)} sourcetype={_search_literal(name)}"
    if card.part_field:
        route += f" {_field_token(card.part_field)}={_search_literal(card.part_value)}"
    # Model name == root dataset for Authentication/Web; another root's zero rows fall through.
    by = ", ".join(f"{model}.{_field_token(field)}" for field in fields)
    return _bounded(
        f"| tstats summariesonly=true count min(_time) as first max(_time) as last "
        f"from datamodel={model} where {route} by {by}",
        rarest,
    )


def _datamodel_values(
    prober: _Prober,
    index: str,
    card: SourceCard,
    fields: Sequence[str],
    only: str = "",
) -> tuple[AcceleratedModel | None, str, list[dict[str, Any]], str, float]:
    """The first accelerated model that answers this source; the aggregate is its own probe."""
    paths = prober.source(card)
    if not paths.tstats_name:
        return None, "", [], "", 0.0
    for model in prober.accelerated():
        if only and model.name != only:
            continue
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


def _value_rows(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> list[dict[str, Any]]:
    """One value dict per aggregate row; a row missing a value column carries nothing."""
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
    return values


def _capped_values(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    tail: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The volume head plus the rarest rows: a capped list is smaller, never empty."""
    rare = _value_rows(tail, fields)
    head = _value_rows(rows[: INVENTORY_MAX_VALUES - min(len(rare), INVENTORY_MAX_TAIL)], fields)
    seen = {tuple(item["values"][field] for field in fields) for item in head}
    for item in rare:
        key = tuple(item["values"][field] for field in fields)
        if key not in seen:
            seen.add(key)
            head.append(item)
    return head[:INVENTORY_MAX_VALUES]


def _capped_share(rows: Sequence[Mapping[str, Any]], kept: int) -> float:
    """Kept over the aggregate's own distinct total; the rows it surfaced are the floor."""
    total = max((int(_number(row.get("inventory_distinct"))) for row in rows), default=0)
    return round(kept / max(total, len(rows), 1), 6)


def _values(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    mechanism: str,
    problem: str = "",
    tail: Sequence[Mapping[str, Any]] = (),
) -> tuple[str, list[dict[str, Any]], float | None]:
    """complete | capped | unavailable:<mechanism>; only a proven mechanism may report empty."""
    if len(rows) > INVENTORY_MAX_VALUES:
        values = _capped_values(rows, fields, tail)
        return "capped", values, _capped_share(rows, len(values))
    if problem:
        return f"failed:{problem}", [], None
    if rows and not all(_has_column(row, field) for row in rows for field in fields):
        return f"unavailable:{mechanism}", [], None
    values = _value_rows(rows, fields)
    return ("empty" if not values else "complete"), values, None


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
    capped_share: float | None = None,
    parse_only: bool = False,
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
        "capped_share": capped_share,
        "parse_only": parse_only,
        "mechanism": mechanism,
        "name_used": name_used,
        "events_scanned": events_scanned,
        "events_scope": (
            "source"
            if mechanism == "stats"
            else ("summary" if mechanism == "accelerated" else ("aggregate" if mechanism else ""))
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
        if _sub_budget_expired(prober):
            records.append(_pending_field(prober, choice))
            continue
        card = cards_by_id[choice.card_id]
        if choice.parse_only:
            records.append(
                _field_record(
                    choice,
                    "parse_only",
                    (),
                    searched_window=(prober.start, prober.end),
                    parse_only=True,
                )
            )
            continue
        available = int(_number(card.facts.get("events")))
        model, route_name, rows, problem, seconds = _datamodel_values(
            prober, index, card, (choice.field,)
        )
        if _sub_budget_expired(prober) and model is None:
            records.append(_pending_field(prober, choice))
            continue
        if model is not None:
            value_field = f"{model.name}.{choice.field}"
            status, values, share = _values(rows, (value_field,), "accelerated", problem)
            if problem == "inventory_budget_exhausted":
                records.append(_pending_field(prober, choice))
                continue
            if status == "capped":
                tail, tail_seconds = _tail_values(
                    prober, index, card, choice, "accelerated", route_name, model.name
                )
                seconds += tail_seconds
                status, values, share = _values(rows, (value_field,), "accelerated", problem, tail)
            records.append(
                _field_record(
                    choice,
                    status,
                    values,
                    mechanism="accelerated",
                    name_used=f"{model.name}:{route_name}",
                    events_scanned=_scanned("accelerated", rows, available),
                    seconds=seconds,
                    value_field=value_field,
                    accel_window=(model.earliest, model.latest) if model.latest > 0 else None,
                    searched_window=(prober.start, prober.end),
                    capped_share=share,
                )
            )
            continue
        mechanism, name, reason = _mechanism(prober, card, (choice.field,))
        if _sub_budget_expired(prober):
            records.append(_pending_field(prober, choice))
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
        if problem == "inventory_budget_exhausted":
            records.append(_pending_field(prober, choice))
            continue
        status, values, share = _values(rows, (choice.field,), mechanism, problem)
        if status == "capped":
            tail, tail_seconds = _tail_values(prober, index, card, choice, mechanism, name)
            seconds += tail_seconds
            status, values, share = _values(rows, (choice.field,), mechanism, problem, tail)
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
                capped_share=share,
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
    capped_share: float | None = None,
) -> dict[str, Any]:
    return {
        "source_id": card.source_id,
        "card_id": card.card_id,
        "sourcetype": card.sourcetype,
        "part": {"field": card.part_field, "value": card.part_value} if card.part_field else None,
        "fields": [{"role": record["role"], "field": record["field"]} for record in picked],
        "status": status,
        "capped_share": capped_share,
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
        if _sub_budget_expired(prober):
            record = _joint_record(card, picked, "pending", "", "", 0, 0.0, (), window)
            record["reason"] = "inventory_budget_exhausted"
            joints.append(record)
            continue
        names = [str(record["field"]) for record in picked]
        mechanism, name, reason = _mechanism(prober, card, names)
        if _sub_budget_expired(prober):
            record = _joint_record(card, picked, "pending", "", "", 0, 0.0, (), window)
            record["reason"] = "inventory_budget_exhausted"
            joints.append(record)
            continue
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
        if problem == "inventory_budget_exhausted":
            record = _joint_record(card, picked, "pending", mechanism, name, 0, seconds, (), window)
            record["reason"] = "inventory_budget_exhausted"
            joints.append(record)
            continue
        status, values, share = _values(rows, names, mechanism, problem)
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
                share,
            )
        )
    return joints


def _entity_token(value: str) -> bool:
    if len(value) < 4:
        return False
    return bool(_IPV4.fullmatch(value) or any(char.isalpha() for char in value))


def _single_hosts(cards: Sequence[SourceCard]) -> dict[str, str]:
    """A source that sits on exactly one host names it; a multi-host source stays unknown."""
    found: dict[str, str] = {}
    for card in cards:
        names = [str(name) for name in (card.facts.get("hosts") or ()) if str(name)]
        if len(names) == 1 and int(_number(card.facts.get("host_count"))) <= 1:
            found[card.card_id] = names[0]
    return found


def _role_vectors(records: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[tuple[str, str]]]:
    """Each card's selected role plan: two sources with one plan read one shape."""
    found: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for record in records:
        if record.get("role") and record.get("field"):
            found[str(record.get("card_id") or "")].add((str(record["role"]), str(record["field"])))
    return {card_id: frozenset(pairs) for card_id, pairs in found.items()}


def _flow_steps(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Steps per casefolded value, with the label each value was written as.

    A capped list proves presence, never absence: its values may carry a flow.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for record in records:
        if record.get("status") not in ("complete", "capped"):
            continue
        part = record.get("part")
        for item in record.get("values") or ():
            if not isinstance(item, Mapping):
                continue
            raw = str(item.get("value") or "")
            labels.setdefault(raw.casefold(), raw)
            grouped[raw.casefold()].append(
                {
                    "source_id": str(record.get("source_id") or ""),
                    "card_id": str(record.get("card_id") or ""),
                    "sourcetype": str(record.get("sourcetype") or ""),
                    "part": part if isinstance(part, Mapping) else None,
                    "field": str(record.get("field") or ""),
                    "role": str(record.get("role") or ""),
                    "mechanism": str(record.get("mechanism") or ""),
                    "name_used": str(record.get("name_used") or ""),
                    "value": raw,
                    "events": item.get("events"),
                    "first_seen": item.get("first_seen"),
                    "last_seen": item.get("last_seen"),
                }
            )
    return grouped, labels


def _flow_digest(step: Mapping[str, Any]) -> str:
    """A step's own span: two sources reporting the same one saw the same raw events."""
    raw = (step.get("first_seen"), step.get("last_seen"))
    return hashlib.sha1(str(raw).encode()).hexdigest()[:16]


def _flow_pair(
    ordered: Sequence[Mapping[str, Any]], vectors: Mapping[str, frozenset[tuple[str, str]]]
) -> tuple[Mapping[str, Any] | None, str]:
    """(later, reason): the first other source that is neither a duplicate nor the same shape."""
    ingress = ordered[0]
    digest = _flow_digest(ingress)
    start = _number(ingress.get("first_seen"))
    others = [step for step in ordered[1:] if step["source_id"] != ingress["source_id"]]
    if not others:
        return None, "single_source"
    distinct = [step for step in others if _flow_digest(step) != digest]
    if not distinct:
        return None, "duplicate"
    ordered_ok = [step for step in distinct if _number(step.get("first_seen")) > start]
    if not ordered_ok:
        return None, "order"
    different = [
        step
        for step in ordered_ok
        if vectors.get(str(step["card_id"])) != vectors.get(str(ingress["card_id"]))
    ]
    if not different:
        return None, "same_role_vector"
    for step in different:
        gap = _number(step.get("first_seen")) - _number(ingress.get("last_seen"))
        if gap <= FLOW_MAX_GAP_SECONDS:
            return step, ""
    return None, "gap"


def _probe_hosts(
    prober: _Prober, index: str, step: Mapping[str, Any]
) -> tuple[bool, tuple[str, ...]]:
    """(probed, hosts) for one endpoint; a search-time field cannot answer from the tsidx."""
    name = str(step.get("name_used") or "")
    if step.get("mechanism") != "tstats" or not name:
        return False, ()
    route = f"index={_search_literal(index)} sourcetype={_search_literal(name)}"
    part = step.get("part")
    if isinstance(part, Mapping) and part.get("field"):
        route += (
            f" {_field_token(str(part['field']))}={_search_literal(str(part.get('value') or ''))}"
        )
    route += f" {_field_token(str(step.get('field') or ''))}={_search_literal(str(step['value']))}"
    rows, problem = prober.probe(f"| tstats count where {route} by host", FLOW_HOST_ROWS)
    if problem:
        return False, ()
    return True, tuple(sorted({str(row.get("host") or "") for row in rows} - {""}))


def _flow_host(
    prober: _Prober,
    index: str,
    ingress: Mapping[str, Any],
    later: Mapping[str, Any],
    hosts: Mapping[str, str],
    budget: list[int],
) -> tuple[str, str, list[str]]:
    """("shared"|"disjoint"|"unproven", one host or "", every shared host both endpoints see)."""
    seen: dict[str, set[str]] = {}
    for step in (ingress, later):
        card_id = str(step.get("card_id") or "")
        known = hosts.get(card_id, "")
        if known:
            seen[card_id] = {known}
            continue
        if budget[0] <= 0:
            continue
        budget[0] -= 1
        probed, found = _probe_hosts(prober, index, step)
        if probed:
            seen[card_id] = set(found)
    if len(seen) < 2:
        return "unproven", "", []
    shared = sorted(set.intersection(*seen.values()))
    if not shared:
        return "disjoint", "", []
    return "shared", shared[0] if len(shared) == 1 else "", shared


def _flows(
    records: Sequence[Mapping[str, Any]],
    hosts: Mapping[str, str],
    prober: _Prober,
    index: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Flows: (entity, host) ordered across role-different sources; a duplicate is not one."""
    grouped, labels = _flow_steps(records)
    vectors = _role_vectors(records)
    flows: list[dict[str, Any]] = []
    skips: dict[str, int] = defaultdict(int)
    budget = [FLOW_MAX_PROBES]
    # the rarest value first: the flow budget is spent on traverses, never on ambient volume
    order = sorted(
        grouped, key=lambda key: (sum(_number(step.get("events")) for step in grouped[key]), key)
    )
    for key in order:
        steps = grouped[key]
        value = labels[key]
        sources = {str(step["source_id"]) for step in steps}
        if not _entity_token(value) or is_sentinel_value(value):
            skips["not_entity"] += 1
            continue
        if len(sources) < 2:
            skips["single_source"] += 1
            continue
        if len(sources) > FLOW_MAX_SOURCES:
            skips["ambient"] += 1
            continue
        if len(flows) >= FLOW_MAX_FLOWS:
            skips["capped"] += 1
            continue
        ordered = sorted(
            steps, key=lambda step: (_number(step.get("first_seen")), str(step["source_id"]))
        )
        later, reason = _flow_pair(ordered, vectors)
        if later is None:
            skips[reason] += 1
            continue
        state, host, shared_hosts = _flow_host(prober, index, ordered[0], later, hosts, budget)
        if state == "disjoint":
            skips["host"] += 1
            continue
        flows.append(
            {
                "value": value,
                "status": "complete",
                "host": host,
                "hosts": shared_hosts,
                "host_proven": state == "shared",
                "ingress": ordered[0]["source_id"],
                "later": later["source_id"],
                "steps": [ordered[0], later],
            }
        )
    flows.sort(key=lambda item: (str(item["value"]).casefold(), str(item["ingress"])))
    return flows, dict(sorted(skips.items()))


def _restore_probe_state(
    prober: _Prober, prior: Mapping[str, Any], cards_by_id: Mapping[str, SourceCard]
) -> bool:
    specs = prior.get("field_plan")
    if not prior.get("planning_complete") or not isinstance(specs, list):
        return False
    prober._vocabulary = tuple(str(name) for name in prior.get("vocabulary_names") or ())
    prober._accelerated = tuple(
        AcceleratedModel(
            str(item.get("model") or ""),
            _number(item.get("earliest")),
            _number(item.get("latest")),
        )
        for item in prior.get("accelerated") or ()
        if isinstance(item, Mapping) and item.get("model")
    )
    for item in prior.get("names") or ():
        if not isinstance(item, Mapping):
            continue
        card = cards_by_id.get(str(item.get("card_id") or ""))
        if card is None:
            continue
        prober._sources[(card.index, card.sourcetype)] = SourcePaths(
            str(item.get("tstats_name") or ""),
            str(item.get("search_name") or ""),
            int(_number(item.get("tstats_events"))),
            tuple(str(name) for name in item.get("observed") or ()),
            bool(item.get("failed")),
        )
    return True


def _merge_field_records(
    choices: Sequence[FieldChoice],
    previous: Sequence[Mapping[str, Any]],
    fresh: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    keyed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in (*previous, *fresh):
        key = (str(item.get("source_id")), str(item.get("card_id")), str(item.get("field")))
        if item.get("status") == "pending":
            continue
        keyed[key] = item
    new = {
        (str(item.get("source_id")), str(item.get("card_id")), str(item.get("field"))): item
        for item in fresh
    }
    return [
        dict(
            keyed.get((choice.source_id, choice.card_id, choice.field))
            or new[(choice.source_id, choice.card_id, choice.field)]
        )
        for choice in choices
    ]


def _joint_signature(item: Mapping[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (
        str(item.get("card_id") or ""),
        tuple(
            (str(field.get("role") or ""), str(field.get("field") or ""))
            for field in item.get("fields") or ()
            if isinstance(field, Mapping)
        ),
    )


def _merge_joint_records(
    prober: _Prober,
    index: str,
    planned: Sequence[tuple[SourceCard, list[Mapping[str, Any]]]],
    previous: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    prior = {
        _joint_signature(item): item
        for item in previous
        if isinstance(item, Mapping) and item.get("status") != "pending"
    }
    missing = [
        (card, picked)
        for card, picked in planned
        if (card.card_id, tuple((str(item["role"]), str(item["field"])) for item in picked))
        not in prior
    ]
    new = _enumerate_joints(prober, index, missing)
    fresh = {_joint_signature(item): item for item in new}
    return [
        dict(
            prior.get(
                (card.card_id, tuple((str(item["role"]), str(item["field"])) for item in picked))
            )
            or fresh[
                (card.card_id, tuple((str(item["role"]), str(item["field"])) for item in picked))
            ]
        )
        for card, picked in planned
    ]


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
            "card_id": choice.card_id,
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
    *,
    prior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Enumerate selected fields, resuming only field specs the prior pass did not finish."""
    began = time.monotonic()
    previous = prior or {}
    if previous and not inventory_scope_matches(previous, index, start, end):
        previous = {}
    prober = _Prober(executor, index, start, end, _span(cards, start, end))
    cards_by_id = {card.card_id: card for card in cards}
    restored = _restore_probe_state(prober, previous, cards_by_id)
    if restored:
        choices = _restore_choices(previous.get("field_plan") or (), cards_by_id)
        vocabulary = prober._vocabulary or ()
        planning_complete = True
    else:
        vocabulary = prober.vocabulary()
        known = {
            card.card_id: prober.present(card, vocabulary)
            for card in _probe_order(cards)[:INVENTORY_MAX_PRESENCE_PROBES]
        }
        choices = select_fields(cards, known, vocabulary)
        planning_complete = not any(
            item.endswith("inventory_budget_exhausted") for item in prober.failures
        )
    previous_fields = [item for item in previous.get("fields") or () if isinstance(item, Mapping)]
    previous_by_key = {
        (str(item.get("source_id")), str(item.get("card_id")), str(item.get("field"))): item
        for item in previous_fields
    }
    remaining = [
        choice
        for choice in choices
        if previous_by_key.get((choice.source_id, choice.card_id, choice.field), {}).get("status")
        == "pending"
        or (choice.source_id, choice.card_id, choice.field) not in previous_by_key
    ]
    fresh_fields = _enumerate_fields(prober, index, remaining, cards_by_id)
    fields = _merge_field_records(choices, previous_fields, fresh_fields)
    planned = _joint_plan(fields, cards_by_id)
    joints = _merge_joint_records(
        prober,
        index,
        planned,
        [item for item in previous.get("joints") or () if isinstance(item, Mapping)],
    )
    jointed = {str(item["card_id"]) for item in joints if item.get("status") == "complete"}
    joints.extend(_single_field_joints(fields, jointed))
    accelerated = prober.accelerated()
    flows, flow_skips = _flows(fields, _single_hosts(cards), prober, index)
    names = (
        list(previous.get("names") or ())
        if restored
        else _name_documents(choices, cards_by_id, prober)
    )
    unprobed_fields = [
        {key: item.get(key) for key in ("source_id", "card_id", "field")}
        for item in fields
        if item.get("status") == "pending"
    ]
    unprobed_joints = [
        {
            "source_id": item.get("source_id"),
            "card_id": item.get("card_id"),
            "fields": item.get("fields"),
        }
        for item in joints
        if item.get("status") == "pending"
    ]
    budget_exhausted = _sub_budget_expired(prober)
    searches = int(previous.get("searches") or 0) + prober.queries - prober.probe_queries
    probe_queries = int(previous.get("probe_queries") or 0) + prober.probe_queries
    failures = list(previous.get("probe_failures") or ()) + prober.failures
    document = _empty_document(index)
    document.update(
        {
            "index": index,
            "start": start,
            "end": end,
            "searches": searches,
            "probe_queries": probe_queries,
            "model_probes": int(previous.get("model_probes") or 0) + prober.model_probes,
            "probe_failures": failures[:16],
            "seconds": round(float(previous.get("seconds") or 0.0) + time.monotonic() - began, 3),
            "fields_selected": sum(1 for choice in choices if not choice.parse_only),
            "fields": fields,
            "joints": joints,
            "flows": flows,
            "flow_skips": flow_skips,
            "names": names,
            "vocabulary": len(vocabulary),
            "vocabulary_names": list(vocabulary),
            "field_plan": [_choice_document(choice) for choice in choices],
            "planning_complete": planning_complete,
            "unprobed_fields": unprobed_fields,
            "unprobed_joints": unprobed_joints,
            "budget_exhausted": budget_exhausted,
            "coverage_complete": planning_complete
            and not unprobed_fields
            and not unprobed_joints
            and not budget_exhausted,
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
        "vocabulary": int(document.get("vocabulary") or 0),
        "events_scanned": scanned,
        "values": values,
        "joints": len(document.get("joints") or ()),
        "flows": len(document.get("flows") or ()),
        "flows_skipped": sum(int(count) for count in (document.get("flow_skips") or {}).values()),
        "flow_skips": dict(document.get("flow_skips") or {}),
        "flows_proven": sum(
            1
            for item in document.get("flows") or ()
            if isinstance(item, Mapping) and item.get("host_proven")
        ),
        "coverage_complete": bool(document.get("coverage_complete")),
        "unprobed_fields": list(document.get("unprobed_fields") or ()),
        "unprobed_joints": list(document.get("unprobed_joints") or ()),
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
                "capped_share": item.get("capped_share"),
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


def _consumers(cards: Sequence[SourceCard]) -> dict[str, frozenset[str]]:
    """The consumers each source's cards permit, unioned across that source's parts."""
    found: dict[str, set[str]] = defaultdict(set)
    for card in cards:
        found[card.source_id].update(card_consumers(card))
    return {source: frozenset(names) for source, names in found.items()}


def apply_inventory(
    behaviours: Sequence[Behaviour],
    document: Mapping[str, Any],
    facts: Mapping[str, SourceFacts],
    cards: Sequence[SourceCard],
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
    candidates = _unseen_candidates(document, seen, facts, _consumers(cards))
    summary = inventory_summary(document)
    return [*corrected, *candidates], {
        "first_seen_replaced": replaced,
        "candidates": len(candidates),
        "flows": summary["flows"],
        "flows_skipped": summary["flows_skipped"],
        "flow_skips": summary["flow_skips"],
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
    consumers: Mapping[str, frozenset[str]],
) -> list[Behaviour]:
    per_source: dict[str, list[Behaviour]] = defaultdict(list)
    for joint in document.get("joints") or ():
        if not isinstance(joint, Mapping) or joint.get("status") != "complete":
            continue
        source_id = str(joint.get("source_id") or "")
        if not consumers.get(source_id, frozenset()) & ROLE_CONSUMERS:
            continue  # no generator reads behaviours from this card
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
