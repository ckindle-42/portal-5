"""Compliance retrieval — the second composition (TASK_RAG_COMPOSITION_SEAM_V1 P7).

This proves the seam: a consumer other than ``rag_multimodal`` composes the same
`portal.platform.retrieval` stages with its own routes and its own tables. It has
**no compliance semantics** — no register, no authority tiers, no coverage
matrix; those are `TASK_COMPLIANCE_ENGINE`, which lands on this scaffold.

What makes the two lifecycles independent: the tables are namespaced
``compliance_*`` (vs ``kb_*``), so a compliance re-ingest can never touch another
consumer's index, and the stamp sidecar is prefixed the same way. Everything
else — the VL client, chunking, page rendering, extraction, fusion, the pipeline
entry points, `require_lance_dir` — is the shared stage library, unchanged.
"""

from __future__ import annotations

import functools
import os

# The compliance composition forces docling chunking so every chunk carries a
# heading path and page (an operator answer must cite section + page), and
# enables the BM25 sparse arm so an exact requirement ID resolves lexically
# even when it is out-of-distribution for the dense embedder
# (TASK_COMPLIANCE_REASONING_V6 P1 / Y25). Both are set ONLY on this
# composition — the module-global CHUNK_STRATEGY and every other consumer's
# index are untouched.
_COMPLIANCE_CHUNK_STRATEGY = "docling"
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from portal.platform.retrieval import chunking as _chunking
from portal.platform.retrieval import embedding as _embedding
from portal.platform.retrieval import extraction as _extraction
from portal.platform.retrieval import fusion as _fusion
from portal.platform.retrieval import pages as _pages
from portal.platform.retrieval import pipeline as _pipeline
from portal.platform.retrieval import store as _store

# The DoclingDocument source. Bound to a name so `_stage_set` can record whether
# the docling chunker is actually REACHABLE, not merely requested (Y25).
_READ_DOCUMENT = _extraction.read_document

_PREFIX = "compliance_"
_PAGES_DIR = Path(
    os.environ.get("COMPLIANCE_PAGES_DIR", os.path.join(_store.LANCE_DIR, "compliance_pages"))
)


async def _no_transcribe(_img_path: str) -> str:
    """S0 figure transcription is off for the compliance composition (P7)."""
    return ""


def _stage_set() -> dict[str, Any]:
    return {
        "chunk_size": _chunking.CHUNK_SIZE,
        "chunk_overlap": _chunking.CHUNK_OVERLAP,
        "figure_page_max_text": _pages.FIGURE_PAGE_MAX_TEXT,
        "transcribe_figures": False,
        # fusion_mode dropped — search-time, not an index-building stage
        # (SUBSTRATE_MIGRATION_V1 P3).
        # compliance answers live in prose and tables, never diagrams — index
        # only real embedded figures, not full-page renders, so a text-less
        # page image can never outrank a prose answer (prose-cip-07 / Y25).
        "visual_scope": "figures",
        "contextualize": True,
        "chunk_strategy": _COMPLIANCE_CHUNK_STRATEGY,
        # Y25 (2026-09-12): `chunk_strategy` records what the composition ASKS
        # for, and for a year it asked for docling and silently got fixed
        # slicing — so every KB carried a "docling" stamp it had not earned and
        # no drift check could see it. This records what the composition can
        # actually DO: the layout-aware chunker needs a DoclingDocument, which
        # only `read_document` supplies. Two KBs that differ here differ in
        # their chunks, so the stamp comparison now catches it. Adding the key
        # deliberately marks every pre-fix compliance KB stale — they were
        # fixed-sliced and DO need re-ingesting.
        "chunker_effective": (
            "docling"
            if (_COMPLIANCE_CHUNK_STRATEGY == "docling" and _READ_DOCUMENT is not None)
            else "fixed"
        ),
        "fts": True,
    }


