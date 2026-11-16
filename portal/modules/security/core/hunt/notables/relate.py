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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb

from ..engine import Search, _literal_term_segments, _search_literal
from ..executor import executor_for
from .receipt import read_json, write_json
from .run import NOTABLES_FILE, SOURCES_FILE, STORE_FILE, read_notables

RELATE_FILE = "relate.json"
MAX_SEEDS = 40  # effort budget: highest-ranked Stage 1 notables to expand
MAX_ENTITIES_PER_SEED = 5  # effort budget: identity pivots read from one notable
MAX_EVENTS_PER_QUERY = 20  # effort budget: neighbouring rows retained per identity query
EVIDENCE_CHARS = 400  # effort budget: event preview kept beside its reproducible reference
TRAINING_INDEXES = frozenset({"hb_kyoushi_s1", "hb_ait_santos", "hb_ait_russellmitchell"})
_PROGRAM_FIELD = "program"  # a template source keys its actor on the program, not an identity
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_CLF_TIME = re.compile(r"\[\d{1,2}/\w{3}/\d{4}:")  # an access-log timestamp is not an identity


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
    return info


def _route(info: Mapping[str, Any]) -> str:
    """A source filter selecting this seed's own source, mirroring the behaviour-stage route."""
    sources = info.get("sources") or ()
    if sources:
        return "(" + " OR ".join(f"source={_search_literal(name)}" for name in sources) + ")"
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


def _seed_records(
    rows: Sequence[dict[str, Any]],
    start: float,
    end: float,
    identity: Mapping[str, Mapping[str, Any]],
    shares: Mapping[tuple[str, str], float],
    spans: Mapping[tuple[str, str], tuple[float, float]],
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for rank, row in enumerate(rows[:MAX_SEEDS]):
        source_id = str(row.get("source_id") or "")
        entities = _entities(row, identity, shares)
        if not entities:
            continue
        low, high = _episode_window(row, source_id, start, end, spans, entities)
        if high <= low:
            continue
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


def _case_groups(seeds: Sequence[Mapping[str, Any]]) -> list[list[str]]:
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


def _case_order(case: Mapping[str, Any]) -> tuple[float, float, float, str]:
    """Order by the best Stage 1 seed, then measured relation support."""
    ranks = [
        rank
        for link in case["links"]
        if isinstance(link, Mapping) and (rank := _number(link.get("seed_rank"))) is not None
    ]
    return (
        min(ranks, default=float("inf")),
        -float(case["score"]),
        float(case["start"]),
        str(case["case_id"]),
    )


def _cases(
    seeds: Sequence[Mapping[str, Any]], related: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    groups = _case_groups(seeds)
    by_seed = {str(seed["id"]): seed for seed in seeds}
    cases: list[dict[str, Any]] = []
    for seed_ids in groups:
        seed_set = set(seed_ids)
        events = [
            row for row in related if any(link["seed_id"] in seed_set for link in row["relations"])
        ]
        if not events:
            continue
        links = [link for row in events for link in row["relations"] if link["seed_id"] in seed_set]
        evidence = [row["evidence"][0]["event"] for row in events]
        seed_ids_out = sorted(str(by_seed[seed_id]["id"]) for seed_id in seed_ids)
        score = round(sum(float(row["relation_score"]) for row in events), 8)
        all_ids = sorted([*seed_ids_out, *(str(row["notable_id"]) for row in events)])
        case_id = hashlib.sha1("|".join([*seed_ids_out, *all_ids]).encode()).hexdigest()[:16]
        cases.append(
            {
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
            }
        )
    return sorted(cases, key=_case_order)


def relate_stage(*, out: Path, search: Search, judged_only: bool = False) -> dict[str, Any]:
    """Read identity neighbours over episode windows, score links by within-source share."""
    sources = read_json(out / SOURCES_FILE)
    index = str(sources.get("index") or "")
    if index not in TRAINING_INDEXES:
        raise ValueError(
            f"Stage 3 is restricted to training indexes: {', '.join(sorted(TRAINING_INDEXES))}"
        )
    start, end = _number(sources.get("start")), _number(sources.get("end"))
    if start is None or end is None or end <= start:
        raise ValueError(f"{out / SOURCES_FILE} needs a valid start/end range")
    notables = read_notables(out / NOTABLES_FILE)
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
    cases = _cases(seeds, related)
    snapshot = executor.budget.snapshot()
    receipt = {
        "index": index,
        "seeds": len(seeds),
        "notables_considered": len(selected),
        "unjudged_skipped": len(notables) - len(selected),
        "requests": len(requests),
        "related_events": len(related),
        "cases": len(cases),
        "seconds": round(time.monotonic() - began, 3),
        "coverage_complete": bool(coverage)
        and not any(
            row["reason"] or row["capped"] or row["unreferenced_events"] for row in coverage
        ),
        "capped_queries": sum(1 for row in coverage if row["capped"]),
        "coverage": coverage,
        "executor": snapshot,
    }
    write_json(out / RELATE_FILE, {"receipt": receipt, "notables": related, "cases": cases})
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
