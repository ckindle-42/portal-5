"""SA3.3 -- Arm B: llama.cpp embedding server tests
(TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1).

The Arm B server wraps a real `llama-server` child process, so these tests
verify the prefix-routing + OpenAI contract logic fully offline by faking the
upstream llama-server HTTP round trip (httpx MockTransport), and verify the
`organ` side (document vs query URL wiring) with an httpx double -- no real
llama-server, no network.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from portal.modules.security.core.bully.organ import Organ, OrganUnavailable
from portal.modules.security.core.bully.store import Store

SCRIPT = "scripts/embedding-server-llamacpp.py"
DOC_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "


@pytest.fixture
def arm_b_module(monkeypatch):
    """Import the Arm B server with a fake llama-server backend (MockTransport)
    so the wrapper's prefix logic is exercised without spawning llama-server."""
    monkeypatch.setattr(
        sys, "argv", ["embedding-server-llamacpp.py", "--port", "8943", "--model", "mock.gguf"]
    )
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location("embedding_server_llamacpp_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _fake_llama(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content.decode("utf-8"))
        inputs = body["input"]
        inputs = [inputs] if isinstance(inputs, str) else inputs
        # Emit prefix-distinguishable vectors: doc form gets +1 offset on the
        # first coordinate, query form gets +10, so routing is observable.
        is_query = all(text.startswith(QUERY_PREFIX) for text in inputs)
        offset = 10.0 if is_query else 1.0
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "index": i,
                        "embedding": [
                            float(i + 1) * offset,
                            float(i + 1) * 2 * offset,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                        ],
                    }
                    for i in range(len(inputs))
                ],
                "model": "mock.gguf",
            },
        )

    module._client = httpx.Client(
        base_url="http://127.0.0.1:8942", transport=httpx.MockTransport(_fake_llama)
    )
    module._start_llama_server = lambda: None  # noqa: SLF001 -- no real spawn in tests
    module._llama_proc = type(
        "P",
        (),
        {
            "poll": lambda self: None,
            "send_signal": lambda self, sig: None,
            "wait": lambda self, timeout=5: None,
        },
    )()
    yield module


@pytest.fixture
def arm_b_client(arm_b_module):
    with TestClient(arm_b_module.app) as client:
        yield client


def test_health_reports_backend_and_prefixes(arm_b_client):
    resp = arm_b_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["backend"] == "llamacpp"
    assert body["task_prefixes"]["document"] == DOC_PREFIX.strip()
    assert body["task_prefixes"]["query"] == QUERY_PREFIX.strip()


def test_v1_models_contract(arm_b_client):
    resp = arm_b_client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["id"] == "mock.gguf"


def test_document_endpoint_applies_document_prefix(arm_b_client, arm_b_module):
    captured: list[list[str]] = []
    orig_post = arm_b_module._client.post  # noqa: SLF001

    def _spy_post(*args, **kwargs):
        payload = kwargs.get("json") or args[1]
        captured.append(payload["input"])
        return orig_post(*args, **kwargs)

    arm_b_module._client.post = _spy_post  # type: ignore[method-assign]
    resp = arm_b_client.post("/v1/embeddings", json={"input": ["logon ticket_request"]})
    assert resp.status_code == 200
    assert resp.json()["task"] == "document"
    assert captured == [[DOC_PREFIX + "logon ticket_request"]]
    assert resp.json()["data"][0]["embedding"] == [1.0, 2.0, 0.0, 0.0, 0.0, 0.0]


def test_query_endpoint_applies_query_prefix(arm_b_client, arm_b_module):
    captured: list[list[str]] = []
    orig_post = arm_b_module._client.post  # noqa: SLF001

    def _spy_post(*args, **kwargs):
        payload = kwargs.get("json") or args[1]
        captured.append(payload["input"])
        return orig_post(*args, **kwargs)

    arm_b_module._client.post = _spy_post  # type: ignore[method-assign]
    resp = arm_b_client.post("/v1/embeddings/query", json={"input": ["logon ticket_request"]})
    assert resp.status_code == 200
    assert resp.json()["task"] == "query"
    assert captured == [[QUERY_PREFIX + "logon ticket_request"]]
    assert resp.json()["data"][0]["embedding"] == [10.0, 20.0, 0.0, 0.0, 0.0, 0.0]


def test_document_and_query_vectors_differ_in_routing(arm_b_client, arm_b_module):
    doc = arm_b_client.post("/v1/embeddings", json={"input": ["same text"]}).json()
    q = arm_b_client.post("/v1/embeddings/query", json={"input": ["same text"]}).json()
    assert doc["data"][0]["embedding"] != q["data"][0]["embedding"]


def test_empty_input_returns_400(arm_b_client):
    resp = arm_b_client.post("/v1/embeddings", json={"input": []})
    assert resp.status_code == 400


def test_float16_not_used_in_server_source():
    """SA3.3: EmbeddingGemma activations do not support float16 -- the wrapper
    must never force float16 (llama.cpp GGUF runs bf16/f32 by default)."""
    source = Path(SCRIPT).read_text(encoding="utf-8")
    assert "float16" not in source


# ── organ-side query/document wiring ────────────────────────────────────────


def _embed_url_client(doc_payload=None, query_payload=None):
    calls = {"doc": [], "query": []}

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = __import__("json").loads(request.content.decode("utf-8"))
        n = len(body["input"])
        if path == "/v1/embeddings":
            calls["doc"].append(body["input"])
            vector = doc_payload or [[1.0, 0.0] for _ in range(n)]
        else:
            calls["query"].append(body["input"])
            vector = query_payload or [[0.0, 1.0] for _ in range(n)]
        return httpx.Response(
            200,
            json={
                "data": [{"index": i, "embedding": list(v)} for i, v in enumerate(vector)],
                "model": "test",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    return client, calls


def test_organ_upsert_uses_document_url_and_knn_uses_query_url(tmp_path):
    store = Store(tmp_path / "hunt_state.db")
    store.hunt_create(
        hunt_id="hunt-1",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    embed_client, calls = _embed_url_client()
    record = {
        "kind": "cousin",
        "semantic_query": "logon ticket_request",
        "tactic": "discovery",
    }
    doc_text = "discovery | logon ticket_request"  # organ._canonical_record_text
    organ = Organ(
        store=store,
        db_path=tmp_path / "hunt_memory",
        embed_url="http://localhost:8943/v1/embeddings",
        query_embed_url="http://localhost:8943/v1/embeddings/query",
        embed_client=embed_client,
    )
    try:
        organ.upsert_many([record], batch_size=1)
        assert calls["doc"] == [[doc_text]]
        assert calls["query"] == []

        organ.prepare_knn(["logon ticket_request"], k=2)
        assert calls["query"] == [["logon ticket_request"]]
        assert calls["doc"] == [[doc_text]]

        organ.knn("logon ticket_request", k=2)
        # prepared vectors cache -> no new embed call
        assert len(calls["query"]) == 1
    finally:
        organ.close()
        store.close()


def test_organ_query_url_off_surfaces_organ_unavailable(tmp_path):
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    embed_client = httpx.Client(transport=httpx.MockTransport(_handler))
    store = Store(tmp_path / "hunt_state.db")
    organ = Organ(
        store=store,
        db_path=tmp_path / "hunt_memory",
        embed_url="http://localhost:8943/v1/embeddings",
        query_embed_url="http://localhost:8943/v1/embeddings/query",
        embed_client=embed_client,
    )
    try:
        with pytest.raises(OrganUnavailable):
            organ.knn("anything", k=2)
    finally:
        organ.close()
        store.close()
