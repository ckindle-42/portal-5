"""Sections — one production tool of each stateful MCP, through the Pipeline.

Each hop drives the workspace that whitelists the tool under its own correlation id,
then reads that turn's ``/v1/trace`` record for the tool span and the service's own
store for the value the call produced. The wiki MCP has no workspace tool, so its
hop calls the tool the Pipeline would.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference import mcp_http

from . import media
from .context import TraceContext, env_value
from .model import Hop, Status, short
from .workspaces import StreamedTurn, stream_turn

Runner = Callable[[TraceContext, dict[str, Any]], list[Hop]]
#: The workspace's own predict_limit governs: a tool call plus its answer must fit.
MAX_TOKENS: int | None = None
TABLE = "portal_trace_probe"
MARKER = "40895"
REQUIREMENT = "CIP-007-6 R1 Part 1.2"
#: The KB ``trace-seed-rag`` builds from real repo docs; the rag hop prefers it.
SEED_KB = "portal-trace-docs"
RAG_QUERY = "security patch management"


def servers() -> dict[str, str]:
    """Pipeline-exposed MCP base URLs, from the same roster the tool registry reads."""
    from portal.platform.inference.config import get_pipeline_mcp_servers, load_portal_config

    return get_pipeline_mcp_servers(load_portal_config())


def mcp_call(
    url: str, name: str, arguments: dict[str, Any], timeout: float = 60.0
) -> dict[str, Any]:
    """One native MCP call; an error comes back as data, never raised."""

    async def call() -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return mcp_http.map_tool_result(
                await mcp_http.call_tool(client, url, name, arguments, timeout)
            )

    try:
        payload = asyncio.run(call())
    except (mcp_http.MCPHTTPError, httpx.HTTPError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return payload if isinstance(payload, dict) else {"result": payload}


def span_tools(record: Any) -> tuple[set[str], str]:
    """Tool names that completed ok in one trace record, plus what its spans say."""
    spans = [
        span
        for span in (record.get("spans") if isinstance(record, dict) else None) or []
        if isinstance(span, dict) and span.get("name") == "tool.completed"
    ]
    ok = {str(span.get("tool")) for span in spans if span.get("outcome") == "ok"}
    refused = [f"{s.get('tool')}:{s.get('outcome')}" for s in spans if s.get("outcome") != "ok"]
    observed = f"tools={','.join(sorted(ok)) or 'none'}"
    return ok, observed + (f" refused={','.join(refused)}" if refused else "")


def trace_tools(ctx: TraceContext, cid: str) -> tuple[set[str], str]:
    """The tool spans of this exact turn, read back from the Pipeline's trace store.

    A streaming turn writes its record from the generator's ``finally``, so a read
    that lands between the last byte and that write is re-read once."""
    headers = {"Authorization": f"Bearer {ctx.api_key}"} if ctx.api_key else {}
    ok: set[str] = set()
    observed = ""
    for attempt in (0, 1):
        try:
            response = httpx.get(
                f"{ctx.pipeline_url}/v1/trace/{cid}", headers=headers, timeout=15.0
            )
            response.raise_for_status()
            ok, observed = span_tools(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return set(), f"trace unreadable: {short(exc, 50)}"
        if ok or attempt:
            return ok, observed
        time.sleep(0.5)
    return ok, observed


def turn(ctx: TraceContext, model: str, prompt: str) -> tuple[StreamedTurn, set[str], str]:
    """One Pipeline turn under a known correlation id, with its trace's tool spans."""
    if not ctx.api_key:
        return StreamedTurn(0, error="PIPELINE_API_KEY unset"), set(), "not run: no key"
    cid = f"p5-{uuid.uuid4().hex[:12]}"
    streamed = stream_turn(
        ctx.pipeline_url,
        ctx.api_key,
        model,
        ctx.timeout_s,
        max_tokens=MAX_TOKENS,
        prompt=prompt,
        cid=cid,
    )
    ok, observed = trace_tools(ctx, cid)
    return streamed, ok, observed


