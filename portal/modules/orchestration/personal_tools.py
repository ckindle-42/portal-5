"""Local reads for a personal task. The Pipeline still runs its own tool loop.

``queue_status`` and ``read_receipt`` are local. Wiki tools call the same functions
the wiki MCP serves. Nothing here writes; reads stay inside the tasks root or the
shared workspace (``workspace_files``, read-only).
"""

from __future__ import annotations

import heapq
import json
import os
from pathlib import Path
from typing import Any

LOCAL_TOOLS = frozenset(
    {
        "queue_status",
        "read_receipt",
        "wiki_search",
        "wiki_get_unit",
        "workspace_files",
        "security_sweep",
    }
)
# Bound the listing so one read cannot exhaust the tool-caller window on a huge tree.
WORKSPACE_FILE_CAP = 200
# The weekly sweep job writes its report here (scripts/security_sweep.py default_output_dir).
SWEEP_DIR = Path.home() / ".portal5" / "security"
SWEEP_CRITICAL_CAP = 20


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
            "List the largest files in the shared workspace, size descending, at most "
            f"{WORKSPACE_FILE_CAP}. Smaller files are omitted; the largest are not. "
            "path is relative to the workspace root: '/workspace/generated' -> 'generated', "
            "'/workspace/uploads' -> 'uploads'. Read-only."
        )
        properties = {"path": {"type": "string"}}
    elif name == "security_sweep":
        description = (
            "Read the newest security sweep report: MAL advisories, critical findings, the "
            "new/carried/resolved delta and the CRITICAL rows, with the report path. Read-only."
        )
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
    if name == "security_sweep":
        return json.dumps(_security_sweep(), sort_keys=True)
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
        return _file_listing(root, relative, [], 0)
    heap: list[tuple[int, int, dict[str, Any]]] = []
    scanned = 0
    for base, _dirs, names in os.walk(target):
        for filename in names:
            full = Path(base) / filename
            if full.is_symlink():
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            scanned += 1
            _keep_largest(
                heap,
                {"path": str(full.relative_to(root)), "size": size},
                scanned,
                WORKSPACE_FILE_CAP,
            )
    return _file_listing(root, relative, heap, scanned)


def _keep_largest(
    heap: list[tuple[int, int, dict[str, Any]]],
    item: dict[str, Any],
    seq: int,
    cap: int,
) -> None:
    """Bound the listing by size, not by walk order. The smallest of the kept set is the floor."""
    size = int(item["size"])
    if len(heap) < cap:
        heapq.heappush(heap, (size, seq, item))
        return
    if size > heap[0][0]:
        heapq.heapreplace(heap, (size, seq, item))


def _file_listing(
    root: Path,
    relative: str,
    heap: list[tuple[int, int, dict[str, Any]]],
    scanned: int,
) -> dict[str, Any]:
    files = [item for _size, _seq, item in sorted(heap, key=lambda row: row[0], reverse=True)]
    return {
        "root": str(root),
        "path": relative,
        "count": len(files),
        "scanned": scanned,
        "truncated": scanned > len(files),
        "files": files,
    }


def _security_sweep() -> dict[str, Any]:
    """The newest sweep report's counts, delta line and CRITICAL rows (2026-11-20)."""
    reports = sorted(SWEEP_DIR.glob("security_sweep_*.md"))
    if not reports:
        return {"error": f"no security sweep report in {SWEEP_DIR}"}
    report = reports[-1]
    try:
        lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"error": f"could not read {report}: {exc}"}
    sections = _sweep_sections(lines)
    critical = [row for row in sections.get("OSV findings", []) if "| CRITICAL |" in row]
    return {
        "path": str(report),
        "date": report.stem.removeprefix("security_sweep_"),
        "summary": [line.strip() for line in sections.get("", []) if line.startswith("- ")],
        "delta": _sweep_delta(sections),
        "critical": critical[:SWEEP_CRITICAL_CAP],
        "critical_truncated": len(critical) > SWEEP_CRITICAL_CAP,
    }


def _sweep_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    heading = ""
    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip()
            sections.setdefault(heading, [])
            continue
        sections.setdefault(heading, []).append(line)
    return sections


def _sweep_delta(sections: dict[str, list[str]]) -> str:
    for heading, body in sections.items():
        if heading.startswith("Delta"):
            for line in body:
                if line.strip():
                    return line.strip()
    return ""
