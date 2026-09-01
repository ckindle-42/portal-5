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

import lancedb
from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data
from portal.platform.memory.graph_memory import (
    LANCE_DIR,
    MEMORY_TABLE,
    register_memory_routes,
)

logger = logging.getLogger(__name__)
mcp = MCPServer("memory")


def _stored_count() -> int:
    db = lancedb.connect(LANCE_DIR)
    if MEMORY_TABLE not in db.table_names():
        return 0
    return len(db.open_table(MEMORY_TABLE))


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    try:
        from portal.platform.memory.graph_memory import graph_stats

        g = graph_stats()
        status = "ok" if g["graph_intact"] else "degraded"
        return JSONResponse(
            {
                "status": status,
                "service": "memory-mcp",
                "stored": g["memories"],
                "graph": {
                    "entities": g["entities"],
                    "relations": g["relations"],
                    "intact": g["graph_intact"],
                },
            }
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "error": str(e)})


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_memory_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse(TOOLS_MANIFEST)


# All /tools/* memory routes are owned by graph_memory — one implementation.
register_memory_routes(mcp)


def main():
    port = int(os.environ.get("MEMORY_MCP_PORT", "8920"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
