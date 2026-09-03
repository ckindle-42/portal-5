"""Portal 5 RAG MCP Server.

Multiple knowledge bases (KBs) backed by LanceDB. Retrieval is multimodal
(TASK_RAG_VISUAL_OVERHAUL_V1): kb_ingest renders PDF pages to images and
embeds them alongside text chunks with the Qwen3-VL retrieval server, and
kb_search fuses text + page-image retrieval (RRF) by default. Those routes
live in rag_multimodal; this server keeps the KB-lifecycle tools
(kb_list / kb_optimize / kb_versions / kb_restore) and registers the
multimodal retrieval routes.

Port: 8921 (RAG_MCP_PORT env override).
"""

import asyncio
import contextlib
import logging
import os
import re

import lancedb
import pyarrow as pa
from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.modules.research.tools.rag_multimodal import register_retrieval_routes
from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
mcp = MCPServer("rag")

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
RAG_DIR = os.path.join(LANCE_DIR, "rag")
# Retrieval (embedding + rerank) is now the Qwen3-VL retrieval server — see
# rag_multimodal. kb_ingest/kb_search/kb_search_all are owned there. The
# lifecycle tools below (kb_optimize/versions/restore/list) stay here.
EMBEDDING_DIM = int(os.environ.get("VL_EMBEDDING_DIM", "2048"))
CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))

_db = None
_kb_cache = {}


def _get_db():
    global _db
    if _db is None:
        from portal.platform.lance_guard import require_lance_dir

        require_lance_dir(LANCE_DIR)
        os.makedirs(RAG_DIR, exist_ok=True)
        _db = lancedb.connect(RAG_DIR)
    return _db


def _kb_table_name(kb_id):
    return f"kb_{re.sub(r'[^a-z0-9_]', '_', kb_id.lower())}"


def _kb_table(kb_id, create_if_missing=False):
    name = _kb_table_name(kb_id)
    db = _get_db()
    if name in db.table_names():
        return db.open_table(name)
    if not create_if_missing:
        return None
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("kb_id", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            pa.field("char_start", pa.int32()),
            pa.field("char_end", pa.int32()),
            pa.field("ingested_at", pa.float64()),
        ]
    )
    return db.create_table(name, schema=schema)


def _list_kbs():
    """List all KBs by table prefix."""
    return sorted([t.replace("kb_", "", 1) for t in _get_db().table_names() if t.startswith("kb_")])


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        kbs = _list_kbs()
        return JSONResponse({"status": "ok", "service": "rag-mcp", "knowledge_bases": kbs})
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_rag_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


_DOCLING_FORMATS = (".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub")
_docling_converter = None


def _get_docling_converter():
    """Lazily build and cache a Docling DocumentConverter (expensive to init)."""
    global _docling_converter
    if _docling_converter is None:
        from docling.document_converter import DocumentConverter

        _docling_converter = DocumentConverter()
    return _docling_converter


def _docling_convert(path):
    """Blocking Docling conversion -> markdown. Raises on any failure.

    Kept as a module-level indirection so unit tests can patch it without
    installing docling on the host (docling ships only in Dockerfile.mcp).
    """
    result = _get_docling_converter().convert(str(path))
    return result.document.export_to_markdown()


