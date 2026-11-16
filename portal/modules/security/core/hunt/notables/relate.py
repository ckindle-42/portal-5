"""Pull bounded event neighbours from Stage 1 notables and assemble evidence cases."""

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
MAX_ENTITIES_PER_SEED = 5  # effort budget: entity pivots read from one notable
MAX_EVENTS_PER_QUERY = 20  # effort budget: neighbouring rows retained per entity query
TIME_MARGIN_SECONDS = 3600  # effort budget: adjacency window on either side of a seed
EVIDENCE_CHARS = 400  # effort budget: event preview kept beside its reproducible reference
TRAINING_INDEXES = frozenset({"hb_kyoushi_s1", "hb_ait_santos", "hb_ait_russellmitchell"})
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


def _rarity_weight(hosts: int, sources: int) -> float:
    """1.0 for an entity seen on one host and source; shrinks as its spread grows."""
    if hosts <= 0 or sources <= 0:
        return 1.0
    return 1.0 / (hosts * sources)


def _load_rarity(store: Path) -> dict[str, tuple[int, int]]:
    """Entity value -> (distinct hosts, distinct sources) across the behaviour events table.

    Rarity is learned from the run's own behaviour store, not from a list: an entity that
    appears in many hosts' or sources' events is a shared pivot (a gateway, DNS, a common
    user) and is down-weighted; one that appears on a single host is attack-specific.
    """
    if not store.is_file():
        return {}
    con = duckdb.connect(str(store), read_only=True)
    try:
        rows = con.execute(
            "SELECT value, count(DISTINCT NULLIF(host, '')) AS hosts, "
            "count(DISTINCT source_id) AS sources "
            "FROM ("
            "SELECT actor AS value, host, source_id FROM events WHERE NULLIF(actor, '') IS NOT NULL "
            "UNION ALL "
            "SELECT action AS value, host, source_id FROM events WHERE NULLIF(action, '') IS NOT NULL "
            "UNION ALL "
            "SELECT object AS value, host, source_id FROM events WHERE NULLIF(object, '') IS NOT NULL"
            ") GROUP BY value"
        ).fetchall()
    finally:
        con.close()
    rarity = {str(value).casefold(): (int(hosts), int(sources)) for value, hosts, sources in rows}
    addresses = sorted({match for value in rarity for match in _IPV4.findall(value)})
    if not addresses:
        return rarity
    con = duckdb.connect(str(store), read_only=True)
    try:
        for address in addresses:
            row = con.execute(
                "SELECT count(DISTINCT NULLIF(host, '')), count(DISTINCT source_id) "
                "FROM events WHERE instr(actor, ?) > 0 OR instr(action, ?) > 0 "
                "OR instr(object, ?) > 0",
                [address, address, address],
            ).fetchone()
            if row is None:
                continue
            hosts, sources = row
            rarity[address.casefold()] = (int(hosts), int(sources))
    finally:
        con.close()
    return rarity


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


def _seed_window(row: Mapping[str, Any], start: float, end: float) -> tuple[float, float]:
    evidence = [item for item in row.get("evidence") or () if isinstance(item, Mapping)]
    lows: list[float] = []
    highs: list[float] = []
    for item in evidence:
        earliest, latest = _number(item.get("earliest")), _number(item.get("latest"))
        if earliest is not None:
            lows.append(earliest)
        if latest is not None:
            highs.append(latest)
    first, last = _number(row.get("first_seen")), _number(row.get("last_seen"))
    low = min(lows) if lows else (first if first is not None else start)
    high = max(highs) if highs else (last if last is not None else low)
    return max(start, low - TIME_MARGIN_SECONDS), min(end, max(high, low) + TIME_MARGIN_SECONDS)


