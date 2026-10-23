"""Helpers for keeping native MCP tools aligned with Portal's REST contracts."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from starlette.responses import Response

from portal.platform.mcp_host.eval_scope import TOOL_TIMEOUT_META_KEY

if TYPE_CHECKING:
    from mcp.types import Tool


def _manifest_tools(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return each manifest entry in its flat tool shape."""
    return [
        item["function"] if isinstance(item.get("function"), dict) else item for item in manifest
    ]


def align_native_tools(mcp: Any, manifest: list[dict[str, Any]]) -> None:
    """Publish REST names, descriptions, schemas, and timeouts through native tools/list."""
    native_list = getattr(mcp, "list_tools", None)
    if not callable(native_list):
        return

    async def list_tools() -> list[Tool]:
        from mcp.types import Tool

        registered = {tool.name: tool for tool in await native_list()}
        aligned = []
        for definition in _manifest_tools(manifest):
            tool = registered.get(definition.get("name", ""))
            if tool is None:
                continue
            meta = dict(tool.meta or {})
            timeout_s = definition.get("timeout_s")
            if timeout_s is not None:
                meta[TOOL_TIMEOUT_META_KEY] = timeout_s
            aligned.append(
                Tool(
                    name=definition["name"],
                    title=tool.title,
                    description=definition.get("description", ""),
                    input_schema=definition.get("parameters", definition.get("inputSchema", {})),
                    output_schema=tool.output_schema,
                    annotations=tool.annotations,
                    icons=tool.icons,
                    _meta=meta or None,
                )
            )
        return aligned

    mcp.list_tools = list_tools


class _ToolRequest:
    """Small request stand-in for calling an existing JSON REST handler in-process."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


async def call_json_route(
    handler: Callable[..., Awaitable[Response]],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call a JSON REST handler with tool arguments and return its response body."""
    from portal.platform.mcp_host.eval_scope import EVAL_SCOPE

    body: dict[str, Any] = {"arguments": arguments}
    scope = EVAL_SCOPE.get()
    if scope is not None:
        body["eval"] = scope
    response = await handler(cast(Any, _ToolRequest(body)))
    payload = json.loads(bytes(response.body))
    if not isinstance(payload, dict):
        raise TypeError("REST tool response must be a JSON object")
    return payload
