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

TASK_RAG_COMPOSITION_SEAM_V1: the retrieval substrate — chunking, page
rendering, extraction, the VL client, the LanceDB store, and fusion — lives in
`portal.platform.retrieval`. This module is one *composition* of those stages
(`_COMPOSITION`), byte-identical to its pre-seam behaviour, plus the route
handlers and the S0 figure-transcription step. The compliance engine is a
second composition. Substrate *behaviour* changes are a separate per-KB
migration — see `unit-platform-retrieval`.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from starlette.responses import JSONResponse

from portal.platform.retrieval import chunking as _chunking
from portal.platform.retrieval import embedding as _embedding
from portal.platform.retrieval import extraction as _extraction
from portal.platform.retrieval import fusion as _fusion
from portal.platform.retrieval import pages as _pages
from portal.platform.retrieval import pipeline as _pipeline
from portal.platform.retrieval import store as _store

# ── Thin aliases over the stage library ────────────────────────────────────────
# Kept so existing references, tests, and the per-KB profile probe resolve
# unchanged through the transition. `scripts/rag_retrieval_eval.py` also reaches
# in through these. The rope is cut in P5.
LANCE_DIR = _store.LANCE_DIR
RAG_DIR = _store.RAG_DIR
VL_URL = _embedding.VL_URL
VL_DIM = _embedding.VL_DIM
VL_EMBED_MAX_ITEMS = _embedding.VL_EMBED_MAX_ITEMS
VL_TEXT_GATE = _fusion.VL_TEXT_GATE
VL_TEXT_GATE_MODE = _fusion.VL_TEXT_GATE_MODE
VL_TEXT_MARGIN = _fusion.VL_TEXT_MARGIN
VL_RERANK_DEPTH = _fusion.VL_RERANK_DEPTH
FUSION = _fusion.FUSION
UNIFIED_TEXT_DEPTH = _fusion.UNIFIED_TEXT_DEPTH
CHUNK_SIZE = _chunking.CHUNK_SIZE
CHUNK_OVERLAP = _chunking.CHUNK_OVERLAP
CHUNK_STRATEGY = _chunking.CHUNK_STRATEGY
FIGURE_PAGE_MAX_TEXT = _pages.FIGURE_PAGE_MAX_TEXT
_MAX_PAGES = _pages.MAX_PAGES
_RRF_K = _fusion.RRF_K
_PAGES_DIR = Path(os.environ.get("RAG_PAGES_DIR", os.path.join(LANCE_DIR, "rag_pages")))

_SECTION_BOUNDARY = _chunking.SECTION_BOUNDARY
_chunk_fixed = _chunking.chunk_fixed
_chunk_structured = _chunking.chunk_structured
_chunk = _chunking.chunk
_render_pages = _pages.render_pages
_figure_pages = _pages.figure_pages
_PAGE_TEXT_LEN = _pages._PAGE_TEXT_LEN
_read_text = _extraction.read_text

_VLUnavailableError = _embedding.VLUnavailableError
_vl_error = _embedding.vl_error
_vl_model_id = _embedding.vl_model_id
_vl_embed_batch = _embedding.vl_embed_batch
_vl_embed = _embedding.vl_embed
_vl_rerank = _embedding.vl_rerank
_text_arm_is_unconfident = _fusion.text_arm_is_unconfident
_search_unified = _fusion.search_unified

_get_db = _store.get_db
_meta_path = _store.meta_path
_read_stamp = _store.read_stamp
_write_stamp = _store.write_stamp
_assert_embedding_space = _store.assert_embedding_space
_tname = _store.tname
_vname = _store.vname
_text_table = _store.text_table
_visual_table = _store.visual_table
_list_kbs = _store.list_kbs

# ── S0: figure-page transcription (Ollama vision LLM at ingest) ────────────────
# Model chosen by a 5-round, 16-model bake-off across 6 lineages and both
# runtimes, scored on ground-truth fact recall — see
# reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md and the git history. Still off
# by default: text_gate already achieves diagram recall@1 = 1.000, so S0 buys
# query latency, not recall.
TRANSCRIBE_FIGURES = os.environ.get("RAG_TRANSCRIBE_FIGURES", "0") not in ("0", "false", "")
TRANSCRIBE_MODEL = os.environ.get("RAG_TRANSCRIBE_MODEL", "qwen3-vl:4b-instruct-q4_K_M")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_TRANSCRIBE_PROMPT = (
    "This is a page from an engineering / compliance document. Transcribe every "
    "piece of information visible in any figure, diagram, table, or screenshot on "
    "the page: equipment tags, instrument numbers, IP addresses, setpoints, valve "
    "states, alarm labels, legend entries, and how components connect. Write it as "
    "plain prose and lists — reproduce the exact identifiers and values. If the "
    "page is only body text, reply with the single word NONE."
)


