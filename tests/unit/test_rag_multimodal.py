"""Unit tests for portal.modules.research.tools.rag_multimodal client seam
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 A1).

No network, no LanceDB, no VL server — httpx.AsyncClient is faked.
"""

from __future__ import annotations

import pytest

rm = pytest.importorskip(
    "portal.modules.research.tools.rag_multimodal",
    reason="lancedb/pyarrow/httpx not importable",
)


class _FakeResp:
    def __init__(self, n):
        self._n = n

    def raise_for_status(self):
        pass

    def json(self):
        return {"embeddings": [[0.1] * rm.VL_DIM for _ in range(self._n)]}


class _FakeClient:
    posted: list[int] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url, json):
        n = len(json["items"])
        _FakeClient.posted.append(n)
        return _FakeResp(n)


async def test_vl_embed_batch_caps_request_size(monkeypatch):
    monkeypatch.setattr(rm, "VL_EMBED_MAX_ITEMS", 4)
    monkeypatch.setattr(rm.httpx, "AsyncClient", _FakeClient)
    _FakeClient.posted = []
    vecs = await rm._vl_embed_batch([{"text": f"t{i}"} for i in range(10)])
    assert len(vecs) == 10
    assert _FakeClient.posted == [4, 4, 2]  # 3 requests, none over the cap, order kept


async def test_vl_embed_batch_empty_is_noop(monkeypatch):
    monkeypatch.setattr(rm.httpx, "AsyncClient", _FakeClient)
    _FakeClient.posted = []
    assert await rm._vl_embed_batch([]) == []
    assert _FakeClient.posted == []


# ── A3: embedding-model identity stamp ──────────────────────────────────────


def test_write_then_read_stamp_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RAG_DIR", str(tmp_path))
    rm._write_stamp("kb1", "mlx-community/Qwen3-VL-Embedding-2B-mxfp8", 2048)
    got = rm._read_stamp("kb1")
    assert got["embed_model"] == "mlx-community/Qwen3-VL-Embedding-2B-mxfp8"
    assert got["vl_dim"] == 2048
    assert rm._read_stamp("absent") is None


def test_assert_embedding_space_rejects_same_dim_different_model(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RAG_DIR", str(tmp_path))
    rm._write_stamp("kb1", "model-A-2048", 2048)
    rm._assert_embedding_space("kb1", "model-A-2048")  # match: fine
    with pytest.raises(rm._VLUnavailableError, match="different spaces"):
        rm._assert_embedding_space("kb1", "model-B-2048")
    # an unstamped KB (legacy) is not blocked
    rm._assert_embedding_space("kb-legacy", "model-B-2048")


class _HealthClient:
    payload = {"embed_model": "model-X", "embedding_dim": 2048}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url):
        return _FakeHealthResp(_HealthClient.payload)


class _FakeHealthResp:
    def __init__(self, p):
        self._p = p

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


async def test_vl_model_id_reads_health(monkeypatch):
    monkeypatch.setattr(rm.httpx, "AsyncClient", _HealthClient)
    assert await rm._vl_model_id() == ("model-X", 2048)
