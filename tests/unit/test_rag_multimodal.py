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


async def test_vl_model_id_reads_health_and_caches(monkeypatch):
    monkeypatch.setattr(rm.httpx, "AsyncClient", _HealthClient)
    rm._MODEL_ID_CACHE.update(value=None, at=0.0)
    calls = []
    orig_get = _HealthClient.get

    async def counting_get(self, url):
        calls.append(url)
        return await orig_get(self, url)

    monkeypatch.setattr(_HealthClient, "get", counting_get)
    assert await rm._vl_model_id() == ("model-X", 2048)
    assert await rm._vl_model_id() == ("model-X", 2048)  # served from cache
    assert len(calls) == 1  # /health hit once, not per call


# ── C1: text-gated visual boost (B1 fusion fix) ────────────────────────────


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def search(self, _qvec):
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        return self._rows


def _wire_search(monkeypatch, *, text_distance, rerank_scores):
    """Patch _search's dependencies so only the fusion is exercised."""

    async def _emb(text=None, image_path=None, is_query=False):
        return [0.1] * rm.VL_DIM

    async def _model_id():
        return ("m", rm.VL_DIM)

    async def _rerank(q, cands, n):
        return [{"index": i, "score": s} for i, s in enumerate(rerank_scores)]

    monkeypatch.setattr(rm, "_vl_embed", _emb)
    monkeypatch.setattr(rm, "_vl_model_id", _model_id)
    monkeypatch.setattr(rm, "_assert_embedding_space", lambda *a: None)
    monkeypatch.setattr(rm, "_vl_rerank", _rerank)
    monkeypatch.setattr(
        rm,
        "_text_table",
        lambda kb, create=False: _FakeTable(
            [
                {
                    "chunk_id": "t1",
                    "source_file": "prose.pdf",
                    "chunk_index": 0,
                    "text": "x",
                    "_distance": text_distance,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        rm,
        "_visual_table",
        lambda kb, create=False: _FakeTable(
            [{"chunk_id": "v1", "source_file": "figure.pdf", "page": 1, "image_path": "/x.png"}]
        ),
    )


async def _run_search(kb="k", query="q"):
    class _R:
        async def json(self):
            return {"arguments": {"kb_id": kb, "query": query, "top_k": 3}}

    import json as _j

    return _j.loads((await rm._search(_R())).body)["results"]


async def test_c1_weak_text_promotes_the_figure(monkeypatch):
    # top text cosine ~0.40 (< VL_TEXT_GATE 0.67) -> visual boost ON
    _wire_search(monkeypatch, text_distance=1.2, rerank_scores=[0.7])
    res = await _run_search(query="which valve is fail-closed")
    assert res[0]["kind"] == "visual" and res[0]["reranker_prob"] == 0.7


async def test_c1_strong_text_keeps_text_first(monkeypatch):
    # top text cosine ~0.85 (>= gate) -> visual boost OFF, RRF tie -> text wins
    _wire_search(monkeypatch, text_distance=0.3, rerank_scores=[0.7])
    res = await _run_search(query="how often must an ESP be reviewed")
    assert res[0]["kind"] == "text"