def _entities(
    row: Mapping[str, Any], rarity: Mapping[str, tuple[int, int]] | None = None
) -> list[dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    spread = rarity or {}
    for item in row.get("entities") or ():
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip()
        value = str(item.get("value") or "").strip()
        if value:
            for match in _IPV4.finditer(value):
                try:
                    address = str(ipaddress.IPv4Address(match.group()))
                except ValueError:
                    continue
                found.setdefault(
                    ("address", address),
                    {
                        "role": "address",
                        "value": address,
                        "terms": (address,),
                        "case_anchor": True,
                        "weight": _rarity_weight(*spread.get(address.casefold(), (0, 0))),
                    },
                )
            if "*" not in value and "?" not in value:
                terms = _literal_term_segments(value)
                found.setdefault(
                    (role.casefold(), value.casefold()),
                    {
                        "role": role,
                        "value": value,
                        "terms": terms,
                        "case_anchor": False,
                        "weight": _rarity_weight(*spread.get(value.casefold(), (0, 0))),
                    },
                )
    return list(found.values())[:MAX_ENTITIES_PER_SEED]


def _query(index: str, entity: Mapping[str, Any]) -> str:
    terms = " ".join(f"TERM({_search_literal(term)})" for term in entity["terms"])
    options = ([f"({terms})"] if terms else []) + [f"(host={_search_literal(entity['value'])})"]
    return (
        f"search index={_search_literal(index)} ({' OR '.join(options)}) "
        f"| head {MAX_EVENTS_PER_QUERY}"
    )


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
    return (
        bool(re.search(rf"(?<!\w){re.escape(value)}(?!\w)", raw, re.IGNORECASE))
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


def _seed_records(
    rows: Sequence[dict[str, Any]],
    start: float,
    end: float,
    rarity: Mapping[str, tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    ordered = list(enumerate(rows[:MAX_SEEDS]))
    seeds: list[dict[str, Any]] = []
    for rank, (_original_rank, row) in enumerate(ordered):
        entities = _entities(row, rarity)
        if not entities:
            continue
        low, high = _seed_window(row, start, end)
        if high <= low:
            continue
        seeds.append(
            {
                "id": _seed_id(row, rank),
                "rank": rank,
                "original_rank": _original_rank,
                "row": row,
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
            query = _query(index, entity)
            requests.append((query, seed["start"], seed["end"], "relate", MAX_EVENTS_PER_QUERY))
            details.append({"seed": seed, "entity": entity, "query": query})
    return requests, details


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
                    "delta": None,
                },
            )
            support["entities"][str(entity["value"]).casefold()] = str(entity["value"])
            support["weight"] = min(support["weight"], float(entity.get("weight", 1.0)))
            delta = abs(identity[2] - float(seed["center"]))
            support["delta"] = delta if support["delta"] is None else min(support["delta"], delta)
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
        score = sum(
            float(support.get("weight", 1.0))
            * (1.0 / (int(support["seed_rank"]) + 1))
            / (1.0 + float(support["delta"] or 0.0) / TIME_MARGIN_SECONDS)
            for support in supports
        )
        anchor = supports[0]
        event_id = hashlib.sha256("|".join(map(str, identity)).encode()).hexdigest()[:16]
        relations = [
            {
                "seed_id": support["seed_id"],
                "seed_rank": support["seed_rank"],
                "shared_entities": sorted(support["entities"].values()),
                "time_delta_seconds": round(float(support["delta"] or 0.0), 3),
                "query": support["query"],
            }
            for support in supports
        ]
        related.append(
            {
                "notable_id": f"relate-{event_id}",
                "generator": "relate",
                "basis": "entity_time_adjacency",
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


def _case_groups(seeds: Sequence[Mapping[str, Any]]) -> list[tuple[str, list[str]]]:
    by_entity: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for seed in seeds:
        for entity in seed["entities"]:
            if entity.get("case_anchor"):
                by_entity[str(entity["value"]).casefold()].append(seed)
    groups: list[tuple[str, list[str]]] = []
    for entity, matches in by_entity.items():
        parent = {str(seed["id"]): str(seed["id"]) for seed in matches}
        for offset, left in enumerate(matches):
            for right in matches[offset + 1 :]:
                gap = max(
                    0.0,
                    max(float(left["start"]), float(right["start"]))
                    - min(float(left["end"]), float(right["end"])),
                )
                if gap <= TIME_MARGIN_SECONDS:
                    _union(parent, str(left["id"]), str(right["id"]))
        components: dict[str, list[str]] = defaultdict(list)
        for node in parent:
            components[_root(parent, node)].append(node)
        groups.extend((entity, sorted(nodes)) for nodes in components.values() if len(nodes) > 1)
    return sorted(groups)


def _cases(
    seeds: Sequence[Mapping[str, Any]], related: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    groups = _case_groups(seeds)
    by_seed = {str(seed["id"]): seed for seed in seeds}
    cases: list[dict[str, Any]] = []
    for anchor_entity, seed_ids in groups:
        seed_set = set(seed_ids)
        events = [
            row
            for row in related
            if any(
                link["seed_id"] in seed_set
                and anchor_entity in {str(value).casefold() for value in link["shared_entities"]}
                for link in row["relations"]
            )
        ]
        if not events:
            continue
        links = [
            link
            for row in events
            for link in row["relations"]
            if link["seed_id"] in seed_set
            and anchor_entity in {str(value).casefold() for value in link["shared_entities"]}
        ]
        evidence = [row["evidence"][0]["event"] for row in events]
        seed_ids_out = sorted(str(by_seed[seed_id]["id"]) for seed_id in seed_ids)
        score = round(sum(float(row["relation_score"]) for row in events), 8)
        all_ids = sorted([*seed_ids_out, *(str(row["notable_id"]) for row in events)])
        case_id = hashlib.sha1("|".join([anchor_entity, *all_ids]).encode()).hexdigest()[:16]
        cases.append(
            {
                "case_id": case_id,
                "anchor_entity": anchor_entity,
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
    return sorted(cases, key=lambda case: (-case["score"], case["start"], case["case_id"]))


def relate_stage(*, out: Path, search: Search, judged_only: bool = False) -> dict[str, Any]:
    """Read bounded entity neighbours, score links from seed rank, and save cases."""
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
    rarity = _load_rarity(out / STORE_FILE)
    seeds = _seed_records(selected, start, end, rarity)
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