async def _transcribe_page(img_path: str) -> str:
    """S0: vision-LLM transcript of one rendered page ("" if body-text-only)."""
    import base64 as _b64

    b64 = _b64.b64encode(Path(img_path).read_bytes()).decode()
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": TRANSCRIBE_MODEL,
                    "prompt": _TRANSCRIBE_PROMPT,
                    "images": [b64],
                    "stream": False,
                    # temperature 0.0 (greedy) is a known repetition-loop
                    # trigger on VL models — measured: it drove granite-vision
                    # to 147s/page and deepseek-ocr to 33k-char dumps, both of
                    # which recovered under repeat_penalty. num_predict bounds
                    # the worst case so one bad page cannot stall an ingest.
                    "options": {
                        "temperature": 0.1,
                        "repeat_penalty": 1.1,
                        "num_predict": 1200,
                    },
                },
            )
            r.raise_for_status()
            out = (r.json().get("response") or "").strip()
    except httpx.HTTPError:
        return ""
    return "" if out.upper().startswith("NONE") or len(out) < 20 else out


# ── The composition ───────────────────────────────────────────────────────────
# The stage set is stamped into each KB at ingest (P6): a stale index against a
# changed chunker / figure policy / fusion mode is caught by the same machinery
# that catches an embedding-model swap.
def _stage_set() -> dict:
    return {
        "chunk_strategy": CHUNK_STRATEGY,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "figure_page_max_text": FIGURE_PAGE_MAX_TEXT,
        "transcribe_figures": TRANSCRIBE_FIGURES,
        "fusion_mode": FUSION,
    }


def _composition() -> _pipeline.Composition:
    """Built per call, from this module's own names, so a test that patches an
    alias (``rm._vl_embed``, ``rm._text_table``, ``rm._PAGES_DIR``, ...) or a
    stage constant is honoured exactly as it was before the seam."""
    return _pipeline.Composition(
        name="rag_multimodal",
        get_db=_get_db,
        text_table=_text_table,
        visual_table=_visual_table,
        tname=_tname,
        vname=_vname,
        list_kbs=_list_kbs,
        read_stamp=_read_stamp,
        write_stamp=_write_stamp,
        assert_embedding_space=_assert_embedding_space,
        vl_model_id=_vl_model_id,
        vl_embed=_vl_embed,
        vl_embed_batch=_vl_embed_batch,
        vl_rerank=_vl_rerank,
        unavailable_error=_VLUnavailableError,
        chunk=_chunk,
        read_text=_read_text,
        render_pages=_render_pages,
        figure_pages=_figure_pages,
        transcribe_page=_transcribe_page,
        pages_dir=_PAGES_DIR,
        fusion_mode=FUSION,
        transcribe_figures=TRANSCRIBE_FIGURES,
        stage_set=_stage_set(),
    )


# ── Routes (contract-preserving, multimodal-backed) ───────────────────────────
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
        result = await _pipeline.ingest_document(_composition(), kb_id, src, rebuild)
        return JSONResponse(result)
    except _VLUnavailableError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


async def _search(request):
    """kb_search: default multimodal — RRF fusion of text-chunk and page-image
    retrieval. Contract-preserved: {kb_id, query, top_k}, response
    {kb_id, query, num_results, results:[{chunk_id, source_file, chunk_index,
    text, fused_score, reranker_prob, kind, page?}]}.

    `fused_score` is the RRF value plus, on visual rows, the VL reranker's
    calibrated probability when the text arm has no confident answer (see
    VL_TEXT_GATE / the B1 fusion fix). `reranker_prob` is that raw probability
    for visual rows, null for text rows."""
    args = (await request.json()).get("arguments", {})
    kb_id = args.get("kb_id", "")
    query = args.get("query", "")
    top_k = min(int(args.get("top_k", 5)), 20)
    if not kb_id or not query:
        return JSONResponse({"error": "kb_id and query required"}, status_code=400)
    try:
        result = await _pipeline.search(_composition(), kb_id, query, top_k)
        return JSONResponse(result)
    except _pipeline.UnknownKBError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
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
        result = await _pipeline.search_all(_composition(), query, top_k)
        return JSONResponse(result)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=503)


async def reindex_all() -> dict:
    """In-task migration: re-embed every existing KB's text with the VL model
    (the old tables are 1024-d; VL is VL_DIM, so tables are recreated)."""
    return await _pipeline.reindex(_composition())


def register_retrieval_routes(mcp) -> None:
    """Own the kb_* retrieval routes with the multimodal implementation."""
    mcp.custom_route("/tools/kb_ingest", methods=["POST"])(_ingest)
    mcp.custom_route("/tools/kb_search", methods=["POST"])(_search)
    mcp.custom_route("/tools/kb_search_all", methods=["POST"])(_search_all)
