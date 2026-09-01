"""Portal 5 — Multimodal retrieval for the RAG MCP (replaces text-only retrieval).

TASK_RAG_VISUAL_OVERHAUL_V1 — the ComfyUI pattern: `kb_search` is multimodal by
default (RRF fusion of text-chunk and page-image retrieval), `kb_ingest` renders
PDF pages to images and embeds them alongside text chunks in one pass, and the
Qwen3-VL retrieval server replaces the RAG stack's use of the text embedder
(:8917) / reranker (:8925) *for retrieval*. Those shared servers stay up for
other subsystems (memory, the Bully ORG projection).

This module owns the `kb_ingest` / `kb_search` / `kb_search_all` routes. The
KB-lifecycle tools (`kb_list` / `kb_optimize` / `kb_versions` / `kb_restore`)
stay in `rag_mcp.py`. Tool contracts (args + response shapes) are preserved —
the multimodal behaviour is the new default backing, not a new interface.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import lancedb
import pyarrow as pa
from starlette.responses import JSONResponse

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
RAG_DIR = os.path.join(LANCE_DIR, "rag")
VL_URL = os.environ.get("VL_RETRIEVAL_URL", "http://localhost:8942")
VL_DIM = int(os.environ.get("VL_EMBEDDING_DIM", "2048"))
VL_EMBED_MAX_ITEMS = max(1, int(os.environ.get("VL_EMBED_MAX_ITEMS", "16")))
CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))
_MAX_PAGES = int(os.environ.get("RAG_MAX_PAGES", "500"))
_PAGES_DIR = Path(os.environ.get("RAG_PAGES_DIR", os.path.join(LANCE_DIR, "rag_pages")))
_RRF_K = 60

_db = None


def _get_db():
    global _db
    if _db is None:
        from portal.platform.lance_guard import require_lance_dir

        require_lance_dir(LANCE_DIR)
        os.makedirs(RAG_DIR, exist_ok=True)
        _db = lancedb.connect(RAG_DIR)
    return _db


def _meta_path(kb_id: str) -> str:
    """Sidecar recording which embedding model produced a KB's vectors (A3).
    A JSON file next to the LanceDB dir — no vector-table schema change."""
    return os.path.join(RAG_DIR, f"kb_{kb_id}.meta.json")


async def _vl_model_id() -> tuple[str, int]:
    """(embed_model, dim) the live VL server is serving. `_vl_embed_batch`
    already guards dim; this catches a same-dim different-model swap (the `-6bit`
    flavour, a re-conversion, a changed VL_EMBED_MODEL default) that stored
    vectors and live queries would otherwise silently occupy different spaces."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{VL_URL}/health")
            r.raise_for_status()
            j = r.json()
        return str(j.get("embed_model", "?")), int(j.get("embedding_dim", VL_DIM))
    except (httpx.HTTPError, ValueError) as e:
        raise _vl_error(e) from e


def _read_stamp(kb_id: str) -> dict | None:
    try:
        with open(_meta_path(kb_id)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_stamp(kb_id: str, embed_model: str, dim: int) -> None:
    with open(_meta_path(kb_id), "w") as fh:
        json.dump({"embed_model": embed_model, "vl_dim": dim, "stamped_at": time.time()}, fh)


def _assert_embedding_space(kb_id: str, live_model: str) -> None:
    """Raise if the KB was stamped with a different embedding model."""
    stamp = _read_stamp(kb_id)
    if stamp and stamp.get("embed_model") not in (None, "?", live_model):
        raise _VLUnavailableError(
            f"KB '{kb_id}' was embedded with '{stamp['embed_model']}' but the VL "
            f"server now serves '{live_model}'. Stored vectors and live queries "
            f"are in different spaces — re-run rag_multimodal.reindex_all()."
        )


def _tname(kb_id: str) -> str:
    return f"kb_{kb_id}"


def _vname(kb_id: str) -> str:
    return f"kb_{kb_id}_visual"


def _text_table(kb_id: str, create: bool = False):
    db = _get_db()
    name = _tname(kb_id)
    if name in db.table_names():
        return db.open_table(name)
    if not create:
        return None
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("kb_id", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), VL_DIM)),
            pa.field("char_start", pa.int64()),
            pa.field("char_end", pa.int64()),
            pa.field("ingested_at", pa.float64()),
        ]
    )
    return db.create_table(name, schema=schema)


