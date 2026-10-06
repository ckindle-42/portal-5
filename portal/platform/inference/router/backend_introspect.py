"""Backend introspection seam — timeout disambiguation across engine types.

When a streaming/non-streaming request times out, the router needs to know
whether the backend is *busy* (model still generating → tell the user to
retry) or *down* (no model loaded → record an error and cascade to the next
candidate). Ollama answers this precisely with ``/api/ps`` (a loaded model
mid-generation is listed); other engines need their own probe.

This module is the single place that knows which probe applies to which
backend ``type`` — the streaming/non-streaming paths call
``model_still_running`` instead of hardcoding ``/api/ps`` (P5-FUT-013
Phase 1: oMLX has no ``/api/ps`` equivalent on its OpenAI surface; its
loaded/active state lives behind the admin API, which requires auth — see
the note in ``_omlx_engine_reachable``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from portal.platform.inference.omlx_auth import OmlxKeyAuth

logger = logging.getLogger(__name__)


async def model_still_running(backend_url: str, timeout_s: float = 5.0) -> bool:
    """Return True when the backend at ``backend_url`` should be treated as
    busy (request timed out but generation is likely still in progress),
    False when it should be treated as down/dead.

    ``backend_url`` is the full chat URL used for the request; the base is
    derived by stripping at ``/v1/`` exactly as the legacy call sites did.
    The backend ``type`` is resolved from the registry singleton (set by
    ``lifespan``) so call sites don't have to thread it through the
    streaming signatures; unknown URLs fall back to the legacy Ollama
    probe, preserving pre-seam behavior for every existing path.
    """
    base = backend_url.split("/v1/")[0]
    if _backend_type_for_url(base) == "omlx":
        return await _omlx_engine_reachable(base, timeout_s)
    # Ollama and every other type keep the legacy /api/ps semantics.
    return await _ollama_model_loaded(base, timeout_s)


def _backend_type_for_url(base_url: str) -> str:
    """Resolve a backend base URL to its registry ``type`` ("ollama" default).

    Uses the same lifespan-set registry singleton that
    ``validation._model_supports_tools`` already relies on. Matching by URL
    keeps the seam out of the streaming function signatures.
    """
    try:
        from portal.platform.inference.router import validation

        reg = validation.registry
        if reg is not None:
            needle = base_url.rstrip("/")
            for b in reg.list_backends():
                if b.url.rstrip("/") == needle:
                    return b.type
    except Exception:
        pass
    return "ollama"


async def _ollama_model_loaded(base_url: str, timeout_s: float) -> bool:
    """Legacy probe: True when /api/ps still lists a model after the timeout."""
    try:
        from portal.platform.inference.router.monitor import (
            wait_for_model_loaded as _wfml,
        )

        return await _wfml(timeout_s=timeout_s, poll_s=timeout_s, ollama_url=base_url)
    except Exception:
        return False


async def _omlx_engine_reachable(base_url: str, timeout_s: float) -> bool:
    """oMLX probe: engine reachable ⇒ treat as busy; unreachable ⇒ down.

    oMLX serves loaded-model state only via the authenticated admin API
    (``/admin/api/models``); wiring an admin key into the pipeline is B3
    scope. Until then the honest degraded semantic is a liveness check on
    the OpenAI surface: an engine that answers ``/v1/models`` is up and the
    timeout is almost certainly a long generation (single-user workloads,
    no queue dropping), so the user-facing "may still be generating" path
    applies; an engine that does not answer is down, and the caller
    cascades to the next candidate.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_s, auth=OmlxKeyAuth()) as client:
            resp = await client.get(f"{base_url}/v1/models")
            return resp.status_code == 200
    except Exception:
        return False


async def free_ollama_for_omlx(wait_s: float = 15.0) -> list[str]:
    """Unload Ollama's resident models (the intent router excepted); return their names.

    oMLX sizes its prefill ceiling from free memory and cannot reclaim what
    Ollama holds, so a model Ollama is still keeping warm (default 5 min) makes
    oMLX's memory guard reject a long prompt that would otherwise fit — and the
    request then cascades to the slower engine. Called only after such a
    rejection, so the cost (a reload if the user returns to that model) is paid
    only when the alternative is the fallback. The router model stays: it is
    small, pinned on purpose and evicting it breaks auto-routing.
    """
    from portal.platform.inference.router import validation
    from portal.platform.inference.router.routing import _LLM_ROUTER_MODEL

    reg = validation.registry
    if reg is None:
        return []
    urls = {b.url.rstrip("/") for b in reg.list_backends() if b.type == "ollama"}
    freed: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in sorted(urls):
            try:
                ps = (await client.get(f"{url}/api/ps")).json().get("models", [])
                names = [m["name"] for m in ps if m.get("name") != _LLM_ROUTER_MODEL]
                for name in names:
                    await client.post(f"{url}/api/generate", json={"model": name, "keep_alive": 0})
                deadline = time.monotonic() + wait_s
                while names and time.monotonic() < deadline:
                    ps = (await client.get(f"{url}/api/ps")).json().get("models", [])
                    if not {m["name"] for m in ps} & set(names):
                        break
                    await asyncio.sleep(0.5)
                freed.extend(names)
            except Exception as exc:
                logger.warning("Could not free Ollama memory at %s: %s", url, exc)
    return freed


#: Prompts at or above this size free Ollama's idle models before an oMLX
#: dispatch. The two engines share one unified-memory pool and oMLX cannot
#: reclaim what Ollama holds: measured 2026-10-06, an idle Ollama 35B shrank
#: oMLX's prefill ceiling to ~21 GB, so a ~24K-token prompt was rejected and a
#: ~38K one was admitted, then killed mid-prefill by the process-memory
#: enforcer — an error the client has already started receiving, so it cannot
#: be retried. Short prompts leave Ollama's models alone.
_FREE_OLLAMA_ABOVE_TOKENS = int(os.environ.get("OMLX_FREE_OLLAMA_ABOVE_TOKENS", "12000"))


def _approx_prompt_tokens(body: dict[str, Any]) -> int:
    """Cheap token estimate (about 3.5 characters per token, erring high)."""
    chars = 0
    for msg in body.get("messages") or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            chars += sum(len(p.get("text", "")) for p in content if isinstance(p, dict))
    return int(chars / 3.5)


async def make_room_for_omlx(backend: Any, body: dict[str, Any]) -> list[str]:
    """Free Ollama's idle models before a large prompt goes to oMLX; return what was freed."""
    if getattr(backend, "type", "") != "omlx":
        return []
    if _approx_prompt_tokens(body) < _FREE_OLLAMA_ABOVE_TOKENS:
        return []
    freed = await free_ollama_for_omlx()
    if freed:
        logger.info("Freed Ollama %s ahead of a large oMLX prompt", freed)
    return freed
