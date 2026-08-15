"""bully.organ -- ORG, the sole toucher of the `hunt_memory` LanceDB
projection (P1.4). Mandatory recall receipts, decision impacts.

API per I-4: upsert (via the outbox worker, never inline in a caller's
transaction), knn (raw cosine distance + source hashes), recall (mandatory
pre-hunt -> RecallReceipt), index_emissions (universal, outbox-coupled),
stats. store.py is the coordination point for the outbox table itself
(MASTER SS3: only store.py does SQL); this module calls the Store's public
outbox_* API rather than touching sqlite3 directly.

Failure semantics (I-4, critical): the embed service (:8917) unreachable ->
recall unsatisfiable -> the hunt blocks honestly. There is no lexical
fallback path here, ever -- that is the growth_loop failure mode this
design explicitly rejects.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .contracts import RecallReceipt
from .store import Store

DEFAULT_EMBED_URL = "http://localhost:8917/v1/embeddings"
DEFAULT_RERANK_URL = "http://localhost:8925/rerank"
PROJECTION_VERSION = "hunt-memory-v1"
EMBEDDING_VERSION = "sentence-transformers-v1"
TABLE_NAME = "hunt_memory"
VECTOR_DIM = 1024


class OrganUnavailable(RuntimeError):  # noqa: N818 -- exact name from FINAL_VALIDATION I2
    """Embed service unreachable -> recall unsatisfiable -> honest block (I-4)."""


def _canonical_record_text(record: dict[str, Any]) -> str:
    """Deterministic embed text (DATA_MODEL SS2): substantive fields only,
    no timestamps/ids (identity lives in metadata, not the embedded text)."""
    parts = [
        str(record.get("tactic", "")),
        " ".join(record.get("technique_ids") or []),
        str(record.get("field_signature", "")),
        str(record.get("behavior_sequence", "")),
        str(record.get("detection_response", "")),
        str(record.get("relationship", "")),
        str(record.get("rationale", "")),
    ]
    return " | ".join(p for p in parts if p)


def record_id_for(record: dict[str, Any]) -> str:
    """Content-derived record id (DATA_MODEL SS4.1): `hr-<kind>-<hash>`."""
    kind = record.get("kind", "record")
    h = hashlib.sha256(_canonical_record_text(record).encode("utf-8")).hexdigest()[:16]
    return f"hr-{kind}-{h}"


def source_hash_for(record: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class Organ:
    """ORG -- the sole toucher of the `hunt_memory` LanceDB projection."""

    def __init__(
        self,
        *,
        store: Store,
        db_path: Path,
        embed_url: str = DEFAULT_EMBED_URL,
        rerank_url: str | None = DEFAULT_RERANK_URL,
        embed_client: httpx.Client | None = None,
        projection_version: str = PROJECTION_VERSION,
        embedding_version: str = EMBEDDING_VERSION,
    ) -> None:
        import lancedb

        self.store = store
        self.embed_url = embed_url
        self.rerank_url = rerank_url
        self._http = embed_client or httpx.Client(timeout=10.0)
        self.projection_version = projection_version
        self.embedding_version = embedding_version
        self._db = lancedb.connect(str(db_path))

    def close(self) -> None:
        self._http.close()

    # ── embedding client (:8917) ─────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self._http.post(self.embed_url, json={"input": texts})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OrganUnavailable(f"embed service unreachable at {self.embed_url}: {exc}") from exc
        data = resp.json()
        vectors = data.get("embeddings") or [d["embedding"] for d in data.get("data", [])]
        if not vectors:
            raise OrganUnavailable("embed service returned no vectors")
        return vectors

    def _table(self):
        if TABLE_NAME in self._db.list_tables().tables:
            return self._db.open_table(TABLE_NAME)
        return None

    # ── upsert / knn (I-4) ───────────────────────────────────────────────

    def upsert(self, record: dict[str, Any]) -> str:
        """Embed + upsert one row, keyed by content-derived record_id.

        Called by the outbox worker (`process_outbox`), never inline in a
        producer's own transaction (I-4).
        """
        rid = record.get("record_id") or record_id_for(record)
        text = _canonical_record_text(record)
        vector = self._embed([text])[0]
        row = {
            **record,
            "record_id": rid,
            "text": text,
            "vector": vector,
            "projection_version": self.projection_version,
            "ingested_at": time.time(),
        }
        table = self._table()
        if table is None:
            self._db.create_table(TABLE_NAME, data=[row])
        else:
            table.merge_insert(
                "record_id"
            ).when_matched_update_all().when_not_matched_insert_all().execute([row])
        return rid

    def knn(
        self, query: str, k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        # Embed first, unconditionally: an empty projection is a legitimate
        # empty result, but an unreachable embed service must surface as
        # OrganUnavailable even when there is nothing indexed yet -- recall
        # health is about the service, not about whether data exists.
        vector = self._embed([query])[0]
        table = self._table()
        if table is None:
            return []
        search = table.search(vector).metric("cosine").limit(k)
        if filters:
            clauses = []
            for key, value in filters.items():
                if isinstance(value, str):
                    clauses.append(f"{key} = '{value}'")
                else:
                    clauses.append(f"{key} = {value}")
            if clauses:
                search = search.where(" AND ".join(clauses))
        rows = search.to_list()
        return [({k2: v for k2, v in r.items() if k2 != "_distance"}, r["_distance"]) for r in rows]

    # ── recall (mandatory pre-hunt) ──────────────────────────────────────

    def recall(
        self, *, hunt_id: str, query: str, k: int = 8, filters: dict | None = None
    ) -> RecallReceipt:
        """Mandatory pre-hunt recall (I-4). Persisted even when empty/degraded.

        On embed outage: persists a degraded receipt (source_health records
        the outage) and then raises OrganUnavailable -- the caller (LOOP,
        P1.7) must treat this as an honest block, never a silent lexical
        fallback.
        """
        recall_id = f"rr-{uuid.uuid4().hex[:12]}"
        try:
            candidates = self.knn(query, k, filters)
            source_health = {"embed": "ok"}
            receipt = RecallReceipt(
                recall_id=recall_id,
                hunt_id=hunt_id,
                query=query,
                filters=filters or {},
                source_health=source_health,
                projection_version=self.projection_version,
                embedding_version=self.embedding_version,
                reranker_version=self.rerank_url and "rerank-v1",
                candidates=[{"record": rec, "distance": dist} for rec, dist in candidates],
                exclusions=[],
                selected_context=[{"record": rec} for rec, _ in candidates[:k]],
            )
            self.store.recall_receipt_put(receipt)
            return receipt
        except OrganUnavailable as exc:
            degraded = RecallReceipt(
                recall_id=recall_id,
                hunt_id=hunt_id,
                query=query,
                filters=filters or {},
                source_health={"embed": "unreachable", "error": str(exc)},
                projection_version=self.projection_version,
                embedding_version=self.embedding_version,
                reranker_version=None,
                candidates=[],
                exclusions=[],
                selected_context=[],
            )
            self.store.recall_receipt_put(degraded)
            raise

    # ── index_emissions (universal, outbox-coupled) ─────────────────────

    def index_emissions(
        self, records: list[dict[str, Any]], *, required_for_closure: bool = True
    ) -> list[str]:
        """Enqueue every record for indexing via the transactional outbox.

        Universal: every record that must reach the projection goes through
        here, so `store.outbox_required_dead_letters()` is a complete
        picture of what has NOT yet reached ORG.
        """
        outbox_ids = []
        for record in records:
            rid = record.get("record_id") or record_id_for(record)
            record = {**record, "record_id": rid}
            outbox_ids.append(
                self.store.outbox_append(
                    record_type=str(record.get("kind", "record")),
                    record_id=rid,
                    record_version=0,
                    projection_version=self.projection_version,
                    source_hash=source_hash_for(record),
                    operation="upsert",
                    required_for_closure=required_for_closure,
                    payload=record,
                )
            )
        return outbox_ids

    def process_outbox(self, limit: int = 50) -> dict[str, int]:
        """The outbox worker: lease -> upsert -> complete/fail."""
        leased = self.store.outbox_lease(limit)
        completed = 0
        failed = 0
        for item in leased:
            payload = json.loads(item["payload"])
            try:
                self.upsert(payload)
            except OrganUnavailable as exc:
                self.store.outbox_fail(item["outbox_id"], error=str(exc))
                failed += 1
                continue
            self.store.outbox_complete(item["outbox_id"], source_hash=item["source_hash"])
            completed += 1
        return {"leased": len(leased), "completed": completed, "failed": failed}

    # ── stats / rebuild ───────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        table = self._table()
        return {
            "row_count": table.count_rows() if table is not None else 0,
            "projection_version": self.projection_version,
            "embedding_version": self.embedding_version,
        }

    def rebuild_by_replay(self, records: list[dict[str, Any]]) -> int:
        """Idempotent rebuild-by-replay from SUB (C3): drop + re-upsert."""
        if TABLE_NAME in self._db.list_tables().tables:
            self._db.drop_table(TABLE_NAME)
        for record in records:
            self.upsert(record)
        return len(records)
