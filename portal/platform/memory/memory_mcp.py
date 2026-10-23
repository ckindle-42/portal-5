"""Portal 5 Memory MCP Server.

Cross-conversation persistent memory backed by a temporal knowledge graph
(``graph_memory``): ``remember`` embeds a memory *and* extracts entities and
relations into the graph; ``recall`` is graph-aware — vector-seeded, then
relation-expanded, returning memories plus their connected context. The old
flat-vector top-K recall path was removed (TASK_MEMORY_GRAPH_OVERHAUL_V1); this
module is now a thin server that registers the graph implementation.

Tool contracts (``remember`` / ``recall`` / ``forget`` / ``list_memories`` /
``clear_memories``) are preserved; graph tools (``link`` / ``neighbors`` /
``entity_timeline`` / ``graph_recall``) are added.

Port: 8920 (MEMORY_MCP_PORT env override).
"""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import lancedb
from mcp.server import MCPServer
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.platform.data_loader import load_data
from portal.platform.lance_guard import list_all_table_names
from portal.platform.mcp_host.build_info import build_info
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.tool_support import align_native_tools, call_json_route
from portal.platform.memory import graph_memory
from portal.platform.memory.graph_memory import (
    LANCE_DIR,
    MEMORY_TABLE,
    register_memory_routes,
)

logger = logging.getLogger(__name__)
mcp = MCPServer("memory")

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route


def _stored_count() -> int:
    db = lancedb.connect(LANCE_DIR)
    if MEMORY_TABLE not in list_all_table_names(db):
        return 0
    return len(db.open_table(MEMORY_TABLE))


@_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    try:
        from portal.platform.memory.graph_memory import graph_stats

        g = graph_stats()
        status = "ok" if g["graph_intact"] else "degraded"
        return JSONResponse(
            {
                "status": status,
                "service": "memory-mcp",
                **build_info(),
                "stored": g["memories"],
                "graph": {
                    "entities": g["entities"],
                    "relations": g["relations"],
                    "intact": g["graph_intact"],
                },
            }
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "error": str(e), **build_info()})


@_route("/metrics", methods=["GET"])
async def metrics(request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_memory_mcp")


@_route("/tools", methods=["GET"])
async def list_tools(request: Request) -> JSONResponse:
    return JSONResponse(TOOLS_MANIFEST)


# All /tools/* memory routes are owned by graph_memory — one implementation.
register_memory_routes(mcp)


@mcp.tool()
async def remember(
    text: str, category: str = "fact", tags: list[str] | None = None
) -> dict[str, Any]:
    args: dict[str, Any] = {"text": text, "category": category}
    if tags is not None:
        args["tags"] = tags
    return await call_json_route(graph_memory._remember, args)


@mcp.tool()
async def recall(
    query: str,
    category: str | None = None,
    tags: list[str] | None = None,
    hops: int = 2,
    top_k: int = 5,
) -> dict[str, Any]:
    args: dict[str, Any] = {"query": query, "hops": hops, "top_k": top_k}
    if category is not None:
        args["category"] = category
    if tags is not None:
        args["tags"] = tags
    return await call_json_route(graph_memory._recall, args)


@mcp.tool()
async def graph_recall(query: str, hops: int = 2, top_k: int = 5) -> dict[str, Any]:
    return await call_json_route(
        graph_memory._recall, {"query": query, "hops": hops, "top_k": top_k}
    )


@mcp.tool()
async def link(
    src: str, dst: str, rel_type: str = "related_to", weight: float = 1.0
) -> dict[str, Any]:
    return await call_json_route(
        graph_memory._link,
        {"src": src, "dst": dst, "rel_type": rel_type, "weight": weight},
    )


@mcp.tool()
async def neighbors(name: str, hops: int = 1) -> dict[str, Any]:
    return await call_json_route(graph_memory._neighbors, {"name": name, "hops": hops})


@mcp.tool()
async def entity_timeline(name: str) -> dict[str, Any]:
    return await call_json_route(graph_memory._entity_timeline, {"name": name})


@mcp.tool()
async def forget(id: str) -> dict[str, Any]:
    return await call_json_route(graph_memory._forget, {"id": id})


@mcp.tool()
async def list_memories(
    category: str | None = None, limit: int = 50, tags: list[str] | None = None
) -> dict[str, Any]:
    args: dict[str, Any] = {"limit": limit}
    if category is not None:
        args["category"] = category
    if tags is not None:
        args["tags"] = tags
    return await call_json_route(graph_memory._list_memories, args)


@mcp.tool()
async def clear_memories(confirm_token: str) -> dict[str, Any]:
    return await call_json_route(graph_memory._clear_memories, {"confirm_token": confirm_token})


def main() -> None:
    port = int(os.environ.get("MEMORY_MCP_PORT", "8920"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


bind_native_context(mcp)
align_native_tools(mcp, TOOLS_MANIFEST)

if __name__ == "__main__":
    main()
