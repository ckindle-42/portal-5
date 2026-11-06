"""Production tools the eval allowlist does not offer, answered inside the row's scope."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Parameter names of portal.modules.coding.tools.code_sandbox_mcp.execute_python.
# Kept here so a call can be rejected without importing that module (import creates
# data/sandbox). tests/wfe/tests asserts this tuple against the function source.
EXECUTE_PYTHON_PARAMS = ("code", "timeout", "session_id", "packages")
EXECUTE_PYTHON_REQUIRED = ("code",)
# portal.modules.research.tools.web_search_mcp.web_search
WEB_SEARCH_PARAMS = ("query", "num_results", "time_range")
WEB_SEARCH_REQUIRED = ("query",)
# Same engine pin as web_search_mcp._SEARXNG_ENGINES. SearXNG only: no Brave key, no browser.
_SEARXNG_ENGINES = "bing,mojeek,marginalia,wikipedia,brave,duckduckgo,google"

# A real call would leave the row's namespace or write a store the evaluation must not touch.
UNSAFE_REASONS: dict[str, str] = {
    "generate_part": (
        "generate_part writes the shared models3d directory and publishes to Open WebUI; "
        "cad_render_mcp does not read the eval scope"
    ),
    "render_openscad": (
        "render_openscad runs host openscad into the shared models3d directory and does not "
        "read the eval scope"
    ),
    "compliance_ask": (
        "compliance_ask calls the reading model and stores a derived source; the eval instance "
        "refuses it, and an in-process call would use the operator compliance store"
    ),
    "compliance_context": (
        "compliance_context is not a verified eval-instance tool; calling it in-process opens "
        "the operator compliance store"
    ),
    "compliance_conflicts": (
        "compliance_conflicts is not a verified eval-instance tool; calling it in-process opens "
        "the operator compliance store"
    ),
    "compliance_review_list": (
        "compliance_review_list reads the operator review queue and is refused by the eval instance"
    ),
    "compliance_review_decide_batch": (
        "compliance_review_decide_batch writes the mapping store and is refused by the eval instance"
    ),
}


def register_proxy_tools(dest: dict[str, Callable[[dict, dict], str]]) -> None:
    """Install the production-surface handlers on the harness proxy map."""
    dest["execute_python"] = proxy_execute_python
    dest["web_search"] = proxy_web_search
    for name, reason in UNSAFE_REASONS.items():
        dest[name] = _unsafe(name, reason)


def _reject(name: str, detail: str) -> str:
    return json.dumps({"error": f"Tool '{name}' rejected the arguments", "detail": detail})


def _check_args(
    name: str, args: dict, accepted: tuple[str, ...], required: tuple[str, ...]
) -> str | None:
    unknown = sorted(set(args) - set(accepted))
    if unknown:
        return _reject(
            name,
            f"unexpected keyword argument(s) {unknown}; accepted: {sorted(accepted)}",
        )
    missing = [
        key
        for key in required
        if key not in args
        or args[key] is None
        or (isinstance(args[key], str) and not args[key].strip())
    ]
    if missing:
        return _reject(name, f"missing required argument(s) {missing}")
    return None


def _exclude(ctx: dict, name: str, reason: str) -> None:
    ctx.setdefault("scoring_excluded", []).append({"tool": name, "reason": reason})


def _defined(name: str, reason: str) -> str:
    return json.dumps(
        {
            "error": f"Tool '{name}' is not executed in this evaluation",
            "excluded_from_scoring": True,
            "reason": reason,
        }
    )


def _unsafe(name: str, reason: str) -> Callable[[dict, dict], str]:
    def answer(args: dict, ctx: dict) -> str:
        _exclude(ctx, name, reason)
        return _defined(name, reason)

    return answer


def scoped_mcp_call(base_url: str, name: str, arguments: dict, scope: dict) -> Any:
    """One native MCP call carrying the row's eval scope. Tests replace this."""
    import asyncio

    import httpx

    from portal.platform.inference.mcp_http import call_tool, map_tool_result
    from portal.platform.mcp_host.eval_scope import EVAL_META_KEY

    async def _run() -> Any:
        async with httpx.AsyncClient() as client:
            result = await call_tool(
                client,
                base_url,
                name,
                arguments,
                120,
                metadata={EVAL_META_KEY: scope},
            )
            return map_tool_result(result)

    return asyncio.run(_run())


def proxy_execute_python(args: dict, ctx: dict) -> str:
    """execute_python on the sandbox MCP, scoped to this row the way the pipeline forwards it."""
    rejected = _check_args("execute_python", args, EXECUTE_PYTHON_PARAMS, EXECUTE_PYTHON_REQUIRED)
    if rejected:
        return rejected
    from tests.wfe.eval_mode import mcp_url

    url = mcp_url("WFE_SANDBOX_MCP_URL", "SANDBOX_HOST_PORT", 8914)
    try:
        result = scoped_mcp_call(url, "execute_python", args, ctx["scope"])
    except Exception as exc:  # noqa: BLE001 — an unreachable sandbox is an instrument gap
        reason = f"sandbox MCP unreachable: {exc}"
        _exclude(ctx, "execute_python", reason)
        return _defined("execute_python", reason)
    return result if isinstance(result, str) else json.dumps(result)


