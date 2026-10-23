"""Portal 5 — Wiki MCP Tool Server.

Agent-native retrieval from the canonical knowledge layer.
All answers RETURN their citations (grounded, not hallucinated).

Port: 8931 (configurable via WIKI_MCP_PORT env var)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.mcp_host.eval_scope import bind_native_context

logger = logging.getLogger(__name__)

# ── MCP Server Setup ─────────────────────────────────────────────────────────
_port = int(os.environ.get("WIKI_MCP_PORT") or os.environ.get("MCP_PORT", "8931"))

mcp = MCPServer(
    "Portal Wiki Tools",
    instructions="Canonical knowledge layer — search, get_unit, explain. "
    "Every answer cites its source. Use for architecture questions, "
    "technique signatures, design rationale lookup.",
)

# ── Ensure canonical dir is set ──────────────────────────────────────────────
_CANONICAL_DIR = Path(__file__).resolve().parent.parent / "portal_wiki" / "canonical"


def _ensure_canonical():
    from portal.platform.wiki.store import set_canonical_dir

    set_canonical_dir(_CANONICAL_DIR)


# ── Tool Manifest ────────────────────────────────────────────────────────────

# ── HTTP Routes ──────────────────────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "wiki-mcp", "port": _port})


# ── Tool Implementations ─────────────────────────────────────────────────────


@mcp.tool()
def wiki_search(query: str, top_k: int = 10) -> dict[str, Any]:
    """Search the canonical knowledge layer by keyword.

    Args:
        query: search query (keyword or phrase)
        top_k: max results (default 10)

    Returns:
        dict with matching units and their citations.
    """
    _ensure_canonical()
    from portal_wiki.mcp import wiki_search as _search

    return _search(query, top_k)


@mcp.tool()
def wiki_get_unit(unit_id: str) -> dict[str, Any]:
    """Get a specific knowledge unit by ID.

    Args:
        unit_id: the unit ID (e.g. "unit-T1190-signature")

    Returns:
        dict with full unit content and citations.
    """
    _ensure_canonical()
    from portal_wiki.mcp import wiki_get_unit as _get

    return _get(unit_id)


@mcp.tool()
def wiki_explain(query: str) -> dict[str, Any]:
    """Explain something by searching the canonical layer and returning
    a cited answer.

    Args:
        query: what to explain (e.g. "T1003.006 windows telemetry signature")

    Returns:
        dict with answer text and source citations.
    """
    _ensure_canonical()
    from portal_wiki.mcp import wiki_explain as _explain

    return _explain(query)


# ── Serve ────────────────────────────────────────────────────────────────────

bind_native_context(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
