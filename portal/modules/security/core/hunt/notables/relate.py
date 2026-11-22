"""Pull distinctive-identity neighbours from Stage 1 notables and assemble cases over the spine.

v2 (from docs/hunt/RELATE_LINKAGE_REPORT.md): pivot on the identity-field values a card
declares — the attacker's source IP for web sources, the user for auth/audit sources — not on
program names or cross-host-rare-but-actually-common values. Distinctiveness is the entity's
share of its own source's events (dominance), learned from the run's behaviour store, not a
host/source rarity table. The pivot window is the episode: the measured activity span of the
seed's identities, bounded by the run's own time range, never a fixed ±1 h.

S3: cases are built over the spine (S2) — union-find over the episodes and signals that share
an entity, and over flow values whose endpoint role vectors differ, bounded by a 24 h window
and requiring two independent pieces of evidence. A single signal is a notable, not a case.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
import time
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..engine import Search, _literal_term_segments, _search_literal
from ..executor import executor_for
from .inventory import INVENTORY_FILE, load_inventory
from .knowledge import PROOF_INDEXES
from .receipt import progress_update, read_json, write_json
from .run import NOTABLES_FILE, SOURCES_FILE, STORE_FILE, configure_ledger, read_notables
from .sample import shared_source_names, source_route
from .spine import FILE, SPINE_FILE, SPINE_RECEIPT, classify, event_id

RELATE_FILE = "relate.json"
CASES_FILE = "cases.json"
MAX_SEEDS = 40  # effort budget: seed notables expanded into episodes
MAX_ENTITIES_PER_SEED = 5  # effort budget: identity pivots read from one notable
MAX_EVENTS_PER_QUERY = 20  # effort budget: neighbouring rows retained per identity query
EVIDENCE_CHARS = 400  # effort budget: event preview kept beside its reproducible reference
PROMOTE_HEAD = 50  # the scoreboard's smallest recall cut; a case already inside it is strong
PROMOTE_PER_CASE = 3  # effort budget: weak members one strong case may lift into the head
PROMOTE_TOTAL = 12  # effort budget: lifts across every strong case in the run
CASE_MAX_SPAN_SECONDS = 24 * 3600.0  # a case is one day at most
CASE_LINK_GAP_SECONDS = 4 * 3600.0  # the spine's episode adjacency window
CASE_MIN_EVIDENCE = 2  # a case is two independent pieces of evidence, never one signal
CASE_EVIDENCE_ROWS = 20  # effort budget: evidence rows kept beside a case
CASE_WEIGHTS = (1.0, 1.0, 1.0, 1.0, 1.0)  # sources, signals, anchor, distinctiveness, coherence
SET_NOVELTY_FIELD = "unit"  # the structural field a systemd unit name arrives in
SET_NOVELTY_MIN_CLASS_VALUES = 3  # a host has a routine class once it produces this many values
SET_NOVELTY_MAX_EVENTS = 2  # a two-event step still needs a unit that can hold it
SET_NOVELTY_CLASS_EVENTS = 50  # a file class this small on one host is not routine
SET_NOVELTY_MAX_ROWS = 200  # effort budget: candidates one run may carry
_ROLE_ORDER = {"actor": 0, "action": 1, "object": 2, "from": 3, "to": 4, "outcome": 5}
_DECIDING_ROLES = frozenset({"actor", "from", "to"})  # a participant, not merely a holder
_PROGRAM_FIELD = "program"  # a template source keys its actor on the program, not an identity
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_CLF_TIME = re.compile(r"\[\d{1,2}/\w{3}/\d{4}:")  # an access-log timestamp is not an identity
_SOURCE_IN_QUERY = re.compile(r'source="([^"]+)"')  # the source path the read actually named
_UNIT_PAIR = re.compile(r"""\bunit=("[^"]*"|'[^']*'|[^\s,;]+)""")
_FILE_TOKEN = re.compile(r"""[^\s,;()\[\]{}"']+""")
# attack-signal generators rank ahead of the statistical ones when seeds are chosen
_SEED_GENERATOR_PRIORITY = {"similar_to_known": 0, "alerts": 1}


def _is_timestamp(value: str) -> bool:
    return bool(_CLF_TIME.search(value))


def _identity_fields(out: Path) -> dict[str, dict[str, Any]]:
    """Per source_id: the structure, the identity fields and the card's full role plan.

    The cards carry their recorded `role_overrides` (the behaviours stage's identity plan):
    the actor field is the identity unless it is `program` (a template source, where the
    literal object slots carry the user instead). This is the card's own identity model, not a
    list of program names.
    """
    payload = read_json(out / SOURCES_FILE)
    info: dict[str, dict[str, Any]] = {}
    for card in payload.get("cards") or ():
        if not isinstance(card, Mapping):
            continue
        source_id = str(card.get("source_id") or f"{card.get('index')}:{card.get('sourcetype')}")
        overrides = card.get("role_overrides")
        if not isinstance(overrides, Mapping):
            overrides = {}
        actor = overrides.get("actor")
        actor_field = str((actor or {}).get("field") or "")
        action = overrides.get("action")
        action_field = str((action or {}).get("field") or "")
        objects = [
            str(item.get("field") or "")
            for item in overrides.get("objects") or ()
            if isinstance(item, Mapping) and str(item.get("mode") or "") == "literal"
        ]
        entry = info.setdefault(
            source_id,
            {
                "fmt": str(card.get("structure") or "text"),
                "actor_field": "",
                "action_field": "",
                "objects": [],
                "roles": {},
                "sources": [],
                "sourcetype": str(card.get("sourcetype") or ""),
                "shared_sources": [],
            },
        )
        if actor_field:
            entry["actor_field"] = actor_field
        if action_field:
            entry["action_field"] = action_field
        entry["objects"] = sorted(set(entry["objects"]) | set(objects))
        planned = card.get("roles")
        if isinstance(planned, Mapping):
            for name, fields in planned.items():
                entry["roles"][str(name)] = sorted(
                    set(entry["roles"].get(str(name), [])) | {str(field) for field in fields or ()}
                )
        facts = card.get("facts")
        if isinstance(facts, Mapping):
            entry["sources"] = sorted(
                set(entry["sources"]) | {str(name) for name in facts.get("sources") or ()}
            )
            entry["shared_sources"] = sorted(
                set(entry["shared_sources"]) | set(facts.get("shared_sources") or ())
            )
    shared = shared_source_names({key: entry["sources"] for key, entry in info.items()})
    for entry in info.values():
        entry["shared_sources"].extend(s for s in entry["sources"] if s.casefold() in shared)
    return info


def _route(info: Mapping[str, Any]) -> str:
    """A source filter selecting this seed's own source, mirroring the behaviour-stage route."""
    sources = info.get("sources") or ()
    if sources:
        route, _ = source_route(
            str(info.get("sourcetype") or ""), sources, info.get("shared_sources") or ()
        )
        return route
    return ""


def _identity_role(info: Mapping[str, Any]) -> str:
    """The role whose values are identities: `actor` unless the actor is the program name."""
    actor_field = str(info.get("actor_field") or "")
    return "actor" if actor_field and actor_field != _PROGRAM_FIELD else "object"