def hop(name: str, ok: bool, observed: str, expected: str, turn_: StreamedTurn) -> Hop:
    if turn_.error.startswith("PIPELINE_API_KEY"):
        return Hop(name, Status.WARN, observed, expected, turn_.error)
    detail = "" if ok else short(turn_.error or turn_.body or turn_.stats.text, 70)
    return Hop(name, Status.PASS if ok else Status.FAIL, observed, expected, detail)


def file_hop(_ctx: TraceContext, link: str) -> str:
    """Fetch a published artifact from Open WebUI; the bytes are the proof it exists."""
    response, error = media.fetch_file(link, env_value("OWUI_API_KEY"))
    if response is None:
        return f"fetch failed: {short(error, 40)}"
    kind = response.headers.get("content-type", "").split(";")[0]
    return (
        f"{response.status_code} {kind} {len(response.content)}B "
        f"xlsx={response.content[:2] == b'PK'}"
    )


def documents(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """A generated workbook exists as bytes the user can download, not just a claim."""
    token = f"pt{uuid.uuid4().hex[:8]}"
    streamed, ok, observed = turn(
        ctx,
        "auto-documents",
        f"Call create_excel exactly once with title '{token}' and data "
        f"[['marker', 'value'], ['{token}', 42]]. Then reply with only the download_url "
        "that tool returned.",
    )
    link = media.artifact_url(streamed.stats.text)
    artifact = file_hop(ctx, link) if link else "no download link in the answer"
    done = "create_excel" in ok and artifact.startswith("200") and "xlsx=True" in artifact
    return [
        hop(
            "documents excel artifact",
            done,
            f"{observed} artifact={artifact}",
            "create_excel + a fetchable workbook",
            streamed,
        )
    ]


def memory(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """A remembered marker is recallable from the live store, then forgotten."""
    registry = servers()
    token = f"pt-{uuid.uuid4().hex[:8]}"
    streamed, ok, observed = turn(
        ctx,
        "auto-research",
        f"Call remember exactly once with text 'portal trace marker {token}' and tags "
        "['portal-trace']. Then call recall with query 'portal trace marker' and tags "
        "['portal-trace']. Reply with only the number of memories it returned.",
    )
    found = mcp_call(registry["memory"], "recall", {"query": token, "tags": ["portal-trace"]})
    rows = found.get("memories") or found.get("results") or []
    hit = next((row for row in rows if token in str(row.get("text", ""))), None)
    forgotten = "not run"
    if hit is not None:
        forgot = mcp_call(registry["memory"], "forget", {"id": str(hit.get("id", ""))})
        forgotten = "ok" if "error" not in forgot else short(forgot["error"], 40)
    done = "remember" in ok and hit is not None and forgotten == "ok"
    observed += f" recalled={len(rows)} forgotten={forgotten}"
    return [hop("memory round trip", done, observed, "remember + recall + forget", streamed)]


def rag(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """A retrieval answer names a source file the live KB's own search returns."""
    registry = servers()
    listed = mcp_call(registry["rag"], "kb_list", {})
    kbs = [kb for kb in listed.get("knowledge_bases") or [] if kb.get("chunks")]
    if not kbs:
        reason = short(listed.get("error") or "no knowledge base holds chunks", 60)
        return [
            Hop(
                "rag retrieval",
                Status.WARN,
                f"not run: {reason}",
                "a loaded knowledge base",
                "seed one: portal trace-seed-rag",
            )
        ]
    # Any loaded KB proves retrieval; the seed's own KB keeps the hop deterministic.
    kb_id = str(next((kb["kb_id"] for kb in kbs if kb.get("kb_id") == SEED_KB), kbs[0]["kb_id"]))
    streamed, ok, observed = turn(
        ctx,
        "auto-research",
        f"Call kb_search exactly once with kb_id '{kb_id}' and query '{RAG_QUERY}'. Reply with "
        "only the source_file of the first result.",
    )
    store = mcp_call(registry["rag"], "kb_search", {"kb_id": kb_id, "query": RAG_QUERY, "top_k": 3})
    sources = {str(row.get("source_file") or "") for row in store.get("results") or []}
    named = sorted(name for name in sources if name and name in streamed.stats.text)
    done = "kb_search" in ok and bool(named)
    observed += f" kb={kb_id} cited={named[0] if named else 'none'}"
    return [hop("rag retrieval", done, observed, f"{kb_id} source_file in the answer", streamed)]


def wiki(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """No workspace whitelists a wiki tool, so the hop calls the tool the Pipeline would."""
    found = mcp_call(servers()["wiki"], "wiki_search", {"query": "workspace routing", "top_k": 3})
    rows = found.get("results") or []
    unit = str(rows[0].get("unit_id") or "") if rows else ""
    path = Path(ctx.repo_root) / "portal_wiki" / "canonical" / f"{unit}.md"
    body = path.read_text(encoding="utf-8") if path.is_file() else ""
    preview = str(rows[0].get("preview") or "") if rows else ""
    # The unit ranked first must be the canonical file it serves, and a design unit
    # must outrank a `-s0*` acceptance section on this query (TASK_WIKI_ZERO_DEBT_V1 P7).
    real = bool(unit) and bool(body) and bool(preview) and preview[:60] in body
    done = real and "-s0" not in unit
    return [
        Hop(
            "wiki search",
            Status.PASS if done else Status.FAIL,
            f"unit={unit or 'none'} bytes={len(body)}",
            "a canonical design unit whose body matches the returned preview",
            "" if done else short(found.get("error") or preview or "no result", 70),
        )
    ]


def data(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """A row the user's SQL wrote is readable from the same session, then dropped."""
    registry = servers()
    streamed, ok, observed = turn(
        ctx,
        "auto-research::data",
        f"Call run_sql exactly once with session_id 'portal_trace' and sql "
        f"'CREATE OR REPLACE TABLE {TABLE} AS SELECT {MARKER} AS marker'. Reply with only 'done'.",
    )
    read = mcp_call(
        registry["data"],
        "run_sql",
        {"session_id": "portal_trace", "sql": f"SELECT marker FROM {TABLE}"},
    )
    rows = read.get("rows") or []
    value = str(rows[0][0]) if rows and rows[0] else ""
    mcp_call(
        registry["data"],
        "run_sql",
        {"session_id": "portal_trace", "sql": f"DROP TABLE IF EXISTS {TABLE}"},
    )
    done = "run_sql" in ok and value == MARKER
    observed += f" marker={value or 'absent'}"
    return [hop("data sql row", done, observed, f"run_sql writes {MARKER}", streamed)]


def compliance(ctx: TraceContext, _portal: dict[str, Any]) -> list[Hop]:
    """The cited requirement is the part the live register serves, by id."""
    streamed, ok, observed = turn(
        ctx,
        "auto-compliance",
        f"Call compliance_requirement exactly once with requirement '{REQUIREMENT}'. Reply with "
        "only the id of the first part it returned.",
    )
    store = mcp_call(
        servers()["compliance"], "compliance_requirement", {"requirement": REQUIREMENT}
    )
    parts = store.get("parts") or []
    served = str(parts[0].get("id") or "") if parts else ""
    cited = bool(served) and served in streamed.stats.text
    done = "compliance_requirement" in ok and cited
    observed += f" served={served or 'none'} cited={cited}"
    return [hop("compliance requirement", done, observed, f"{served} in the answer", streamed)]


SECTIONS: tuple[tuple[str, str, Runner], ...] = (
    ("documents", "DOCUMENTS MCP", documents),
    ("memory", "MEMORY MCP", memory),
    ("rag", "RAG MCP", rag),
    ("wiki", "WIKI MCP", wiki),
    ("data", "DATA MCP", data),
    ("compliance", "COMPLIANCE MCP", compliance),
)

#: Each of these drives a seat through the Pipeline; run them by name, not in a bare sweep.
OPT_IN = frozenset(key for key, _title, _run in SECTIONS)
