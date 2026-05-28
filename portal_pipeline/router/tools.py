"""MCP tool dispatch for the chat-completion tool loop.

Houses ``_dispatch_tool_call`` and its private helpers. Calls the shared
``tool_registry`` singleton and workspace tool helpers. Depends on
metrics, state, and tool_registry; never imports router_pipe.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from portal_pipeline.router.metrics import (
    _tool_call_duration,
    _tool_call_errors,
    _tool_calls_total,
)
from portal_pipeline.router.state import _record_error

logger = logging.getLogger(__name__)


async def _dispatch_tool_call(
    tool_call: dict,
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
) -> dict:
    """Whitelist-check and dispatch one model-emitted tool call.

    The single chokepoint between the model's ``tool_calls`` array and
    the registry dispatcher. Every tool the model asks for comes
    through here. **Never raises** — every failure path returns a
    ``tool``-role message with an ``{"error": "..."}`` payload that
    the caller appends to ``messages[]`` and the model interprets.
    This is what lets the streaming tool loop in chunk 3 keep its
    SSE stream alive across tool failures.

    Three failure paths, all metric-tagged and returning an error
    message:

    1. **JSON parse fails** on ``tool_call.function.arguments`` →
       error type ``tool_arg_parse``.
    2. **Tool not whitelisted** for this workspace × persona →
       error type ``tool_not_allowed``. This is the least-privilege
       gate. ``effective_tools`` is resolved by
       ``_resolve_persona_tools`` at the call site; a tool absent
       from that set cannot be called even if the registry has it
       healthy. The split between this whitelist and the registry's
       circuit breaker is deliberate: this is "is this combination
       authorized?", the registry is "is this tool reachable?".
    3. **Registry dispatch returns ``{"error": ...}``** → emitted
       as the tool's content; metrics tag ``tool_call_errors``.

    Records three Prometheus metrics on every dispatch (success or
    error): ``portal5_tool_calls_total``,
    ``portal5_tool_call_duration_seconds``, and
    ``portal5_tool_call_errors_total`` (on error only).

    Lazy-imports the ``tool_registry`` singleton on first call to
    keep test stubbing simple (patch the module attribute before
    any request flows through here).

    Args:
        tool_call: One element of the model's ``tool_calls`` array,
            shaped ``{"id": str, "function": {"name": str,
            "arguments": str (JSON)}}``.
        effective_tools: Authorized tool names for this workspace ×
            persona combination. From ``_resolve_persona_tools``.
        workspace_id: For metric labels and error logging.
        persona: For error-message text and logging.
        request_id: Forwarded to ``tool_registry.dispatch`` for
            cross-log correlation between pipeline and MCP servers.

    Returns:
        A ``tool``-role message dict shaped
        ``{"role": "tool", "tool_call_id": str, "name": str,
        "content": str}`` where ``content`` is JSON-encoded.
    """
    from portal_pipeline.tool_registry import tool_registry

    fn = tool_call.get("function", {})
    tool_name = fn.get("name", "").strip()
    arguments_str = fn.get("arguments", "{}")
    tool_call_id = tool_call.get("id", "")

    # Parse arguments
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        _record_error(workspace_id, "tool_arg_parse")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Invalid JSON arguments: {arguments_str[:200]}"}),
        }

    # Whitelist enforcement
    if tool_name not in effective_tools:
        _record_error(workspace_id, "tool_not_allowed")
        logger.warning(
            "Tool %s called but not in workspace=%s persona=%s whitelist; rejected",
            tool_name,
            workspace_id,
            persona,
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Tool '{tool_name}' not available for {persona}"}),
        }

    # Dispatch via registry
    t0 = time.monotonic()
    result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)
    elapsed = time.monotonic() - t0

    # Metrics
    _tool_calls_total.labels(tool=tool_name, workspace=workspace_id).inc()
    _tool_call_duration.labels(tool=tool_name).observe(elapsed)
    if "error" in result:
        _tool_call_errors.labels(tool=tool_name, workspace=workspace_id).inc()

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
    }
