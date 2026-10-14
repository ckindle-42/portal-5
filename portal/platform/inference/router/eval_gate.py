"""The pipeline side of a WFE evaluation scope (root-fix Part 2a); see mcp_host.eval_scope."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from portal.platform.inference.router.trace import note as trace_note
from portal.platform.mcp_host import eval_scope


def bind_eval_scope(body: dict[str, Any]) -> None:
    """Bind a `portal_eval` scope before the handler's own tool calls (memory and KB
    injection, write-back) so they run inside it too. The scope stays in the body for
    apply_eval_scope, which narrows the tools later."""
    try:
        scope = eval_scope.parse(body.get("portal_eval"))
    except eval_scope.ScopeError as e:
        raise HTTPException(status_code=400, detail=f"portal_eval: {e}") from e
    if scope is not None:
        eval_scope.EVAL_SCOPE.set(scope)
        trace_note(eval=scope)


def apply_eval_scope(body: dict[str, Any], tools: list[str]) -> list[str]:
    """Narrow the workspace's tools to a `portal_eval` scope's allowlist and arm its forwarding
    to every MCP call. A malformed scope is a 400: ignoring it would run unrestricted tools."""
    try:
        scope = eval_scope.parse(body.pop("portal_eval", None))
    except eval_scope.ScopeError as e:
        raise HTTPException(status_code=400, detail=f"portal_eval: {e}") from e
    if scope is None:
        return tools
    eval_scope.EVAL_SCOPE.set(scope)
    trace_note(eval=scope)
    return [t for t in tools if t in scope["allow"]]
