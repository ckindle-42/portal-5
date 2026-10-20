"""Open WebUI tool server mappings loaded from config."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SERVERS_FILE = REPO / "config" / "owui_tool_servers.yaml"


def _load(path: Path | None = None) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    config_path = path or SERVERS_FILE
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    tool_to_server: dict[str, str] = {}
    for server, tools in (data.get("servers") or {}).items():
        for tool in tools:
            if tool in tool_to_server:
                raise ValueError(
                    f"{config_path.name}: tool {tool!r} is served by both "
                    f"{tool_to_server[tool]!r} and {server!r}"
                )
            tool_to_server[tool] = server
    dead_servers = frozenset(data.get("dead_servers") or [])
    pipeline_native = frozenset(data.get("pipeline_native") or [])
    return tool_to_server, dead_servers, pipeline_native


def tool_to_server(path: Path | None = None) -> dict[str, str]:
    """Return a copy of the tool-to-server map."""
    return dict(_load(path)[0])


def dead_servers(path: Path | None = None) -> frozenset[str]:
    """Return the configured server ids without a live backing service."""
    return _load(path)[1]


def pipeline_native_tools(path: Path | None = None) -> frozenset[str]:
    """Return tools handled directly by the pipeline."""
    return _load(path)[2]


def compute_tool_ids(tools: list[str], path: Path | None = None) -> list[str]:
    """Map raw tool names to sorted, deduplicated Open WebUI tool ids."""
    mapping, dead, _ = _load(path)
    return sorted(
        {
            f"server:mcp:{mapping[tool]}"
            for tool in tools
            if tool in mapping and mapping[tool] not in dead
        }
    )


def all_tools_dead(tools: list[str], path: Path | None = None) -> bool:
    """Return whether every declared tool maps to a server marked dead."""
    if not tools:
        return False
    mapping, dead, _ = _load(path)
    return all(mapping.get(tool) in dead for tool in tools)
