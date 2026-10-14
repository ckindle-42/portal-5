"""N-29: kb_list and the KB maintenance tools use the one KB store (retrieval.store)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import pytest


@pytest.fixture
def rag(tmp_path, monkeypatch):
    import portal.platform.lance_guard as lg
    from portal.modules.research.tools import rag_mcp
    from portal.modules.research.tools import rag_multimodal as rm
    from portal.platform.retrieval import embedding as emb
    from portal.platform.retrieval import store

    monkeypatch.setattr(lg, "require_lance_dir", lambda *a, **k: None)
    monkeypatch.setattr(store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(store, "_db", None)
    monkeypatch.setenv("PORTAL5_KB_SOURCES_DIR", str(tmp_path / "sources"))
    dim = emb.VL_DIM

    async def embed_batch(items):
        out = []
        for it in items:
            v = [0.0] * dim
            for w in re.findall(r"[a-z0-9]+", (it.get("text") or "").lower()):
                v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % dim] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out

    async def model_id():
        return ("stub-vl", dim)

    async def rerank(query, candidates, top_n):
        return [{"index": i, "score": 0.5} for i in range(min(top_n, len(candidates)))]

    monkeypatch.setattr(emb, "vl_embed_batch", embed_batch)
    monkeypatch.setattr(emb, "vl_model_id", model_id)
    monkeypatch.setattr(emb, "vl_rerank", rerank)
    return rm, rag_mcp, store, tmp_path


def _post(handler, body):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
    resp = asyncio.run(handler(req))
    return resp.status_code, json.loads(resp.body)


def test_kb_list_uses_the_one_store_n21(rag):
    """N-29: kb_list kept its own (lower-casing, unpaged) table naming and lost KBs."""
    rm, rag_mcp, store, tmp = rag
    src = tmp / "cip"
    src.mkdir()
    (src / "r.md").write_text("CIP-007 R2 patch management evaluation every 35 days.")
    asyncio.run(rm._pipeline.ingest_document(rm._composition(), "NERC-CIP", src, True))
    _, full = _post(rag_mcp.kb_list_endpoint, {})
    kbs = {k["kb_id"]: k["chunks"] for k in full["knowledge_bases"]}
    assert kbs.get("NERC-CIP", 0) >= 1 and not any(k.endswith("_visual") for k in kbs)
