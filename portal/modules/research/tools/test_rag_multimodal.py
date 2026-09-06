"""Acceptance: multimodal search is default; ingest indexes text (+visual); contracts intact."""

import asyncio
import importlib
import json
import sys
import types
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")


class _Req:
    def __init__(self, a: Any) -> None:
        self._a: dict[str, Any] = {"arguments": a}

    async def json(self) -> dict[str, Any]:
        return self._a


def _run[R](c: Awaitable[R]) -> R:
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SEAM V1: the store + VL client are the stage library; patch them there.
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", 8)
    monkeypatch.setattr(rm, "_PAGES_DIR", tmp_path / "pages")
    monkeypatch.setattr(_store, "_db", None)

    async def _emb(
        text: str | None = None, image_path: str | None = None, is_query: bool = False
    ) -> list[float]:
        return [0.1] * 8

    async def _emb_batch(items: list[Any]) -> list[list[float]]:
        return [[0.1] * 8 for _ in items]

    async def _rr(q: str, cands: list[Any], n: int) -> list[dict[str, Any]]:
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]

    async def _model_id() -> tuple[str, int]:
        return ("fake-vl-model", 8)

    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    # a fake rag_mcp so docling isn't required
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")

    async def _read_file(p: Path) -> str:
        return "PLC-21 one-line diagram governed by CIP-007. " * 30

    fake.__dict__["_read_file"] = _read_file
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)


def test_registration_owns_retrieval_routes() -> None:
    calls: list[str] = []

    class F:
        def custom_route(
            self, p: str, methods: list[str] | None = None
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def d(fn: Callable[..., Any]) -> Callable[..., Any]:
                calls.append(p)
                return fn

            return d

    rm.register_retrieval_routes(F())
    assert set(calls) == {"/tools/kb_ingest", "/tools/kb_search", "/tools/kb_search_all"}


def test_ingest_then_search_contract(tmp_path: Path) -> None:
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
    assert all("fused_score" in r and "text" in r for r in res["results"])
    assert res["results"][0]["kind"] == "text"


def test_search_unknown_kb_is_404() -> None:
    out = _run(rm._search(_Req({"kb_id": "nope", "query": "q"})))
    assert out.status_code == 404


def test_search_all_contract(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    src = tmp_path / "s"
    src.mkdir()
    (src / "a.md").write_text("y")
    _run(rm._ingest(_Req({"kb_id": "kba", "source_dir": str(src)})))
    res = json.loads(_run(rm._search_all(_Req({"query": "CIP-007"}))).body)
    assert {"query", "num_results", "results"} <= set(res)


def test_ingest_stamps_model_and_search_rejects_a_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A3: kb_ingest records the embedding model; a later same-dim model swap is
    caught at kb_search instead of degrading silently."""
    pytest.importorskip("lancedb")
    src = tmp_path / "kbsrc"
    src.mkdir()
    (src / "d.txt").write_text("x")
    _run(rm._ingest(_Req({"kb_id": "kbz", "source_dir": str(src)})))
    assert _store.read_stamp("kbz")["embed_model"] == "fake-vl-model"

    async def _swapped() -> tuple[str, int]:
        return ("different-vl-model", 8)

    monkeypatch.setattr(_embedding, "vl_model_id", _swapped)
    out = _run(rm._search(_Req({"kb_id": "kbz", "query": "x"})))
    body = json.loads(out.body)
    assert out.status_code == 503 and "different spaces" in body["error"]
