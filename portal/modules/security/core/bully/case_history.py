"""Store-backed case history for investigation recall and provenance."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from typing import Any

from . import events
from .connectors import QUERY_IN_PLACE_MODE, NativeQuery, QueryIntent, QueryResult
from .data_plane import DataPlane, SourceProfile
from .store import Store

_TOKEN = re.compile(r"[a-z0-9_:-]+", re.IGNORECASE)


def _tokens(value: Any) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(str(value)) if len(token) > 2}


class StoreCaseHistoryConnector:
    """Query the durable Store without copying it into the data plane."""

    source_id = "case-history"
    mode = QUERY_IN_PLACE_MODE
    language = "Store API"

    def __init__(self, store: Store) -> None:
        self.store = store

    def translate(self, intent: QueryIntent) -> NativeQuery:
        return NativeQuery(
            self.source_id,
            self.language,
            {
                "endpoint": "decision_events+promotion_queue+decision_impacts",
                "hunt_id": intent.seed.get("hunt_id"),
                "terms": sorted(_tokens(intent.seed.get("query", ""))),
            },
            intent,
        )

    def _records(self, intent: QueryIntent) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        hunt_id = intent.seed.get("hunt_id")
        decision_events = (
            self.store.decision_events_for_hunt(str(hunt_id))
            if hunt_id is not None
            else self.store.decision_events()
        )
        grouped: defaultdict[str | None, list[Any]] = defaultdict(list)
        for event in decision_events:
            grouped[event.hunt_id].append(event)
        chain_failures = []
        for _event_hunt_id, history in grouped.items():
            valid, broken = events.verify_chain(history)
            if not valid and broken:
                chain_failures.append(broken)

        records: list[dict[str, Any]] = []
        for event in decision_events:
            item = event.to_dict()
            item.update(
                {
                    "record_class": "case_decision",
                    "record_id": event.event_id,
                    "source": "bully.store",
                    "provenance": {
                        "store_db": str(self.store.db_path),
                        "event_id": event.event_id,
                        "prev_event_hash": event.prev_event_hash,
                        "chain_hash": event.chain_hash,
                    },
                }
            )
            records.append(item)

        for item in self.store.promotion_list():
            if hunt_id is not None and item.get("hunt_id") != hunt_id:
                continue
            record = dict(item)
            record.update(
                {
                    "record_class": (
                        "operator_confirmation"
                        if item.get("state") in {"confirmed", "rejected"}
                        else "promotion_queue"
                    ),
                    "record_id": item.get("queue_id"),
                    "source": "bully.store",
                    "provenance": {
                        "store_db": str(self.store.db_path),
                        "queue_id": item.get("queue_id"),
                        "resolved_by": item.get("resolved_by"),
                    },
                }
            )
            records.append(record)

        for item in self.store.decision_impacts():
            records.append(
                {
                    **item,
                    "record_class": "decision_impact",
                    "record_id": item.get("impact_id"),
                    "source": "bully.store",
                    "provenance": {
                        "store_db": str(self.store.db_path),
                        "impact_id": item.get("impact_id"),
                        "recall_id": item.get("recall_id"),
                    },
                }
            )

        terms = _tokens(intent.seed.get("query", ""))
        terms.update(_tokens(intent.seed.get("entities", ())))
        if terms:
            ranked = []
            for record in records:
                haystack = _tokens(json.dumps(record, sort_keys=True, default=str))
                score = len(terms & haystack)
                if score:
                    ranked.append((score, str(record.get("record_id")), record))
            records = [
                record for _, _, record in sorted(ranked, key=lambda item: (-item[0], item[1]))
            ]
        if intent.limit is not None:
            records = records[: intent.limit]
        metadata = {
            "record_count": len(records),
            "chain_valid": not chain_failures,
            "chain_failures": chain_failures,
            "record_classes": sorted({str(record["record_class"]) for record in records}),
        }
        return records, metadata

    def read(self, intent: QueryIntent) -> QueryResult:
        started = time.time()
        records, metadata = self._records(intent)
        return QueryResult(
            self.source_id,
            self.mode,
            self.translate(intent),
            tuple(records),
            started,
            time.time(),
            truncated=intent.limit is not None and len(records) >= intent.limit,
            metadata=metadata,
        )


def register_case_history_source(
    plane: DataPlane,
    store: Store,
    *,
    sample_limit: int = 64,
    source_id: str = "case-history",
) -> SourceProfile:
    connector = StoreCaseHistoryConnector(store)
    sample = connector.read(QueryIntent("case history sample", limit=sample_limit))
    record_count = len(connector._records(QueryIntent("case history count"))[0])
    if source_id != connector.source_id:
        connector.source_id = source_id
    return plane.connect(
        source_id,
        connector,
        sample.records,
        source_meta={
            "record_class": "case_history",
            "label_basis": True,
            "benign_present": True,
            "record_count_override": record_count,
            "freshness_at": time.time(),
        },
    )
