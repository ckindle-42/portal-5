"""Locks the shape of the shared RAG tools against their consumers.

TASK_RAG_COMPOSITION_SEAM_V1 P1.2. ``kb_search`` / ``kb_ingest`` / ``kb_search_all``
serve fourteen persona workspaces plus the router's auto-context injector. The
injector drifted off-contract (sent ``k`` instead of ``top_k`` and no ``kb_id``)
and the failure read as an empty-KB miss for months. This test asserts:

* the documented response keys are present (extra keys are allowed);
* the router's own consumer parse (``_extract_snippets``) tolerates unknown extra
  fields rather than raising;
* every argument shape a live caller sends is one ``_search`` / ``_ingest`` accepts.

The caller shapes are enumerated here from the P0 discovery sweep, not hardcoded
guesses: the only dynamic (non-persona-declaration) caller of the shared tools is
``context_inject.inject_retrieved_context``.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")
from portal.platform.inference.router import context_inject  # noqa: E402


class _Req:
    def __init__(self, a: dict):
        self._a = {"arguments": a}

    async def json(self):
        return self._a


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", 8)
    monkeypatch.setattr(rm, "VL_DIM", 8)
    monkeypatch.setattr(rm, "_PAGES_DIR", tmp_path / "pages")
    _store._db = None

    async def _emb(text=None, image_path=None, is_query=False):
        return [0.1] * 8

    async def _emb_batch(items):
        return [[0.1] * 8 for _ in items]

    async def _rr(q, cands, n):
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]

    async def _model_id():
        return ("fake-vl-model", 8)

    monkeypatch.setattr(rm, "_vl_embed", _emb)
    monkeypatch.setattr(rm, "_vl_embed_batch", _emb_batch)
    monkeypatch.setattr(rm, "_vl_rerank", _rr)
    monkeypatch.setattr(rm, "_vl_model_id", _model_id)
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")

    async def _read_file(p):
        return "PLC-21 one-line diagram governed by CIP-007. " * 30

    fake._read_file = _read_file
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)


# Documented response contracts (P1.2). Extra keys are allowed; these must be present.
_KB_SEARCH_KEYS = {"kb_id", "query", "num_results", "results"}
_KB_SEARCH_RESULT_KEYS = {
    "chunk_id",
    "source_file",
    "chunk_index",
    "text",
    "fused_score",
    "reranker_prob",
    "kind",
}
_KB_INGEST_KEYS = {"kb_id", "files_ingested", "chunks_added", "pages_added", "fts_index"}
_KB_SEARCH_ALL_KEYS = {"query", "num_results", "results"}

# Argument shapes live callers send. Enumerated from P0.B: the injector is the only
# dynamic caller; personas declare the tools but the MCP bridge fills args.
_CALLER_ARG_SHAPES = [
    ("kb_search", {"kb_id": "kbc", "query": "CIP-007", "top_k": 4}),
    ("kb_search", {"kb_id": "kbc", "query": "CIP-007"}),
    ("kb_search_all", {"query": "CIP-007", "top_k": 4}),
    ("kb_ingest", None),  # filled per-test with a real source_dir
]


@pytest.fixture
def _kb(tmp_path):
    pytest.importorskip("lancedb")
    src = tmp_path / "kbsrc"
    src.mkdir()
    (src / "d.txt").write_text("PLC-21 one-line diagram governed by CIP-007-6 R2.")
    _run(rm._ingest(_Req({"kb_id": "kbc", "source_dir": str(src)})))
    return "kbc", src


def test_kb_search_response_contract(_kb):
    res = json.loads(_run(rm._search(_Req({"kb_id": "kbc", "query": "CIP-007", "top_k": 4}))).body)
    assert set(res) >= _KB_SEARCH_KEYS
    for r in res["results"]:
        assert set(r) >= _KB_SEARCH_RESULT_KEYS, sorted(r)
        assert r["kind"] in ("text", "visual")
        if r["kind"] == "visual":
            assert "page" in r


def test_kb_ingest_response_contract(_kb):
    _kb_id, src = _kb
    out = json.loads(_run(rm._ingest(_Req({"kb_id": "kbi", "source_dir": str(src)}))).body)
    assert set(out) >= _KB_INGEST_KEYS


def test_kb_search_all_response_contract(_kb):
    res = json.loads(_run(rm._search_all(_Req({"query": "CIP-007", "top_k": 4}))).body)
    assert set(res) >= _KB_SEARCH_ALL_KEYS
    for r in res["results"]:
        assert "kb_id" in r


def test_extract_snippets_tolerates_unknown_extra_fields(_kb):
    """The router's own consumer parse must survive schema additions."""
    res = json.loads(_run(rm._search(_Req({"kb_id": "kbc", "query": "CIP-007", "top_k": 4}))).body)
    for r in res["results"]:
        r["a_new_field_added_later"] = {"nested": 1}
    res["another_top_level_addition"] = 42
    snippets = context_inject._extract_snippets(res)
    assert isinstance(snippets, list)
    assert snippets and all(isinstance(s, str) for s in snippets)


def test_extract_snippets_error_dict_is_not_a_miss():
    """An error dict must be distinguishable from an empty result (P1.1 hole)."""
    assert context_inject._extract_snippets({"error": "kb_id and query required"}) == []
    assert context_inject._dispatch_outcome("rag", {"error": "boom"}, []) == "error"
    assert context_inject._dispatch_outcome("rag", {"results": []}, []) == "miss"
    assert context_inject._dispatch_outcome("rag", {"results": [{"text": "x"}]}, ["x"]) == "hit"


@pytest.mark.parametrize("tool,args", _CALLER_ARG_SHAPES)
def test_caller_arg_shapes_are_accepted(_kb, tmp_path, tool, args):
    _kb_id, src = _kb
    if tool == "kb_ingest":
        out = _run(rm._ingest(_Req({"kb_id": "kbargs", "source_dir": str(src)})))
        assert out.status_code == 200
        return
    handler = rm._search if tool == "kb_search" else rm._search_all
    out = _run(handler(_Req(args)))
    assert out.status_code == 200, json.loads(out.body)


def test_injector_sends_an_accepted_shape():
    """context_inject must not reintroduce the k / kb_id drift."""
    import inspect

    srccode = inspect.getsource(context_inject.inject_retrieved_context)
    assert '"top_k": _TOP_K' in srccode
    assert '"k": _TOP_K' not in srccode
