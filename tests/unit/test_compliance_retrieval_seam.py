"""P7 acceptance: the compliance composition is a real second consumer of the
shared retrieval stages, writing to disjoint tables, with zero effect on `kb_*`.

TASK_RAG_COMPOSITION_SEAM_V1 Phase 7 — "that last check is the whole point of the
task expressed as a test."
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")
cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")


class _Req:
    def __init__(self, a):
        self._a = {"arguments": a}

    async def json(self):
        return self._a


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", 8)
    monkeypatch.setattr(rm, "_PAGES_DIR", tmp_path / "kb_pages")
    monkeypatch.setattr(cr, "_PAGES_DIR", tmp_path / "compliance_pages")
    _store._db = None

    async def _emb(text=None, image_path=None, is_query=False):
        return [0.1] * 8

    async def _emb_batch(items):
        return [[0.1] * 8 for _ in items]

    async def _rr(q, cands, n):
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]

    async def _model_id():
        return ("fake-vl-model", 8)

    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)

    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")

    async def _read_file(p):
        return "PLC-21 one-line diagram governed by CIP-007-6 R2. " * 20

    fake._read_file = _read_file
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)


@pytest.fixture
def _corpus(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("Requirement R2.1 patch management for CIP-007-6.")
    (src / "b.md").write_text("The ESP review cadence is 15 calendar months.")
    return src


def _rows(table_name):
    db = _store.get_db()
    return sorted(
        db.open_table(table_name).search().limit(10_000).to_list(),
        key=lambda r: r["chunk_id"],
    )


def _stable(rows):
    return [
        {
            "chunk_id": r["chunk_id"],
            "source_file": r["source_file"],
            "text": r["text"],
            "vector": list(r["vector"]),
        }
        for r in rows
    ]


def test_disjoint_tables_and_equivalent_results(_corpus):
    rm_out = json.loads(_run(rm._ingest(_Req({"kb_id": "x", "source_dir": str(_corpus)}))).body)
    cr_out = json.loads(_run(cr._ingest(_Req({"kb_id": "x", "source_dir": str(_corpus)}))).body)
    assert rm_out["chunks_added"] == cr_out["chunks_added"] >= 1

    names = set(_store.get_db().table_names())
    assert {"kb_x", "compliance_x"} <= names
    assert "compliance_x" not in {"kb_x", "kb_x_visual"}

    # same corpus, same (fake) embeddings -> the two arms return the same texts
    q = {"kb_id": "x", "query": "patch management requirement", "top_k": 3}
    rm_res = json.loads(_run(rm._search(_Req(q))).body)["results"]
    cr_res = json.loads(_run(cr._search(_Req(q))).body)["results"]
    assert [r["text"] for r in rm_res] == [r["text"] for r in cr_res]
    assert [r["kind"] for r in rm_res] == [r["kind"] for r in cr_res]

    # disjoint stamps
    assert _store.read_stamp("x", prefix="kb_") is not None
    assert _store.read_stamp("x", prefix="compliance_") is not None


def test_compliance_rebuild_leaves_kb_tables_byte_identical(_corpus):
    _run(rm._ingest(_Req({"kb_id": "x", "source_dir": str(_corpus)})))
    _run(cr._ingest(_Req({"kb_id": "x", "source_dir": str(_corpus)})))

    before = _stable(_rows("kb_x"))
    before_stamp = _store.read_stamp("x", prefix="kb_")

    out = json.loads(
        _run(cr._ingest(_Req({"kb_id": "x", "source_dir": str(_corpus), "rebuild": True}))).body
    )
    assert "error" not in out

    assert _stable(_rows("kb_x")) == before
    assert _store.read_stamp("x", prefix="kb_") == before_stamp