def _visual_table(kb_id: str, create: bool = False):
    db = _get_db()
    name = _vname(kb_id)
    if name in db.table_names():
        return db.open_table(name)
    if not create:
        return None
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("kb_id", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("page", pa.int64()),
            pa.field("image_path", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), VL_DIM)),
            pa.field("ingested_at", pa.float64()),
        ]
    )
    return db.create_table(name, schema=schema)


def _list_kbs() -> list[str]:
    return sorted(
        t[3:] for t in _get_db().table_names() if t.startswith("kb_") and not t.endswith("_visual")
    )


class _VLUnavailableError(Exception):
    """The VL retrieval server is not serving a working model (see :8942/ready)."""


def _vl_error(exc: Exception) -> _VLUnavailableError:
    detail = str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        with contextlib.suppress(Exception):
            detail = exc.response.json().get("error", exc.response.text)
    return _VLUnavailableError(f"VL retrieval server unavailable: {detail} (check {VL_URL}/ready)")


async def _vl_embed_batch(items: list[dict]) -> list[list[float]]:
    """items: list of {text?, image_path?, is_query?}. Instruction is applied
    server-side for is_query items only; chunk/page items carry none."""
    if not items:
        return []
    # Cap the POST body: a whole document's chunks (or every page image) in one
    # request is unbounded by construction. Split into <= VL_EMBED_MAX_ITEMS
    # requests, issued sequentially (the server serialises on one lock anyway),
    # and concatenate in order. The server also sub-chunks at VL_MAX_BATCH — the
    # two bounds are independent (request size vs. forward-pass memory).
    vecs: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            for start in range(0, len(items), VL_EMBED_MAX_ITEMS):
                batch = items[start : start + VL_EMBED_MAX_ITEMS]
                r = await c.post(f"{VL_URL}/embed_batch", json={"items": batch})
                r.raise_for_status()
                vecs.extend(r.json()["embeddings"])
    except httpx.HTTPError as e:
        raise _vl_error(e) from e
    for v in vecs:
        if len(v) != VL_DIM:
            raise _VLUnavailableError(f"VL embedding dim {len(v)} != VL_EMBEDDING_DIM {VL_DIM}")
    return vecs


async def _vl_embed(text: str | None = None, image_path: str | None = None, is_query: bool = False):
    item: dict = {"is_query": is_query}
    if text:
        item["text"] = text
    if image_path:
        item["image_path"] = image_path
    return (await _vl_embed_batch([item]))[0]


async def _vl_rerank(query: str, candidates: list, top_n: int) -> list:
    """candidates: list of {text?, image_path?}. One call; the server chunks it
    at VL_RERANK_CHUNK. Returns [{index, score}] ordered best-first."""
    try:
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{VL_URL}/rerank",
                json={"query": {"text": query}, "documents": candidates, "top_n": top_n},
            )
            r.raise_for_status()
            return r.json()["results"]
    except httpx.HTTPError as e:
        raise _vl_error(e) from e


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    out, i = [], 0
    while i < len(text):
        seg = text[i : i + size]
        if seg.strip():
            out.append((i, i + len(seg), seg))
        i += max(1, size - overlap)
    return out


def _render_pages(pdf_path: str, out_dir: Path, dpi: int = 150) -> list:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    doc = pymupdf.open(pdf_path)
    for i, page in enumerate(doc):
        if i >= _MAX_PAGES:
            break
        p = out_dir / f"{Path(pdf_path).stem}_p{i:04d}.png"
        page.get_pixmap(dpi=dpi).save(str(p))
        pages.append((i, str(p)))
    doc.close()
    return pages


async def _read_text(path: Path) -> str:
    """Reuse rag_mcp's docling extraction; fall back to plain read for text."""
    from portal.modules.research.tools import rag_mcp

    reader = getattr(rag_mcp, "_read_file", None)
    if reader is not None:
        with contextlib.suppress(Exception):
            return await reader(path)
    conv = getattr(rag_mcp, "_docling_convert", None)
    if conv is not None:
        with contextlib.suppress(Exception):
            return conv(path)
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(errors="ignore")
    return ""


