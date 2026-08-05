import json
from pathlib import Path
from typing import Any

"""Portal 5 Memory MCP Server.

Cross-conversation persistent memory backed by LanceDB.
Each memory has: id, user_id, text, vector, category, tags, created_at,
last_accessed_at, access_count.
Recall is hybrid: vector similarity (top-K) + recency boost + tag filter.

Port: 8920 (MEMORY_MCP_PORT env override).
"""

import logging
import os
import time
import uuid

import httpx
import lancedb
import pyarrow as pa
from mcp.server import MCPServer

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_data(name: str) -> Any:
    """Load a data file that was a module-level literal before V1."""
    path = _PROJECT_ROOT / "config" / "inference" / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
mcp = MCPServer("memory")

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
MEMORY_TABLE = "memory"
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8917/v1/embeddings")
EMBEDDING_DIM = 1024
DEFAULT_USER = "default"

_memory_table = None


def _get_table():
    global _memory_table
    if _memory_table is not None:
        return _memory_table
    os.makedirs(LANCE_DIR, exist_ok=True)
    db = lancedb.connect(LANCE_DIR)
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("user_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("category", pa.string()),
            pa.field("tags", pa.list_(pa.string())),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            pa.field("created_at", pa.float64()),
            pa.field("last_accessed_at", pa.float64()),
            pa.field("access_count", pa.int64()),
        ]
    )
    _memory_table = (
        db.create_table(MEMORY_TABLE, schema=schema)
        if MEMORY_TABLE not in db.table_names()
        else db.open_table(MEMORY_TABLE)
    )
    return _memory_table


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(EMBEDDING_URL, json={"input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        return JSONResponse({"status": "ok", "service": "memory-mcp", "stored": len(_get_table())})
    except Exception as e:
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = _load_data("tools_manifest_memory_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


@mcp.custom_route("/tools/remember", methods=["POST"])
async def remember_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    text = args.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    if len(text) > 4000:
        return JSONResponse({"error": "text too long (max 4000 chars)"}, status_code=400)
    try:
        vector = await _embed(text)
    except Exception as e:
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    now = time.time()
    record = {
        "id": str(uuid.uuid4()),
        "user_id": DEFAULT_USER,
        "text": text,
        "category": args.get("category", "fact"),
        "tags": args.get("tags", []),
        "vector": vector,
        "created_at": now,
        "last_accessed_at": now,
        "access_count": 0,
    }
    _get_table().add([record])
    return JSONResponse({"id": record["id"], "stored": True, "category": record["category"]})


@mcp.custom_route("/tools/recall", methods=["POST"])
async def recall_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    query = args.get("query", "")
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    top_k = min(max(args.get("top_k", 5), 1), 20)
    tags = args.get("tags", [])
    category = args.get("category")
    try:
        qvec = await _embed(query)
    except Exception as e:
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    table = _get_table()
    where_parts = [f"user_id = '{DEFAULT_USER}'"]
    if category:
        where_parts.append(f"category = '{category}'")
    fetch_k = min(top_k * 3, 100)
    results = table.search(qvec).where(" AND ".join(where_parts)).limit(fetch_k).to_list()
    if tags:
        tags_set = set(tags)
        results = [r for r in results if tags_set & set(r.get("tags", []))]
    now = time.time()
    for r in results:
        recency = max(0, 1 - (now - r.get("last_accessed_at", 0)) / (90 * 86400))
        r["_score"] = r.get("_distance", 1.0) - 0.05 * recency
    results = sorted(results, key=lambda r: r["_score"])[:top_k]
    out = []
    for r in results:
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "category": r["category"],
                "tags": r["tags"],
                "similarity": round(1 - r.get("_distance", 1.0), 3),
                "created_at": r["created_at"],
            }
        )
    return JSONResponse({"query": query, "num_results": len(out), "memories": out})


@mcp.custom_route("/tools/forget", methods=["POST"])
async def forget_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    mem_id = args.get("id", "")
    if not mem_id:
        return JSONResponse({"error": "id is required"}, status_code=400)
    try:
        _get_table().delete(f"id = '{mem_id}'")
        return JSONResponse({"id": mem_id, "deleted": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/tools/list_memories", methods=["POST"])
async def list_memories_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    category = args.get("category")
    tags = args.get("tags", [])
    limit = min(args.get("limit", 50), 500)
    table = _get_table()
    where = f"user_id = '{DEFAULT_USER}'"
    if category:
        where += f" AND category = '{category}'"
    rows = table.search().where(where).limit(limit).to_list()
    if tags:
        tags_set = set(tags)
        rows = [r for r in rows if tags_set & set(r.get("tags", []))]
    return JSONResponse(
        {
            "total": len(rows),
            "memories": [
                {
                    "id": r["id"],
                    "text": r["text"][:200],
                    "category": r["category"],
                    "tags": r["tags"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
        }
    )


@mcp.custom_route("/tools/clear_memories", methods=["POST"])
async def clear_memories_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    if args.get("confirm_token") != "YES_DELETE_ALL":
        return JSONResponse({"error": "confirm_token must be 'YES_DELETE_ALL'"}, status_code=400)
    _get_table().delete(f"user_id = '{DEFAULT_USER}'")
    return JSONResponse({"deleted": "all", "user_id": DEFAULT_USER})


def main():
    port = int(os.environ.get("MEMORY_MCP_PORT", "8920"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