def _load_metrics(
    store: Path,
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], tuple[float, float]]]:
    """Within-source share and activity span per (source_id, value), learned from the run.

    `share` is the value's event count over its source's total events — the entity dominates
    its source when the share is high, which is the report's distinctiveness signal, not a
    cross-host rarity. `span` is that value's first-to-last activity in its source, the
    episode-sized window bound. Both cover actor and object roles, plus addresses embedded in
    a behaviour's text (an IP inside an access-log request line, mirrored into Suricata flows).
    """
    shares: dict[tuple[str, str], float] = {}
    spans: dict[tuple[str, str], tuple[float, float]] = {}
    if not store.is_file():
        return shares, spans
    con = duckdb.connect(str(store), read_only=True)
    try:
        totals = {
            str(source_id): float(events)
            for source_id, events in con.execute(
                "SELECT source_id, events FROM source_stats"
            ).fetchall()
        }
        rows = con.execute(
            "SELECT source_id, actor AS value, SUM(events) AS n, MIN(first_seen) AS lo, "
            "MAX(last_seen) AS hi FROM behaviours WHERE NULLIF(actor, '') IS NOT NULL "
            "GROUP BY source_id, actor "
            "UNION ALL "
            "SELECT source_id, object AS value, SUM(events) AS n, MIN(first_seen) AS lo, "
            "MAX(last_seen) AS hi FROM behaviours WHERE NULLIF(object, '') IS NOT NULL "
            "GROUP BY source_id, object"
        ).fetchall()
        addresses: set[str] = set()
        for source_id, value, n, lo, hi in rows:
            source = str(source_id)
            key = (source, str(value).casefold())
            total = totals.get(source, 0.0)
            if total:
                shares[key] = float(n) / total
            if lo is not None and hi is not None:
                spans[key] = (float(lo), float(hi))
            addresses.update(_IPV4.findall(str(value)))
        for address in sorted(addresses):
            for source_id, n, lo, hi in con.execute(
                "SELECT source_id, SUM(events), MIN(first_seen), MAX(last_seen) FROM behaviours "
                "WHERE instr(actor, ?) > 0 OR instr(action, ?) > 0 OR instr(object, ?) > 0 "
                "GROUP BY source_id",
                [address, address, address],
            ).fetchall():
                source = str(source_id)
                key = (source, address.casefold())
                total = totals.get(source, 0.0)
                if total:
                    shares[key] = max(shares.get(key, 0.0), float(n) / total)
                if lo is not None and hi is not None:
                    previous = spans.get(key)
                    spans[key] = (
                        (min(previous[0], float(lo)), max(previous[1], float(hi)))
                        if previous
                        else (float(lo), float(hi))
                    )
    finally:
        con.close()
    return shares, spans


def _share_weight(source_id: str, value: str, shares: Mapping[tuple[str, str], float]) -> float:
    """The entity's within-source share; unknown is 0.0 (no measured dominance)."""
    return float(shares.get((source_id, str(value).casefold()), 0.0))


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _seed_id(row: Mapping[str, Any], rank: int) -> str:
    found = str(row.get("notable_id") or row.get("content_key") or "")
    return (
        found or hashlib.sha1(f"{rank}:{json.dumps(row, sort_keys=True)}".encode()).hexdigest()[:16]
    )


