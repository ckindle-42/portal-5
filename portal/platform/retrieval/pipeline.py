"""Retrieval pipeline — the composition (SEAM V1 P3).

``rag_multimodal`` is one composition of the stage library; the compliance
engine (P7) is a second. A ``Composition`` bundles the store accessors, the VL
service client, the content stages, and the tuning config; the four entry
points — ``ingest_document`` / ``search`` / ``search_all`` / ``reindex`` — are
free functions over it.

The bodies are lifted verbatim from ``rag_multimodal``'s ``_ingest`` / ``_search``
/ ``_search_all`` / ``reindex_all``. What changed:

* the HTTP concern (parse ``request.json()``, wrap in ``JSONResponse``, map
  errors to 503/500/404) stays in the route handlers — these functions take
  plain args and either return a dict or raise;
* ``UnknownKBError`` is raised where ``_search`` returned an in-body 404;
* ``search_all`` swallows a per-KB failure to ``[]`` exactly as the old code did
  (it parsed ``_search``'s own 503 body and read ``results`` as missing).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from portal.platform.retrieval import fusion as _fusion

_DEFAULT_SUFFIXES = (
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".epub",
)


class UnknownKBError(Exception):
    """No text or visual table exists for the requested kb_id."""

    def __init__(self, kb_id: str):
        super().__init__(f"unknown kb_id '{kb_id}'")
        self.kb_id = kb_id


@dataclass
class Composition:
    """One wiring of the retrieval stages. ``rag_multimodal`` builds the default;
    a second consumer builds its own with different tables / config."""

    name: str
    # store
    get_db: Callable[[], Any]
    text_table: Callable[..., Any]
    visual_table: Callable[..., Any]
    tname: Callable[[str], str]
    vname: Callable[[str], str]
    list_kbs: Callable[[], list[str]]
    read_stamp: Callable[[str], dict | None]
    write_stamp: Callable[..., None]
    assert_embedding_space: Callable[..., None]
    # embedding service
    vl_model_id: Callable[[], Awaitable[tuple[str, int]]]
    vl_embed: Callable[..., Awaitable[list]]
    vl_embed_batch: Callable[[list], Awaitable[list]]
    vl_rerank: Callable[[str, list, int], Awaitable[list]]
    unavailable_error: type[BaseException]
    # content stages
    chunk: Callable[[str], list]
    read_text: Callable[[Path], Awaitable[str]]
    render_pages: Callable[..., list]
    figure_pages: Callable[[list], list]
    transcribe_page: Callable[[str], Awaitable[str]]
    # config
    pages_dir: Path
    fusion_mode: str = "text_gate"
    transcribe_figures: bool = False
    table_prefix: str = "kb_"
    file_suffixes: tuple[str, ...] = _DEFAULT_SUFFIXES
    stage_set: dict = field(default_factory=dict)


# ── ingest ────────────────────────────────────────────────────────────────────
async def _ingest_text(comp: Composition, ttbl, kb_id: str, f: Path, rel: str) -> int:
    text = await comp.read_text(f)
    chunks = list(comp.chunk(text))
    if not chunks:
        return 0
    vecs = await comp.vl_embed_batch([{"text": ct} for _, _, ct in chunks])
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


async def _ingest_pages(comp: Composition, vtbl, kb_id: str, f: Path, rel: str) -> tuple[int, list]:
    pages = comp.render_pages(str(f), comp.pages_dir / kb_id)
    if not pages:
        return 0, []
    vecs = await comp.vl_embed_batch([{"image_path": img} for _, img in pages])
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
    return len(rows), pages


async def _ingest_page_transcripts(
    comp: Composition, ttbl, kb_id: str, f: Path, rel: str, pages: list
) -> int:
    figures = comp.figure_pages(pages)
    if not figures:
        return 0
    transcripts = [(pn, await comp.transcribe_page(img)) for pn, img in figures]
    keep = [(pn, t) for pn, t in transcripts if t]
    if not keep:
        return 0
    vecs = await comp.vl_embed_batch([{"text": t} for _, t in keep])
    rows = [
        {
            "chunk_id": hashlib.sha1(f"{kb_id}|{f}|figtext|p{pn}".encode()).hexdigest(),
            "kb_id": kb_id,
            "source_file": rel,
            "chunk_index": -1000 - pn,  # marks a figure transcript, not a prose chunk
            "text": f"[figure transcript, {rel} p{pn}]\n{t}",
            "vector": vec,
            "char_start": 0,
            "char_end": len(t),
            "ingested_at": time.time(),
        }
        for (pn, t), vec in zip(keep, vecs, strict=True)
    ]
    ttbl.add(rows)
    return len(rows)


async def ingest_document(comp: Composition, kb_id: str, source_dir: Path, rebuild: bool) -> dict:
    """Text chunks + rendered PDF pages (+ figure transcripts) in one pass.
    Returns the kb_ingest response dict; raises ``comp.unavailable_error`` or
    any other exception for the handler to map."""
    import contextlib

    live_model, live_dim = await comp.vl_model_id()
    if not rebuild:
        comp.assert_embedding_space(kb_id, live_model, comp.stage_set or None)
    if rebuild:
        db = comp.get_db()
        for name in (comp.tname(kb_id), comp.vname(kb_id)):
            if name in db.table_names():
                with contextlib.suppress(Exception):
                    db.open_table(name).delete("chunk_id IS NOT NULL")
    ttbl = comp.text_table(kb_id, create=True)
    vtbl = None
    files = [
        f for f in source_dir.rglob("*") if f.is_file() and f.suffix.lower() in comp.file_suffixes
    ][:5000]
    chunks_added = pages_added = figtext_added = 0
    for f in files:
        rel = str(f.relative_to(source_dir))
        chunks_added += await _ingest_text(comp, ttbl, kb_id, f, rel)
        if f.suffix.lower() == ".pdf":
            if vtbl is None:
                vtbl = comp.visual_table(kb_id, create=True)
            n_pages, pages = await _ingest_pages(comp, vtbl, kb_id, f, rel)
            pages_added += n_pages
            if comp.transcribe_figures and pages:
                figtext_added += await _ingest_page_transcripts(comp, ttbl, kb_id, f, rel, pages)
    comp.write_stamp(kb_id, live_model, live_dim, comp.stage_set or None)
    return {
        "kb_id": kb_id,
        "files_ingested": len(files),
        "chunks_added": chunks_added,
        "pages_added": pages_added,
        "figtext_added": figtext_added,
        "fts_index": False,
    }


# ── search ────────────────────────────────────────────────────────────────────
async def search(comp: Composition, kb_id: str, query: str, top_k: int) -> dict:
    """RRF (or unified) fusion of text-chunk and page-image retrieval. Returns
    the kb_search response dict; raises ``UnknownKBError`` for a missing table and
    propagates VL errors."""
    ttbl = comp.text_table(kb_id)
    vtbl = comp.visual_table(kb_id)
    if ttbl is None and vtbl is None:
        raise UnknownKBError(kb_id)
    live_model, _ = await comp.vl_model_id()
    comp.assert_embedding_space(kb_id, live_model, comp.stage_set or None)
    qvec = await comp.vl_embed(text=query, is_query=True)
    results = await _fusion.fuse(comp.fusion_mode, ttbl, vtbl, query, qvec, top_k, comp.vl_rerank)
    return {"kb_id": kb_id, "query": query, "num_results": len(results), "results": results}


async def search_all(comp: Composition, query: str, top_k: int) -> dict:
    merged: list = []
    for kb_id in comp.list_kbs():
        try:
            body = await search(comp, kb_id, query, max(top_k, 3))
        except Exception:  # noqa: BLE001 — matches the old per-KB-swallow behaviour
            body = {"results": []}
        for r in body.get("results", []):
            r["kb_id"] = kb_id
            merged.append(r)
    merged.sort(key=lambda r: -r.get("fused_score", 0))
    merged = merged[:top_k]
    return {"query": query, "num_results": len(merged), "results": merged}


# ── reindex ───────────────────────────────────────────────────────────────────
async def reindex(comp: Composition) -> dict:
    """Re-embed every existing KB's text with the current VL model."""
    import contextlib

    db = comp.get_db()
    live_model, live_dim = await comp.vl_model_id()
    done: dict = {}
    plen = len(comp.table_prefix)
    for t in [
        x for x in db.table_names() if x.startswith(comp.table_prefix) and not x.endswith("_visual")
    ]:
        kb_id = t[plen:]
        rows = db.open_table(t).search().limit(1_000_000).to_list()
        with contextlib.suppress(Exception):
            db.drop_table(t)
        new = comp.text_table(kb_id, create=True)
        keep = [r for r in rows if r.get("text")]
        vecs = await comp.vl_embed_batch([{"text": r["text"]} for r in keep])
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
        comp.write_stamp(kb_id, live_model, live_dim, comp.stage_set or None)
        done[kb_id] = len(buf)
    return {"reindexed_kbs": done}
