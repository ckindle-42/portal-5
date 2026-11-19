"""Local reads for a personal task. The Pipeline still runs its own tool loop.

``queue_status`` and ``read_receipt`` are local. Wiki tools call the same functions
the wiki MCP serves. Nothing here writes; reads stay inside the tasks root or the
shared workspace (``workspace_files``, read-only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

LOCAL_TOOLS = frozenset(
    {"queue_status", "read_receipt", "wiki_search", "wiki_get_unit", "workspace_files"}
)
# Bound the listing so one read cannot exhaust the tool-caller window on a huge tree.
WORKSPACE_FILE_CAP = 200


def tool_schema(name: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    description = f"Personal task read tool {name}."
    if name == "wiki_search":
        properties = {"query": {"type": "string"}}
        required = ["query"]
    elif name == "wiki_get_unit":
        properties = {"unit_id": {"type": "string"}}
        required = ["unit_id"]
    elif name == "workspace_files":
        description = (
            "List files in the shared workspace with their sizes in bytes, largest first. "
            "path is relative to the workspace root: '/workspace/generated' -> 'generated', "
            "'/workspace/uploads' -> 'uploads'. Read-only."
        )
        properties = {"path": {"type": "string"}}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
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
    if name == "workspace_files":
        return json.dumps(_workspace_files(arguments), sort_keys=True)
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


def _workspace_files(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only file listing under the shared workspace root, largest first."""
    from portal.platform.mcp_host.workspace import get_workspace_root

    root = get_workspace_root().resolve()
    raw = arguments.get("path")
    relative = raw.strip() if isinstance(raw, str) and raw.strip() else "generated"
    parts = Path(relative.replace("\\", "/")).parts
    while parts and parts[0] in {"/", "workspace"}:
        parts = parts[1:]
    target = (root.joinpath(*parts)).resolve() if parts else root
    if target != root and not target.is_relative_to(root):
        raise ValueError("workspace_files path is outside the shared workspace")
    if not target.is_dir():
        return {"root": str(root), "path": relative, "count": 0, "files": []}
    files: list[dict[str, Any]] = []
    for base, _dirs, names in os.walk(target):
        for filename in names:
            full = Path(base) / filename
            if full.is_symlink():
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            files.append({"path": str(full.relative_to(root)), "size": size})
            if len(files) >= WORKSPACE_FILE_CAP:
                break
        if len(files) >= WORKSPACE_FILE_CAP:
            break
    files.sort(key=lambda item: item["size"], reverse=True)
    return {"root": str(root), "path": relative, "count": len(files), "files": files}