def _composition() -> _pipeline.Composition:
    """Same stages as ``rag_multimodal``, bound to the ``compliance_`` prefix."""
    pfx: dict[str, Any] = {"prefix": _PREFIX}
    return _pipeline.Composition(
        name="compliance_retrieval",
        get_db=_store.get_db,
        text_table=functools.partial(_store.text_table, **pfx),
        visual_table=functools.partial(_store.visual_table, **pfx),
        tname=functools.partial(_store.tname, **pfx),
        vname=functools.partial(_store.vname, **pfx),
        list_kbs=functools.partial(_store.list_kbs, **pfx),
        read_stamp=functools.partial(_store.read_stamp, **pfx),
        write_stamp=functools.partial(_store.write_stamp, **pfx),
        assert_embedding_space=functools.partial(_store.assert_embedding_space, **pfx),
        vl_model_id=_embedding.vl_model_id,
        vl_embed=_embedding.vl_embed,
        vl_embed_batch=_embedding.vl_embed_batch,
        vl_rerank=_embedding.vl_rerank,
        unavailable_error=_embedding.VLUnavailableError,
        chunk=functools.partial(_chunking.chunk, strategy=_COMPLIANCE_CHUNK_STRATEGY),
        read_text=_extraction.read_text,
        # Y25 root cause, found 2026-09-12. `chunk(strategy="docling")` uses the
        # layout-aware HybridChunker ONLY when it is handed a DoclingDocument;
        # with `doc=None` it silently falls back to `chunk_fixed`, which is blind
        # character slicing and hardcodes page=-1 / headings="". This composition
        # declared `chunk_strategy: "docling"` in its stage_set and set
        # `contextualize=True` ("embed heading path + text") but never supplied
        # `read_document`, so `doc` was always None: every chunk in every
        # compliance KB was fixed-sliced with an empty heading path, and
        # contextualize had nothing to contextualize. Measured on the 14-PDF CIP
        # corpus before the fix: 1508/1508 chunks at page=-1 with headings="".
        read_document=_READ_DOCUMENT,
        render_pages=_pages.render_pages,
        figure_pages=_pages.figure_pages,
        transcribe_page=_no_transcribe,
        pages_dir=_PAGES_DIR,
        fusion_mode=_fusion.FUSION,
        transcribe_figures=False,
        table_prefix=_PREFIX,
        visual_scope="figures",  # prose/table corpus — no full-page-image chunks
        contextualize=True,  # embed heading path + text so a section cite resolves
        fts=True,  # BM25 sparse arm — an exact requirement ID has a lexical path
        stage_set=_stage_set(),
    )


async def search(kb_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    """Plain-arg entry point — the HTTP concern (request parsing, status codes)
    stays in ``_search`` below; ``compliance_mcp``'s sync dispatch wrapper calls
    this directly (pipeline.py's own separation, P3)."""
    return await _pipeline.search(_composition(), kb_id, query, min(int(top_k), 20))


async def _search(request: Request) -> JSONResponse:
    """compliance_search: same behaviour as kb_search, over the compliance_* tables."""
    args = (await request.json()).get("arguments", {})
    kb_id = args.get("kb_id", "")
    query = args.get("query", "")
    top_k = args.get("top_k", 5)
    if not kb_id or not query:
        return JSONResponse({"error": "kb_id and query required"}, status_code=400)
    try:
        return JSONResponse(await search(kb_id, query, top_k))
    except _pipeline.UnknownKBError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=503)


async def _ingest(request: Request) -> JSONResponse:
    """compliance_ingest: ingest a folder of policy AND procedure PDFs in one
    pass over the compliance_* tables — TASK_COMPLIANCE_ENGINE_LANDING_V1 P3.
    Beyond kb_ingest's chunk/embed, this derives layer (policy/procedure/
    evidence) and authority tier per document from its own self-description,
    queues every derivation (``document_tier``), and reports the layer census
    — a census with zero procedures means no coverage cell can reach FULL."""
    from portal.modules.compliance.core.ingest import ingest_folder

    args = (await request.json()).get("arguments", {})
    kb_id = args.get("kb_id", "operator_corpus")
    source_dir = args.get("source_dir", "")
    rebuild = args.get("rebuild", False)
    if not source_dir:
        return JSONResponse({"error": "source_dir is required"}, status_code=400)
    try:
        return JSONResponse(await ingest_folder(source_dir, kb_id, rebuild))
    except _embedding.VLUnavailableError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


def register_compliance_retrieval_routes(mcp: Any) -> None:
    """Own the compliance_* retrieval routes on the compliance MCP."""
    mcp.custom_route("/tools/compliance_ingest", methods=["POST"])(_ingest)
    mcp.custom_route("/tools/compliance_search", methods=["POST"])(_search)
