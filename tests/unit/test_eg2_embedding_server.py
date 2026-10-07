"""Server-seam tests for scripts/eg2-embedding-server.py with a fake backend.

No model, no network: the backend factory is injected and the VL upstream is
patched. Covers prefixing, Matryoshka truncation, strict-model rejection, the
readiness probes, and the VL / Open WebUI compatibility surfaces.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "eg2-embedding-server.py"
_spec = importlib.util.spec_from_file_location("eg2_embedding_server", _PATH)
assert _spec and _spec.loader
srv = importlib.util.module_from_spec(_spec)
sys.modules["eg2_embedding_server"] = srv
_spec.loader.exec_module(srv)

from portal.platform.embedding import contract as ec  # noqa: E402


def _vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    return [((h[i % len(h)] + i * 7) % 89) - 44.0 for i in range(768)]


class FakeBackend:
    def __init__(self, nan: bool = False) -> None:
        self.seen: list[Any] = []
        self.nan = nan

    def identity(self) -> ec.Identity:
        return ec.Identity(
            "google/embeddinggemma-2",
            "deadbeefcafe0000",
            768,
            "bfloat16",
            "cpu",
            "fake",
            ("text", "image"),
        )

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        self.seen.extend(texts)
        if self.nan:
            return [[float("nan")] * 768 for _ in texts]
        return [ec.l2_normalize(_vec(t)) for t in texts]

    def encode_items(self, items: list[dict[str, Any]]) -> list[list[float]]:
        self.seen.extend(items)
        return [ec.l2_normalize(_vec(repr(sorted(i.items())))) for i in items]


@pytest.fixture()
def fake() -> FakeBackend:
    fb = FakeBackend()
    srv.set_backend_factory(lambda: fb)
    return fb


@pytest.fixture()
def client(fake: FakeBackend) -> TestClient:
    return TestClient(srv.app)


def test_health_does_not_load(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["loaded"] is False


def test_ready_reports_identity_and_checks(client: TestClient) -> None:
    r = client.get("/ready")
    body = r.json()
    assert r.status_code == 200 and body["ready"] is True
    assert body["identity"]["model"] == "google/embeddinggemma-2"
    assert body["version_tag"] == "google/embeddinggemma-2@deadbeefcafe:768d"
    assert all(body["checks"].values())


def test_ready_fails_on_nan() -> None:
    srv.set_backend_factory(lambda: FakeBackend(nan=True))
    r = TestClient(srv.app).get("/ready")
    assert r.status_code == 503 and r.json()["ready"] is False


def test_embed_applies_contract_prefix_and_truncates(client: TestClient, fake: FakeBackend) -> None:
    r = client.post(
        "/embed",
        json={
            "inputs": [{"text": "kerberoast"}],
            "task": "search result",
            "role": "query",
            "dim": 128,
        },
    )
    assert r.status_code == 200
    v = r.json()["embeddings"][0]
    assert len(v) == 128 and abs(sum(x * x for x in v) - 1.0) < 1e-9
    assert fake.seen[-1] == "task: search result | query: kerberoast"
    r = client.post(
        "/embed",
        json={"inputs": [{"text": "x", "title": "T"}], "task": "search result", "role": "document"},
    )
    assert fake.seen[-1] == "title: T | text: x" and len(r.json()["embeddings"][0]) == 768


def test_embed_rejects_untrained_dim(client: TestClient) -> None:
    r = client.post(
        "/embed", json={"inputs": [{"text": "x"}], "task": "classification", "dim": 300}
    )
    assert r.status_code == 400


def test_openai_endpoint_is_raw_and_strict_on_model(client: TestClient, fake: FakeBackend) -> None:
    r = client.post(
        "/v1/embeddings",
        json={"input": ["raw text"], "model": "google/embeddinggemma-2", "dimensions": 256},
    )
    assert r.status_code == 200 and len(r.json()["data"][0]["embedding"]) == 256
    assert fake.seen[-1] == "raw text"  # no server-side prefix on the OpenAI surface
    r = client.post("/v1/embeddings", json={"input": "x", "model": "microsoft/harrier-oss-v1-0.6b"})
    assert r.status_code == 409


def test_embed_items_media_unprefixed_text_prefixed(
    client: TestClient, fake: FakeBackend, tmp_path: Path
) -> None:
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    r = client.post(
        "/embed_items",
        json={
            "items": [{"text": "only text"}, {"image_path": str(img)}],
            "task": "search result",
            "role": "document",
            "dim": 512,
        },
    )
    assert r.status_code == 200 and len(r.json()["embeddings"]) == 2
    first, second = fake.seen[-2], fake.seen[-1]
    assert first == {"text": "title: none | text: only text"}
    assert second == {"image": str(img)}


def test_embed_items_missing_file_is_400(client: TestClient) -> None:
    r = client.post("/embed_items", json={"items": [{"image_path": "/nope.png"}]})
    assert r.status_code == 400


def test_vl_compat_surface(
    client: TestClient, fake: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = client.get("/vl/health").json()
    assert h["embedding_dim"] == srv.VL_COMPAT_DIM and h["embed_model"].startswith(
        "google/embeddinggemma-2"
    )
    r = client.post(
        "/vl/embed_batch", json={"items": [{"text": "q", "is_query": True}, {"text": "d"}]}
    )
    assert r.status_code == 200 and r.json()["count"] == 2
    assert fake.seen[-2] == {"text": "task: search result | query: q"}
    assert fake.seen[-1] == {"text": "title: none | text: d"}

    async def fake_rerank(query: Any, documents: list[Any], top_n: Any) -> list[dict[str, Any]]:
        return [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}]

    monkeypatch.setattr(srv, "_vl_rerank", fake_rerank)
    r = client.post(
        "/vl/rerank", json={"query": {"text": "q"}, "documents": [{"text": "a"}, {"text": "b"}]}
    )
    assert r.json()["results"][0] == {"index": 1, "score": 0.9}
    r = client.post(
        "/v1/rerank", json={"model": "x", "query": "q", "documents": ["a", "b"], "top_n": 2}
    )
    assert r.json()["results"][0] == {"index": 1, "relevance_score": 0.9}


def test_config_kwargs_selective_loading() -> None:
    assert srv._config_kwargs(("text",)) == {"vision_config": None, "audio_config": None}
    assert srv._config_kwargs(("text", "image")) == {"audio_config": None}
    assert srv._config_kwargs(("text", "video")) == {"audio_config": None}
    assert srv._config_kwargs(("text", "audio")) == {"vision_config": None}
    assert srv._config_kwargs(("text", "image", "audio")) == {}