def _entities(
    row: Mapping[str, Any],
    identity: Mapping[str, Mapping[str, Any]],
    shares: Mapping[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """The identity pivots of one seed: addresses plus identity-field values, not program names.

    An address is always a potential identity (the web-phase link). A literal value is a pivot
    only when its role is the source's identity role — the actor for `uid`/`src_ip`/`v1`
    sources, the object for `program` sources — and only when it is not a timestamp or a
    wildcard template. Short numeric identities (uids) stay pivots through their field query.
    """
    source_id = str(row.get("source_id") or "")
    info = identity.get(source_id) or {}
    id_role = _identity_role(info)
    actor_field = str(info.get("actor_field") or "")
    structured = str(info.get("fmt") or "") in ("kv", "delimited")
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(key: tuple[str, str], entity: dict[str, Any]) -> None:
        found.setdefault(key, entity)

    for item in row.get("entities") or ():
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip()
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        is_address = False
        for match in _IPV4.finditer(value):
            try:
                address = str(ipaddress.IPv4Address(match.group()))
            except ValueError:
                continue
            is_address = True
            add(
                ("address", address),
                {
                    "role": "address",
                    "value": address,
                    "terms": (address,),
                    "case_anchor": True,
                    "kind": "address",
                    "field": None,
                    "weight": _share_weight(source_id, address, shares),
                },
            )
        if role == id_role and "*" not in value and "?" not in value and not _is_timestamp(value):
            if is_address:
                continue  # the value is already pivoted as an address
            field = actor_field if structured and id_role == "actor" else None
            terms = _literal_term_segments(value)
            if not terms and field is None:
                continue  # a short value with no field query cannot be reproduced
            add(
                (role.casefold(), value.casefold()),
                {
                    "role": role,
                    "value": value,
                    "terms": terms,
                    "case_anchor": True,
                    "kind": "user",
                    "field": field,
                    "weight": _share_weight(source_id, value, shares),
                },
            )
    return list(found.values())[:MAX_ENTITIES_PER_SEED]


def _episode_window(
    row: Mapping[str, Any],
    source_id: str,
    start: float,
    end: float,
    spans: Mapping[tuple[str, str], tuple[float, float]],
    entities: Sequence[Mapping[str, Any]],
) -> tuple[float, float]:
    """The window where the seed's identities stay active, bounded by the run's own range."""
    lows: list[float] = []
    highs: list[float] = []
    for entity in entities:
        span = spans.get((source_id, str(entity["value"]).casefold()))
        if span is not None:
            lows.append(span[0])
            highs.append(span[1])
    evidence = [item for item in row.get("evidence") or () if isinstance(item, Mapping)]
    for item in evidence:
        earliest, latest = _number(item.get("earliest")), _number(item.get("latest"))
        if earliest is not None:
            lows.append(earliest)
        if latest is not None:
            highs.append(latest)
    first, last = _number(row.get("first_seen")), _number(row.get("last_seen"))
    if first is not None:
        lows.append(first)
    if last is not None:
        highs.append(last)
    low = min(lows) if lows else start
    high = max(highs) if highs else low
    return max(start, low), min(end, max(high, low))


def _query(index: str, entity: Mapping[str, Any], route: str = "", anchor: float = 0.0) -> str:
    """A reproducible pivot query scoped to the seed's source, sorted toward the seed's time."""
    value = str(entity["value"])
    if entity.get("field"):
        body = f"{entity['field']}={_search_literal(value)}"
    else:
        terms = " ".join(f"TERM({_search_literal(term)})" for term in entity["terms"])
        options = ([f"({terms})"] if terms else []) + [f"(host={_search_literal(value)})"]
        body = "(" + " OR ".join(options) + ")"
    parts = [f"index={_search_literal(index)}", route, body]
    return (
        "search "
        + " ".join(part for part in parts if part)
        + f" | eval _relate_delta=abs(_time - {anchor:.3f})"
        + f" | sort limit={MAX_EVENTS_PER_QUERY} _relate_delta"
    )


def _seed_anchor(
    row: Mapping[str, Any],
    fallback: float,
    spans: Mapping[tuple[str, str], tuple[float, float]],
    source_id: str,
    entities: Sequence[Mapping[str, Any]],
) -> float:
    """The seed's own time to sort toward: its first_seen, else its earliest evidence."""
    first = _number(row.get("first_seen"))
    if first is not None and first > 0:
        return first
    for item in row.get("evidence") or ():
        if isinstance(item, Mapping):
            earliest = _number(item.get("earliest"))
            if earliest is not None and earliest > 0:
                return earliest
    for entity in entities:
        span = spans.get((source_id, str(entity["value"]).casefold()))
        if span is not None:
            return span[0]
    return fallback


def _seed_priority(row: Mapping[str, Any]) -> int:
    return _SEED_GENERATOR_PRIORITY.get(str(row.get("generator") or ""), 2)


def _seed_distinctiveness(entities: Sequence[Mapping[str, Any]]) -> float:
    """The strongest identity a notable carries: its max within-source share."""
    return max((float(entity.get("weight", 0.0) or 0.0) for entity in entities), default=0.0)


def _seed_records(
    rows: Sequence[dict[str, Any]],
    start: float,
    end: float,
    identity: Mapping[str, Mapping[str, Any]],
    shares: Mapping[tuple[str, str], float],
    spans: Mapping[tuple[str, str], tuple[float, float]],
) -> list[dict[str, Any]]:
    """The most attack-likely notables become seeds, ranked by identity distinctiveness.

    Seed selection ranks every notable on the evidence relate itself pivots on — the
    within-source share of the identity entities it carries — with the attack-signal
    generators first, not on the notable's position in the merged (interleaved) file.
    """
    candidates: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        source_id = str(row.get("source_id") or "")
        entities = _entities(row, identity, shares)
        if not entities:
            continue
        low, high = _episode_window(row, source_id, start, end, spans, entities)
        if high <= low:
            continue
        candidates.append(
            {
                "row": row,
                "source_id": source_id,
                "entities": entities,
                "low": low,
                "high": high,
                "position": position,
            }
        )
    candidates.sort(
        key=lambda candidate: (
            _seed_priority(candidate["row"]),
            -_seed_distinctiveness(candidate["entities"]),
            candidate["position"],
        )
    )
    seeds: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates[:MAX_SEEDS]):
        row = candidate["row"]
        source_id = candidate["source_id"]
        entities = candidate["entities"]
        low, high = candidate["low"], candidate["high"]
        seeds.append(
            {
                "id": _seed_id(row, rank),
                "rank": rank,
                "original_rank": rank,
                "row": row,
                "source_id": source_id,
                "route": _route(identity.get(source_id) or {}),
                "anchor": _seed_anchor(row, low, spans, source_id, entities),
                "entities": entities,
                "start": low,
                "end": high,
                "center": (low + high) / 2,
            }
        )
    return seeds


def _requests(
    index: str, seeds: Sequence[Mapping[str, Any]]
) -> tuple[list[tuple[str, float, float, str, int | None]], list[dict[str, Any]]]:
    requests: list[tuple[str, float, float, str, int | None]] = []
    details: list[dict[str, Any]] = []
    for seed in seeds:
        for entity in seed["entities"]:
            query = _query(index, entity, seed["route"], seed["anchor"])
            requests.append((query, seed["start"], seed["end"], "relate", MAX_EVENTS_PER_QUERY))
            details.append({"seed": seed, "entity": entity, "query": query})
    return requests, details


def _event_identity(row: Mapping[str, Any]) -> tuple[str, str, float, str] | None:
    raw = str(row.get("_raw") or "")
    host = str(row.get("host") or "")
    source = str(row.get("source") or "")
    moment = _number(row.get("_time"))
    if not raw or not host or not source or moment is None:
        return None
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return host, source, moment, digest


def _entity_supported(entity: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    value = str(entity["value"])
    raw = str(row.get("_raw") or "")
    candidates = list(entity.get("terms") or ()) or [value]
    return (
        any(
            re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", raw, re.IGNORECASE)
            for candidate in candidates
        )
        or value.casefold() == str(row.get("host") or "").casefold()
    )


def _event_query(index: str, row: Mapping[str, Any], raw: str, moment: float) -> str:
    predicates = [f"index={_search_literal(index)}"]
    for name in ("host", "source"):
        value = str(row.get(name) or "")
        if value:
            predicates.append(f"{name}={_search_literal(value)}")
    predicates.extend(f"TERM({_search_literal(term)})" for term in _literal_term_segments(raw)[:3])
    predicates.extend((f"earliest={moment - 1:.3f}", f"latest={moment + 1:.3f}"))
    return "search " + " ".join(predicates) + " | head 5"


def _event_ref(index: str, row: Mapping[str, Any], query: str) -> dict[str, Any] | None:
    identity = _event_identity(row)
    if identity is None:
        return None
    host, source, moment, digest = identity
    raw = str(row["_raw"])
    return {
        "event_id": str(row.get("_cd") or digest[:16]),
        "index": index,
        "host": host,
        "source": source,
        "sourcetype": str(row.get("sourcetype") or ""),
        "time": moment,
        "raw_sha256": digest,
        "line": raw[:EVIDENCE_CHARS],
        "query": _event_query(index, row, raw, moment),
        "relation_query": query,
        "earliest": moment - 1,
        "latest": moment + 1,
    }


def _gather(
    executor: Any,
    requests: Sequence[tuple[str, float, float, str, int | None]],
    details: Sequence[Mapping[str, Any]],
) -> tuple[dict[tuple[str, str, float, str], dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[tuple[str, str, float, str], dict[str, Any]] = {}
    outcomes = executor.read_many(requests)
    coverage: list[dict[str, Any]] = []
    for detail, outcome in zip(details, outcomes, strict=True):
        seed = detail["seed"]
        entity = detail["entity"]
        query = str(detail["query"])
        unreferenced = 0
        for row in outcome.rows:
            identity = _event_identity(row)
            if identity is None:
                unreferenced += 1
                continue
            if not _entity_supported(entity, row):
                continue
            item = candidates.setdefault(
                identity, {"row": dict(row), "supports": {}, "time": identity[2]}
            )
            support = item["supports"].setdefault(
                seed["id"],
                {
                    "seed_id": seed["id"],
                    "seed_rank": seed["rank"],
                    "original_rank": seed["original_rank"],
                    "entities": {},
                    "weight": 1.0,
                },
            )
            support["entities"][str(entity["value"]).casefold()] = str(entity["value"])
            support["weight"] = min(support["weight"], float(entity.get("weight", 0.0) or 0.0))
            support["query"] = query
        coverage.append(
            {
                "seed_id": seed["id"],
                "query": query,
                "rows": len(outcome.rows),
                "reason": outcome.reason,
                "capped": len(outcome.rows) >= MAX_EVENTS_PER_QUERY,
                "unreferenced_events": unreferenced,
            }
        )
    return candidates, coverage


def _related_rows(
    index: str,
    candidates: Mapping[tuple[str, str, float, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    for identity, item in candidates.items():
        row = item["row"]
        supports = sorted(item["supports"].values(), key=lambda value: value["seed_rank"])
        raw = str(row["_raw"])
        query = str(supports[0]["query"])
        evidence = _event_ref(index, row, query)
        if evidence is None:
            continue
        shared = sorted({value for support in supports for value in support["entities"].values()})
        # Distinctive support: the identity's within-source share, weighted by seed rank.
        score = sum(
            float(support.get("weight", 0.0)) / (1.0 + int(support["seed_rank"]))
            for support in supports
        )
        anchor = supports[0]
        event_id = hashlib.sha256("|".join(map(str, identity)).encode()).hexdigest()[:16]
        relations = [
            {
                "seed_id": support["seed_id"],
                "seed_rank": support["seed_rank"],
                "shared_entities": sorted(support["entities"].values()),
                "query": support["query"],
            }
            for support in supports
        ]
        related.append(
            {
                "notable_id": f"relate-{event_id}",
                "generator": "relate",
                "basis": "identity_episode",
                "what": raw[:EVIDENCE_CHARS],
                "unjudged": True,
                "entities": [{"role": "related_entity", "value": value} for value in shared],
                "source_id": f"{index}:{row.get('sourcetype') or row.get('source') or ''}",
                "first_seen": item["time"],
                "last_seen": item["time"],
                "measure": {"name": "relation_support", "value": round(score, 8)},
                "relation_score": round(score, 8),
                "anchor_rank": int(anchor["original_rank"]),
                "relations": relations,
                "evidence": [
                    {
                        "line": evidence["line"],
                        "query": evidence["query"],
                        "earliest": evidence["earliest"],
                        "latest": evidence["latest"],
                        "event": evidence,
                    }
                ],
            }
        )
    return sorted(
        related, key=lambda row: (row["anchor_rank"], -row["relation_score"], row["notable_id"])
    )


def _root(parent: dict[str, str], node: str) -> str:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _union(parent: dict[str, str], left: str, right: str) -> None:
    a, b = _root(parent, left), _root(parent, right)
    if a != b:
        parent[max(a, b)] = min(a, b)


def relatable_index(index: str) -> None:
    """Relate runs on any index except the held-out proof indexes."""
    cleaned = index.strip()
    if not cleaned:
        raise ValueError(f"{SOURCES_FILE} needs an index")
    if cleaned.casefold() in PROOF_INDEXES:
        raise ValueError(f"{cleaned} is a proof index and is not hunted")


@dataclass(frozen=True)
class CaseUnit:
    """One piece of case evidence: an episode, a signal occurrence or a flow value."""

    unit_id: str
    kind: str  # episode | signal | flow
    key: str  # "<entity kind>:<value>" or the flow's own value
    value: str
    source_id: str
    host: str
    start: float
    end: float
    event_ids: tuple[str, ...] = ()
    lines: tuple[Mapping[str, Any], ...] = ()
    notable_id: str = ""
    generator: str = ""
    measure: float = 0.0
    share: float = 0.0
    endpoints: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    p_yes: float | None = None
    rank: int = 0


def _step_role(step: Mapping[str, Any], identity: Mapping[str, Mapping[str, Any]]) -> str:
    """The role a flow step's field plays at its source, from that card's own role plan.

    A directional role comes first: `from` then `to` is what makes a value a transition.
    """
    info = identity.get(str(step.get("source_id") or "")) or {}
    field = str(step.get("field") or "")
    planned = info.get("roles")
    roles: Mapping[str, Sequence[str]] = planned if isinstance(planned, Mapping) else {}
    for role in ("from", "to", "actor", "action", "object", "outcome"):
        if field and field in (roles.get(role) or ()):
            return role
    return ""


def _role_transition(left: str, right: str) -> bool:
    """A value held in a different role at each endpoint is a transition, not ambient data."""
    return bool(left) and bool(right) and left != right


def _pick_key(options: Mapping[str, set[str]]) -> str:
    """The entity key a value most broadly carries: most sources, then the lexicographic key."""
    if not options:
        return ""
    return min(options, key=lambda key: (-len(options[key]), key))


def _spine_units(
    out: Path,
) -> tuple[list[CaseUnit], dict[str, dict[str, set[str]]], dict[tuple[str, str], float]]:
    """Episode units from the spine, the entity keys each value carries, and each key's share."""
    if not (out / SPINE_FILE).is_file():
        return [], {}, {}
    con = duckdb.connect(str(out / SPINE_FILE), read_only=True)
    try:
        entities = con.execute(
            "SELECT entity_kind, value, source_id, events FROM entities"
        ).fetchall()
        episodes = con.execute(
            "SELECT episode_id, entity_kind, value, source_id, host, start_time, end_time,"
            " event_ids, events FROM episodes"
        ).fetchall()
    finally:
        con.close()
    totals: dict[str, float] = defaultdict(float)
    for source_id, info in (read_json(out / SPINE_RECEIPT).get("sources") or {}).items():
        if isinstance(info, Mapping):
            totals[str(source_id)] = float(info.get("events") or 0.0)
    seen: dict[tuple[str, str], float] = defaultdict(float)
    paths: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for kind, value, source_id, events in entities:
        key = f"{kind}:{str(value).casefold()}"
        seen[(key, str(source_id))] += float(events)
        paths[str(value).casefold()][key].add(str(source_id))
    for source_id, total in list(totals.items()):
        if not total:
            totals[source_id] = sum(
                events for (key, source), events in seen.items() if source == source_id
            )
    shares = {key: _share_of(seen, totals, key[0], key[1]) for key in seen}
    units = [
        CaseUnit(
            str(episode_id),
            "episode",
            f"{kind}:{str(value).casefold()}",
            str(value),
            str(source_id),
            str(host or ""),
            float(start),
            float(end),
            tuple(json.loads(str(event_ids or "[]"))),
            measure=float(events or 0),
            share=shares.get((f"{kind}:{str(value).casefold()}", str(source_id)), 0.0),
        )
        for episode_id, kind, value, source_id, host, start, end, event_ids, events in episodes
    ]
    return units, paths, shares


def _share_of(
    seen: Mapping[tuple[str, str], float], totals: Mapping[str, float], key: str, source_id: str
) -> float:
    """An entity's share of its source's events: the dominance measure relate already uses."""
    total = float(totals.get(source_id, 0.0))
    return float(seen.get((key, source_id), 0.0)) / total if total else 0.0


def _signal_span(row: Mapping[str, Any]) -> tuple[float, float] | None:
    """When the signal occurred: its evidence line, else the behaviour's own span."""
    for item in row.get("evidence") or ():
        if isinstance(item, Mapping) and _number(item.get("earliest")) is not None:
            low = float(_number(item.get("earliest")) or 0.0)
            return low, float(_number(item.get("latest")) or low)
    first, last = _number(row.get("first_seen")), _number(row.get("last_seen"))
    if first is None:
        return None
    return float(first), float(last if last is not None else first)


def _signal_units(
    rows: Sequence[Mapping[str, Any]],
    paths: Mapping[str, Mapping[str, set[str]]],
    shares: Mapping[tuple[str, str], float],
) -> list[CaseUnit]:
    """One unit per (signal, entity key) a notable carries, so union-find can key on entities."""
    units: list[CaseUnit] = []
    for rank, row in enumerate(rows):
        span = _signal_span(row)
        notable_id = str(row.get("notable_id") or "")
        if span is None or not notable_id:
            continue
        measure = row.get("measure")
        measure = measure if isinstance(measure, Mapping) else {}
        value_measure = float(_number(measure.get("value")) or 0.0)
        p_yes = row.get("p_yes")
        source_id = str(row.get("source_id") or "")
        for entity in row.get("entities") or ():
            if not isinstance(entity, Mapping):
                continue
            value = str(entity.get("value") or "")
            key = _pick_key(paths.get(value.casefold()) or {})
            if not key:
                continue
            units.append(
                CaseUnit(
                    f"{notable_id}#{key}",
                    "signal",
                    key,
                    value,
                    source_id,
                    "",
                    span[0],
                    span[1],
                    lines=tuple(
                        item for item in row.get("evidence") or () if isinstance(item, Mapping)
                    ),
                    notable_id=notable_id,
                    generator=str(row.get("generator") or ""),
                    measure=value_measure,
                    share=float(shares.get((key, source_id), 0.0)),
                    p_yes=None if p_yes is None else float(p_yes),
                    rank=rank,
                )
            )
    return units


def _class_values(raw: str) -> set[tuple[str, str]]:
    """The (class token, value) pairs one event contributes to a class set."""
    found: set[tuple[str, str]] = set()
    for match in _UNIT_PAIR.finditer(raw):
        value = match.group(1).strip("\"'")
        if _class_value_ok(value):
            found.add((SET_NOVELTY_FIELD, value))
    for token in _FILE_TOKEN.findall(raw):
        if "/" not in token and "\\" not in token:
            continue
        hit = classify("", token)
        if hit is not None and hit.kind == FILE and hit.class_token:
            found.add((hit.class_token, token))
    return found


def _class_value_ok(value: str) -> bool:
    return (
        len(value) >= 2
        and "*" not in value
        and "?" not in value
        and not any(char.isspace() for char in value)
    )


def _novelty_row(
    index: str, host: str, kind: str, value: str, rows: Sequence[tuple[Any, ...]]
) -> dict[str, Any]:
    """One class-set candidate: a rare value on a host where its class is routine."""
    ordered = sorted(rows)
    times = [float(row[0]) for row in ordered]
    identifier = hashlib.sha1(f"{host}|{kind}|{value}".encode()).hexdigest()[:16]
    return {
        "notable_id": f"set-novelty-{identifier}",
        "generator": "set_novelty",
        "basis": "class_set_novelty",
        "what": f"{kind} value {value!r} seen {len(ordered)} time(s) only on {host}",
        "why": f"a rare member of a {kind} class this host otherwise produces",
        "entities": [{"role": "object", "value": value}],
        "source_id": str(ordered[0][1]),
        "host": host,
        "first_seen": min(times),
        "last_seen": max(times),
        "event_ids": [event_id(str(row[1]), host, float(row[0]), str(row[3])) for row in ordered],
        "measure": {"name": "class_set_novelty", "value": len(ordered)},
        "relation_score": float(len(ordered)),
        "anchor_rank": 0,
        "unjudged": True,
        "evidence": [_novelty_evidence(index, row) for row in ordered[:3]],
    }


def _novelty_evidence(index: str, row: Sequence[Any]) -> dict[str, Any]:
    moment = float(row[0])
    query = str(row[2] or "") or f"search index={_search_literal(index)} | head 5"
    return {
        "line": str(row[3] or "")[:EVIDENCE_CHARS],
        "query": query,
        "earliest": moment - 1,
        "latest": moment + 1,
    }


def _novelty_rows(out: Path, index: str) -> list[dict[str, Any]]:
    """Set-novelty candidates from the run's own store: no search, no keyword list."""
    store = out / STORE_FILE
    if not store.is_file():
        return []
    con = duckdb.connect(str(store), read_only=True)
    try:
        events = con.execute("SELECT source_id, host, ts, raw, query FROM events").fetchall()
    finally:
        con.close()
    grouped: dict[tuple[str, str], dict[str, list[tuple[Any, ...]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    totals: dict[str, int] = defaultdict(int)
    hosts: dict[str, set[str]] = defaultdict(set)
    for source_id, host, ts, raw, query in events:
        place = str(host or "")
        for kind, value in _class_values(str(raw or "")):
            grouped[(place, kind)][value].append(
                (float(ts or 0.0), str(source_id), str(query or ""), str(raw or ""))
            )
            totals[value] += 1
            hosts[value].add(place)
    candidates: list[tuple[str, str, str, list[tuple[Any, ...]]]] = []
    for (place, kind), values in grouped.items():
        routine = kind == SET_NOVELTY_FIELD and len(values) >= SET_NOVELTY_MIN_CLASS_VALUES
        small = (
            kind != SET_NOVELTY_FIELD
            and sum(len(rows) for rows in values.values()) <= SET_NOVELTY_CLASS_EVENTS
        )
        if not (routine or small):
            continue
        for value, rows in values.items():
            if totals[value] > SET_NOVELTY_MAX_EVENTS or len(hosts[value]) != 1:
                continue
            candidates.append((place, kind, value, rows))
    candidates.sort(
        key=lambda item: (0 if item[1] == SET_NOVELTY_FIELD else 1, item[0], item[1], item[2])
    )
    return [
        _novelty_row(index, place, kind, value, rows)
        for place, kind, value, rows in candidates[:SET_NOVELTY_MAX_ROWS]
    ]


def _novelty_units(rows: Sequence[Mapping[str, Any]]) -> list[CaseUnit]:
    """A set-novelty candidate is a signal unit so a two-event episode can hold a case."""
    units: list[CaseUnit] = []
    for rank, row in enumerate(rows):
        measure = row.get("measure")
        measure = measure if isinstance(measure, Mapping) else {}
        entities = [item for item in row.get("entities") or () if isinstance(item, Mapping)]
        if not entities:
            continue
        units.append(
            CaseUnit(
                str(row.get("notable_id") or ""),
                "signal",
                f"class:{row.get('basis')}",
                str(entities[0].get("value") or ""),
                str(row.get("source_id") or ""),
                str(row.get("host") or ""),
                float(_number(row.get("first_seen")) or 0.0),
                float(_number(row.get("last_seen")) or 0.0),
                event_ids=tuple(str(item) for item in row.get("event_ids") or ()),
                lines=tuple(
                    item for item in row.get("evidence") or () if isinstance(item, Mapping)
                ),
                notable_id=str(row.get("notable_id") or ""),
                generator=str(row.get("generator") or ""),
                measure=float(_number(measure.get("value")) or 0.0),
                rank=rank,
            )
        )
    return units


def _link_novelty(
    parent: dict[str, str], units: Sequence[CaseUnit], counters: dict[str, int]
) -> None:
    """A class-set signal links only the episode that carries its own evidence events."""
    by_event: dict[str, str] = {}
    for unit in units:
        if unit.kind == "episode":
            for identifier in unit.event_ids:
                by_event.setdefault(identifier, unit.unit_id)
    for novelty in (unit for unit in units if unit.generator == "set_novelty"):
        for identifier in novelty.event_ids:
            unit_id = by_event.get(identifier)
            if unit_id is None or unit_id == novelty.unit_id:
                continue
            if _root(parent, unit_id) == _root(parent, novelty.unit_id):
                continue
            _union(parent, novelty.unit_id, unit_id)
            counters["links"] += 1


def _flow_units(
    flows: Sequence[Mapping[str, Any]],
    identity: Mapping[str, Mapping[str, Any]],
    paths: Mapping[str, Mapping[str, set[str]]],
) -> tuple[list[CaseUnit], int]:
    """A flow is a value whose endpoint roles differ and one endpoint can decide the step."""
    units: list[CaseUnit] = []
    skipped = 0
    for flow in flows:
        steps = [step for step in flow.get("steps") or () if isinstance(step, Mapping)]
        roles = (_step_role(steps[0], identity), _step_role(steps[-1], identity)) if steps else ()
        key = _pick_key(paths.get(str(flow.get("value") or "").casefold()) or {})
        times = [_number(step.get("first_seen")) for step in steps] + [
            _number(step.get("last_seen")) for step in steps
        ]
        present = [float(item) for item in times if item is not None]
        if (
            len(steps) < 2
            or not key
            or not _role_transition(*roles)
            or not _DECIDING_ROLES.intersection(roles)
            or not present
        ):
            skipped += 1
            continue
        endpoints = tuple(str(step.get("source_id") or "") for step in steps)
        units.append(
            CaseUnit(
                f"flow-{hashlib.sha1(str(flow.get('value')).encode()).hexdigest()[:16]}",
                "flow",
                key,
                str(flow.get("value") or ""),
                "",
                "",
                min(present),
                max(present),
                measure=float(len(steps)),
                endpoints=endpoints,
                roles=tuple(roles),
            )
        )
    return units, skipped


def _link_chain(
    parent: dict[str, str], group: Sequence[CaseUnit], counters: dict[str, int]
) -> None:
    """Chain one value's units: consecutive spans within the gap, the case capped at a day."""
    ordered = sorted((unit for unit in group if unit.kind != "flow"), key=_unit_order)
    if len(ordered) < 2:
        return
    chain_start = ordered[0].start
    for before, after in zip(ordered, ordered[1:], strict=False):
        if after.start - before.end > CASE_LINK_GAP_SECONDS:
            counters["gap"] += 1
            chain_start = after.start
            continue
        if max(after.end, before.end) - min(after.start, chain_start) > CASE_MAX_SPAN_SECONDS:
            counters["window"] += 1
            chain_start = after.start
            continue
        _union(parent, before.unit_id, after.unit_id)
        counters["links"] += 1


def _link_flows(
    parent: dict[str, str], group: Sequence[CaseUnit], counters: dict[str, int]
) -> None:
    """A flow unions the episodes at its own endpoint sources inside the case window."""
    episodes = [unit for unit in group if unit.kind != "flow"]
    for flow in (unit for unit in group if unit.kind == "flow"):
        for unit in episodes:
            if unit.source_id not in flow.endpoints:
                continue
            if unit.start - flow.end > CASE_LINK_GAP_SECONDS:
                continue
            if flow.start - unit.end > CASE_LINK_GAP_SECONDS:
                continue
            if max(flow.end, unit.end) - min(flow.start, unit.start) > CASE_MAX_SPAN_SECONDS:
                counters["window"] += 1
                continue
            _union(parent, flow.unit_id, unit.unit_id)
            counters["links"] += 1


def _unit_order(unit: CaseUnit) -> tuple[float, float, str]:
    return (unit.start, unit.end, unit.unit_id)


def _case_groups(units: Sequence[CaseUnit]) -> tuple[list[list[CaseUnit]], dict[str, int]]:
    """Union-find the units: shared entities chain, and a flow links its endpoint episodes."""
    parent = {unit.unit_id: unit.unit_id for unit in units}
    counters = {"links": 0, "gap": 0, "window": 0}
    by_key: dict[str, list[CaseUnit]] = defaultdict(list)
    for unit in units:
        by_key[unit.key].append(unit)
    for group in by_key.values():
        _link_chain(parent, group, counters)
        _link_flows(parent, group, counters)
    _link_novelty(parent, units, counters)
    components: dict[str, list[CaseUnit]] = defaultdict(list)
    for unit in units:
        components[_root(parent, unit.unit_id)].append(unit)
    return [components[node] for node in sorted(components)], counters


def _case_score(
    members: Sequence[CaseUnit], sources: int, generators: int, anchor: CaseUnit
) -> float:
    """The plan's five terms: sources, signals, anchor, distinctiveness, coherence."""
    w1, w2, w3, w4, w5 = CASE_WEIGHTS
    span = max(unit.end for unit in members) - min(unit.start for unit in members)
    hosts = len({unit.host for unit in members if unit.host})
    strength = 1.0 / (1.0 + anchor.rank) if anchor.kind == "signal" else min(1.0, anchor.share)
    share = max((unit.share for unit in members), default=0.0)
    coherence = 1.0 / (1.0 + span / 3600.0) / (1.0 + max(0, hosts - 1))
    return round(w1 * sources + w2 * generators + w3 * strength + w4 * share + w5 * coherence, 8)


def _case_evidence(
    members: Sequence[CaseUnit], events: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Reproducible evidence rows, round-robin across members: breadth before depth."""
    rows: list[dict[str, Any]] = []
    queues = [list(unit.event_ids) for unit in members]
    depth = 0
    while len(rows) < CASE_EVIDENCE_ROWS and any(depth < len(queue) for queue in queues):
        for queue in queues:
            if depth >= len(queue):
                continue
            stored = events.get(queue[depth])
            if stored is not None:
                rows.append(
                    {
                        key: value
                        for key, value in {**stored, "event_id": queue[depth]}.items()
                        if key != "query"
                    }
                )
            if len(rows) >= CASE_EVIDENCE_ROWS:
                return rows
        depth += 1
    for unit in members:
        for item in unit.lines:
            rows.append(
                {
                    "line": item.get("line"),
                    "query": item.get("query"),
                    "earliest": item.get("earliest"),
                    "latest": item.get("latest"),
                    "host": "",
                    "source": "",
                }
            )
            if len(rows) >= CASE_EVIDENCE_ROWS:
                return rows
    return rows


def _case_member(unit: CaseUnit) -> dict[str, Any]:
    return {
        "type": unit.kind,
        "id": unit.unit_id,
        "value": unit.value,
        "source_id": unit.source_id,
        "host": unit.host,
        "start": round(unit.start, 3),
        "end": round(unit.end, 3),
        "measure": unit.measure,
        "notable_id": unit.notable_id,
        "generator": unit.generator,
        "unjudged": unit.kind == "signal" and unit.p_yes is None,
    }


def _case_from_members(
    members: Sequence[CaseUnit],
    events: Mapping[str, Mapping[str, Any]],
    related_ids: Collection[str],
) -> dict[str, Any] | None:
    """A case needs two independent pieces of evidence; one signal is only a notable."""
    sources = sorted({unit.source_id for unit in members if unit.source_id})
    signals = sorted({unit.notable_id for unit in members if unit.notable_id})
    generators = len(
        {unit.generator for unit in members if unit.kind == "signal" and unit.generator}
    )
    flows = [unit for unit in members if unit.kind == "flow"]
    novelties = [unit for unit in members if unit.generator == "set_novelty"]
    if not (
        len(sources) >= 2 or len(signals) >= 2 or (sources and flows) or (sources and novelties)
    ):
        return None
    anchor = max(members, key=lambda unit: (unit.share, unit.measure, -unit.start, unit.unit_id))
    ranked = [
        anchor,
        *sorted(
            (unit for unit in members if unit is not anchor),
            key=lambda unit: (-unit.measure, unit.source_id, *_unit_order(unit)),
        ),
    ]
    evidence = _case_evidence(ranked, events)
    if not evidence:
        return None
    start = min(unit.start for unit in members)
    end = max(unit.end for unit in members)
    identifiers = sorted(unit.unit_id for unit in members)
    return {
        "case_id": hashlib.sha1("|".join(identifiers).encode()).hexdigest()[:16],
        "anchor_entity": anchor.value,
        "anchor_episode": anchor.unit_id if anchor.kind == "episode" else "",
        "score": _case_score(members, len(sources), generators, anchor),
        "pieces": len(sources) + len(signals) + len(flows),
        "seed_notables": [name for name in signals if name not in related_ids],
        "related_notables": [name for name in signals if name in related_ids],
        "members": [{**_case_member(unit), "rank": rank} for rank, unit in enumerate(ranked)],
        "entities": sorted({unit.key for unit in members if unit.kind != "flow"}),
        "sources": sources,
        "start": start,
        "end": end,
        "timeline": [
            {"type": unit.kind, "value": unit.value, "start": unit.start, "end": unit.end}
            for unit in sorted(members, key=_unit_order)
        ],
        "links": [
            {"entity": unit.key, "value": unit.value, "source_id": unit.source_id}
            for unit in ranked
            if unit.kind == "episode"
        ],
        "evidence": evidence,
        "transitions": [
            {
                "value": unit.value,
                "ingress": unit.endpoints[0] if unit.endpoints else "",
                "later": unit.endpoints[-1] if unit.endpoints else "",
                "roles": list(unit.roles),
                "steps": [],
            }
            for unit in flows
        ],
        "unjudged": any(unit.kind == "signal" and unit.p_yes is None for unit in members),
        "set_novelty": len(novelties),
        "why": f"{len(sources)} sources, {len(signals)} signals, {len(flows)} flow links",
    }


def _inventory_coverage(document: Mapping[str, Any]) -> dict[str, Any]:
    """How much of the value-list enumeration completed, from the inventory's own statuses."""
    rows = [item for item in document.get("fields") or () if isinstance(item, Mapping)]
    lists = [item for item in rows if not item.get("parse_only")]
    complete = sum(1 for item in lists if item.get("status") == "complete")
    return {
        "lists": len(lists),
        "parse_only": len(rows) - len(lists),
        "complete": complete,
        "capped": sum(1 for item in lists if item.get("status") == "capped"),
        "unavailable": sum(1 for item in lists if str(item.get("status") or "").startswith("un")),
        "uncapped_fraction": round(complete / len(lists), 6) if lists else None,
    }


def _judged(rows: Sequence[Mapping[str, Any]], judged_only: bool) -> list[Mapping[str, Any]]:
    """A judged-only view holds rows the judge scored; an unjudged row is never admitted."""
    return [row for row in rows if not judged_only or row.get("p_yes") is not None]


def build_cases(
    out: Path, related: Sequence[Mapping[str, Any]] = (), judged_only: bool = False
) -> dict[str, Any]:
    """Assemble cases over the spine and write cases.json beside the run."""
    began = time.monotonic()
    units, paths, shares = _spine_units(out)
    identity = _identity_fields(out)
    rows = _judged(read_notables(out / NOTABLES_FILE), judged_only)
    related = _judged(related, judged_only)
    index = str(read_json(out / SOURCES_FILE).get("index") or "")
    novelties = [] if judged_only else _novelty_rows(out, index)
    related = [*related, *novelties]
    units.extend(_signal_units([*rows, *related], paths, shares))
    units.extend(_novelty_units(novelties))
    inventory = load_inventory(out / INVENTORY_FILE)
    flows = [item for item in inventory.get("flows") or () if isinstance(item, Mapping)]
    flow_units, flows_skipped = _flow_units(flows, identity, paths)
    units.extend(flow_units)
    groups, counters = _case_groups(units)
    related_ids = {str(row.get("notable_id") or "") for row in related}
    events = _event_rows(out, identity)
    cases = []
    for group in groups:
        case = _case_from_members(group, events, related_ids)
        if case is not None:
            cases.append(case)
    cases.sort(key=lambda case: (-case["score"], case["start"], case["case_id"]))
    for rank, case in enumerate(cases):
        case["rank"] = rank
    attempted = counters["links"] + counters["gap"] + counters["window"]
    receipt = {
        "units": len(units),
        "episodes": sum(1 for unit in units if unit.kind == "episode"),
        "signals": sum(1 for unit in units if unit.kind == "signal"),
        "flows": len(flow_units),
        "flows_skipped": flows_skipped,
        "set_novelty": len(novelties),
        "cases": len(cases),
        "links": counters["links"],
        "censored": {
            "gap": counters["gap"],
            "window": counters["window"],
            "flow_roles": flows_skipped,
        },
        "uncapped_fraction": round(counters["links"] / attempted, 6) if attempted else None,
        "coverage_complete": not counters["gap"] and not counters["window"],
        "evidence_violations": sum(
            1 for case in cases if int(case.get("pieces") or 0) < CASE_MIN_EVIDENCE
        ),
        "lists": _inventory_coverage(inventory),
        "window_seconds": CASE_MAX_SPAN_SECONDS,
        "link_gap_seconds": CASE_LINK_GAP_SECONDS,
        "weights": list(CASE_WEIGHTS),
        "seconds": round(time.monotonic() - began, 3),
    }
    # compact, not write_json: a run's case payload is large and only machines read it
    (out / CASES_FILE).write_text(json.dumps({"receipt": receipt, "cases": cases}))
    return {
        "receipt": receipt,
        "cases": cases,
        "flows": flows,
        "novelties": novelties,
        "related": related,
    }


def _event_rows(out: Path, identity: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every stored event the spine can name, keyed by the spine's content hash."""
    from .spine import event_id

    if not (out / STORE_FILE).is_file():
        return {}
    con = duckdb.connect(str(out / STORE_FILE), read_only=True)
    try:
        rows = con.execute("SELECT source_id, host, ts, raw, query FROM events").fetchall()
    finally:
        con.close()
    found: dict[str, dict[str, Any]] = {}
    for source_id, host, ts, raw, query in rows:
        text = str(raw or "")
        moment = float(ts or 0.0)
        identifier = event_id(str(source_id), str(host or ""), moment, text)
        named = _SOURCE_IN_QUERY.search(str(query or ""))
        sources = (identity.get(str(source_id)) or {}).get("sources") or [""]
        found[identifier] = {
            "host": str(host or ""),
            "source": named.group(1) if named else str(sources[0]),
            "sourcetype": str(source_id).partition(":")[2],
            "time": moment,
            "raw_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "line": text[:EVIDENCE_CHARS],
            "query": str(query or ""),
            "earliest": moment - 1,
            "latest": moment + 1,
        }
    return found


def _row_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, row in enumerate(rows):
        notable_id = str(row.get("notable_id") or "")
        if notable_id and notable_id not in found:
            found[notable_id] = index
    return found


def _store_raws(out: Path) -> dict[str, tuple[str, ...]]:
    """Every stored raw line, keyed by source tail: the deterministic evidence check's input."""
    store = out / STORE_FILE
    if not store.is_file():
        return {}
    con = duckdb.connect(str(store), read_only=True)
    try:
        rows = con.execute("SELECT source_id, raw FROM events").fetchall()
    finally:
        con.close()
    found: dict[str, list[str]] = defaultdict(list)
    for source_id, raw in rows:
        found[str(source_id).rsplit(":", 1)[-1]].append(str(raw or "").casefold())
    return {name: tuple(lines) for name, lines in found.items()}


def _verified_row(row: Mapping[str, Any], raws: Mapping[str, Sequence[str]] | None) -> bool:
    """A member is lifted only when its evidence resolves and its carrier value is in that row."""
    if raws is None:
        return True
    source = str(row.get("source_id") or "").rsplit(":", 1)[-1]
    candidates = raws.get(source, ())
    values = [
        str(item.get("value") or "").casefold()
        for item in row.get("entities") or ()
        if isinstance(item, Mapping)
    ]
    values = [value for value in values if len(value) >= 2]
    for item in row.get("evidence") or ():
        line = str(item.get("line") or "").casefold() if isinstance(item, Mapping) else ""
        if len(line) < 8:
            continue
        head = line[:200]
        for raw in candidates:
            if raw.startswith(head) and any(value in raw for value in values):
                return True
    return False


def _weak_members(
    case: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    by_id: Mapping[str, int],
    related_by_id: Mapping[str, Mapping[str, Any]],
    raws: Mapping[str, Sequence[str]] | None = None,
) -> tuple[int, list[tuple[int, dict[str, Any]]]] | None:
    positions = [
        by_id[seed_id]
        for seed_id in (str(item) for item in case.get("seed_notables") or ())
        if seed_id in by_id
    ]
    if not positions or min(positions) >= PROMOTE_HEAD:
        return None
    anchor = min(positions)
    weak = [(position, dict(rows[position])) for position in positions if position >= PROMOTE_HEAD]
    for related_id in (str(item) for item in case.get("related_notables") or ()):
        if related_id in by_id and by_id[related_id] >= PROMOTE_HEAD:
            weak.append((by_id[related_id], dict(rows[by_id[related_id]])))
        elif related_id not in by_id and related_id in related_by_id:
            weak.append((len(rows) + 1, dict(related_by_id[related_id])))
    weak = [item for item in weak if _verified_row(item[1], raws)]
    weak.sort(key=lambda item: (item[0], str(item[1].get("notable_id") or "")))
    return anchor, weak[:PROMOTE_PER_CASE]


def _apply_lifts(
    rows: Sequence[Mapping[str, Any]],
    planned: Sequence[tuple[int, str, Sequence[tuple[int, dict[str, Any]]]]],
    by_id: Mapping[str, int],
    raws: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lifts: dict[int, list[dict[str, Any]]] = defaultdict(list)
    remove: set[int] = set()
    lifted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor, case_id, weak in sorted(planned):
        for _position, row in weak:
            notable_id = str(row.get("notable_id") or "")
            if len(lifted) >= PROMOTE_TOTAL or not notable_id or notable_id in seen:
                continue
            seen.add(notable_id)
            if notable_id in by_id:
                remove.add(by_id[notable_id])
            lifts[anchor].append(dict(row))
            lifted.append(
                {
                    "case_id": case_id,
                    "notable_id": notable_id,
                    "after_rank": anchor,
                    "unjudged": not _verified_row(row, raws),
                    "judged": not _unjudged(row),
                }
            )
    rebuilt: list[dict[str, Any]] = []
    for index, stored in enumerate(rows):
        if index in remove:
            continue
        rebuilt.append(dict(stored))
        rebuilt.extend(lifts.get(index, ()))
    return rebuilt, lifted


def promote_case_members(
    rows: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    *,
    judged_only: bool = False,
    raws: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A case already inside the head lifts only its verified members to sit after its anchor."""
    by_id = _row_index(rows)
    related_by_id = {
        str(row.get("notable_id") or ""): row for row in related if row.get("notable_id")
    }
    planned = [
        (anchor, str(case.get("case_id") or ""), weak)
        for case in cases
        if (picked := _weak_members(case, rows, by_id, related_by_id, raws)) is not None
        for anchor, weak in (picked,)
    ]
    if judged_only:
        kept = [
            (anchor, case_id, [(position, row) for position, row in weak if not _unjudged(row)])
            for anchor, case_id, weak in planned
        ]
        planned = [(anchor, case_id, weak) for anchor, case_id, weak in kept if weak]
    rebuilt, lifted = _apply_lifts(rows, planned, by_id, raws)
    return rebuilt, {
        "lifted": len(lifted),
        "judged_only": judged_only,
        "head": PROMOTE_HEAD,
        "per_case": PROMOTE_PER_CASE,
        "total": PROMOTE_TOTAL,
        "ids": lifted,
    }


def _unjudged(row: Mapping[str, Any]) -> bool:
    return row.get("p_yes") is None


def _write_notables(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows))


def relate_stage(*, out: Path, search: Search, judged_only: bool = False) -> dict[str, Any]:
    """Read identity neighbours over episode windows, score links by within-source share."""
    configure_ledger(search, out, "relate")
    sources = read_json(out / SOURCES_FILE)
    index = str(sources.get("index") or "")
    relatable_index(index)
    start, end = _number(sources.get("start")), _number(sources.get("end"))
    if start is None or end is None or end <= start:
        raise ValueError(f"{out / SOURCES_FILE} needs a valid start/end range")
    notables = [
        {**row, "unjudged": row.get("p_yes") is None} for row in read_notables(out / NOTABLES_FILE)
    ]
    selected = [row for row in notables if not judged_only or row.get("p_yes") is not None]
    identity = _identity_fields(out)
    shares, spans = _load_metrics(out / STORE_FILE)
    seeds = _seed_records(selected, start, end, identity, shares, spans)
    requests, details = _requests(index, seeds)
    executor = executor_for(search)
    executor.budget.restart_clock()  # behaviours owns the wall clock to here; relate starts its own
    executor.budget.phase = "investigating"
    began = time.monotonic()
    candidates, coverage = _gather(executor, requests, details)
    related = _related_rows(index, candidates)
    built = build_cases(out, related, judged_only)
    cases = built["cases"]
    novelties = built.get("novelties") or []
    related = built.get("related") or related
    promotable = [row for row in related if row.get("generator") != "set_novelty"]
    promoted, promotion = promote_case_members(
        selected, cases, promotable, judged_only=judged_only, raws=_store_raws(out)
    )
    promoted = [{**row, "unjudged": row.get("p_yes") is None} for row in promoted]
    _write_notables(out / NOTABLES_FILE, [*promoted, *novelties])
    snapshot = executor.budget.snapshot()
    receipt = {
        "index": index,
        "seeds": len(seeds),
        "notables_considered": len(selected),
        "unjudged_skipped": len(notables) - len(selected),
        "requests": len(requests),
        "related_events": len(related),
        "cases": len(cases),
        "set_novelty": len(novelties),
        "case_receipt": built["receipt"],
        "flows": len(built["flows"]),
        "promotion": promotion,
        "seconds": round(time.monotonic() - began, 3),
        "coverage_complete": bool(coverage)
        and not any(row["reason"] or row["unreferenced_events"] for row in coverage),
        "capped_queries": sum(1 for row in coverage if row["capped"]),
        "coverage": coverage,
        "executor": snapshot,
    }
    write_json(
        out / RELATE_FILE,
        {"receipt": receipt, "notables": related, "cases": cases, "flows": built["flows"]},
    )
    progress_update(out, "relate", receipt)
    return receipt


def main(argv: list[str] | None = None, *, search: Search | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="Stage 1 output directory")
    parser.add_argument(
        "--cases",
        action="store_true",
        help="assemble cases from the stored spine and inventory, with no searches",
    )
    args = parser.parse_args(argv)
    if args.cases:
        return _cases_main(args.out)
    try:
        receipt = relate_stage(
            out=args.out, search=search if search is not None else _default_search()
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"relate: {error}", file=sys.stderr)
        return 2
    print(
        f"relate: seeds={receipt['seeds']} requests={receipt['requests']} "
        f"related_events={receipt['related_events']} cases={receipt['cases']} "
        f"coverage_complete={receipt['coverage_complete']} wall={receipt['seconds']}s "
        f"-> {args.out / RELATE_FILE}"
    )
    return 0


def _cases_main(out: Path) -> int:
    """Offline case assembly: the stored run is the proof surface, no Splunk needed."""
    try:
        built = build_cases(out)
    except (FileNotFoundError, ValueError) as error:
        print(f"relate: {error}", file=sys.stderr)
        return 2
    receipt = built["receipt"]
    kept = [
        row for row in read_notables(out / NOTABLES_FILE) if row.get("generator") != "set_novelty"
    ]
    _write_notables(out / NOTABLES_FILE, [*kept, *(built.get("novelties") or ())])
    print(
        f"cases: units={receipt['units']} episodes={receipt['episodes']} "
        f"signals={receipt['signals']} flows={receipt['flows']} cases={receipt['cases']} "
        f"set_novelty={receipt['set_novelty']} links={receipt['links']} "
        f"censored={receipt['censored']} uncapped_fraction={receipt['uncapped_fraction']} "
        f"coverage_complete={receipt['coverage_complete']} "
        f"evidence_violations={receipt['evidence_violations']} wall={receipt['seconds']}s "
        f"-> {out / CASES_FILE}"
    )
    return 0


def _default_search() -> Search:
    from .run import default_search

    return default_search()


if __name__ == "__main__":
    sys.exit(main())
