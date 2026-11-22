"""Shared client-tool merge for the streaming and non-streaming router paths."""

from __future__ import annotations

import logging
from collections.abc import Collection
from functools import lru_cache
from typing import Any

from portal.platform.inference.owui_tools import tool_to_server
from portal.platform.inference.tool_registry import MCP_SERVERS

logger = logging.getLogger(__name__)


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
    windows, so they are dropped when the pipeline manages the toolset. Bite-allowlist
    requests name their own tools and pass with drop_portal_mirrors=False (legacy dedup).
    """
    seen_names = {t.get("function", {}).get("name") for t in tools_array}
    registered = set(registered_names)
    prefixes = _portal_mirror_prefixes() if drop_portal_mirrors else ()
    dropped = 0
    for ct in client_tools:
        ct_name = ct.get("function", {}).get("name", "")
        if not ct_name or ct_name in seen_names:
            continue
        if prefixes and _is_portal_mirror(ct_name, prefixes, registered, seen_names):
            dropped += 1
            continue
        tools_array.append(ct)
        seen_names.add(ct_name)
    if dropped:
        logger.info("Tool-merge: dropped %d OWUI portal_* mirror schema(s)", dropped)
    return tools_array
