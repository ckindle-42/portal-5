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

import logging

import httpx

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
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(f"{base_url}/v1/models")
            return resp.status_code == 200
    except Exception:
        return False