async def _ingest_text(ttbl, kb_id: str, f: Path, rel: str) -> int:
    text = await _read_text(f)
    chunks = list(_chunk(text))
    if not chunks:
        return 0
    vecs = await _vl_embed_batch([{"text": ct} for _, _, ct in chunks])
    rows = [
        {
            "chunk_id": hashlib.sha1(f"{kb_id}|{f}|{idx}".encode()).hexdigest(),
            "kb_id": kb_id,
            "source_file": rel,
            "chunk_index": idx,
            "text": ct,
            "vector": vec,
            "char_start": cs,
            "char_end": ce,
            "ingested_at": time.time(),
        }
        for idx, ((cs, ce, ct), vec) in enumerate(zip(chunks, vecs, strict=True))
    ]
    ttbl.add(rows)
    return len(rows)


async def _ingest_pages(vtbl, kb_id: str, f: Path, rel: str) -> int:
    pages = _render_pages(str(f), _PAGES_DIR / kb_id)
    if not pages:
        return 0
    vecs = await _vl_embed_batch([{"image_path": img} for _, img in pages])
    rows = [
        {
            "chunk_id": hashlib.sha1(f"{kb_id}|{f}|p{page_no}".encode()).hexdigest(),
            "kb_id": kb_id,
            "source_file": rel,
            "page": page_no,
            "image_path": img,
            "vector": vec,
            "ingested_at": time.time(),
        }
        for (page_no, img), vec in zip(pages, vecs, strict=True)
    ]
    vtbl.add(rows)
    return len(rows)


# ── Routes (contract-preserving, multimodal-backed) ─────────────────────────
async def _ingest(request):
    """kb_ingest: ingest a source directory. Text chunks (VL-embedded) + rendered
    PDF pages (VL-embedded) in one pass. Contract-preserved:
    args {kb_id, source_dir, rebuild, fts}, response
    {kb_id, files_ingested, chunks_added, pages_added, fts_index}."""
    args = (await request.json()).get("arguments", {})
    kb_id = args.get("kb_id", "")
    source_dir = args.get("source_dir", "")
    rebuild = args.get("rebuild", False)
    if not kb_id or not source_dir:
        return JSONResponse({"error": "kb_id and source_dir are required"}, status_code=400)
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return JSONResponse({"error": f"directory not found: {src}"}, status_code=404)
    try:
        live_model, live_dim = await _vl_model_id()
        if not rebuild:
            _assert_embedding_space(kb_id, live_model)
        if rebuild:
            db = _get_db()
            for name in (_tname(kb_id), _vname(kb_id)):
                if name in db.table_names():
                    with contextlib.suppress(Exception):
                        db.open_table(name).delete("chunk_id IS NOT NULL")
        ttbl = _text_table(kb_id, create=True)
        vtbl = None
        files = [
            f
            for f in src.rglob("*")
            if f.is_file()
            and f.suffix.lower()
            in (".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub")
        ][:5000]
        chunks_added = pages_added = 0
        for f in files:
            rel = str(f.relative_to(src))
            chunks_added += await _ingest_text(ttbl, kb_id, f, rel)
            if f.suffix.lower() == ".pdf":
                if vtbl is None:
                    vtbl = _visual_table(kb_id, create=True)
                pages_added += await _ingest_pages(vtbl, kb_id, f, rel)
        _write_stamp(kb_id, live_model, live_dim)
        return JSONResponse(
            {
                "kb_id": kb_id,
                "files_ingested": len(files),
                "chunks_added": chunks_added,
                "pages_added": pages_added,
                "fts_index": False,
            }
        )
    except _VLUnavailableError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


