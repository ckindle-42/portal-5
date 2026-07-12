"""Proactive context injection + salient memory write-back.

All three features reuse ``tool_registry.dispatch`` (never-raises, circuit-broken) to
call tools the model already has — ``recall``, ``kb_search``, ``remember`` — so
grounding and persistence no longer depend on the model choosing to call them.

Design mirrors ``_route_with_llm``: env feature flag + per-workspace opt-in, a short
hard timeout via ``asyncio.wait_for`` (dispatch's own 60s is too long for the hot
path), never-raises, metric-instrumented, graceful no-op on any failure.

  * ``inject_recalled_memory`` / ``inject_retrieved_context`` — read-only, run in the
    request preinject phase (handlers.py), inject a system context block.
  * ``schedule_writeback`` / ``writeback_memory`` — fire-and-forget, run once per turn
    from the non-streaming success path (non_streaming.py). Persists only *salient*
    USER statements (durable facts come from the user), gated by a salience filter so
    the store does not bloat.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from portal.platform.inference import tool_registry
from portal.platform.inference.router.metrics import (
    _auto_context_inject_total,
    _auto_context_latency_seconds,
)
from portal.platform.inference.router.workspaces import WORKSPACES

logger = logging.getLogger(__name__)

_AUTO_MEMORY_ENABLED = os.environ.get("AUTO_MEMORY_ENABLED", "true").lower() != "false"
_AUTO_RAG_ENABLED = os.environ.get("AUTO_RAG_ENABLED", "true").lower() != "false"
_AUTO_MEMORY_WRITEBACK_ENABLED = (
    os.environ.get("AUTO_MEMORY_WRITEBACK_ENABLED", "true").lower() != "false"
)
_TIMEOUT_MS = int(os.environ.get("AUTO_CONTEXT_TIMEOUT_MS", "1500"))
_TOP_K = int(os.environ.get("AUTO_CONTEXT_TOP_K", "4"))

# High-precision write-back triggers. A workspace may set memory_writeback_all: true
# to persist every user message instead (aggressive; relies on the memory tool to
# dedup). See DISCOVER & FINISH latitude for upgrading this to a small-model classifier.
_WRITEBACK_MARKERS = (
    "remember that",
    "remember this",
    "remember:",
    "please remember",
    "note that",
    "for future reference",
    "keep in mind",
    "don't forget",
    "make a note",
    "save this",
)

# Keep fire-and-forget write-back tasks referenced so they are not GC'd mid-flight.
_writeback_tasks: set[asyncio.Task] = set()


def _last_user_text(messages: list[dict], limit: int) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c[:limit]
            if isinstance(c, list):  # OpenAI multimodal content parts
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return str(part.get("text", ""))[:limit]
    return ""


def _extract_snippets(result: dict[str, Any]) -> list[str]:
    """Defensively pull text snippets from a recall/kb_search result.

    Tolerates the common shapes. Returns [] for an error dict or empty result. If a
    NON-empty, NON-error result cannot be parsed, raises ValueError so the acceptance
    gate surfaces a live-contract mismatch (honest-BLOCKED) rather than silently
    dropping grounding.
    """
    if not isinstance(result, dict) or "error" in result:
        return []
    for key in ("results", "memories", "matches", "documents", "hits"):
        items = result.get(key)
        if isinstance(items, list):
            out: list[str] = []
            for it in items:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    txt = it.get("text") or it.get("content") or it.get("snippet")
                    if txt:
                        out.append(str(txt))
            return out
    if isinstance(result.get("text"), str):
        return [result["text"]]
    if not result:
        return []
    raise ValueError(f"unrecognised tool result shape: keys={sorted(result)[:6]}")


def _inject_context_block(body: dict, header: str, items: list[str]) -> dict:
    if not items:
        return body
    block = header + "\n" + "\n".join(f"- {s}" for s in items if s)
    messages = list(body.get("messages", []))
    sys_i = next((i for i, m in enumerate(messages) if m.get("role") == "system"), None)
    if sys_i is not None:
        updated = dict(messages[sys_i])
        updated["content"] = (updated.get("content", "") + "\n\n" + block).lstrip()
        messages[sys_i] = updated
    else:
        messages = [{"role": "system", "content": block}] + messages
    return {**body, "messages": messages}


async def _dispatch_bounded(tool: str, args: dict, cid: str) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            tool_registry.dispatch(tool, args, request_id=cid),
            timeout=_TIMEOUT_MS / 1000.0,
        )
    except TimeoutError:
        logger.debug("auto-context: %s timed out after %dms — no-op", tool, _TIMEOUT_MS)
        return {"error": "timeout"}
    except Exception as e:
        logger.debug("auto-context: %s failed (%s) — no-op", tool, e)
        return {"error": str(e)}


async def inject_recalled_memory(workspace_id: str, body: dict, cid: str) -> dict:
    if not _AUTO_MEMORY_ENABLED:
        return body
    if not WORKSPACES.get(workspace_id, {}).get("inject_memory", False):
        return body
    query = _last_user_text(body.get("messages", []), 500)
    if not query:
        return body
    t0 = asyncio.get_event_loop().time()
    result = await _dispatch_bounded("recall", {"query": query, "k": _TOP_K}, cid)
    snippets = _extract_snippets(result)
    _auto_context_latency_seconds.labels(source="memory").observe(
        asyncio.get_event_loop().time() - t0
    )
    _auto_context_inject_total.labels(source="memory", outcome="hit" if snippets else "miss").inc()
    return _inject_context_block(body, "Relevant context from prior sessions:", snippets)


async def inject_retrieved_context(workspace_id: str, body: dict, cid: str) -> dict:
    if not _AUTO_RAG_ENABLED:
        return body
    if not WORKSPACES.get(workspace_id, {}).get("auto_rag", False):
        return body
    query = _last_user_text(body.get("messages", []), 500)
    if not query:
        return body
    t0 = asyncio.get_event_loop().time()
    result = await _dispatch_bounded("kb_search", {"query": query, "k": _TOP_K}, cid)
    snippets = _extract_snippets(result)
    _auto_context_latency_seconds.labels(source="rag").observe(asyncio.get_event_loop().time() - t0)
    _auto_context_inject_total.labels(source="rag", outcome="hit" if snippets else "miss").inc()
    return _inject_context_block(body, "Relevant information from the knowledge base:", snippets)


def _salient_user_text(messages: list[dict], workspace_id: str) -> str | None:
    """The user text worth persisting, or None. High-precision by default."""
    text = _last_user_text(messages, 2000)
    if not text:
        return None
    if WORKSPACES.get(workspace_id, {}).get("memory_writeback_all", False):
        return text
    low = text.lower()
    if any(mk in low for mk in _WRITEBACK_MARKERS):
        return text
    return None


async def writeback_memory(workspace_id: str, messages: list[dict], cid: str) -> None:
    """Persist a salient user statement via the remember tool. Never raises."""
    if not _AUTO_MEMORY_WRITEBACK_ENABLED:
        return
    if not WORKSPACES.get(workspace_id, {}).get("memory_writeback", False):
        return
    text = _salient_user_text(messages, workspace_id)
    if not text:
        return
    result = await _dispatch_bounded(
        "remember",
        {"text": text, "category": "auto_writeback", "tags": [workspace_id]},
        cid,
    )
    outcome = "error" if (isinstance(result, dict) and "error" in result) else "stored"
    _auto_context_inject_total.labels(source="writeback", outcome=outcome).inc()


def schedule_writeback(workspace_id: str, messages: list[dict], cid: str) -> None:
    """Kick off write-back without blocking the response path (fire-and-forget)."""
    if not _AUTO_MEMORY_WRITEBACK_ENABLED:
        return
    if not WORKSPACES.get(workspace_id, {}).get("memory_writeback", False):
        return
    try:
        task = asyncio.create_task(writeback_memory(workspace_id, list(messages or []), cid))
    except RuntimeError:
        return  # no running loop — skip silently
    _writeback_tasks.add(task)
    task.add_done_callback(_writeback_tasks.discard)
