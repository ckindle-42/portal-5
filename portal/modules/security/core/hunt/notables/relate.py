"""Pull distinctive-identity neighbours from Stage 1 notables and assemble episodes.

v2 (from docs/hunt/RELATE_LINKAGE_REPORT.md): pivot on the identity-field values a card
declares — the attacker's source IP for web sources, the user for auth/audit sources — not on
program names or cross-host-rare-but-actually-common values. Distinctiveness is the entity's
share of its own source's events (dominance), learned from the run's behaviour store, not a
host/source rarity table. The pivot window is the episode: the measured activity span of the
seed's identities, bounded by the run's own time range, never a fixed ±1 h. A case is one
episode of linked distinctive identities.
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
from pathlib import Path
from statistics import median
from typing import Any

import duckdb

from ..engine import Search, _literal_term_segments, _search_literal
from ..executor import executor_for
from .inventory import INVENTORY_FILE, load_inventory
from .knowledge import PROOF_INDEXES
from .receipt import progress_update, read_json, write_json
from .run import NOTABLES_FILE, SOURCES_FILE, STORE_FILE, configure_ledger, read_notables
from .sample import shared_source_names, source_route

RELATE_FILE = "relate.json"
MAX_SEEDS = 40  # effort budget: seed notables expanded into episodes
MAX_ENTITIES_PER_SEED = 5  # effort budget: identity pivots read from one notable
MAX_EVENTS_PER_QUERY = 20  # effort budget: neighbouring rows retained per identity query
EVIDENCE_CHARS = 400  # effort budget: event preview kept beside its reproducible reference
PROMOTE_HEAD = 50  # the scoreboard's smallest recall cut; a case already inside it is strong
PROMOTE_PER_CASE = 3  # effort budget: weak members one strong case may lift into the head
PROMOTE_TOTAL = 12  # effort budget: lifts across every strong case in the run
_PROGRAM_FIELD = "program"  # a template source keys its actor on the program, not an identity
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_CLF_TIME = re.compile(r"\[\d{1,2}/\w{3}/\d{4}:")  # an access-log timestamp is not an identity
# attack-signal generators rank ahead of the statistical ones when seeds are chosen
_SEED_GENERATOR_PRIORITY = {"similar_to_known": 0, "alerts": 1}


def _is_timestamp(value: str) -> bool:
    return bool(_CLF_TIME.search(value))


def _identity_fields(out: Path) -> dict[str, dict[str, Any]]:
    """Per source_id: the structure and which fields the behaviours stage keyed as identities.

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
                "objects": [],
                "sources": [],
                "sourcetype": str(card.get("sourcetype") or ""),
                "shared_sources": [],
            },
        )
        if actor_field:
            entry["actor_field"] = actor_field
        entry["objects"] = sorted(set(entry["objects"]) | set(objects))
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


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return max(float(left["start"]), float(right["start"])) < min(
        float(left["end"]), float(right["end"])
    )


def relatable_index(index: str) -> None:
    """Relate runs on any index except the held-out proof indexes."""
    cleaned = index.strip()
    if not cleaned:
        raise ValueError(f"{SOURCES_FILE} needs an index")
    if cleaned.casefold() in PROOF_INDEXES:
        raise ValueError(f"{cleaned} is a proof index and is not hunted")


def _union_flows(
    parent: dict[str, str], seeds: Sequence[Mapping[str, Any]], flow_values: Collection[str]
) -> None:
    """A stored cross-source value links seeds on different sources without a time overlap."""
    flows = {value.casefold() for value in flow_values if value}
    if not flows:
        return
    by_flow: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for seed in seeds:
        for entity in seed.get("entities") or ():
            if not isinstance(entity, Mapping):
                continue
            value = str(entity.get("value") or "").casefold()
            if value in flows:
                by_flow[value].append(seed)
    for matches in by_flow.values():
        for offset, left in enumerate(matches):
            for right in matches[offset + 1 :]:
                if str(left.get("source_id")) != str(right.get("source_id")):
                    _union(parent, str(left["id"]), str(right["id"]))


def _case_groups(
    seeds: Sequence[Mapping[str, Any]], flow_values: Collection[str] = ()
) -> list[list[str]]:
    """Union-find seeds into episodes: a shared identity anchor or a same-source user chain."""
    parent = {str(seed["id"]): str(seed["id"]) for seed in seeds}
    by_value: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for seed in seeds:
        has_user = False
        for entity in seed["entities"]:
            if entity.get("case_anchor"):
                by_value[(str(entity.get("kind")), str(entity["value"]).casefold())].append(seed)
            if entity.get("kind") == "user":
                has_user = True
        if has_user:
            by_source[str(seed["source_id"])].append(seed)
    for matches in (*by_value.values(), *by_source.values()):
        for offset, left in enumerate(matches):
            for right in matches[offset + 1 :]:
                if _overlap(left, right):
                    _union(parent, str(left["id"]), str(right["id"]))
    _union_flows(parent, seeds, flow_values)
    components: dict[str, list[str]] = defaultdict(list)
    for node in parent:
        components[_root(parent, node)].append(node)
    return sorted(sorted(nodes) for nodes in components.values() if len(nodes) > 1)


