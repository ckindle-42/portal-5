"""The pipeline side of a WFE evaluation scope (root-fix Part 2a); see mcp_host.eval_scope."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
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


def bind_attached_uploads(body: Mapping[str, Any]) -> None:
    """Bind the OWUI attachment ids of this request (body["files"]) for MCP forwarding, so the
    code sandbox can mount exactly those uploads and nothing else of the user file store."""
    files = body.get("files")
    ids = [f.get("id") for f in files if isinstance(f, Mapping)] if isinstance(files, list) else []
    eval_scope.ATTACHED_UPLOADS.set(eval_scope.upload_ids(ids))


def apply_eval_scope(body: dict[str, Any], tools: list[str]) -> list[str]:
    """Narrow the workspace's tools to a `portal_eval` scope's allowlist and arm its forwarding
    to every MCP call. A malformed scope is a 400: ignoring it would run unrestricted tools."""
    try:
        scope = eval_scope.parse(body.pop("portal_eval", None))
    except eval_scope.ScopeError as e:
        raise HTTPException(status_code=400, detail=f"portal_eval: {e}") from e
    offered = tools if scope is None else [t for t in tools if t in scope["allow"]]
    if scope is not None:
        eval_scope.EVAL_SCOPE.set(scope)
        trace_note(eval=scope)
    return offered


def offered_tool_names(body: Mapping[str, Any]) -> list[str]:
    """Return the tool names present in the backend request schemas."""
    schemas = body.get("tools")
    if not isinstance(schemas, list):
        return []
    names = []
    for schema in schemas:
        if not isinstance(schema, dict) or not isinstance(schema.get("function"), dict):
            continue
        name = schema["function"].get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return sorted(names)


def resolve_bite_tool_pool(
    body: dict[str, Any],
    default_persona: str,
    workspace_id: str,
    personas: Mapping[str, Any],
    workspaces: Mapping[str, Any],
    resolve_tools: Callable[[Any, str], list[str]],
) -> list[str]:
    """Resolve and remove the bite-only tool persona selector."""
    supplied = "portal_bite_persona" in body
    requested = body.pop("portal_bite_persona", None)
    if "portal_bite_tools" not in body or not supplied:
        return resolve_tools(personas.get(default_persona, {}), workspace_id)
    if not isinstance(requested, str) or (
        requested not in personas and requested not in workspaces
    ):
        raise HTTPException(status_code=400, detail="portal_bite_persona must name a known persona")
    if requested in personas:
        # A persona inherits its tools from its own workspace_model, not the serving seat's.
        persona = personas[requested]
        parent = (
            persona.get("workspace_model")
            if isinstance(persona, Mapping)
            else getattr(persona, "workspace_model", None)
        )
        return resolve_tools(persona, parent or workspace_id)
    return resolve_tools({}, requested)


def filter_bite_client_tools(
    body: dict[str, Any],
    bite_allowlist: set[str] | None,
    effective_tools: Collection[str],
    registered_tools: Collection[str],
) -> None:
    """Remove registered Pipeline schemas outside the bite's effective tool pool."""
    if bite_allowlist is None:
        return
    denied = set(registered_tools) - set(effective_tools)
    client_tools = body.get("tools")
    if isinstance(client_tools, list):
        body["tools"] = [
            tool
            for tool in client_tools
            if not (
                isinstance(tool, dict)
                and isinstance(tool.get("function"), dict)
                and tool["function"].get("name") in denied
            )
        ]


def apply_bite_tool_scope(
    body: dict[str, Any], tools: list[str]
) -> tuple[list[str], set[str] | None]:
    """Intersect pipeline tools with a request's bite allowlist when supplied."""
    if "portal_bite_tools" not in body:
        return tools, None
    requested = body.pop("portal_bite_tools")
    if not isinstance(requested, list) or not all(
        isinstance(name, str) and name for name in requested
    ):
        raise HTTPException(status_code=400, detail="portal_bite_tools must be a list of names")
    allowed = set(requested)
    client_tools = body.get("tools")
    if isinstance(client_tools, list):
        body["tools"] = [
            tool
            for tool in client_tools
            if isinstance(tool, dict) and (tool.get("function") or {}).get("name") in allowed
        ]
    else:
        body.pop("tools", None)
    return [name for name in tools if name in allowed], allowed