def searxng_search(query: str, num_results: int, time_range: str) -> dict:
    """Read-only SearXNG search, the local backend production uses when no Brave key is set."""
    from tests.wfe.eval_mode import setting

    engines = setting("SEARXNG_ENGINES", _SEARXNG_ENGINES)
    params = {
        "q": query,
        "format": "json",
        "categories": "general",
        "engines": engines,
    }
    if time_range != "any":
        params["time_range"] = time_range
    url = setting("SEARXNG_URL", "http://localhost:8088").rstrip("/") + "/search?"
    url += urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — local SearXNG
        body = json.loads(resp.read().decode())
    rows = body.get("results", []) if isinstance(body, dict) else []
    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": str(item.get("content", ""))[:500],
            "engine": item.get("engine", ""),
            "published": item.get("publishedDate", "") or "",
        }
        for item in rows[:num_results]
        if isinstance(item, dict)
    ]
    return {"query": query, "num_results": len(results), "results": results}


def _web_search_numbers(args: dict) -> tuple[int, str] | str:
    raw = args.get("num_results", 5)
    try:
        num = int(raw)
    except (TypeError, ValueError):
        return _reject("web_search", "num_results must be an integer")
    num = min(max(num, 1), 20)
    time_range = args.get("time_range", "any")
    if not isinstance(time_range, str):
        return _reject("web_search", "time_range must be a string")
    return num, time_range


def proxy_web_search(args: dict, ctx: dict) -> str:
    """SearXNG only. The query is recorded on the row; an unreachable engine excludes the row."""
    rejected = _check_args("web_search", args, WEB_SEARCH_PARAMS, WEB_SEARCH_REQUIRED)
    if rejected:
        return rejected
    parsed = _web_search_numbers(args)
    if isinstance(parsed, str):
        return parsed
    num, time_range = parsed
    query = str(args["query"])
    ctx.setdefault("web_search_queries", []).append(query)
    try:
        return json.dumps(searxng_search(query, num, time_range))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        reason = f"SearXNG unreachable: {exc}"
        _exclude(ctx, "web_search", reason)
        return _defined("web_search", reason)


# The nine tools round 2 executes. Schemas come from the manifests align_native_tools
# publishes (tool_registry's inputSchema); web_search has no manifest and uses tools/list.
PROMPT_NAMED_TOOLS = ("execute_python", "web_search", *tuple(sorted(UNSAFE_REASONS)))
_REPO = Path(__file__).resolve().parents[2]
_manifest_schemas: dict[str, dict] | None = None


def _openai_tool(name: str, description: str, parameters: dict) -> dict:
    """ToolDefinition.to_openai_tool: name, description, parameters only."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _manifest_schemas_by_name() -> dict[str, dict]:
    """OpenAI schemas from config/inference/tools_manifest_*.json, the published source."""
    global _manifest_schemas
    if _manifest_schemas is not None:
        return _manifest_schemas
    found: dict[str, dict] = {}
    root = _REPO / "config" / "inference"
    for path in sorted(root.glob("tools_manifest_*.json")):
        data = json.loads(path.read_text())
        tools = data if isinstance(data, list) else data.get("tools") or []
        for item in tools:
            if not isinstance(item, dict):
                continue
            fn = item["function"] if isinstance(item.get("function"), dict) else item
            name = fn.get("name")
            if not isinstance(name, str) or name in found:
                continue
            found[name] = _openai_tool(
                name,
                str(fn.get("description") or ""),
                fn.get("parameters") or fn.get("inputSchema") or {},
            )
    _manifest_schemas = found
    return found


def _web_search_schema() -> dict:
    """web_search as research MCP tools/list publishes it (no tools manifest)."""
    import asyncio

    from portal.modules.research.tools.web_search_mcp import mcp

    tool = next(item for item in asyncio.run(mcp.list_tools()) if item.name == "web_search")
    return _openai_tool(tool.name, tool.description or "", dict(tool.input_schema))


def production_schema(name: str) -> dict | None:
    """The schema production advertises for one tool, or None when it has no source."""
    schemas = _manifest_schemas_by_name()
    if name in schemas:
        return schemas[name]
    if name == "web_search":
        schemas["web_search"] = _web_search_schema()
        return schemas["web_search"]
    return None


def offered_schemas(declared: list[str], allow: list[str]) -> list[dict]:
    """Production schemas for prompt-named tools this workspace has off the allowlist."""
    want = sorted(set(declared) & set(PROMPT_NAMED_TOOLS) - set(allow))
    out = []
    for name in want:
        schema = production_schema(name)
        if schema is not None:
            out.append(schema)
    return out
