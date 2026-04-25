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


def _backoff_seconds(failures: int) -> float:
    """Backoff schedule: 30s, 2m, 5m, 15m, 1h, capped."""
    schedule = [30, 120, 300, 900, 3600]
    return float(schedule[min(failures - 1, len(schedule) - 1)])


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
    next_retry_at: float = 0.0        # epoch seconds; 0 = retry allowed immediately
    consecutive_failures: int = 0     # for exponential backoff calc

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

            # Preserve backoff state from previous tools that re-appeared
            for name, tool in new_tools.items():
                if name in self._tools:
                    prev = self._tools[name]
                    tool.healthy = prev.healthy
                    tool.consecutive_failures = prev.consecutive_failures
                    tool.next_retry_at = prev.next_retry_at

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
        """Get OpenAI-format tools array, filtered by name list.

        A tool is included if healthy or if its backoff window has elapsed.
        """
        now = time.time()
        result = []
        for n in names:
            t = self._tools.get(n)
            if t is None:
                continue
            if t.healthy or now >= t.next_retry_at:
                result.append(t.to_openai_tool())
        return result

    async def dispatch(
        self, tool_name: str, arguments: dict[str, Any], request_id: str = ""
    ) -> dict[str, Any]:
        """Dispatch a tool call to its MCP server. Returns the tool result."""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Tool '{tool_name}' not in registry — call ignored"}

        now = time.time()
        if not tool.healthy and now < tool.next_retry_at:
            remaining = int(tool.next_retry_at - now)
            return {
                "error": f"Tool '{tool_name}' in backoff (retry in {remaining}s after "
                         f"{tool.consecutive_failures} consecutive failures)"
            }

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
                tool.healthy = True
                tool.consecutive_failures = 0
                tool.next_retry_at = 0.0
                return r.json()
            else:
                tool.consecutive_failures += 1
                tool.healthy = False
                tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
                return {
                    "error": f"Tool '{tool_name}' returned HTTP {r.status_code}",
                    "detail": r.text[:200],
                }
        except asyncio.TimeoutError:
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' timed out after {timeout_s}s"}
        except Exception as e:
            tool.consecutive_failures += 1
            tool.healthy = False
            tool.next_retry_at = now + _backoff_seconds(tool.consecutive_failures)
            return {"error": f"Tool '{tool_name}' dispatch failed: {e}"}

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None


# Module-level singleton — pipeline imports this and uses it
tool_registry = ToolRegistry()
