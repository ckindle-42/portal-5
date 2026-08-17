"""Asset, identity, and peer context derived from live source APIs."""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from .connectors import QUERY_IN_PLACE_MODE, NativeQuery, QueryIntent, QueryResult, SourceConnector
from .data_plane import DataPlane, SourceProfile


def _fields(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("fields")
    return {**record, **(nested if isinstance(nested, dict) else {})}


def _entity(record: Any) -> tuple[str | None, str | None]:
    fields = _fields(record)
    actor = next(
        (
            fields.get(key)
            for key in ("actor", "user", "username", "userName", "principal", "account")
            if fields.get(key)
        ),
        None,
    )
    asset = next(
        (
            fields.get(key)
            for key in ("asset", "host", "hostname", "device", "ComputerName", "dest")
            if fields.get(key)
        ),
        None,
    )
    return (str(actor) if actor is not None else None, str(asset) if asset is not None else None)


class AssetIdentityConnector:
    """Join indexed activity to optional AD/Proxmox inventory on read."""

    source_id = "asset-identity-context"
    mode = QUERY_IN_PLACE_MODE
    language = "source-join"

    def __init__(
        self,
        indexed: SourceConnector,
        *,
        inventory_provider: Callable[[], Iterable[Any]] | None = None,
    ) -> None:
        self.indexed = indexed
        self.inventory_provider = inventory_provider or (lambda: ())

    def translate(self, intent: QueryIntent) -> NativeQuery:
        return NativeQuery(
            self.source_id,
            self.language,
            {
                "indexed_source": self.indexed.source_id,
                "inventory": "provider",
                "entities": list(intent.entities),
                "limit": intent.limit,
            },
            intent,
        )

    def _records(self, intent: QueryIntent) -> list[dict[str, Any]]:
        indexed = self.indexed.read(
            QueryIntent(
                "derive indexed asset and identity context",
                seed=dict(intent.seed),
                start=intent.start,
                end=intent.end,
                entities=intent.entities,
                limit=intent.limit,
            )
        )
        records: list[dict[str, Any]] = []
        actor_counts: Counter[str] = Counter()
        asset_counts: Counter[str] = Counter()
        activity_by_actor: defaultdict[str, set[str]] = defaultdict(set)
        for original in indexed.records:
            actor, asset = _entity(original)
            if actor:
                actor_counts[actor] += 1
                fields = _fields(original)
                action = fields.get("action") or fields.get("eventName") or fields.get("event")
                if action:
                    activity_by_actor[actor].add(str(action))
            if asset:
                asset_counts[asset] += 1
            if not actor and not asset:
                continue
            records.append(
                {
                    "record_class": "indexed_entity_context",
                    "entity_id": actor or asset,
                    "actor": actor,
                    "asset": asset,
                    "context_topology": {"source": self.indexed.source_id, "indexed": True},
                    "provenance": {
                        "source_id": self.indexed.source_id,
                        "native_query": indexed.native_query.expression,
                    },
                    "observed_at": _fields(original).get("_time") or time.time(),
                }
            )

        for item in self.inventory_provider():
            if not isinstance(item, dict):
                continue
            actor, asset = _entity(item)
            entity_id = actor or asset or item.get("name") or item.get("vmid")
            if entity_id is None:
                continue
            records.append(
                {
                    "record_class": "inventory_context",
                    "entity_id": str(entity_id),
                    "actor": actor,
                    "asset": asset or str(item.get("name") or entity_id),
                    "context_topology": {
                        "source": item.get("source") or "lab-inventory",
                        "domain": item.get("domain"),
                        "node": item.get("node"),
                    },
                    "provenance": {
                        "source_id": item.get("source") or "lab-inventory",
                        "inventory_record_id": item.get("id") or item.get("vmid") or str(entity_id),
                    },
                    "inventory": item,
                    "observed_at": item.get("observed_at") or time.time(),
                }
            )

        for actor, count in sorted(actor_counts.items()):
            records.append(
                {
                    "record_class": "peer_baseline",
                    "entity_id": actor,
                    "actor": actor,
                    "peer_count": count,
                    "peer_actions": sorted(activity_by_actor[actor]),
                    "context_topology": {
                        "source": self.indexed.source_id,
                        "baseline": "observed-indexed",
                    },
                    "provenance": {
                        "source_id": self.indexed.source_id,
                        "baseline": "indexed-activity",
                    },
                    "observed_at": time.time(),
                }
            )
        for asset, count in sorted(asset_counts.items()):
            if asset in actor_counts:
                continue
            records.append(
                {
                    "record_class": "asset_baseline",
                    "entity_id": asset,
                    "asset": asset,
                    "peer_count": count,
                    "context_topology": {
                        "source": self.indexed.source_id,
                        "baseline": "observed-indexed",
                    },
                    "provenance": {
                        "source_id": self.indexed.source_id,
                        "baseline": "indexed-activity",
                    },
                    "observed_at": time.time(),
                }
            )
        return records

    def read(self, intent: QueryIntent) -> QueryResult:
        started = time.time()
        records = self._records(intent)
        requested = {str(entity).lower() for entity in intent.entities}
        if requested:
            records = [
                record
                for record in records
                if str(record.get("entity_id", "")).lower() in requested
                or any(
                    str(value).lower() in requested
                    for value in (record.get("actor"), record.get("asset"))
                )
            ]
        truncated = intent.limit is not None and len(records) >= intent.limit
        if intent.limit is not None:
            records = records[: intent.limit]
        return QueryResult(
            self.source_id,
            self.mode,
            self.translate(intent),
            tuple(records),
            started,
            time.time(),
            truncated=truncated,
            metadata={
                "indexed_source": self.indexed.source_id,
                "inventory_joined": any(
                    record["record_class"] == "inventory_context" for record in records
                ),
                "peer_baseline": any(
                    record["record_class"] == "peer_baseline" for record in records
                ),
            },
        )


def register_asset_identity_source(
    plane: DataPlane,
    indexed: SourceConnector,
    *,
    inventory_provider: Callable[[], Iterable[Any]] | None = None,
    sample_limit: int = 128,
    source_id: str = "asset-identity-context",
) -> SourceProfile:
    connector = AssetIdentityConnector(indexed, inventory_provider=inventory_provider)
    connector.source_id = source_id
    sample = connector.read(QueryIntent("profile asset and identity context", limit=sample_limit))
    return plane.connect(
        source_id,
        connector,
        sample.records,
        source_meta={
            "record_class": "asset_identity_context",
            "capabilities": {
                "entity_identity": True,
                "cross_source_entity": inventory_provider is not None,
                "shared_timeline": True,
                "semantic_text": True,
            },
            "freshness_at": sample.finished_at,
        },
    )


def context_answer(
    plane: DataPlane,
    *,
    entity_id: str,
    source_id: str = "asset-identity-context",
) -> dict[str, Any]:
    connector = plane.connectors.get(source_id)
    if connector is None:
        return {
            "entity_id": entity_id,
            "available": False,
            "finding": "asset/identity context unavailable",
        }
    result = connector.read(
        QueryIntent("answer asset and identity context", entities=(entity_id,), limit=128)
    )
    if result.records:
        return {"entity_id": entity_id, "available": True, "records": list(result.records)}
    return {
        "entity_id": entity_id,
        "available": False,
        "finding": "asset/identity context unavailable for entity",
    }
