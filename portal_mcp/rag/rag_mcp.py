"""Portal 5 RAG MCP Server.

Multiple knowledge bases (KBs) backed by LanceDB. Each KB:
- ingested from local directory of .md, .txt, .pdf, .docx files
- chunked at CHUNK_SIZE chars with CHUNK_OVERLAP overlap
- embedded via MLX mxbai
- two-stage retrieval: vector top-50 -> bge reranker top-K

Tools: kb_list, kb_search, kb_search_all, kb_ingest.
Port: 8921 (RAG_MCP_PORT env override).
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import time
from pathlib import Path

import httpx
import lancedb
import pyarrow as pa
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("rag", host="0.0.0.0")

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
RAG_DIR = os.path.join(LANCE_DIR, "rag")
KB_SOURCES_DIR = os.environ.get("PORTAL5_KB_SOURCES_DIR", "/Volumes/data01/portal5_kb_sources")
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8917/v1/embeddings")
# RERANKER_URL: dedicated Qwen3-Reranker-0.6B-mxfp8 MCP on :8925.
# Falls back gracefully to dense-order if reranker is unavailable.
RERANK_URL = os.environ.get("RERANKER_URL", "http://localhost:8925")
EMBEDDING_DIM = 1024
CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))

_db = None
_kb_cache = {}


def _get_db():
    global _db
    if _db is None:
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


async def _embed(text):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(EMBEDDING_URL, json={"input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


async def _embed_batch(texts):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(EMBEDDING_URL, json={"input": texts})
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


async def _rerank(query, docs, top_n):
    if len(docs) == 0:
        return []
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(RERANK_URL, json={"query": query, "documents": docs, "top_n": top_n})
        if r.status_code != 200:
            return [
                {"index": i, "relevance_score": 0.5, "document": d}
                for i, d in enumerate(docs[:top_n])
            ]
        return r.json()["results"]


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        kbs = _list_kbs()
        return JSONResponse({"status": "ok", "service": "rag-mcp", "knowledge_bases": kbs})
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = [
    {
        "name": "kb_list",
        "description": "List all available knowledge bases (KBs) and their document counts.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kb_search",
        "description": "Search a specific knowledge base. Returns top relevant chunks with source file and similarity score. Use kb_list first to find available KB IDs. query_type: vector (semantic, default), fts (BM25 keyword — exact terms/IDs), hybrid (both, RRF-fused). fts/hybrid require the KB to be ingested with fts=true.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base identifier"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "query_type": {
                    "type": "string",
                    "enum": ["vector", "fts", "hybrid"],
                    "default": "vector",
                },
            },
            "required": ["kb_id", "query"],
        },
    },
    {
        "name": "kb_search_all",
        "description": "Search across all knowledge bases simultaneously. Useful when the user's question may match multiple KBs. query_type: vector (default), fts, hybrid; KBs without an FTS index transparently fall back to vector.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "query_type": {
                    "type": "string",
                    "enum": ["vector", "fts", "hybrid"],
                    "default": "vector",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx, .pptx, .xlsx, .html, .htm, .epub files (Docling-first extraction with pypdf/python-docx fallback). Run via curl or as setup; not typically called from chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "source_dir": {
                    "type": "string",
                    "description": "Absolute path to directory of source files",
                },
                "rebuild": {
                    "type": "boolean",
                    "description": "Drop existing chunks and reingest",
                    "default": False,
                },
                "fts": {
                    "type": "boolean",
                    "description": "Build a native Lance BM25 full-text index after ingest (enables query_type fts/hybrid on this KB)",
                    "default": False,
                },
            },
            "required": ["kb_id", "source_dir"],
        },
    },
    {
        "name": "kb_optimize",
        "description": "Admin: build an IVF_PQ vector index on a KB for faster search. Skipped automatically for KBs under 256 chunks (brute-force is already fast). Run after large ingests.",
        "parameters": {
            "type": "object",
            "properties": {"kb_id": {"type": "string"}},
            "required": ["kb_id"],
        },
    },
    {
        "name": "kb_versions",
        "description": "List a KB's LanceDB version history and named tags (e.g. automatic pre-rebuild tags). Use with kb_restore to roll back.",
        "parameters": {
            "type": "object",
            "properties": {"kb_id": {"type": "string"}},
            "required": ["kb_id"],
        },
    },
    {
        "name": "kb_restore",
        "description": "Admin: restore a KB to an earlier LanceDB version (see kb_versions). The restore itself is a new version, so it can be undone.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "version": {"type": "integer", "description": "Version number from kb_versions"},
            },
            "required": ["kb_id", "version"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


def _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Sliding-window chunk on character boundaries; respects paragraph breaks where possible."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            for delim in ("\n\n", ". ", "\n"):
                idx = text.rfind(delim, start + chunk_size // 2, end + len(delim))
                if idx > 0:
                    end = idx + len(delim)
                    break
        chunks.append((start, end, text[start:end]))
        start = max(end - overlap, start + 1)
    return chunks


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


@mcp.custom_route("/tools/kb_ingest", methods=["POST"])
async def kb_ingest_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    source_dir = args.get("source_dir", "")
    rebuild = args.get("rebuild", False)
    fts = args.get("fts", False)
    if not kb_id or not source_dir:
        return JSONResponse({"error": "kb_id and source_dir are required"}, status_code=400)
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return JSONResponse({"error": f"directory not found: {src}"}, status_code=404)

    if rebuild:
        tname = _kb_table_name(kb_id)
        try:
            existing = _get_db().open_table(tname)
            pre_version = existing.version
            with contextlib.suppress(Exception):
                existing.tags.create(f"pre-rebuild-{int(time.time())}", pre_version)
            # Delete rows instead of dropping the table: the delete is itself a
            # new version, so the pre-rebuild state stays restorable via
            # kb_restore. drop_table would destroy the version history.
            existing.delete("chunk_id IS NOT NULL")
        except Exception:
            # Table missing or version-safe path unavailable — fall back to drop.
            with contextlib.suppress(Exception):
                _get_db().drop_table(tname)

    table = _kb_table(kb_id, create_if_missing=True)

    files = [
        f
        for f in src.rglob("*")
        if f.is_file()
        and f.suffix.lower()
        in (".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub")
    ]
    files = files[:5000]

    total_chunks = 0
    for f in files:
        text = await _read_file(f)
        if not text:
            continue
        chunks = _chunk_text(text)
        if not chunks:
            continue
        for batch_start in range(0, len(chunks), 16):
            batch = chunks[batch_start : batch_start + 16]
            try:
                vectors = await _embed_batch([c[2] for c in batch])
            except Exception as e:
                logger.error("embed batch failed for %s: %s", f, e)
                continue
            now = time.time()
            records = []
            for i, ((cstart, cend, ctext), vec) in enumerate(zip(batch, vectors, strict=False)):
                chunk_id = hashlib.sha1(f"{kb_id}|{f}|{batch_start + i}".encode()).hexdigest()
                records.append(
                    {
                        "chunk_id": chunk_id,
                        "kb_id": kb_id,
                        "source_file": str(f.relative_to(src)),
                        "chunk_index": batch_start + i,
                        "text": ctext,
                        "vector": vec,
                        "char_start": cstart,
                        "char_end": cend,
                        "ingested_at": now,
                    }
                )
            table.add(records)
            total_chunks += len(records)

    fts_created = False
    if fts and total_chunks > 0:
        try:
            try:
                table.create_fts_index("text", use_tantivy=False, replace=True)
            except TypeError:
                # use_tantivy kwarg removed in newer lancedb (native is default)
                table.create_fts_index("text", replace=True)
            fts_created = True
        except Exception as e:
            logger.warning("FTS index creation failed for %s: %s", kb_id, e)

    return JSONResponse(
        {
            "kb_id": kb_id,
            "files_ingested": len(files),
            "chunks_added": total_chunks,
            "fts_index": fts_created,
        }
    )


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
    kbs = []
    for kb_id in _list_kbs():
        t = _kb_table(kb_id)
        if t is not None:
            kbs.append({"kb_id": kb_id, "chunks": len(t)})
    return JSONResponse({"knowledge_bases": kbs})


@mcp.custom_route("/tools/kb_search", methods=["POST"])
async def kb_search_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    query = args.get("query", "")
    top_k = min(args.get("top_k", 5), 20)
    if not kb_id or not query:
        return JSONResponse({"error": "kb_id and query required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)

    query_type = args.get("query_type", "vector")
    if query_type == "fts":
        try:
            candidates = table.search(query, query_type="fts").limit(50).to_list()
        except Exception as e:
            return JSONResponse(
                {"error": f"fts search failed (no FTS index? re-ingest with fts=true): {e}"},
                status_code=400,
            )
    elif query_type == "hybrid":
        qvec = await _embed(query)
        try:
            candidates = (
                table.search(query_type="hybrid").vector(qvec).text(query).limit(50).to_list()
            )
        except Exception as e:
            return JSONResponse(
                {"error": f"hybrid search failed (no FTS index? re-ingest with fts=true): {e}"},
                status_code=400,
            )
    else:
        qvec = await _embed(query)
        candidates = table.search(qvec).limit(50).to_list()
    if not candidates:
        return JSONResponse({"kb_id": kb_id, "query": query, "results": []})

    docs = [c["text"] for c in candidates]
    reranked = await _rerank(query, docs, top_k)
    out = []
    for r in reranked:
        c = candidates[r["index"]]
        out.append(
            {
                "chunk_id": c["chunk_id"],
                "source_file": c["source_file"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
                "rerank_score": round(r["relevance_score"], 4),
            }
        )
    return JSONResponse({"kb_id": kb_id, "query": query, "num_results": len(out), "results": out})


@mcp.custom_route("/tools/kb_search_all", methods=["POST"])
async def kb_search_all_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    query = args.get("query", "")
    top_k = min(args.get("top_k", 5), 20)
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    kbs = _list_kbs()
    if not kbs:
        return JSONResponse({"query": query, "results": []})

    query_type = args.get("query_type", "vector")
    qvec = await _embed(query)
    all_candidates = []
    for kb_id in kbs:
        t = _kb_table(kb_id)
        if t is None:
            continue
        try:
            if query_type == "fts":
                hits = t.search(query, query_type="fts").limit(20).to_list()
            elif query_type == "hybrid":
                hits = t.search(query_type="hybrid").vector(qvec).text(query).limit(20).to_list()
            else:
                hits = t.search(qvec).limit(20).to_list()
        except Exception:
            # KBs without an FTS index fall back to vector search.
            hits = t.search(qvec).limit(20).to_list()
        for c in hits:
            c["_kb_id"] = kb_id
            all_candidates.append(c)
    if not all_candidates:
        return JSONResponse({"query": query, "results": []})

    docs = [c["text"] for c in all_candidates]
    reranked = await _rerank(query, docs, top_k)
    out = []
    for r in reranked:
        c = all_candidates[r["index"]]
        out.append(
            {
                "kb_id": c["_kb_id"],
                "source_file": c["source_file"],
                "text": c["text"],
                "rerank_score": round(r["relevance_score"], 4),
            }
        )
    return JSONResponse({"query": query, "num_results": len(out), "results": out})


def main():
    port = int(os.environ.get("RAG_MCP_PORT", "8921"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
