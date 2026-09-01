"""Acceptance: multimodal search is default; ingest indexes text (+visual); contracts intact."""

import asyncio
import importlib
import json
import sys
import types

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")


class _Req:
    def __init__(self, a):
        self._a = {"arguments": a}

    async def json(self):
        return self._a


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(rm, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(rm, "VL_DIM", 8)
    monkeypatch.setattr(rm, "_PAGES_DIR", tmp_path / "pages")
    rm._db = None

    async def _emb(text=None, image_path=None):
        return [0.1] * 8

    async def _rr(q, cands, n):
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]

    monkeypatch.setattr(rm, "_vl_embed", _emb)
    monkeypatch.setattr(rm, "_vl_rerank", _rr)
    # a fake rag_mcp so docling isn't required
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")

    async def _read_file(p):
        return "PLC-21 one-line diagram governed by CIP-007. " * 30

    fake._read_file = _read_file
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)


def test_registration_owns_retrieval_routes():
    calls = []

    class F:
        def custom_route(self, p, methods=None):
            def d(fn):
                calls.append(p)
                return fn

            return d

    rm.register_retrieval_routes(F())
    assert set(calls) == {"/tools/kb_ingest", "/tools/kb_search", "/tools/kb_search_all"}


def test_ingest_then_search_contract(tmp_path):
    pytest.importorskip("lancedb")
    src = tmp_path / "kbsrc"
    src.mkdir()
    (src / "d.txt").write_text("x")
    out = json.loads(_run(rm._ingest(_Req({"kb_id": "kbx", "source_dir": str(src)}))).body)
    # preserved kb_ingest contract keys
    assert {"kb_id", "files_ingested", "chunks_added", "fts_index"} <= set(out)
    assert out["chunks_added"] >= 1

    res = json.loads(_run(rm._search(_Req({"kb_id": "kbx", "query": "CIP-007"}))).body)
    assert {"kb_id", "query", "num_results", "results"} <= set(res)
    assert all("rerank_score" in r and "text" in r for r in res["results"])
    assert res["results"][0]["kind"] == "text"


def test_search_unknown_kb_is_404():
    out = _run(rm._search(_Req({"kb_id": "nope", "query": "q"})))
    assert out.status_code == 404


def test_search_all_contract(tmp_path):
    pytest.importorskip("lancedb")
    src = tmp_path / "s"
    src.mkdir()
    (src / "a.md").write_text("y")
    _run(rm._ingest(_Req({"kb_id": "kba", "source_dir": str(src)})))
    res = json.loads(_run(rm._search_all(_Req({"query": "CIP-007"}))).body)
    assert {"query", "num_results", "results"} <= set(res)