def _anchor_label(seed_ids: Sequence[str], by_seed: Mapping[str, Mapping[str, Any]]) -> str:
    values: list[str] = []
    for seed_id in seed_ids:
        for entity in by_seed[seed_id]["entities"]:
            if entity.get("case_anchor") and entity.get("kind") == "address":
                values.append(str(entity["value"]))
    return ",".join(sorted(set(values))) or str(by_seed[seed_ids[0]]["source_id"])


def _seed_generator(seed: Mapping[str, Any]) -> str:
    row = seed.get("row")
    return str(row.get("generator") or "") if isinstance(row, Mapping) else ""


def _seed_source_share(seed: Mapping[str, Any]) -> float:
    weights = [
        weight
        for entity in seed.get("entities") or ()
        if isinstance(entity, Mapping)
        and (weight := _number(entity.get("weight"))) is not None
        and weight > 0
    ]
    return max(weights, default=1.0)


def _case_order(
    case: Mapping[str, Any], generator_agreement: float, seed_agreement: float, source_share: float
) -> tuple[float, float, float, float, float, float, str]:
    """Prefer independent support, distinctive identities, and compact episodes."""
    return (
        -generator_agreement,
        -seed_agreement,
        source_share,
        float(case["end"]) - float(case["start"]),
        -float(case["score"]),
        float(case["start"]),
        str(case["case_id"]),
    )


def _transition(flow: Mapping[str, Any]) -> dict[str, Any]:
    steps = [step for step in flow.get("steps") or () if isinstance(step, Mapping)]
    return {
        "value": flow.get("value"),
        "ingress": flow.get("ingress") or (steps[0].get("source_id") if steps else ""),
        "later": flow.get("later") or (steps[-1].get("source_id") if steps else ""),
        "steps": steps,
    }


