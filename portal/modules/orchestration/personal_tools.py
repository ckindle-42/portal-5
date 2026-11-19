"""Local reads for a personal task. The Pipeline still runs its own tool loop.

``queue_status`` and ``read_receipt`` are local. Wiki tools call the same functions
the wiki MCP serves. Nothing here writes, and nothing reads outside the tasks root.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCAL_TOOLS = frozenset({"queue_status", "read_receipt", "wiki_search", "wiki_get_unit"})


def tool_schema(name: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    if name == "wiki_search":
        properties = {"query": {"type": "string"}}
        required = ["query"]
    elif name == "wiki_get_unit":
        properties = {"unit_id": {"type": "string"}}
        required = ["unit_id"]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Personal task read tool {name}.",
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def run_read_tool(name: str, arguments: dict[str, Any], tasks_root: Path) -> str:
    """Execute one allowlisted read. Any other name is refused and not logged by the caller."""
    if name not in LOCAL_TOOLS:
        raise PermissionError(f"refused local tool {name}")
    if name == "queue_status":
        return json.dumps(_queue_status(tasks_root), sort_keys=True)
    if name == "read_receipt":
        return json.dumps(_newest_receipt(tasks_root), sort_keys=True)
    if name == "wiki_search":
        from portal_wiki.mcp import wiki_search

        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("wiki_search requires query")
        return json.dumps(wiki_search(query.strip()), sort_keys=True, default=str)
    from portal_wiki.mcp import wiki_get_unit

    unit_id = arguments.get("unit_id")
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("wiki_get_unit requires unit_id")
    return json.dumps(wiki_get_unit(unit_id.strip()), sort_keys=True, default=str)


def _queue_status(tasks_root: Path) -> dict[str, Any]:
    from portal.modules.orchestration.queue import QueueLedger

    with QueueLedger(tasks_root) as ledger:
        items = ledger.items()
    counts: dict[str, int] = {}
    for item in items:
        state = str(item.get("state") or "")
        counts[state] = counts.get(state, 0) + 1
    return {"counts": counts, "items": items}


def _newest_receipt(tasks_root: Path) -> dict[str, Any]:
    root = tasks_root.resolve()
    found: list[Path] = []
    for path in root.glob("*/receipt.json"):
        resolved = path.resolve()
        if resolved.is_file() and resolved.is_relative_to(root):
            found.append(resolved)
    if not found:
        return {"status": None, "path": None}
    newest = max(found, key=lambda item: item.stat().st_mtime)
    try:
        payload = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": None, "path": str(newest)}
    status = payload.get("status") if isinstance(payload, dict) else None
    return {"status": status, "path": str(newest)}
