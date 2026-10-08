"""Graph memory on EmbeddingGemma 2: prefixed wire format, the dimension guard, and the
resumable re-embed of a store left at 1024d by the retired :8917 embedder."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import lancedb
import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from portal.platform.embedding.client import EmbeddingClient
from portal.platform.memory import graph_memory as gm
from portal.platform.memory import reembed

IDENTITY = {
    "model": "google/embeddinggemma-2",
    "revision": "914f7f89142e33e77833254d9c9b90c3cef7303b",
    "native_dim": 768,
    "dtype": "bfloat16",
    "device": "mps",
    "backend": "sentence-transformers",
    "modalities": ["text"],
}


def _fake_service(calls: list[dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ready":
            return httpx.Response(200, json={"ready": True, "identity": IDENTITY})
        body = json.loads(request.content)
        calls.append(body)
        n = len(body["inputs"])
        return httpx.Response(
            200,
            json={
                "embeddings": [[1.0] + [0.0] * (body["dim"] - 1)] * n,
                "model": IDENTITY["model"],
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(gm, "LANCE_DIR", str(tmp_path))
    monkeypatch.setattr(gm, "_db", None)
    monkeypatch.setattr(gm, "_tables", {})
    monkeypatch.setattr(
        gm, "_client", EmbeddingClient("http://eg2.test", transport=_fake_service(calls))
    )
    return calls


def test_memory_and_query_embed_as_search_documents_and_queries(store) -> None:
    asyncio.run(gm._embed("PLC-21 is governed by CIP-007", gm.Role.DOCUMENT))
    asyncio.run(gm._embed("which standard governs PLC-21", gm.Role.QUERY))
    assert [(c["task"], c["role"], c["dim"]) for c in store] == [
        ("search result", "document", 768),
        ("search result", "query", 768),
    ]


def _legacy_store(path: Path) -> None:
    db = lancedb.connect(str(path))
    vec = pa.field("vector", pa.list_(pa.float32(), 1024))
    db.create_table(
        gm.MEMORY_TABLE,
        data=pa.Table.from_pylist(
            [
                {"id": f"m{i}", "user_id": "default", "text": f"fact {i}", "category": "fact",
                 "tags": [], "vector": [0.1] * 1024, "created_at": 1.0,
                 "last_accessed_at": 1.0, "access_count": 0}
                for i in range(70)
            ],
            schema=pa.schema(
                [pa.field("id", pa.string()), pa.field("user_id", pa.string()),
                 pa.field("text", pa.string()), pa.field("category", pa.string()),
                 pa.field("tags", pa.list_(pa.string())), vec,
                 pa.field("created_at", pa.float64()), pa.field("last_accessed_at", pa.float64()),
                 pa.field("access_count", pa.int64())]
            ),
        ),
    )  # fmt: skip
    db.create_table(
        gm.ENTITIES_TABLE,
        data=pa.Table.from_pylist(
            [{"id": "e0", "user_id": "default", "name": "PLC-21", "etype": "asset",
              "vector": [0.1] * 1024, "first_seen": 1.0, "last_seen": 1.0, "mention_count": 1}],
            schema=pa.schema(
                [pa.field("id", pa.string()), pa.field("user_id", pa.string()),
                 pa.field("name", pa.string()), pa.field("etype", pa.string()), vec,
                 pa.field("first_seen", pa.float64()), pa.field("last_seen", pa.float64()),
                 pa.field("mention_count", pa.int64())]
            ),
        ),
    )  # fmt: skip


def test_legacy_dimension_store_is_refused(store, tmp_path: Path) -> None:
    _legacy_store(tmp_path)
    with pytest.raises(gm.StoreSpaceMismatchError, match="reembed"):
        gm._memory_table()


def test_reembed_rewrites_both_tables_stamped_and_resumes(store, tmp_path: Path) -> None:
    _legacy_store(tmp_path)
    # a previous run embedded the first batch and died
    (tmp_path / reembed.CHECKPOINT).write_text(
        json.dumps({gm.MEMORY_TABLE: {f"m{i}": [0.5] * 768 for i in range(64)}})
    )
    out = asyncio.run(reembed.run())

    assert out[gm.MEMORY_TABLE] == 70 and out[gm.ENTITIES_TABLE] == 1
    # only the 6 missing memories and the entity were sent to the service
    assert sum(len(c["inputs"]) for c in store) == 7
    assert all((c["task"], c["role"]) == ("search result", "document") for c in store)
    rows = {r["id"]: r for r in gm._memory_table().to_arrow().to_pylist()}
    assert len(rows) == 70 and rows["m0"]["vector"][0] == 0.5 and rows["m69"]["vector"][0] == 1.0
    assert {r["embedding_version"] for r in rows.values()} == {
        "google/embeddinggemma-2@914f7f89142e:768d"
    }
    assert gm._entities().count_rows() == 1
    assert (tmp_path / reembed.BACKUP_DIR / f"{gm.MEMORY_TABLE}.lance").is_dir()
    assert not (tmp_path / reembed.CHECKPOINT).exists()
    assert list(tmp_path.glob(f"{reembed.CHECKPOINT}.done-*"))
    # a second run is a no-op
    store.clear()
    assert asyncio.run(reembed.run())[gm.MEMORY_TABLE] == 0 and not store
