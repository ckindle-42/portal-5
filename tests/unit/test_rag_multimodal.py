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
