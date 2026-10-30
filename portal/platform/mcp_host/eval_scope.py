"""Evaluation scope for tool calls (WFE production tool mode, root-fix Part 2a).

A WFE row sends `portal_eval` in its request body. The pipeline narrows the
workspace's tools to the scope's allowlist and forwards the scope as `eval` on
every MCP call; each MCP confines the call's files to the run's namespace and
writes a creation receipt. Without a scope nothing changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"^wfe_[0-9a-f]{16,40}$")
EVAL_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar("portal_eval_scope", default=None)
REQUEST_ID: ContextVar[str] = ContextVar("portal_request_id", default="")
EVAL_META_KEY = "portal5/eval"
REQUEST_ID_META_KEY = "portal5/request_id"
TOOL_TIMEOUT_META_KEY = "portal5/timeout_s"


class ScopeError(ValueError):
    """A malformed scope, or a path outside the run's namespace."""


def bind_native_context(mcp: Any, tool_guard: Callable[[str], bool] | None = None) -> None:
    """Bind native MCP metadata to the existing evaluation and request contextvars."""
    call_tool = mcp.call_tool

    async def dispatch(name: str, arguments: dict[str, Any], context: Any) -> Any:
        if tool_guard is not None and not tool_guard(name):
            raise PermissionError(f"{name} is not served by this MCP instance")
        request = getattr(context, "request_context", None)
        params = getattr(request, "params", None)
        meta = params.get("_meta", {}) if isinstance(params, Mapping) else {}
        if not isinstance(meta, Mapping):
            meta = {}
        scope_token = EVAL_SCOPE.set(parse(meta.get(EVAL_META_KEY)))
        request_id = meta.get(REQUEST_ID_META_KEY)
        request_token = REQUEST_ID.set(request_id if isinstance(request_id, str) else "")
        try:
            return await call_tool(name, arguments, context)
        finally:
            REQUEST_ID.reset(request_token)
            EVAL_SCOPE.reset(scope_token)

    mcp.call_tool = dispatch


def parse(raw: Any) -> dict[str, Any] | None:
    """A validated scope from a body's `portal_eval` (pipeline) or `eval` (MCP) field."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScopeError("eval scope must be an object")
    camp, run, allow = raw.get("campaign"), raw.get("run"), raw.get("allow")
    if not (
        isinstance(camp, str) and TOKEN.match(camp) and isinstance(run, str) and TOKEN.match(run)
    ):
        raise ScopeError("eval scope campaign and run must match wfe_<hex>")
    # An empty allowlist is a sandbox row: no workspace tools, but injection still scoped.
    if not (isinstance(allow, list) and all(isinstance(t, str) and t for t in allow)):
        raise ScopeError("eval scope allow must be a list of tool names")
    return {"campaign": camp, "run": run, "allow": sorted(set(allow))}


def bind_route(handler: Any) -> Any:
    """Wrap a Starlette route handler so the request body's `eval` scope is bound while it
    runs. A malformed scope is a 400; a body that is not JSON is left to the handler."""

    async def run(request: Any) -> Any:
        from starlette.responses import JSONResponse  # noqa: PLC0415

        try:
            body = await request.json()
            scope = parse(body.get("eval")) if isinstance(body, dict) else None
        except ScopeError as e:
            return JSONResponse({"error": f"eval scope: {e}"}, status_code=400)
        except Exception:  # noqa: BLE001
            scope = None
        token = EVAL_SCOPE.set(scope)
        try:
            return await handler(request)
        finally:
            EVAL_SCOPE.reset(token)

    return run


def run_root(base: Path | str, scope: dict[str, Any]) -> Path:
    """`<base>/wfe/<campaign>/<run>`, with `base` resolved first; created if absent."""
    root = Path(base).resolve() / "wfe" / scope["campaign"] / scope["run"]
    root.mkdir(parents=True, exist_ok=True)
    return Path(root)


_UPLOAD_PREFIX = "/workspace/uploads/realuse_v1/"


def _row_path(path: str | Path) -> Path:
    """Map `/workspace/uploads/realuse_v1/<rest>` onto the row-relative tree."""
    text = str(path).replace("\\", "/")
    if not text.startswith(_UPLOAD_PREFIX):
        return Path(path)
    rest = text[len(_UPLOAD_PREFIX) :]
    if not rest or any(part in {".", ".."} for part in Path(rest).parts):
        raise ScopeError(f"path outside the evaluation namespace: {path}")
    return Path("realuse_v1") / rest


def confine(base: Path | str, scope: dict[str, Any], path: str | Path, sub: str = "") -> Path:
    """`path` resolved inside the run root (relative paths under `sub`); escapes refused."""
    root = run_root(base, scope)
    p = _row_path(path)
    cand = (p if p.is_absolute() else root / sub / p).resolve()
    if cand != root and root not in cand.parents:
        raise ScopeError(f"path outside the evaluation namespace: {path}")
    return cand


def receipt(base: Path | str, scope: dict[str, Any], tool: str, path: Path | str) -> dict[str, Any]:
    """Append a creation receipt to `<run root>/.receipts.jsonl` and return it."""
    p = confine(base, scope, path)
    data = p.read_bytes()
    # `rel` is what the harness resolves: an MCP in a container sees the run root under its own
    # mount (/app/data/generated/...), the harness under the host's (~/AI_Output/...).
    rec = {
        "tool": tool,
        "path": str(p),
        "rel": str(p.relative_to(run_root(base, scope))),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "utc": time.time(),
    }
    with (run_root(base, scope) / ".receipts.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec
