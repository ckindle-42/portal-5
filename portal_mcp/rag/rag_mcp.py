"""Portal 5 RAG MCP Server.

Multiple knowledge bases (KBs) backed by LanceDB. Each KB:
- ingested from local directory of .md, .txt, .pdf, .docx files
- chunked at CHUNK_SIZE chars with CHUNK_OVERLAP overlap
- embedded via MLX mxbai
- two-stage retrieval: vector top-50 -> bge reranker top-K

Tools: kb_list, kb_search, kb_search_all, kb_ingest.
Port: 8921 (RAG_MCP_PORT env override).
"""

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
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8081/v1/embeddings")
RERANK_URL = os.environ.get("MLX_RERANK_URL", "http://localhost:8081/v1/rerank")
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
        "description": "Search a specific knowledge base. Returns top relevant chunks with source file and similarity score. Use kb_list first to find available KB IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base identifier"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["kb_id", "query"],
        },
    },
    {
        "name": "kb_search_all",
        "description": "Search across all knowledge bases simultaneously. Useful when the user's question may match multiple KBs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx files. Run via curl or as setup; not typically called from chat.",
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
            },
            "required": ["kb_id", "source_dir"],
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


async def _read_file(path):
    """Best-effort text extraction from common formats."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            r = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            logger.warning("PDF read failed for %s: %s", path, e)
            return ""
    if suffix == ".docx":
        try:
            from docx import Document

            d = Document(str(path))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            logger.warning("DOCX read failed for %s: %s", path, e)
            return ""
    return ""


@mcp.custom_route("/tools/kb_ingest", methods=["POST"])
async def kb_ingest_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    source_dir = args.get("source_dir", "")
    rebuild = args.get("rebuild", False)
    if not kb_id or not source_dir:
        return JSONResponse({"error": "kb_id and source_dir are required"}, status_code=400)
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return JSONResponse({"error": f"directory not found: {src}"}, status_code=404)

    if rebuild:
        with contextlib.suppress(Exception):
            _get_db().drop_table(_kb_table_name(kb_id))

    table = _kb_table(kb_id, create_if_missing=True)

    files = [
        f
        for f in src.rglob("*")
        if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")
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

    return JSONResponse(
        {"kb_id": kb_id, "files_ingested": len(files), "chunks_added": total_chunks}
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

    qvec = await _embed(query)
    all_candidates = []
    for kb_id in kbs:
        t = _kb_table(kb_id)
        if t is None:
            continue
        for c in t.search(qvec).limit(20).to_list():
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