async def _search(request):
    """kb_search: default multimodal — RRF fusion of text-chunk and page-image
    retrieval. Contract-preserved: {kb_id, query, top_k}, response
    {kb_id, query, num_results, results:[{chunk_id, source_file, chunk_index,
    text, fused_score, reranker_prob, kind, page?}]}.

    `fused_score` is the RRF fusion value (was misnamed `rerank_score`).
    `reranker_prob` is the VL reranker's calibrated sigmoid(yes-no) probability
    for visual rows and null for text rows — carried through for P5's
    score-aware fusion work; the fusion itself is still rank-position RRF."""
    args = (await request.json()).get("arguments", {})
    kb_id = args.get("kb_id", "")
    query = args.get("query", "")
    top_k = min(int(args.get("top_k", 5)), 20)
    if not kb_id or not query:
        return JSONResponse({"error": "kb_id and query required"}, status_code=400)
    try:
        ttbl = _text_table(kb_id)
        vtbl = _visual_table(kb_id)
        if ttbl is None and vtbl is None:
            return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
        live_model, _ = await _vl_model_id()
        _assert_embedding_space(kb_id, live_model)
        qvec = await _vl_embed(text=query, is_query=True)
        scores: dict = {}
        payload: dict = {}
        if ttbl is not None:
            for rank, r in enumerate(ttbl.search(qvec).limit(top_k * 3).to_list()):
                key = ("text", r["chunk_id"])
                scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
                payload[key] = {
                    "chunk_id": r["chunk_id"],
                    "source_file": r["source_file"],
                    "chunk_index": r["chunk_index"],
                    "text": r["text"],
                    "kind": "text",
                    "reranker_prob": None,
                }
        if vtbl is not None:
            coarse = vtbl.search(qvec).limit(top_k * 3).to_list()
            cands = [{"image_path": r["image_path"]} for r in coarse]
            order = await _vl_rerank(query, cands, min(len(cands), top_k * 2)) if cands else []
            for rank, o in enumerate(order):
                r = coarse[o["index"]]
                key = ("visual", r["chunk_id"])
                scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
                payload[key] = {
                    "chunk_id": r["chunk_id"],
                    "source_file": r["source_file"],
                    "chunk_index": r["page"],
                    "page": r["page"],
                    "text": f"[page image {r['source_file']} p{r['page']}]",
                    "kind": "visual",
                    "reranker_prob": round(float(o["score"]), 5),
                }
        fused = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        results = [{**payload[k], "fused_score": round(s, 5)} for k, s in fused]
        return JSONResponse(
            {"kb_id": kb_id, "query": query, "num_results": len(results), "results": results}
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=503)


async def _search_all(request):
    """kb_search_all: multimodal search across all KBs. Contract-preserved:
    {query, top_k}, response {query, num_results, results:[{kb_id, source_file,
    text, fused_score, kind}]}."""
    args = (await request.json()).get("arguments", {})
    query = args.get("query", "")
    top_k = min(int(args.get("top_k", 5)), 30)
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    try:
        merged: list = []
        for kb_id in _list_kbs():

            class _R:
                async def json(self, _kb=kb_id):
                    return {"arguments": {"kb_id": _kb, "query": query, "top_k": max(top_k, 3)}}

            import json as _json

            body = _json.loads((await _search(_R())).body)
            for r in body.get("results", []):
                r["kb_id"] = kb_id
                merged.append(r)
        merged.sort(key=lambda r: -r.get("fused_score", 0))
        merged = merged[:top_k]
        return JSONResponse({"query": query, "num_results": len(merged), "results": merged})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=503)


async def reindex_all() -> dict:
    """In-task migration: re-embed every existing KB's text with the VL model
    (the old tables are 1024-d; VL is VL_DIM, so tables are recreated)."""
    db = _get_db()
    live_model, live_dim = await _vl_model_id()
    done: dict = {}
    for t in [x for x in db.table_names() if x.startswith("kb_") and not x.endswith("_visual")]:
        kb_id = t[3:]
        rows = db.open_table(t).search().limit(1_000_000).to_list()
        old_name = t
        with contextlib.suppress(Exception):
            db.drop_table(old_name)
        new = _text_table(kb_id, create=True)
        keep = [r for r in rows if r.get("text")]
        vecs = await _vl_embed_batch([{"text": r["text"]} for r in keep])
        buf = [
            {
                "chunk_id": r.get("chunk_id", hashlib.sha1(r["text"].encode()).hexdigest()),
                "kb_id": kb_id,
                "source_file": r.get("source_file", ""),
                "chunk_index": int(r.get("chunk_index", 0)),
                "text": r["text"],
                "vector": vec,
                "char_start": int(r.get("char_start", 0)),
                "char_end": int(r.get("char_end", 0)),
                "ingested_at": r.get("ingested_at", time.time()),
            }
            for r, vec in zip(keep, vecs, strict=True)
        ]
        if buf:
            new.add(buf)
        _write_stamp(kb_id, live_model, live_dim)
        done[kb_id] = len(buf)
    return {"reindexed_kbs": done}


def register_retrieval_routes(mcp) -> None:
    """Own the kb_* retrieval routes with the multimodal implementation."""
    mcp.custom_route("/tools/kb_ingest", methods=["POST"])(_ingest)
    mcp.custom_route("/tools/kb_search", methods=["POST"])(_search)
    mcp.custom_route("/tools/kb_search_all", methods=["POST"])(_search_all)
