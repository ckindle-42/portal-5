"""P7 acceptance: the compliance composition is a real second consumer of the
shared retrieval stages, writing to disjoint tables, with zero effect on `kb_*`.

TASK_RAG_COMPOSITION_SEAM_V1 Phase 7 — "that last check is the whole point of the
task expressed as a test."
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")

cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")

_store = importlib.import_module("portal.platform.retrieval.store")

_embedding = importlib.import_module("portal.platform.retrieval.embedding")


@pytest.fixture(autouse=True)
def _temp_dirs_are_allowed_roots(monkeypatch):
    """These tests ingest from temporary directories; allow exactly those (PORTAL5_KB_INGEST_ROOTS).
    Production confines ingest to configured roots (N-28)."""
    import tempfile
    from pathlib import Path

    monkeypatch.setenv("PORTAL5_KB_INGEST_ROOTS", tempfile.gettempdir())
    # compliance_ingest's roots (N-33) are the data dir and the profile; allow temp here too.
    monkeypatch.setattr(
        cr, "_compliance_ingest_roots", lambda: [Path(tempfile.gettempdir()).resolve()]
    )


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


def test_compliance_composition_forces_docling_chunking_and_bm25():
    """P1 / Y25: the compliance composition — and ONLY it — carries docling
    chunking (heading path + page) and the BM25 sparse arm. The module-global
    CHUNK_STRATEGY and rag_multimodal's composition are untouched."""
    comp = cr._composition()
    assert comp.fts is True
    assert comp.contextualize is True
    assert comp.stage_set["chunk_strategy"] == "docling"
    assert comp.stage_set["fts"] is True
    # rag_multimodal stays on the global default
    rag_comp = rm._composition() if hasattr(rm, "_composition") else None
    if rag_comp is not None:
        assert rag_comp.fts is False or rag_comp.stage_set.get("fts") in (False, None)
    # the global is not flipped
    _chunking = importlib.import_module("portal.platform.retrieval.chunking")
    assert _chunking.CHUNK_STRATEGY == "fixed"