async def _read_file(path):
    """Extract text via Docling (preferred) with pypdf/python-docx fallback.

    Docling adds table extraction, layout preservation, and reading-order
    awareness, and extends coverage to PPTX/XLSX/HTML/EPUB. Conversion runs
    in a worker thread (CPU-bound). Falls back to pypdf (PDF) or python-docx
    (DOCX) when docling is unavailable, fails, or returns no usable text.
    """
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix in _DOCLING_FORMATS:
        try:
            text = await asyncio.to_thread(_docling_convert, path)
            if text and len(text.strip()) > 20:
                return text
            logger.warning("Docling returned no usable text for %s, falling back", path)
        except Exception as e:
            logger.warning("Docling read failed for %s, falling back: %s", path, e)

    if suffix == ".pdf":
        # pymupdf first: it is already a hard dep (research extra, used by
        # portal.platform.retrieval.pages.render_pages) so this fallback works host-native, where
        # docling and pypdf are not installed (docling ships only in
        # Dockerfile.mcp). pypdf stays as a second try.
        try:
            import pymupdf

            with pymupdf.open(str(path)) as doc:
                text = "\n\n".join(page.get_text() for page in doc)
            if text.strip():
                return text
        except Exception as e:
            logger.warning("pymupdf PDF read failed for %s: %s", path, e)
        try:
            from pypdf import PdfReader

            r = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            logger.warning("PDF fallback read failed for %s: %s", path, e)
            return ""
    if suffix == ".docx":
        try:
            from docx import Document

            d = Document(str(path))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            logger.warning("DOCX fallback read failed for %s: %s", path, e)
            return ""
    return ""


@mcp.custom_route("/tools/kb_optimize", methods=["POST"])
async def kb_optimize_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    if not kb_id:
        return JSONResponse({"error": "kb_id required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    rows = len(table)
    if rows < 256:
        return JSONResponse(
            {
                "kb_id": kb_id,
                "rows": rows,
                "skipped": "fewer than 256 chunks; brute-force scan is already fast",
            }
        )
    num_partitions = min(512, int(rows**0.5))
    try:
        # num_sub_vectors must divide the embedding dim (1024); the lancedb
        # default of 96 does not and raises. 64 divides 1024 cleanly.
        table.create_index(
            metric="l2",
            num_partitions=num_partitions,
            num_sub_vectors=64,
            replace=True,
        )
    except Exception as e:
        return JSONResponse({"error": f"index build failed: {e}"}, status_code=500)
    with contextlib.suppress(Exception):
        table.optimize()
    return JSONResponse(
        {
            "kb_id": kb_id,
            "rows": rows,
            "index": "IVF_PQ",
            "num_partitions": num_partitions,
            "num_sub_vectors": 64,
        }
    )


@mcp.custom_route("/tools/kb_versions", methods=["POST"])
async def kb_versions_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    if not kb_id:
        return JSONResponse({"error": "kb_id required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    versions = [
        # timestamp is a datetime — not JSON serializable without str()
        {"version": v["version"], "timestamp": str(v["timestamp"])}
        for v in table.list_versions()
    ]
    tags = {}
    with contextlib.suppress(Exception):
        for name, t in table.tags.list().items():
            tags[name] = t["version"] if isinstance(t, dict) else getattr(t, "version", None)
    return JSONResponse(
        {"kb_id": kb_id, "current_version": table.version, "versions": versions, "tags": tags}
    )


@mcp.custom_route("/tools/kb_restore", methods=["POST"])
async def kb_restore_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    version = args.get("version")
    if not kb_id or version is None:
        return JSONResponse({"error": "kb_id and version required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    try:
        table.restore(int(version))
    except Exception as e:
        return JSONResponse({"error": f"restore failed: {e}"}, status_code=400)
    return JSONResponse(
        {"kb_id": kb_id, "restored_to": int(version), "current_version": table.version}
    )


@mcp.custom_route("/tools/kb_list", methods=["POST"])
async def kb_list_endpoint(request):
    from portal.modules.research.tools.rag_multimodal import _read_stamp

    kbs = []
    for kb_id in _list_kbs():
        t = _kb_table(kb_id)
        if t is not None:
            stamp = _read_stamp(kb_id) or {}
            kbs.append(
                {
                    "kb_id": kb_id,
                    "chunks": len(t),
                    "embed_model": stamp.get("embed_model"),
                    "vl_dim": stamp.get("vl_dim"),
                }
            )
    return JSONResponse({"knowledge_bases": kbs})


# kb_ingest / kb_search / kb_search_all are owned by the multimodal
# implementation — one retrieval path, not two.
register_retrieval_routes(mcp)


def main():
    port = int(os.environ.get("RAG_MCP_PORT", "8921"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
