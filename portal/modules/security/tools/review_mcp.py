"""Host-native analyst surface for the grounded, replay-only security reviewer.

The reviewer reads indexed Splunk telemetry and writes only its private local run,
concern, and verdict stores. Every concern remains a candidate until an analyst records
a verdict. This server has no attack, emulation, or target-execution tools.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.security.core.hunt import jobs as hunt_jobs
from portal.modules.security.core.hunt import product_jobs as r2_hunt_jobs
from portal.modules.security.core.review.contracts import Verdict, to_plain
from portal.modules.security.core.review.service import (
    ReviewRequest,
    ReviewRuntime,
    build_default_runtime,
)
from portal.modules.security.core.review.window import SourceSpec
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.tool_support import tool_result_byte_budget

logger = logging.getLogger(__name__)
_port = int(os.environ.get("REVIEW_MCP_PORT") or os.environ.get("MCP_PORT", "8943"))
mcp = MCPServer(
    "Portal Security Review",
    instructions=(
        "Read-only review of already-indexed security telemetry. Concerns are candidates with "
        "checkable evidence; the analyst decides. No attack, emulation, or target-execution tools."
    ),
)
_runtime: ReviewRuntime | None = None
_HUNT_TOOLS = frozenset({"hunt_sources", "hunt_start", "hunt_status", "hunt_leads", "hunt_case"})


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


@lru_cache(maxsize=1)
def _hunt_result_byte_limit() -> int:
    path = Path(__file__).resolve().parents[4] / "config" / "portal.yaml"
    config = yaml.safe_load(path.read_text()) or {}
    contexts = [
        int(workspace["context_limit"])
        for workspace in (config.get("workspaces") or {}).values()
        if _HUNT_TOOLS.intersection(workspace.get("tools", [])) and workspace.get("context_limit")
    ]
    if not contexts:
        raise RuntimeError("no configured workspace carries the hunt tools")
    return tool_result_byte_budget(min(contexts)) // 8


def _hunt_guard(tool: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    result = _guard(tool, fn)
    try:
        limit = _hunt_result_byte_limit()
    except Exception as exc:  # noqa: BLE001 -- return a compact tool error
        return {"error": f"hunt output limit unavailable: {type(exc).__name__}"}
    size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size <= limit:
        return result
    return {
        "error": "hunt response exceeds the configured tool-loop result limit",
        "result_bytes": size,
        "max_bytes": limit,
    }


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


def _hunt_search() -> Any:
    from portal.modules.security.core.review.window import SplunkWindowSource

    return SplunkWindowSource(timeout_seconds=600)


@mcp.tool()
def hunt_sources(job_id: str | None = None, index: str | None = None, n: int = 3) -> dict[str, Any]:
    """List a run's source cards, or available indexes when no run selector is supplied."""

    if job_id or index:
        return _hunt_guard("hunt_sources", lambda: r2_hunt_jobs.sources_view(job_id, index, n))

    def run() -> dict[str, Any]:
        rows = _hunt_search().iter_post(
            "| tstats count min(_time) as first max(_time) as last where index=* by index",
            0,
            time.time(),
        )
        selected = [
            {"index": str(row.get("index") or "")[:80], "events": row.get("count")}
            for row in rows[: max(0, min(n, 3))]
        ]
        return {
            "total_indexes": len(rows),
            "indexes": selected,
            "indexes_omitted": len(rows) - len(selected),
        }

    return _hunt_guard("hunt_sources", run)


@mcp.tool()
def hunt_start(
    index: str,
    start: float | None = None,
    end: float | None = None,
    query_seconds: float = 30.0,
    job_seconds: float = 1260.0,
    request_budget: int = 2000,
    cell_budget: int = 10000,
    event_budget: int = 5000,
    judge: bool = False,
) -> dict[str, Any]:
    """Start an R2 Stage 1 hunt, optionally annotating its top leads with the judge."""

    def run() -> dict[str, Any]:
        start_t = 0.0 if start is None else start
        end_t = time.time() if end is None else end
        job_id = r2_hunt_jobs.start(
            _hunt_search(),
            index,
            start_t,
            end_t,
            {
                "query_seconds": query_seconds,
                "job_seconds": job_seconds,
                "requests": request_budget,
                "cells": cell_budget,
                "events": event_budget,
            },
            judge_enabled=judge,
        )
        nxt = (
            f"call hunt_status(job_id={job_id!r}); if still RUNNING, report the stage and ask "
            f"the user to request results later. Once COMPLETE, PARTIAL, or FAILED, call "
            f"hunt_sources, hunt_leads, "
            f"and hunt_case(job_id={job_id!r}, case=1)"
        )
        return hunt_jobs.compact(
            {
                "job_id": job_id,
                "index": index,
                "judge_enabled": judge,
                "status": "QUEUED",
                "next": nxt,
            }
        )

    return _hunt_guard("hunt_start", run)


@mcp.tool()
def hunt_status(job_id: str | None = None, index: str | None = None) -> dict[str, Any]:
    """Wait for an R2 hunt and return its bounded compact status."""
    kwargs: dict[str, Any] = {"wait_seconds": r2_hunt_jobs.STATUS_WAIT_MAX_S}
    return _hunt_guard("hunt_status", lambda: r2_hunt_jobs.status(job_id, index, **kwargs))


@mcp.tool()
def hunt_leads(
    job_id: str | None = None,
    index: str | None = None,
    n: int = r2_hunt_jobs.LEADS_VIEW_DEFAULT,
) -> dict[str, Any]:
    """Return compact ranked R2 leads with one explanation and evidence query each."""
    return _hunt_guard("hunt_leads", lambda: r2_hunt_jobs.leads_view(job_id, index, n))


@mcp.tool()
def hunt_case(
    job_id: str | None = None, index: str | None = None, case: int = 1, n: int = 2
) -> dict[str, Any]:
    """Return a case anchor, seed count, and a few evidence lines."""
    return _hunt_guard("hunt_case", lambda: r2_hunt_jobs.case_view(job_id, index, case, n))


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


bind_native_context(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
