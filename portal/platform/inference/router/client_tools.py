"""Shared client-tool merge for the streaming and non-streaming router paths."""

from __future__ import annotations

import logging
from collections.abc import Collection
from functools import lru_cache
from typing import Any

from portal.platform.inference.owui_tools import tool_to_server
from portal.platform.inference.tool_registry import MCP_SERVERS

logger = logging.getLogger(__name__)

# Open WebUI v0.13.4+ attaches ~38 native builtin tool schemas (automations, calendar,
# notes, chats, OWUI memory/KB) to persona chats by default. When the Pipeline manages a
# workspace's toolset (drop_portal_mirrors=True), merging these unsolicited schemas adds
# ~10,000+ tokens on turn 1 (overflowing 8k/16k workspaces) and shadows Portal's own
# memory/RAG MCP tools. Keep genuinely external custom client tools intact.
_OWUI_BUILTIN_TOOLS: frozenset[str] = frozenset(
    {
        "add_memory",
        "ask_user",
        "calculate_timestamp",
        "create_automation",
        "create_calendar_event",
        "create_skill",
        "create_tasks",
        "create_tool",
        "delete_automation",
        "delete_calendar_event",
        "delete_memory",
        "display_file",
        "get_current_timestamp",
        "grep_knowledge_files",
        "list_automations",
        "list_knowledge_bases",
        "list_memory_paths",
        "query_knowledge_bases",
        "query_knowledge_files",
        "read_memory_path",
        "replace_memory_content",
        "replace_note_content",
        "search_calendar_events",
        "search_chats",
        "search_knowledge_bases",
        "search_knowledge_files",
        "search_memories",
        "search_notes",
        "search_users",
        "toggle_automation",
        "update_automation",
        "update_calendar_event",
        "update_memory",
        "update_task",
        "view_chat",
        "view_knowledge_file",
        "view_note",
        "write_note",
    }
)


@lru_cache(maxsize=1)
def _portal_mirror_prefixes() -> tuple[str, ...]:
    """OWUI name prefixes of Portal MCP servers: yaml ids plus portal_<fleet id>."""
    server_ids = set(tool_to_server().values())
    server_ids.update(f"portal_{sid}" for sid in MCP_SERVERS)
    return tuple(sorted(f"{sid}_" for sid in server_ids))


def _is_portal_mirror(
    name: str,
    prefixes: tuple[str, ...],
    registered: set[str],
    seen_names: set[Any],
) -> bool:
    """True when name is portal_<known server>_<registered or already-offered tool>."""
    if not name.startswith("portal_"):
        return False
    for prefix in prefixes:
        if name.startswith(prefix):
            rest = name[len(prefix) :]
            if rest in registered or rest in seen_names:
                return True
    return False


def merge_client_tools(
    tools_array: list[dict[str, Any]],
    client_tools: list[Any],
    registered_names: Collection[str],
    *,
    drop_portal_mirrors: bool = True,
) -> list[dict[str, Any]]:
    """Append external client tools to the workspace schemas, deduped by name.

    OWUI attaches Portal's own MCP tools back to the request as portal_<server>_<tool>
    mirrors; merging them bypasses the workspace whitelist and overflows small context
    windows, so they are dropped when the pipeline manages the toolset. The same
    authority drops unprefixed echoes of registered pipeline tools (2026-11-26: OWUI
    injected a bare `list_memories` the workspace never declared). Bite-allowlist
    requests name their own tools and pass with drop_portal_mirrors=False (legacy dedup).
    """
    seen_names = {t.get("function", {}).get("name") for t in tools_array}
    registered = set(registered_names)
    prefixes = _portal_mirror_prefixes() if drop_portal_mirrors else ()
    dropped = 0
    dropped_builtins = 0
    dropped_echoes = 0
    for ct in client_tools:
        ct_name = ct.get("function", {}).get("name", "")
        if not ct_name or ct_name in seen_names:
            continue
        if prefixes and _is_portal_mirror(ct_name, prefixes, registered, seen_names):
            dropped += 1
            continue
        if drop_portal_mirrors and ct_name in _OWUI_BUILTIN_TOOLS:
            dropped_builtins += 1
            continue
        if drop_portal_mirrors and ct_name in registered:
            dropped_echoes += 1
            continue
        tools_array.append(ct)
        seen_names.add(ct_name)
    if dropped:
        logger.info("Tool-merge: dropped %d OWUI portal_* mirror schema(s)", dropped)
    if dropped_builtins:
        logger.info("Tool-merge: dropped %d OWUI builtin tool schema(s)", dropped_builtins)
    if dropped_echoes:
        logger.info(
            "Tool-merge: dropped %d unprefixed echo(s) of pipeline-registered tool(s)",
            dropped_echoes,
        )
    return tools_array


def external_client_tool_names(
    client_tools: Collection[Any],
    registered_names: Collection[str],
    effective_tools: Collection[str],
) -> list[str]:
    """Names the pipeline-managed merge would keep: the caller's own tool selection."""
    registered = set(registered_names)
    prefixes = _portal_mirror_prefixes()
    seen_names = set(effective_tools)
    keep: list[str] = []
    for ct in client_tools:
        if not isinstance(ct, dict):
            continue
        name = (ct.get("function") or {}).get("name", "")
        if not name or name in seen_names:
            continue
        if _is_portal_mirror(name, prefixes, registered, seen_names):
            continue
        if name in _OWUI_BUILTIN_TOOLS or name in registered:
            continue
        keep.append(name)
        seen_names.add(name)
    return keep
