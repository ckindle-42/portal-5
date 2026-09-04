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
from pathlib import Path

from starlette.responses import JSONResponse

from portal.platform.retrieval import chunking as _chunking
from portal.platform.retrieval import embedding as _embedding
from portal.platform.retrieval import extraction as _extraction
from portal.platform.retrieval import fusion as _fusion
from portal.platform.retrieval import pages as _pages
from portal.platform.retrieval import pipeline as _pipeline
from portal.platform.retrieval import store as _store

_PREFIX = "compliance_"
_PAGES_DIR = Path(
    os.environ.get("COMPLIANCE_PAGES_DIR", os.path.join(_store.LANCE_DIR, "compliance_pages"))
)


async def _no_transcribe(_img_path: str) -> str:
    """S0 figure transcription is off for the compliance composition (P7)."""
    return ""


def _stage_set() -> dict:
    return {
        "chunk_strategy": _chunking.CHUNK_STRATEGY,
        "chunk_size": _chunking.CHUNK_SIZE,
        "chunk_overlap": _chunking.CHUNK_OVERLAP,
        "figure_page_max_text": _pages.FIGURE_PAGE_MAX_TEXT,
        "transcribe_figures": False,
        # fusion_mode dropped — search-time, not an index-building stage
        # (SUBSTRATE_MIGRATION_V1 P3).
        "visual_scope": _pages.VISUAL_SCOPE,
        "contextualize": False,
        "fts": False,
    }


def _composition() -> _pipeline.Composition:
    """Same stages as ``rag_multimodal``, bound to the ``compliance_`` prefix."""
    pfx = {"prefix": _PREFIX}
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
        chunk=_chunking.chunk,
        read_text=_extraction.read_text,
        render_pages=_pages.render_pages,
        figure_pages=_pages.figure_pages,
        transcribe_page=_no_transcribe,
        pages_dir=_PAGES_DIR,
        fusion_mode=_fusion.FUSION,
        transcribe_figures=False,
        table_prefix=_PREFIX,
        stage_set=_stage_set(),
    )


async def search(kb_id: str, query: str, top_k: int = 5) -> dict:
    """Plain-arg entry point — the HTTP concern (request parsing, status codes)
    stays in ``_search`` below; ``compliance_mcp``'s sync dispatch wrapper calls
    this directly (pipeline.py's own separation, P3)."""
    return await _pipeline.search(_composition(), kb_id, query, min(int(top_k), 20))


async def _search(request):
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


async def _ingest(request):
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


def register_compliance_retrieval_routes(mcp) -> None:
    """Own the compliance_* retrieval routes on the compliance MCP."""
    mcp.custom_route("/tools/compliance_ingest", methods=["POST"])(_ingest)
    mcp.custom_route("/tools/compliance_search", methods=["POST"])(_search)
