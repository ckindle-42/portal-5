"""Host-native analyst surface for the grounded, replay-only security reviewer.

The reviewer reads indexed Splunk telemetry and writes only its private local run,
concern, and verdict stores. Every concern remains a candidate until an analyst records
a verdict. This server has no attack, emulation, or target-execution tools.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

from mcp.server import MCPServer
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.security.core.review.contracts import Verdict, to_plain
from portal.modules.security.core.review.service import (
    ReviewRequest,
    ReviewRuntime,
    build_default_runtime,
)
from portal.modules.security.core.review.window import SourceSpec
from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
_port = int(os.environ.get("REVIEW_MCP_PORT") or os.environ.get("MCP_PORT", "8943"))
mcp = MCPServer(
    "Portal Security Review",
    instructions=(
        "Read-only review of already-indexed security telemetry. Concerns are candidates with "
        "checkable evidence; the analyst decides. No attack, emulation, or target-execution tools."
    ),
)
TOOLS_MANIFEST: list[dict[str, Any]] = load_data("config/security", "tools_manifest_review_mcp")
_runtime: ReviewRuntime | None = None


def _get_runtime() -> ReviewRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_default_runtime()
    return _runtime


def _guard(tool: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 -- surface failures in the tool response
        logger.exception("review tool %s failed", tool)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _plain_dict(value: Any) -> dict[str, Any]:
    plain = to_plain(value)
    if not isinstance(plain, dict):
        raise TypeError("review response did not serialize to an object")
    return plain


@mcp.tool()
def review_start(
    sources: list[dict[str, str]],
    start: float,
    end: float,
    environment_id: str | None = None,
) -> dict[str, Any]:
    """Start an asynchronous review of explicit indexed sources and an epoch time window."""

    def start_run() -> dict[str, Any]:
        runtime = _get_runtime()
        source_specs = [
            SourceSpec(index=item["index"], sourcetype=item["sourcetype"]) for item in sources
        ]
        request = ReviewRequest(
            sources=source_specs,
            start=start,
            end=end,
            environment_id=environment_id or runtime.environment_id,
            config=runtime.config,
        )
        run_id = runtime.start(request)
        record = runtime.status(run_id)
        return {
            "run_id": run_id,
            "status": record.status.value if record is not None else "QUEUED",
        }

    return _guard("review_start", start_run)


@mcp.tool()
def review_status(run_id: str) -> dict[str, Any]:
    """Read the persisted status and progress of one review run."""

    def get_status() -> dict[str, Any]:
        record = _get_runtime().status(run_id)
        return {"error": f"unknown run {run_id!r}"} if record is None else to_plain(record)

    return _guard("review_status", get_status)


@mcp.tool()
def review_result(run_id: str) -> dict[str, Any]:
    """Read a completed review result, or the current status while it is still running."""

    def get_result() -> dict[str, Any]:
        runtime = _get_runtime()
        record = runtime.status(run_id)
        if record is None:
            return {"error": f"unknown run {run_id!r}"}
        if record.result is None:
            return {"run_id": run_id, "status": record.status.value, "progress": record.progress}
        return record.result

    return _guard("review_result", get_result)


@mcp.tool()
def review_cancel(run_id: str) -> dict[str, Any]:
    """Request cancellation at the next review checkpoint."""
    return _guard(
        "review_cancel", lambda: {"run_id": run_id, "cancelled": _get_runtime().cancel(run_id)}
    )


@mcp.tool()
def review_verdict(
    concern_id: str,
    verdict: str,
    actor: str,
    note: str = "",
) -> dict[str, Any]:
    """Record the analyst's something, nothing, or unsure verdict for a concern."""

    def record_verdict() -> dict[str, Any]:
        writeback = _get_runtime().verdict(concern_id, Verdict(verdict), actor=actor, note=note)
        return _plain_dict(writeback)

    return _guard("review_verdict", record_verdict)


@mcp.tool()
def review_queue(limit: int | None = None) -> dict[str, Any]:
    """List concerns that still need an analyst decision."""

    def get_queue() -> dict[str, Any]:
        runtime = _get_runtime()
        concerns = runtime.queue() if limit is None else runtime.queue(limit=limit)
        return {"count": len(concerns), "concerns": to_plain(concerns)}

    return _guard("review_queue", get_queue)


@mcp.tool()
def review_explain(concern_id: str) -> dict[str, Any]:
    """Return concern claims and the verbatim reviewer-visible text of every cited event."""
    return _guard("review_explain", lambda: _get_runtime().explain(concern_id))


@mcp.tool()
def review_doctor(fix: bool = False) -> dict[str, Any]:
    """Check Splunk, reasoning models, databases, and embedder-bound calibrations."""
    return _guard("review_doctor", lambda: _get_runtime().doctor(fix=fix))


_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "review_start": review_start,
    "review_status": review_status,
    "review_result": review_result,
    "review_cancel": review_cancel,
    "review_verdict": review_verdict,
    "review_queue": review_queue,
    "review_explain": review_explain,
    "review_doctor": review_doctor,
}


def _route(
    path: str,
    methods: list[str],
    name: str | None = None,
    include_in_schema: bool = True,
) -> Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]]:
    return cast(
        Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
        mcp.custom_route(path, methods=methods, name=name, include_in_schema=include_in_schema),
    )


@_route("/ready", methods=["GET"])
async def ready(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "review-mcp", "port": _port})


@_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "review-mcp", "port": _port})


@_route("/tools", methods=["GET"])
async def list_tools(_request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOLS_MANIFEST})


@_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request: Request) -> JSONResponse:
    name = str(request.path_params.get("tool_name", ""))
    function = _DISPATCH.get(name)
    if function is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    arguments = body.get("arguments", body) if isinstance(body, dict) else {}
    if not isinstance(arguments, dict):
        return JSONResponse({"error": "arguments must be an object"}, status_code=400)
    try:
        result = await run_in_threadpool(functools.partial(function, **arguments))
        return JSONResponse(result)
    except TypeError as exc:
        return JSONResponse({"error": f"bad params: {exc}"}, status_code=400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("review REST dispatch %s failed", name)
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