def _matching_flows(
    seed_ids: Sequence[str],
    by_seed: Mapping[str, Mapping[str, Any]],
    flows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    values: set[str] = set()
    for seed_id in seed_ids:
        for entity in by_seed[seed_id].get("entities") or ():
            if isinstance(entity, Mapping):
                values.add(str(entity.get("value") or "").casefold())
    return [
        _transition(flow)
        for flow in flows
        if str(flow.get("value") or "").casefold() in values and len(flow.get("steps") or ()) >= 2
    ]


def _flow_case(
    seed_ids: Sequence[str],
    by_seed: Mapping[str, Mapping[str, Any]],
    flows: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """A case whose only link is a stored cross-source value, with no pivot rows yet."""
    transitions = _matching_flows(seed_ids, by_seed, flows)
    if not transitions:
        return None
    seed_ids_out = sorted(str(by_seed[seed_id]["id"]) for seed_id in seed_ids)
    starts = [float(by_seed[seed_id]["start"]) for seed_id in seed_ids_out]
    ends = [float(by_seed[seed_id]["end"]) for seed_id in seed_ids_out]
    return {
        "case_id": hashlib.sha1("|".join(seed_ids_out).encode()).hexdigest()[:16],
        "anchor_entity": _anchor_label(seed_ids_out, by_seed),
        "score": 0.0,
        "seed_notables": seed_ids_out,
        "related_notables": [],
        "start": min(starts),
        "end": max(ends),
        "links": [],
        "evidence": [],
        "transitions": transitions,
    }


def _cases(
    seeds: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
    flows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    flow_values = [str(item.get("value") or "") for item in flows]
    groups = _case_groups(seeds, flow_values)
    by_seed = {str(seed["id"]): seed for seed in seeds}
    ordered_cases: list[
        tuple[tuple[float, float, float, float, float, float, str], dict[str, Any]]
    ] = []
    for seed_ids in groups:
        seed_set = set(seed_ids)
        events = [
            row for row in related if any(link["seed_id"] in seed_set for link in row["relations"])
        ]
        if not events:
            flow_case = _flow_case(seed_ids, by_seed, flows)
            if flow_case is not None:
                ordered_cases.append((_case_order(flow_case, 0.0, 0.0, 1.0), flow_case))
            continue
        links = [link for row in events for link in row["relations"] if link["seed_id"] in seed_set]
        evidence = [row["evidence"][0]["event"] for row in events]
        seed_ids_out = sorted(str(by_seed[seed_id]["id"]) for seed_id in seed_ids)
        score = round(sum(float(row["relation_score"]) for row in events), 8)
        all_ids = sorted([*seed_ids_out, *(str(row["notable_id"]) for row in events)])
        case_id = hashlib.sha1("|".join([*seed_ids_out, *all_ids]).encode()).hexdigest()[:16]
        case = {
            "case_id": case_id,
            "anchor_entity": _anchor_label(seed_ids_out, by_seed),
            "score": score,
            "seed_notables": seed_ids_out,
            "related_notables": [str(row["notable_id"]) for row in events],
            "start": min(float(event["time"]) for event in evidence),
            "end": max(float(event["time"]) for event in evidence),
            "links": links,
            "evidence": sorted(
                evidence, key=lambda event: (event["time"], event["host"], event["source"])
            ),
            "transitions": _matching_flows(seed_ids_out, by_seed, flows),
        }
        event_seed_counts: list[int] = []
        event_generator_counts: list[int] = []
        supported_seed_ids: set[str] = set()
        for event in events:
            supported = {
                str(link["seed_id"])
                for link in event["relations"]
                if str(link.get("seed_id")) in seed_set
            }
            supported_seed_ids.update(supported)
            event_seed_counts.append(len(supported))
            event_generators = {_seed_generator(by_seed[seed_id]) for seed_id in supported}
            event_generator_counts.append(len(event_generators - {""}))
        source_shares = [_seed_source_share(by_seed[seed_id]) for seed_id in supported_seed_ids]
        ordered_cases.append(
            (
                _case_order(
                    case,
                    float(median(event_generator_counts)),
                    float(median(event_seed_counts)),
                    max(source_shares, default=1.0),
                ),
                case,
            )
        )
    return [case for _, case in sorted(ordered_cases, key=lambda item: item[0])]


def _row_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, row in enumerate(rows):
        notable_id = str(row.get("notable_id") or "")
        if notable_id and notable_id not in found:
            found[notable_id] = index
    return found


def _weak_members(
    case: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    by_id: Mapping[str, int],
    related_by_id: Mapping[str, Mapping[str, Any]],
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
    weak.sort(key=lambda item: (item[0], str(item[1].get("notable_id") or "")))
    return anchor, weak[:PROMOTE_PER_CASE]


def _apply_lifts(
    rows: Sequence[Mapping[str, Any]],
    planned: Sequence[tuple[int, str, Sequence[tuple[int, dict[str, Any]]]]],
    by_id: Mapping[str, int],
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
            lifted.append({"case_id": case_id, "notable_id": notable_id, "after_rank": anchor})
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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A case already inside the head lifts its weak members to sit just after its anchor."""
    by_id = _row_index(rows)
    related_by_id = {
        str(row.get("notable_id") or ""): row for row in related if row.get("notable_id")
    }
    planned = [
        (anchor, str(case.get("case_id") or ""), weak)
        for case in cases
        if (picked := _weak_members(case, rows, by_id, related_by_id)) is not None
        for anchor, weak in (picked,)
    ]
    rebuilt, lifted = _apply_lifts(rows, planned, by_id)
    return rebuilt, {
        "lifted": len(lifted),
        "head": PROMOTE_HEAD,
        "per_case": PROMOTE_PER_CASE,
        "total": PROMOTE_TOTAL,
        "ids": lifted,
    }


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
    executor.budget.phase = "investigating"
    began = time.monotonic()
    candidates, coverage = _gather(executor, requests, details)
    related = _related_rows(index, candidates)
    inventory = load_inventory(out / INVENTORY_FILE)
    flows = [item for item in inventory.get("flows") or () if isinstance(item, Mapping)]
    cases = _cases(seeds, related, flows)
    promoted, promotion = promote_case_members(notables, cases, related)
    promoted = [{**row, "unjudged": row.get("p_yes") is None} for row in promoted]
    _write_notables(out / NOTABLES_FILE, promoted)
    snapshot = executor.budget.snapshot()
    receipt = {
        "index": index,
        "seeds": len(seeds),
        "notables_considered": len(selected),
        "unjudged_skipped": len(notables) - len(selected),
        "requests": len(requests),
        "related_events": len(related),
        "cases": len(cases),
        "flows": len(flows),
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
        {"receipt": receipt, "notables": related, "cases": cases, "flows": flows},
    )
    progress_update(out, "relate", receipt)
    return receipt


def main(argv: list[str] | None = None, *, search: Search | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="Stage 1 output directory")
    args = parser.parse_args(argv)
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


def _default_search() -> Search:
    from .run import default_search

    return default_search()


if __name__ == "__main__":
    sys.exit(main())
