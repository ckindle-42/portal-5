"""Portal 5 — Tool registry for MCP server-backed tools.

Maps tool name -> MCP server URL + tool schema. Loaded at pipeline startup by
discovering tools from each MCP server's /tools endpoint. Registry is the
single source of truth — workspaces and personas reference tools by name.

Refresh: every TOOL_REGISTRY_REFRESH_S seconds, or on POST /admin/refresh-tools.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# MCP server base URLs — env-overridable for development
MCP_SERVERS: dict[str, str] = {
    "documents": os.environ.get("MCP_DOCUMENTS_URL", "http://localhost:8913"),
    "execution": os.environ.get("MCP_EXECUTION_URL", "http://localhost:8914"),
    "security": os.environ.get("MCP_SECURITY_URL", "http://localhost:8919"),
    "comfyui": os.environ.get("MCP_COMFYUI_URL", "http://localhost:8910"),
    "music": os.environ.get("MCP_MUSIC_URL", "http://localhost:8912"),
    "video": os.environ.get("MCP_VIDEO_URL", "http://localhost:8911"),
    "whisper": os.environ.get("MCP_WHISPER_URL", "http://localhost:8915"),
    "tts": os.environ.get("MCP_TTS_URL", "http://localhost:8916"),
    # M3 additions:
    "research": os.environ.get("MCP_RESEARCH_URL", "http://localhost:8922"),
    "memory": os.environ.get("MCP_MEMORY_URL", "http://localhost:8920"),
    "rag": os.environ.get("MCP_RAG_URL", "http://localhost:8921"),
}

TOOL_REGISTRY_REFRESH_S = float(os.environ.get("TOOL_REGISTRY_REFRESH_S", "3600"))
TOOL_DISCOVERY_TIMEOUT_S = 5.0
TOOL_DISPATCH_TIMEOUT_S = float(os.environ.get("TOOL_DISPATCH_TIMEOUT_S", "60"))


@dataclass
class ToolDefinition:
    """A single tool, resolvable to an MCP server."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    server_id: str
    server_url: str
    last_seen: float = 0.0
    healthy: bool = True
    custom_timeout_s: float | None = None  # override TOOL_DISPATCH_TIMEOUT_S

    def to_openai_tool(self) -> dict[str, Any]:
        """Serialize to OpenAI tools array format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Discovers and caches tools from MCP servers. Single source of truth."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._last_refresh: float = 0.0
        self._refresh_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TOOL_DISCOVERY_TIMEOUT_S)
        return self._http

    async def refresh(self, force: bool = False) -> int:
        """Refresh the registry by polling each MCP server's /tools endpoint.

        Returns the number of tools currently registered.
        Only refreshes if TOOL_REGISTRY_REFRESH_S has elapsed (unless force=True).
        """
        async with self._refresh_lock:
            now = time.time()
            if not force and now - self._last_refresh < TOOL_REGISTRY_REFRESH_S:
                return len(self._tools)

            client = await self._client()
            new_tools: dict[str, ToolDefinition] = {}

            async def _discover_one(server_id: str, base_url: str) -> None:
                try:
                    r = await client.get(f"{base_url.rstrip('/')}/tools")
                    if r.status_code != 200:
                        logger.warning("Tool discovery: %s returned %d", server_id, r.status_code)
                        return
                    payload = r.json()
                    tools = payload if isinstance(payload, list) else payload.get("tools", [])
                    for tdef in tools:
                        name = tdef.get("name")
                        if not name:
                            continue
                        new_tools[name] = ToolDefinition(
                            name=name,
                            description=tdef.get("description", ""),
                            parameters=tdef.get("parameters", {}),
                            server_id=server_id,
                            server_url=base_url,
                            last_seen=now,
                        )
                except Exception as e:
                    logger.warning("Tool discovery for %s failed: %s", server_id, e)

            await asyncio.gather(
                *[_discover_one(sid, url) for sid, url in MCP_SERVERS.items()],
                return_exceptions=True,
            )

            # Preserve health flags from previous tools that re-appeared
            for name, tool in new_tools.items():
                if name in self._tools:
                    tool.healthy = self._tools[name].healthy

            self._tools = new_tools
            self._last_refresh = now
            logger.info(
                "Tool registry refreshed: %d tools across %d servers",
                len(self._tools),
                len(MCP_SERVERS),
            )
            return len(self._tools)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_openai_tools(self, names: list[str]) -> list[dict[str, Any]]:
        """Get OpenAI-format tools array, filtered by name list."""
        return [
            self._tools[n].to_openai_tool()
            for n in names
            if n in self._tools and self._tools[n].healthy
        ]

    async def dispatch(
        self, tool_name: str, arguments: dict[str, Any], request_id: str = ""
    ) -> dict[str, Any]:
        """Dispatch a tool call to its MCP server. Returns the tool result."""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Tool '{tool_name}' not in registry — call ignored"}
        if not tool.healthy:
            return {"error": f"Tool '{tool_name}' marked unhealthy by registry"}

        timeout_s = tool.custom_timeout_s or TOOL_DISPATCH_TIMEOUT_S
        url = f"{tool.server_url.rstrip('/')}/tools/{tool_name}"

        try:
            client = await self._client()
            r = await client.post(
                url,
                json={"arguments": arguments, "request_id": request_id},
                timeout=timeout_s,
            )
            if r.status_code == 200:
                return r.json()
            else:
                tool.healthy = False  # Mark unhealthy on non-200; refresh will reset
                return {
                    "error": f"Tool '{tool_name}' returned HTTP {r.status_code}",
                    "detail": r.text[:200],
                }
        except asyncio.TimeoutError:
            return {"error": f"Tool '{tool_name}' timed out after {timeout_s}s"}
        except Exception as e:
            return {"error": f"Tool '{tool_name}' dispatch failed: {e}"}

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None


# Module-level singleton — pipeline imports this and uses it
tool_registry = ToolRegistry()
